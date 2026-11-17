#!/usr/bin/env python3
"""Báo cáo dev end-to-end (13/11): Full vs Baseline từ hai trace (job riêng) + report.json của bộ chấm BTC.

    python scripts/dev_report.py --scenarios /tmp/suites/dev --full full.jsonl --baseline baseline.jsonl \
        --report report.json --latency latency/latency_report.json --out <dir>

Chỉ đọc trace / kịch bản (không gọi model, không sửa eval/reference_eval.py — chỉ import hàm của nó):
- TSR / HR (+ HR giá & KM) / CCR / RQR / vi phạm guardrail: lấy từ report.json của BTC.
- Ghi sai / thừa (order.create, order.update, schedule.callback, handoff.transfer) theo success_if của từng call:
  forbidden = tool trong must_not_call_tools; unexpected = tool ghi khác tool đích của call (hoặc call không có tool đích);
  duplicate = cùng tool ghi > 1 lần trong một call; wrong_args = tool đích có gọi nhưng không lần nào khớp args_match.
- Câu hỏi chưa trả lời: ask còn treo khi B2 kết thúc lượt (planner.loop.unanswered) + outcome noop / blocked / error.
- Lỗi API theo nguồn: DeepSeek (understanding.error), Jev planner (stop planner_error), audit nền (audit_status error /
  timeout / thiếu), generator (llm_error_template / fallback mạng), tool trả lỗi, lượt lỗi harness.
"""
import argparse
import collections
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITES = ("order.create", "order.update", "schedule.callback", "handoff.transfer")


