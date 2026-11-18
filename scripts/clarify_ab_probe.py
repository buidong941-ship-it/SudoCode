"""Thử CHẨN ĐOÁN (12/11, người dùng yêu cầu): Jev có hiểu sai nghĩa `clarify` không — trên đúng các lượt B2 v6 dừng `no_progress`
(clarify lặp) ở V3 holdout. KHÔNG phải bằng chứng khái quát, KHÔNG thay số holdout v6, KHÔNG sửa runtime chính.

So sánh trên CÙNG trạng thái, CÙNG output DeepSeek, CÙNG model Jev, CÙNG tập lựa chọn nghiệp vụ; chỉ đổi TÊN / MÔ TẢ bước:
  A = tên / mô tả hiện tại của runtime (harness/planner_b2.options);
  B = tên / mô tả phân biệt rõ ba nghĩa: ĐỌC TOOL (read_tool_*), HỎI KHÁCH bổ sung thông tin còn thiếu của yêu cầu
      (ask_customer_missing_info:R#), HỎI KHÁCH nói lại khi câu mơ hồ (ask_customer_to_rephrase); trả lời câu hỏi
      (answer_customer_question:<chủ đề>) ghi rõ executor tự hỏi khách mẫu / nhu cầu nếu chưa rõ sản phẩm (h_recommend /
      ask_product là hành vi CÓ SẴN của handler). Không bỏ clarify khỏi danh sách, không thêm / bớt bước, không ép đọc kho.
  R = phát lại đúng chuỗi bước Jev đã ghi trong trace ở lượt lỗi (kiểm độ khớp của phần dựng lại).

DỰNG LẠI TRẠNG THÁI (trace không đủ để tái tạo chính xác — ghi rõ):
  - Phát lại kịch bản từ đầu tới lượt lỗi, KHÔNG gọi model nào trước lượt lỗi: output bộ hiểu lấy từ trace B2 v6 (intent, flags,
    requests + evidence (chữ số đã che #), request_items (kind / target_ref / loại điều kiện), asks, refs, response, withdrawn,
    safety, ambiguity, observation slot + stance); bước Jev các lượt trước = đúng chuỗi `step` trong trace; tool = mock BTC.
  - GIẢ ĐỊNH 1: trace không lưu GIÁ TRỊ slot / span (PII) → giá trị slot DeepSeek đã quan sát được dựng lại bằng parser luật
    (`extractor.customer_slots_rules`, chỉ luật) trên câu khách gốc; slot parser không tách được thì bỏ (ghi `slots_missing`).
  - GIẢ ĐỊNH 4: tóm tắt phiên cuối cuộc (episodic) dùng template (generator offline) thay vì Qwen như bản gốc; state Jev không
    đưa nội dung tóm tắt vào, nhưng brief cuộc sau có thể khác ở phần văn bản tóm tắt.
  - GIẢ ĐỊNH 2: span điều kiện / evidence dùng bản trong trace (chữ số đã che) — không ảnh hưởng ra quyết định ở các lượt này
    (không có yêu cầu điều kiện).
  - GIẢ ĐỊNH 3: profile đầu cuộc gọi (call_brief.profile_facts trong trace) được nạp lại vào known / carried như bản gốc; CRM
    import (DeepSeek) không gọi lại.
  - Audit (Jev question / Qwen claim) và compose không ảnh hưởng planner → stub.
  - Kiểm độ khớp: (i) bước đầu tiên đã ghi phải có trong danh mục dựng lại; (ii) chạy R phải cho cùng goals / stop như trace.

Mỗi fixture: R ×1, rồi A/B mỗi bên 3 lần, đảo thứ tự (A,B), (B,A), (A,B). Jev thật (TYPESAFE_API_KEY), CPU.
Dùng: python scripts/clarify_ab_probe.py <trace.jsonl> <scenarios_dir> <out_dir> [--dry]   (--dry: bộ quyết định giả, không API)
"""
import json
import os
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
TRACE, SCEN_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
DRY = "--dry" in sys.argv
os.makedirs(OUT, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="clarify_ab_"), "m.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "kaggle")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import FLAGS, Router  # noqa: E402
from harness import agent, audit, extractor, planner_b2, understanding as U  # noqa: E402
from harness.loader import agent_view, load_scenarios  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402

