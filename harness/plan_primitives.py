"""Hành động nguyên tử dùng chung cho B2-Jev và B3-workflow (THIET-KE-B1-B2-JEV-B3-WORKFLOW mục 4.3 / 5).

Mỗi hành động: code resolve ref → dữ liệu có nguồn, gọi tool, ghi BẰNG CHỨNG của lượt (giá / kho / đơn / hạn đổi trả theo đúng
đối tượng), trả một OBSERVATION: {action, refs, status: ok|blocked|error|noop, missing, goals, result, tools}. Hành động không tự
gọi tiếp chuỗi nghiệp vụ còn thiếu: ghi mà thiếu bằng chứng → `blocked` kèm phần thiếu, chủ sở hữu tiến trình (Jev ở B2, workflow
ở B3) quyết định bước sau. Phạm vi kỹ thuật bắt buộc bên trong một hành động được công khai trong SCOPE.

v2 (duyệt 12/11, mục 4): đổi địa chỉ / đổi sản phẩm / trả hàng tách thành bước — read_order (đơn thuộc khách), check_window (hạn
đổi trả theo phiên bản đơn), read_stock V# (tồn kho biến thể mới) — và commit_request chỉ còn MỘT lần ghi `order.update` sau khi
code kiểm quyền + điều kiện trên bằng chứng đã đọc trong lượt. Không còn chuỗi tự tra – tự quyết – tự ghi trong commit_request.

Giá trị mới của khách chỉ đến từ bộ hiểu DeepSeek đã kiểm (slots / request_items); planner không sinh giá, địa chỉ, SKU, mã đơn.
"""
import time

from core.config import settings  # bước 2 (18/11): cờ B2_TWO_TIER cho clarify_field / giữ giá theo biến thể

from harness import planner_table as T
from harness.request_state import ACTIVE, _parent

ACTIONS = ("read_quote", "read_stock", "read_order", "check_window", "read_policy", "answer_ask", "commit_request", "clarify",
           "report_cart", "finish", "clarify_field")     # clarify_field: bước 2 (18/11), chỉ được đưa vào danh mục khi B2_TWO_TIER
ORDER_OP_KINDS = ("change_order_address", "exchange", "return")
OP_ACTION_VI = {"change_order_address": "đổi địa chỉ giao", "exchange": "đổi hàng", "return": "trả hàng"}   # V45: hỏi đơn nào cho thao tác gì
# Phạm vi kỹ thuật công khai của từng hành động (tool có thể gọi bên trong). Ghi vào trace; fixture kiểm không vượt phạm vi.
SCOPE = {
    "read_quote": ("pricing.get_quote", "inventory.check"),     # view báo giá dùng chung (CallSession._quote) đọc kèm tồn kho
    "read_stock": ("inventory.check",),                         # P# sản phẩm, hoặc V# biến thể mới của yêu cầu đổi
    "read_order": ("order.status",),
    "check_window": (),                                         # tính hạn đổi trả từ đơn đã đọc + chính sách theo phiên bản
    "read_policy": (),                                          # knowledge.search (RAG chính sách, không phải tool MCP)
    "answer_ask": ("pricing.get_quote", "inventory.check", "order.status", "pricing.quote_order", "catalog.search"),
    "commit_request:place_order": ("pricing.quote_order", "order.create", "order.update"),   # update = bổ sung địa chỉ đơn vừa tạo
    "commit_request:change_order_address": ("order.update",),
    "commit_request:exchange": ("order.update",),
    "commit_request:return": ("order.update",),
    "commit_request:callback": ("schedule.callback",),
    "commit_request:cancel": ("handoff.transfer",),
    "commit_request:complete_address": ("order.update",),
    "clarify": ("pricing.quote_order", "handoff.transfer"),     # hỏi rõ nhiều đơn hàng / chuyển nhân viên đơn nhiều dòng
    # 13/11 (bàn giao cải thiện B2): báo giỏ hiện có — CHỈ ĐỌC (giá từng món + quote_order), không sửa giỏ, không order.*.
    # Giỏ chỉ đổi ở _prepare_target (một chủ duy nhất, theo yêu cầu add_to_cart / place_order của bộ hiểu).
    "report_cart": ("pricing.get_quote", "inventory.check", "pricing.quote_order"),
    "finish": (),
}
REASON_CODES = ("need_price", "need_stock", "need_order", "need_window", "need_policy", "customer_asked", "commit_ready",
                "missing_info", "conflict", "nothing_to_do", "after_blocked")
DEFER_REASONS = ("safety", "missing_source", "tool_error", "conflict")

# ask (enum bộ hiểu) → các handler trả lời có nguồn của bảng (cùng code với dòng trả lời B1)
ASK_HANDLERS = {
    "price": ("quote",), "promo": ("quote",), "promo_end": ("quote",), "stock": ("quote",), "compare": ("quote",),
    "gift": ("quote", "gift_status"), "cod": ("cod_check",), "cart_total": ("cart_total",), "refund_amount": ("refund_amount",),
    "return_policy": ("policy_answer",), "payment_method": ("policy_answer",), "delivery_time": ("policy_answer",),
    "policy": ("policy_answer",), "other": ("policy_answer",), "quality": ("policy_answer",),
    "warranty": ("warranty_fact", "policy_answer"), "attribute": ("attr_check", "policy_peek"),
    "delivery_address": ("order_status",), "order_status": ("order_status",), "recommend": ("recommend",),
    "budget": ("budget_fit",),        # V52: nghĩa vụ NGẦM khi khách nêu ngân sách lúc đang bàn một mẫu (_budget_turn), không phải ask bộ hiểu
}

# ---------------------------------------------------------------------- 13/11: kết quả trả lời ask có trạng thái thật
# Bàn giao docs/PLAN/BAN-GIAO-CAI-THIEN-B2-SAU-DO-V6-2026-11-13.md (chốt sau vòng 2): `ask_outcome[topic]` lưu outcome + evidence
# refs + reason RIÊNG, không nhét vào DEFER_REASONS.
#   answered            có nội dung đúng chủ đề + bằng chứng thuộc loại TOPIC_EVIDENCE của chủ đề (tool đúng đối tượng / catalog /
#                       chính sách / khối mẫu cố định được phép) — chỉ có tool call hoặc goal thì CHƯA đủ;
#   responded_no_source có khối nói chưa có thông tin (no_info) — đã phản hồi, không phải đã trả lời dữ kiện;
#   needs_customer      có câu hỏi cụ thể cho khách về phần thiếu (goal câu hỏi của generator.QUESTION_GOALS / ask_need);
#   noop | blocked | error  ghi rõ; KHÔNG append answered; ask vẫn còn nghĩa vụ (không âm thầm xóa để cho finish).
#   responded_common    (patch cuối 13/11) ask `other` đã được khối chung CỐ ĐỊNH của lượt phản hồi (is_bot / refuse_internal,
#                       tạo trước vòng planner) — không phải câu trả lời dữ kiện; ghi vetted_block + dòng nguồn.
ASK_OUTCOMES = ("answered", "responded_no_source", "needs_customer", "responded_common", "noop", "blocked", "error")
RESPONDED = frozenset({"answered", "responded_no_source", "needs_customer", "responded_common"})
COMMON_RESPONSE_GOALS = ("is_bot", "refuse_internal")
# nhãn thông tin catalog để hỏi lại khách đúng nội dung (chỉ khóa renderer có câu mẫu)
ATTR_LABELS = {"room_area_m2": "diện tích phòng phù hợp", "features": "tính năng", "warranty_months": "bảo hành",
               "child_safe_lock": "khóa trẻ em", "material": "chất liệu", "stages": "số cấp lọc", "max_weight_kg": "tải trọng",
               "volume_ml": "dung tích"}
_PRICE_EV = frozenset({"tool:pricing.get_quote"})
_POLICY_EV = frozenset({"policy", "window"})
TOPIC_EVIDENCE = {
    "price": _PRICE_EV, "promo": _PRICE_EV, "promo_end": _PRICE_EV, "compare": _PRICE_EV, "gift": _PRICE_EV,
    "stock": frozenset({"tool:inventory.check"}),           # kho đọc trực tiếp (view báo giá luôn đọc kèm inventory.check)
    "recommend": _PRICE_EV,
    "budget": _PRICE_EV,
    "cod": frozenset({"tool:pricing.get_quote", "tool:pricing.quote_order", "vetted_block"}),   # cod_ok / cod_limit là mẫu cố định
    "cart_total": frozenset({"tool:pricing.quote_order"}),
    "refund_amount": frozenset({"tool:order.update", "tool:order.status"}),
    "return_policy": _POLICY_EV, "payment_method": _POLICY_EV, "delivery_time": _POLICY_EV, "policy": _POLICY_EV,
    "other": _POLICY_EV, "quality": _POLICY_EV,
    "warranty": frozenset({"catalog", "policy"}),
    "attribute": frozenset({"catalog"}),
    "delivery_address": frozenset({"tool:order.status"}), "order_status": frozenset({"tool:order.status"}),
}
# Thuộc tính: thuật ngữ khách (đã bỏ dấu, khớp theo ranh giới từ) → khóa catalog. Bảng TĨNH rà tay, chỉ gồm khóa renderer có câu
# mẫu (renderer.ATTR_PHRASE). Không phải bộ hiểu ý: chỉ ánh xạ tên thuộc tính khách nói ra sang khóa dữ liệu; thuật ngữ chứng nhận /
# xuất xứ (ATTR_ASK_RX) không có khóa catalog → phản hồi thiếu nguồn.
ATTR_TERM_KEYS = {
    "room_area_m2": ("dien tich", "met vuong", "m2", "phong bao nhieu", "phong rong"),
    "features": ("tinh nang", "chuc nang"),
    "warranty_months": ("bao hanh",),
    "child_safe_lock": ("khoa tre em", "khoa an toan"),
    "material": ("chat lieu", "lam bang"),
    "stages": ("cap loc", "may loi", "bao nhieu loi"),
    "max_weight_kg": ("tai trong", "chiu tai", "nang toi da"),
    "volume_ml": ("dung tich",),
}


class Turn:
    """Bằng chứng + tiến trình trong MỘT lượt khách (không mang sang lượt sau — dữ liệu cũ phải đọc lại)."""

    def __init__(self, c):
        self.c, self.s = c, c.s
        self.quotes = {}            # sku biến thể đã đọc → view báo giá (có in_stock / stock_qty)
        self.stock = {}             # sku → {"in_stock", "qty", "restock_expected"}
        self.orders = None          # kết quả order.status THÔ (đã đọc trong lượt) — bằng chứng đơn thuộc khách
        self.windows = {}           # order_id → quyết định hạn đổi trả (planner_policy.exchange_window)
        self.vrefs = {}             # V# → {"sku", "order_id", "action"} biến thể mới của yêu cầu đổi (do code dựng)
        self.policy = None
        self.steps = []
        self.answered, self.deferred = [], {}
        self.blocked = {}           # request id → observation bị chặn gần nhất (để hỏi rõ đúng phần thiếu)
        self.addressed = set()      # yêu cầu đã được phản hồi trong lượt (thực hiện / hỏi rõ / báo điều kiện có nội dung)
        self.ask_outcome = {}       # 13/11: topic → {"outcome", "evidence": [{"kind", "ref"}], "reason"} (lần trả lời gần nhất)
        self.reuse_quotes = False   # patch cuối 13/11 (chỉ B2 bật): s._quote trong hành động dùng lại view đã đọc TRONG lượt
        self.cart_reported = False  # patch cuối 13/11: đã phản hồi giỏ cho yêu cầu add_to_cart của lượt
        self.cart_reported_for = None  # 13/11 vòng giỏ: giỏ (tuple SKU) lúc báo giỏ gần nhất — giỏ không đổi thì không báo lại
        self.price_context = None   # 13/11 vòng giỏ: nhật ký đối chiếu giá mua riêng / giá trong giỏ trước khi render (trace)
        # 13/11: khối trả lời CHUNG đã tạo trước vòng planner (R01/R02/R05/N03…) — nạp cho planner để biết phần đã phản hồi;
        # KHÔNG tự coi ask nào đã xong (ask `other` rộng có thể chứa câu thứ hai).
        self.common = {"rows": [r for r in (getattr(self.s, "table_rows", None) or []) if ":" not in str(r)],
                       "goals": list(c.goals)}
        self.t0 = time.perf_counter()
        self.tool_calls = 0

    # ------------------------------------------------------------------ tiện ích
    def asks(self):
        out = [a for a in ((self.c.u or {}).get("asks") or []) if a in ASK_HANDLERS and a != "budget"]
        if _budget_turn(self):
            out.append("budget")          # V52: khách vừa nêu ngân sách khi đang bàn một mẫu → phải phản hồi trước khi kết thúc lượt
        return out

    def pending_asks(self):
        """Ask còn nghĩa vụ phản hồi: chưa answered / responded_no_source / needs_customer. noop / blocked / error vẫn còn."""
        return [a for a in self.asks() if a not in self.answered and a not in self.deferred
                and (self.ask_outcome.get(a) or {}).get("outcome") not in RESPONDED]

    def product_ref(self, ref):
        t = self.s.reqs.refmap.get(ref) if ref else None
        if t is None and ref and ref in self.order_target_parents():
            return {"type": "product", "skus": (ref,)}       # SKU cha của đối tượng yêu cầu (do code dẫn xuất, ngoài danh sách ứng viên)
        return t if t and t.get("type") == "product" and len(t.get("skus") or ()) == 1 else None

    def order_target_parents(self):
        """SKU cha là đối tượng của yêu cầu đặt hàng còn hiệu lực (bằng chứng đọc cho các SKU này phục vụ ghi, không là câu trả lời)."""
        out = set()
        for r in self.active_requests():
            if r["kind"] == "place_order" and (r.get("target") or {}).get("type") == "product":
                out |= {_parent(x) for x in r["target"]["skus"]}
        return out

    def order_ref(self, ref):
        """O# trong danh sách ứng viên, hoặc mã đơn có trong kết quả order.status đã đọc trong lượt."""
        t = self.s.reqs.refmap.get(ref) if ref else None
        if t and t.get("type") == "order":
            return t
        if ref and self.orders and any(o.get("order_id") == ref for o in self.orders):
            return {"type": "order", "order_id": ref}
        return None

    def order_of(self, oid):
        return next((o for o in self.orders or [] if o.get("order_id") == oid), None)

    def oref_of(self, oid):
        return next((k for k, v in self.s.reqs.refmap.items() if v.get("type") == "order" and v.get("order_id") == oid), oid)

    def request(self, rid):
        return next((r for r in self.s.reqs.items if r["id"] == rid), None)

    def active_requests(self):
        return [r for r in self.s.reqs.items if r["status"] in ACTIVE]

    def order_ops_active(self):
        return [r for r in self.active_requests() if r["kind"] in ORDER_OP_KINDS]

    def extra_requests(self):
        """Yêu cầu không có bản ghi state, ref do code cấp:
        X_CANCEL — khách đòi hủy và có đơn (mock không có thao tác hủy → chuyển nhân viên);
        X_COMPLETE_ADDRESS — khách đọc địa chỉ cho đơn VỪA tạo trong cuộc còn thiếu địa chỉ (tiếp tục yêu cầu đặt hàng đã thực
        hiện, như dòng R29 của B1)."""
        u, s, out = self.c.u or {}, self.s, []
        if "cancel" in (u.get("requests") or []) and T.PREDS["has_any_order"](self.c):
            out.append("X_CANCEL")
        from core.config import settings
        if settings.planner_variant == "b2_jev":
            if s.reqs.completion_for(s):                     # V48: địa chỉ đã gắn cho đúng một đơn vừa tạo còn thiếu địa chỉ
                out.append("X_COMPLETE_ADDRESS")
        elif self.c.slots.get("address") and s.reqs.done_orders_ok() and any(not o.get("address") for o in s.orders_created) \
                and not s.reqs.has_active("change_order_address"):
            out.append("X_COMPLETE_ADDRESS")
        return out

    def variant_refs(self):
        """V# cho biến thể mới của yêu cầu đổi còn hiệu lực, khi đã đọc đơn đích trong lượt và biến thể xác định được từ dữ liệu
        đã kiểm (mẫu khác parser catalog thấy trong câu, hoặc size bộ hiểu trả)."""
        for r in self.order_ops_active():
            if r["kind"] != "exchange":
                continue
            o = _order_for(self, r, None)[0]
            if o is None:
                continue
            new_sku, action, _ = _exchange_variant(self, o)
            if new_sku and not any(v["sku"] == new_sku for v in self.vrefs.values()):
                self.vrefs[f"V{len(self.vrefs) + 1}"] = {"sku": new_sku, "order_id": o["order_id"], "action": action}
        return list(self.vrefs)

    def cart_obligation(self):
        """Lượt có yêu cầu add_to_cart làm giỏ được chạm tới (thêm mới hoặc mẫu đã có) → phải phản hồi giỏ trước khi kết thúc."""
        return "add_to_cart" in ((self.c.u or {}).get("requests") or []) and bool(getattr(self.c, "cart_touched", None))

    def cart_already(self):
        """SKU khách bảo thêm nhưng ĐÃ có trong giỏ trước lượt (giỏ không có số lượng → không đổi)."""
        before = getattr(self.c, "cart_before", None) or []
        return list(dict.fromkeys(x for x in getattr(self.c, "cart_touched", None) or [] if x in before and x in self.s.cart))

    def quote_view_reused(self, sku):
        return self.reuse_quotes and sku in self.quotes

    def run(self, action, request_ref=None, target_ref=None, why=None):
        """Thực thi một hành động; ghi observation vào steps. Đếm tool call theo log của ToolBox (kể cả lời gọi lỗi).
        B2 (reuse_quotes): s._quote(sku) không basket trong hành động trả về view ĐÃ đọc trong chính lượt này (cùng SKU) thay vì
        gọi lại pricing.get_quote + inventory.check — bằng chứng cùng lượt, không phải cache liên lượt."""
        n0 = len(self.s.tools.log)
        fn = globals()["_" + action]
        patched = False
        if self.reuse_quotes:
            s, orig, t = self.s, self.s._quote, self

            def _quote(sku, role="advised", basket=None):
                if basket is None and sku in t.quotes:
                    return dict(t.quotes[sku])
                view = orig(sku, role, basket)
                if basket is None and isinstance(view, dict) and view.get("final_price_vnd") is not None:
                    # 13/11 vòng giỏ: MỌI lần đọc get_quote không basket trong lượt (kể cả bên trong report_cart) là bằng chứng
                    # giá MUA RIÊNG của lượt — không đọc lại cùng SKU; khác bằng chứng giá TRONG GIỎ (quote_order)
                    t.quotes[sku] = dict(view)
                    t.stock.setdefault(sku, {"in_stock": view.get("in_stock"), "qty": view.get("stock_qty"),
                                             "restock_expected": view.get("restock_expected")})
                return view
            s._quote, patched = _quote, True
        try:
            obs = fn(self, request_ref, target_ref)
        except Exception as e:                      # lỗi code / tool không mong đợi: không ghi gì thêm, báo lỗi
            obs = {"status": "error", "error": f"{type(e).__name__}: {str(e)[:120]}"}
        finally:
            if patched:
                del self.s._quote
        new = self.s.tools.log[n0:]
        self.tool_calls += len(new)
        obs = {"action": action, "request_ref": request_ref, "target_ref": target_ref, "why": why, **obs,
               "tools": [t["name"] for t in new]}
        obs.setdefault("goals", [])
        if action in ("commit_request", "clarify") and request_ref and (obs["goals"] or obs["status"] not in ("blocked", "error")):
            self.addressed.add(request_ref)
        self.steps.append(obs)
        return obs


