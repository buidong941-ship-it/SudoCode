#!/usr/bin/env python3
"""Replay ca nghi vấn của cổng v2 F1b (14/11, §8.11 của docs/PLAN/TRIEN-KHAI-LATENCY-EMIT-VA-DEV-2026-11-13.md). KHÔNG phải E2E.

Dựng lại trạng thái theo cách của b2_improve_probe.py, nhưng phiên mở giống run_eval.py (phiên phụ nạp CRM / seed rồi phiên thật):
  - lượt trước đích: ÉP hiểu (dựng từ trace của lần chạy làm tiền tố) + ÉP chuỗi bước planner đã ghi;
  - hết cuộc gọi trước: ÉP tóm tắt phiên = đúng chuỗi trong memory.db của lần chạy đó (vá core.llm.summarizer.summarize);
  - understand_record (nạp CRM) gọi thật MỘT lần cho mỗi câu, lưu memo ra file và dùng lại ở bản code kia (state giống nhau);
  - lượt đích: bắt nguyên đối số / prompt của bộ hiểu; "hội thoại gần đây" thay bằng đúng câu đã ghi của tiền tố;
    gọi thật K lần (DeepSeek: understand(); Jev: dựng lại phiên mỗi lần, lượt đích dùng planner_b2.jev_decide).
Điểm đo R1–R7 và quy tắc đọc: §8.11. Chạy lần lượt trên hai bản đóng băng (v37 rồi v36 sau freeze_apply --overlay):
    python scripts/f1b_replay_probe.py run --tag v37 --scenarios /tmp/suites/set19 --traces ref_full=... ref_base=... new_full=... \
        new_base=... --db ref_full=... new_full=... --memo <file> --out <dir> [--k 5] [--dry]
    python scripts/f1b_replay_probe.py compare --a <dir>/replay_v36.json --b <dir>/replay_v37.json --out <dir>"""
import argparse
import copy
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# (điểm, kịch bản, cuộc gọi, lượt, config, loại, các tiền tố)
POINTS = [
    ("R1", "GEN-T04-01", "call_1", 3, "full", "deepseek", ("ref", "new")),
    ("R2", "GEN-T04-01", "call_2", 1, "full", "deepseek", ("ref", "new")),
    ("R3", "GEN-T04-01", "call_2", 1, "full", "jev", ("new",)),
    ("R4", "GEN-T04-01", "call_2", 2, "full", "forced", ("new", "ref")),
    ("R5f", "GEN-T09-01", "call_1", 1, "full", "jev", ("ref",)),
    ("R5b", "GEN-T09-01", "call_1", 1, "baseline", "jev", ("new",)),
    ("R6", "BTCD7-007", "call_2", 2, "baseline", "deepseek", ("ref", "new")),
    ("R7a", "RT-03", "call_1", 2, "full", "forced", ("new",)),
    ("R7b", "BTCL-051", "call_2", 1, "full", "forced", ("new",)),
    ("R7c", "BTCD7-010", "call_2", 1, "full", "forced", ("new",)),
]
CFG = {"full": "full", "baseline": "baseline_no_memory"}


def load_rows(p):
    out = {}
    for ln in open(p, encoding="utf-8"):
        if ln.strip():
            r = json.loads(ln)
            out[(r["scenario_id"], r["call"], r["turn"])] = r
    return out


def db_sessions(p):
    if not p or not os.path.isfile(p):
        return {}
    c = sqlite3.connect(p)
    return {sid: {"summary": s, "open_questions": json.loads(oq or "[]")}
            for sid, s, oq in c.execute("select session_id, summary, open_questions_json from sessions")}