if not DRY and not settings.typesafe_api_key:
    print("THIẾU TYPESAFE_API_KEY: không chạy (không giả lập Jev)")
    sys.exit(2)

FIXTURES = [("V3-001", "call_1", 1), ("V3-001", "call_1", 2), ("V3-008", "call_2", 2), ("V3-009", "call_2", 2),
            ("V3-038", "call_2", 1), ("V3-055", "call_1", 3), ("V3-055", "call_1", 4), ("V3-056", "call_1", 1),
            ("V3-057", "call_1", 1), ("V3-057", "call_1", 4), ("V3-058", "call_1", 1), ("V3-060", "call_2", 1),
            ("V3-063", "call_2", 1), ("V3-066", "call_2", 1)]

# ---------------------------------------------------------------------- dữ liệu trace
ROWS = {}
for line in open(TRACE, encoding="utf-8"):
    r = json.loads(line)
    ROWS[(r["scenario_id"], r["call"], r["turn"])] = r
SCENS = {s["scenario_id"]: s for s in load_scenarios(SCEN_DIR)}


def recorded_steps(row):
    return [d.get("step") for d in ((row.get("planner") or {}).get("loop") or {}).get("decisions") or [] if d.get("step")]


def rebuild_u(row, text, today):
    """Output bộ hiểu dựng lại từ trace (xem GIẢ ĐỊNH ở đầu file). → (u, slots_missing)."""
    t = row.get("understanding") or {}
    rule_slots = extractor.customer_slots_rules(text, today) or {}
    obs, slots, missing = [], {}, []
    for slot in t.get("observations") or []:
        stance = (t.get("observation_stance") or {}).get(slot, "stated")
        if slot in rule_slots and rule_slots[slot] not in (None, ""):
            v = rule_slots[slot]
            obs.append({"slot": slot, "span": str(v), "value": v, "stance": stance, "subject": "self"})
            slots[slot] = v
        else:
            missing.append(slot)
    ev = dict(t.get("request_evidence") or {})
    items = [{"kind": it["kind"], "evidence": ev.get(it["kind"], ""), "target_ref": it.get("target_ref"),
              "target_invalid": False, "condition": ({"type": it["condition"], "span": ""} if it.get("condition") else None)}
             for it in t.get("request_items") or []]
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
    u = {"route": route, "slots": slots, "observations": obs, "requests": requests, "request_items": items, "request_evidence": ev,
         "withdrawn": withdrawn, "response": {"act": act, "evidence": ""}, "asks": asks, "refs": refs,
         "safety": list(t.get("safety") or []), "asks_question": bool(t.get("asks_question")),
         "ambiguity": {"level": amb, "reason": ""}, "meta": {"ms": 0, "attempts": 1, "dropped": [], "rebuilt_from_trace": True}}
    return u, missing


# ---------------------------------------------------------------------- tên / mô tả B
def name_b(step):
    a, rq, tg = planner_b2.parse_step(step)
    return {"read_quote": f"read_tool_quote:{tg}", "read_stock": f"read_tool_stock:{tg}", "read_order": "read_tool_orders",
            "check_window": f"read_tool_return_window:{tg}", "read_policy": "read_tool_policy_docs",
            "answer_ask": f"answer_customer_question:{str(tg)[4:]}",
            "commit_request": f"execute_request:{rq}" + (f"@{tg}" if tg else ""),
            "clarify": f"ask_customer_missing_info:{rq}" if rq else "ask_customer_to_rephrase",
            "finish": "finish_turn"}[a]