# ---------------------------------------------------------------------- hành động đọc

def _variant(t, sku):
    return t.s._target_variant(sku, t.c.text)


def _read_quote(t, req_ref, ref):
    p = t.product_ref(ref)
    if p is None:
        return {"status": "blocked", "missing": ["valid_product_ref"]}
    s, c = t.s, t.c
    sku = _variant(t, p["skus"][0])
    for_commit = _parent(sku) in t.order_target_parents()
    if settings.b2_two_tier and not for_commit:
        # bước 2 (18/11): ĐỌC ≠ CÔNG BỐ. Giá / KM phụ thuộc thuộc tính biến thể khách chưa nói → không phát giá mẫu gốc; ghi lý do +
        # trường còn thiếu cho planner (chọn clarify_field). Mọi biến thể liên quan như nhau → báo giá ngay bằng SKU đại diện.
        from harness import variant_gate as VG
        a = VG.analyze(s, sku, c.text)
        if a["state"] in ("needs", "unavailable"):
            t.withheld = {**(getattr(t, "withheld", None) or {}), a["target"]: a}
            return {"status": "ok", "goals": [], "result": {"sku": a["target"], "price_withheld": True,
                                                            "why": "price_depends_on_variant" if a["state"] == "needs" else "variant_unavailable",
                                                            "missing_fields": a.get("fields"), "options": a.get("options")}}
        if a["state"] == "uniform":
            sku = a["sku"]
    q = s._quote(sku, "chosen" if for_commit else "advised")
    if settings.b2_two_tier and not for_commit and a["state"] == "uniform":
        VG.present(q, a)
    t.quotes[sku] = q
    t.stock[sku] = {"in_stock": q.get("in_stock"), "qty": q.get("stock_qty"), "restock_expected": q.get("restock_expected")}
    if for_commit and not any(a in t.asks() for a in ("price", "promo", "stock")):
        # bằng chứng cho yêu cầu đặt hàng (như B1 đọc trong executor): không thành block báo giá riêng trong câu trả lời
        return {"status": "ok", "goals": [], "result": {"sku": sku, "final_price_vnd": q.get("final_price_vnd"),
                                                         "in_stock": q.get("in_stock"), "stock_qty": q.get("stock_qty"),
                                                         "use": "commit_evidence"}}
    goals = []
    first = "quote" not in c.facts
    if first:
        c.facts["quote"] = q
        if q.get("in_stock") is False:
            goals.append("out_of_stock"); c.facts["restock_expected"] = q.get("restock_expected")
        else:
            goals.append("quote")
        T._price_claim_target(c, q)                 # khách nhắc giá khác: chỉ giải thích khi có provenance (dùng chung B1)
        if s.focus is None or _parent(s.focus) != _parent(sku):
            s.focus, s.focus_by = sku, "planner"
    elif _parent(c.facts["quote"]["sku"]) != _parent(sku):
        c.facts["alternative"] = q; goals.append("alternative_quote")
    c.goals += [g for g in goals if g not in c.goals]
    return {"status": "ok", "goals": goals, "result": {"sku": sku, "final_price_vnd": q.get("final_price_vnd"),
                                                      "in_stock": q.get("in_stock"), "stock_qty": q.get("stock_qty")}}


def _variant_withhold(t):
    """Bước 2: đối tượng câu hỏi giá của lượt (như h_quote: mẫu so sánh / mẫu đang bàn; khách nêu đúng một mẫu thì mẫu đó) có phải
    giữ giá không → analysis | None."""
    from harness import variant_gate as VG
    c, s = t.c, t.s
    men = list(dict.fromkeys(_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x))
    target = men[0] if len(men) == 1 else ((c.alt or (c.mentioned[-1] if c.mentioned else None)) if c.compare else s.focus)
    return VG.withhold(s, target, c.text) if target else None


def _clarify_field(t, req_ref, ref):
    """Bước 2 (18/11): hỏi khách ĐÚNG MỘT thuộc tính biến thể còn thiếu cho tác vụ báo giá rồi kết thúc lượt. ref = "<field>@<P#>".
    Code đã kiểm trường có ảnh hưởng + còn thiếu (danh mục chỉ dựng từ variant_gate). Lưu tác vụ đang chờ (đối tượng, trường, lý do,
    các câu hỏi giá của lượt) vào s.pending_clarify để lượt sau gắn câu trả lời rồi tiếp tục. Không tool, không ghi."""
    from harness import variant_gate as VG
    field, _, pref = str(ref or "").partition("@")
    p = t.product_ref(pref)
    if p is None or field not in VG.FIELDS:
        return {"status": "blocked", "missing": ["valid_clarify_target"]}
    s, c = t.s, t.c
    a = VG.analyze(s, p["skus"][0], c.text)
    if a["state"] != "needs" or field not in (a.get("fields") or []):
        return {"status": "blocked", "missing": ["field_not_needed"], "result": {"state": a["state"]}}
    asks = [x for x in t.pending_asks() if x in PRICE_ASKS] or [x for x in t.asks() if x in PRICE_ASKS] or ["price"]
    prev = getattr(s, "pending_clarify", None) or {}
    same = prev.get("target") == a["target"] and prev.get("field") == field
    s.pending_clarify = {"task": "quote", "target": a["target"], "field": field, "purpose": "price_depends_on_variant",
                         "basis": a.get("basis"), "asks": asks, "turn": s.turn_no,
                         "tries": int(prev.get("tries") or 0) if same else 0}          # hỏi lại cùng trường: không đặt lại số lần
    c.facts["clarify_field"] = {"field": field, "field_vi": VG.FIELD_VI.get(field, field), "product": a["name"],
                                "options": (a.get("options") or {}).get(field) or []}
    goal = "ask_size_for_price" if field == "size" else "ask_variant"
    if goal not in c.goals:
        c.goals.append(goal)
    for x in asks:
        t.ask_outcome[x] = {"outcome": "needs_customer", "reason": f"clarify_field:{field}", "evidence": []}
    return {"status": "ok", "terminal": True, "goals": [goal], "result": {"asked": field, "product": a["name"]}}


def resume_pending_clarify(t):
    """Bước 2: đầu lượt — gắn câu trả lời của khách với tác vụ đang chờ. Khách nêu mẫu KHÁC / rút / từ chối → bỏ tác vụ. Thuộc tính đã
    đủ (biến thể rõ hoặc nhóm còn lại cùng giá-điều kiện) → mở lại đúng các câu hỏi giá đã chờ (planner phải trả lời). Khách nêu giá trị
    không có → báo phần thiếu (variant_unavailable). Vẫn thiếu → giữ thêm MỘT lượt rồi bỏ (không hỏi vòng lặp). → trace dict | None."""
    from harness import variant_gate as VG
    s, c = t.s, t.c
    pc = getattr(s, "pending_clarify", None)
    if not settings.b2_two_tier or not pc:
        return None
    u = c.u if isinstance(c.u, dict) else None
    full = s.u_turn or {}
    men = {_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x}
    out = {"pending": {k: pc.get(k) for k in ("target", "field", "purpose", "asks", "turn")}}
    if men and pc["target"] not in men:
        s.pending_clarify = None
        return {**out, "action": "dropped", "why": "target_changed"}
    if (full.get("response") or {}).get("act") in ("decline", "defer") or full.get("withdrawn"):
        s.pending_clarify = None
        return {**out, "action": "dropped", "why": "declined_or_withdrawn"}
    a = VG.analyze(s, pc["target"], c.text)
    if a["state"] in ("resolved", "uniform", "no_variants"):
        if u is not None:
            u["asks"] = list(dict.fromkeys(list(u.get("asks") or []) + list(pc["asks"])))
        s.pending_clarify = None
        return {**out, "action": "resumed", "state": a["state"], "sku": a.get("sku")}
    if a["state"] == "unavailable":
        c.facts["variant_unavailable"] = {"product": a["name"], "said": a.get("known"), "fields": a.get("fields"), "options": a.get("options")}
        if "variant_unavailable" not in c.goals:
            c.goals.append("variant_unavailable")
        s.pending_clarify = {**pc, "turn": s.turn_no}
        return {**out, "action": "told_unavailable"}
    pc["tries"] = int(pc.get("tries") or 0) + 1
    if pc["tries"] > 1:
        s.pending_clarify = None
        return {**out, "action": "dropped", "why": "unanswered_twice"}
    return {**out, "action": "kept", "missing": a.get("fields")}


def _read_stock(t, req_ref, ref):
    if str(ref or "").startswith("V"):
        t.variant_refs()
        v = t.vrefs.get(ref)
        if v is None:
            return {"status": "blocked", "missing": ["valid_variant_ref"]}
        inv = t.s.tools.call("inventory.check", sku=v["sku"])
        t.stock[v["sku"]] = {"in_stock": inv.get("in_stock"), "qty": inv.get("qty"), "restock_expected": inv.get("restock_expected")}
        return {"status": "ok", "goals": [], "result": {"sku": v["sku"], "in_stock": inv.get("in_stock"), "for": "exchange"}}
    p = t.product_ref(ref)
    if p is None:
        return {"status": "blocked", "missing": ["valid_product_ref"]}
    sku = _variant(t, p["skus"][0])
    inv = t.s.tools.call("inventory.check", sku=sku)
    t.stock[sku] = {"in_stock": inv.get("in_stock"), "qty": inv.get("qty"), "restock_expected": inv.get("restock_expected")}
    goals = []
    q = t.c.facts.get("quote")
    if inv.get("in_stock") is False and q and q.get("sku") == sku and "out_of_stock" not in t.c.goals:
        t.c.goals = [g for g in t.c.goals if g != "quote"] + ["out_of_stock"]
        t.c.facts["restock_expected"] = inv.get("restock_expected")
        goals = ["out_of_stock"]
    return {"status": "ok", "goals": goals, "result": {"sku": sku, "in_stock": inv.get("in_stock"), "qty": inv.get("qty")}}


def _read_order(t, req_ref, ref):
    """Tra đơn của khách (một lần order.status). Là câu trả lời (block tình trạng đơn) khi khách hỏi đơn / địa chỉ giao hoặc
    không có thao tác đơn nào đang chờ; là bằng chứng cho thao tác đơn thì không thêm block."""
    if ref and ref != "none" and t.order_ref(ref) is None and not t.s.reqs.refmap.get(ref):
        return {"status": "blocked", "missing": ["valid_order_ref"]}
    s, c = t.s, t.c
    t.orders = list(s._customer_orders())
    informational = bool({"order_status", "delivery_address"} & set(t.asks())) or c.it == "order_status" or not t.order_ops_active()
    goals = []
    if informational:
        goals = s._orders_view(t.orders, c.facts)
        c.goals += [g for g in goals if g not in c.goals]
    return {"status": "ok", "goals": goals, "result": {"orders": [o.get("order_id") for o in t.orders][-5:],
                                                      "use": "answer" if informational else "op_evidence"}}


