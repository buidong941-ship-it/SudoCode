"""v1.2 (18/11, freeze integ-ui6c): SỬA SAU KẾT QUẢ, công khai. v1 (integ-ui6-cpu-a-1118) và v1.1 (integ-ui6b-cpu-a-1118) TRƯỢT ở S4;
verdict giữ. Chẩn đoán từ trace (job diag-s4-ui6-1118): ở S4 cổng đặt hàng CÓ SẴN (V42, request_state: hai đối tượng hợp lý — mẫu đang
bàn + mẫu vừa đề xuất) KHÔNG mở yêu cầu mà hỏi ngay "muốn lấy mẫu nào: A, B" (sự kiện order_gate target_ambiguous). Kỳ vọng v1 / v1.1
giả định SAI cơ chế (yêu cầu mở với đối tượng rỗng). v1.2: S4 kiểm đúng mục tiêu — không yêu cầu đặt nào được gắn mẫu, không ghi,
câu hỏi nêu đủ hai mẫu; dòng "luồng chính bỏ commit_request@P#" chuyển sang S1 mutant A (nơi yêu cầu thật sự mở không đối tượng).
Không đổi code runtime, không đổi kỳ vọng nào khác.

Nghiệm thu CPU b2tt-2 (18/11, freeze integ-ui6) — bước 1 của docs/DE-XUAT/QUYET-DINH-KIEN-TRUC-SAU-UI5.md: phạm vi tác vụ theo
đối tượng khách nói, mô tả chuyển luồng đúng hành vi, nguồn ref (khách nêu / agent đề xuất / khách đồng ý), đối chiếu mục tiêu đặt hàng.
Kaggle CPU, KHÔNG API. DeepSeek = phản hồi đóng gói theo hợp đồng (trường consult.goal mới); Jev = bộ quyết định có kịch bản theo
CHÍNH SÁCH chung (không viết riêng cho từng ca); tool = mock BTC thật; đáp án tính độc lập bằng eval/mock_tools.
Kiểm cả ĐỐI TƯỢNG trong câu trả lời và SKU gắn vào yêu cầu đặt (không chỉ "có gọi pricing.get_quote SKU đó" như probe CNY-CN-DELEGATE
cũ — survey cả nhóm tình cờ đọc đúng SKU không đủ chứng minh trả lời đúng).
KHÔNG chứng minh Jev / DeepSeek thật chọn đúng (phần đó là API nhỏ sau cổng CPU).

S1 giữ mẫu (dạng V3-123) + 2 mutant (mở lại recommend khi đã nêu mẫu; bỏ cả nguồn ref) · S2 nêu mẫu + diện tích (dạng GEN-T01-01) ·
S3 so hai mẫu · S4 nhờ tìm mẫu khác: mốc giữ, đề xuất riêng, đồng ý mơ hồ → hỏi lại · S5 đổi mẫu rõ ràng → ref mới · S6 rẻ nhất ·
S7 tìm trong nhóm chưa có mẫu → gọi Jev tầng ngoài, Jev chọn chuyển luồng → luồng chính chạy · S8 mô tả chuyển luồng ·
S9 hợp đồng consult.goal · S10 cờ tắt: không ảnh hưởng.
Dùng: python tests/b2tt_scope_check.py   (chỉ chạy trên cây đã áp overlay runs/freeze/20261118-integ-ui6)"""
import os
import sys
import types
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)

from eval import mock_tools as mt  # noqa: E402
from harness import planner_b2tt as TT, understanding as U  # noqa: E402
from harness.request_state import RequestState  # noqa: E402
from harness.tools import product_name  # noqa: E402

