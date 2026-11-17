"""B3-workflow (THIET-KE-B1-B2-JEV-B3-WORKFLOW mục 5; phạm vi duyệt 12/11 mục 3): CODE sở hữu tiến trình nghiệp vụ, quyết bước
kế của từng yêu cầu từ request_state + bằng chứng của lượt + kết quả tool. Điều phối TRẢ LỜI giữ bảng B1 (dòng N02, R13–R23,
R26, R27 chạy bằng bảng, cùng predicate / handler / thứ tự) — khác B2 (Jev điều phối cả nghiệp vụ lẫn trả lời, dùng chung
handler / renderer có nguồn). Hành động nguyên tử dùng chung B2 (harness/plan_primitives.py).

Pha theo đúng vị trí dòng B1 để thứ tự với dòng trả lời giữ như B1:
  orders_pre    (vị trí T01, 75):  đổi địa chỉ đơn có yêu cầu (T01); R08 hỏi giả định trả → câu hỏi chính sách; R09 ý mua + địa
                                   chỉ, chưa có đơn → đặt hàng; E03 hủy → chuyển nhân viên; R10 bổ sung địa chỉ đơn vừa tạo.
  orders_change (vị trí R11, 100): yêu cầu đổi / trả còn hiệu lực → agenda từng bước (đọc đơn → hạn đổi trả → kho biến thể mới →
                                   ghi); intent đổi/trả KHÔNG có yêu cầu → xem trước chỉ đọc (executor B1, không thể ghi vì không
                                   có quyền); R12 tra đơn. (N02 tiền hoàn chạy GIỮA hai pha như B1.)
  sales         (vị trí E12, 244): E12 từ chối sau đề nghị; E15 hẹn chốt sau; R28 ý mua; nhóm order (R29 bổ sung địa chỉ | R30 giá
                                   đổi chưa báo | agenda đặt hàng | R32 xin xác nhận khi vừa hỏi vừa muốn mua); R33; gọi lại.
Progress DẪN XUẤT mỗi lượt (không lưu `ready` thành quyền); mỗi yêu cầu chạy tới điểm dừng tự nhiên, tối đa PLANNER_B3_MAX_STEPS
bước; operation thất bại / unresolved không tự gửi lại (request_state + tool_outcome dùng chung).
"""
from core.config import settings
from harness import plan_primitives as P
from harness import planner_table as T

READS = ("read_quote:", "read_stock:", "check_window:")


def _pred(c, name):
    return bool((T.PREDS_TARGET.get(name) or T.PREDS[name])(c))


def _loop(c):
    s = c.s
    if getattr(s, "planner_loop", None) is None or s.planner_loop.get("variant") != "b3_workflow":
        s.planner_loop = {"variant": "b3_workflow", "steps": [], "agenda": []}
    return s.planner_loop


def run(c, phase):
    t = getattr(c, "_b3_turn", None)
    if t is None:
        t = c._b3_turn = P.Turn(c)
    lp = _loop(c)
    n0 = len(t.steps)
    res = {"orders_pre": _orders_pre, "orders_change": _orders_change, "sales": _sales}[phase](c, t, lp)
    lp["steps"] += [{k: v for k, v in o.items() if k not in ("dup", "resolved", "clarify_fn", "clarify_facts")} for o in t.steps[n0:]]
    lp["tool_calls"] = t.tool_calls
    return res


def _note(lp, rid, state, nxt):
    lp["agenda"].append({"request": rid, "progress": state, "next": nxt})


def _progress(c, t, lp, r):
    """Agenda của MỘT yêu cầu: thử thực hiện; bị chặn vì thiếu BẰNG CHỨNG → đọc đúng phần thiếu rồi thử lại; thiếu thông tin
    khách / quyền / điều kiện → hỏi rõ (câu hỏi có nguồn do hành động dựng). → observation cuối."""
    o = None
    while True:
        if len(t.steps) >= settings.b3_max_steps:          # trần bước của LƯỢT (mọi pha, mọi yêu cầu) — xem core/config.py
            lp["stop"] = "max_steps"
            return o
        o = t.run("commit_request", r["id"], None, "workflow")
        miss = o.get("missing") or []
        if o["status"] != "blocked":
            _note(lp, r["id"], "executed", o["status"])
            return o
        reads = [m for m in miss if m == "read_order" or m.startswith(READS)]
        if reads:
            _note(lp, r["id"], "missing_evidence", ",".join(reads))
            before = (len(t.quotes), len(t.stock), t.orders is not None, len(t.windows))
            for m in reads:
                act, _, ref = m.partition(":")
                if act == "read_stock" and ref.startswith("P") and any(P._ref_of(t, k) == ref for k in t.quotes):
                    continue                       # view báo giá đã đọc kèm tồn kho
                t.run(act, None, ref or None, "workflow")
            if (len(t.quotes), len(t.stock), t.orders is not None, len(t.windows)) == before:
                lp["stop"] = "no_progress"
                return o
            continue
        _note(lp, r["id"], "needs_customer:" + ",".join(miss), "clarify")
        if any(m.startswith("not_executed:") for m in miss):
            return o                                # executor đặt hàng đã dựng câu trả lời (hết hàng / COD / điều kiện…)
        t.blocked[r["id"]] = o
        t.run("clarify", r["id"], None, "workflow")
        return o


# ---------------------------------------------------------------------- pha orders_pre (T01, R08, R09, E03, R10)