def _check_window(t, req_ref, ref):
    """Hạn đổi / trả của MỘT đơn đã đọc trong lượt, theo phiên bản chính sách ở ngày tạo đơn (planner_policy.exchange_window).
    Kết quả là bằng chứng; quá hạn / chưa xác định được thì nêu cho khách (không ghi)."""
    from harness.planner_policy import exchange_window
    tg = t.order_ref(ref)
    if tg is None:
        return {"status": "blocked", "missing": ["valid_order_ref"]}
    if t.orders is None:
        return {"status": "blocked", "missing": ["read_order"]}
    o = t.order_of(tg["order_id"])
    if o is None:
        return {"status": "blocked", "missing": ["order_not_in_customer_orders"]}
    s, c = t.s, t.c
    od = o.get("created_on") or o.get("date")
    d = exchange_window(o, s.today) if od else None
    t.windows[o["order_id"]] = d
    if d is not None:
        c.facts["exchange_policy"] = d
    return {"status": "ok", "goals": [], "result": {"order_id": o["order_id"],
                                                   "eligible": None if d is None else d.get("eligible"),
                                                   "days": (d or {}).get("days"), "version": (d or {}).get("version")}}


def _read_policy(t, req_ref, ref):
    n = len(t.c.goals)
    T.h_policy_answer(t.c, None)
    t.policy = t.c.facts.get("policy")
    return {"status": "ok", "goals": t.c.goals[n:], "result": {"chunks": [h["chunk_id"] for h in t.policy or []]}}


def _question_goal(g):
    from core.llm.generator import QUESTION_GOALS
    return g in QUESTION_GOALS or g == "ask_need"


def _record_tool_evidence(t, new_log, facts_before):
    """S7 (13/11): bằng chứng tool do handler trả lời đọc trong CHÍNH hành động này → bằng chứng của lượt, đúng đối tượng:
    inventory.check(sku=X) → t.stock[X]; pricing.get_quote(sku=X, không basket) → t.quotes[X] CHỈ khi facts.quote / alternative
    được gán MỚI trong hành động này đúng SKU X (view báo giá dùng chung). Không cache ngoài lượt; một quote không đại diện giỏ."""
    c = t.c
    fresh = {k: c.facts.get(k) for k in ("quote", "alternative")
             if isinstance(c.facts.get(k), dict) and c.facts.get(k) is not facts_before.get(k)}
    for tc in new_log:
        a, r = tc.get("args") or {}, tc.get("result")
        if not isinstance(r, dict) or r.get("error"):
            continue
        if tc.get("name") == "inventory.check" and a.get("sku"):
            t.stock[a["sku"]] = {"in_stock": r.get("in_stock"), "qty": r.get("qty"), "restock_expected": r.get("restock_expected")}
        elif tc.get("name") == "pricing.get_quote" and a.get("sku") and not a.get("basket_skus"):
            view = next((v for v in fresh.values() if v.get("sku") == a["sku"]), None)
            if view is not None:
                t.quotes[a["sku"]] = view


def _evidence_of(t, topic, new_log, new_goals, facts_before):
    """Bằng chứng của lần trả lời: [{"kind", "ref"}]. kind: tool:<tên> (đúng đối tượng của câu trả lời) | catalog | policy |
    window (hạn đổi trả theo đơn + phiên bản chính sách) | vetted_block (goal mẫu cố định)."""
    c, ev = t.c, []
    answer_skus = {(c.facts.get(k) or {}).get("sku") for k in ("quote", "alternative") if isinstance(c.facts.get(k), dict)}
    for tc in new_log:
        a, r, name = tc.get("args") or {}, tc.get("result"), tc.get("name")
        if not isinstance(r, dict) or r.get("error"):
            continue
        if name in ("pricing.get_quote", "inventory.check"):
            if a.get("sku") in answer_skus:
                ev.append({"kind": f"tool:{name}", "ref": a["sku"]})
        elif name == "pricing.quote_order":
            if c.facts.get("cart") is not facts_before.get("cart") or c.facts.get("cod_total_vnd") is not None:
                ev.append({"kind": "tool:pricing.quote_order", "ref": ",".join(str(x.get("sku")) for x in a.get("lines") or [])})
        elif name == "order.status":
            ev.append({"kind": "tool:order.status", "ref": "customer_orders"})
    if t.reuse_quotes:                       # view dùng lại: bằng chứng là lần đọc tool ĐÃ có trong chính lượt này, cùng SKU
        have = {(e["kind"], e["ref"]) for e in ev}
        for sku in answer_skus:
            if sku in t.quotes and ("tool:pricing.get_quote", sku) not in have:
                ev.append({"kind": "tool:pricing.get_quote", "ref": sku, "reused_this_turn": True})
            if sku in t.stock and ("tool:inventory.check", sku) not in have:
                ev.append({"kind": "tool:inventory.check", "ref": sku, "reused_this_turn": True})
    if topic == "refund_amount" and isinstance(c.facts.get("refund"), dict):
        basis = c.facts["refund"].get("basis")
        ev.append({"kind": "tool:order.update" if basis in ("return_request", "exchange_difference") else "tool:order.status",
                   "ref": c.facts["refund"].get("order_id")})
    if topic == "refund_amount" and "order_updated" in new_goals and isinstance(c.facts.get("update"), dict):
        ev.append({"kind": "tool:order.update", "ref": c.facts["update"].get("order_id")})
    if "policy_answer" in new_goals and c.facts.get("policy") and c.facts.get("policy") is not facts_before.get("policy"):
        ev += [{"kind": "policy", "ref": h.get("chunk_id")} for h in c.facts["policy"]]
    if "exchange_window_info" in new_goals and c.facts.get("exchange_window"):
        ev.append({"kind": "window", "ref": c.facts["exchange_window"].get("order_id")})
    if isinstance(c.facts.get("product_warranty"), dict) and c.facts.get("product_warranty") is not facts_before.get("product_warranty"):
        ev.append({"kind": "catalog", "ref": f"{c.facts['product_warranty'].get('product')}.warranty_months"})
    if isinstance(c.facts.get("attribute_answer"), dict) and c.facts.get("attribute_answer") is not facts_before.get("attribute_answer"):
        aa = c.facts["attribute_answer"]
        ev += [{"kind": "catalog", "ref": f"{aa['sku']}.{x['key']}"} for x in aa.get("items") or []]
    ev += [{"kind": "vetted_block", "ref": g} for g in new_goals if g in ("cod_ok", "cod_limit")]
    return ev


def _attr_terms(c):
    """Thuật ngữ thuộc tính trong câu: (khóa catalog có trong bảng tĩnh, thuật ngữ cụ thể KHÔNG có khóa — chứng nhận / xuất xứ)."""
    import re
    f = c.f or ""
    keys = [k for k, terms in ATTR_TERM_KEYS.items() if any(re.search(rf"\b{re.escape(x)}\b", f) for x in terms)]
    unkeyed = [m.group(0) for m in T._A().ATTR_ASK_RX.finditer(f)]
    return keys, unkeyed


def _answer_attribute(t):
    """S3 (13/11): trả lời thuộc tính bằng payload catalog đúng SKU / khóa / giá trị — adapter B2, KHÔNG sửa h_attr_check chung,
    không đọc giá chỉ để mượn renderer. Sản phẩm: một sản phẩm cha duy nhất trong câu, hoặc mẫu đang bàn khi câu không nhắc mẫu
    nào; nhiều mẫu → hỏi mẫu nào (không lấy phần tử cuối). Thuật ngữ có khóa và catalog có giá trị → facts.attribute_answer (renderer
    đọc nguyên văn câu mẫu ATTR_PHRASE). Thuật ngữ cụ thể không có khóa / không có giá trị → khối no_info (thiếu nguồn). Không nhận
    ra thuộc tính nào → không làm gì (noop, ask còn nghĩa vụ)."""
    A, s, c = T._A(), t.s, t.c
    from harness.renderer import ATTR_PHRASE
    keys, unkeyed = _attr_terms(c)
    pars = list(dict.fromkeys(A.mt._parent(x)[0]["sku"] for x in c.mentioned or [] if A.mt._parent(x)[0]))
    if len(pars) > 1:
        c.goals += [g for g in ["ask_product"] if g not in c.goals]
        return {"reason": "ambiguous_product"}
    par_sku = pars[0] if pars else (A.mt._parent(s.focus)[0] or {}).get("sku") if s.focus else None
    if not par_sku:
        c.goals += [g for g in ["ask_product"] if g not in c.goals]
        return {"reason": "no_product"}
    par = A.mt._parent(par_sku)[0]
    attrs = (par or {}).get("attributes") or {}
    if not keys and not unkeyed:
        # patch cuối 13/11: không nhận ra thuộc tính nào → HỎI ĐÚNG NỘI DUNG (thông tin gì về mẫu này), gợi ý thông tin catalog có;
        # không đọc giá, không đoán thuộc tính, không để ask treo gây lặp
        opts = [ATTR_LABELS[k] for k in ATTR_LABELS if k in attrs and ATTR_PHRASE.get(k) and ATTR_PHRASE[k](attrs[k])]
        c.facts["attribute_ask"] = {"product": par["name"], "options": opts[:4]}
        c.goals += [g for g in ["ask_which_attribute"] if g not in c.goals]
        return {"reason": "no_attribute_term", "product": par_sku}
    items, missing = [], list(unkeyed)
    for k in keys:
        fn = ATTR_PHRASE.get(k)
        if k in attrs and fn and fn(attrs[k]):
            items.append({"key": k, "value": attrs[k]})
        else:
            missing.append(k)
    if items:
        c.facts["attribute_answer"] = {"sku": par_sku, "product": par["name"], "items": items, "source": "catalog"}
    if missing:
        c.facts["unknown_topic"] = missing[0]
        if "no_info" not in c.goals:
            c.goals.append("no_info")
        s._why("attr_unknown", f"{par_sku}: {missing[0]}")
    return {"reason": ("partial_missing:" + ",".join(missing)) if items and missing else None, "product": par_sku}


def customer_product(t):
    """Mẫu CỦA CHÍNH KHÁCH để giữ đúng chủ đề (A1/A2 15/11, không đoán ý): sản phẩm cha parser catalog thấy trong câu (c.mentioned)
    — đúng một → mẫu đó, nhiều → mơ hồ; không nhắc mẫu nào → mẫu đang bàn (s.focus: lời khách trong cuộc / memory của khách).
    → (sản phẩm cha dict | None, "one" | "ambiguous" | "none")."""
    A, s, c = T._A(), t.s, t.c
    pars = list(dict.fromkeys(A.mt._parent(x)[0]["sku"] for x in c.mentioned or [] if A.mt._parent(x)[0]))
    if len(pars) > 1:
        return None, "ambiguous"
    par_sku = pars[0] if pars else (_parent(s.focus) if s.focus else None)
    par = A.mt._parent(par_sku)[0] if par_sku else None
    return (par, "one") if par else (None, "none")


def ask_which_attribute(c, par):
    """Câu hỏi lại ĐÚNG nội dung về một mẫu (goal ask_which_attribute), gợi ý thông tin catalog có của mẫu. Không gọi tool."""
    from harness.renderer import ATTR_PHRASE
    attrs = (par or {}).get("attributes") or {}
    opts = [ATTR_LABELS[k] for k in ATTR_LABELS if k in attrs and ATTR_PHRASE.get(k) and ATTR_PHRASE[k](attrs[k])]
    c.facts["attribute_ask"] = {"product": par["name"], "options": opts[:4]}
    c.goals += [g for g in ["ask_which_attribute"] if g not in c.goals]


def _evaluate_named(t):
    """Sửa sau DI24 (18/11, chỉ khi B2_TWO_TIER + phạm vi consult_named): câu "tư vấn / có hợp không" về ĐÚNG mẫu khách nêu → đọc giá +
    kho từng mẫu theo ref (cùng bước read_quote, kể cả điều kiện phát giá theo biến thể nếu có), một mẫu + khách nêu ngân sách → so ngân
    sách (không đề xuất mẫu thay thế). Không khảo sát nhóm, không gợi ý mẫu khác."""
    c, s = t.c, t.s
    sc = t.consult_scope or {}
    done = []
    for ref in sc.get("refs") or []:
        obs = _read_quote(t, None, ref)
        done.append({"ref": ref, "status": obs.get("status"), "withheld": bool((obs.get("result") or {}).get("price_withheld"))})
    b = (c.slots or {}).get("budget_vnd") or (sc.get("constraints") or {}).get("budget_max_vnd")
    q = c.facts.get("quote") if isinstance(c.facts.get("quote"), dict) else None
    if b and len(sc.get("refs") or []) == 1 and q and q.get("final_price_vnd"):
        c.facts["budget_fit"] = {"budget_vnd": b, "final_price_vnd": q["final_price_vnd"], "within_budget": q["final_price_vnd"] <= b,
                                 "product": q.get("name"), "no_alternative_offered": True}
        if "budget_fit" not in c.goals:
            c.goals.append("budget_fit")
    return {"reason": "named_scope_evaluate", "refs": done}


def _recommend_customer_product(t):
    """A1 (15/11, duyệt): bước gợi ý (h_recommend) KHÔNG cho nội dung nào (không xác định danh mục, hoặc gợi ý trùng mẫu đang bàn)
    mà khách có mẫu của chính mình → đọc giá + kho ĐÚNG mẫu đó (tool) và hỏi khách muốn biết thông tin gì về mẫu đó. Không gợi ý
    mẫu khác, không đoán ý. Kết quả ask là needs_customer (báo giá tự động KHÔNG phải đã trả lời câu tư vấn). Nhiều mẫu trong câu →
    hỏi mẫu nào. Không có mẫu nào → None (giữ hành vi cũ của h_recommend)."""
    s, c = t.s, t.c
    par, kind = customer_product(t)
    if kind == "ambiguous":
        c.goals += [g for g in ["ask_product"] if g not in c.goals]
        return {"reason": "recommend_none:ambiguous_product", "a1": True}
    if par is None:
        return None
    sku = _variant(t, par["sku"])
    q = s._quote(sku, "advised")
    if isinstance(q, dict) and q.get("final_price_vnd") is not None:
        t.quotes[sku] = q
        t.stock[sku] = {"in_stock": q.get("in_stock"), "qty": q.get("stock_qty"), "restock_expected": q.get("restock_expected")}
        if "quote" not in c.facts:
            c.facts["quote"] = q
            g = "out_of_stock" if q.get("in_stock") is False else "quote"
            if g == "out_of_stock":
                c.facts["restock_expected"] = q.get("restock_expected")
            c.goals += [x for x in [g] if x not in c.goals]
    ask_which_attribute(c, par)
    return {"reason": "recommend_none:customer_product", "product": par["sku"], "a1": True}


CATEGORY_LABEL = {"gia-dung/may-loc-khong-khi": "máy lọc không khí", "gia-dung/may-loc-nuoc": "máy lọc nước",
                  "gia-dung/noi-chien": "nồi chiên", "gia-dung/quat": "quạt", "thoi-trang/giay": "giày", "thoi-trang/ao": "áo khoác",
                  "me-be": "đồ mẹ và bé"}          # nhãn đọc cho khách của nhóm trong CATEGORY_WORDS (danh mục catalog, không phải từ khóa ca)


def _cat_of(sku):
    p = T._A().mt._parent(sku)[0] if sku else None
    return (p or {}).get("category") or ""


def _in_cat(sku, cat):
    c = _cat_of(sku)
    return bool(c) and (c == cat or c.startswith(cat + "/") or c.startswith(cat))


def _named_categories(t):
    """Nhóm hàng câu khách NÊU ĐÍCH DANH (CATEGORY_WORDS của catalog), theo thứ tự xuất hiện, không trùng."""
    import re
    A = T._A()
    f = A.fold(t.c.text)
    hits = []
    for w, cat in A.CATEGORY_WORDS:
        m = re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", f)
        if m and cat not in [c for _, c in hits]:
            hits.append((m.start(), cat))
    return [c for _, c in sorted(hits)]