ok, resp, Script = F.ok, F.resp, F.Script
TT_ON = {"b2_two_tier": True, "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4}
AIR = "gia-dung/may-loc-khong-khi"
STER, BAG, PRO, XM, APX, APY = "SKU-MB-STER", "SKU-MB-BAG", "SKU-AP-PRO", "SKU-XM-4L", "SKU-AP-X", "SKU-AP-Y"
WRITES = ("order.create", "order.update", "schedule.callback", "handoff.transfer")
N = {k: product_name(k) for k in (STER, BAG, PRO, XM, APX, APY)}


def policy_inner(state, opts):
    for pre in ("survey:", "answer", "ask_customer_category", "finish_unresolved"):
        hit = next((k for k in opts if k.startswith(pre)), None)
        if hit:
            return {"pick": hit, "backend": "script", "ms": 0}


OUTER_SEEN = []


def policy_outer(state, opts):
    """Chính sách chung: chọn tác vụ tư vấn đầu tiên (không phải chuyển luồng). Ghi lại để kiểm có / không gọi tầng ngoài."""
    OUTER_SEEN.append(dict(opts))
    return {"pick": next((k for k in opts if k != TT.DELEGATE), TT.DELEGATE), "backend": "script", "ms": 0}


def delegate_outer(state, opts):
    OUTER_SEEN.append(dict(opts))
    return {"pick": TT.DELEGATE, "backend": "script", "ms": 0}


def main_policy(state, opts):
    """Planner chính có kịch bản theo chính sách chung: đọc giá mẫu chưa đọc → trả lời câu hỏi → thực hiện yêu cầu (không tự gắn
    mẫu @P#) → hỏi phần thiếu → kết thúc."""
    st = opts["step"]
    for pre in ("read_quote:", "answer_ask:"):
        hit = next((x for x in st if x.startswith(pre)), None)
        if hit:
            return hit
    hit = next((x for x in st if x.startswith("commit_request:") and "@" not in x), None)
    if hit:
        return hit
    return next((x for x in st if x.startswith("clarify")), "finish")


def mk_main():
    return Script(*[main_policy] * 60)


def consult(goal="none", scope="none", sort="none", cat=None, budget=None, area=None):
    return {"sort": sort, "scope": scope, "goal": goal, "category_span": cat, "budget_span": budget, "area_span": area}


def tt(row):
    return (F.loop(row) or {}).get("two_tier") or {}


def calls(row, n):
    return [t for t in row["tool_calls"] if t["name"] == n]


def quoted(row):
    return {t["args"].get("sku") for t in calls(row, "pricing.get_quote")}


def place_targets(s):
    return [tuple((r.get("target") or {}).get("skus") or ()) for r in s.reqs.items if r["kind"] == "place_order"]


def mem_roles(s):
    cid = (s.customer or {}).get("customer_id")
    return {(q["sku"], q["role"]) for q in s.mem.past_quotes(cid)} if cid else set()


ORDER_NOREF = lambda ev: resp(intent="place_order", requests=[F.req("place_order", ev, None)])  # noqa: E731


def s1(name, mutate=None):
    """Dạng V3-123: khách nêu mẫu Moaz Bebe + ngân sách + 'tư vấn giúp' → lượt sau 'lấy 1 cái' (không nêu mẫu)."""
    md = mk_main()
    s = F.session(name, decider=md)
    r1 = F.say(s, f"Chị đang xem {N[STER]}, ngân sách tầm 2 triệu, em tư vấn giúp chị",
               resp(intent="price_promo", asks=["recommend"], asks_question=True,
                    consult=consult("about_named", "mentioned", budget="2 triệu")))
    r2 = F.say(s, "Ừ vậy lấy cho chị 1 cái", ORDER_NOREF("lấy cho chị 1 cái"))
    return s, r1, r2, md


with F.Ctx(TT_ON):
    TT.DECIDERS.update(inner=policy_inner, outer=policy_outer)

    # ---------------- S1 giữ mẫu (dạng V3-123)
    OUTER_SEEN.clear()
    s, r1, r2, md = s1("s1")
    x = tt(r1)
    ok("S1", "tiền đề: parser thấy đúng mẫu khách nêu", (x.get("criteria") or {}).get("named"), [STER])
    ok("S1", "tác vụ consult_named, không mở recommend", str((x.get("outer") or {}).get("task", "")).startswith("consult_named@")
       and not any(k.startswith("consult_recommend") for k in (x.get("outer") or {}).get("options") or []), True)
    ok("S1", "bỏ lời gọi tầng ngoài có lý do (cùng luồng chính)", (x.get("outer") or {}).get("why"), "named_runs_on_main_flow")
    ok("S1", "outcome named_to_main_flow (luồng chính xử lý)", x.get("outcome"), "named_to_main_flow")
    ok("S1", "không survey nhóm (không catalog.search)", calls(r1, "catalog.search"), [])
    ok("S1", "báo giá ĐÚNG mẫu khách nêu", quoted(r1), {STER})
    ok("S1", "câu trả lời nêu đúng mẫu, không nêu mẫu khác", N[STER] in r1["agent_text"] and N[BAG] not in r1["agent_text"], True)
    ok("S1", "luồng chính nhận phạm vi ref (consult_scope trong state Jev)", any("consult_scope" in st for st in md.seen), True)
    ok("S1", "đặt 'lấy 1 cái' gắn ĐÚNG mẫu khách nêu", place_targets(s)[-1:], [(STER,)])
    ok("S1", "không ghi đơn sai mẫu", [a for t in calls(r2, "order.create") for a in [t["args"].get("sku")] if a and TT._par(a) != STER],
       [])
    ok("S1", "nguồn ref: khách nêu Moaz Bebe", "customer_named" in (s.ref_roles.get(STER) or {}), True)
    ok("S1", "không gọi Jev tầng ngoài", OUTER_SEEN, [])

    # mutant A: mở lại recommend khi đã nêu mẫu (hành vi b2tt-1) — lớp nguồn ref vẫn chặn đặt nhầm: mẫu đề xuất không thay mẫu khách
    def tasks_b2tt1(c, t, crit):
        return {f"consult_recommend@{crit['category']}": "mutant", TT.DELEGATE: TT.DELEGATE_DESC}
    with patch.object(TT, "tasks", tasks_b2tt1):
        sa, ra1, ra2, _ = s1("s1-mutA")
    prop = getattr(sa, "b2tt_proposal", None)
    ok("S1", "mutant A (tiền đề): recommend chạy và đề xuất mẫu khác", bool(prop) and TT._par(prop["sku"]) != STER, True)
    ok("S1", "mutant A: đề xuất KHÔNG thành mẫu đang bàn", bool(prop) and TT._par(sa.focus) != TT._par(prop["sku"]), True)
    ok("S1", "mutant A: đề xuất lưu vai proposed (không thành product_advised)", (prop or {}).get("sku") and
       (prop["sku"], "proposed") in mem_roles(sa), True)
    ok("S1", "mutant A: 'lấy 1 cái' sau đề xuất khác mẫu → mơ hồ, không gắn mẫu", place_targets(sa)[-1:], [()])
    ok("S1", "mutant A: không order.create", [t for t in calls(ra2, "order.create")], [])
    rm = {v for d in (F.loop(ra2) or {}).get("decisions") or [] for v in (d.get("removed") or {}).values()}
    ok("S1", "mutant A: luồng chính bỏ commit_request@P# (purchase_target_ambiguous)", "purchase_target_ambiguous" in rm, True)
    ok("S1", "mutant A: không nhắc đặt mẫu đề xuất như mẫu khách chọn", f"đặt {N[BAG]}" in ra2["agent_text"], False)

    # mutant B: thêm bỏ luôn nguồn ref (ref_roles rỗng mỗi lần) → tái hiện lỗi gốc: đề xuất thay mẫu khách, đặt nhầm mẫu đề xuất
    with patch.object(TT, "tasks", tasks_b2tt1), patch.object(TT, "ref_roles", lambda s_: {}):
        sb, rb1, rb2, _ = s1("s1-mutB")
    ok("S1", "mutant B: test PHÁT HIỆN đặt nhầm mẫu đề xuất (lỗi gốc V3-123)", place_targets(sb)[-1:] != [(STER,)], True)

    # ---------------- S2 nêu mẫu + diện tích (dạng GEN-T01-01)
    s = F.session("s2", decider=mk_main())
    r = F.say(s, f"Phòng chị 25 mét, chị có để ý mẫu {N[PRO]}", resp(intent="price_promo", asks=["recommend"], asks_question=True,
                                                                      consult=consult("about_named", "mentioned", area="Phòng chị 25 mét")))
    ok("S2", "consult_named (không recommend cả nhóm)", str((tt(r).get("outer") or {}).get("task", "")).startswith("consult_named@"), True)
    ok("S2", "báo giá đúng AirPure Pro, không Xiaomi", quoted(r) == {PRO} and N[XM] not in r["agent_text"], True)
    ok("S2", "mẫu đang bàn = mẫu khách nêu", TT._par(s.focus), PRO)

    # ---------------- S3 so hai mẫu
    s = F.session("s3", decider=mk_main())
    r = F.say(s, f"{N[APX]} với {N[APY]} cái nào rẻ hơn em", resp(intent="price_promo", asks=["compare", "price"], asks_question=True,
                                                                   consult=consult("compare_named", "mentioned")))
    task = str((tt(r).get("outer") or {}).get("task", ""))
    ok("S3", "consult_named hai ref", task.startswith("consult_named@") and len(task.split("@")[1].split(",")) == 2, True)
    ok("S3", "đọc giá đúng hai mẫu, không survey", quoted(r) == {APX, APY} and not calls(r, "catalog.search"), True)

    # ---------------- S4 nhờ tìm mẫu khác: mốc giữ, đề xuất riêng, đồng ý mơ hồ → hỏi lại
    OUTER_SEEN.clear()
    s = F.session("s4", decider=mk_main())
    F.say(s, f"{N[PRO]} giá bao nhiêu em", resp(intent="price_promo", asks=["price"], asks_question=True,
                                                 consult=consult("about_named", "mentioned")))
    r = F.say(s, "Có mẫu nào khác rẻ hơn không em", resp(intent="price_promo", asks=["recommend"], asks_question=True,
                                                         consult=consult("find_other", "discussed")))
    x = tt(r)
    ok("S4", "tác vụ consult_alternative cùng nhóm", x.get("task"), f"consult_alternative@{AIR}")
    ok("S4", "gọi Jev tầng ngoài (tác vụ + chuyển luồng đều hợp lệ)", (x.get("outer") or {}).get("mode") == "jev" and
       bool(OUTER_SEEN) and TT.DELEGATE in OUTER_SEEN[-1], True)
    prop = getattr(s, "b2tt_proposal", None) or {}
    ok("S4", "đề xuất là mẫu KHÁC mốc", bool(prop.get("sku")) and TT._par(prop["sku"]) != PRO, True)
    ok("S4", "câu trả lời giữ mốc ('ngoài mẫu AirPure Pro')", f"ngoài mẫu {N[PRO]}" in r["agent_text"] and
       product_name(prop.get("sku")) in r["agent_text"], True)
    ok("S4", "mẫu đang bàn vẫn là AirPure Pro", TT._par(s.focus), PRO)
    ok("S4", "bộ nhớ: đề xuất vai proposed", (prop.get("sku"), "proposed") in mem_roles(s), True)
    ok("S4", "ứng viên cho bộ hiểu có vai agent_proposed", any(c_.get("role") == "agent_proposed" for c_ in
                                                               s.reqs.context(s)["candidates"]), True)
    r = F.say(s, "Ừ vậy lấy cho anh 1 cái", ORDER_NOREF("lấy cho anh 1 cái"))
    ok("S4", "tiền đề: bộ hiểu nhận yêu cầu đặt", ((s.u_turn or {}).get("requests") or []), ["place_order"])
    ok("S4", "đồng ý không nêu mẫu ngay sau đề xuất → KHÔNG yêu cầu nào được gắn mẫu", [x for x in place_targets(s) if x], [])
    ok("S4", "không ghi gì", [t["name"] for t in r["tool_calls"] if t["name"] in WRITES], [])
    ok("S4", "hỏi khách lấy mẫu nào, nêu đủ hai mẫu", "?" in r["agent_text"] and N[PRO] in r["agent_text"]
       and product_name(prop.get("sku")) in r["agent_text"], True)

    # ---------------- S5 đổi mẫu rõ ràng → ref mới, không hỏi lặp
    alt = prop.get("sku")
    r = F.say(s, f"Thôi lấy {product_name(alt)} cho anh", resp(intent="place_order", requests=[F.req("place_order", "lấy", "P1")]))
    ok("S5", "khách nêu đúng mẫu đề xuất → yêu cầu gắn mẫu đó", place_targets(s)[-1:], [(TT._par(alt),)])
    ok("S5", "không hỏi lại 'mẫu nào'", "mẫu nào" in r["agent_text"], False)

    # ---------------- S6 rẻ nhất (không hỏi trẻ nhỏ; không gọi tầng ngoài vì luồng chính không so cực trị)
    OUTER_SEEN.clear()
    s = F.session("s6", decider=mk_main())
    rows = [(mt.pricing_get_quote(it["sku"], on="2026-10-15")["final_price_vnd"], it["sku"]) for it in mt.catalog_search(category=AIR)["items"]
            if mt.inventory_check(it["sku"], on="2026-10-15").get("in_stock")]
    cheapest = min(rows)[1]
    r = F.say(s, "Máy lọc không khí rẻ nhất là bao nhiêu?", resp(intent="price_promo", asks=["price"], asks_question=True,
                                                               consult=consult("find_in_category", "category", "cheapest", "Máy lọc không khí")))
    ok("S6", "trả lời đúng mẫu rẻ nhất (oracle)", product_name(cheapest) in r["agent_text"] and "ask_need" not in r["goals"], True)
    ok("S6", "không gọi Jev tầng ngoài, có lý do", ((tt(r).get("outer") or {}).get("why"), OUTER_SEEN),
       ("main_flow_has_no_extreme_search", []))
    ok("S6", "không có mẫu khách nêu → mẫu rẻ nhất thành mẫu đang bàn", TT._par(s.focus), TT._par(cheapest))

    # ---------------- S7 tìm trong nhóm chưa có mẫu → gọi tầng ngoài; Jev chọn chuyển luồng → luồng chính chạy
    OUTER_SEEN.clear()
    TT.DECIDERS["outer"] = delegate_outer
    md = mk_main()
    s = F.session("s7", decider=md)
    r = F.say(s, "Tư vấn giúp anh máy lọc không khí với", resp(intent="price_promo", asks=["recommend"], asks_question=True,
                                                                consult=consult("find_in_category", "category", cat="máy lọc không khí")))
    ok("S7", "gọi Jev tầng ngoài với recommend + chuyển luồng", bool(OUTER_SEEN) and any(k.startswith("consult_recommend") for k in
       OUTER_SEEN[-1]) and TT.DELEGATE in OUTER_SEEN[-1], True)
    ok("S7", "chọn chuyển luồng → planner chính được gọi", (tt(r).get("outcome"), len(md.seen) >= 1), ("delegated", True))
    TT.DECIDERS["outer"] = policy_outer

    # ---------------- S8 mô tả chuyển luồng nói đúng nơi tiếp tục
    io = TT.inner_options(f"consult_recommend@{AIR}", {"steps": [], "tools": 0}, s)
    ok("S8", "finish_unresolved: nói rõ chuyển về luồng chính", "LUỒNG CHÍNH" in io["finish_unresolved"], True)
    ok("S8", "delegate_main_flow: nói rõ luồng chính xử lý tiếp trong lượt", "LUỒNG CHÍNH" in TT.DELEGATE_DESC
       and "NGAY trong lượt" in TT.DELEGATE_DESC, True)

    # ---------------- S9 hợp đồng consult.goal
    from core.pii import Redactor
    g_ok = U._accept_consult({"consult": {"goal": "find_other"}}, "có mẫu nào khác không", Redactor(), {"dropped": []})
    g_bad = U._accept_consult({"consult": {"goal": "mua_ngay"}}, "x", Redactor(), {"dropped": []})
    ok("S9", "goal hợp lệ giữ nguyên; sai → none", (g_ok["goal"], g_bad["goal"]), ("find_other", "none"))
    ok("S9", "schema gửi DeepSeek có goal (enum)", U._consult_schema()["properties"]["goal"]["enum"], U.GOALS)

TT.DECIDERS.update(inner=None, outer=None)

# ---------------- S10 cờ TẮT: không trace two_tier, không áp mơ hồ đề xuất
with F.Ctx({"b2_two_tier": False}):
    s = F.session("s10", decider=mk_main())
    s.b2tt_proposal = {"sku": BAG, "turn": s.turn_no}
    ok("S10", "cờ tắt: proposal_ambiguity luôn None", RequestState.proposal_ambiguity(s), None)
    r = F.say(s, f"{N[PRO]} giá bao nhiêu em", resp(intent="price_promo", asks=["price"], asks_question=True))
    ok("S10", "cờ tắt: không có trace two_tier", "two_tier" in (F.loop(r) or {}), False)
    ok("S10", "cờ tắt: ứng viên không có vai agent_proposed", any(c_.get("role") == "agent_proposed" for c_ in
                                                                  s.reqs.context(s)["candidates"]), False)

print(f"\n{F.PASS[0]} OK, {len(F.FAIL)} FAIL")
for g, n in F.FAIL:
    print("FAIL", g, n)
sys.exit(1 if F.FAIL else 0)