def _orders_pre(c, t, lp):
    s = c.s
    if _pred(c, "address_change_request"):                                   # T01
        r = s.reqs.active("change_order_address")[-1]
        _note(lp, r["id"], "address_change_requested", "agenda")
        o = _progress(c, t, lp, r)
        if o and o.get("goals"):
            c.memo["address_dispatched"] = True
            s._addr_dispatched = True
    if c.it == "order_change" and _pred(c, "hypothetical_refund_ask"):      # R08
        s._why("hypothetical_return", "hỏi giả định về trả hàng, không tạo yêu cầu trả")
        c.it = "policy_question"
    if c.it == "order_change" and _pred(c, "buy_intent") and not s.orders_created and _pred(c, "slot_address"):   # R09
        c.it = "place_order"
    if _pred(c, "cancel_ask") and T.PREDS["has_any_order"](c):              # E03
        _note(lp, "X_CANCEL", "cancel_requested", "handoff")
        t.run("commit_request", "X_CANCEL", None, "workflow")
        return "stop"
    if c.it == "order_change" and s.orders_created and _pred(c, "slot_address") \
            and not getattr(s, "_addr_dispatched", False):                 # R10 (tiếp tục đơn vừa tạo)
        _note(lp, None, "created_order_address", "complete_address")
        c.goals += s._update_address(c.slots["address"], c.facts)
        return "stop"
    return None


# ---------------------------------------------------------------------- pha orders_change (R11, R12)

def _orders_change(c, t, lp):
    s = c.s
    ops = [r for r in t.order_ops_active() if r["kind"] in ("exchange", "return")]
    if ops:
        r = ops[-1]
        _note(lp, r["id"], f"{r['kind']}_requested", "agenda")
        o = _progress(c, t, lp, r)
        if o and o.get("window_passed"):
            c.it = "product_inquiry"                 # như B1: quá hạn → tư vấn tiếp, các dòng trả lời sau vẫn chạy
            return None
        return "stop" if c.goals else None
    if c.it == "order_change" and not getattr(s, "_addr_dispatched", False):
        # không có yêu cầu đổi / trả có căn cứ: chỉ xem trước (đọc đơn / chính sách / tồn kho) — executor B1 không thể ghi vì
        # request_state không cấp quyền khi không có yêu cầu
        _note(lp, None, "order_change_without_request", "preview_read_only")
        n = len(c.goals)
        g = s._plan_order_change(c.text, c.facts)
        if g == ["WINDOW_PASSED"]:
            if not s.window_told:
                s.window_told = True
                c.goals.append("exchange_window_passed")
            c.it = "product_inquiry"
            return None
        c.goals += [x for x in g if x not in c.goals]
        return "stop" if c.goals[n:] else None
    if c.it == "order_status":                                             # R12
        _note(lp, None, "order_status_asked", "read_order")
        t.run("read_order", None, None, "workflow")
        return "stop"
    return None


# ---------------------------------------------------------------------- pha sales (E12, E15, R28–R34, N04)

def _sales(c, t, lp):
    s = c.s
    if _pred(c, "declines_after_confirm"):                                 # E12
        _note(lp, None, "proposal_declined", "defer_close")
        T.h_defer_close(c, {"do": {"args": {"why": "khách từ chối sau câu xác nhận đơn"}}})
    if c.it == "place_order" and _pred(c, "later_close") and not _pred(c, "slot_address"):   # E15
        _note(lp, None, "customer_defers_close", "defer_close")
        T.h_defer_close(c, {"do": {"args": {"why": "khách hẹn chốt sau (lát / để mai), chưa tạo đơn"}}})
    if _pred(c, "wants"):                                                   # R28
        T.h_mark_buy_intent(c, None)
    orders_req = [x for x in t.active_requests() if x["kind"] == "place_order"]
    deferring = (c.u or {}).get("response") == "defer"
    if _pred(c, "orders_created") and _pred(c, "slot_address") and not c.memo.get("address_dispatched") \
            and not getattr(s, "_addr_dispatched", False) and not orders_req:   # R29: bổ sung địa chỉ đơn vừa tạo
        _note(lp, None, "created_order_missing_address", "complete_address")
        T.h_update_address(c, None)
    elif orders_req and _pred(c, "stale_focus_untold"):                    # R30: giá / KM đổi chưa báo → báo lại trước khi ghi
        _note(lp, orders_req[0]["id"], "price_changed_untold", "requote")
        T.h_stale_quote(c, None)
    elif orders_req:
        multi = len(orders_req) > 1
        for r in orders_req:
            if deferring and r["turn"] < s.turn_no:
                _note(lp, r["id"], "customer_defers", "wait")
                continue
            if multi:
                _note(lp, r["id"], "multi_request", "clarify")
                t.run("clarify", r["id"], None, "workflow")
                break
            _note(lp, r["id"], "order_requested", "agenda")
            _progress(c, t, lp, r)
    elif _pred(c, "wants_asking_quoted"):                                  # R32
        _note(lp, None, "wants_but_asking", "confirm_order")
        c.goals.append("confirm_order")
    if _pred(c, "stale_goal_untold"):                                      # R33
        T.h_stale_requote(c, None)
    for r in [x for x in t.active_requests() if x["kind"] == "callback"]:   # R34 / N04
        _note(lp, r["id"], "callback_requested", "commit")
        o = t.run("commit_request", r["id"], None, "workflow")
        if o["status"] == "blocked":
            c.goals += [g for g in o.get("clarify") or [] if g not in c.goals]
    return None