def desc_b(step, desc_a):
    a, rq, _ = planner_b2.parse_step(step)
    if a in ("read_quote", "read_stock", "read_order", "check_window", "read_policy"):
        return "ĐỌC TOOL / TÀI LIỆU để lấy thông tin, KHÔNG hỏi khách: " + desc_a
    if a == "answer_ask":
        return desc_a + " — nếu câu hỏi chưa gắn được sản phẩm, bước này tự hỏi khách mẫu nào / nhu cầu để trả lời"
    if a == "clarify" and rq:
        return (f"HỎI KHÁCH bổ sung thông tin CÒN THIẾU của yêu cầu {rq} rồi kết thúc lượt — chỉ dùng khi mức sẵn sàng của {rq} là "
                f"thiếu thông tin, điều kiện chưa thỏa hoặc bị cấm; nếu chỉ thiếu giá / kho / đơn thì dùng bước ĐỌC TOOL, nếu {rq} "
                f"đã đủ để thử thì dùng execute_request")
    if a == "clarify":
        return ("HỎI KHÁCH nói lại vì câu khách mơ hồ / không hiểu được rồi kết thúc lượt — không dùng để tìm thông tin (dùng ĐỌC "
                "TOOL) hay để trả lời câu hỏi (dùng answer_customer_question)")
    return desc_a


def to_b(opts):
    back = {name_b(s): s for s in opts["step"]}
    return {"step": list(back), "desc": {name_b(s): desc_b(s, opts["desc"][s]) for s in opts["step"]}}, back


# ---------------------------------------------------------------------- bộ quyết định
CUR = {"key": None, "mode": None, "target": None, "replay": []}
LOG = []


def dry_pick(opts):
    for p in ("answer_ask:", "read_quote:", "commit_request:", "finish"):
        x = next((s for s in opts["step"] if s.startswith(p)), None)
        if x:
            return x
    return opts["step"][-1]


def decider(state, opts):
    if CUR["key"] != CUR["target"] or CUR["mode"] == "R":
        step = CUR["replay"].pop(0) if CUR["replay"] else "finish"
        return {"step": step, "backend": "replay", "ms": 0}
    t0 = time.perf_counter()
    rec = {"mode": CUR["mode"], "options_A": list(opts["step"]), "state_keys": sorted(state)}
    try:
        if CUR["mode"] == "A":
            d = {"step": dry_pick(opts), "confidence": None} if DRY else planner_b2.jev_decide(state, opts)
            rec["chosen_shown"] = d["step"]
        else:
            ob, back = to_b(opts)
            d = {"step": name_b(dry_pick(opts)), "confidence": None} if DRY else planner_b2.jev_decide(state, ob)
            rec["chosen_shown"] = d["step"]
            d = {**d, "step": back.get(d["step"], d["step"])}
        rec.update(step=d["step"], confidence=d.get("confidence"))
        return d
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        raise
    finally:
        rec["ms"] = int((time.perf_counter() - t0) * 1000)
        LOG.append(rec)