def _category_switch(t):
    """V52-B (16/11): câu hỏi tư vấn nêu NHÓM HÀNG mà không nêu mẫu cụ thể, và mẫu đang bàn KHÔNG thuộc nhóm đó → đối tượng câu hỏi là
    nhóm được nêu, không phải mẫu đang bàn. Chỉ B2. → [nhóm] | None (không áp → luồng cũ)."""
    from core.config import settings
    c, s = t.c, t.s
    if settings.planner_variant != "b2_jev" or c.mentioned or c.alt:
        return None
    cats = _named_categories(t)
    if not cats or (len(cats) == 1 and s.focus and _in_cat(s.focus, cats[0])):
        return None                                     # không nêu nhóm / nêu đúng nhóm của mẫu đang bàn → luồng cũ
    return cats                                         # nhóm khác, hoặc NHIỀU nhóm (kể cả có nhóm của mẫu đang bàn) → hỏi rõ


def _discussed_in(s, cat):
    return next((d for d in reversed(s.discussed or []) if _in_cat(d, cat)), None)


def ask_object(t):
    """V52 (16/11): ĐỐI TƯỢNG của câu hỏi tư vấn ở lượt này + CĂN CỨ, từ dữ liệu hiện có (mẫu khách nêu, nhóm hàng khách nêu, mẫu đã
    bàn, mẫu đang bàn). CÙNG hàm cho state gửi Jev, mô tả bước answer_ask và executor (_answer_ask → _answer_category), để Jev thấy đúng
    đối tượng mà bước trả lời sẽ dùng. Chỉ đọc. Không đổi giỏ / đơn / yêu cầu."""
    from harness.tools import product_name
    c, s = t.c, t.s
    if c.mentioned:
        return {"object": product_name(c.mentioned[-1]), "sku": c.mentioned[-1], "basis": "khách nêu mẫu ở lượt này", "scope": "mentioned"}
    sw = _category_switch(t)
    if sw:
        if len(sw) > 1:
            return {"object": " / ".join(CATEGORY_LABEL.get(x, x) for x in sw), "categories": sw,
                    "basis": "khách nêu nhiều nhóm hàng — bước trả lời hỏi khách xem nhóm nào trước", "scope": "categories"}
        prev = _discussed_in(s, sw[0])
        if prev:
            return {"object": product_name(prev), "sku": prev, "categories": sw, "scope": "category_return",
                    "basis": "khách nêu nhóm hàng — quay lại mẫu đã bàn trong nhóm"}
        return {"object": CATEGORY_LABEL.get(sw[0], sw[0]), "category": sw[0], "categories": sw, "scope": "category_new",
                "basis": "khách nêu nhóm hàng chưa bàn — bước trả lời gợi ý mẫu trong nhóm"}
    if s.focus:
        return {"object": product_name(s.focus), "sku": s.focus, "basis": "mẫu đang bàn (câu không nêu mẫu / nhóm khác)", "scope": "focus"}
    return {"object": None, "basis": "chưa có đối tượng — bước trả lời hỏi khách quan tâm gì", "scope": "none"}


def question_scope(t):
    """P1 (17/11): phạm vi câu hỏi tư vấn của lượt, CHỐT ở lần gọi đầu (trước bước nào chạy) và giữ nguyên cả lượt — bước gợi ý có thể
    đổi s.focus giữa vòng Jev, phạm vi không được đổi theo. None khi lượt không có câu hỏi còn nghĩa vụ phản hồi."""
    if not hasattr(t, "_qscope"):
        t._qscope = ask_object(t) if t.pending_asks() else None
    return t._qscope


def outside_question_scope(t, skus):
    """P1: True khi MỌI SKU của ứng viên nằm ngoài nhóm hàng khách vừa nêu (phạm vi theo nhóm hàng), và ứng viên KHÔNG là đích của
    yêu cầu đặt hàng còn hiệu lực (bằng chứng cho yêu cầu giao dịch vẫn được đọc). Phạm vi theo mẫu nêu tên đã có lọc F2; phạm vi
    mẫu đang bàn / chưa có đối tượng → không lọc."""
    qs = question_scope(t)
    if not qs or qs.get("scope") not in ("categories", "category_new", "category_return"):
        return False
    par = {_parent(x) for x in skus}
    if par & t.order_target_parents():
        return False
    if qs["scope"] == "category_return":
        return _parent(qs["sku"]) not in par
    return not any(_in_cat(x, cat) for x in par for cat in qs["categories"])


def _answer_category(t, cats):
    """V52-B: trả lời theo nhóm hàng được nêu. Một nhóm: mẫu ĐÃ bàn trong nhóm (gần nhất) → báo giá / kho đúng mẫu đó; chưa bàn → gợi ý
    trong nhóm (h_recommend, giá / kho từ tool). Nhiều nhóm → hỏi khách muốn xem nhóm nào trước. Đổi mẫu ĐANG TƯ VẤN (focus) nhưng không
    đụng giỏ / đơn / yêu cầu chờ; mẫu cũ vẫn trong danh sách đã bàn để khách quay lại. Không ghi."""
    c, s = t.c, t.s
    if len(cats) > 1:
        c.facts["which_products"] = [CATEGORY_LABEL.get(x, x) for x in cats]
        if "ask_which_product" not in c.goals:
            c.goals.append("ask_which_product")
        return {"reason": "multi_category"}
    cat = cats[0]
    prev = _discussed_in(s, cat)
    if prev:
        s.focus, s.focus_by = prev, "category_return"
        q = s._quote(s._resolve_variant(prev, c.text), "advised")
        t.quotes[q["sku"]] = q
        c.facts["quote"] = q
        c.goals.append("out_of_stock" if q.get("in_stock") is False else "quote")
        if q.get("in_stock") is False:
            c.facts["restock_expected"] = q.get("restock_expected")
        return {"reason": "category_return"}
    old = s.focus
    s.focus, s.category = None, cat                     # gợi ý trong nhóm được nêu (focus cũ vẫn ở danh sách đã bàn)
    T.h_recommend(c, None)
    if s.focus is None:
        s.focus = old                                   # không gợi ý được (vd chưa có nhu cầu) → giữ mẫu đang bàn, không đổi
    alt = c.facts.get("alternative")
    if isinstance(alt, dict) and not _in_cat(alt.get("sku"), cat):
        c.facts.pop("alternative", None)                # không so mẫu khác nhóm
    if c.facts.get("quote") and not _in_cat((c.facts["quote"] or {}).get("sku"), cat):
        c.facts.pop("quote", None)
    return {"reason": "category_recommend"}


def _budget_turn(t):
    """V52 (16/11): lượt khách NÊU ngân sách (slot budget_vnd của chính lượt này) khi đang bàn một mẫu, giỏ trống, và lượt KHÔNG có
    yêu cầu nào (đặt hàng / giỏ / thao tác đơn — luồng đó giữ nguyên). Chỉ B2. Chỉ đọc."""
    from core.config import settings
    c, s = t.c, t.s
    b = (c.slots or {}).get("budget_vnd")
    if settings.planner_variant != "b2_jev" or not isinstance(b, int) or isinstance(b, bool) or b <= 0 or not s.focus or s.cart:
        return False
    return not ((c.u or {}).get("requests") or [])


def _budget_alternative(t, focus, budget, max_checks=4):
    """Mẫu cùng loại (khác mẫu đang bàn), còn hàng, giá thật từ tool: ưu tiên mẫu giá niêm yết cao nhất KHÔNG vượt ngân sách; không có
    thì mẫu rẻ nhất (gần ngân sách nhất). Bỏ phụ kiện < 400k và mẫu ngừng bán. → quote của mẫu đó | None."""
    s = t.s
    A = T._A()
    par = A.mt._parent(focus)[0] or {}
    cat = par.get("category")
    if not cat:
        return None
    items = (s.tools.call("catalog.search", category=cat).get("items") or [])
    cands = [it for it in items if it.get("sku") != par.get("sku") and (it.get("list_price_vnd") or 0) >= 400000]
    under = sorted([it for it in cands if it["list_price_vnd"] <= budget], key=lambda it: -it["list_price_vnd"])
    over = sorted([it for it in cands if it["list_price_vnd"] > budget], key=lambda it: it["list_price_vnd"])
    for it in (under + over)[:max_checks]:
        inv = s.tools.call("inventory.check", sku=it["sku"])
        if inv.get("in_stock") and not inv.get("discontinued"):
            q = s._quote(it["sku"], "alternative")
            if q.get("final_price_vnd"):
                t.quotes[it["sku"]] = q
                t.stock[it["sku"]] = inv
                return q
    return None


def _answer_budget(t):
    """V52: so giá mẫu đang bàn với ngân sách khách vừa nêu (giá từ pricing.get_quote, không suy). Vượt → mẫu thay thế cùng loại còn
    hàng (nêu rõ còn vượt bao nhiêu nếu vẫn vượt) hoặc báo chưa có mẫu phù hợp. Không đổi mẫu đang bàn, không ghi."""
    c, s = t.c, t.s
    b = c.slots["budget_vnd"]
    focus = s._resolve_variant(s.focus, c.text)
    q = t.quotes.get(focus) or s._quote(focus, "advised")
    if not q.get("final_price_vnd"):
        return {"reason": "no_quote"}
    t.quotes[focus] = q
    c.facts["quote"] = q
    fit = {"budget_vnd": b, "final_price_vnd": q["final_price_vnd"], "within_budget": q["final_price_vnd"] <= b,
           "product": q.get("name")}
    if not fit["within_budget"]:
        alt = _budget_alternative(t, focus, b)
        if alt:
            c.facts["alternative"] = alt
            fit["alternative"] = {"name": alt.get("name"), "sku": alt.get("sku"), "final_price_vnd": alt["final_price_vnd"],
                                  "within_budget": alt["final_price_vnd"] <= b,
                                  "over_by_vnd": max(0, alt["final_price_vnd"] - b)}
        else:
            fit["no_alternative"] = True
    c.facts["budget_fit"] = fit
    if "budget_fit" not in c.goals:
        c.goals.append("budget_fit")
    return {"reason": "budget_fit"}


def _answer_ask(t, req_ref, ref):
    """Trả lời một ask đã nhận diện bằng handler có nguồn của bảng (cùng code với dòng trả lời B1), rồi PHÂN LOẠI kết quả theo
    hợp đồng ask_outcome (13/11). Chỉ `answered` khi có bằng chứng đúng loại của chủ đề; noop không bao giờ thành answered."""
    topic = (ref or "")[4:] if str(ref or "").startswith("ask:") else None
    if topic not in t.asks():
        return {"status": "blocked", "missing": ["ask_not_detected"]}
    c, s, n = t.c, t.s, len(t.c.goals)
    if topic == "other":
        return _answer_other(t)
    if settings.b2_two_tier and topic in PRICE_ASKS:
        wh = _variant_withhold(t)
        if wh:
            # bước 2: không chạy handler báo giá (h_quote phát giá mẫu gốc / câu phụ thu) khi biến thể còn thiếu; planner chọn
            # clarify_field (hỏi đúng trường) hoặc báo phần thiếu
            t.withheld = {**(getattr(t, "withheld", None) or {}), wh["target"]: wh}
            t.ask_outcome[topic] = {"outcome": "blocked", "reason": "price_depends_on_variant", "evidence": []}
            return {"status": "blocked", "missing": [f"variant_field:{f}" for f in wh.get("fields") or []] or ["variant_unavailable"],
                    "result": {"price_withheld": True, "product": wh["name"], "options": wh.get("options")}}
    n_log = len(s.tools.log)
    facts_before = dict(c.facts)
    extra = {}
    named_eval = settings.b2_two_tier and topic == "recommend" and bool(getattr(t, "consult_scope", None))
    sw = None if named_eval else (_category_switch(t) if (topic in _QUOTE_TOPICS or topic == "recommend") else None)
    try:
        for h in (() if (sw or named_eval) else ASK_HANDLERS[topic]):
            if h == "attr_check":
                extra = _answer_attribute(t)            # adapter B2 (thay h_attr_check cho B2; B1/B3 giữ dòng R15)
                continue
            if h == "budget_fit" and topic == "budget":
                extra = _answer_budget(t)               # V52: adapter B2 cho ngân sách khách vừa nêu (B1 giữ dòng R19)
                continue
            if h == "policy_peek" and topic == "attribute":
                continue                                # thuộc tính chỉ trả từ catalog đúng SKU / khóa (không đọc tài liệu chung)
            if h == "gift_status" and not c.facts.get("quote"):
                continue
            if h == "warranty_fact" and not (c.mentioned or c.s.focus):
                continue
            if h == "cart_total" and not c.s.cart:
                continue
            if h == "refund_amount" and not T.PREDS_TARGET["has_return_info"](c):
                continue
            if h == "quote" and not (c.s.focus or c.mentioned or c.alt):
                T.h_recommend(c, None)
                continue
            T.HANDLERS[h](c, None)
        if named_eval:
            extra = _evaluate_named(t)                       # sửa sau DI24: phạm vi consult_named — đánh giá đúng mẫu khách nêu
        elif sw:
            extra = _answer_category(t, sw)                  # V52-B: đối tượng = nhóm hàng khách nêu, không phải mẫu đang bàn
        elif topic == "recommend" and not c.goals[n:] and not c.facts.get("attribute_answer"):
            extra = _recommend_customer_product(t) or {}     # A1 (15/11): gợi ý không ra nội dung → giữ đúng mẫu của khách
    except Exception as e:                              # lỗi handler / tool: ghi error, không answered
        t.ask_outcome[topic] = {"outcome": "error", "evidence": [], "reason": f"{type(e).__name__}: {str(e)[:120]}"}
        return {"status": "error", "error": f"{type(e).__name__}: {str(e)[:120]}", "goals": c.goals[n:],
                "result": {"topic": topic}, "ask_outcome": t.ask_outcome[topic]}
    goals = c.goals[n:]
    if topic in ASKED_IN_QUOTE and "quote" in c.goals and isinstance(c.facts.get("quote"), dict):
        # F1 (13/11): khối báo giá phải nói đúng điều khách hỏi (còn hàng / tình trạng KM) — không chỉ nhắc lại giá
        q = c.facts["quote"]
        q["ask_topics"] = sorted(set(q.get("ask_topics") or []) | {topic})
    new_log = s.tools.log[n_log:]
    _record_tool_evidence(t, new_log, facts_before)
    if "cart_total" in goals and s.cart:                # 13/11 vòng giỏ: giỏ đã được báo qua câu trả lời tổng giỏ
        t.cart_reported_for = tuple(s.cart)
        if not t.cart_already():
            t.cart_reported = True
    ev = _evidence_of(t, topic, new_log, goals, facts_before)
    kinds = {e["kind"] for e in ev}
    need = TOPIC_EVIDENCE.get(topic, frozenset())
    if kinds & need and (goals or "catalog" in kinds):
        outcome = "answered"
    elif "no_info" in goals:
        outcome = "responded_no_source"
    elif any(_question_goal(g) for g in goals):
        outcome = "needs_customer"
    else:
        outcome = "noop"
    reason = extra.get("reason") if outcome in ("answered", "noop", "responded_no_source", "needs_customer") else None
    if extra.get("a1") and outcome == "answered":
        outcome = "needs_customer"          # A1: báo giá tự động đúng mẫu + câu hỏi lại — chưa trả lời câu tư vấn
    if outcome == "noop" and goals and not reason:
        reason = "goals_without_topic_evidence:" + ",".join(goals)
    t.ask_outcome[topic] = {"outcome": outcome, "evidence": ev, "reason": reason}
    if outcome == "answered" and topic not in t.answered:
        t.answered.append(topic)
    status = "ok" if outcome in RESPONDED else "noop"
    return {"status": status, "goals": goals, "result": {"topic": topic, "outcome": outcome}, "ask_outcome": t.ask_outcome[topic]}


