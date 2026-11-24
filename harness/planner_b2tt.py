"""Candidate B2-TT (17/11): tư vấn CHỈ ĐỌC hai tầng trên B2 (docs/DE-XUAT/THIET-KE-CANDIDATE-B2TT-2026-11-17.md).

    DeepSeek (bộ hiểu, như cũ + trường có kiểu `consult`) → code dựng danh mục TÁC VỤ
      → Jev tầng ngoài chọn tác vụ (bỏ qua lời gọi khi: giao dịch → delegate; chỉ một tác vụ; tái dùng tác vụ dang dở)
      → Jev tầng trong chọn THAO TÁC có đối tượng (survey:<nhóm> | quote:<sku> | answer | ask_need | clarify_category |
        finish_unresolved), nhận observation sau mỗi bước
      → code gọi tool (ToolBox → MCP), so sánh trên dữ liệu có nguồn, dựng block `product_pick` (renderer kiểm giá với tool).

Không ghi gì: không đơn, không giỏ, không yêu cầu (request_state không bị đụng). Lượt có giao dịch → `delegate` cho vòng B2 chính
(request / binding / authorization / order gate giữ nguyên). Không có luật "phải hỏi trẻ nhỏ / ngân sách trước": ask_need chỉ là
MỘT lựa chọn của tác vụ recommend khi chưa biết nhu cầu nào.

b2tt-2 (18/11, docs/DE-XUAT/QUYET-DINH-KIEN-TRUC-SAU-UI5.md bước 1; điều tra DIEU-TRA-CANARY-UI5-2026-11-18.md mục 1):
- Tầng ngoài chọn PHẠM VI: `consult_named@P#[,P#]` (một / hai mẫu đã xác định → luồng chính đọc theo ref, không tìm mẫu khác),
  `consult_alternative@<nhóm>` (khách muốn mẫu KHÁC mẫu đang xem; mẫu đó là mốc, không bị thay), tìm trong nhóm (recommend /
  rẻ nhất / đắt nhất), hoặc `delegate_main_flow`. Chỉ bỏ lời gọi chọn khi còn đúng MỘT phương án hợp lệ về nghĩa (kể cả phương án
  chuyển luồng khi nó có ý nghĩa) — lý do ghi trace.
- Nguồn của ref sản phẩm: khách nêu (customer_named) / agent đề xuất (agent_proposed) / khách đồng ý mua (customer_agreed) ghi ở
  s.ref_roles. Khảo sát / xếp hạng chỉ thêm ĐỀ XUẤT: không thay mẫu khách đang nói khi khách đã nêu mẫu trong cuộc (đề xuất ghi
  s.b2tt_proposal + báo giá vai "proposed" trong bộ nhớ, không thành product_advised). Lời đồng ý không nêu mẫu ngay sau một đề
  xuất khác mẫu đang bàn → request_state coi là mơ hồ, hỏi lại.
"""
import time

from core.config import settings
from core.pii import Redactor

CONSULT_ASKS = {"price", "promo", "stock", "recommend", "compare"}
SORT_TASKS = ("cheapest", "most_expensive")
GOALS = ("about_named", "compare_named", "find_other", "find_in_category", "none")
DELEGATE = "delegate_main_flow"
DELEGATE_DESC = ("CHUYỂN VỀ LUỒNG CHÍNH: planner B2 chính xử lý tiếp NGAY trong lượt này với đủ bước (đọc giá / kho theo từng mẫu đã "
                 "gắn ref, chính sách, đơn, giỏ, đặt hàng). Dùng khi câu khách không phải tìm / chọn mẫu trong một nhóm hàng.")
FINISH_DESC = ("DỪNG tác vụ tư vấn này, không trả lời từ tầng này: nếu CHƯA đọc dữ liệu thì lượt chuyển ngay về LUỒNG CHÍNH (planner "
               "B2 chính xử lý tiếp trong cùng lượt: đọc giá / kho theo từng mẫu, chính sách...); nếu ĐÃ đọc thì code trả lời giới hạn "
               "chính xác từ dữ liệu đã đọc. Dùng khi tác vụ không hợp với câu khách (vd khách hỏi đúng một mẫu cụ thể).")
