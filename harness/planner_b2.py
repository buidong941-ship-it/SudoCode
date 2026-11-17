"""B2-Jev mức 2 (THIET-KE-B1-B2-JEV-B3-WORKFLOW mục 4): Jev chọn TỪNG bước trong lượt khách.

    DeepSeek hiểu lượt khách MỘT lần (đã chạy trước planner)
      → Jev đọc understanding + memory/known + request state + bằng chứng đã đọc trong lượt + ask chưa trả lời + ngân sách
      → Jev chọn (action, request_ref, target_ref, reason_code) trong danh mục ĐÓNG theo trạng thái hiện tại
      → code kiểm tuple → thực hiện hành động được phép (harness/plan_primitives.py) → observation đưa lại cho Jev
      → Jev chọn tiếp, hoặc hỏi rõ / dừng.

Giới hạn (mục 4.4): số quyết định, tổng tool call, deadline mỗi lượt (settings.b2_*); lặp cùng action/ref không có bằng chứng
mới → `no_progress`; hết ngân sách → `budget_exhausted`. Lỗi API / tuple sai / confidence thấp → KHÔNG ghi từ quyết định lỗi,
dừng có lý do, KHÔNG fallback B1 / Qwen; bước đã thành công trước lỗi được giữ. Không có bypass single-candidate.
Code theo dõi mọi ask đã nhận diện: `finish` khi còn ask → blocked; dừng mà còn ask → ghi `unanswered` kèm lý do.

Encoding Jev (v4, duyệt 12/11 sau E1): MỘT `Choice` (`next_step`) trên danh mục bước nguyên tử ĐÃ GẮN đối tượng do code dựng
(vd read_quote:P1, check_window:OD600001, commit_request:R1, answer_ask:price, finish). E1 v3 với bốn Choice độc lập cho 22/65
tuple ghép sai loại (read_quote + ask:price, finish + P1…); một Choice làm việc ghép sai không thể xảy ra. Validator chỉ còn
kiểm bước có trong danh mục hiện tại.
"""
import time

from core.config import settings
from core.pii import Redactor
from harness import plan_primitives as P
from harness.tools import product_name as _pname

# 13/11 (bàn giao cải thiện B2): ACTION_DESC / REASON_DESC cũ đã bỏ — không đường gọi nào gửi chúng cho Jev; mô tả thật sự Jev
# nhận là opts["desc"] do options() dựng. Mỗi mô tả gồm: làm gì · đối tượng · khi nào dùng · kết quả · tool / tác dụng phụ (theo
# SCOPE). Tên HIỂN THỊ cho Jev (display_of) tách khỏi ID CANONICAL (trace / replay / validator / executor giữ canonical).
INSTRUCTIONS = ("Bạn là bộ lập kế hoạch của nhân viên bán hàng qua điện thoại. Dựa vào dữ liệu (lời khách đã được phân tích, "
                "yêu cầu đang mở, bằng chứng tool đã đọc trong lượt, các bước đã làm, các khối trả lời chung đã có), chọn MỘT bước "
                "tiếp theo. Bước read_tool_* chỉ ĐỌC dữ liệu, không hỏi khách; ask_customer_* là HỎI KHÁCH rồi kết thúc lượt. Chỉ "
                "thực hiện yêu cầu khi khách thật sự yêu cầu và đã có giá + tồn kho của đúng sản phẩm trong lượt này. Trả lời mọi "
                "câu khách hỏi trước khi kết thúc. Không lặp lại bước đã làm.")

_DISPLAY = {"read_quote": "read_tool_quote_and_stock", "read_stock": "read_tool_stock", "read_order": "read_tool_customer_orders",
            "check_window": "read_tool_return_window", "read_policy": "read_tool_policy_docs",
            "answer_ask": "answer_customer_question", "commit_request": "execute_request", "report_cart": "tell_customer_cart",
            "finish": "finish_turn"}


def display_of(step):
    """ID canonical → tên hiển thị cho Jev (wording-only, ánh xạ 1-1, đảo được)."""
    a, rq, tg = parse_step(step)
    if a == "clarify":
        return f"ask_customer_missing_info:{rq}" if rq else "ask_customer_to_rephrase"
    name = _DISPLAY[a]
    if a == "answer_ask":
        return f"{name}:{str(tg)[4:]}"
    if a == "commit_request":
        return f"{name}:{rq}" + (f"@{tg}" if tg else "")
    return f"{name}:{tg}" if tg else name


# ---------------------------------------------------------------------- trạng thái nạp cho Jev

SKU_SLOTS = ("product_chosen", "product_advised", "variant_sku", "unresolved_order_sku")
HIDDEN_SLOTS = ("self_name", "unresolved_order_sku")          # tên khách không cần cho lập kế hoạch