def btc():
    spec = importlib.util.spec_from_file_location("btc_reference_eval", os.path.join(ROOT, "eval", "reference_eval.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def by_call(rows):
    d = collections.defaultdict(list)
    for r in rows:
        d[(r.get("scenario_id"), r.get("call"))].append(r)
    return d


def writes_audit(B, scen, rows):
    calls = by_call(rows)
    out = collections.Counter()
    ex = []
    for sid, s in scen.items():
        prev = None                          # địa chỉ của call trước: CHỈ để phát hiện đuôi thừa, không kết luận mismatch
        for call, spec in s["calls"].items():
            rr = calls.get((sid, call), [])
            tcs = [tc for r in rr for tc in r.get("tool_calls") or [] if tc.get("name") in WRITES]
            si = spec.get("success_if") or {}
            target = si.get("tool_called")
            forbid = set(si.get("must_not_call_tools") or [])
            cnt = collections.Counter(tc["name"] for tc in tcs)
            for tc in tcs:
                kind = None
                if tc["name"] in forbid:
                    kind = "forbidden"
                elif tc["name"] != target:
                    kind = "unexpected"
                if kind:
                    out[kind] += 1
                    ex.append({"scenario": sid, "call": call, "type": kind, "tool": tc["name"], "target": target})
            for name, n in cnt.items():
                if n > 1:
                    out["duplicate"] += n - 1
                    ex.append({"scenario": sid, "call": call, "type": "duplicate", "tool": name, "count": n})
            if target in WRITES and target != "handoff.transfer" and cnt.get(target):
                if target == "order.create":
                    hit = any(B.args_match(si.get("args_match"), ln) for ln in B.order_lines([tc for r in rr for tc in r.get("tool_calls") or []]))
                else:
                    hit = any(B.args_match(si.get("args_match"), tc.get("args") or {}) for tc in tcs if tc["name"] == target)
                if not hit:
                    out["wrong_args"] += 1
                    ex.append({"scenario": sid, "call": call, "type": "wrong_args", "tool": target})
    return {"counts": dict(out), "total_writes": sum(1 for r in rows for tc in r.get("tool_calls") or [] if tc.get("name") in WRITES),
            "examples": ex[:40]}


def _norm_addr(a):
    """So địa chỉ: bỏ dấu, chữ thường, gom khoảng trắng / dấu phẩy — chỉ để ĐO (không dùng trong agent)."""
    import unicodedata
    a = unicodedata.normalize("NFD", str(a or "")).replace("đ", "d").replace("Đ", "D")
    a = "".join(ch for ch in a if unicodedata.category(ch) != "Mn").lower()
    return " ".join(a.replace(",", " ").split()).strip(" .")


def address_audit(scen, rows):
    """C (14/11): địa chỉ ghi vào order.create so với địa chỉ của kịch bản (success_if.args_match.address của call, nếu không có thì
    facts_established.address của chính call đó). Loại: ok / tail_extra (địa chỉ đúng + phần đuôi thừa) /
    mismatch / no_expected, theo địa chỉ CUỐI của đơn (sau order.update update_address trong cùng call;
    đếm thêm corrected_by_update). Chỉ là phép đo; không thay tiêu chí BTC."""
    calls = by_call(rows)
    out, ex = collections.Counter(), []
    for sid, s in scen.items():
        prev = None                          # địa chỉ của call trước: CHỈ để phát hiện đuôi thừa, không kết luận mismatch
        for call, spec in s["calls"].items():
            # chỉ địa chỉ của CHÍNH call (không mang từ call trước: người gọi / địa chỉ có thể đổi, vd GEN-T11 hai người)
            exp = ((spec.get("success_if") or {}).get("args_match") or {}).get("address")                 or (spec.get("facts_established") or {}).get("address")
            made = {}                        # order_id -> [địa chỉ lúc tạo, địa chỉ cuối, lượt tạo]
            for r in calls.get((sid, call), []):
                for tc in r.get("tool_calls") or []:
                    a, res = tc.get("args") or {}, tc.get("result") or {}
                    if tc.get("name") == "order.create" and a.get("address"):
                        made[res.get("order_id") or f"?{len(made)}"] = [a["address"], a["address"], r.get("turn")]
                    elif tc.get("name") == "order.update" and a.get("action") == "update_address" and a.get("order_id") in made:
                        new = str(a.get("reason") or "").split("địa chỉ mới:", 1)        # định dạng do agent ghi (agent._update)
                        if len(new) == 2 and new[1].strip():
                            made[a["order_id"]][1] = new[1].strip()
            for oid, (first, final, turn) in made.items():
                if not exp:
                    g, e = _norm_addr(final), _norm_addr(prev)
                    kind = "tail_extra_vs_previous_call" if prev and g != e and g.startswith(e) else "no_expected"
                else:
                    g, e = _norm_addr(final), _norm_addr(exp)
                    kind = "ok" if g == e else "tail_extra" if g.startswith(e) else "mismatch"
                out[kind] += 1
                if final != first:
                    out["corrected_by_update"] += 1
                if kind not in ("ok", "no_expected"):
                    ex.append({"where": f"{sid}/{call}/t{turn}", "type": kind, "got": final, "expected": exp or prev,
                               **({"created_with": first} if final != first else {})})
            prev = exp or prev
    return {"counts": dict(out), "examples": ex[:40]}


def unanswered(rows):
    n_turns, pend, outcomes, ex = 0, 0, collections.Counter(), []
    for r in rows:
        if r.get("error"):
            continue
        n_turns += 1
        lp = (r.get("planner") or {}).get("loop") or {}
        un = lp.get("unanswered") or {}
        if un:
            pend += 1
            ex.append({"scenario": r.get("scenario_id"), "call": r.get("call"), "turn": r.get("turn"), "unanswered": un,
                       "stop": lp.get("stop"), "customer": (r.get("customer_text") or "")[:120]})
        for k, v in (lp.get("ask_outcome") or {}).items():
            outcomes[v.get("outcome")] += 1
    return {"turns": n_turns, "turns_with_unanswered_ask": pend, "ask_outcomes": dict(outcomes), "examples": ex[:40]}


def api_errors(rows):
    c = collections.Counter()
    ex = []
    for r in rows:
        if r.get("error"):
            c["harness_turn_error"] += 1; ex.append({"type": "harness", "where": f"{r.get('scenario_id')}/{r.get('call')}/t{r.get('turn')}", "error": r["error"][:160]})
            continue
        u = r.get("understanding") or {}
        if u.get("error"):
            c["deepseek_understanding"] += 1; ex.append({"type": "deepseek", "where": f"{r.get('scenario_id')}/{r.get('call')}/t{r.get('turn')}", "error": str(u["error"])[:160]})
        lp = (r.get("planner") or {}).get("loop") or {}
        if str(lp.get("stop") or "").startswith("planner_error"):
            c["jev_planner"] += 1
            err = next((d.get("error") for d in lp.get("decisions") or [] if d.get("error")), None)
            ex.append({"type": "jev_planner", "where": f"{r.get('scenario_id')}/{r.get('call')}/t{r.get('turn')}", "error": str(err)[:160]})
        st = r.get("audit_status")
        if st in ("error", "timeout", None, "pending"):
            c[f"audit_{st or 'missing'}"] += 1
        elif st == "ok" and (r.get("audit") or {}).get("status") in ("partial", "unavailable"):
            c[f"audit_{r['audit']['status']}"] += 1
        g = (r.get("guardrail") or {}).get("action")
        fb = " ".join(str(x) for x in ((r.get("router") or {}).get("fallback"), (r.get("extractor") or {}).get("fallback")) if x)
        if g == "llm_error_template" or any(s in fb for s in ("Connection", "Timeout", "APIStatusError", "InternalServerError", "JSONDecodeError")):
            c["generator_or_llm_fallback"] += 1
        for tc in r.get("tool_calls") or []:
            res = tc.get("result")
            if isinstance(res, dict) and res.get("error"):
                c[f"tool_error:{res.get('error')}"] += 1
    return {"counts": dict(c), "examples": ex[:30]}


def metric(rep, side):
    s = rep.get(side) or {}
    g = lambda k, sub=None: ((s.get(k) or {}).get(sub) or {}).get("value") if sub else (s.get(k) or {}).get("value")
    tsr = s.get("task_success_rate") or {}
    return {"TSR": g("task_success_rate"), "TSR_passed": f"{tsr.get('passed')}/{tsr.get('total')}",
            "TSR_hard": ((tsr.get("hard_cases") or {}).get("value")), "HR": g("hallucination_rate"),
            "HR_price_promo": g("hallucination_rate", "price_promo_only"),
            "HR_claims": (s.get("hallucination_rate") or {}).get("total_claims"),
            "CCR": g("context_carryover_rate"), "RQR": g("repeat_question_rate"),
            "RQR_questions": (s.get("repeat_question_rate") or {}).get("total_questions"),
            "guardrail_violations": (s.get("guardrail_violations") or {}).get("total")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--full", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--latency")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    B = btc()
    scen = B.load_scenarios(a.scenarios)
    rep = json.load(open(a.report, encoding="utf-8"))
    out = {"n_scenarios": rep.get("n_scenarios"), "comparison": rep.get("comparison"),
           "metrics": {"full": metric(rep, "system"), "baseline": metric(rep, "baseline")}, "configs": {}}
    for name, path in (("full", a.full), ("baseline", a.baseline)):
        rows = load(path)
        out["configs"][name] = {"rows": len(rows), "writes": writes_audit(B, scen, rows), "unanswered": unanswered(rows),
                                "api_errors": api_errors(rows),
                                "address": address_audit(scen, rows)}
    out["tsr_failures_full"] = (rep.get("system") or {}).get("task_success_rate", {}).get("failures")
    out["hr_examples_full"] = (rep.get("system") or {}).get("hallucination_rate", {}).get("examples")
    out["rqr_examples_full"] = (rep.get("system") or {}).get("repeat_question_rate", {}).get("examples")
    if a.latency and os.path.exists(a.latency):
        out["latency"] = json.load(open(a.latency, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "dev_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    m = out["metrics"]
    L = ["# Báo cáo dev E2E — Full vs Baseline", "", "| Chỉ số | Baseline | Full |", "|---|---|---|"]
    for k in ("TSR", "TSR_passed", "TSR_hard", "HR", "HR_price_promo", "HR_claims", "CCR", "RQR", "RQR_questions", "guardrail_violations"):
        L.append(f"| {k} | {m['baseline'].get(k)} | {m['full'].get(k)} |")
    for name, c in out["configs"].items():
        L += ["", f"## {name}", f"- ghi: {c['writes']['counts']} / tổng lần ghi {c['writes']['total_writes']}",
              f"- câu hỏi treo: {c['unanswered']['turns_with_unanswered_ask']} / {c['unanswered']['turns']} lượt; outcome {c['unanswered']['ask_outcomes']}",
              f"- lỗi API / hạ tầng: {c['api_errors']['counts']}",
              f"- địa chỉ ghi vào đơn so với kịch bản: {c['address']['counts']}"]
    open(os.path.join(a.out, "dev_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