CAT_LABEL = {"gia-dung/may-loc-khong-khi": "máy lọc không khí", "gia-dung/may-loc-nuoc": "máy lọc nước", "gia-dung/noi-chien": "nồi chiên",
             "gia-dung/quat": "quạt", "thoi-trang/giay": "giày", "thoi-trang/ao": "áo khoác", "me-be": "đồ mẹ & bé"}
NEED_SLOTS = ("has_children", "budget_vnd", "room_area_m2")
# Hook cho test (bộ quyết định có kịch bản): {"outer": fn(state, opts), "inner": fn(state, opts)}; None = Jev thật / mô phỏng
DECIDERS = {"outer": None, "inner": None}

OUTER_INSTR = ("Bạn là người điều phối của nhân viên bán hàng. Chọn MỘT tác vụ phù hợp với câu khách hiện tại, giữ đúng tiêu chí khách "
               "nêu (mẫu khách nêu, nhóm hàng, rẻ nhất / đắt nhất, ngân sách, diện tích). consult_named xử lý đúng mẫu khách nêu; "
               "consult_alternative tìm mẫu khác mẫu khách đang xem; consult_recommend / cheapest / most_expensive tìm trong cả nhóm; "
               "delegate_main_flow chuyển về luồng chính. Không thay mẫu khách nêu bằng mẫu khác khi khách không xin gợi ý mẫu khác. "
               "Không tự thêm điều kiện khách không nói.")
INNER_INSTR = ("Bạn chọn MỘT thao tác tiếp theo cho tác vụ tư vấn đã chọn. survey đọc danh mục + tồn kho + giá thật bằng tool; answer "
               "trả lời khách từ dữ liệu đã đọc (code so sánh); ask_* là hỏi khách rồi kết thúc lượt — chỉ dùng khi thật sự thiếu thông "
               "tin để làm tác vụ; finish_unresolved khi không thể hoàn thành. Không lặp thao tác đã làm.")


# ---------------------------------------------------------------------- tiện ích
def _cat_label(cat, span=None):
    return (span or "").strip().lower() or CAT_LABEL.get(cat) or cat


def _cat_of_sku(sku):
    from eval import mock_tools as mt
    p, _ = mt._parent(sku) if sku else (None, None)
    return p["category"] if p else None


def _choice(instr, state, opts):
    """MỘT Choice của Jev trên danh mục đóng (cùng cơ chế planner_b2.jev_decide). → {"pick","confidence","backend","ms"}."""
    t0 = time.perf_counter()
    shown = dict(opts)
    if settings.jev_simulated:
        from harness.jev_adapter import infer
        schema = {"type": "object", "additionalProperties": False, "required": ["pick"],
                  "properties": {"pick": {"type": "string", "enum": list(shown)}}}
        d = infer(f"{instr}\nCác lựa chọn: {shown}\nDữ liệu: {state}\nTrả JSON pick.", schema)
        return {"pick": d.get("pick"), "confidence": None, "backend": "qwen_simulated_jev", "ms": int((time.perf_counter() - t0) * 1000)}
    from typesafe_sdk import Choice
    from harness.question_classifiers.jev_slots import _client
    r = _client().system_one(state=state, questions={"pick": Choice(instructions=instr, criteria=shown)}, model=settings.jev_model)
    ch = r.choices["pick"]
    return {"pick": ch.choice, "confidence": float(ch.confidence), "backend": f"jev:{settings.jev_model}",
            "ms": int((time.perf_counter() - t0) * 1000)}


def _decide(tier, state, opts, rec):
    fn = DECIDERS.get(tier)
    d = fn(state, opts) if fn else _choice(OUTER_INSTR if tier == "outer" else INNER_INSTR, state, opts)
    rec.update({k: d.get(k) for k in ("pick", "confidence", "backend", "ms")})
    rec["options"] = list(opts)
    if d.get("pick") not in opts:
        rec["rejected"] = "pick_not_in_options"
        return None
    return d["pick"]


# ---------------------------------------------------------------------- tầng ngoài: tác vụ
def _par(sku):
    from harness.request_state import _parent
    return _parent(sku) if sku else None


def _pname(sku):
    from harness.tools import product_name
    return product_name(sku)


def ref_roles(s):
    """Nguồn của ref sản phẩm trong CUỘC GỌI: {sku cha: {"customer_named": lượt, "agent_proposed": lượt, "customer_agreed": lượt}}."""
    if not isinstance(getattr(s, "ref_roles", None), dict):
        s.ref_roles = {}
    return s.ref_roles