def _known_context(t):
    """Ngữ cảnh khách cho Jev (duyệt 12/11): GIÁ TRỊ memory / known kèm NGUỒN và TTL — không chỉ tên slot.
    - nguồn: customer:tN (khách nói ở lượt N) | memory (phiên trước; kèm phiên, hạn dùng) | default;
    - hết hạn (TTL) tách riêng ở `expired_do_not_use_as_current`, không trộn với giá trị hiện tại;
    - SKU đổi sang tên sản phẩm; địa chỉ đặt dưới khóa address để Redactor che thành [ĐỊA_CHỈ_n]; không gửi SĐT;
    - config baseline_no_memory: memory không được đọc → không có giá trị phiên trước (known chỉ có lời khách trong cuộc)."""
    s = t.s
    if not hasattr(t, "mem_facts"):
        cid = (s.customer or {}).get("customer_id")
        t.mem_facts = s.mem.current_facts(cid, s.today, include_expired=True) if cid and s.mem.read_enabled else {}
    src = getattr(s, "known_src", {}) or {}
    values, meta = {}, {}
    for k, v in s.known.items():
        if k in HIDDEN_SLOTS or k in ("phone", "contact_phone"):
            continue
        values[k] = _pname(v) if k in SKU_SLOTS and isinstance(v, str) else v
        origin = src.get(k) or ("memory" if k in (s.carried or {}) else "call")
        m = {"source": origin}
        f = t.mem_facts.get(k)
        if origin == "memory" and f:
            m.update(from_session=f.get("session_id"), expires_on=f.get("expires_on"))
        meta[k] = m
    expired = {k: (_pname(v) if k in SKU_SLOTS and isinstance(v, str) else v) for k, v in (s.expired or {}).items()
               if k not in HIDDEN_SLOTS}
    return {"values": values, "meta": meta, "expired_do_not_use_as_current": expired,
            "has_contact_phone": bool(getattr(s, "contact_phone", None) or (s.customer or {}).get("phone"))}


def _request_context(t, r):
    s = t.s
    cond = r.get("condition") or {}
    rev = r.get("revision") or {}
    out = {"id": r["id"], "kind": r["kind"], "status": r["status"], "target": s.reqs._target_name(r["target"]),
           "from_turn": r["turn"], "source": r.get("source"),
           # dữ kiện dẫn xuất (không cấp quyền, executor kiểm lại trước ghi): thiếu thông tin / chưa có bằng chứng / điều kiện
           # chưa thỏa / bị cấm / đủ dữ kiện để thử
           "readiness": {k: v for k, v in P.readiness(t, r).items() if k != "request"}}
    if cond:
        out["condition"] = {"type": cond.get("type"), **({"max_vnd": cond["max_vnd"]} if cond.get("max_vnd") else {}),
                            **({"customer_words": cond["span"]} if cond.get("span") else {})}
    if rev:
        terms = {}
        if rev.get("units"):
            terms["units"] = [[_pname(u[0]), u[1]] for u in rev["units"]]
        if rev.get("qty"):
            terms["qty"] = rev["qty"]
        if rev.get("new_variant"):
            terms["new_variant"] = _pname(rev["new_variant"])
        for k in ("payment", "address"):
            if rev.get(k):
                terms[k] = {k: (rev[k] or {}).get("value"), "source": (rev[k] or {}).get("src")}
        out["agreed_terms"] = terms
    return out