# ---------------------------------------------------------------------- phát lại kịch bản
def run_fixture(fx, mode, run_no):
    sid, call, turn = fx
    view = agent_view(SCENS[sid])
    mem = Memory(f"clarify_ab:{sid}:{call}:{turn}:{mode}:{run_no}")
    mem.wipe()
    ToolBox.reset_world()
    CUR.update(target=fx, mode=mode)
    out = {"fixture": f"{sid}/{call}/t{turn}", "mode": mode, "run": run_no, "slots_missing": {}, "drift": []}
    for c in view["calls"]:
        sess = agent.CallSession(memory=mem, today=c["date"], call_name=c["call"], session_id=f"{sid}:{c['call']}",
                                 channel=c["channel"], channel_identity=c["channel_identity"],
                                 phone=view["phone"] if c["channel"] == "hotline" else None, input_mode=c["input_mode"],
                                 router=Router("rules"), generator=Generator("offline"), config="full",
                                 planner_variant="b2_jev", planner_decider=decider)
        if c["seed_history"]:
            sess.phone = sess.phone or view["phone"]
        sess.start()
        if c["seed_history"] and sess.customer:
            for h in c["seed_history"]:
                sess.import_old_session(h, h.get("customer_id") or sess.customer["customer_id"])
            sess._bind(sess.customer["customer_id"], sess.customer["name"], sess.customer["honorific"], sess.customer["phone"], None)
            sess.brief = sess._build_brief()
        row1 = ROWS.get((sid, c["call"], 1)) or {}
        pf = ((row1.get("call_brief") or {}).get("profile_facts") or {})
        for k, v in pf.items():                                  # GIẢ ĐỊNH 3: profile như bản gốc
            sess.carried[k] = v
            sess.known.setdefault(k, v)
            sess.known_src.setdefault(k, "memory")
        for i, text in enumerate(c["turns"], start=1):
            key = (sid, c["call"], i)
            row = ROWS[key]
            u, miss = rebuild_u(row, text, c["date"])
            if miss:
                out["slots_missing"][f"{c['call']}/t{i}"] = miss
            CUR["key"] = key
            CUR["replay"] = list(recorded_steps(row)) if (key != fx or mode == "R") else []
            n0 = len(LOG)
            with patch.object(U, "understand", lambda *a, **k: json.loads(json.dumps(u))):
                r = sess.turn(text)
            lp = r["planner"].get("loop") or {}
            if key != fx:
                if r["goals"] != row["goals"]:
                    out["drift"].append({"turn": f"{c['call']}/t{i}", "goals_trace": row["goals"], "goals_replay": r["goals"]})
                continue
            first_opts = (LOG[n0]["options_A"] if len(LOG) > n0 else None)
            out.update(customer_text=row.get("customer_text"),
                       deepseek={"asks": (row.get("understanding") or {}).get("asks"),
                                 "requests": (row.get("understanding") or {}).get("request_items"),
                                 "ambiguity": ((row.get("understanding") or {}).get("ambiguity") or {}).get("level")},
                       recorded_steps=recorded_steps(row), recorded_goals=row["goals"], recorded_stop=((row.get("planner") or {}).get("loop") or {}).get("stop"),
                       steps=[d.get("step") for d in lp.get("decisions") or []], stop=lp.get("stop"), goals=r["goals"],
                       n_decisions=len(lp.get("decisions") or []), loop_ms=lp.get("ms"),
                       clarify_nothing=sum(1 for s in lp.get("steps") or [] if s.get("action") == "clarify"
                                           and any(str(m).startswith("nothing_to_clarify") for m in s.get("missing") or [])),
                       api_errors=[x["error"] for x in LOG[n0:] if x.get("error")],
                       jev_ms=[x["ms"] for x in LOG[n0:] if x.get("mode") in ("A", "B")],
                       shown=[x.get("chosen_shown") for x in LOG[n0:] if x.get("mode") in ("A", "B")],
                       precheck={"product_candidates": [s for s in (first_opts or []) if s.startswith("read_quote:")],
                                 "read_tool_options": [s for s in (first_opts or []) if s.split(":")[0] in
                                                       ("read_quote", "read_stock", "read_order", "check_window", "read_policy")],
                                 "answer_options": [s for s in (first_opts or []) if s.startswith("answer_ask:")],
                                 "request_options": [s for s in (first_opts or []) if s.startswith(("commit_request:", "clarify:"))],
                                 "first_recorded_step_offered": (recorded_steps(row) or [None])[0] in (first_opts or []) if first_opts else None},
                       clarify_desc_A={s: d for s, d in (planner_b2.options.__globals__.get("_last_desc") or {}).items()})
            return out
        sess.end()
    out["error"] = "target turn not reached"
    return out