def _answer_other(t):
    """Patch cuối 13/11: ask `other` KHÔNG tự ánh xạ sang tra chính sách. Thứ tự:
    1. planner đã CHỦ ĐỘNG đọc tài liệu trong lượt (read_policy có đoạn, goal policy_answer) → answered, evidence policy;
    2. khối chung cố định của lượt (is_bot / refuse_internal, tạo trước vòng) → responded_common (không phải trả lời dữ kiện);
    3. còn lại → khối no_info (responded_no_source), không đọc tài liệu chung để đoán.
    Hạn chế đã ghi: câu kép mà bộ hiểu gộp cả hai ý vào `other` thì ý thứ hai không được trả lời riêng."""
    c, s = t.c, t.s
    n = len(c.goals)
    if t.policy and "policy_answer" in c.goals:
        ev = [{"kind": "policy", "ref": h.get("chunk_id")} for h in t.policy]
        t.ask_outcome["other"] = {"outcome": "answered", "evidence": ev, "reason": "read_policy_this_turn"}
        if "other" not in t.answered:
            t.answered.append("other")
    else:
        common = [g for g in t.common["goals"] if g in COMMON_RESPONSE_GOALS]
        if common:
            t.ask_outcome["other"] = {"outcome": "responded_common", "evidence": [{"kind": "vetted_block", "ref": g} for g in common],
                                      "reason": "common:" + ",".join(t.common["rows"])}
        else:
            c.facts.setdefault("unknown_topic", "other")
            if "no_info" not in c.goals:
                c.goals.append("no_info")
            s._why("other_no_source", "ask other: không có khối chung / tài liệu đã đọc → chưa có thông tin")
            t.ask_outcome["other"] = {"outcome": "responded_no_source", "evidence": [], "reason": "no_common_no_policy_read"}
    o = t.ask_outcome["other"]
    return {"status": "ok", "goals": c.goals[n:], "result": {"topic": "other", "outcome": o["outcome"]}, "ask_outcome": o}


def _report_cart(t, req_ref, ref):
    """Báo khách giỏ hiện có (từng món + tổng theo pricing.quote_order) — CHỈ ĐỌC: không thêm / bớt món, không tạo đơn. Giỏ đã
    được cập nhật ở bước chuẩn bị (_prepare_target) theo yêu cầu add_to_cart / place_order; số lượng không có trong hợp đồng giỏ."""
    c, s = t.c, t.s
    if not s.cart:
        return {"status": "blocked", "missing": ["cart_empty"]}
    n, n_log, facts_before = len(c.goals), len(s.tools.log), dict(c.facts)
    already = t.cart_already()
    if already:                               # patch cuối 13/11: thêm mẫu đã có → báo đã có trong giỏ, không suy số lượng
        from harness.tools import product_name
        c.facts["cart_already"] = {"products": [product_name(x) for x in already]}
        c.goals += [g for g in ["cart_item_already"] if g not in c.goals]
    T.h_cart_total(c, None)
    goals = c.goals[n:]
    if "cart_total" in goals or "cart_item_already" in goals:
        t.cart_reported = True
        t.cart_reported_for = tuple(s.cart)
    new_log = s.tools.log[n_log:]
    _record_tool_evidence(t, new_log, facts_before)
    if "cart_total" in t.asks():
        ev = _evidence_of(t, "cart_total", new_log, goals, facts_before)
        ok_ = any(e["kind"] == "tool:pricing.quote_order" for e in ev)
        t.ask_outcome["cart_total"] = {"outcome": "answered" if ok_ else "noop", "evidence": ev, "reason": None if ok_ else "no_quote_order"}
        if ok_ and "cart_total" not in t.answered:
            t.answered.append("cart_total")
    items = [(x.get("name"), x.get("final_price_vnd")) for x in (c.facts.get("cart") or {}).get("items") or []]
    return {"status": "ok" if goals else "noop", "goals": goals,
            "result": {"items": [x[0] for x in items], "total_vnd": (c.facts.get("cart") or {}).get("total_vnd"),
                       "skus": [x.get("sku") for x in (c.facts.get("cart") or {}).get("items") or []]}}


# ---------------------------------------------------------------------- hành động ghi

def _commit_request(t, req_ref, ref):
    c, s = t.c, t.s
    if req_ref == "X_CANCEL":
        if "X_CANCEL" not in t.extra_requests():
            return {"status": "blocked", "missing": ["cancel_request_with_order"]}
        T.h_cancel_request(c, None)
        return {"status": "ok", "goals": ["cancel_handoff"], "terminal": True}
    if req_ref == "X_COMPLETE_ADDRESS":
        if "X_COMPLETE_ADDRESS" not in t.extra_requests():
            return {"status": "blocked", "missing": ["created_order_missing_address"]}
        n = len(c.goals)
        from core.config import settings
        g_new = _complete_address(t) if settings.planner_variant == "b2_jev" else s._update_address(c.slots["address"], c.facts)
        c.goals += [g for g in g_new or [] if g not in c.goals]
        return {"status": "ok" if "address_updated" in c.goals[n:] else "blocked", "goals": c.goals[n:],
                "result": {"via": "address_completion"}}
    r = t.request(req_ref)
    if r is None or r["status"] not in ACTIVE:
        return {"status": "blocked", "missing": ["active_request"]}
    if s.reqs.hold:
        return {"status": "blocked", "missing": [s.reqs.hold], "clarify": ["ask_repeat"]}
    kind = r["kind"]
    if kind == "place_order":
        return _commit_place_order(t, r, ref)
    if kind in ORDER_OP_KINDS:
        return _commit_order_op(t, r, ref)
    n = len(c.goals)
    if kind == "callback":
        w = c.slots.get("callback_requested")
        if not w:
            pw = T._A().extractor.parse_relative_datetime(c.text, s.today)
            w = f"{pw[0]}T{pw[1] or '09:00'}" if pw else None
        if not w:
            return {"status": "blocked", "missing": ["callback_time"], "clarify": ["defer_ack"]}
        g = s._plan_callback(w, c.facts)
    else:
        return {"status": "blocked", "missing": ["unsupported_kind"]}
    c.goals += [x for x in g if x not in c.goals]
    st = r["status"]
    return {"status": "ok" if st in ("done", "partial") else "blocked" if st in ACTIVE else st,
            "goals": c.goals[n:], "result": {"request": r["id"], "request_status": st}}


def _order_for(t, r, ref):
    """Đơn đích của yêu cầu thao tác đơn, CHỈ từ bằng chứng order.status đã đọc trong lượt: target của yêu cầu (O#) / ref Jev
    chọn → phải có trong danh sách đơn của khách; không có target → chỉ khi khách có đúng một đơn. → (đơn | None, unique, lý do)."""
    if t.orders is None:
        return None, False, "read_order"
    if not t.orders:
        return None, False, "no_order"
    from core.config import settings
    if settings.planner_variant == "b2_jev" and r["kind"] in ORDER_OP_KINDS:
        return _order_for_v45(t, r)
    oid = (r.get("target") or {}).get("order_id")
    if oid is None and ref:
        tg = t.order_ref(ref)
        oid = tg["order_id"] if tg else None
    if oid is not None:
        o = t.order_of(oid)
        # E1 v3: Jev chọn đúng đơn DUY NHẤT của khách bằng mã đơn → coi như đơn duy nhất (trước đây unique=False làm authorize
        # báo target_unresolved). Khách có nhiều đơn mà yêu cầu không có target → vẫn không cấp (Jev không đoán thay khách);
        # authorize / điều kiện / hạn đổi trả vẫn kiểm đầy đủ ở _commit_order_op.
        unique = bool(o) and (r.get("target") or {}).get("order_id") is None and len(t.orders) == 1
        return (o, unique, None) if o else (None, False, "order_target")
    if r["status"] != "needs_target" and len(t.orders) == 1:
        return t.orders[0], True, None
    return None, False, "order_target"


def _order_for_v45(t, r):
    """V45 (MP1, duyệt 15/11): đơn đích CHỈ từ căn cứ của khách đã ghi trên yêu cầu (request_state: mã đơn / sản phẩm / size–màu /
    focus / đồng ý đề nghị cho đơn cụ thể), đối chiếu danh sách order.status ĐÃ ĐỌC trong lượt. ref Jev và target_ref của bộ hiểu
    KHÔNG được dùng. Không có căn cứ → chỉ khi khách có đúng MỘT đơn (và câu không nêu đơn mơ hồ). Mã đơn lạ → chặn hẳn."""
    if r.get("target_block"):
        return None, False, r["target_block"]
    tgt = r.get("target") or {}
    if tgt.get("type") == "order" and r.get("target_basis"):
        o = t.order_of(tgt["order_id"])
        return (o, False, None) if o else (None, False, "order_target")
    if not tgt and not r.get("target_ambiguous") and r["status"] != "needs_target" and len(t.orders) == 1:
        return t.orders[0], True, None
    return None, False, "order_target"


def _exchange_variant(t, o):
    """Biến thể mới cho yêu cầu đổi của đơn o (logic B1, dữ liệu đã kiểm): mẫu khác parser catalog thấy trong câu → đổi mẫu;
    size bộ hiểu trả (hoặc size khách nói ở lượt trước của cùng yêu cầu) → đổi size cùng màu. → (sku | None, action, thiếu)."""
    A, s, c = T._A(), t.s, t.c
    parent, ov = A.mt._parent(o["sku"])
    other = [x for x in A.find_products(c.text) if x != parent["sku"]]
    if other:
        return A.find_variant(other[0], c.text, None, None) or other[0], "exchange_product", None
    size = ((s.u_turn or {}).get("slots") or {}).get("size") or s.pending_size
    if not size:
        return None, None, "new_size"
    size = str(size).upper()
    if not ov or size == str(ov["size"]).upper():
        return None, None, "new_size"
    new_sku = next((v["variant_sku"] for v in parent["variants"] if str(v["size"]).upper() == size and v["color"] == ov["color"]), None)
    return (new_sku, "exchange_size", None) if new_sku else (None, None, "variant")


# ---------------------------------------------------------------------- kiểm điều kiện ghi (KHÔNG tác dụng phụ) — v5

def _order_op_check(t, r, ref):
    """Mọi kiểm trước ghi của đổi địa chỉ / đổi / trả, KHÔNG ghi, KHÔNG authorize, KHÔNG đổi state yêu cầu.
    → (observation bị chặn | None, ctx). ctx["mode"]: write | no_change | already. Dùng chung cho commit (rồi mới authorize + ghi),
    cho `readiness` (dữ kiện gửi planner) và cho `clarify` (hỏi đúng phần thiếu)."""
    from harness.tools import product_name
    s, c = t.s, t.c
    kind = r["kind"]
    if getattr(s, "proxy_caller", False):
        return {"status": "blocked", "missing": ["identity"], "clarify": ["refuse_other_customer"]}, {}
    if kind in ("exchange", "return"):
        other = "return" if kind == "exchange" else "exchange"
        if s.reqs.has_active(other) or {kind, other} <= set((c.u or {}).get("requests") or []):
            return {"status": "blocked", "missing": ["exchange_or_return"], "clarify": ["ask_exchange_or_return"]}, {}
    o, unique, why = _order_for(t, r, ref)
    if o is None:
        if why == "read_order":
            return {"status": "blocked", "missing": ["read_order"]}, {}
        if why == "no_order":
            return {"status": "blocked", "missing": ["no_order"], "clarify": ["order_not_found"]}, {}
        return {"status": "blocked", "missing": [why if why == "order_not_owned" else "order_target"], "clarify": ["ask_which_order"],
                "clarify_facts": {"which_orders": [{"order_id": x["order_id"], "product": s._order_products(x)} for x in t.orders[-5:]],
                                  "which_orders_action": OP_ACTION_VI.get(kind)}}, {}
    oid = o["order_id"]
    ctx = {"o": o, "oid": oid, "unique": unique, "tgt": {"type": "order", "order_id": oid}, "mode": "write"}
    if kind == "change_order_address":
        # V45 §8.5: địa chỉ của lượt; không có thì địa chỉ khách đã nói cho CHÍNH yêu cầu (lượt hỏi chọn đơn trước đó)
        # V48: B2 chỉ dùng địa chỉ ĐÃ GẮN với chính request (lệnh trực tiếp / trả lời câu hỏi địa chỉ đã gửi); không lấy địa chỉ
        # mức lượt hay known. B3 giữ đường cũ.
        from core.config import settings
        if settings.planner_variant == "b2_jev":
            # V51-A (16/11 — issue GEN-T10). (1) Trạng thái kết thúc theo order.status → không đổi địa chỉ (giới hạn an toàn do agent
            # chọn; mock BTC vẫn nhận). Chỉ change_order_address; đổi / trả giữ nguyên.
            if str(o.get("status") or "").lower() in TERMINAL_ORDER_STATUS:
                return {"status": "blocked", "missing": ["address_change_order_closed"], "clarify": ["address_change_unavailable"],
                        "clarify_facts": {"address_block": {"order_id": oid, "product": s._order_products(o), "why": "terminal",
                                                            "status": o.get("status")}}, "addr_block": oid}, ctx
            # (2) Đơn ngoài cuộc chỉ được chọn vì khách có đúng một đơn (không căn cứ của khách) → hỏi xác nhận đơn, không ghi.
            if unique and oid not in {x["order_id"] for x in s.orders_created}:
                return {"status": "blocked", "missing": ["order_target"], "clarify": ["ask_which_order"],
                        "clarify_facts": {"which_orders": [{"order_id": oid, "product": s._order_products(o)}],
                                          "which_orders_action": OP_ACTION_VI.get(kind)}}, ctx
        address = s.reqs.bound_address(r) if settings.planner_variant == "b2_jev" else (c.slots.get("address") or r.get("op_address"))
        mine = next((x for x in s.orders_created if x["order_id"] == oid), None)
        current = (mine or {}).get("address") or o.get("address")
        if not address:
            return {"status": "blocked", "missing": ["address"], "clarify": ["ask_address"],
                    "clarify_facts": {"address_change": {"order_id": oid}}}, ctx
        ctx.update(address=address, mine=mine, current=current)
        if current and T._A().fold(current) == T._A().fold(address):
            ctx["mode"] = "no_change"
        return None, ctx
    if len({ln.get("sku") for ln in o.get("lines") or []}) > 1:
        return {"status": "blocked", "missing": ["multi_line_order"], "clarify_fn": "handoff_multi_line"}, ctx
    if oid not in t.windows:
        return {"status": "blocked", "missing": [f"check_window:{t.oref_of(oid)}"]}, ctx
    d = t.windows[oid]
    od = o.get("created_on") or o.get("date")
    if d is not None and d.get("eligible") is False:
        return {"status": "blocked", "missing": ["window_passed"], "clarify": [] if s.window_told else ["exchange_window_passed"],
                "clarify_facts": {"old_order": {"order_id": oid, "product": s._order_products(o), "date": od}}, "window_passed": True}, ctx
    if d is not None and d.get("eligible") is None:
        return {"status": "blocked", "missing": ["window_undetermined"], "clarify": ["exchange_window_info"],
                "clarify_facts": {"exchange_window": {"order_id": oid, "created_ddmm": T._A()._ddmm(od), "days": d["days"],
                                                      "version": d["version"], "action": "trả hàng" if kind == "return" else "đổi hàng"}}}, ctx
    if kind == "return":
        ctx["key"] = (oid, "return", None)
        ctx["mode"] = "already" if ctx["key"] in s.updates_done else "write"
        return None, ctx
    new_sku, action, miss = _exchange_variant(t, o)
    if new_sku is None:
        return {"status": "blocked", "missing": [miss], "clarify": ["ask_variant" if miss == "variant" else "ask_new_size"],
                "clarify_facts": {"current_variant": product_name(o["sku"])}}, ctx
    vref = next((k for k, v in t.vrefs.items() if v["sku"] == new_sku), None)
    if vref is None:
        t.variant_refs()                       # chỉ đăng ký ref V# (ánh xạ tất định, không tool)
        vref = next((k for k, v in t.vrefs.items() if v["sku"] == new_sku), "V?")
    if new_sku not in t.stock:
        return {"status": "blocked", "missing": [f"read_stock:{vref}"]}, ctx
    if t.stock[new_sku].get("in_stock") is False:
        return {"status": "blocked", "missing": ["new_variant_out_of_stock"], "clarify": ["out_of_stock"],
                "clarify_facts": {"quote": {"sku": new_sku, "name": product_name(new_sku)},
                                  "restock_expected": t.stock[new_sku].get("restock_expected")}}, ctx
    ctx.update(new_sku=new_sku, action=action, key=(oid, action, new_sku))
    ctx["mode"] = "already" if ctx["key"] in s.updates_done else "write"
    return None, ctx