def state_for(t):
    """Chỉ dữ liệu cần thiết, đã che PII (Redactor); không answer key, không toàn DB, không khách khác.
    Gồm: phân tích lượt của DeepSeek; giá trị memory/known kèm nguồn/TTL; yêu cầu (điều kiện, điều khoản đã đồng ý); facts
    liên quan có nguồn (báo giá phiên trước, cảnh báo giá/KM đổi, đơn tạo trong cuộc, bằng chứng tool trong lượt, đơn đã tra,
    hạn đổi trả); tiến trình trong lượt và ngân sách còn lại."""
    s, c, u = t.s, t.c, t.c.u or {}
    full = s.u_turn or {}            # route.understanding là bản gọn (withdrawn = tên loại); request_items chỉ có ở u_turn
    cands = [{"ref": k, **({"product": s.reqs._target_name(v)} if v.get("type") == "product" else {"order_id": v.get("order_id")})}
             for k, v in s.reqs.refmap.items() if k not in ("CART", "ALL")]
    reqs = [_request_context(t, r) for r in t.active_requests()]
    reqs += [{"id": x, "kind": {"X_CANCEL": "cancel", "X_COMPLETE_ADDRESS": "complete_address_of_created_order"}[x], "status": "open"}
             for x in t.extra_requests()]
    vrefs = [{"ref": k, "new_variant": _pname(v["sku"]), "order_id": v["order_id"], "action": v["action"]}
             for k, v in t.vrefs.items()]
    orders_read = None if t.orders is None else [
        {"ref": t.oref_of(o.get("order_id")), "order_id": o.get("order_id"), "status": o.get("status"),
         "created_on": o.get("created_on") or o.get("date"), "estimated_delivery": o.get("estimated_delivery"),
         "items": s._order_products(o), "address": o.get("address"),
         "multi_line": len({ln.get("sku") for ln in o.get("lines") or []}) > 1} for o in t.orders[-5:]]
    windows = [{"order_ref": t.oref_of(k), "eligible": None if d is None else d.get("eligible"), "days": (d or {}).get("days"),
                "policy_version": (d or {}).get("version"), "basis": (d or {}).get("basis")} for k, d in t.windows.items()]
    evidence = [{"sku_ref": P._ref_of(t, k), "product": v.get("name"), "final_price_vnd": v.get("final_price_vnd"),
                 "list_price_vnd": v.get("list_price_vnd"), "promos": v.get("promo_names"), "in_stock": v.get("in_stock"),
                 "restock_expected": v.get("restock_expected"), "source": "pricing.get_quote+inventory.check"}
                for k, v in t.quotes.items()]
    evidence += [{"sku_ref": P._ref_of(t, k), "in_stock": v["in_stock"], "qty": v["qty"], "source": "inventory.check"}
                 for k, v in t.stock.items() if k not in t.quotes]
    brief = s.brief or {}
    prior = [{"product": _pname(a["sku"]), "price_quoted_vnd": a.get("price_quoted_vnd"), "quoted_on": a.get("quoted_on"),
              "promo_still_active": a.get("promo_still_active"), "current_price_vnd": a.get("current_price_vnd"),
              "in_stock_now": a.get("in_stock_now"), "source": "memory:quotes"} for a in brief.get("products_advised") or []]
    created = [{"order_id": o["order_id"], "items": s._order_products(o), "total_vnd": o.get("total_vnd"), "payment": o.get("payment"),
                "address": o.get("address"), "source": "order.create (cuộc này)"} for o in s.orders_created]
    steps = []
    for o in t.steps:
        x = {k: o.get(k) for k in ("action", "request_ref", "target_ref", "status", "missing", "result") if o.get(k) is not None}
        if o.get("action") in P.ACTIONS and not str(o.get("action")).startswith("halt"):
            x["step_shown"] = display_of(step_of(o["action"], o.get("request_ref"), o.get("target_ref")))
        steps.append(x)
    # 13/11 S4: giỏ do bước chuẩn bị cập nhật (một chủ); planner chỉ thấy, không sửa. Không có số lượng trong hợp đồng giỏ.
    before = list(getattr(c, "cart_before", None) or [])
    touched = list(dict.fromkeys(getattr(c, "cart_touched", None) or []))
    cart = {"items": [_pname(x) for x in s.cart],
            "added_this_turn": [_pname(x) for x in s.cart if x not in before],
            "replaced_this_turn": [_pname(x) for x in before if x not in s.cart],
            "requested_but_already_in_cart": [_pname(x) for x in touched if x in before and x in s.cart],
            "quantity_tracked": False, "source": "bước chuẩn bị theo yêu cầu add_to_cart / place_order của bộ hiểu"}
    st = {"turn": s.turn_no, "intent": c.it,
          "understanding": {"requests": u.get("requests") or [], "asks": u.get("asks") or [], "response": u.get("response"),
                            "request_items": [{"kind": i["kind"], "target_ref": i.get("target_ref"),
                                               "condition": (i.get("condition") or {}).get("type")}
                                              for i in full.get("request_items") or []],
                            "observations": [o["slot"] + ":" + o.get("stance", "") for o in full.get("observations") or []],
                            "withdrawn": [w["kind"] for w in full.get("withdrawn") or []],
                            "ambiguity": (full.get("ambiguity") or {}).get("level")},
          "customer": _known_context(t),
          "candidates": cands, "open_requests": reqs,
          "facts": {"prior_quotes": prior, "stale_warnings": list(brief.get("stale_warnings") or []),
                    "orders_created_this_call": created, "agent_proposal_last_turn": (s.reqs.proposal or {}).get("goal")},
          "evidence_this_turn": evidence, "orders_read_this_turn": orders_read, "return_windows": windows,
          "exchange_variants": vrefs, "steps_done": steps, "asks_pending": t.pending_asks(),
          "ask_outcomes": {k: {"outcome": v["outcome"], "reason": v.get("reason"),
                               "evidence": [e["kind"] for e in v.get("evidence") or []]} for k, v in t.ask_outcome.items()},
          # 13/11 S6: khối trả lời chung đã tạo TRƯỚC vòng planner (vd is_bot của R02) — không tự đánh dấu ask nào đã xong
          "responses_prepared_before_planner": {"rows": t.common["rows"], "goals": t.common["goals"]},
          "cart": cart,
          # V52 (16/11): đối tượng câu hỏi tư vấn của lượt + căn cứ — cùng hàm executor dùng (P.ask_object)
          "question_object": P.question_scope(t),
          "budget_left": {"decisions": settings.b2_max_decisions - len(t.decisions),
                          "tool_calls": settings.b2_max_tool_calls - t.tool_calls}}
    out = Redactor().redact(st)
    t.last_state = out                 # kiểm chứng: đúng dữ liệu đã gửi Jev (sau che PII)
    return out


def step_of(action, request_ref=None, target_ref=None):
    """Bước nguyên tử dạng chuỗi (đơn vị lựa chọn của Jev, v4). Dùng cả để chuyển quyết định dạng cũ (action/request/target)
    của bộ quyết định có kịch bản trong test sang cùng dạng."""
    rq = None if request_ref in (None, "none") else request_ref
    tg = None if target_ref in (None, "none") else target_ref
    if action in ("read_quote", "read_stock", "check_window"):
        return f"{action}:{tg}"
    if action == "answer_ask":
        return f"answer_ask:{str(tg)[4:] if str(tg).startswith('ask:') else tg}"
    if action == "commit_request":
        return f"commit_request:{rq}" + (f"@{tg}" if tg and str(tg).startswith("P") else "")
    if action == "clarify":
        return f"clarify:{rq}" if rq else "clarify"
    return action                                   # read_order | read_policy | finish


