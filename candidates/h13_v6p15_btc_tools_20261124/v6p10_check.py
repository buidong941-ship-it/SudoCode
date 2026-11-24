"""Kaggle only. v6p10: nạp seed_history.facts theo BTC 11/2026 (giải đáp 2.2) — ánh xạ field, kiểm kiểu, as_of mới nhất thắng
bất kể thứ tự nạp, fact học từ cuộc gọi thật không bị seed ghi đè, field lạ bỏ + ghi log, phiên không có facts giữ đường summary."""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p10_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import agent as A

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


facts, bad = A._seed_facts([
    {"field": "interest_sku", "value": "SKU-AP-X", "as_of": "2026-09-17"},
    {"field": "address", "value": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội", "as_of": "2026-09-17"},
    {"field": "budget_vnd", "value": 5000000},
    {"field": "favourite_colour_of_cat", "value": "x"},
    {"field": "interest_sku", "value": "SKU-NOT-REAL"},
    {"field": "has_children", "value": "yes"}], "2026-09-20")
print("  parsed:", facts, bad, flush=True)
check("unit: interest_sku → product_advised", ("2026-09-17", "product_advised", "SKU-AP-X") in facts)
check("unit: missing as_of → session date", ("2026-09-20", "budget_vnd", 5000000) in facts)
check("unit: unknown field / bad SKU / wrong type dropped and logged",
      len(facts) == 3 and any(b.startswith("unknown_field") for b in bad) and sum(b.startswith("bad_value") for b in bad) == 2)
check("unit: no facts / empty → nothing", A._seed_facts(None, "2026-09-20") == ([], []) and A._seed_facts([], "2026-09-20") == ([], []))


def seed(sid, d, field_values, summary=""):
    return {"session_id": sid, "date": d, "channel": "phone", "summary": summary, "outcome": "hen_goi_lai",
            "facts": [{"field": f, "value": v, **({"as_of": a} if a else {})} for f, v, a in field_values]}


with F.Ctx({"jev_write_gate": True, "b2_two_tier": False}):
    s = F.session("v6p10-seed")
    cid = (s.customer or {}).get("customer_id")
    newer = seed("S-NEW", "2026-10-01", [("address", "99 Lê Lợi, Quận 1, TP HCM", "2026-10-01"), ("interest_sku", "SKU-AP-Y", None)])
    older = seed("S-OLD", "2026-09-01", [("address", "12 Nguyễn Trãi, Thanh Xuân, Hà Nội", "2026-09-01"),
                                          ("interest_sku", "SKU-AP-X", "2026-09-01"), ("room_area_m2", 25, "2026-09-01")])
    for h in (newer, older):                                 # nạp NGƯỢC thứ tự thời gian
        s.import_old_session(h, cid)
    cur = s.mem.current_facts(cid, s.today, include_expired=True)
    print("  facts:", {k: v["value"] for k, v in cur.items()}, "| log:", s.crm_import_log[-3:], flush=True)
    check("as_of newest wins regardless of load order (address)", cur.get("address", {}).get("value") == "99 Lê Lợi, Quận 1, TP HCM")
    check("as_of newest wins (interest_sku → product_advised)", cur.get("product_advised", {}).get("value") == "SKU-AP-Y")
    check("non-conflicting older fact still imported", cur.get("room_area_m2", {}).get("value") == 25)
    check("seed sessions recorded as past sessions", {"S-NEW", "S-OLD"} <= {p["session_id"] for p in s.mem.past_sessions(cid)})

    s2 = F.session("v6p10-live")
    cid2 = (s2.customer or {}).get("customer_id")
    s2.mem.write_fact(cid2, "address", "7 Hai Bà Trưng, Hoàn Kiếm, Hà Nội", "call_1#turn2", "live", s2.today, valid_from=s2.today)
    s2.import_old_session(seed("S-X", "2026-09-01", [("address", "12 Nguyễn Trãi, Thanh Xuân, Hà Nội", "2026-09-01")]), cid2)
    cur2 = s2.mem.current_facts(cid2, s2.today, include_expired=True)
    check("fact learned in a live call not overwritten by seed", cur2.get("address", {}).get("value") == "7 Hai Bà Trưng, Hoàn Kiếm, Hà Nội")

print("v6p10 checks:", passed, "PASS", flush=True)
assert not failed, failed