def _note_roles(c, t):
    """Đầu lượt: mẫu parser catalog thấy trong câu KHÁCH → customer_named; yêu cầu đặt đã có đối tượng → customer_agreed."""
    s = c.s
    roles = ref_roles(s)
    for x in getattr(s, "turn_mentioned", None) or []:
        if x:
            roles.setdefault(_par(x), {})["customer_named"] = s.turn_no
    for r in t.active_requests():
        tg = r.get("target") or {}
        if r.get("kind") == "place_order" and tg.get("type") == "product":
            for x in tg.get("skus") or ():
                roles.setdefault(_par(x), {})["customer_agreed"] = s.turn_no


def _criteria(c):
    s = c.s
    u = s.u_turn or {}
    con = u.get("consult") or {}
    asks = set(u.get("asks") or [])
    mentioned = [x for x in (getattr(s, "turn_mentioned", None) or []) if x]
    named = list(dict.fromkeys(_par(x) for x in mentioned))
    goal = con.get("goal") if con.get("goal") in GOALS else "none"
    # mốc của câu "mẫu khác / so với mẫu đang bàn": mẫu khách nêu trong câu, không có thì mẫu đang bàn
    anchor = named or ([_par(s.focus)] if s.focus else [])
    cat = con.get("category")
    basis = "category_span" if cat else None
    if not cat and con.get("scope") == "discussed" and s.category:
        cat, basis = s.category, "discussed_category"
    if not cat and (con.get("scope") in ("mentioned", "discussed") or goal in ("find_other", "about_named", "compare_named")):
        cats = {_cat_of_sku(x) for x in mentioned or ([s.focus] if s.focus else [])} - {None}
        if len(cats) == 1:
            cat, basis = cats.pop(), "mentioned_products"
    return {"sort": con.get("sort") or "none", "scope": con.get("scope") or "none", "goal": goal, "category": cat,
            "category_basis": basis, "category_span": con.get("category_span"), "budget_max_vnd": con.get("budget_max_vnd"),
            "room_area_m2": con.get("room_area_m2"), "asks": sorted(asks), "mentioned": mentioned, "named": named, "anchor": anchor}


def _transactional(c, t):
    s = c.s
    u = s.u_turn or {}
    return bool(u.get("requests") or t.active_requests() or t.extra_requests() or s.reqs.hold)