def run(a):
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="f1b_replay_"), "m.db").replace("\\", "/")
    os.environ["TOOL_TRANSPORT"] = "direct"
    os.environ.setdefault("RUN_PROFILE", "kaggle")
    os.environ.setdefault("RAG_MODE", "bm25")
    os.environ["LLM_CACHE"] = "off"
    from core.config import settings
    from core.llm import summarizer
    from core.llm.generator import Generator
    from core.llm.router import FLAGS, Router
    from harness import agent, audit, extractor, planner_b2, understanding as U
    from harness.loader import agent_view, load_scenarios
    # audit hậu kỳ chỉ ghi trace (claims / questions), không đổi trạng thái phiên; replay CPU không có Qwen → bỏ để không treo
    audit.run = lambda *args, **kw: ([], [])
    from harness.memory import open_memory
    from harness.tools import ToolBox

    if not a.dry and not a.rerender and not (settings.typesafe_api_key and os.environ.get("DEEPSEEK_API_KEY")):
        print("THIẾU DEEPSEEK_API_KEY / TYPESAFE_API_KEY: không replay (không giả lập)")
        sys.exit(2)
    traces = {k: load_rows(v) for k, v in (x.split("=", 1) for x in a.traces)}
    dbs = {k: db_sessions(v) for k, v in (x.split("=", 1) for x in a.db)}
    scens = {s["scenario_id"]: s for s in load_scenarios(a.scenarios)}
    memo = json.load(open(a.memo, encoding="utf-8")) if os.path.isfile(a.memo) else {}
    real_record, real_understand, real_call = U.understand_record, U.understand, U._call
    CUR = {"live": False, "replay": [], "skipped": [], "log": [], "missing": []}

    def memo_record(summary, today):
        k = f"{today}|{summary}"
        if k not in memo and a.rerender:
            # rerender (D1, 14/11): không gọi model; tóm tắt CRM chưa có trong memo → không nạp fact nào (giống nhau ở mọi bản), ghi lại
            CUR.setdefault("record_skipped", []).append(today)
            return {}, {"calls": 0, "rerender_no_api": True}
        if k not in memo:
            s, m = real_record(summary, today)
            memo[k] = [s, {kk: vv for kk, vv in (m or {}).items() if isinstance(vv, (int, float, str, bool, list, dict, type(None)))}]
        s, m = memo[k]
        return copy.deepcopy(s), copy.deepcopy(m)

    def rebuild_u(row, text, today):
        t = row.get("understanding") or {}
        rule_slots = extractor.customer_slots_rules(text, today) or {}
        obs, slots = [], {}
        for slot in t.get("observations") or []:
            stance = (t.get("observation_stance") or {}).get(slot, "stated")
            if slot == "claimed_price_vnd" and rule_slots.get("claimed_prices"):
                # understand() gom claimed_price_vnd vào slots["claimed_prices"]; luật trả sẵn danh sách claimed_prices
                for v in rule_slots["claimed_prices"]:
                    obs.append({"slot": slot, "span": str(v), "value": v, "stance": stance, "subject": "self"})
                    slots.setdefault("claimed_prices", []).append(v)
            elif slot in rule_slots and rule_slots[slot] not in (None, ""):
                v = rule_slots[slot]
                obs.append({"slot": slot, "span": str(v), "value": v, "stance": stance, "subject": "self"})
                slots[slot] = v
            else:
                CUR["missing"].append({"turn": f"{row.get('call')}/t{row.get('turn')}", "slot": slot})
        ev = dict(t.get("request_evidence") or {})
        items = [{"kind": it["kind"], "evidence": ev.get(it["kind"], ""), "target_ref": it.get("target_ref"), "target_invalid": False,
                  "condition": ({"type": it["condition"], "span": ""} if it.get("condition") else None)} for it in t.get("request_items") or []]
        on = set(t.get("flags") or [])
        asks = list(t.get("asks") or [])
        refs = {k: bool((t.get("refs") or {}).get(k)) for k in ("previous_contact", "existing_order", "previous_address", "closing")}
        amb = (t.get("ambiguity") or {}).get("level") or "none"
        act = t.get("response") or "none"
        withdrawn = [{"kind": k, "evidence": ""} for k in t.get("withdrawn") or []]
        requests = sorted({i["kind"] for i in items})
        route = {"intent": t.get("intent") or "greeting_or_other", "confidence": 1.0, "probabilities": {},
                 "flags": {k: (1.0 if k in on else 0.0) for k in FLAGS},
                 "understanding": {"requests": requests, "asks_question": bool(t.get("asks_question")), "safety": list(t.get("safety") or []),
                                   "asks": asks, "response": act, "refs": refs, "ambiguity": amb, "withdrawn": [w["kind"] for w in withdrawn]}}
        return {"route": route, "slots": slots, "observations": obs, "requests": requests, "request_items": items, "request_evidence": ev,
                "withdrawn": withdrawn, "response": {"act": act, "evidence": ""}, "asks": asks, "refs": refs,
                "safety": list(t.get("safety") or []), "asks_question": bool(t.get("asks_question")),
                "ambiguity": {"level": amb, "reason": ""}, "meta": {"ms": 0, "attempts": 1, "dropped": [], "rebuilt_from_trace": True}}

    def rec_steps(row):
        return [d.get("step") for d in ((row.get("planner") or {}).get("loop") or {}).get("decisions") or [] if d.get("step")]


    def decider(state, opts):
        if CUR["live"]:
            t0 = time.perf_counter()
            if a.dry:
                st = next((s for s in opts["step"] if s.startswith(("answer_ask:", "read_quote:"))), "finish")
                d = {"step": st, "shown": opts["display"].get(st), "confidence": None}
            else:
                d = planner_b2.jev_decide(state, opts)
            CUR["log"].append({"step": d.get("step"), "shown": d.get("shown"), "ms": int((time.perf_counter() - t0) * 1000),
                               "options": [opts["display"][s] for s in opts["step"]]})
            return d
        while CUR["replay"]:
            st = CUR["replay"].pop(0)
            if st in opts["step"]:
                return {"step": st, "backend": "replay", "ms": 0}
            CUR["skipped"].append(st)
        x = next((s for s in opts["step"] if s.startswith("answer_ask:")), None)
        return {"step": x or "finish", "backend": "replay", "ms": 0}

    def replay(point, prefix, live_turn):
        """Chạy tiền tố tới lượt đích. live_turn: None (ép cả lượt đích) | 'jev'. Trả (row_đích, args bộ hiểu ở lượt đích, drift)."""
        pid, sid, call, turn, cfg, kind, _ = point
        rows = traces[f"{prefix}_{cfg}"]
        sess_db = dbs.get(f"{prefix}_{cfg}") or {}
        view = agent_view(scens[sid])
        mem = open_memory(f"replay:{a.tag}:{pid}:{prefix}:{time.time_ns()}", read_enabled=(cfg == "full"))
        mem.wipe()
        ToolBox.reset_world()
        cap, drift = {}, []
        CUR["missing"] = []
        for c in view["calls"]:
            def summ(kind_, facts, history, allowed, backend, max_chars, _c=c["call"]):
                rec = sess_db.get(f"{sid}:{_c}")
                if not rec:
                    return None
                s = rec["summary"]
                return {"summary": s.split("): ", 1)[1] if "): " in s else s, "open_questions": rec["open_questions"], "source": "replay"}
            mk = lambda: agent.CallSession(memory=mem, today=c["date"], call_name=c["call"], session_id=f"{sid}:{c['call']}",  # noqa: E731
                                           channel=c["channel"], channel_identity=c["channel_identity"],
                                           phone=(view["phone"] if c["channel"] == "hotline" or c["seed_history"] else None),
                                           input_mode=c["input_mode"], router=Router("rules"), generator=Generator("offline"),
                                           config=CFG[cfg], planner_variant="b2_jev", planner_decider=decider)
            with patch.object(U, "understand_record", memo_record):
                pre = mk()
                pre.start()
                if c["seed_history"] and pre.customer:
                    for h in c["seed_history"]:
                        pre.import_old_session(h, h.get("customer_id") or pre.customer["customer_id"])
                pre.tools.take_log()
                sess = mk()
                sess.start()
            for i, text in enumerate(c["turns"], start=1):
                key = (sid, c["call"], i)
                row = rows[key]
                u = rebuild_u(row, text, c["date"])
                target = (c["call"], i) == (call, turn)
                CUR.update(live=bool(target and live_turn == "jev"), replay=[] if (target and live_turn == "jev") else rec_steps(row),
                           skipped=[], log=[])

                def fake_understand(t_, today_, recent_, summary_="", asked_=None, state_ctx=None, _u=u, _target=target):
                    if _target:
                        cap.update(text=t_, today=today_, summary=summary_, asked=asked_, state_ctx=copy.deepcopy(state_ctx))
                    return json.loads(json.dumps(_u))
                with patch.object(U, "understand", fake_understand), patch.object(summarizer, "summarize", summ):
                    r = sess.turn(text)
                if not target:
                    if r["goals"] != row["goals"]:
                        drift.append({"turn": f"{c['call']}/t{i}", "goals_trace": row["goals"], "goals_replay": r["goals"]})
                    continue
                prev = [rows[(sid, c["call"], j)] for j in range(1, i)]
                rec_hist = []
                for p in prev:
                    rec_hist += [{"role": "customer", "text": p.get("customer_text")}, {"role": "agent", "text": p.get("agent_text")}]
                cap["recent"] = rec_hist[-6:]
                cap["recent_replay"] = sess.history[:-2][-6:]
                cap["slots_missing"] = list(CUR["missing"])
                return r, cap, drift, list(CUR["skipped"]), list(CUR["log"])
            with patch.object(summarizer, "summarize", summ):
                sess.end()
        raise RuntimeError("target turn not reached")

    def u_view(x):
        return {"intent": x["route"]["intent"], "asks": sorted(x.get("asks") or []), "response": (x.get("response") or {}).get("act"),
                "items": sorted(i["kind"] for i in x.get("request_items") or [])}

    def prompt_of(cap):
        got = {}

        def grab(prompt, schema, max_tokens):
            got["p"] = prompt
            raise RuntimeError("captured")
        with patch.object(U, "_call", grab):
            try:
                real_understand(cap["text"], cap["today"], cap["recent"], cap["summary"], cap["asked"], state_ctx=cap["state_ctx"])
            except RuntimeError:
                pass
        return got.get("p", "")

    def replay_all(sid, cfg, prefix):
        """D1 (14/11): dựng lại MỌI lượt của kịch bản bằng hiểu + bước đã ghi (không gọi model); ghi goals / câu từng lượt."""
        rows = traces[f"{prefix}_{cfg}"]
        sess_db = dbs.get(f"{prefix}_{cfg}") or {}
        view = agent_view(scens[sid])
        mem = open_memory(f"rerender:{a.tag}:{sid}:{cfg}:{time.time_ns()}", read_enabled=(cfg == "full"))
        mem.wipe()
        ToolBox.reset_world()
        CUR["record_skipped"] = []
        out = []
        for c in view["calls"]:
            def summ(kind_, facts, history, allowed, backend, max_chars, _c=c["call"]):
                rec = sess_db.get(f"{sid}:{_c}")
                if not rec:
                    return None
                s = rec["summary"]
                return {"summary": s.split("): ", 1)[1] if "): " in s else s, "open_questions": rec["open_questions"], "source": "replay"}
            mk = lambda: agent.CallSession(memory=mem, today=c["date"], call_name=c["call"], session_id=f"{sid}:{c['call']}",  # noqa: E731
                                           channel=c["channel"], channel_identity=c["channel_identity"],
                                           phone=(view["phone"] if c["channel"] == "hotline" or c["seed_history"] else None),
                                           input_mode=c["input_mode"], router=Router("rules"), generator=Generator("offline"),
                                           config=CFG[cfg], planner_variant="b2_jev", planner_decider=decider)
            with patch.object(U, "understand_record", memo_record):
                pre = mk()
                pre.start()
                if c["seed_history"] and pre.customer:
                    for h in c["seed_history"]:
                        pre.import_old_session(h, h.get("customer_id") or pre.customer["customer_id"])
                pre.tools.take_log()
                sess = mk()
                sess.start()
            for i, text in enumerate(c["turns"], start=1):
                row = rows.get((sid, c["call"], i))
                if row is None:
                    out.append({"turn": f"{c['call']}/t{i}", "error": "missing_in_trace"})
                    continue
                CUR["missing"] = []
                u = rebuild_u(row, text, c["date"])
                CUR.update(live=False, replay=rec_steps(row), skipped=[], log=[])

                def fake_understand(t_, today_, recent_, summary_="", asked_=None, state_ctx=None, _u=u):
                    return json.loads(json.dumps(_u))
                with patch.object(U, "understand", fake_understand), patch.object(summarizer, "summarize", summ):
                    r = sess.turn(text)
                out.append({"turn": f"{c['call']}/t{i}", "goals": r.get("goals"), "goals_trace": row.get("goals"),
                            "text": r.get("agent_text"), "text_trace": row.get("agent_text"),
                            "skipped": list(CUR["skipped"]), "slots_missing": [m["slot"] for m in CUR["missing"]]})
            with patch.object(summarizer, "summarize", summ):
                sess.end()
        return {"turns": out, "crm_record_skipped": len(CUR.get("record_skipped") or [])}

    if a.rerender:
        res = {}
        for cfg in ("full", "baseline"):
            ids = sorted({k[0] for k in traces.get(f"new_{cfg}", {})})
            for sid in ids:
                try:
                    res[f"{cfg}:{sid}"] = replay_all(sid, cfg, "new")
                except Exception as e:  # noqa: BLE001
                    res[f"{cfg}:{sid}"] = {"error": f"{type(e).__name__}: {str(e)[:200]}", "traceback": traceback.format_exc()[-1500:]}
                print(json.dumps({"rerender": f"{cfg}:{sid}", "error": res[f"{cfg}:{sid}"].get("error")}, ensure_ascii=False), flush=True)
        os.makedirs(a.out, exist_ok=True)
        json.dump({"tag": a.tag, "source": "new (trace F1b v37)", "results": res},
                  open(os.path.join(a.out, f"rerender_{a.tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        errs = [k for k, v in res.items() if v.get("error")]
        print(json.dumps({"scenarios": len(res), "errors": errs}), flush=True)
        if errs:
            raise SystemExit(3)
        return

    results = []
    for pt in POINTS:
        pid, sid, call, turn, cfg, kind, prefixes = pt
        for prefix in prefixes:
            rec = {"point": pid, "case": f"{sid}/{call}/t{turn}", "config": cfg, "kind": kind, "prefix": prefix, "tag": a.tag}
            row_rec = traces[f"{prefix}_{cfg}"][(sid, call, turn)]
            rec["recorded"] = {"understanding": {k: (row_rec.get("understanding") or {}).get(k) for k in ("intent", "asks", "response")},
                               "steps": rec_steps(row_rec), "goals": row_rec.get("goals"), "text": row_rec.get("agent_text")}
            try:
                if kind in ("deepseek", "forced"):
                    r, cap, drift, skipped, _ = replay(pt, prefix, None)
                    p = prompt_of(cap)
                    rec.update(drift=drift, replay_skipped=skipped, prompt_sha=hashlib.sha256(p.encode("utf-8")).hexdigest(),
                               prompt_tail=p[-1500:], summary_in_prompt=cap["summary"], asked=cap["asked"],
                               recent_matches_replay=[h.get("text") for h in cap["recent"]] == [h.get("text") for h in cap["recent_replay"]],
                               forced_text=r.get("agent_text"), forced_goals=r.get("goals"), slots_missing=cap.get("slots_missing"))
                    if kind == "deepseek":
                        outs = []
                        for _ in range(a.k):
                            if a.dry:
                                outs.append({"dry": True})
                                continue
                            try:
                                outs.append(u_view(real_understand(cap["text"], cap["today"], cap["recent"], cap["summary"], cap["asked"],
                                                                   state_ctx=cap["state_ctx"])))
                            except Exception as e:  # noqa: BLE001 — lỗi API ghi riêng, không tính vào tỉ lệ
                                outs.append({"api_error": f"{type(e).__name__}: {str(e)[:120]}"})
                        rec["live"] = outs
                else:
                    outs = []
                    for _ in range(a.k):
                        try:
                            r, cap, drift, skipped, log = replay(pt, prefix, "jev")
                            outs.append({"steps": [x["step"] for x in log], "goals": r.get("goals"), "text": (r.get("agent_text") or "")[:300],
                                         "quoted": [(t.get("args") or {}).get("sku") for t in r.get("tool_calls") or []
                                                    if t.get("name") == "pricing.get_quote"], "drift": drift, "slots_missing": cap.get("slots_missing")})
                        except Exception as e:  # noqa: BLE001
                            outs.append({"api_error": f"{type(e).__name__}: {str(e)[:160]}"})
                    rec["live"] = outs
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                rec["traceback"] = traceback.format_exc()[-1500:]
            results.append(rec)
            print(json.dumps({k: rec.get(k) for k in ("point", "prefix", "prompt_sha", "error")}, ensure_ascii=False)[:300], flush=True)
    os.makedirs(a.out, exist_ok=True)
    json.dump(memo, open(a.memo, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"tag": a.tag, "k": a.k, "dry": a.dry, "results": results},
              open(os.path.join(a.out, f"replay_{a.tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    errs = [r for r in results if r.get("error")]
    print(json.dumps({"points": len(results), "errors": len(errs)}), flush=True)
    if errs:
        raise SystemExit(3)


# ------------------------------------------------------------------------------------------ so sánh hai bản + đọc theo quy tắc
GIFT_DUP = re.compile(r"không có quà tặng kèm")
GIFT_STATUS = re.compile(r"không kèm quà tặng")


def compare(a):
    A, B = json.load(open(a.a, encoding="utf-8")), json.load(open(a.b, encoding="utf-8"))
    key = lambda r: (r["point"], r["prefix"])  # noqa: E731
    ra, rb = {key(r): r for r in A["results"]}, {key(r): r for r in B["results"]}
    out = {"versions": [A["tag"], B["tag"]], "points": []}
    for k in sorted(set(ra) | set(rb)):
        x, y = ra.get(k) or {}, rb.get(k) or {}
        e = {"point": k[0], "prefix": k[1], "case": (x or y).get("case"), "config": (x or y).get("config"), "kind": (x or y).get("kind"),
             "recorded": (y or x).get("recorded"), "errors": [z.get("error") for z in (x, y) if z.get("error")]}
        if e["kind"] in ("deepseek", "forced"):
            e["prompt_same_v36_v37"] = bool(x.get("prompt_sha")) and x.get("prompt_sha") == y.get("prompt_sha")
            e["prompt_sha"] = {A["tag"]: (x.get("prompt_sha") or "")[:12], B["tag"]: (y.get("prompt_sha") or "")[:12]}
        if e["kind"] == "deepseek":
            e["live"] = {A["tag"]: x.get("live"), B["tag"]: y.get("live")}
        if e["kind"] == "jev":
            e["live"] = {A["tag"]: x.get("live"), B["tag"]: y.get("live")}
        if e["kind"] == "forced":
            e["forced_text"] = {A["tag"]: x.get("forced_text"), B["tag"]: y.get("forced_text")}
            e["forced_goals"] = {A["tag"]: x.get("forced_goals"), B["tag"]: y.get("forced_goals")}
        e["drift"] = {A["tag"]: x.get("drift"), B["tag"]: y.get("drift")}
        out["points"].append(e)
    # prompt giữa hai tiền tố (cùng bản) — ảnh hưởng history
    for tag, R in ((A["tag"], ra), (B["tag"], rb)):
        for p in ("R1", "R2", "R6"):
            if (p, "ref") in R and (p, "new") in R:
                out.setdefault("prompt_ref_vs_new", {}).setdefault(p, {})[tag] = R[(p, "ref")].get("prompt_sha") == R[(p, "new")].get("prompt_sha")
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "replay_compare.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"points": len(out["points"]), "prompt_ref_vs_new": out.get("prompt_ref_vs_new")}, ensure_ascii=False))


# ------------------------------------------------------------------------------------------ D1 (14/11): tiêu chí CHỐT TRƯỚC khi chạy
GIFT_NOTE = " Hiện mẫu này không có quà tặng kèm ạ."
EXP_NOTE = " Chương trình Tặng 1 màng lọc khi mua AirPure X/Y đã hết hạn rồi ạ."
D1_CHANGE = {("full", "RT-03", "call_1/t2"): [GIFT_NOTE], ("full", "RT-03", "call_1/t3"): [GIFT_NOTE],
             ("baseline", "RT-03", "call_1/t2"): [GIFT_NOTE], ("baseline", "RT-03", "call_1/t3"): [GIFT_NOTE],
             ("full", "BTCD7-010", "call_2/t1"): [GIFT_NOTE], ("full", "BTCL-051", "call_2/t1"): [EXP_NOTE, GIFT_NOTE]}
D1_KEEP = {("full", "GEN-T02-01", "call_2/t2"): "không có quà tặng kèm", ("baseline", "GEN-T02-01", "call_2/t2"): "không có quà tặng kèm",
           ("full", "V3-141", "call_2/t1"): "không có quà tặng kèm", ("full", "BTCL-051", "call_2/t2"): "đã hết hạn rồi ạ",
           ("full", "GEN-T05-01", "call_2/t2"): "đã hết hạn rồi ạ", ("baseline", "GEN-T05-01", "call_2/t2"): "đã hết hạn rồi ạ"}


def rerender_compare(a):
    V = {}
    for tag, p in (("v36", a.v36), ("v37", a.v37), ("v38", a.v38)):
        d = json.load(open(p, encoding="utf-8"))
        V[tag] = {}
        for key, sc in d["results"].items():
            cfg, sid = key.split(":", 1)
            for t in sc.get("turns") or []:
                V[tag][(cfg, sid, t["turn"])] = t
    keys = sorted(set(V["v37"]) | set(V["v38"]))
    txt = lambda tag, k: (V[tag].get(k) or {}).get("text") or ""  # noqa: E731
    changed = sorted(k for k in keys if txt("v37", k) != txt("v38", k))
    goals_diff = sorted(k for k in keys if (V["v37"].get(k) or {}).get("goals") != (V["v38"].get(k) or {}).get("goals"))
    c3 = {}
    for k, drop in D1_CHANGE.items():
        want = txt("v37", k)
        present = [x for x in drop if x in want]
        for x in drop:
            want = want.replace(x, "")
        c3["/".join(k)] = {"v37_had_dup": present == drop, "v38_equals_v37_minus_dup": txt("v38", k) == want,
                           "v38_keeps_gift_status": "không kèm quà tặng" in txt("v38", k), "v37": txt("v37", k), "v38": txt("v38", k),
                           "v36": txt("v36", k)}
    c4 = {"/".join(k): {"v37_has": s in txt("v37", k), "v38_same": txt("v38", k) == txt("v37", k), "v38": txt("v38", k)}
          for k, s in D1_KEEP.items()}
    rt10 = [k for k in keys if k[1] == "RT-10" and k[2].startswith("call_2")]
    both = [k for k in keys if "không có quà tặng kèm" in txt("v38", k) and "không kèm quà tặng" in txt("v38", k)]
    crit = {
        "C1_goals_v38_eq_v37_all_turns": not goals_diff,
        "C2_changed_turns_eq_D1_set": set(changed) == set(D1_CHANGE),
        "C3_D1_turns_exact_removal": all(v["v37_had_dup"] and v["v38_equals_v37_minus_dup"] and v["v38_keeps_gift_status"] for v in c3.values()),
        "C4_keep_turns_unchanged_with_sentence": all(v["v37_has"] and v["v38_same"] for v in c4.values()),
        "C4b_RT10_c2_unchanged": bool(rt10) and all(txt("v37", k) == txt("v38", k) for k in rt10),
        "C5_no_turn_with_both_gift_sentences_v38": not both,
    }
    fid = {tag: {"turns": len(V[tag]),
                 "text_eq_trace": sum(1 for t in V[tag].values() if t.get("text") == t.get("text_trace")),
                 "goals_eq_trace": sum(1 for t in V[tag].values() if t.get("goals") == t.get("goals_trace")),
                 "turns_slots_missing": sorted("/".join(k) + ":" + ",".join(t["slots_missing"]) for k, t in V[tag].items() if t.get("slots_missing")),
                 "steps_skipped": sorted("/".join(k) for k, t in V[tag].items() if t.get("skipped"))} for tag in V}
    out = {"criteria": crit, "pass": all(crit.values()), "changed_v37_v38": ["/".join(k) for k in changed],
           "goals_diff_v37_v38": ["/".join(k) for k in goals_diff], "d1_turns": c3, "keep_turns": c4,
           "both_gift_sentences_v38": ["/".join(k) for k in both],
           "changed_v36_v37": ["/".join(k) for k in keys if txt("v36", k) != txt("v37", k)], "fidelity": fid}
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "d1_check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"criteria": crit, "pass": out["pass"], "changed_v37_v38": out["changed_v37_v38"]}, ensure_ascii=False))
    if not out["pass"]:
        raise SystemExit(4)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tag", required=True)
    r.add_argument("--scenarios", required=True)
    r.add_argument("--traces", nargs="+", required=True)
    r.add_argument("--db", nargs="*", default=[])
    r.add_argument("--memo", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--k", type=int, default=5)
    r.add_argument("--dry", action="store_true")
    r.add_argument("--rerender", action="store_true", help="D1: dựng lại mọi lượt bộ trace 'new_*' bằng hiểu + bước đã ghi, không gọi model")
    c = sub.add_parser("compare")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.add_argument("--out", required=True)
    rc = sub.add_parser("rerender-compare")
    for x in ("--v36", "--v37", "--v38", "--out"):
        rc.add_argument(x, required=True)
    a = ap.parse_args()
    {"run": run, "compare": compare, "rerender-compare": rerender_compare}[a.cmd](a)


if __name__ == "__main__":
    main()