def _place_order_check(t, r, ref):
    """Mọi kiểm trước ghi của đặt hàng, KHÔNG ghi / authorize / park. → (observation bị chặn | None, ctx).
    ctx["mode"]: write | continuation (khách chỉ đọc thêm địa chỉ / thanh toán cho đơn vừa tạo cùng sản phẩm)."""
    from harness.request_state import RequestState
    from harness.tools import product_name
    s, c = t.s, t.c
    multi = [x for x in t.active_requests() if x["kind"] == "place_order"]
    if len(multi) > 1:
        return {"status": "blocked", "missing": ["which_request"], "clarify_fn": "multi_request"}, {}
    if r["status"] == "needs_target":
        return {"status": "blocked", "missing": ["target"], "clarify_fn": "ask_product_target"}, {}
    picked = False
    if r["target"] is not None:
        skus = tuple(r["target"]["skus"])
    else:
        p = t.product_ref(ref)
        sel = p["skus"] if p else RequestState.unambiguous_selection(s, r.get("inherit"))
        if not sel:
            return {"status": "blocked", "missing": ["target"], "clarify_fn": "ask_product_target"}, {}
        skus, picked = tuple(sel), True
    resolved = []
    for sku in skus:
        rv = s._target_variant(sku, c.text)
        p, v = T._A().mt._parent(rv)
        if p and p["variants"] and not v:
            return {"status": "blocked", "missing": [f"variant:{_ref_of(t, sku)}"], "clarify": ["ask_variant"],
                    "clarify_facts": {"need_variant_for": product_name(sku)}}, {}
        resolved.append(rv)
    ctx = {"resolved": resolved, "picked": picked, "mode": "write"}
    if not r.get("additional"):
        dup, rel = s._order_overlap(resolved)
        if dup is not None and rel == "same":
            u = s.u_turn or {}
            if bool(set(u.get("slots") or {}) & {"address", "payment"}) or bool((u.get("refs") or {}).get("previous_address")):
                ctx.update(mode="continuation", dup=dup)
                return None, ctx
        if dup is not None:
            return {"status": "blocked", "missing": ["confirm_additional_order"], "clarify_fn": "additional_order",
                    "dup": dup["order_id"], "rel": rel, "resolved": resolved}, ctx
    missing = []
    for rv in resolved:
        if rv not in t.quotes:
            missing.append(f"read_quote:{_ref_of(t, rv)}")
        if rv not in t.stock:
            missing.append(f"read_stock:{_ref_of(t, rv)}")
    if missing:
        return {"status": "blocked", "missing": missing}, ctx
    return None, ctx


# ---------------------------------------------------------------------- mức sẵn sàng (DỮ KIỆN dẫn xuất — duyệt 12/11)

MISSING_INFO = {"address", "new_size", "variant", "order_target", "target", "which_request", "confirm_additional_order",
                "exchange_or_return", "callback_time", "order_not_owned"}      # V45: mã đơn khách nói không thuộc khách → hỏi đơn nào
CONDITION_UNMET = {"window_undetermined", "new_variant_out_of_stock"}
FORBIDDEN = {"identity", "window_passed", "multi_line_order", "no_order",
             "address_change_order_closed"}                 # V51-A: đổi địa chỉ đơn đã kết thúc (giới hạn an toàn của agent)
TERMINAL_ORDER_STATUS = {"delivered", "cancelled", "canceled", "returned", "completed"}
EVIDENCE_PREFIX = ("read_order", "check_window:", "read_stock:", "read_quote:")


def _classify(missing):
    for m in missing:
        if m in FORBIDDEN:
            return "forbidden"
    for m in missing:
        if m in MISSING_INFO or m.startswith("variant:"):
            return "missing_info"
    for m in missing:
        if m in CONDITION_UNMET:
            return "condition_unmet"
    if any(m == "read_order" or m.startswith(EVIDENCE_PREFIX) for m in missing):
        return "missing_evidence"
    return "missing_info"


def evaluate_condition(t, r, ctx):
    """Điều kiện của chính yêu cầu (bộ hiểu trích, căn cứ trong câu) đánh giá CHỈ từ bằng chứng đã đọc trong lượt, không gọi
    tool (v6, duyệt 12/11 — điều kiện tổng quát). → None (không có điều kiện) hoặc
    {"state": met | unmet | missing_evidence | pending | executor, "detail": [...], "goals": [...], "facts": {...}}.
    - stock: kho của ĐÚNG đối tượng (mọi đơn vị còn hàng → met; có món hết → unmet; chưa đọc → missing_evidence);
    - price_max (ngưỡng max_vnd do code tách từ lời khách): tổng = giá cuối từng đơn vị đã báo × số lượng, so như executor
      (vượt ngưỡng → unmet; ≤ ngưỡng → met); đối tượng nhiều sản phẩm → executor (giá chung đơn chỉ biết qua quote_order);
      thiếu ngưỡng / chưa báo giá → missing_evidence;
    - approval / time / other / unknown → pending (code không tự đánh giá; chờ khách).
    met không cấp quyền: executor vẫn kiểm lại khi ghi (authorize, quote_order, kho theo số lượng)."""
    from harness.tools import product_name
    cond = r.get("condition") or {}
    typ = cond.get("type")
    if not typ or (r["kind"] == "callback" and typ == "time"):
        return None
    resolved = list(ctx.get("resolved") or [])
    text = cond.get("span") or None
    if typ == "stock":
        st = [t.stock.get(rv, {}).get("in_stock") for rv in resolved]
        if st and all(x is True for x in st):
            return {"state": "met", "detail": ["stock_in"], "goals": [], "facts": {}}
        if any(x is False for x in st):
            oos = next(rv for rv in resolved if t.stock.get(rv, {}).get("in_stock") is False)
            q = t.quotes.get(oos) or {"sku": oos, "name": product_name(oos)}
            return {"state": "unmet", "detail": ["stock_condition_not_met"], "goals": ["out_of_stock", "condition_pending"],
                    "facts": {"quote": q, "restock_expected": (t.stock.get(oos) or {}).get("restock_expected") or q.get("restock_expected"),
                              "condition": {"type": "stock", "text": text}}}
        return {"state": "missing_evidence", "detail": ["stock_for_condition"], "goals": [], "facts": {}}
    if typ == "price_max":
        mx = cond.get("max_vnd")
        if not mx:
            return {"state": "pending", "detail": ["price_max_without_amount"], "goals": ["condition_pending"],
                    "facts": {"condition": {"type": "price_max", "text": text}}}
        if r["kind"] != "place_order" or len(resolved) != 1:
            return {"state": "executor", "detail": ["price_max_bundle_checked_by_executor"], "goals": [], "facts": {}}
        q = t.quotes.get(resolved[0])
        if not q or not q.get("final_price_vnd"):
            return {"state": "missing_evidence", "detail": ["price_for_condition"], "goals": [], "facts": {}}
        s = t.s
        qty = s.qty_obs[1] if s.qty_obs and s.qty_obs[0] >= r["turn"] and 1 <= s.qty_obs[1] <= 20 else 1
        total = q["final_price_vnd"] * qty
        if total > mx:
            return {"state": "unmet", "detail": [f"total_{total}_over_{mx}"], "goals": ["condition_unmet"],
                    "facts": {"condition": {"type": "price_max", "max_vnd": mx, "total_vnd": total}}}
        return {"state": "met", "detail": [f"total_{total}_within_{mx}"], "goals": [], "facts": {}}
    return {"state": "pending", "detail": [f"condition_{typ}_pending"], "goals": ["condition_pending"],
            "facts": {"condition": {"type": typ, "text": text}}}


def _condition_ctx(t, r):
    """ctx (đối tượng đã resolve) cho đánh giá điều kiện, không tác dụng phụ."""
    if r["kind"] == "place_order":
        return _place_order_check(t, r, None)[1]
    if r["kind"] in ORDER_OP_KINDS:
        return _order_op_check(t, r, None)[1]
    return {}


def condition_reply(t, r):
    """Phản hồi điều kiện chỉ từ bằng chứng đã có (không tool, không thực hiện nghiệp vụ). → goals (đã ghi facts)."""
    ev = evaluate_condition(t, r, _condition_ctx(t, r))
    if not ev:
        return []
    c = t.c
    if ev["goals"]:
        c.facts.update(ev["facts"])
        return list(ev["goals"])
    cond = r.get("condition") or {}
    if ev["state"] in ("missing_evidence", "executor", "met"):
        # chưa đủ bằng chứng / chưa thử thực hiện: chỉ nói rõ yêu cầu còn kèm điều kiện, CHƯA lên đơn (không hứa, không ghi)
        c.facts["condition"] = {"type": cond.get("type"), "text": cond.get("span") or None}
        return ["condition_pending"]
    return []


def readiness(t, r):
    """Mức sẵn sàng của MỘT yêu cầu — DỮ KIỆN dẫn xuất từ cùng các kiểm của commit, gửi planner để biết còn thiếu gì. KHÔNG cấp
    quyền, KHÔNG tự commit: khi thực hiện, executor vẫn chạy lại toàn bộ kiểm + authorize (request ID / revision / điều kiện) trước
    ghi. state: missing_info (cần khách nói thêm) | missing_evidence (chưa đọc giá/kho/đơn/hạn) | condition_unmet (điều kiện nghiệp
    vụ chưa thỏa: hết hàng, chưa xác định hạn, điều kiện của khách) | forbidden (bị cấm: quá hạn, người khác, đơn nhiều dòng…) |
    ready_executor_rechecks (đủ dữ kiện để THỬ thực hiện)."""
    s = t.s
    if s.reqs.hold:
        return {"request": r["id"], "state": "missing_info", "detail": [s.reqs.hold]}
    ctx = {}
    if r["kind"] == "place_order":
        obs, ctx = _place_order_check(t, r, None)
    elif r["kind"] in ORDER_OP_KINDS:
        obs, ctx = _order_op_check(t, r, None)
    elif r["kind"] == "callback":
        has_time = bool(t.c.slots.get("callback_requested")) or bool(T._A().extractor.parse_relative_datetime(t.c.text, s.today))
        obs = None if has_time else {"status": "blocked", "missing": ["callback_time"]}
    else:
        obs = None
    if obs is not None:
        return {"request": r["id"], "state": _classify(obs.get("missing") or []), "detail": list(obs.get("missing") or [])}
    cond = evaluate_condition(t, r, ctx)
    if cond and cond["state"] in ("unmet", "pending"):
        return {"request": r["id"], "state": "condition_unmet", "detail": cond["detail"]}
    if cond and cond["state"] == "missing_evidence":
        return {"request": r["id"], "state": "missing_evidence", "detail": cond["detail"]}
    if r["kind"] == "place_order" and any(t.stock.get(rv, {}).get("in_stock") is False for rv in ctx.get("resolved") or []):
        return {"request": r["id"], "state": "condition_unmet", "detail": ["out_of_stock"]}
    return {"request": r["id"], "state": "ready_executor_rechecks",
            "detail": (cond["detail"] if cond else []) + [ctx.get("mode", "write")]}


# ---------------------------------------------------------------------- ghi

def _commit_order_op(t, r, ref):
    """Đổi địa chỉ / đổi / trả: kiểm (_order_op_check) → authorize theo request ID → MỘT order.update. Thiếu bằng chứng / thông
    tin / điều kiện → blocked kèm phần thiếu; không tự đọc thay planner."""
    from harness import tool_outcome
    from harness.tools import public_view
    s, c = t.s, t.c
    kind = r["kind"]
    obs, ctx = _order_op_check(t, r, ref)
    if obs is not None:
        return obs
    o, oid, tgt, unique = ctx["o"], ctx["oid"], ctx["tgt"], ctx["unique"]
    n = len(c.goals)
    if kind == "change_order_address":
        if r["target"] is None:
            r["target"] = tgt
            if unique:
                r["target_basis"] = "single_order"          # V45: executor xác nhận đơn duy nhất trên order.status của lượt
        if ctx["mode"] == "no_change":
            s.reqs.settle(r, "confirmed_success", {"order_id": oid, "no_change": True})
            c.facts["order"] = {"order_id": oid, "product": s._order_products(o), "address": ctx["current"]}
            c.goals.append("confirm_delivery_address")
            return {"status": "ok", "goals": c.goals[n:], "result": {"order_id": oid, "no_change": True}}
        req = s._req_ok("change_order_address", target=tgt, unique_target=unique, req_id=r["id"], address=ctx["address"])
        if not req:
            return {"status": "blocked", "missing": [f"authorize:{getattr(s, '_req_why', None)}"],
                    "clarify": s._blocked_goals("change_order_address", c.facts, ["confirm_old_address"], orders=t.orders)}
        address = ctx["address"]
        args = dict(order_id=oid, action="update_address", reason=f"địa chỉ mới: {address}")
        s.reqs.begin(req)
        res = s.tools.call("order.update", **args)
        st = tool_outcome.classify({"name": "order.update", "args": args, "result": res})["status"]
        s.reqs.settle(req, st, {"order_id": oid, "action": "update_address"})
        if st != "confirmed_success":
            c.goals.append("contract_error")
            return {"status": st, "goals": c.goals[n:]}
        if ctx.get("mine") is not None:
            ctx["mine"]["address"] = address
        s._addr_dispatched = True
        c.facts["address_update"] = {"orders": [oid], "address": address}
        if o.get("estimated_delivery"):
            c.facts["address_update"]["estimated_delivery_ddmm"] = T._A()._ddmm(o["estimated_delivery"])
        c.goals.append("address_updated")
        return {"status": "ok", "goals": c.goals[n:], "result": {"order_id": oid, "action": "update_address"}}
    key = ctx["key"]
    if ctx["mode"] == "already":
        c.facts["update"] = s.updates_done[key]
        c.goals.append("order_updated")
        return {"status": "ok", "goals": c.goals[n:], "result": {"order_id": oid, "already": True}}
    if kind == "return":
        req = s._req_ok("return", target=tgt, unique_target=unique, req_id=r["id"])
        args = dict(order_id=oid, action="return", reason="khach yeu cau tra hang")
    else:
        if ctx["action"] == "exchange_size":
            s.pending_size = str(((s.u_turn or {}).get("slots") or {}).get("size") or s.pending_size).upper()
        req = s._req_ok("exchange", target=tgt, unique_target=unique, revision={"new_variant": ctx["new_sku"]}, req_id=r["id"])
        args = dict(order_id=oid, action=ctx["action"], new_variant_sku=ctx["new_sku"])
    if not req:
        return {"status": "blocked", "missing": [f"authorize:{getattr(s, '_req_why', None)}"],
                "clarify": s._blocked_goals(kind, c.facts, None, orders=t.orders) or []}
    s.reqs.begin(req)
    res = s.tools.call("order.update", **args)
    st = tool_outcome.classify({"name": "order.update", "args": args, "result": res})["status"]
    s.reqs.settle(req, st, {"order_id": oid, "action": key[1]})
    if st == "unresolved":
        c.goals.append("contract_error")
        return {"status": "unresolved", "goals": c.goals[n:]}
    if (res or {}).get("error"):
        c.facts["order_error"] = res["error"]
        if res.get("restock_expected"):
            c.facts["restock_expected"] = res["restock_expected"]
        c.goals.append("out_of_stock" if "out_of_stock" in res["error"] else "order_failed")
        return {"status": "failed", "goals": c.goals[n:]}
    s.updates_done[key] = public_view(res)
    c.facts["update"] = public_view(res)
    c.goals.append("order_updated")
    return {"status": "ok", "goals": c.goals[n:], "result": {"order_id": oid, "action": key[1]}}