patches = [patch.object(settings, k, v) for k, v in dict(arch="target", jev_simulated=False, planner_variant="b2_jev",
                                                         b2_max_decisions=10, b2_max_tool_calls=12, b2_deadline_s=12.0,
                                                         b2_min_conf=0.0, goal_contract=True, contract_v2=True, order_qty=True,
                                                         planner_selector="rules", planner_backend="rules", improve_dir="",
                                                         requests_backend="").items()]
patches += [patch.object(U, "understand_record", lambda summary, today: ({}, {"calls": 0, "ms": 0, "error": None})),
            patch.object(audit, "_jev_sentence", lambda s, k: None),
            patch.object(deepseek.LLM, "json", lambda self, p, **kw: {"claims": []} if "claims" in json.dumps(kw.get("schema") or {})
                         else {"lead": "L0", "policy_refs": [], "attribute_refs": []})]
# ghi lại mô tả clarify / finish của A ở lựa chọn đầu tiên (chỉ để báo cáo, không đổi hành vi)
_orig_options = planner_b2.options


def _options_logged(t):
    o = _orig_options(t)
    planner_b2.options.__globals__["_last_desc"] = {k: v for k, v in o["desc"].items() if k.startswith(("clarify", "finish"))}
    return o


patches.append(patch.object(planner_b2, "options", _options_logged))
for p in patches:
    p.start()

results = []
for fx in FIXTURES:
    results.append(run_fixture(fx, "R", 0))
    for rep, order in enumerate((("A", "B"), ("B", "A"), ("A", "B"))):
        for mode in order:
            results.append(run_fixture(fx, mode, rep))
for p in reversed(patches):
    p.stop()

summary = {}
for fx in FIXTURES:
    name = f"{fx[0]}/{fx[1]}/t{fx[2]}"
    rs = [x for x in results if x["fixture"] == name]
    r0 = next(x for x in rs if x["mode"] == "R")
    summary[name] = {"replay_matches_trace": r0.get("goals") == r0.get("recorded_goals") and r0.get("stop") == r0.get("recorded_stop"),
                     "drift_prior_turns": len(r0.get("drift") or []), "slots_missing": r0.get("slots_missing"),
                     "precheck": r0.get("precheck"), "deepseek": r0.get("deepseek"), "recorded_steps": r0.get("recorded_steps")}
    for m in ("A", "B"):
        ms = [x for x in rs if x["mode"] == m]
        summary[name][m] = {"no_progress": sum(1 for x in ms if x.get("stop") == "no_progress"),
                            "clarify_nothing_runs": sum(1 for x in ms if x.get("clarify_nothing")),
                            "stops": [x.get("stop") for x in ms], "steps": [x.get("steps") for x in ms],
                            "goals": [x.get("goals") for x in ms], "decisions": [x.get("n_decisions") for x in ms],
                            "loop_ms": [x.get("loop_ms") for x in ms], "api_errors": sum(len(x.get("api_errors") or []) for x in ms)}
json.dump({"dry": DRY, "summary": summary, "runs": results, "decisions": LOG}, open(os.path.join(OUT, "clarify_ab.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)
tot = {m: {"no_progress": sum(v[m]["no_progress"] for v in summary.values()),
           "clarify_nothing_runs": sum(v[m]["clarify_nothing_runs"] for v in summary.values()),
           "api_errors": sum(v[m]["api_errors"] for v in summary.values())} for m in ("A", "B")}
print(json.dumps({"dry": DRY, "fixtures": len(FIXTURES), "replay_matches": sum(v["replay_matches_trace"] for v in summary.values()),
                  "totals": tot}, ensure_ascii=False, indent=1))
for k, v in summary.items():
    print(k, "| replay ok:", v["replay_matches_trace"], "| drift:", v["drift_prior_turns"], "| A np:", v["A"]["no_progress"], "B np:",
          v["B"]["no_progress"], "| A steps:", v["A"]["steps"][0], "| B steps:", v["B"]["steps"][0])