def _named_refs(s, parents):
    """Sku cha → ref P# của bảng ứng viên lượt này (request_state.context). Thiếu ref nào → None (không tự đặt ref)."""
    inv = {v["skus"][0]: k for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product" and v.get("skus")}
    refs = [inv.get(p) for p in parents]
    return refs if refs and all(refs) else None


def tasks(c, t, crit):
    """Danh mục tác vụ do code dựng từ hiểu + trạng thái. → {task_id: mô tả} (luôn có delegate_main_flow).

    b2tt-2: phạm vi theo ĐỐI TƯỢNG khách nói — mẫu khách nêu (hoặc mẫu đang bàn khi khách hỏi đúng về nó) → consult_named (luồng
    chính đọc theo ref); khách xin mẫu khác mẫu đang xem → consult_alternative (mẫu đó là mốc); chỉ khi khách tìm trong nhóm hàng mới
    mở recommend / rẻ nhất / đắt nhất. Xếp hạng chỉ chạy trong phạm vi đã chọn."""
    s = c.s
    out = {}
    from core.config import settings
    if settings.pick_by_name and not crit["named"] and 2 <= len(((s.u_turn or {}).get("name_pick") or {}).get("skus") or []) <= 4:
        # S2 v6p13: tên khách gọi khớp nhiều mẫu → luồng chính hỏi khách chọn mẫu, không tư vấn / gợi ý mẫu khác trong nhóm
        return {"delegate_main_flow": DELEGATE_DESC}
    cat, lab = crit["category"], _cat_label(crit["category"], crit["category_span"])
    cons = ", ".join(x for x in ([f"ngân sách tối đa {crit['budget_max_vnd']:,}đ".replace(",", ".")] if crit["budget_max_vnd"] else [])
                     + ([f"phòng {crit['room_area_m2']} m²"] if crit["room_area_m2"] else []))
    asks = set(crit["asks"])
    goal = crit["goal"]
    named = crit["named"] or (crit["anchor"] if goal in ("about_named", "compare_named") else [])
    no_product = not (crit["named"] or s.focus)
    consult_ask = bool(asks & CONSULT_ASKS) or goal != "none"
    # sửa sau DI24 (S1P-COMPARE): mẫu khách nêu (1–2) mà khách KHÔNG xin tìm trong nhóm / mẫu khác → phạm vi là các mẫu đó, kể cả khi
    # câu có tiêu chí "rẻ hơn / đắt hơn" (so sánh chỉ giữa các mẫu khách nêu; xếp hạng chỉ trong phạm vi đã chọn)
    named_first = bool(crit["named"]) and len(crit["named"]) <= 2 and goal not in ("find_other", "find_in_category") and consult_ask
    if named_first:
        refs = _named_refs(s, crit["named"])
        if refs:
            what = "SO SÁNH hai mẫu" if len(crit["named"]) == 2 else "TRẢ LỜI / ĐÁNH GIÁ đúng mẫu"
            out[f"consult_named@{','.join(refs)}"] = (f"{what} khách nêu ({', '.join(_pname(x) for x in crit['named'])}"
                                                      + (f"; {cons}" if cons else "") + (f"; tiêu chí {crit['sort']}" if crit["sort"] in SORT_TASKS else "")
                                                      + f"): luồng chính đọc giá / kho của từng mẫu theo ref ({', '.join(refs)}) "
                                                      "rồi trả lời; không tìm hay gợi ý mẫu khác.")
    elif crit["sort"] in SORT_TASKS:
        if cat:
            w = "RẺ NHẤT" if crit["sort"] == "cheapest" else "ĐẮT NHẤT"
            out[f"consult_{crit['sort']}@{cat}"] = (f"Tìm mẫu {w} còn bán trong nhóm {lab}" + (f" ({cons})" if cons else "")
                                                   + ": đọc danh mục, tồn kho, giá bán hiện hành bằng tool; code so sánh.")
        else:
            out["consult_clarify_category"] = "Khách hỏi rẻ / đắt nhất nhưng chưa rõ nhóm hàng: hỏi khách nhóm hàng nào."
    elif goal == "find_other" and crit["anchor"]:
        alab = ", ".join(_pname(x) for x in crit["anchor"])
        if cat:
            out[f"consult_alternative@{cat}"] = (f"Tìm mẫu KHÁC {alab} trong nhóm {lab}" + (f" ({cons})" if cons else "")
                                                 + f": đọc danh mục, tồn kho, giá thật; code xếp hạng trong nhóm, không tính {alab}. "
                                                 f"{alab} vẫn là mẫu khách đang xem (không thay).")
        else:
            out["consult_clarify_category"] = "Khách muốn mẫu khác nhưng chưa rõ nhóm hàng: hỏi khách nhóm hàng nào."
    elif named and consult_ask:
        refs = _named_refs(s, named)
        if refs and len(named) <= 2:
            what = "SO SÁNH hai mẫu" if len(named) == 2 else "TRẢ LỜI / ĐÁNH GIÁ đúng mẫu"
            out[f"consult_named@{','.join(refs)}"] = (f"{what} khách nêu ({', '.join(_pname(x) for x in named)}" + (f"; {cons}" if cons else "")
                                                      + f"): luồng chính đọc giá / kho của từng mẫu theo ref ({', '.join(refs)}) "
                                                      "rồi trả lời; không tìm hay gợi ý mẫu khác.")
    elif asks & {"recommend"} or goal == "find_in_category" or \
            (asks & {"price", "promo", "stock"} and no_product and crit["scope"] in ("category", "discussed")):
        if cat:
            out[f"consult_recommend@{cat}"] = (f"Tư vấn mẫu trong nhóm {lab}" + (f" ({cons})" if cons else "")
                                               + " theo nhu cầu đã biết; đọc danh mục, tồn kho, giá thật.")
        elif no_product:
            out["consult_clarify_category"] = "Khách nhờ tư vấn / hỏi giá nhưng chưa rõ nhóm hàng hay mẫu nào: hỏi khách."
    out["delegate_main_flow"] = DELEGATE_DESC
    return out


def auto_pick(opts):
    """Bỏ lời gọi Jev tầng ngoài CHỈ khi còn đúng một phương án hợp lệ về nghĩa (kể cả chuyển luồng khi có ý nghĩa).
    → (task, lý do) | (None, None)."""
    consult = [k for k in opts if k != DELEGATE]
    if len(consult) != 1:
        return None, None
    k = consult[0]
    if k.startswith("consult_named@"):
        return k, "named_runs_on_main_flow"            # cùng luồng chính, chỉ thêm phạm vi ref → delegate không khác nghĩa
    if k.split("@")[0] in ("consult_cheapest", "consult_most_expensive"):
        return k, "main_flow_has_no_extreme_search"    # luồng chính không có bước so cực trị cả nhóm
    if k == "consult_clarify_category":
        return k, "main_flow_would_ask_same"
    return None, None                                  # recommend / alternative: luồng chính cũng tư vấn được → Jev chọn


# ---------------------------------------------------------------------- thao tác chỉ đọc
def _survey(c, w, cat, crit):
    """Đọc danh mục nhóm + tồn kho từng mẫu + giá bán (pricing.get_quote) các mẫu còn hàng. Chỉ đọc; không ghi bộ nhớ / không đổi focus.
    → observation có cấu trúc (mọi số liệu kèm nguồn tool)."""
    s = c.s
    from harness.agent import public_view
    args = {"category": cat}
    if cat == "me-be" and crit.get("category_span"):
        args["query"] = crit["category_span"].lower()          # nhóm thô của bộ từ → lọc thêm theo đúng cụm khách nêu
    if crit.get("budget_max_vnd"):
        args["max_price_vnd"] = crit["budget_max_vnd"]
    if crit.get("room_area_m2"):
        args["min_room_area_m2"] = crit["room_area_m2"]
    res = s.tools.call("catalog.search", **args)
    w["tools"] += 1
    if not isinstance(res, dict) or res.get("error"):
        return {"status": "error", "error": "catalog.search", "items": []}
    items = res.get("items") or []
    if (res.get("total") or 0) > len(items):
        w["truncated"] = True                                    # catalog trả tối đa 20 → không đủ căn cứ "rẻ nhất toàn nhóm"
    cust = s.customer or {}
    rows = []
    for it in items:
        if w["tools"] + 2 > settings.b2tt_max_tool_calls - 2:   # chừa 2 cho báo giá mẫu được chọn
            w["budget_hit"] = True
            break
        inv = s.tools.call("inventory.check", sku=it["sku"])
        w["tools"] += 1
        row = {"sku": it["sku"], "name": it["name"], "list_price_vnd": it["list_price_vnd"], "has_variants": bool(it.get("variants")),
               "in_stock": bool(isinstance(inv, dict) and inv.get("in_stock")), "restock_expected": (inv or {}).get("restock_expected"),
               "attributes": {k: v for k, v in (it.get("attributes") or {}).items() if not str(k).startswith("_")}}
        if isinstance(inv, dict) and inv.get("error"):
            row["error"] = "inventory.check"
        elif row["in_stock"]:
            q = public_view(s.tools.call("pricing.get_quote", sku=it["sku"], customer_phone=cust.get("phone"),
                                         address=s.known.get("address")))
            w["tools"] += 1
            if isinstance(q, dict) and q.get("final_price_vnd") is not None:
                row["final_price_vnd"] = q["final_price_vnd"]
                row["promo_codes"] = [a["promo_code"] for a in q.get("applied_promos") or []]
            else:
                row["error"] = "pricing.get_quote"
        rows.append(row)
    w["survey"] = {"category": cat, "args": args, "total": res.get("total"), "rows": rows}
    return {"status": "ok", "n_items": len(items), "n_checked": len(rows), "n_in_stock": sum(r["in_stock"] for r in rows),
            "n_priced": sum("final_price_vnd" in r for r in rows), "budget_hit": bool(w.get("budget_hit")),
            "truncated": bool(w.get("truncated"))}


def _rank(w, task, s):
    """CODE so sánh trên bằng chứng có nguồn. → dict cho block product_pick."""
    sv = w.get("survey") or {}
    rows = sv.get("rows") or []
    priced = [r for r in rows if r.get("in_stock") and "final_price_vnd" in r]
    oos = [r for r in rows if not r.get("in_stock") and not r.get("error")]
    errs = [r for r in rows if r.get("error")]
    complete = bool(rows) and not w.get("budget_hit") and not w.get("truncated") and not errs and len(rows) == (sv.get("total") or 0)
    kind = task.split("@")[0].replace("consult_", "")
    out = {"kind": kind, "n_compared": len(priced), "complete": complete, "pick": None,
           "excluded_out_of_stock": [r["name"] for r in oos], "errors": [r["name"] for r in errs]}
    if not priced:
        return out
    if kind == "cheapest":
        pick = min(priced, key=lambda r: (r["final_price_vnd"], r["sku"]))
        cheaper_oos = [r["name"] for r in oos if r["list_price_vnd"] < pick["final_price_vnd"]]
        out["cheaper_out_of_stock"] = cheaper_oos
    elif kind == "most_expensive":
        pick = max(priced, key=lambda r: (r["final_price_vnd"], r["sku"]))
    else:                                                        # recommend / alternative: theo nhu cầu đã biết; không có thì giá thấp nhất
        if kind == "alternative":
            anchor = set(w.get("anchor") or [])
            priced = [r for r in priced if _par(r["sku"]) not in anchor]     # mẫu khác mốc: loại chính mốc khỏi xếp hạng
            if not priced:
                return out
        k = s.known
        def score(r):
            a = r["attributes"]
            sc = 0
            if k.get("has_children") is True and a.get("child_safe_lock"):
                sc += 2
            if k.get("room_area_m2") and a.get("room_area_m2") and a["room_area_m2"] >= k["room_area_m2"]:
                sc += 1
            if k.get("budget_vnd") and r["final_price_vnd"] > k["budget_vnd"]:
                sc -= 2
            return (-sc, r["final_price_vnd"], r["sku"])
        pick = min(priced, key=score)
        out["basis"] = {x: k.get(x) for x in NEED_SLOTS if k.get(x) is not None}
    out["pick"] = {x: pick.get(x) for x in ("sku", "name", "final_price_vnd", "list_price_vnd", "promo_codes", "has_variants")}
    return out


def _answer(c, w, task, crit):
    s = c.s
    r = _rank(w, task, s)
    cat = task.split("@")[1] if "@" in task else None
    r.update({"category_label": _cat_label(cat, crit.get("category_span")),
              "constraints": {k: crit.get(k) for k in ("budget_max_vnd", "room_area_m2") if crit.get(k)}})
    if r["kind"] == "alternative":
        r["anchor_names"] = [_pname(x) for x in crit.get("anchor") or []]
    if r["pick"]:
        # b2tt-2: khảo sát / xếp hạng chỉ thêm ĐỀ XUẤT. Mẫu được chọn thành mẫu đang bàn (focus, báo giá vai advised như mọi lần tư
        # vấn) CHỈ khi khách chưa nêu mẫu nào khác trong cuộc và tác vụ không phải "mẫu khác"; còn lại ghi đề xuất riêng (vai
        # proposed — không thành product_advised / focus), mẫu khách đang nói giữ nguyên.
        roles = ref_roles(s)
        pk = _par(r["pick"]["sku"])
        other_named = {p for p, ro in roles.items() if "customer_named" in ro} - {pk}
        becomes_focus = r["kind"] != "alternative" and not other_named
        view = s._quote(r["pick"]["sku"], "advised" if becomes_focus else "proposed")
        w["tools"] += 2
        if view.get("final_price_vnd") != r["pick"]["final_price_vnd"]:
            r["pick_mismatch"] = {"survey": r["pick"]["final_price_vnd"], "quote": view.get("final_price_vnd")}
            r["pick"] = None                                     # hai lần đọc lệch → không phát giá (không đoán)
        else:
            r["pick"]["promo_names"] = view.get("promo_names") or []
            roles.setdefault(pk, {})["agent_proposed"] = s.turn_no
            r["provenance"] = {"pick": "agent_proposed", "becomes_focus": becomes_focus,
                               "customer_named_kept": sorted(other_named) if not becomes_focus else []}
            if becomes_focus:
                s.focus, s.category = r["pick"]["sku"], cat or s.category
            else:
                s.b2tt_proposal = {"sku": r["pick"]["sku"], "turn": s.turn_no, "task": task, "kept_focus": s.focus}
    c.facts["product_pick"] = r
    if "product_pick" not in c.goals:
        c.goals.append("product_pick")
    if r["pick"] and (r["complete"] or r["kind"] == "recommend"):
        return "answered_sourced"
    return "incomplete" if r["pick"] else "no_source"


# ---------------------------------------------------------------------- tầng trong
def inner_options(task, w, s):
    out = {}
    if task == "consult_clarify_category":
        return {"ask_customer_category": "Hỏi khách nhóm hàng / mẫu muốn tư vấn rồi kết thúc lượt."}
    cat = task.split("@")[1]
    if not w.get("survey"):
        out[f"survey:{cat}"] = (f"ĐỌC TOOL: danh mục nhóm {CAT_LABEL.get(cat, cat)} + tồn kho từng mẫu + giá bán hiện hành mẫu còn hàng. "
                                f"Không hỏi khách, không ghi.")
    else:
        out["answer"] = "TRẢ LỜI khách từ dữ liệu đã đọc (code so sánh và chỉ nói điều có nguồn)."
    if task.startswith(("consult_recommend", "consult_alternative")) and not any(s.known.get(x) is not None for x in NEED_SLOTS) \
            and not w.get("asked_need"):
        out["ask_customer_need"] = "HỎI khách một nhu cầu còn thiếu (trẻ nhỏ / ngân sách) rồi kết thúc lượt."
    out["finish_unresolved"] = FINISH_DESC
    return out


def _with_guidance(st, t, audience):
    """17/11 candidate kho hướng dẫn: thêm guidance_context đúng tầng vào payload; ghi ID thực có trong state đã gửi."""
    from harness import guidance as G
    gc = G.context(getattr(t, "guidance", None), audience) if t is not None else None
    if gc:
        st["guidance_context"] = gc
    out = Redactor().redact(st)
    if gc and t is not None:
        t.guidance_supplied = getattr(t, "guidance_supplied", set()) | {g["id"] for g in (out.get("guidance_context") or {}).get("guides") or []}
    return out


def _state(c, w, crit, task, t=None):
    s = c.s
    st = {"turn": s.turn_no, "customer_text": c.text, "criteria": crit, "task": task,
          "customer_named_products": [_pname(p) for p, ro in ref_roles(s).items() if "customer_named" in ro],
          "known_needs": {k: s.known.get(k) for k in NEED_SLOTS if s.known.get(k) is not None},
          "steps_done": [x["op"] for x in w["steps"]], "last_observation": (w["steps"][-1].get("obs") if w["steps"] else None),
          "tool_calls_left": settings.b2tt_max_tool_calls - w["tools"]}
    return _with_guidance(st, t, "inner")


def run(c, t):
    """→ ("delegate", info) | ("stop", info). Ghi s.b2tt_task (tác vụ dang dở) và info vào trace."""
    s = c.s
    t0 = time.perf_counter()
    crit = _criteria(c)
    info = {"version": "b2tt-2", "criteria": crit, "outer": {}, "inner": [], "tool_calls": 0, "jev_calls": 0}
    prev = getattr(s, "b2tt_task", None)
    s.b2tt_task = None
    _note_roles(c, t)
    info["ref_roles"] = {p: dict(ro) for p, ro in ref_roles(s).items()}
    if _transactional(c, t):
        info["outer"] = {"mode": "rule_delegate", "reason": "transaction_or_open_request"}
        return "delegate", _fin(info, t0, "delegated")
    opts = tasks(c, t, crit)
    consult = [k for k in opts if k != DELEGATE]
    other_asks = set(crit["asks"]) - CONSULT_ASKS
    task = None
    if (prev and prev.get("turn") == s.turn_no - 1 and crit["sort"] == "none" and crit["scope"] == "none" and not crit["asks"]
            and crit["goal"] == "none" and not crit["named"]):
        task, crit = prev["task"], {**prev["criteria"], "resumed": True}
        info["outer"] = {"mode": "reuse_pending", "task": task, "from_turn": prev["turn"]}
        info["criteria"] = crit
    elif not consult:
        info["outer"] = {"mode": "rule_delegate", "reason": "no_consult_task"}
        return "delegate", _fin(info, t0, "delegated")
    elif other_asks:
        info["outer"] = {"mode": "rule_delegate", "reason": "mixed_turn:" + ",".join(sorted(other_asks))}
        return "delegate", _fin(info, t0, "delegated")
    else:
        auto, why = auto_pick(opts)
        if auto:
            task = auto
            info["outer"] = {"mode": "direct_single_task", "task": task, "why": why, "options": list(opts)}
        else:
            rec = {"mode": "jev"}
            info["jev_calls"] += 1
            try:
                task = _decide("outer", _with_guidance({"customer_text": c.text, "criteria": crit,
                                                        "customer_named_products": [_pname(x) for x in crit["named"]]}, t, "outer"),
                               opts, rec)
            except Exception as e:  # noqa: BLE001 — lỗi tầng ngoài: không đoán, để luồng chính xử lý
                rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            info["outer"] = rec
            if not task or task == DELEGATE:
                return "delegate", _fin(info, t0, "delegated")
    if task.startswith("consult_named@"):
        # mẫu đã xác định: tái dùng các bước đọc theo ref của planner chính, giới hạn đúng các ref này (planner_b2.options)
        refs = task.split("@", 1)[1].split(",")
        t.consult_scope = {"task": task, "refs": refs,
                           "skus": [s.reqs.refmap[r]["skus"][0] for r in refs if r in s.reqs.refmap],
                           "goal": crit.get("goal"), "constraints": {k: crit.get(k) for k in ("budget_max_vnd", "room_area_m2")
                                                                     if crit.get(k)}}
        info["consult_scope"] = t.consult_scope
        return "delegate", _fin(info, t0, "named_to_main_flow", task=task)
    # ---- tầng trong
    w = {"steps": [], "tools": 0, "anchor": crit.get("anchor") if task.startswith("consult_alternative") else None}
    outcome, stop = None, None
    seen = set()
    for _ in range(settings.b2tt_max_decisions):
        if time.perf_counter() - t0 > settings.b2_deadline_s:
            stop = "deadline"; break
        io = inner_options(task, w, s)
        rec = {}
        info["jev_calls"] += 1
        try:
            op = _decide("inner", _state(c, w, crit, task, t), io, rec)
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            op = None
        info["inner"].append(rec)
        if op is None:
            stop = "inner_error_or_invalid"; break
        if op in seen:
            rec["rejected"] = "no_progress"; stop = "no_progress"; break
        seen.add(op)
        step = {"op": op}
        if op.startswith("survey:"):
            step["obs"] = _survey(c, w, op.split(":", 1)[1], crit)
        elif op == "answer":
            outcome = _answer(c, w, task, crit)
            step["obs"] = {"outcome": outcome}
            w["steps"].append(step)
            break
        elif op == "ask_customer_need":
            miss = [x for x in ("has_children", "budget_vnd") if s.known.get(x) is None]
            c.facts["need_slots_missing"] = miss
            c.goals.append("ask_need")
            w["asked_need"] = True
            outcome = "needs_customer"
            s.b2tt_task = {"task": task, "criteria": crit, "turn": s.turn_no, "waiting": "need"}
            w["steps"].append({**step, "obs": {"asked": miss[:1]}})
            break
        elif op == "ask_customer_category":
            c.goals.append("ask_product")
            outcome = "needs_customer"
            w["steps"].append({**step, "obs": {"asked": "category"}})
            break
        elif op == "finish_unresolved":
            stop = "finish_unresolved"; w["steps"].append(step); break
        w["steps"].append(step)
    else:
        stop = "max_decisions"
    if outcome is None:
        # dừng mà chưa trả lời: nếu đã đọc được dữ liệu thì trả lời giới hạn chính xác; không thì để luồng chính (không đoán)
        if w.get("survey"):
            outcome = _answer(c, w, task, crit)
            info["forced_answer_after"] = stop
        else:
            info["unresolved"] = stop
            return "delegate", _fin(info, t0, "unresolved_delegated", w)
    return "stop", _fin(info, t0, outcome, w, task)


def _fin(info, t0, outcome, w=None, task=None):
    if w is not None:
        info["steps"] = w["steps"]
        info["tool_calls"] = w["tools"]
        info["flags"] = {k: bool(w.get(k)) for k in ("budget_hit", "truncated")}
    if task:
        info["task"] = task
    info["outcome"] = outcome
    info["ms"] = int((time.perf_counter() - t0) * 1000)
    return info