def _commit_place_order(t, r, ref):
    """Đặt hàng: kiểm (_place_order_check) → pricing.quote_order + authorize theo request ID + order.create trong executor B1
    (_order_target, dùng chung). Lựa chọn trùng / chứa sản phẩm của đơn đã tạo → hỏi (holdout 2); khách chỉ đọc thêm địa chỉ /
    thanh toán cho chính đơn đó → tiếp tục đơn."""
    from harness.tools import product_name
    s, c = t.s, t.c
    obs, ctx = _place_order_check(t, r, ref)
    if obs is not None:
        return obs
    resolved = ctx["resolved"]
    if ctx["mode"] == "continuation":
        dup = ctx["dup"]
        n = len(c.goals)
        from core.config import settings as _st
        if _st.planner_variant == "b2_jev":
            got = s.reqs.completion_for(s)
            if got and got[1]["order_id"] == dup["order_id"]:
                c.goals += [g for g in _complete_address(t) or [] if g not in c.goals]
            elif c.slots.get("address") and not dup.get("address"):
                c.goals += [g for g in ("ask_address",) if g not in c.goals]     # V48: địa chỉ chưa có chủ → hỏi, không ghi
        elif c.slots.get("address") and not dup.get("address"):
            c.goals += [g for g in s._update_address(c.slots["address"], c.facts) if g not in c.goals]
        s.reqs.settle(r, "confirmed_success", {"continuation_of": dup["order_id"]})
        c.goals += [g for g in s._order_exists_goals(dup, c.facts) if g not in c.goals]
        return {"status": "ok", "goals": c.goals[n:], "result": {"continuation_of": dup["order_id"]}}
    quotes = [t.quotes[rv] for rv in resolved]
    for rv in resolved:                                       # bằng chứng kho mới nhất của lượt (read_stock có thể sau read_quote)
        st = t.stock[rv]
        t.quotes[rv].update(in_stock=st["in_stock"], **({"stock_qty": st["qty"]} if isinstance(st.get("qty"), int) else {}))
    from core.config import settings
    qty = 1
    if settings.order_qty and len(resolved) == 1 and s.qty_obs and s.qty_obs[0] >= r["turn"] and 1 <= s.qty_obs[1] <= 20:
        qty = s.qty_obs[1]
        s.known["qty"] = qty
    c.facts["proposal"] = {"skus": tuple(resolved), "names": [product_name(x) for x in resolved]}
    n = len(c.goals)
    s._req_why = None
    g = s._order_target(c.facts, s.customer or {}, r, resolved, quotes, qty, s._pay_terms(), unique=ctx["picked"])
    c.goals += [x for x in g if x not in c.goals]
    st = r["status"]
    out = {"status": "ok" if st in ("done", "partial") else "blocked" if st in ACTIVE else st,
           "goals": c.goals[n:], "result": {"request": r["id"], "request_status": st,
                                            "orders": (r.get("outcome") or {}).get("orders")}}
    if st in ACTIVE:
        # chưa ghi: hết hàng / vượt hạn mức COD / điều kiện / revision… — executor đã dựng câu trả lời có nguồn (B1 dùng chung)
        out["missing"] = ["not_executed:" + (getattr(s, "_req_why", None) or ",".join(out["goals"]) or "unknown")]
    return out


def _ref_of(t, sku):
    par = _parent(sku)
    return next((k for k, v in t.s.reqs.refmap.items() if k.startswith("P") and v.get("skus") == (par,)), par)


# ---------------------------------------------------------------------- hỏi rõ / dừng

def _clarify_from(t, r, obs, c, s):
    """Câu hỏi / câu báo có nguồn cho đúng phần chặn của yêu cầu r (obs = kết quả kiểm MỚI NHẤT). → goals."""
    c.facts.update(obs.get("clarify_facts") or {})
    if obs.get("window_passed"):
        g = [] if s.window_told else list(obs.get("clarify") or [])
        s.window_told = True
        return g
    if obs.get("addr_block"):
        told = s.__dict__.setdefault("addr_block_told", set())     # V51: báo một lần cho mỗi đơn trong cuộc
        g = [] if obs["addr_block"] in told else list(obs.get("clarify") or [])
        told.add(obs["addr_block"])
        return g
    if obs.get("clarify"):
        if "ask_which_order" in obs["clarify"] and r is not None and r.get("kind") in ORDER_OP_KINDS:
            s.reqs.mark_asked_target(r, s.turn_no)          # V45 §8.5: lượt sau khách trả lời chọn đơn cho CHÍNH yêu cầu này
        return list(obs["clarify"])
    fn = obs.get("clarify_fn")
    if getattr(t, "halting", False) and fn in ("handoff_multi_line", "multi_request"):
        return []                                   # dừng sớm: chỉ phản hồi từ bằng chứng đã có, không thực hiện thêm nghiệp vụ
    if fn == "handoff_multi_line":
        s._why("multi_line_order_change_limit", r["id"])
        c.facts["handoff"] = s._handoff(c.text, "khac")
        s.open_questions.append(s._record_view(c.text)[:200])
        s.outcome = "chuyen_may"
        return ["handoff"]
    if fn == "ask_product_target":
        return s._ask_product_target(r, c.facts)
    if fn == "multi_request":
        return s._plan_order_target(c.text, c.facts)              # nhánh multi_request của B1: hỏi trước khi ghi, không gộp
    if fn == "additional_order":
        dup = next(o for o in s.orders_created if o["order_id"] == obs["dup"])
        if obs.get("rel") == "overlap":
            return s._ask_overlap_order(r, dup, obs["resolved"], c.facts)
        from harness.tools import product_name
        s.reqs.park(r, "same_products_as_existing_order")
        c.facts["additional_order"] = {"products": [product_name(x) for x in obs["resolved"]], "order_id": dup["order_id"]}
        c.facts["proposal"] = {"skus": tuple(obs["resolved"]), "names": [product_name(x) for x in obs["resolved"]], "additional": True}
        return s._order_exists_goals(dup, c.facts) + ["ask_additional_order"]
    return []


def _clarify(t, req_ref, ref):
    """Hỏi lại ĐÚNG điều cần làm rõ (duyệt 12/11): phần chặn được TÍNH LẠI từ cùng các kiểm của commit (không dựa observation
    cũ); điều kiện chưa thỏa / bị cấm → báo đúng điều đó; chỉ thiếu bằng chứng tool hoặc đã đủ để thử → KHÔNG hỏi khách gì
    (bước bị chặn `nothing_to_clarify`, không kết thúc lượt — planner đọc / thực hiện tiếp). Không rơi về câu chính sách chung.
    Không ghi gì (trừ chuyển nhân viên đơn nhiều dòng — scope công khai)."""
    s, c, n = t.s, t.c, len(t.c.goals)
    r = t.request(req_ref) if req_ref else None
    if r is None and not req_ref:
        last = next((o for o in reversed(t.steps) if o["status"] == "blocked" and o.get("request_ref")), None)
        r = t.request(last["request_ref"]) if last else None
    if r is None and getattr(s.reqs, "write_hold", None) == "target_only_turn":
        # V45 §8.4: câu chỉ thiếu đơn đích → hỏi đơn nào cho đúng yêu cầu vừa mở, không xin khách nói lại cả câu
        r = next((x for x in reversed(t.active_requests()) if x["kind"] in ORDER_OP_KINDS and x.get("target") is None), None)
    if s.reqs.hold or (r is None and (t.c.u or {}).get("ambiguity") == "needs_clarification"):
        g = ["ask_repeat"]
    elif r is None:
        return {"status": "blocked", "missing": ["nothing_to_clarify:no_request"]}
    elif any(str(m).startswith(("authorize:", "not_executed:")) for m in (t.blocked.get(r["id"]) or {}).get("missing") or [])             and (t.blocked[r["id"]].get("clarify") or t.blocked[r["id"]].get("goals")):
        # executor đã thử và bị từ chối (điều kiện / revision / hết hàng / COD…): câu trả lời có nguồn executor đã dựng
        last = t.blocked[r["id"]]
        g = list(last.get("clarify") or [])
    else:
        rd = readiness(t, r)
        if rd["state"] in ("missing_evidence", "ready_executor_rechecks"):
            return {"status": "blocked", "missing": [f"nothing_to_clarify:{rd['state']}"], "readiness": rd}
        if r["kind"] == "place_order":
            obs, ctx = _place_order_check(t, r, ref)
        elif r["kind"] in ORDER_OP_KINDS:
            obs, ctx = _order_op_check(t, r, ref)
        else:
            obs, ctx = ({"status": "blocked", "missing": ["callback_time"], "clarify": ["defer_ack"]}, {}) \
                if rd["detail"] == ["callback_time"] else (None, {})
        if obs is not None:
            g = _clarify_from(t, r, obs, c, s)
        elif rd["state"] == "condition_unmet" and "out_of_stock" in rd["detail"]:
            from harness.tools import product_name
            oos = next(rv for rv in ctx.get("resolved") or [] if t.stock.get(rv, {}).get("in_stock") is False)
            c.facts["quote"] = t.quotes.get(oos) or {"sku": oos, "name": product_name(oos)}
            c.facts["restock_expected"] = (t.stock.get(oos) or {}).get("restock_expected") or c.facts["quote"].get("restock_expected")
            g = ["out_of_stock"]
        elif rd["state"] == "condition_unmet":
            g = condition_reply(t, r)                    # điều kiện của khách chưa thỏa / chờ: nói đúng điều kiện, chưa lên đơn
        else:
            g = []
        if not g and not (obs or {}).get("window_passed"):
            return {"status": "blocked", "missing": [f"nothing_to_clarify:{rd['state']}"], "readiness": rd}
    if "ask_address" in g and r is not None and r.get("kind") == "change_order_address":
        s.reqs.note_question(r, "address", s.turn_no)       # V48: ý định hỏi địa chỉ cho ĐÚNG request này (xác nhận khi câu gửi có)
    c.goals += [x for x in g if x not in c.goals]
    return {"status": "ok", "goals": c.goals[n:], "terminal": True}


def _complete_address(t):
    """V48: bổ sung địa chỉ cho ĐÚNG MỘT đơn vừa tạo trong cuộc còn thiếu địa chỉ, theo binding bổ sung (khách trả lời câu hỏi địa
    chỉ đã gửi cho đơn đó, lượt một mục đích). Không sửa địa chỉ đã có, không ghi nhiều đơn, không đọc địa chỉ mức lượt / known.
    → goals, hoặc None khi không có binding."""
    from harness import tool_outcome
    from harness.request_state import _parents_of, _parent as par
    s, c = t.s, t.c
    got = s.reqs.completion_for(s)
    if not got:
        return None
    cb, o = got
    address = cb["value"]
    args = dict(order_id=o["order_id"], action="update_address", reason=f"địa chỉ mới: {address}")
    res = s.tools.call("order.update", **args)
    st = tool_outcome.classify({"name": "order.update", "args": args, "result": res})["status"]
    s.reqs.completion = None
    if st != "confirmed_success":
        return ["contract_error"]
    o["address"] = address
    done_par = {par(k) for k in (o.get("skus") or [o["sku"]])}
    for x in s.reqs.active("place_order"):
        if x["turn"] == s.reqs.turn and (x["target"] is None or _parents_of(x["target"]) <= done_par):
            s.reqs.settle(x, "confirmed_success", {"continuation_of": o["order_id"], "via": "address_completion"})
    s.known["address"] = address
    c.facts["address_update"] = {"orders": [o["order_id"]], "address": address}
    return ["address_updated"]


def _finish(t, req_ref, ref):
    """Kết thúc lượt: còn ask chưa trả lời, hoặc yêu cầu CÓ ĐIỀU KIỆN mở trong lượt chưa được phản hồi (chưa thử thực hiện /
    chưa hỏi rõ / chưa báo điều kiện) → bị chặn. Phản hồi điều kiện KHÔNG bắt thực hiện hay đánh dấu hoàn thành khi điều kiện
    chưa thỏa (executor / request_state giữ yêu cầu ở trạng thái conditional)."""
    pend = t.pending_asks()
    cond = [r["id"] for r in t.active_requests() if r.get("condition") and r["turn"] == t.s.turn_no and r["id"] not in t.addressed]
    # patch cuối 13/11: yêu cầu add_to_cart của lượt phải được phản hồi về giỏ (report_cart) — chỉ khi B2 bật reuse_quotes
    cart = ["respond_cart"] if t.reuse_quotes and t.cart_obligation() and not t.cart_reported else []
    if pend or cond or cart:
        return {"status": "blocked", "missing": [f"ask:{a}" for a in pend] + [f"respond_request:{x}" for x in cond] + cart}
    return {"status": "ok", "terminal": True}


# ---------------------------------------------------------------------- ngữ cảnh giá: mua riêng vs trong giỏ (13/11 vòng giỏ)

PRICE_ASKS = ("price", "promo", "promo_end", "compare", "gift")      # khách hỏi giá / KM của một mẫu = giá MUA RIÊNG
ASKED_IN_QUOTE = ("stock", "promo", "promo_end", "gift")             # F1 (+gift F1b): chủ đề khối báo giá phải trả lời thành lời
PRODUCT_ASKS = frozenset({"price", "promo", "promo_end", "stock", "compare", "gift", "recommend"})   # F2
ORDER_GOAL_DONE = ("order_created", "order_exists", "order_partial", "order_unresolved", "order_failed", "confirm_order",
                   "confirm_new_price", "ask_variant", "out_of_stock", "cod_limit")