def parse_step(step):
    """→ (action, request_ref | None, target_ref | None)."""
    action, _, rest = str(step).partition(":")
    if action == "commit_request":
        rq, _, tg = rest.partition("@")
        return action, rq or None, tg or None
    if action == "clarify":
        return action, rest or None, None
    if action == "answer_ask":
        return action, None, f"ask:{rest}"
    return action, None, rest or None


def options(t):
    """Danh mục ĐÓNG các bước nguyên tử hợp lệ ở trạng thái hiện tại, mỗi bước đã gắn đúng đối tượng (v4, duyệt 12/11): code
    dựng nên không thể ghép hành động với đối tượng sai loại. Là vocabulary / giới hạn thực thi, không phải kế hoạch dựng sẵn:
    Jev vẫn chọn bước kế, quan sát kết quả rồi chọn tiếp. → {"step": [...], "desc": {step: mô tả}, + dạng cũ cho test}."""
    s = t.s
    desc, removed = {}, {}
    prods = [(k, v) for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product"]
    for k, v in prods:
        name = s.reqs._target_name(v)
        desc[f"read_quote:{k}"] = (f"ĐỌC TOOL (không hỏi khách): giá, khuyến mãi và tồn kho hiện tại của {name} ({k}). Dùng khi cần giá / "
                                   f"kho của mẫu này để trả lời hoặc trước khi thực hiện yêu cầu đặt mẫu này. Kết quả: bằng chứng giá + "
                                   f"kho trong lượt (lần báo giá đầu của lượt thành khối báo giá cho khách). Tool: pricing.get_quote, "
                                   f"inventory.check; không ghi gì.")
        desc[f"read_stock:{k}"] = (f"ĐỌC TOOL (không hỏi khách): chỉ tồn kho hiện tại của {name} ({k}). Dùng khi đã có giá, chỉ còn thiếu "
                                   f"kho. Kết quả: bằng chứng kho. Tool: inventory.check; không ghi gì.")
    for k in t.variant_refs():
        v = t.vrefs[k]
        desc[f"read_stock:{k}"] = (f"ĐỌC TOOL (không hỏi khách): tồn kho của biến thể mới {_pname(v['sku'])} ({k}) cho yêu cầu đổi đơn "
                                   f"{v['order_id']}. Dùng trước khi thực hiện đổi. Kết quả: bằng chứng kho. Tool: inventory.check.")
    desc["read_order"] = ("ĐỌC TOOL (không hỏi khách): các đơn của khách. Dùng trước mọi thao tác trên đơn (đổi địa chỉ / đổi / trả) "
                          "hoặc khi khách hỏi đơn. Kết quả: danh sách đơn (là câu trả lời nếu khách hỏi đơn). Tool: order.status.")
    for o in (t.orders or [])[-5:]:
        ref = t.oref_of(o["order_id"])
        desc[f"check_window:{ref}"] = (f"ĐỌC (không hỏi khách): hạn đổi / trả của đơn {o['order_id']} ({s._order_products(o)}) theo phiên "
                                       f"bản chính sách ở ngày tạo đơn. Dùng sau khi đã tra đơn, trước khi đổi / trả. Kết quả: còn / quá "
                                       f"hạn. Không gọi tool, không ghi.")
    desc["read_policy"] = ("ĐỌC TÀI LIỆU (không hỏi khách): tìm đoạn chính sách cho câu khách. Kết quả: đoạn chính sách làm nguồn "
                           "(có thể thành câu trả lời chính sách). Không tool commerce, không ghi.")
    from harness.understanding import ASKS
    BUDGET_ASK_LABEL = ("ngân sách khách VỪA NÊU khi đang bàn một mẫu (V52, không phải câu hỏi của bộ hiểu): so giá mẫu đang "
                        "bàn với ngân sách; vượt thì xem mẫu cùng loại còn hàng hoặc báo chưa có mẫu phù hợp")
    common = ", ".join(t.common["goals"]) or "không có"
    for a in t.pending_asks():
        last = (t.ask_outcome.get(a) or {}).get("outcome")
        desc[f"answer_ask:{a}"] = (f"TRẢ LỜI câu khách hỏi về: {ASKS.get(a, BUDGET_ASK_LABEL if a == 'budget' else a)}. Bên trong có thể đọc giá / kho / đơn / giỏ / chính sách / "
                                   f"catalog đúng chủ đề; nếu câu hỏi chưa gắn được sản phẩm thì bước này tự hỏi khách mẫu nào / nhu "
                                   f"cầu. Kết quả: trả lời có nguồn, hoặc báo chưa có thông tin, hoặc câu hỏi lại khách. Không ghi."
                                   + (f" Riêng câu hỏi khác (other): bước này KHÔNG tự tra tài liệu — ghi nhận khối trả lời chung "
                                      f"đã có ({common}); nếu câu cần chính sách thì dùng read_tool_policy_docs trước; không có gì "
                                      f"thì báo chưa có thông tin." if a == "other" else "")
                                   + (f" Lần trước: {last} (chưa trả lời được)." if last else "")
                                   + (lambda o: f" Đối tượng: {o['object'] or 'chưa có'} ({o['basis']})." if a != "other" and o else "")(P.question_scope(t)))
    if s.cart:
        desc["report_cart"] = ("BÁO KHÁCH GIỎ HÀNG: các món đang có trong giỏ và tổng tiền theo pricing.quote_order (mẫu khách bảo "
                               "thêm mà đã có trong giỏ thì báo đã có, không tăng số lượng). BẮT BUỘC trước khi kết thúc khi khách "
                               "thêm vào giỏ trong lượt này. Chỉ đọc: không thêm / bớt món, không tạo đơn, không suy số lượng. Tool: "
                               "pricing.quote_order (+ giá từng mẫu chưa đọc trong lượt). Giỏ không đổi từ lần báo trước trong lượt thì bước này "
                               "không còn trong danh mục.")
    for r in t.active_requests():
        tgt = s.reqs._target_name(r["target"]) or "chưa rõ đối tượng"
        rd = P.readiness(t, r)
        desc[f"commit_request:{r['id']}"] = (f"THỰC HIỆN yêu cầu {r['id']} ({r['kind']}: {tgt}). Mức sẵn sàng hiện tại: {rd['state']} "
                                             f"({', '.join(map(str, rd['detail']))}). Code kiểm lại quyền + bằng chứng và từ chối kèm "
                                             f"phần thiếu nếu chưa đủ. Kết quả: ghi một lần hoặc bị chặn. Tool: "
                                             f"{', '.join(P.SCOPE.get('commit_request:' + r['kind'], ())) or 'không'}.")
        if r["kind"] == "place_order" and r["target"] is None:
            for k, v in prods:
                desc[f"commit_request:{r['id']}@{k}"] = (f"THỰC HIỆN yêu cầu {r['id']} (đặt hàng) với sản phẩm {s.reqs._target_name(v)} "
                                                         f"({k}); code kiểm lại và từ chối nếu chưa đủ. Tool: pricing.quote_order, "
                                                         f"order.create.")
        # S8 (13/11, thay đổi hành vi): chỉ đưa hỏi khách khi guard có sẵn xác định CÓ điều cần hỏi / báo (thiếu thông tin, điều
        # kiện chưa thỏa, bị cấm, hoặc executor đã từ chối kèm câu trả lời) — chiếu đúng guard của _clarify lên danh mục.
        last = t.blocked.get(r["id"]) or {}
        executor_refused = any(str(m).startswith(("authorize:", "not_executed:")) for m in last.get("missing") or []) \
            and bool(last.get("clarify") or last.get("goals"))
        if rd["state"] in ("missing_info", "condition_unmet", "forbidden") or executor_refused:
            desc[f"clarify:{r['id']}"] = (f"HỎI / BÁO KHÁCH đúng điều đang chặn yêu cầu {r['id']} ({rd['state']}: "
                                          f"{', '.join(map(str, rd['detail']))}) rồi KẾT THÚC lượt. Không ghi gì.")
        else:
            removed[f"clarify:{r['id']}"] = f"readiness:{rd['state']}"
    for x in t.extra_requests():
        desc[f"commit_request:{x}"] = {"X_CANCEL": "THỰC HIỆN: chuyển yêu cầu HỦY đơn của khách sang nhân viên rồi kết thúc lượt. "
                                                   "Tool: handoff.transfer.",
                                       "X_COMPLETE_ADDRESS": "THỰC HIỆN: bổ sung địa chỉ khách vừa đọc cho đơn VỪA tạo trong cuộc. "
                                                             "Tool: order.update."}[x]
    amb = (t.c.u or {}).get("ambiguity")                 # route.understanding: ambiguity là CHUỖI level (understanding.py)
    if s.reqs.hold or amb == "needs_clarification":
        desc["clarify"] = ("HỎI KHÁCH nói lại vì câu khách mơ hồ / không hiểu được rồi KẾT THÚC lượt. Không dùng để tìm thông tin "
                           "(dùng read_tool_*) hay để trả lời câu hỏi (dùng answer_customer_question). Không ghi gì.")
    else:
        removed["clarify"] = "no_hold_no_ambiguity"
    desc["finish"] = ("KẾT THÚC lượt và trả lời khách bằng các khối đã có. Chỉ khi mọi câu hỏi đã được phản hồi và mọi yêu cầu có "
                      "điều kiện của lượt đã được phản hồi; nếu không code chặn. Không gọi tool, không ghi.")
    # patch cuối 13/11: (a) không đưa bước ĐỌC TOOL lại khi bằng chứng đã có trong lượt (giá+kho / kho / đơn);
    # (b) trần tool CỨNG: bước có chi phí tối đa vượt phần ngân sách còn lại không được đưa vào danh mục.
    legacy = [parse_step(x) for x in desc]          # dạng cũ cho bộ quyết định có kịch bản trong test: dựng TRƯỚC khi lọc
    if getattr(t, "reuse_quotes", False):
        left = settings.b2_max_tool_calls - t.tool_calls
        for st in list(desc):
            a, rq, tg = parse_step(st)
            why = None
            if a in ("read_quote", "read_stock") and str(tg).startswith("P"):
                p = t.product_ref(tg)
                sku = P._variant(t, p["skus"][0]) if p else None
                if sku and sku in t.stock and (a == "read_stock" or sku in t.quotes):
                    why = "evidence_present_this_turn"
            elif a == "read_stock" and str(tg).startswith("V"):
                v = t.vrefs.get(tg)
                if v and v["sku"] in t.stock:
                    why = "evidence_present_this_turn"
            elif a == "read_order" and t.orders is not None:
                why = "evidence_present_this_turn"
            elif a == "report_cart" and t.cart_reported_for is not None and t.cart_reported_for == tuple(s.cart):
                why = "cart_reported_unchanged"          # 13/11 vòng giỏ: giỏ không đổi từ lần báo gần nhất trong lượt
            if why is None:
                cost = P.step_cost(t, a, rq, tg)
                if cost > left:
                    why = f"tool_budget:{cost}>{left}"
            if why:
                removed[st] = why
                del desc[st]
    # F2 (13/11, duyệt): khách nêu tên mẫu trong lượt và hỏi giá / KM / kho / so sánh / tư vấn → chỉ đọc giá / kho của mẫu được
    # nhắc (không trả lời bằng mẫu đang bàn trước đó, vd GEN-T16 t3 hỏi X mà báo giá Pro). Không nhắc mẫu nào → không lọc.
    named = {P._parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x}
    if named and set(t.pending_asks()) & P.PRODUCT_ASKS:
        for st in list(desc):
            a, rq, tg = parse_step(st)
            if a in ("read_quote", "read_stock") and str(tg).startswith("P"):
                p = t.product_ref(tg)
                if p and not (set(p["skus"]) & named):
                    removed[st] = "not_mentioned_this_turn"
                    del desc[st]
    # P1 (17/11): khách nêu NHÓM HÀNG (khác mẫu đang bàn) → không mời đọc giá / kho mẫu ngoài nhóm đó (tránh "Ngoài ra bên em có mẫu
    # cũ…"); giữ đích của yêu cầu đặt hàng còn hiệu lực. Phạm vi chốt đầu lượt (P.question_scope), không theo focus đổi giữa vòng.
    for st in list(desc):
        a, rq, tg = parse_step(st)
        if a in ("read_quote", "read_stock") and str(tg).startswith("P"):
            p = t.product_ref(tg)
            if p and P.outside_question_scope(t, p["skus"]):
                removed[st] = "outside_question_scope"
                del desc[st]
    steps = list(desc)
    parsed = legacy
    return {"step": steps, "desc": desc, "display": {x: display_of(x) for x in steps}, "removed": removed,
            # dạng cũ (chỉ để bộ quyết định có kịch bản trong test chọn ref); Jev chỉ thấy "step"
            "action": list(dict.fromkeys(p[0] for p in parsed)),
            "request_ref": list(dict.fromkeys([p[1] for p in parsed if p[1]] + ["none"])),
            "target_ref": list(dict.fromkeys([p[2] for p in parsed if p[2]] + ["none"]))}


def validate(step, opts):
    """Bước (canonical) có trong danh mục hiện tại? → lý do sai hoặc None."""
    return None if step in opts["step"] else "step_not_allowed"


def to_canonical(step, opts):
    """Tên hiển thị Jev chọn → ID canonical (ánh xạ của chính danh mục này). ID canonical giữ nguyên (bộ quyết định có kịch bản,
    phát lại trace v6)."""
    back = {v: k for k, v in (opts.get("display") or {}).items()}
    return back.get(step, step)


# ---------------------------------------------------------------------- bộ quyết định

def jev_decide(state, opts):
    """MỘT Choice trên danh mục bước nguyên tử đã gắn đối tượng (v4). → {"step", "confidence", "backend", "ms"}.
    Lỗi → raise (vòng lặp dừng, không fallback)."""
    t0 = time.perf_counter()
    disp = opts.get("display") or {x: x for x in opts["step"]}
    shown = {disp[x]: opts["desc"][x] for x in opts["step"]}          # Jev chỉ thấy tên hiển thị + mô tả
    if settings.jev_simulated:
        from harness.jev_adapter import infer
        schema = {"type": "object", "additionalProperties": False, "required": ["step"],
                  "properties": {"step": {"type": "string", "enum": list(shown)}}}
        d = infer(f"{INSTRUCTIONS}\nCác bước: {shown}\nDữ liệu: {state}\nTrả JSON step.", schema)
        return {"step": to_canonical(d.get("step"), opts), "shown": d.get("step"), "confidence": None,
                "backend": "qwen_simulated_jev", "ms": int((time.perf_counter() - t0) * 1000)}
    from typesafe_sdk import Choice
    from harness.question_classifiers.jev_slots import _client
    q = {"next_step": Choice(instructions=INSTRUCTIONS, criteria=shown)}
    r = _client().system_one(state=state, questions=q, model=settings.jev_model)
    ch = r.choices["next_step"]
    return {"step": to_canonical(ch.choice, opts), "shown": ch.choice, "confidence": {"next_step": float(ch.confidence)},
            "backend": f"jev:{settings.jev_model}", "ms": int((time.perf_counter() - t0) * 1000)}


# ---------------------------------------------------------------------- vòng lặp

def run(c, decider=None):
    """Chạy vòng lập kế hoạch cho lượt. Ghi s.planner_loop (trace). → "stop" nếu lượt kết thúc trong vòng (clarify / finish /
    thao tác terminal); None nếu dừng do ngân sách / lỗi để các dòng chung (fallback…) chạy tiếp."""
    s = c.s
    decide = decider or jev_decide
    t = P.Turn(c)
    t.reuse_quotes = True              # patch cuối 13/11: dùng lại view báo giá đã đọc trong lượt; trần tool cứng; nghĩa vụ phản hồi giỏ
    t.decisions = []
    stop, seen, result = None, set(), None
    while True:
        if len(t.decisions) >= settings.b2_max_decisions:
            stop = "budget_exhausted:decisions"; break
        if time.perf_counter() - t.t0 > settings.b2_deadline_s:
            stop = "budget_exhausted:deadline"; break
        opts = options(t)
        try:
            d = decide(state_for(t), opts)
        except Exception as e:
            stop = f"planner_error:{type(e).__name__}"
            t.decisions.append({"error": f"{type(e).__name__}: {str(e)[:160]}"})
            break
        step = d.get("step") or step_of(d.get("action"), d.get("request_ref"), d.get("target_ref"))
        step = to_canonical(step, opts)
        action, rq, tg = parse_step(step)
        rec = {"step": step, "shown": d.get("shown") or (opts.get("display") or {}).get(step), "action": action, "request_ref": rq,
               "target_ref": tg, **{k: d.get(k) for k in ("confidence", "backend", "ms")}}
        if opts.get("removed"):
            rec["removed"] = dict(opts["removed"])          # bước bị lọc theo guard (S8) — ghi lý do, không phải bằng chứng Jev chọn tốt
        t.decisions.append(rec)
        bad = validate(step, opts)
        if bad:
            rec["rejected"] = bad
            stop = f"invalid_tuple:{bad}"; break
        conf = d.get("confidence") or {}
        if settings.b2_min_conf > 0 and conf and min(conf.values()) < settings.b2_min_conf:
            rec["rejected"] = "low_confidence"
            stop = "low_confidence"; break
        # "tiến triển" = có bằng chứng mới (giá / kho / đơn / hạn đổi trả / biến thể), ask đã trả lời, hoặc state yêu cầu đổi
        key = (step, len(t.quotes), len(t.stock), t.orders is not None, len(t.windows), len(t.vrefs), len(t.answered),
               tuple(sorted((k, v["outcome"]) for k, v in t.ask_outcome.items())), tuple(r["status"] for r in s.reqs.items))
        if action == "report_cart":
            # báo giỏ lần 2 khi giỏ không đổi không là tiến triển (bằng chứng giá / kho do chính lần báo trước ghi vào lượt)
            key = (step, tuple(s.cart), tuple(sorted((k, v["outcome"]) for k, v in t.ask_outcome.items())))
        if key in seen:
            rec["rejected"] = "no_progress"
            stop = "no_progress"; break
        seen.add(key)
        cost = P.step_cost(t, action, rq, tg)
        if t.tool_calls + cost > settings.b2_max_tool_calls:    # trần cứng: kiểm theo chi phí tối đa của bước (patch cuối 13/11)
            rec["rejected"] = f"tool_budget:{cost}>{settings.b2_max_tool_calls - t.tool_calls}"
            stop = "budget_exhausted:tool_calls"; break
        n_before = t.tool_calls
        obs = t.run(action, rq, tg, "jev")
        if t.tool_calls - n_before > cost:                       # ước tính sai → ghi rõ (không được xảy ra; probe kiểm)
            rec["cost_overrun"] = {"estimate": cost, "actual": t.tool_calls - n_before}
        if obs["status"] == "blocked" and rq:
            t.blocked[rq] = obs
        if obs.get("terminal") and obs["status"] == "ok":
            # kết thúc lượt trong vòng; finish không có nội dung → để dòng chung (hoãn / fallback / chào kết) trả lời.
            # 13/11: câu trả lời thuộc tính từ catalog không có goal riêng (renderer đọc facts.attribute_answer) vẫn là nội dung.
            result = "stop" if _has_content(c) else None
            stop = action
            break
    if stop and result is None:
        _halt(t, stop)
        result = "stop" if _has_content(c) else None
    opening_focus = P.apply_opening_focus(t, stop)   # TA1 (14/11): khách quay lại nêu mẫu khác → đọc giá đúng mẫu được nêu
    if opening_focus and "quote" in c.goals and result is None:
        result = "stop"
    P.reconcile_price_context(t)       # 13/11 vòng giỏ: giá mua riêng vs giá trong giỏ trước khi render (không gọi tool)
    order_gate = P.apply_order_gate(t)   # F8 (13/11): yêu cầu đặt bị cổng chặn → xin xác nhận, không ghi
    if order_gate and order_gate.get("goals") and result is None:
        result = "stop"                  # câu xin xác nhận là nội dung của lượt (không để dòng chung thay)
    unanswered = t.pending_asks()
    s.planner_loop = {"variant": "b2_jev", "encoding": "single_choice_atomic_steps", "stop": stop, "decisions": t.decisions,
                      "steps": [{k: v for k, v in o.items() if k not in ("dup", "resolved", "clarify_fn", "clarify_facts")} for o in t.steps],
                      "tool_calls": t.tool_calls, "ms": int((time.perf_counter() - t.t0) * 1000),
                      **({"halt_tool_calls": t.halt_tool_calls} if hasattr(t, "halt_tool_calls") else {}),
                      "asks": t.asks(), "answered": list(t.answered),
                      "unanswered": {a: (t.deferred.get(a) or stop) for a in unanswered},
                      "ask_outcome": t.ask_outcome,
                      "common_before_planner": t.common,
                      **({"price_context": t.price_context} if t.price_context else {}),
                      **({"order_gate": order_gate} if order_gate else {}),
                      **({"opening_focus": opening_focus} if opening_focus else {}),
                      **({"cart": {"before": list(getattr(c, "cart_before", None) or []), "after": list(s.cart),
                                  "source": getattr(c, "cart_source", None), "accessory_unclear": list(getattr(c, "cart_unclear", None) or [])}}
                         if s.cart or getattr(c, "cart_before", None) else {}),
                      "budget": {"tool_cap": "hard: step offered / run only if tool_calls + max_cost <= max_tool_calls",
                                 "max_decisions": settings.b2_max_decisions, "max_tool_calls": settings.b2_max_tool_calls,
                                 "deadline_s": settings.b2_deadline_s, "min_conf": settings.b2_min_conf}}
    s._why("b2_jev", f"stop={stop}, {len(t.decisions)} quyết định, {t.tool_calls} tool")
    return result


def _has_content(c):
    return bool(c.goals) or bool(c.facts.get("attribute_answer"))


def _halt(t, stop):
    """Dừng do ngân sách / lặp / lỗi: không ghi thêm; nêu đúng việc chưa làm. Yêu cầu bị chặn → hỏi đúng phần thiếu; không
    có gì để nói → để dòng chung (fallback) xử lý. Không tuyên bố đã tạo đơn nếu chưa có kết quả (goal chỉ từ observation)."""
    t.halting = True                    # v6: không gọi tool / không thực hiện nghiệp vụ trong phần dừng
    n_tools = len(t.s.tools.log)
    blocked = [o for o in t.steps if o["status"] == "blocked" and o.get("request_ref")
               and (o["request_ref"].startswith("X_") or (t.request(o["request_ref"]) or {}).get("status") in P.ACTIVE)]
    if blocked:
        t.run("clarify", blocked[-1]["request_ref"], None, f"halt:{stop}")
    elif t.s.reqs.hold:
        t.c.goals.append("ask_repeat")
    # patch cuối 13/11: yêu cầu add_to_cart chưa được phản hồi → báo mẫu đã có trong giỏ (không tool); tổng giỏ cần tool nên không
    # làm trong phần dừng
    if t.reuse_quotes and t.cart_obligation() and not t.cart_reported and t.cart_already():
        from harness.tools import product_name
        t.c.facts["cart_already"] = {"products": [product_name(x) for x in t.cart_already()]}
        t.c.goals += [g for g in ["cart_item_already"] if g not in t.c.goals]
        t.steps.append({"action": "halt_cart_reply", "status": "ok", "goals": ["cart_item_already"], "tools": []})
    # yêu cầu CÓ ĐIỀU KIỆN mở trong lượt chưa được phản hồi → phản hồi điều kiện từ bằng chứng đã có (không tool, không ghi)
    for r in t.active_requests():
        if r.get("condition") and r["turn"] == t.s.turn_no and r["id"] not in t.addressed:
            g = P.condition_reply(t, r)
            if g:
                t.c.goals += [x for x in g if x not in t.c.goals]
                t.addressed.add(r["id"])
                t.steps.append({"action": "halt_condition_reply", "request_ref": r["id"], "status": "ok", "goals": g, "tools": []})
    # A2 (15/11, duyệt): dừng mà câu khách hỏi còn treo và lượt KHÔNG có nội dung → hỏi lại đúng loại thay vì để câu đệm rỗng
    # ("Dạ vâng ạ"): câu hỏi về sản phẩm + có mẫu của khách → hỏi khách muốn biết gì về mẫu đó; còn lại → xin khách nói lại.
    # Không gọi tool, không ghi; ask vẫn ghi là chưa trả lời (unanswered) trong trace.
    pend = t.pending_asks()
    if pend and not _has_content(t.c):
        par, kind = P.customer_product(t)
        if set(pend) & (P.PRODUCT_ASKS | {"attribute"}) and kind == "one":
            P.ask_which_attribute(t.c, par)
            g = "ask_which_attribute"
        else:
            t.c.goals.append("ask_repeat")
            g = "ask_repeat"
        t.steps.append({"action": "halt_ask_reply", "status": "ok", "goals": [g], "asks": pend, "tools": []})
    t.halt_tool_calls = len(t.s.tools.log) - n_tools      # phải = 0 (kiểm ở E0 V22); ghi trace thay vì làm đổ lượt
