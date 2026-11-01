"""Kiểm tra UI demo (plan 01/11 mục F): tách biệt core, engine chạy kịch bản C.6, DB riêng, app Streamlit dựng được.

Chạy: python tests/ui_check.py   (router rules + generator offline, không cần mạng).
Phần AppTest chỉ chạy khi đã cài streamlit (requirements-ui.txt); thiếu thì báo BỎ QUA, không tính lỗi.
"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="ui_check_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")
os.environ["IMPROVE_ROOT"] = os.path.join(tmp, "improve")
FAILS = []


def ok(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)


# 1. core không import ui
for top in ("harness", "core", "eval", "mcp_servers", "improve"):
    for d, _, fs in os.walk(os.path.join(ROOT, top)):
        for f in fs:
            if f.endswith(".py"):
                src = open(os.path.join(d, f), encoding="utf-8").read()
                ok(not re.search(r"^\s*(from|import)\s+ui(\.|\s|$)", src, re.M), f"{top}/{f} import ui — core phải tách khỏi ui/")

from ui import engine as E  # noqa: E402

main_db = os.path.join(ROOT, "data", "memory.db")
main_mtime = os.path.getmtime(main_db) if os.path.exists(main_db) else None

# 2. kịch bản C.6 cuộc 1 + 2
eng = E.Engine("check")
calls = eng.run_demo(upto=2)
ok(len(calls) == 2, f"phải chạy 2 cuộc, có {len(calls)}")
c1, c2 = calls
ok(not c1["brief"].get("is_returning"), "cuộc 1 phải là khách mới")
ok(any("quote" in r["goals"] for r in c1["turns"]), "cuộc 1 phải có báo giá")
ok(any(t["name"] == "pricing.get_quote" for r in c1["turns"] for t in r.get("tool_calls") or []),
   "giá cuộc 1 phải lấy từ tool pricing.get_quote")
b2 = c2["brief"]
ok(b2.get("is_returning") and b2.get("n_previous_sessions") == 1, f"cuộc 2 phải nhận ra khách cũ: {b2.get('is_returning')}")
ok("product_advised" in (b2.get("must_not_ask") or []), f"Call Brief thiếu product_advised: {b2.get('must_not_ask')}")
ok(c2["turns"][0]["goals"][0] == "opening_returning", "cuộc 2 phải mở đầu bằng xác nhận tiếp nối")
asked = {q.get("slot") for r in c2["turns"] for q in r.get("questions") or []}
ok(not (asked & set(b2.get("must_not_ask") or [])), f"cuộc 2 hỏi lại slot đã biết: {asked & set(b2['must_not_ask'])}")
ok(any(t["name"] == "order.create" for r in c2["turns"] for t in r.get("tool_calls") or []), "cuộc 2 phải chốt đơn (order.create)")

# 3. dòng thời gian bộ nhớ
ev = eng.timeline()
kinds = [e["kind"] for e in ev]
ok(kinds.count("phiên") == 2 and "báo giá" in kinds and "fact" in kinds, f"timeline thiếu loại: {kinds}")
ok(ev == sorted(ev, key=lambda e: e["date"] or ""), "timeline phải theo ngày")
ok(all(e["source"] for e in ev if e["kind"] == "fact"), "fact trong timeline phải có nguồn")

# 4. fact bị thay thế vẫn hiện trong timeline
eng.start_call(E.DEMO_PHONE, "hotline", "2026-10-25")
eng.say("Anh chuyển nhà rồi, địa chỉ mới là số 7 Lê Lợi, Quận 1, TP HCM nhé.")
eng.end_call()
addr = [e for e in eng.timeline() if e["kind"] == "fact" and e["what"] == "address"]
ok(len(addr) >= 2 and addr[0]["status"].startswith("superseded"), f"fact địa chỉ cũ phải hiện là superseded: {addr}")

# 5. DB riêng: không đụng data/memory.db; namespace ui:*
ok(main_mtime is None or os.path.getmtime(main_db) == main_mtime, "UI không được ghi vào data/memory.db")
ok(eng.ns.startswith("ui:"), "namespace UI phải bắt đầu bằng ui:")
eng.reset()
ok(eng.timeline() == [] or eng.customer_id() is None, "reset phải xoá bộ nhớ namespace")

# 6. bảng chỉ số
rep = {"system": {"task_success_rate": {"value": 71.4}, "hallucination_rate": {"value": 12, "price_promo_only": {"value": 14.3}},
                  "guardrail_violations": {"total": 0}, "avg_turns_per_call": 2.5},
       "baseline": {"task_success_rate": {"value": 35.7}, "guardrail_violations": {"total": 1}}}
tab = {t: (b, s) for t, b, s in E.metric_table(rep)}
ok(tab["Task Success Rate (%)"] == (35.7, 71.4) and tab["Hallucination giá & KM (%)"] == (None, 14.3)
   and tab["Vi phạm guardrail"] == (1, 0) and tab["Số lượt TB / cuộc"] == (None, 2.5), f"metric_table sai: {tab}")

# 7. app Streamlit (nếu có streamlit)
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    print("BỎ QUA AppTest: chưa cài streamlit (pip install -r requirements-ui.txt)")
else:
    at = AppTest.from_file(os.path.join(ROOT, "ui", "app.py"), default_timeout=300).run()
    ok(not at.exception, f"app lỗi khi mở: {[e.value for e in at.exception]}")
    btn = [b for b in at.button if b.label == "Chạy demo từ đầu"]
    ok(bool(btn), "thiếu nút chạy demo")
    if btn:
        at = btn[0].click().run()
        ok(not at.exception, f"app lỗi khi chạy demo: {[e.value for e in at.exception]}")
        subs = [s.value for s in at.subheader]
        ok(any("Call Brief" in s for s in subs), f"demo không hiện Call Brief: {subs}")
        texts = " ".join(m.value for m in at.markdown)
        ok("call_2" in texts, "demo không hiện cuộc 2")
    print("AppTest OK" if not FAILS else "AppTest có lỗi")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