def _ask_suspended(t, sus):
    """V50 (16/11): lượt vừa TREO binding địa chỉ vì xung đột (request_state._conflict_check) → hỏi lại cho đúng chỗ:
      - đúng MỘT request bị treo, đơn đích đã rõ và thuộc khách → hỏi địa chỉ mới cho ĐÚNG đơn đó (ask_address + address_change
        {order_id, product}); ghi Ý ĐỊNH hỏi bằng note_question — chỉ thành câu hỏi đã gửi khi câu cuối có ask_address (set_proposal);
      - nhiều request bị treo / chưa rõ đơn → hỏi xác định đơn trước (ask_which_order), không tự chọn request để hỏi địa chỉ.
    Không gắn / phục hồi binding, không ghi, không đổi kiểm quyền. Lượt đã có cập nhật địa chỉ → không thêm gì. → nhật ký | None."""
    from harness.request_state import known_orders
    c, s = t.c, t.s
    if "address_updated" in c.goals:
        return None
    orders = {o["order_id"]: o for o in known_orders(s)}
    oids = [(r.get("target") or {}).get("order_id") for r in sus]
    if len(sus) == 1 and oids[0] in orders:
        r, oid = sus[0], oids[0]
        c.facts["address_change"] = {"order_id": oid, "product": s._order_products(orders[oid])}
        if "ask_address" not in c.goals:
            c.goals.append("ask_address")
        s.reqs.note_question(r, "address", s.turn_no)
        return {"why": "address_suspended", "id": r["id"], "order_id": oid, "goals": ["ask_address"]}
    pick = [o for k, o in orders.items() if k in oids] or list(orders.values())[-5:]
    if not pick:
        return None
    c.facts["which_orders"] = [{"order_id": o["order_id"], "product": s._order_products(o)} for o in pick]
    c.facts["which_orders_action"] = OP_ACTION_VI.get("change_order_address")
    if "ask_which_order" not in c.goals:
        c.goals.append("ask_which_order")
    return {"why": "address_suspended_multi", "ids": [r["id"] for r in sus], "goals": ["ask_which_order"]}


def apply_order_gate(t):
    """F8 (13/11, B2): yêu cầu đặt của khách bị cổng request_state chặn ở lượt này (request_state.order_gate) → không ghi gì;
    thêm đúng một câu xin xác nhận:
      - intent_only        → confirm_order nêu đúng mẫu (đối tượng yêu cầu / mẫu nhắc trong lượt / mẫu đang bàn);
      - price_unconfirmed  → khối báo giá THẬT (tool) + confirm_new_price; không nhắc lại số tiền khách tự nêu;
      - pseudo_system      → không thêm gì (câu tự xưng hệ thống không là xác nhận; trả lời theo các khối đã có).
    Không gọi tool ghi. Chỉ đọc giá khi khối báo giá chưa có và còn ngân sách tool. → nhật ký (trace) hoặc None."""
    from core.config import settings
    from harness.tools import product_name
    c, s = t.c, t.s
    g = getattr(s.reqs, "order_gate", None)
    og = getattr(s.reqs, "op_gate", None)
    if settings.planner_variant == "b2_jev" and not g and (og is None or og.get("kind") == "change_order_address") \
            and not s.reqs.hold:
        sus = s.reqs.suspended_in_turn()
        if sus:
            log = _ask_suspended(t, sus)                 # V50: hỏi lại đúng request vừa bị treo, trước nhánh ask_repeat của op_gate
            if log:
                return log
    if not g and og:
        # V44 (15/11): yêu cầu đổi / trả / đổi địa chỉ thiếu căn cứ (đồng ý ngầm, không có động từ thao tác, lời kể, câu hỏi, điều
        # kiện chưa rõ) → không ghi, xin khách nói rõ lại
        if not any(x in c.goals for x in ORDER_GOAL_DONE) and "ask_repeat" not in c.goals:
            c.goals.append("ask_repeat")
        return {"why": f"op:{og['why']}", "kind": og["kind"], "goals": ["ask_repeat"]}
    if not g and getattr(c, "all_unconfirmed", None):
        # C1 (15/11): thêm giỏ nhắm "ALL" → không đổi giỏ, xin xác nhận đúng các món
        g = {"why": "all_unconfirmed", "target": {"type": "product", "skus": tuple(c.all_unconfirmed)}}
    if not g:
        return None
    log = {"why": g["why"], **({"stated_vnd": g["stated_vnd"]} if g.get("stated_vnd") else {})}
    if g["why"] == "pseudo_system":
        return log
    if any(x in c.goals for x in ORDER_GOAL_DONE):
        return {**log, "skipped": "order_goal_present"}
    if g["why"] == "target_ambiguous":
        # V42 (15/11): câu đặt không nêu món, nhiều đối tượng hợp lý → hỏi rõ + liệt kê lựa chọn (goal có sẵn ask_which_product);
        # KHÔNG đặt facts.proposal / confirm_order (không có đề nghị một giỏ do hệ thống đoán)
        names = [product_name(x) for x in (g.get("options") or [])][:4]
        c.facts["which_products"] = names
        if "ask_which_product" not in c.goals:
            c.goals.append("ask_which_product")
        log.update(goals=["ask_which_product"], options=names)
        return log
    skus = list((g.get("target") or {}).get("skus") or ()) \
        or list(dict.fromkeys(_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x)) \
        or ([_parent(s.focus)] if s.focus else [])
    made = {_parent(x) for o in getattr(s, "orders_created", None) or [] for x in (o.get("skus") or [o.get("sku")]) if x}
    if g["why"] == "intent_only" and made and (not skus or set(skus) <= made):
        # câu bổ sung thanh toán / địa chỉ sau khi đơn của mẫu đó đã tạo trong cuộc: không xin xác nhận đặt lại
        return {**log, "skipped": "order_exists_in_call"}
    if g["why"] == "price_unconfirmed":
        if skus and (c.facts.get("quote") or {}).get("sku") is None and t.tool_calls + 2 <= settings.b2_max_tool_calls:
            t.run("read_quote", None, _ref_of(t, skus[0]), "order_gate")
        if (c.facts.get("quote") or {}).get("final_price_vnd") and "quote" not in c.goals:
            c.goals.append("quote")
        c.goals.append("confirm_new_price")
    else:
        c.facts["proposal"] = {"names": [product_name(x) for x in skus], "skus": skus}
        c.goals.append("confirm_order")
    log["goals"] = [x for x in ("quote", "confirm_new_price", "confirm_order") if x in c.goals]
    log["skus"] = skus
    return log


OPENING_FOCUS_STOPS = ("finish", "clarify")    # chỉ sau khi vòng Jev kết thúc bình thường


def apply_opening_focus(t, stop=None):
    """TA1 (14/11, duyệt): lượt đầu khách quay lại nêu ĐÚNG MỘT mẫu khác mẫu đã tư vấn (c.opening_switch do h_opening_returning
    đặt từ parser catalog) → lượt phải nói về CHÍNH mẫu đó: chưa có báo giá của mẫu đó trong lượt thì đọc giá + kho bằng tool,
    thêm goal quote. KHÔNG gọi tool khi vòng đã dừng cứng (ngân sách / deadline / lỗi / tuple sai / phần dừng _halt) hoặc đã quá
    deadline; không vượt trần tool. Không đoán ý khách; không ghi gì."""
    from core.config import settings
    c = t.c
    sku = getattr(c, "opening_switch", None)
    if not sku:
        return None
    par = _parent(sku)
    log = {"sku": par}
    q = c.facts.get("quote") or {}
    if q.get("sku") and _parent(q["sku"]) == par:
        log["skipped"] = "quote_present"
    elif getattr(t, "halting", False) or stop not in OPENING_FOCUS_STOPS:
        log["skipped"] = f"hard_stop:{stop}" if not getattr(t, "halting", False) else "halting"
        return log
    elif time.perf_counter() - t.t0 > settings.b2_deadline_s:
        log["skipped"] = "deadline"
        return log
    elif t.tool_calls + step_cost(t, "read_quote", None, par) <= settings.b2_max_tool_calls:
        t.run("read_quote", None, _ref_of(t, sku), "opening_focus")
        q = c.facts.get("quote") or {}
        if not (q.get("sku") and _parent(q["sku"]) == par):
            log["skipped"] = "quote_unavailable"
            return log
    else:
        log["skipped"] = "tool_budget"
        return log
    if q.get("final_price_vnd") and "quote" not in c.goals:
        c.goals.append("quote")
    return log


def _cart_conditional_promo(name):
    """Tên chương trình (như _cart_facts ghi) là KM phụ thuộc THÀNH PHẦN GIỎ (vd AIR-2ND-50: từ 2 máy lọc không khí cùng đơn)."""
    from harness.tools import mt
    pr = next((x for x in mt.PROMOS if x.get("name") == name), None)
    return bool(pr) and (pr.get("type") == "percent_second_item" or bool((pr.get("conditions") or {}).get("min_qty")))


def reconcile_price_context(t):
    """Trước khi render câu trả lời có giỏ (cart_total): đối chiếu bằng chứng giá MUA RIÊNG (get_quote) với giá TRONG GIỎ
    (quote_order) của cùng mẫu — không để hai giá khác nhau đứng cạnh nhau mà không nói điều kiện:
      - dòng giỏ có KM phụ thuộc thành phần giỏ → ghi kèm tên chương trình (price_note);
      - món đã trong giỏ không trình bày là "mẫu khác" (alternative_quote): khách không hỏi giá → bỏ (dòng giỏ đã có giá);
        khách hỏi giá → giữ, ghi rõ là giá mua riêng;
      - khối báo giá của món trong giỏ: khách không hỏi giá → bỏ goal quote (dòng giỏ thay); hỏi giá mà giá riêng khác giá
        trong giỏ → ghi rõ "mua riêng".
    Chỉ đổi cách trình bày bằng chứng đã đọc (không gọi tool, không đổi giỏ / giá). → nhật ký (trace) hoặc None."""
    c = t.c
    cart = c.facts.get("cart")
    if "cart_total" not in c.goals or not isinstance(cart, dict) or not cart.get("items"):
        return None
    log = {"cart": [i.get("sku") for i in cart["items"]], "noted": [], "dropped": [], "labeled_standalone": []}
    in_cart, cart_prices = set(), {}
    items = []
    for i in cart["items"]:
        par = _parent(i.get("sku")) if i.get("sku") else None
        if par:
            in_cart.add(par)
            cart_prices.setdefault(par, set()).add(i.get("final_price_vnd"))
        conds = [n for n in i.get("promo_names") or [] if _cart_conditional_promo(n)]
        if conds:
            i = {**i, "price_note": "; ".join(conds)}
            log["noted"].append(i.get("sku"))
        items.append(i)
    c.facts["cart"] = {**cart, "items": items}
    asked = bool(set(t.asks()) & set(PRICE_ASKS))
    for key, goal in (("alternative", "alternative_quote"), ("quote", "quote")):
        v = c.facts.get(key)
        if not isinstance(v, dict) or goal not in c.goals or _parent(v.get("sku")) not in in_cart:
            continue
        differs = any(p != v.get("final_price_vnd") for p in cart_prices.get(_parent(v.get("sku")), ()))
        if not asked:
            c.goals.remove(goal)
            if key == "alternative":
                c.facts.pop("alternative", None)
            log["dropped"].append({"goal": goal, "sku": v.get("sku"), "why": "in_cart_no_price_ask"})
        elif differs or key == "alternative":
            c.facts[key] = {**v, "price_context": "standalone"}
            log["labeled_standalone"].append({"goal": goal, "sku": v.get("sku")})
    t.price_context = log
    return log


# ---------------------------------------------------------------------- chi phí tool tối đa của một bước (patch cuối 13/11)

_QUOTE_TOPICS = ("price", "promo", "promo_end", "stock", "compare", "gift")


def _cart_cost(t):
    s = t.s
    return sum(0 if s._resolve_variant(x, t.c.text) in t.quotes else 2 for x in s.cart) + (1 if s.cart else 0)


def step_cost(t, action, rq, tg):
    """Số tool call TỐI ĐA bước này có thể gọi ở trạng thái hiện tại (cận trên, theo SCOPE + bằng chứng đã có trong lượt).
    Vòng B2 chỉ cho chạy bước khi tool_calls + chi phí ≤ trần → trần tool là cứng ở mức lượt (trước đây chỉ kiểm trước bước)."""
    s = t.s
    if action in ("check_window", "read_policy", "finish", "clarify_field"):
        return 0
    if action == "read_quote":
        return 2
    if action in ("read_stock", "read_order"):
        return 1
    if action == "report_cart":
        return _cart_cost(t)
    if action == "clarify":
        r = t.request(rq) if rq else None
        return 0 if r is None else (2 if r["kind"] == "place_order" else 1)
    if action == "answer_ask":
        topic = str(tg or "")[4:]
        if (topic in _QUOTE_TOPICS or topic == "recommend") and _category_switch(t):
            # V52-B: đối tượng là nhóm hàng khách nêu → báo giá mẫu đã bàn (2) hoặc gợi ý trong nhóm (catalog + kho từng mẫu + báo giá)
            A = T._A()
            cats = _named_categories(t)
            n = sum(1 for p in A.mt.PRODUCTS if any(p["category"].startswith(x) for x in cats) and p["list_price_vnd"] >= 400000)
            return 0 if len(cats) > 1 else max(2, 1 + n + 2)        # quay lại mẫu đã bàn (giá + kho) | catalog + kho từng mẫu + giá + kho
        if topic in _QUOTE_TOPICS and (s.focus or t.c.mentioned or t.c.alt):
            f = s.focus and s._resolve_variant(s.focus, t.c.text)
            return (0 if f and f in t.quotes and not t.c.compare else 2) + 2   # +2: mẫu thay thế khi ngừng bán
        if topic in ("recommend",) or topic in _QUOTE_TOPICS:
            # đúng nhánh của CallSession._recommend: không xác định danh mục / máy lọc không khí chưa có nhu cầu → không tool;
            # còn lại catalog.search + inventory.check từng mẫu ≥ 400k của danh mục + báo giá mẫu gợi ý (+ mẫu đang bàn)
            A = T._A()
            f = A.fold(t.c.text)
            cat = next((cc for w, cc in A.CATEGORY_WORDS if w in f), None) or s.category
            if not cat:
                # A1 (15/11): gợi ý không ra nội dung → đọc giá mẫu của khách (2 tool) nếu có mẫu
                return 2 if topic == "recommend" and (s.focus or t.c.mentioned) else 0
            if cat == "gia-dung/may-loc-khong-khi" and not ({"has_children", "budget_vnd"} & set(s.known)):
                return 0
            n = sum(1 for p in A.mt.PRODUCTS if p["category"].startswith(cat) and p["list_price_vnd"] >= 400000)
            return 1 + n + 2 + (2 if s.focus else 0)
        if topic == "budget":
            return 2 + 1 + 4 + 2                                  # V52: báo giá + kho mẫu đang bàn, catalog, ≤4 kho, báo giá + kho mẫu thay thế
        if topic in ("cart_total", "cod"):
            return _cart_cost(t) if s.cart else 0
        if topic in ("refund_amount", "order_status", "delivery_address", "return_policy", "warranty", "policy", "quality",
                     "payment_method", "delivery_time"):
            return 1                                              # có thể tra order.status để xác định đơn / phiên bản chính sách
        return 0                                                  # attribute (catalog) / other (khối chung / no_info)
    if action == "commit_request":
        if rq in ("X_CANCEL", "X_COMPLETE_ADDRESS"):
            return 1
        r = t.request(rq)
        return 3 if (r or {}).get("kind") == "place_order" else 1
    return 2
