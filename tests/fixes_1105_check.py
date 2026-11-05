#!/usr/bin/env python3
"""Các sửa duyệt 05/11 (CHO-DUYET mục 1, 2, 6, 15).

1. D49b: mô tả cờ `asks_internal_cost` của router Jev là bản `moi` (người gọi bất kể tự xưng là ai, giá sàn, giục đọc tiếp).
2. D33: câu mẫu an toàn khi sinh lại vẫn nói KM hết hạn như còn hiệu lực → báo KM đã hết + giá hiện tại, không chỉ "cảm ơn".
3. D54: khách hẹn chốt sau (E15, không lên đơn) → call_1 vẫn ghi `variant_sku` đã báo giá vào bộ nhớ (V3-016, offline).
4. D58: PLANNER_TABLE / PRODUCT_LEXICON / PARALLEL_ROUTER mặc định bật; JEV_MODEL mặc định jev-latest.

    python tests/fixes_1105_check.py [--out-dir DIR]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    out_dir = a.out_dir or tempfile.mkdtemp(prefix="fix1105_")
    os.makedirs(out_dir, exist_ok=True)
    bad = []

    from core.llm.router import FLAGS
    yes = FLAGS["asks_internal_cost"][0]
    if not all(w in yes for w in ("bất kể", "giá sàn", "giục")):
        bad.append(f"D49b: mô tả asks_internal_cost chưa phải bản moi: {yes[:80]}")

    from harness.agent import _promo_safe_plan
    from core.llm.generator import render_offline
    q = {"name": "AirPure X", "sku": "SKU-AP-X", "final_price_vnd": 3290000, "list_price_vnd": 3290000, "promo_codes": []}
    plan = {"goals": ["answer_question"], "facts": {"quote": q}, "honorific": "chị"}
    p = _promo_safe_plan(plan, ["nói chương trình KM10 đã hết hạn như còn hiệu lực"])
    txt = render_offline(p)
    if p["goals"][:2] != ["stale_promo", "quote"] or "hết hạn" not in txt or "3.290.000" not in txt:
        bad.append(f"D33: câu mẫu thiếu KM hết hạn / giá hiện tại: {p['goals']} → {txt}")
    if _promo_safe_plan(plan, ["có số tiền lạ 1.000.000đ"]) is not plan:
        bad.append("D33: lỗi không liên quan KM thì phải giữ nguyên plan")

    # V3-011: guardrail phần trăm giảm không có trong KM đang áp dụng
    from harness.guardrails import promo_problems
    air = {"promo_code": "AIR-2ND-50", "discount_percent": 50, "type": "percent_second_item"}
    cases = [("Dạ giá 2.990.000đ. Vì chị là VIP nên giảm 50% nhé.", {"active": [], "expired": []}, True),
             ("Dạ máy thứ hai trong đơn được giảm 50% ạ.", {"active": [air], "expired": []}, False),
             ("Dạ em không thể áp dụng giảm 50% cho chị ạ.", {"active": [], "expired": []}, False),
             ("Chị hỏi giảm 50% là sao ạ?", {"active": [], "expired": []}, False)]
    for t, pr, want in cases:
        got = any("giảm" in p and "%" in p for p in promo_problems(t, pr))
        if got != want:
            bad.append(f"V3-011 guardrail %: '{t}' → {got}, cần {want}")

    # V3-140: ý trả hàng
    from harness.agent import RETURN_RX
    from harness.textnorm import fold
    for t, want in [("Hàng cô nhận khác hình quá em, cho cô trả nhé.", True), ("chị muốn trả hàng", True),
                    ("cho chị trả lại cái áo", True), ("em xin trả nha shop", True),
                    ("cho chị trả góp được không", False), ("chị trả khi nhận hàng nhé", False),
                    ("cho anh trả tiền mặt", False), ("để chị trả lời sau", False), ("cho chị trả bằng chuyển khoản", False)]:
        if bool(RETURN_RX.search(fold(t))) != want:
            bad.append(f"V3-140 RETURN_RX: '{t}' → {not want}, cần {want}")

    from core.config import Settings
    s = Settings()
    for k in ("planner_table", "product_lexicon", "parallel_router"):
        if os.environ.get(k.upper()) is None and not getattr(s, k):
            bad.append(f"D58: {k} phải mặc định bật")
    if os.environ.get("JEV_MODEL") is None and s.jev_model != "jev-latest":
        bad.append(f"JEV_MODEL mặc định phải là jev-latest, đang {s.jev_model}")

    out = os.path.join(out_dir, "v3016.jsonl")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{out_dir}/v3016.db", "LLM_CACHE": "off", "IMPROVE_DIR": "",
           "PLANNER_TABLE": "1", "PRODUCT_LEXICON": "1"}
    subprocess.run([sys.executable, os.path.join(ROOT, "run_eval.py"), "--scenarios", os.path.join(ROOT, "datagen/out_v3/final/dev"),
                    "--only", "V3-016", "--config", "full", "--out", out, "--router", "rules", "--generator", "offline",
                    "--extractor", "rules", "--transport", "direct", "--run-id", "fix1105"], check=True, env=env, cwd=ROOT)
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    c1 = [r for r in rows if r.get("call") == "call_1"]
    made_order = any(tc.get("name") == "order.create" for r in c1 for tc in r.get("tool_calls", []))
    wrote = any(w.get("key") == "variant_sku" for r in c1 for w in r.get("memory_writes", []) or [])
    if made_order:
        bad.append("D54: V3-016 call_1 không được lên đơn khi khách hẹn chốt sau (E15)")
    if not wrote:
        bad.append("D54: V3-016 call_1 phải ghi variant_sku vào bộ nhớ dù chưa lên đơn")
    c2 = [r for r in rows if r.get("call") == "call_2"]
    used = {f for r in c2 for f in r.get("facts_used", []) or []}
    print(f"V3-016: call_1 lên đơn={made_order}, ghi variant_sku={wrote}; call_2 facts_used={sorted(used)}")

    for b in bad:
        print("LỖI", b)
    print(f"fixes_1105_check: {'OK' if not bad else str(len(bad)) + ' lỗi'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
