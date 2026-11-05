#!/usr/bin/env python3
"""E04 (05/11): slot số lượng `qty` (ORDER_QTY=1) có làm đổi chỉ số không — A/B offline, không Jev, không GPU.

    python tests/order_qty_ab.py --out-dir /tmp/qty_ab

1. Kiểm luật đọc số lượng (`harness.agent.order_qty`) bằng câu dương / âm (không bắt số người, tháng tuổi, m², size, tiền…).
2. Kiểm mock BTC: order.create qty=2 máy lọc không khí → tổng tiền = 2 × giá và KM theo số lượng (AIR-2ND-50, min_qty 2) được tính.
3. Chạy 6 bộ dev (router rules, generator offline, extractor rules, transport direct) với ORDER_QTY=0 và =1, chấm bằng
   eval/reference_eval.py: in chỉ số, kịch bản đổi kết quả, số lượt khác trace và các lượt order.create có qty > 1.
Exit 1 nếu luật đọc sai, mock không như mong đợi, hoặc có bộ TSR giảm / thêm vi phạm guardrail.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "eval"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import reference_eval as RE  # noqa: E402
from mcp_parity import first_diff, strip  # noqa: E402

SETS = [("sample", "test_set/public_sample"), ("nat_dev", "datagen/out_nat/dev"),
        ("v1_1_dev", "datagen/out_btc_like_final_v1_1/final/dev"), ("v2_1_dev", "datagen/out_btc_like_final_v2_1/final/dev"),
        ("d7_dev", "datagen/out_btc_like_d7/final/dev"), ("v3_dev", "datagen/out_v3/final/dev")]
VARIANTS = {"qty0": {"ORDER_QTY": "0"}, "qty1": {"ORDER_QTY": "1"}}
POS = [("Lấy cho chị 2 cái nha em", 2), ("anh đặt hai máy luôn", 2), ("cho cô 3 đôi size 40", 3),
       ("ok chốt 2 chiếc giao về nhà", 2), ("mua ba bộ nhé", 3)]
NEG = ["Bé nhà chị 5 tháng", "phòng 25 mét vuông", "nhà có 4 người", "size 42 màu đen", "giá 2 triệu 990 hả em",
       "lấy thêm 1 cái nữa nha", "giao 32 Hùng Vương", "mấy cái này giá sao em", "chị lấy cái này", "2 tuần nữa giao nhé"]


def run(out_dir, tag, scen, var, workers):
    out = os.path.join(out_dir, f"{tag}-{var}.jsonl")
    env = {**os.environ, **VARIANTS[var], "DATABASE_URL": f"sqlite:///{out_dir}/{tag}-{var}.db", "LLM_CACHE": "off",
           "IMPROVE_DIR": "", "PLANNER_BACKEND": "rules"}
    subprocess.run([sys.executable, os.path.join(ROOT, "run_eval.py"), "--scenarios", os.path.join(ROOT, scen), "--config", "full",
                    "--out", out, "--router", "rules", "--generator", "offline", "--extractor", "rules", "--transport", "direct",
                    "--run-id", f"qty-{var}", "--workers", str(workers)], check=True, env=env, cwd=ROOT, stderr=subprocess.DEVNULL)
    return out


def passed(scen, trace):
    ok = {}
    for sid, s in scen.items():
        res = [RE.check_call(spec, trace.get((sid, call), []))[0] for call, spec in s["calls"].items()]
        res = [r for r in res if r is not None]
        if res:
            ok[sid] = all(res)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    out_dir = a.out_dir or tempfile.mkdtemp(prefix="qty_ab_")
    os.makedirs(out_dir, exist_ok=True)
    fail = []

    from harness.agent import order_qty
    for t, n in POS:
        if order_qty([t]) != n:
            fail.append(f"luật qty: '{t}' → {order_qty([t])}, cần {n}")
    for t in NEG:
        if order_qty([t]) not in (None, 1):
            fail.append(f"luật qty bắt nhầm: '{t}' → {order_qty([t])}")
    print(f"luật qty: {len(POS)} câu dương, {len(NEG)} câu âm, lỗi {len(fail)}")

    import mock_tools as mt
    sku = next(p["sku"] for p in mt.PRODUCTS if "may-loc-khong-khi" in str(p.get("category", "")) and not p.get("variants")
               and not p["attributes"].get("discontinued"))
    q1, q2 = mt.pricing_get_quote(sku, qty=1), mt.pricing_get_quote(sku, qty=2)
    mt.reset() if hasattr(mt, "reset") else None
    o = mt.order_create("0900000000", sku, qty=2, price_vnd=q2["final_price_vnd"], payment="COD")
    print(f"mock {sku}: giá 1 cái {q1['final_price_vnd']}, KM qty=2 {[x['promo_code'] for x in q2.get('applied_promos', [])]}, "
          f"đơn qty=2 → {o.get('total_vnd')} {o.get('error') or ''}")
    if o.get("error") or o.get("total_vnd") != q2["final_price_vnd"] * 2:
        fail.append(f"mock: order.create qty=2 không như mong đợi: {o}")

    print("\n| Bộ | TSR qty0 → qty1 | CCR | RQR | HR | vi phạm | KB đổi kết quả | lượt khác trace | order.create qty>1 |")
    print("|---|---|---|---|---|---|---|---|---|")
    report = {}
    for name, scen_dir in SETS:
        if not os.path.isdir(os.path.join(ROOT, scen_dir)):
            print(f"| {name} | (không có bộ) |"); continue
        scen = RE.load_scenarios(os.path.join(ROOT, scen_dir))
        m, ok, rows = {}, {}, {}
        for var in VARIANTS:
            path = run(out_dir, name, scen_dir, var, a.workers)
            rows[var] = [json.loads(l) for l in open(path, encoding="utf-8")]
            tr = RE.load_trace(path)
            m[var], ok[var] = RE.evaluate(scen, tr), passed(scen, tr)
        key = lambda r: (r.get("scenario_id"), r.get("call"), r.get("turn"))
        b = {key(r): r for r in rows["qty1"]}
        diffs = [k for k, r in ((key(r), r) for r in rows["qty0"]) if k not in b or first_diff(strip(r), strip(b[k]))]
        multi = [f"{r['scenario_id']}/{r['call']}/t{r['turn']}:qty{tc['args'].get('qty')}" for r in rows["qty1"]
                 for tc in r.get("tool_calls", []) if tc.get("name") == "order.create" and (tc.get("args") or {}).get("qty", 1) > 1]
        flips = {sid: ("+" if ok["qty1"].get(sid) else "−") for sid in ok["qty0"] if ok["qty0"].get(sid) != ok["qty1"].get(sid)}
        g = lambda v, k: m[v][k].get("value")
        viol = lambda v: m[v]["guardrail_violations"]["total"]
        print(f"| {name} | {g('qty0', 'task_success_rate')} → {g('qty1', 'task_success_rate')} | "
              f"{g('qty0', 'context_carryover_rate')} → {g('qty1', 'context_carryover_rate')} | "
              f"{g('qty0', 'repeat_question_rate')} → {g('qty1', 'repeat_question_rate')} | "
              f"{g('qty0', 'hallucination_rate')} → {g('qty1', 'hallucination_rate')} | {viol('qty0')} → {viol('qty1')} | "
              + (", ".join(f"{k}{v}" for k, v in sorted(flips.items())) or "—") + f" | {len(diffs)} | " + (", ".join(multi) or "—") + " |")
        report[name] = {"flips": flips, "diff_turns": [list(map(str, d)) for d in diffs], "multi_qty": multi,
                        **{v: {k: m[v][k] for k in ("task_success_rate", "context_carryover_rate", "repeat_question_rate",
                                                     "hallucination_rate", "guardrail_violations")} for v in VARIANTS}}
        if (g("qty1", "task_success_rate") or 0) < (g("qty0", "task_success_rate") or 0):
            fail.append(f"{name}: TSR giảm")
        if viol("qty1") > viol("qty0"):
            fail.append(f"{name}: thêm vi phạm guardrail")
    json.dump(report, open(os.path.join(out_dir, "order_qty_ab.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    for f in fail:
        print("LỖI:", f)
    print(f"order_qty_ab: {'OK' if not fail else str(len(fail)) + ' lỗi'}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
