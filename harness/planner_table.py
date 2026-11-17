"""D50 (docs/PLAN-2026-11-05-PLANNER-TABLE.md): planner chạy theo BẢNG QUYẾT ĐỊNH thay cho chuỗi if-else trong _plan.

Đường planner DUY NHẤT từ 06/11 (bước 1b: bỏ CallSession._plan cũ; PLANNER_SKIP_SINCE=D51 = bảng như trước D51). Ba phần:
  1. Bước chuẩn bị: giữ nguyên code của _plan (sản phẩm được nhắc, focus, giỏ, asking/takes/compare…).
  2. Bộ máy bảng: duyệt dòng trong harness/planner_rules.json theo priority; dòng khớp `when` → gọi HANDLER (code).
     Predicate (điều kiện có tên) tính LƯỜI tại đúng vị trí dòng, nên đọc trạng thái y như code cũ ở cùng thời điểm.
  3. Hậu xử lý: giữ nguyên (open_questions, order_failed liên tiếp → handoff, khử trùng goal).

Bảng chỉ chứa tên handler / predicate; tham số tool, giá, số tiền vẫn do code lấy từ kết quả tool (bất biến của dự án).
Bảng chỉ có nhánh cũ từng trùng trace 100 % với _plan (D50); sau khi bỏ _plan, tests/planner_table_parity.py so với bản tham chiếu --ref-root.

Dòng origin=approved (do người duyệt qua improve/, giai đoạn 3) chỉ được dùng handler trong SAFE_HANDLERS.
"""
import json
import re

from core.config import settings
from harness.lexicon import rx as lexrx

MODES = {"add", "terminal", "rewrite_intent", "handler"}
# handler không tạo / sửa / xóa đơn, không xóa bộ nhớ, không đặt lịch → dòng do người duyệt (origin=approved) chỉ được dùng nhóm này
SAFE_HANDLERS = {"add_goal", "quote", "policy_answer", "order_status", "refuse_other_customer", "attr_check", "gift_status",
                 "cart_total", "defer_ack", "handoff_scope", "warranty_fact", "policy_peek", "order_updated_note",
                 "ask_repeat", "refund_amount", "defer_close", "handoff_reason"}

_cache = {"path": None, "mtime": None, "rows": None}


class Ctx:
    """Trạng thái của một lượt khi chạy bảng (tương ứng các biến cục bộ của _plan)."""

    def __init__(self, s, text, slots, route):
        self.s, self.text, self.slots, self.route = s, text, slots, route
        self.it, self.fl = route["intent"], route.get("flags", {})
        self.goals, self.facts = [], {}
        self.memo = {}
        # cấu hình đích: dữ liệu có kiểu từ bộ hiểu DeepSeek (asks / requests / response / refs / safety) — predicate đọc ở đây
        self.u = route.get("understanding") if settings.arch == "target" else None

    def y(self, k, th=0.6):
        return self.fl.get(k, 0) >= th


# ----------------------------------------------------------------------------------------------- nạp và kiểm bảng

def validate(doc, handlers=None, preds=None):
    """Kiểm schema; trả danh sách lỗi (rỗng = hợp lệ)."""
    handlers = HANDLERS if handlers is None else handlers
    preds = PREDS if preds is None else preds
    errs, ids = [], set()

    def check_when(w, rid, approved=False):
        for k in w:
            if k not in ("intent", "intent_not", "flags", "preds", "any", "text"):
                errs.append(f"{rid}: khóa when lạ '{k}'")
        if approved and w.get("preds"):
            errs.append(f"{rid}: dòng approved chỉ được dùng intent / flags / text, không dùng predicate nội bộ")
        if "text" in w:
            try:
                re.compile(w["text"])
            except (re.error, TypeError) as e:
                errs.append(f"{rid}: when.text không phải regex hợp lệ: {e}")
        for name, cond in (w.get("flags") or {}).items():
            if not re.fullmatch(r"(>=|<)\d+(\.\d+)?", str(cond)):
                errs.append(f"{rid}: điều kiện cờ '{name}: {cond}' phải dạng >=x hoặc <x")
        for p in w.get("preds") or []:
            if p.lstrip("!") not in preds:
                errs.append(f"{rid}: predicate lạ '{p}'")
        for sub in w.get("any") or []:
            check_when(sub, rid, approved)

    for r in doc.get("rows", []):
        rid = r.get("id")
        if not rid or rid in ids:
            errs.append(f"id thiếu hoặc trùng: {rid}")
        ids.add(rid)
        if r.get("mode") not in MODES:
            errs.append(f"{rid}: mode lạ {r.get('mode')}")
        h = (r.get("do") or {}).get("handler")
        if h not in handlers:
            errs.append(f"{rid}: handler lạ {h}")
        if r.get("origin", "core") not in ("core", "proposed", "approved"):
            errs.append(f"{rid}: origin lạ {r.get('origin')}")
        if r.get("origin") == "approved" and h not in SAFE_HANDLERS:
            errs.append(f"{rid}: dòng approved không được dùng handler {h} (chỉ handler an toàn)")
        if not isinstance(r.get("priority"), (int, float)):
            errs.append(f"{rid}: thiếu priority")
        elif r.get("origin") == "approved" and not 1 <= r["priority"] <= 899:
            errs.append(f"{rid}: dòng approved phải có priority trong 1–899 (trước fallback R36)")
        if r.get("origin") == "approved" and not (r.get("when") or {}):
            errs.append(f"{rid}: dòng approved phải có điều kiện when")
        check_when(r.get("when") or {}, rid, r.get("origin") == "approved")
    return errs


def load_rows(path=None, extra=None):
    """Dòng core trong bảng + dòng approved (extra, từ improve_hook) — bỏ dòng proposed. Sắp theo priority (ổn định)."""
    import os
    path = path or settings.planner_rules_path
    mtime = os.path.getmtime(path)
    if _cache["path"] != path or _cache["mtime"] != mtime:
        doc = json.load(open(path, encoding="utf-8"))
        errs = validate(doc)
        if errs:
            raise ValueError("planner_rules.json không hợp lệ: " + "; ".join(errs[:5]))
        _cache.update(path=path, mtime=mtime, rows=[r for r in doc["rows"] if r.get("origin", "core") in ("core", "approved")])
    skip = set(settings.planner_skip_since)      # 1b: PLANNER_SKIP_SINCE=D51 → bỏ dòng "since": "D51"
    rows = [r for r in _cache["rows"] if r.get("since") not in skip]
    if extra:
        errs = validate({"rows": extra})
        if errs:
            raise ValueError("dòng approved không hợp lệ: " + "; ".join(errs[:5]))
        rows += [r for r in extra if r.get("origin") == "approved"]
    return sorted(rows, key=lambda r: r["priority"])


# ----------------------------------------------------------------------------------------------- khớp điều kiện

def _flag_ok(c, name, cond):
    v = c.fl.get(name, 0)
    op, th = (">=", float(cond[2:])) if cond.startswith(">=") else ("<", float(cond[1:]))
    return v >= th if op == ">=" else v < th


def matches(c, w):
    if "intent" in w and c.it not in w["intent"]:
        return False
    if "intent_not" in w and c.it in w["intent_not"]:
        return False
    for name, cond in (w.get("flags") or {}).items():
        if not _flag_ok(c, name, cond):
            return False
    if "text" in w and not re.search(w["text"], c.f):
        return False
    if "any" in w and not any(matches(c, sub) for sub in w["any"]):
        return False
    for p in w.get("preds") or []:
        neg = p.startswith("!")
        name = p.lstrip("!")
        fn = PREDS_TARGET.get(name, PREDS[name]) if c.u is not None else PREDS[name]
        val = bool(fn(c))
        if val == neg:
            return False
    return True


# ----------------------------------------------------------------------------------------------- predicate
# Mỗi predicate chép đúng biểu thức điều kiện trong CallSession._plan (số dòng ghi kèm). Đọc trạng thái tại lúc gọi.

def _A():
    from harness import agent
    return agent


def _sales_turn(c):                                                                     # L841
    return c.it not in ("order_change", "order_status", "meta", "out_of_scope")


def _adding(c):                                                                         # L935
    return bool(re.search(r"\b(lay them|them (cho|mot|1|cai)|mua them)\b", c.f)) and not _A().CLOSE_ORDER_RX.search(c.f)


def _wants(c):                                                                          # L936
    return c.it == "place_order" and (c.y("agrees_to_buy", 0.5) or c.s.router.backend == "rules") and not _adding(c)


def _pending(c):                                                                        # L945–946
    return c.s.buy_intent and not c.asking and c.it not in ("callback", "negotiate", "order_change", "order_status") \
        and any(k in c.slots for k in ("address", "payment", "size", "color"))


def _asks_price(c):                                                                     # L856–858
    s = c.s
    return c.it in ("price_promo", "negotiate", "product_inquiry") or (c.new_focus and c.new_focus != c.prev_focus) \
        or bool(c.alt) or c.compare or ((c.gift_q or bool(_A().PROMO_END_RX.search(c.f))) and bool(s.focus)) \
        or (c.it == "place_order" and c.asking) or "exchange_window_passed" in c.goals


def _policy_gap(c):                                                                     # L789
    if "gap" not in c.memo:
        c.memo["gap"] = c.s._policy_gap(c.text, c.f, c.asking)
    return c.memo["gap"]


def _attr_ask(c):                                                                       # L827–828
    terms = [m.group(0) for m in _A().ATTR_ASK_RX.finditer(c.f)]
    c.memo["terms"] = terms
    return c.asking and terms and "no_info" not in c.goals and "policy_answer" not in c.goals


def _stale_focus(c):                                                                    # L950–952
    s = c.s
    stale = [w for w in (s.brief or {}).get("stale_warnings", []) if s.focus and _A().mt._parent(s.focus)[0]
             and _A().mt._parent(s.focus)[0]["sku"] in w and ("KM" in w or "giá" in w)]
    return bool(stale) and not s.price_change_told


# ---- D51: predicate cho case mới (chỉ dùng ở dòng có "since": "D51")
# cue nằm trong harness/lexicon/cues.json (06/11)
RETURN_CUE_RX = lexrx.rx("cues", "RETURN_CUE_RX")
PRESSURE_RX = lexrx.rx("cues", "PRESSURE_RX")
CANCEL_RX = lexrx.rx("cues", "CANCEL_RX")
LATER_CLOSE_RX = lexrx.rx("cues", "LATER_CLOSE_RX")
DECLINE_RX = lexrx.rx("cues", "DECLINE_RX")
SHOP_CALLS_RX = lexrx.rx("cues", "SHOP_CALLS_RX")


def _noisy_asr(c):
    t = c.text.lower()
    return c.s.input_mode == "asr_transcript" and (t.count("…") + t.count("...") >= 2
                                                     or bool(re.search(r"(?<!\w)(rè|rẹt|tút|xè|xẹt)(?!\w)", t)))


RETURN_LIKE_ACTIONS = ("return", "exchange_product", "exchange_size")


def _has_return_info(c):
    s = c.s
    if any(k[1] == "return" for k in s.updates_done):
        return True
    summ = (((s.brief or {}).get("last_session") or {}).get("summary") or "")
    return bool(RETURN_CUE_RX.search(_A().fold(summ)))


def _shop_calls_time(c):
    A = _A()
    if not SHOP_CALLS_RX.search(c.f) or A.extractor.CUSTOMER_CALLS_RX.search(c.f):
        return False
    w = A.extractor.parse_relative_datetime(c.text, c.s.today)
    c.memo["callback_w"] = w
    return bool(w)


def _repeat_exhausted(c):
    s = c.s
    garbled = s.input_mode == "asr_transcript" and c.route.get("confidence", 1) < 0.6
    return not c.goals and s.turn_no > 1 and not c.slots and not c.mentioned and not _A().CLOSING_RX.search(c.f) \
        and (c.asking or garbled) and s.repeat_asked >= 2 and settings.planner_backend == "rules"


PREDS = {
    "noisy_asr": _noisy_asr,
    "no_slots": lambda c: not c.slots,
    "no_mentioned": lambda c: not c.mentioned and not c.alt,
    "repeat_lt2": lambda c: c.s.repeat_asked < 2,
    "refund_ask": lambda c: bool(re.search(r"\b(tien hoan|so tien hoan|hoan lai|hoan tien|tien tra lai)\b", c.f)
                                 and re.search(r"\b(bao nhieu|nhieu tien|la may|may tien)\b", c.f)),
    "has_return_info": _has_return_info,
    "prev_refuse_internal": lambda c: "refuse_internal" in (c.s.table_prev_goals or []),
    "pressure_words": lambda c: bool(PRESSURE_RX.search(c.f)),
    "cancel_ask": lambda c: bool(CANCEL_RX.search(c.f)),
    "has_any_order": lambda c: bool(c.s.orders_created or (c.s.brief or {}).get("orders") or c.s.known.get("order_id")),
    "later_close": lambda c: bool(LATER_CLOSE_RX.search(c.f)),
    "declines_after_confirm": lambda c: bool(set(c.s.table_prev_goals or []) & {"confirm_order", "confirm_new_price", "exchange_offer"}
                                             and DECLINE_RX.search(c.f)),
    "shop_calls_time": _shop_calls_time,
    "repeat_exhausted": _repeat_exhausted,
    "has_candidates": lambda c: bool(c.s.candidates),
    "turn1": lambda c: c.s.turn_no == 1,
    "returning_with_prev_focus": lambda c: bool(c.s.brief and c.s.brief["is_returning"] and c.prev_focus),
    "other_pii": lambda c: bool(_A().OTHER_PII_RX.search(c.f) or (c.s.privacy_refused and re.search(r"\bchia se\b", c.f))),
    # 1c J6 (06/11): người tự xưng người nhà hỏi / đòi xóa thông tin của khách đó, hoặc giục tiếp sau khi đã bị từ chối
    "proxy_caller": lambda c: bool(getattr(c.s, "proxy_caller", False)),
    "proxy_info_ask": lambda c: bool(getattr(c.s, "proxy_caller", False) and (
        _A().PROXY_INFO_RX.search(c.f) or (c.s.privacy_refused and re.search(r"\b(doc|xoa|noi|kiem tra|cho biet)\b", c.f)))),
    "policy_gap": _policy_gap,
    "hypothetical_refund_ask": lambda c: bool(_A().HYPO_RX.search(c.f) and c.asking and _A().REFUND_RX.search(c.f)),
    "buy_intent": lambda c: bool(c.s.buy_intent),
    "orders_created": lambda c: bool(c.s.orders_created),
    "slot_address": lambda c: bool(c.slots.get("address")),
    "update_money_words": lambda c: bool(c.s.updates_done and re.search(r"\b(hoan|chenh|bu them)\b", c.f)),
    "has_qmark": lambda c: "?" in c.text,
    "focus": lambda c: bool(c.s.focus),
    "attr_ask": _attr_ask,
    "warranty_ask": lambda c: bool(re.search(r"\bbao hanh\b", c.f) and (c.mentioned or c.s.focus)),
    "recommend_needed": lambda c: bool(_sales_turn(c) and not c.mentioned and not c.alt and (
        c.s.focus is None or (c.s.focus_by == "recommend" and any(k in c.slots for k in ("room_area_m2", "has_children", "budget_vnd"))))),
    "asks_price_turn": lambda c: bool(_sales_turn(c) and "recommend" not in c.goals and _asks_price(c)),
    "budget_fit_turn": lambda c: bool(_sales_turn(c) and c.slots.get("budget_vnd") and c.s.focus and not c.s.cart
                                      and "recommend" not in c.goals and "ask_size_for_price" not in c.goals),
    "gift_turn": lambda c: bool(c.gift_q and _sales_turn(c) and c.facts.get("quote")),
    "cart_total_ask": lambda c: bool(c.s.cart and c.asking and re.search(r"\b(tong|het bao nhieu|tat ca|ca hai|giam gi|duoc giam)\b", c.f)),
    "cod_ask": lambda c: bool(c.asking and re.search(r"\b(cod|thanh toan khi nhan)\b", c.f)),
    "policy_peek": lambda c: "?" in c.text and _sales_turn(c) and c.it != "place_order",
    "competitor_words": lambda c: bool(re.search(r"\b(ben (do|kia|khac)|san thuong mai|shopee|lazada)\b", c.f)),
    "quality_words": lambda c: bool(re.search(r"\b(hang gia|hang nhai|kem chat luong|uy tin|chinh hang|duoc gi hon|khac gi|hon gi)\b", c.f)),
    "adding_cart": lambda c: bool(_adding(c) and c.s.cart and "cart_total" not in c.goals),
    "cart_budget": lambda c: bool(c.s.cart and "budget_vnd" in c.slots and "cart_total" not in c.goals),
    "wants": _wants,
    "order_trigger": lambda c: bool((_wants(c) and not c.asking) or _pending(c)),
    "stale_focus_untold": _stale_focus,
    "wants_asking_quoted": lambda c: bool(_wants(c) and c.asking and "quote" in c.goals),
    "stale_goal_untold": lambda c: "stale_promo" in c.goals and not c.s.price_change_told,
    "callback_slot": lambda c: bool(c.slots.get("callback_requested")),
    "no_goals": lambda c: not c.goals,
    "address_change_request": lambda c: False,          # T01 chỉ trên cấu hình đích (R0 không đổi hành vi)
}


# ---- Cấu hình đích (ARCH=target, K05): predicate ĐỌC DỮ LIỆU CÓ KIỂU thay cho regex đoán ý khách.
# Nguồn: bộ hiểu DeepSeek (asks / requests / response_to_agent / refs / safety / ambiguity), state yêu cầu (request_state)
# và kết quả tool. Parser định dạng (catalog lookup, số / ngày, thuật ngữ thuộc tính) vẫn là code; không có cue regex hiểu ý.
# Dòng bảng giữ nguyên; chỉ nguồn dữ liệu của predicate đổi. Bảng đối chiếu caller cũ → chủ sở hữu mới: docs/PLAN báo cáo 11/11.

def _u(c):
    return c.u or {}


def _asks(c, *topics):
    return bool(set(_u(c).get("asks") or []) & set(topics))


def _req(c, kind):
    return kind in (_u(c).get("requests") or [])


def _wants_t(c):
    """Khách chốt mua trong lượt này: yêu cầu place_order có căn cứ (hoặc đồng ý đề nghị đặt hàng) vừa được mở."""
    rs = getattr(c.s, "reqs", None)
    return bool(rs and any(e.get("event") == "opened" and e.get("kind") == "place_order" for e in rs.events))


def _pending_t(c):
    """Yêu cầu đặt hàng còn hiệu lực + khách NÊU / CHỌN thông tin đơn trong lượt (stance có kiểu của bộ hiểu, không theo cờ 'đang
    hỏi' của cả câu — câu đa ý vẫn có thể vừa đọc địa chỉ vừa hỏi điều khác)."""
    rs = getattr(c.s, "reqs", None)
    obs = {o["slot"] for o in ((c.s.u_turn or {}).get("observations") or []) if o.get("stance") in ("chosen", "stated")}
    return bool(rs and rs.has_active("place_order")) \
        and c.it not in ("callback", "negotiate", "order_change", "order_status") \
        and bool(obs & {"address", "payment", "size", "color"})


def _asks_price_t(c):
    s = c.s
    return c.it in ("price_promo", "negotiate", "product_inquiry") or (c.new_focus and c.new_focus != c.prev_focus) \
        or bool(c.alt) or c.compare or (_asks(c, "gift", "promo_end", "promo") and bool(s.focus)) \
        or (c.it == "place_order" and c.asking) or "exchange_window_passed" in c.goals


def _shop_calls_time_t(c):
    if not _req(c, "callback"):
        return False
    w = _A().extractor.parse_relative_datetime(c.text, c.s.today)     # parser thời điểm (không đoán ý)
    c.memo["callback_w"] = w
    return bool(w)


def _attr_ask_t(c):
    if not _asks(c, "attribute"):
        return False
    terms = [m.group(0) for m in _A().ATTR_ASK_RX.finditer(c.f)]       # parser thuật ngữ thuộc tính để tra catalog
    c.memo["terms"] = terms
    return bool(terms) and "no_info" not in c.goals and "policy_answer" not in c.goals


def _policy_gap_t(c):
    if "gap" not in c.memo:
        c.memo["gap"] = c.s._policy_gap(c.text, c.f, c.asking, typed=_asks(c, "return_policy", "refund_amount")) \
            if _asks(c, "return_policy", "refund_amount") or c.s.policy_gap else None
    return c.memo["gap"]


def _repeat_exhausted_t(c):
    s = c.s
    return not c.goals and s.turn_no > 1 and not c.slots and not c.mentioned and not _u(c).get("refs", {}).get("closing") \
        and (c.asking or _u(c).get("ambiguity") == "needs_clarification") and s.repeat_asked >= 2


PREDS_TARGET = {
    "noisy_asr": lambda c: c.s.input_mode == "asr_transcript" and _u(c).get("ambiguity") == "needs_clarification",
    "refund_ask": lambda c: _asks(c, "refund_amount"),
    "has_return_info": lambda c: any(k[1] in RETURN_LIKE_ACTIONS for k in c.s.updates_done)
                                 or bool(_u(c).get("refs", {}).get("existing_order") and PREDS["has_any_order"](c)),
    "pressure_words": lambda c: c.y("asks_internal_cost", 0.6),
    "cancel_ask": lambda c: _req(c, "cancel"),
    "later_close": lambda c: _u(c).get("response") == "defer" or c.y("defers_decision", 0.5),
    "declines_after_confirm": lambda c: bool(set(c.s.table_prev_goals or []) & {"confirm_order", "confirm_new_price", "exchange_offer"})
                                        and _u(c).get("response") in ("decline", "defer"),
    "shop_calls_time": _shop_calls_time_t,
    "repeat_exhausted": _repeat_exhausted_t,
    "other_pii": lambda c: "asks_other_customer" in (_u(c).get("safety") or []),
    "proxy_info_ask": lambda c: bool(getattr(c.s, "proxy_caller", False) and (
        "asks_other_customer" in (_u(c).get("safety") or []) or c.y("wants_data_deleted", 0.6)
        or any(_req(c, k) for k in ("order_status", "forget_me", "change_order_address", "exchange", "return", "cancel"))
        or _asks(c, "order_status", "delivery_address"))),
    "policy_gap": _policy_gap_t,
    "hypothetical_refund_ask": lambda c: bool(c.asking and not _req(c, "return") and not _req(c, "exchange")),
    "update_money_words": lambda c: bool(c.s.updates_done and _asks(c, "refund_amount")),
    "has_qmark": lambda c: bool(c.asking),
    "attr_ask": _attr_ask_t,
    "warranty_ask": lambda c: bool(_asks(c, "warranty") and (c.mentioned or c.s.focus)),
    "cart_total_ask": lambda c: bool(c.s.cart and _asks(c, "cart_total")),
    "cod_ask": lambda c: _asks(c, "cod"),
    "policy_peek": lambda c: bool(c.asking and _sales_turn(c) and c.it != "place_order"),
    "competitor_words": lambda c: c.y("mentions_competitor", 0.5),
    "quality_words": lambda c: _asks(c, "quality"),
    "adding_cart": lambda c: bool(_req(c, "add_to_cart") and c.s.cart and "cart_total" not in c.goals),
    "wants": _wants_t,
    # 4.4: cờ "khách đang hỏi" của cả câu không xóa quyền của yêu cầu đặt hàng hợp lệ trong cùng câu ("chốt A; có COD không?");
    # câu hỏi độc lập vẫn do các dòng trả lời riêng xử lý. Điều kiện ("nếu COD thì đặt") do request_state chặn.
    "order_trigger": lambda c: bool(_wants_t(c) or _pending_t(c)),
    "address_change_request": lambda c: bool(getattr(c.s, "reqs", None) and c.s.reqs.has_active("change_order_address")
                                             and not getattr(c.s, "proxy_caller", False)),
    "slot_address": lambda c: bool(c.slots.get("address")) and not getattr(c.s, "_addr_dispatched", False),
    "buy_intent": lambda c: bool(getattr(c.s, "reqs", None) and (c.s.reqs.has_active("place_order") or c.s.reqs.done_orders_ok())),
    "wants_asking_quoted": lambda c: bool(_wants_t(c) and c.asking and "quote" in c.goals),
    "asks_price_turn": lambda c: bool(_sales_turn(c) and "recommend" not in c.goals and _asks_price_t(c)),
    "gift_turn": lambda c: bool(c.gift_q and _sales_turn(c) and c.facts.get("quote")),
}


def target_safety(c):
    """K04 (ARCH=target): chính sách an toàn BẰNG CODE trên tín hiệu có kiểu, chạy trước bảng. Thứ tự ưu tiên:
    1. bảo vệ dữ liệu khách khác (kể cả người tự xưng người nhà) — trước mọi handoff, để chuyển máy không là đường vòng lộ dữ liệu;
    2. xóa dữ liệu của chính khách — kiểm quyền danh tính (identity_permissions.may_forget), không có quyền thì từ chối;
    3. câu y tế → chuyển chuyên viên; khách ĐÒI người thật (request handoff có căn cứ) → chuyển;
    4. out_of_scope KHÔNG kèm tín hiệu chuyển (y tế / đòi người thật) → không chuyển máy: viết lại thành câu thường để bảng trả
       lời (no_info / chính sách); tiêm lệnh không đổi giá hay quyền (giá vẫn lấy từ tool).
    → "stop" nếu đã xử lý xong lượt; None để bảng chạy tiếp."""
    s, u = c.s, _u(c)
    safety = set(u.get("safety") or [])
    reqs = set(u.get("requests") or [])
    proxy = bool(getattr(s, "proxy_caller", False))
    if "asks_other_customer" in safety or PREDS_TARGET["proxy_info_ask"](c):
        s._why("safety_policy", "dữ liệu khách khác / người tự xưng người nhà → từ chối, không chuyển máy")
        return h_refuse_other_customer(c, None)
    if c.y("wants_data_deleted", 0.6) and "forget_me" not in reqs:
        # xóa dữ liệu là thao tác GHI không đảo ngược: như mọi thao tác ghi, cần yêu cầu forget_me có căn cứ trong câu.
        # Chỉ có cờ → không xóa (tắt cờ để dòng R03 của bảng không xóa thay), trả lời / hỏi rõ theo các dòng còn lại.
        c.fl = {**c.fl, "wants_data_deleted": 0.0}
        s._why("safety_policy", "cờ đòi xóa dữ liệu nhưng không có yêu cầu forget_me có căn cứ → không xóa")
    elif "forget_me" in reqs:
        from harness.identity_permissions import may_forget
        if proxy or not may_forget(s):
            s._why("safety_policy", "đòi xóa dữ liệu nhưng danh tính kênh không đủ quyền → từ chối")
            return h_refuse_other_customer(c, None)
        s._why("safety_policy", "xóa dữ liệu của chính khách (danh tính kênh)")
        return h_forget_customer(c, None)
    if c.y("medical_question", 0.5) or "medical_question" in safety:
        c.fl = {**c.fl, "medical_question": 1.0}
        s._why("safety_policy", "câu y tế → chuyển chuyên viên")
        return h_handoff_scope(c, None)
    if "handoff" in reqs:
        s._why("safety_policy", "khách đòi gặp nhân viên (yêu cầu có căn cứ)")
        return h_handoff_scope(c, None)
    if c.it == "out_of_scope":
        c.it = "greeting_or_other"
        s._why("safety_policy", "out_of_scope không kèm yêu cầu chuyển / câu y tế → không chuyển máy")
    if "prompt_injection" in safety:
        s._why("safety_policy", "câu có lệnh giả hệ thống: không đổi giá / quyền; giá vẫn từ tool")
    return None


# ----------------------------------------------------------------------------------------------- handler
# Trả "stop" để kết thúc lượt ngay (như return trong _plan cũ). Thân hàm chép đúng code cũ.

def h_ask_identity(c, row):                                                             # L726–727
    c.goals = ["ask_identity"]
    return "stop"


def h_opening_returning(c, row):                                                        # L758–767
    A, s = _A(), c.s
    last = s.brief["last_session"]
    need = {k: s.carried[k] for k in ("room_area_m2", "baby_age", "household_size") if s.carried.get(k)}
    blocker = s.known.get("blocker")
    # F3 (13/11, duyệt, chỉ B2): khách quay lại mà lượt đầu đã hỏi / yêu cầu cụ thể → không thêm câu hỏi "đã trao đổi với người nhà
    # chưa" (câu hỏi thừa, làm vượt giới hạn số câu hỏi); vẫn chào và nhắc lần tư vấn trước.
    u = getattr(s, "u_turn", None) or {}
    suppressed = bool(blocker) and settings.planner_variant == "b2_jev" and bool(u.get("asks") or u.get("request_items"))
    # TA1 (14/11, duyệt: theo đối tượng, không regex): lượt đầu khách quay lại NÊU một mẫu khác mẫu đã tư vấn (parser catalog,
    # s.turn_mentioned — cùng nguồn F2) → vẫn nhắc đúng lịch sử (ngày + mẫu đã tư vấn), bỏ giá cũ của mẫu kia và câu hỏi rào cản;
    # mẫu đang bàn đã chuyển sang mẫu khách nêu (_prepare_target), planner_b2 đọc giá mẫu đó bằng tool (opening_focus).
    switched = None
    if settings.planner_variant == "b2_jev" and c.prev_focus:
        par = lambda x: (A.mt._parent(x)[0] or {}).get("sku") or x
        named = list(dict.fromkeys(par(x) for x in (getattr(s, "turn_mentioned", None) or []) if x))
        # chỉ khi khách nêu ĐÚNG MỘT mẫu và mẫu đó khác mẫu đã tư vấn; nêu nhiều mẫu → không tự báo giá mẫu nào (không đoán)
        if len(named) == 1 and par(c.prev_focus) not in named:
            switched = named[0]
    c.opening_switch = switched
    c.facts["brief"] = {"product_name": A.product_name(c.prev_focus),
                        "price_quoted_vnd": None if switched else s.known.get("price_quoted_vnd"),
                        "last_date_ddmm": A._ddmm(last["date"]) if last else None,
                        "blocker": None if (suppressed or switched) else blocker,
                        "need": dict(list(need.items())[:1]), "objection": s.carried.get("objection"),
                        "stale_warnings": s.brief["stale_warnings"], **({"blocker_suppressed": True} if suppressed else {}),
                        **({"focus_switched": {"from": c.prev_focus, "to": switched}} if switched else {})}
    c.goals.append("opening_returning")
    if any("KM" in w for w in s.brief["stale_warnings"]):
        c.goals.append("stale_promo")


def h_add_goal(c, row):
    c.goals += list(row["do"].get("goals") or [])


def h_forget_customer(c, row):                                                          # L771–775
    s, cust = c.s, c.s.customer or {}
    if cust.get("customer_id"):
        s.mem.forget_customer(cust["customer_id"])
    s.known, s.carried, s.deleted, s._deleted_turn = {}, {}, True, s.turn_no
    c.facts["deleted"] = True; c.goals.append("data_deleted")
    return "stop"


def h_handoff_scope(c, row):                                                            # L777–781
    s = c.s
    if c.y("asks_internal_cost", 0.6) and "refuse_internal" not in c.goals:
        # 10/11 (V3-093/097): R04 là terminal nên R05 (từ chối giá nội bộ) không bao giờ chạy khi router xếp out_of_scope.
        # Chuyển máy không thay cho lời từ chối: khách đòi giá nhập/giá sàn vẫn phải nghe rõ là thông tin nội bộ.
        c.goals.append("refuse_internal")
    c.facts["handoff"] = s._handoff(c.text, "cau_hoi_y_te" if c.y("medical_question", 0.5) else "khach_yeu_cau_gap_nguoi")
    s.open_questions.append(s._record_view(c.text)[:200])   # sau brief: lượt nhạy cảm đã được đánh dấu
    c.goals.append("handoff"); s.outcome = "chuyen_may"
    return "stop"


def h_refuse_other_customer(c, row):                                                    # L785–788
    s = c.s
    s._why("privacy_refuse", "khách xin thông tin của khách khác")
    s.privacy_refused = True
    c.goals.append("refuse_other_customer")
    return "stop"


def h_policy_gap(c, row):                                                               # L791–796
    s, gap = c.s, c.memo["gap"]
    s._why("policy_gap", gap["topic"])
    s.policy_gap = gap
    c.facts["unknown_topic"], c.facts["policy"] = gap["topic"], gap["policy"]
    c.goals.append("no_info")
    s.open_questions.append(s._record_view(c.text)[:200])
    return "stop"


def h_rewrite_intent(c, row):                                                           # L797–801
    args = row["do"].get("args") or {}
    if args.get("why"):
        c.s._why(*args["why"])
    c.it = args["intent"]


def h_update_address_return(c, row):                                                    # L802–803
    c.goals = c.goals + c.s._update_address(c.slots["address"], c.facts)
    return "stop"


def h_change_order_address(c, row):                                                     # T01 (đích, 11/11)
    """Yêu cầu đổi địa chỉ đơn có căn cứ → executor riêng (mọi đơn của khách, kể cả đơn phiên trước), trước chính sách đổi/trả.
    Không terminal: các dòng sau vẫn trả lời câu hỏi độc lập; dấu đã xử lý (s._addr_dispatched) chỉ để điều phối / trace, không
    cấp quyền — R09/R10/R29 không chạy lại trên cùng địa chỉ, _plan_order_change_target không đi qua hạn đổi trả."""
    s = c.s
    g = s._plan_address_change_target(c.text, c.facts, c.slots.get("address"))
    if g is None:
        return None
    c.memo["address_dispatched"] = True
    s._why("address_change_dispatch", ",".join(g))
    c.goals += g


def h_order_change(c, row):                                                             # L804–811
    s = c.s
    s._why("order_change")
    g = s._plan_order_change(c.text, c.facts)
    if g != ["WINDOW_PASSED"]:
        c.goals = c.goals + g
        return "stop"
    if not s.window_told:
        s.window_told = True; c.goals.append("exchange_window_passed")
    c.it = "product_inquiry"


def h_order_status(c, row):                                                             # L812–815
    c.s._why("order_status")
    c.goals += c.s._order_status(c.facts)
    return "stop"


def h_order_updated_note(c, row):                                                       # L816–817
    c.facts["update"] = list(c.s.updates_done.values())[-1]; c.goals.append("order_updated")


def _resolved_order(c, orders):
    """Đơn mà câu khách nói tới (đích): target O# của yêu cầu trong lượt, hoặc khách có ĐÚNG một đơn. Nhiều đơn mà không rõ →
    None (không lấy đơn mới nhất)."""
    s = c.s
    for it in _u(c).get("request_items") or (c.s.u_turn or {}).get("request_items") or []:
        t = s.reqs.refmap.get(it.get("target_ref")) if it.get("target_ref") else None
        if t and t.get("type") == "order":
            return next((o for o in orders if o.get("order_id") == t["order_id"]), None)
    return orders[0] if len(orders) == 1 else None


def h_policy_answer(c, row):                                                            # L819–826
    A, s = _A(), c.s
    order_date = None
    about_order = bool(_u(c).get("refs", {}).get("existing_order")) if c.u is not None else \
        bool(re.search(r"\b(don (hang|cu|truoc)|da mua|mua (hom|tu|thang|tuan|dot))\b", c.f))
    if about_order and c.u is not None:
        # 5.1: ngày tạo của ĐÚNG đơn đã resolve (không past[-1] khi có nhiều đơn) → truy hồi đúng phiên bản chính sách
        o = _resolved_order(c, s._customer_orders())
        order_date = (o.get("created_on") or o.get("date")) if o else None
        if o and order_date and _asks(c, "return_policy"):
            from harness.planner_policy import exchange_window
            d = exchange_window(o, s.today)
            c.facts["exchange_policy"] = d
            c.facts["exchange_window"] = {"order_id": o["order_id"], "created_ddmm": A._ddmm(order_date), "days": d["days"],
                                          "version": d["version"], "action": None}
            c.goals.append("exchange_window_info")
    elif about_order:
        past = s._customer_orders()
        order_date = (past[-1].get("created_on") or past[-1].get("date")) if past else None
    hits = A.knowledge.search(c.text, k=2, order_date=order_date)
    c.facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
    c.goals.append("policy_answer" if hits else "no_info")
    s._why("policy", "có tài liệu" if hits else "không có tài liệu")


def h_attr_check(c, row):                                                               # L829–836
    A, s, terms = _A(), c.s, c.memo["terms"]
    specific = [t for t in terms if t in ("fda", "iso", "ce", "rohs") or t.startswith("tieu chuan")] or terms
    par = A.mt._parent((c.mentioned or [s.focus])[-1])[0] if (c.mentioned or s.focus) else None
    known_txt = A.fold(str((par or {}).get("attributes", {}))) + " " + " ".join(
        A.fold(h["text"]) for h in A.knowledge.search(c.text, k=3))
    missing = [t for t in specific if not re.search(rf"\b{re.escape(t)}\b", known_txt)]
    if missing:
        c.goals.append("no_info"); c.facts["unknown_topic"] = missing[0]
        s._why("attr_unknown", missing[0])


def h_warranty_fact(c, row):                                                            # L838–840
    A, s = _A(), c.s
    par = A.mt._parent((c.mentioned or [s.focus])[-1])[0]
    if par and par["attributes"].get("warranty_months"):
        c.facts["product_warranty"] = {"product": par["name"], "warranty_months": par["attributes"]["warranty_months"]}


def h_recommend(c, row):                                                                # L844–855
    s = c.s
    rec = s._recommend(c.text)
    if rec == "ASK_NEED":
        c.goals.append("ask_need")
        c.facts["need_slots_missing"] = [k for k in ("has_children", "budget_vnd", "room_area_m2") if k not in s.known]
        rec = None
    elif rec and rec != s.focus:
        old = s.focus
        s.focus, s.focus_by = rec, "recommend"
        c.facts["quote"] = s._quote(s._resolve_variant(rec, c.text), "advised"); c.goals.append("recommend")
        if old:
            c.facts["alternative"] = s._quote(old, "alternative")
    if not rec and s.focus is None and "ask_need" not in c.goals and c.it in ("product_inquiry", "price_promo"):
        c.goals += s._ask_prior_contact(c.f) or ["ask_product"]


def h_quote(c, row):                                                                    # L859–892
    A, s, facts, goals, text = _A(), c.s, c.facts, c.goals, c.text
    ask_size_after = False
    target = (c.alt or c.mentioned[-1]) if c.compare else s.focus
    if target and not c.compare and s._price_depends_on_size(target, text):
        if not s.size_asked:
            s.size_asked = True
            if s._promo_depends_on_size(target):
                goals.append("ask_size_for_price"); target = None
            else:
                facts["size_note"] = "giá này cho size thường; size lớn có phụ thu"
                ask_size_after = True
        else:
            facts["size_note"] = "giá này cho size thường; size lớn có phụ thu và không áp một số khuyến mãi"
    if target:
        q = s._quote(s._resolve_variant(target, text), "alternative" if c.compare else "advised")
        if q.get("discontinued") and q.get("successor_sku"):
            facts["discontinued_name"], facts["successor_name"] = q["name"], A.product_name(q["successor_sku"])
            goals.append("discontinued")
            if not c.compare:
                s.focus = q["successor_sku"]
            q = s._quote(s._resolve_variant(q["successor_sku"], text), "advised")
        if c.compare:
            facts["alternative"] = q; goals.append("alternative_quote")
        else:
            facts["quote"] = q
            if q.get("in_stock") is False:
                goals.append("out_of_stock"); facts["restock_expected"] = q.get("restock_expected")
            else:
                goals.append("quote")
            if ask_size_after:
                goals.append("ask_size_for_price")
            if c.u is not None:
                _price_claim_target(c, q)
            else:
                claimed = [v for v in c.slots.get("claimed_prices", []) if v != q.get("final_price_vnd")]
                if claimed and q.get("expired_promos"):
                    facts["claimed_price_vnd"] = claimed[0]; goals.append("explain_price_change")


def _price_claim_target(c, q):
    """5.2 (đích): khách nhắc một mức giá khác giá hiện tại. Chỉ nói 'đó là giá khi còn KM, KM đã hết' khi có PROVENANCE: một báo
    giá trước đó của shop (bộ nhớ báo giá các phiên + báo giá trong cuộc) cho CÙNG sản phẩm (cùng biến thể nếu cả hai là biến
    thể), đúng mức giá khách nhắc, kèm mã KM — và tool hiện tại xác nhận chính mã đó đã hết (expired_promos). Không đủ căn cứ →
    nêu giá hiện tại và nói chưa đối chiếu được mức giá khách nhắc (không bịa nguyên nhân). expired_promos đơn lẻ hoặc chênh giá
    đơn lẻ không đủ."""
    A, s, facts = _A(), c.s, c.facts
    from harness.request_state import _parent as par, _is_variant
    cur = q.get("final_price_vnd")
    said = list(c.slots.get("claimed_prices") or [])
    if isinstance(c.slots.get("competitor_price_vnd"), int):
        said.append(c.slots["competitor_price_vnd"])        # giá khách nói "bên Zalo/FB báo" có thể là báo giá cũ của chính shop
    said = [v for v in dict.fromkeys(said) if v and v != cur]
    if not said:
        return
    history = [{"sku": x.get("sku"), "final_price_vnd": x.get("final_price_vnd"), "promo_code": x.get("promo_code"),
                "promo_end": x.get("promo_end"), "quoted_on": x.get("quoted_on")} for x in s.prev_quotes or []]
    for tc in getattr(s, "call_tool_log", []) or []:
        r, a = tc.get("result") or {}, tc.get("args") or {}
        if tc.get("name") == "pricing.get_quote" and isinstance(r, dict) and r.get("final_price_vnd") and not a.get("basket_skus"):
            codes = [x.get("promo_code") for x in r.get("applied_promos") or [] if x.get("promo_code") not in A.STACKABLE_SKIP]
            history.append({"sku": a.get("sku"), "final_price_vnd": r["final_price_vnd"], "promo_code": codes[0] if codes else None,
                            "promo_end": None, "quoted_on": None})
    expired = set(q.get("expired_promos") or [])
    for v in said:
        for h in history:
            if h["final_price_vnd"] != v or not h["promo_code"] or not h["sku"] or par(h["sku"]) != par(q["sku"]):
                continue
            if _is_variant(h["sku"]) and _is_variant(q["sku"]) and h["sku"] != q["sku"]:
                continue
            if h["promo_code"] not in expired:
                continue
            pr = next((x for x in A.mt.PROMOS if x["promo_code"] == h["promo_code"]), {})
            facts["price_change"] = {"promo_name": pr.get("name") or h["promo_code"], "promo_end_ddmm": A._ddmm(pr["end"]) if pr.get("end") else None,
                                     "promo_code": h["promo_code"], "product": q.get("name")}
            c.goals.append("explain_promo_expired")
            s._why("price_claim", f"{v} khớp báo giá cũ {h['sku']} kèm {h['promo_code']}, tool xác nhận đã hết")
            return
    facts["price_claim"] = {"product": q.get("name")}
    c.goals.append("price_claim_unverified")
    s._why("price_claim", "giá khách nhắc không khớp báo giá cũ có KM đã hết của cùng sản phẩm → không giải thích nguyên nhân")


def h_budget_fit(c, row):                                                               # L896–904
    s, facts = c.s, c.facts
    q = facts.get("quote") or s._quote(s._resolve_variant(s.focus, c.text), "advised")
    if q.get("final_price_vnd"):
        facts["quote"], b = q, c.slots["budget_vnd"]
        facts["budget_fit"] = {"budget_vnd": b, "final_price_vnd": q["final_price_vnd"],
                               "within_budget": q["final_price_vnd"] <= b}
        if "quote" not in c.goals and "out_of_stock" not in c.goals:
            c.goals.append("quote")
        c.goals.append("budget_fit")
        s._why("budget_fit", f"ngân sách {b} so với giá {q['final_price_vnd']}")


def h_gift_status(c, row):                                                              # L906–919
    A, s, facts = _A(), c.s, c.facts
    q = facts["quote"]
    par = A.mt._parent(q["sku"])[0]
    psku = par["sku"] if par else q["sku"]
    gifts = [x for x in A.mt.PROMOS if x.get("type") == "gift" and psku in (x.get("applies_to") or [])]
    if gifts:
        active = [x for x in gifts if x["promo_code"] in (q.get("promo_codes") or [])]
        g0 = active[0] if active else max(gifts, key=lambda x: x["end"])
    if gifts and active and "quote" in c.goals and q.get("promo_names"):
        gifts = []
    if gifts:
        facts["gift"] = {"product": q["name"], "gift_name": A.product_name(g0["gift_sku"]), "promo_name": g0["name"],
                         "active": bool(active), "end_ddmm": A._ddmm(g0["end"])}
        c.goals.append("gift_status")
        s._why("gift_status", f"{g0['promo_code']} {'còn' if active else 'hết'} hiệu lực")


def h_cart_total(c, row):                                                               # L921, L938, L940
    c.facts["cart"] = c.s._cart_quote(c.text); c.goals.append("cart_total")


def h_cod_check(c, row):                                                                # L923–925
    s, facts = c.s, c.facts
    tot = (facts.get("cart") or s._cart_quote(c.text) if s.cart else {}).get("total_vnd") if s.cart \
        else (facts.get("quote") or {}).get("final_price_vnd")
    facts["cod_total_vnd"] = tot
    c.goals.append("cod_limit" if tot and tot > 10_000_000 else "cod_ok")


def h_policy_peek(c, row):                                                              # L927–929
    hits = _A().knowledge.search(c.text, k=2)
    if hits:
        c.facts.setdefault("policy", [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits])


def h_mark_buy_intent(c, row):                                                          # L942–944
    s = c.s
    s.buy_intent = True
    if not s.cart and s.focus:
        s._cart_add(s.focus)


def h_update_address(c, row):                                                           # L947–948
    c.goals += c.s._update_address(c.slots["address"], c.facts)


def h_stale_quote(c, row):                                                              # L953–955
    s = c.s
    s.price_change_told = True
    c.facts["quote"] = c.facts.get("quote") or s._quote(s._resolve_variant(s.focus, c.text), "advised")
    c.goals += ["stale_promo", "quote", "confirm_new_price"]


def h_place_order(c, row):                                                              # L957–958
    s = c.s
    s._why("order_create", "đồng ý mua" if _wants(c) else "bổ sung thông tin đơn")
    c.goals += s._plan_order(c.text, c.facts)


def h_stale_requote(c, row):                                                            # L962–965
    s = c.s
    s.price_change_told = True
    if s.focus and "quote" not in c.facts:
        c.facts["quote"] = s._quote(s._resolve_variant(s.focus, c.text), "advised")
    c.goals.append("quote")


def h_callback(c, row):                                                                 # L966–967
    c.goals += c.s._plan_callback(c.slots["callback_requested"], c.facts)


def h_defer_ack(c, row):                                                                # L969
    c.goals.append("defer_ack"); c.s.outcome = c.s.outcome or "hen_goi_lai"


def h_fallback(c, row):                                                                 # L971–986
    A, s = _A(), c.s
    if c.u is not None:     # đích: câu rè / mơ hồ và câu chào kết theo bộ hiểu; không có planner LLM dự phòng
        garbled = _u(c).get("ambiguity") == "needs_clarification"
        closing = bool(_u(c).get("refs", {}).get("closing"))
        prior = s._ask_prior_contact(c.f, typed=bool(_u(c).get("refs", {}).get("previous_contact"))) if s.turn_no == 1 else []
        llm = []
    else:
        garbled = s.input_mode == "asr_transcript" and c.route.get("confidence", 1) < 0.6
        closing = bool(A.CLOSING_RX.search(c.f))
        prior = s._ask_prior_contact(c.f) if s.turn_no == 1 else []
        llm = [] if prior or settings.planner_backend == "rules" or (s.turn_no == 1 and not c.asking) \
            else s._llm_fallback(c.text, c.facts)
    if prior or llm:
        c.goals += prior or llm
    elif s.turn_no == 1:
        c.goals.append("greet")
    elif not c.slots and not c.mentioned and not closing and (c.asking or garbled) and s.repeat_asked < 2:
        s.repeat_asked += 1
        c.goals.append("ask_repeat")
    else:
        c.goals.append("closing")
    if not llm:
        s._why("fallback", c.goals[-1])


# ---- D51: handler cho case mới

def h_ask_repeat(c, row):                                                               # N01
    c.s.repeat_asked += 1
    c.s._why("asr_noisy", "câu ASR bị rè / ngắt, xin khách nói lại trước")
    c.goals.append("ask_repeat")
    return "stop"


def h_refund_amount(c, row):                                                            # N02
    """Số tiền hoàn chỉ lấy từ kết quả tool: order.update(return) trong cuộc này, hoặc giá đơn trong order.status (cuộc sau).
    Không tìm được số → đi tiếp các dòng khác (không dừng)."""
    s = c.s
    # holdout mục 1 (duyệt 12/11): kết quả ĐỔI hàng (exchange_product / exchange_size) cũng là nguồn tiền hoàn chênh lệch —
    # trước đây chỉ đọc `return` nên hỏi tiền chênh sau khi đổi lại rơi về "giá cả đơn nếu trả hàng" (sai đối tượng).
    acts = RETURN_LIKE_ACTIONS if c.u is not None else ("return",)     # R0 (đường cũ, đóng băng) giữ nguyên hành vi
    upd = [(k, v) for k, v in s.updates_done.items() if k[1] in acts and (c.u is not None or v.get("refund_vnd"))]
    if upd:
        k, v = upd[-1]
        if k[1] != "return" and not v.get("refund_vnd") and v.get("extra_payment_vnd"):
            c.facts["update"] = v                       # đổi sang mẫu đắt hơn: khách bù thêm, không có tiền hoàn
            c.goals.append("order_updated")
            s._why("refund_amount", f"đổi hàng {k[1]}: khách bù thêm, không có tiền hoàn")
            return "stop"
        if not v.get("refund_vnd"):
            return None
        c.facts["refund"] = {"order_id": k[0], "refund_vnd": v["refund_vnd"], "refund_days": v.get("refund_days"),
                             "basis": "return_request" if k[1] == "return" else "exchange_difference"}
        src = f"order.update({k[1]}) trong cuộc"
    else:
        orders = s._customer_orders()
        o = next((x for x in reversed(orders) if x.get("order_id") == s.known.get("order_id")), orders[-1] if orders else None)
        amount = o and (o.get("price_vnd") or o.get("total_vnd"))
        if not amount:
            return None
        # G1: chưa có yêu cầu trả trong cuộc → đây chỉ là số tiền dự kiến (giá đơn), không phải khoản đã/sẽ hoàn đã tiếp nhận
        c.facts["refund"] = {"order_id": o["order_id"], "refund_vnd": amount, "basis": "order_price",
                             "product": _A().product_name(o["sku"]) if o.get("sku") else None}
        src = "order.status (giá đơn đã trả lại)"
    c.goals.append("refund_amount")
    s._why("refund_amount", src)
    return "stop"


def h_cancel_request(c, row):                                                           # E03 — mock không có action hủy
    s = c.s
    s.open_questions.append(s._record_view(c.text)[:200])
    c.facts["handoff"] = s._handoff(c.text, "khac")
    c.goals.append("cancel_handoff"); s.outcome = "chuyen_may"
    s._why("cancel_request", "không có thao tác hủy đơn, chuyển nhân viên")
    return "stop"


def h_defer_close(c, row):                                                              # E12, E15
    c.it = "callback"
    c.goals.append("defer_ack"); c.s.outcome = c.s.outcome or "hen_goi_lai"
    c.s._why("defer_close", (row.get("do").get("args") or {}).get("why", "khách hẹn chốt sau"))


def h_callback_from_text(c, row):                                                       # N04
    w = c.memo["callback_w"]
    c.goals += c.s._plan_callback(f"{w[0]}T{w[1] or '09:00'}", c.facts)
    c.s._why("callback_from_text", "khách hẹn shop gọi lại kèm thời điểm")


def h_handoff_reason(c, row):                                                           # E07
    s, reason = c.s, (row["do"].get("args") or {}).get("reason", "khac")
    c.facts["handoff"] = s._handoff(c.text, reason)
    s.open_questions.append(s._record_view(c.text)[:200])
    c.goals.append("handoff"); s.outcome = "chuyen_may"
    s._why("handoff_reason", reason)
    return "stop"


HANDLERS = {
    "ask_repeat": h_ask_repeat, "refund_amount": h_refund_amount, "cancel_request": h_cancel_request,
    "defer_close": h_defer_close, "callback_from_text": h_callback_from_text, "handoff_reason": h_handoff_reason,
    "ask_identity": h_ask_identity, "opening_returning": h_opening_returning, "add_goal": h_add_goal,
    "forget_customer": h_forget_customer, "handoff_scope": h_handoff_scope, "refuse_other_customer": h_refuse_other_customer,
    "policy_gap": h_policy_gap, "rewrite_intent": h_rewrite_intent, "update_address_return": h_update_address_return,
    "order_change": h_order_change, "order_status": h_order_status, "order_updated_note": h_order_updated_note,
    "policy_answer": h_policy_answer, "attr_check": h_attr_check, "warranty_fact": h_warranty_fact, "recommend": h_recommend,
    "quote": h_quote, "budget_fit": h_budget_fit, "gift_status": h_gift_status, "cart_total": h_cart_total,
    "cod_check": h_cod_check, "policy_peek": h_policy_peek, "mark_buy_intent": h_mark_buy_intent,
    "update_address": h_update_address, "stale_quote": h_stale_quote, "place_order": h_place_order,
    "change_order_address": h_change_order_address,
    "stale_requote": h_stale_requote, "callback": h_callback, "defer_ack": h_defer_ack, "fallback": h_fallback,
}


# ----------------------------------------------------------------------------------------------- bộ máy

def _prepare_pre(c):
    """Giai đoạn 1 của bước chuẩn bị (L720–725): chạy TRƯỚC các dòng stage=pre (R00 hỏi danh tính)."""
    s = c.s
    s.plan_why, s.llm_plan = [], None
    for k, v in c.slots.items():
        if k not in ("self_name", "claimed_prices"):
            s.known[k] = v
            if hasattr(s, "known_src"):
                s.known_src[k] = f"customer:t{s.turn_no}"      # nguồn giá trị: khách nói ở lượt này (5.4 / 9.2)


def _prepare(c):
    """Giai đoạn 2 (L728–756): sản phẩm được nhắc, focus, giỏ, asking/takes/compare."""
    A, s, text = _A(), c.s, c.text
    c.f = f = A.fold(text)
    if c.u is not None:
        return _prepare_target(c)
    mentioned = A.find_products(text)
    c.gift_q = bool(A.GIFT_Q_RX.search(f))
    if c.gift_q:
        mentioned = [x for x in mentioned if x not in A.GIFT_SKUS]
    elif re.search(r"\bmang loc\b", f):
        base = mentioned or ([s.focus] if s.focus else [])
        mentioned = [A.FILTER_OF.get(A.mt._parent(x)[0]["sku"], x) for x in base]
    c.mentioned = mentioned
    c.alt = None if mentioned else (A.find_by_model_token(text, s.focus) if s.focus else None)
    sents = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]
    last = A.fold(sents[-1]) if sents else f
    asking = sents[-1].rstrip().endswith("?") if sents else False
    c.asking = asking or (bool(re.search(r"\b(bao nhieu|duoc khong|the nao)\b", last))
                          and not re.search(r"\b(len don|chot|dat hang)\b", last))
    c.takes = takes = bool(re.search(r"\b(lay|them|chot|mua (luon|them|ca|cho|nhe|nha))\b", f))
    u = c.route.get("understanding")
    if u is not None:      # kiến trúc đích (11/11): "khách đang hỏi" / "khách lấy hàng" do bộ hiểu thống nhất quyết, không theo regex
        c.asking = bool(u.get("asks_question"))
        c.takes = takes = "place_order" in (u.get("requests") or [])
    c.compare = bool(c.alt) or bool(mentioned and s.focus and A.mt._parent(mentioned[-1])[0]["sku"] != A.mt._parent(s.focus)[0]["sku"]
                                    and re.search(r"\bcon\b", f) and not takes)
    c.prev_focus = s.focus
    c.new_focus = None
    if mentioned and not c.compare:
        c.new_focus = mentioned[-1]
        s.focus, s.focus_by = c.new_focus, "customer"
    if settings.planner_selector == "rules" and takes and mentioned and not c.compare:
        for m_ in mentioned:
            s._cart_add(m_)
    if settings.planner_selector == "rules" and re.search(r"lay (du|ca|het|tat ca)|ca hai|ca 2|lay du", f):
        for d in s.discussed:
            s._cart_add(d)


def _prepare_target(c):
    """Bước chuẩn bị trên cấu hình đích: sản phẩm được nhắc (parser catalog), focus, giỏ, asking / takes / compare / quà / lấy cả
    — đọc từ bộ hiểu có kiểu, không từ regex đoán ý. Nhắc một mẫu khác chỉ đổi mẫu ĐANG BÀN (focus); giỏ / lựa chọn chỉ đổi khi
    khách có yêu cầu đặt / thêm có căn cứ."""
    A, s, text, f, u = _A(), c.s, c.text, c.f, c.u
    asks = set(u.get("asks") or [])
    reqs = set(u.get("requests") or [])
    mentioned = A.find_products(text)                                   # parser catalog (tên / mã mẫu)
    c.gift_q = "gift" in asks
    if c.gift_q:
        mentioned = [x for x in mentioned if x not in A.GIFT_SKUS]
    else:
        # 13/11 (duyệt): chuẩn hóa mã phụ kiện bằng CÙNG hàm đã dựng ứng viên cho DeepSeek (agent.normalize_accessories):
        # "màng lọc … <máy>" là phụ kiện của máy đó, không phải máy; "màng lọc" không gắn tên máy → của máy duy nhất / mẫu đang bàn
        mentioned, c.accessory_norm = A.normalize_accessories(text, mentioned, s.focus)
    c.mentioned = mentioned
    c.alt = None if mentioned else (A.find_by_model_token(text, s.focus) if s.focus else None)
    c.asking = bool(u.get("asks_question"))
    c.takes = takes = bool(reqs & {"place_order", "add_to_cart"})
    c.compare = bool(c.alt) or bool(mentioned and s.focus and A.mt._parent(mentioned[-1])[0]["sku"] != A.mt._parent(s.focus)[0]["sku"]
                                    and "compare" in asks and not takes)
    c.prev_focus = s.focus
    c.new_focus = None
    # 13/11 (B2 S4): ghi lại giỏ trước bước chuẩn bị + SKU được yêu cầu thêm — chỉ là thuộc tính quan sát cho planner B2 (giỏ vẫn
    # chỉ đổi ở đây, một chủ); không đổi hành vi B1 / B3.
    c.cart_before, c.cart_touched = list(s.cart), []

    def add(sku):
        c.cart_touched.append(sku)
        s._cart_add(sku)
    if mentioned and not c.compare:
        c.new_focus = mentioned[-1]
        s.focus, s.focus_by = c.new_focus, "customer"
    # 13/11 (duyệt): MỘT nơi cập nhật giỏ, MỘT nguồn đối tượng cho mỗi lượt (trước đây nhánh "sản phẩm được nhắc" và nhánh
    # "ref của bộ hiểu" cùng thêm vào giỏ → cộng dồn lựa chọn mâu thuẫn, vd màng lọc + cả máy). Phụ kiện không được thêm chỉ vì
    # được nhắc tên: thiếu căn cứ trong câu yêu cầu thì hỏi rõ (goal ask_accessory_intent), không thêm.
    c.cart_source, c.cart_unclear = None, []
    if takes:
        picks, c.cart_source, c.cart_unclear = _cart_picks(c, mentioned)
        for sku in picks:
            add(sku)
        if c.cart_unclear:
            c.facts["accessory_ask"] = {"products": [A.product_name(x) for x in c.cart_unclear]}
            if "ask_accessory_intent" not in c.goals:
                c.goals.append("ask_accessory_intent")


def _cart_picks(c, mentioned):
    """Đối tượng thêm vào giỏ của lượt từ ĐÚNG MỘT nguồn (thứ tự ưu tiên):
      1. ref của bộ hiểu: "ALL" → các mẫu đã bàn; "CART" → không thêm (yêu cầu nhắm giỏ hiện có); P# → sản phẩm của ref
         (ứng viên đã chuẩn hóa phụ kiện, nên P# của "màng lọc … AirPure Y" là màng lọc);
      2. không có ref → sản phẩm parser thấy trong câu (đã chuẩn hóa phụ kiện), khi không phải câu so sánh.
    Phụ kiện (danh mục phụ kiện) chỉ được thêm khi có căn cứ: bộ hiểu nhắm đúng ref của nó, hoặc câu yêu cầu (evidence) nói
    "màng lọc" / tên phụ kiện, hoặc là sản phẩm duy nhất của lượt khi không có câu yêu cầu. Nhắc phụ kiện trong câu yêu cầu mà
    nguồn đã chọn không gồm nó → hỏi rõ. → (picks, nguồn, phụ kiện cần hỏi)."""
    A, s, u = _A(), c.s, c.u
    targets = list(u.get("targets") or [])
    items = [it for it in ((getattr(s, "u_turn", None) or {}).get("request_items") or []) if it.get("kind") in ("add_to_cart", "place_order")]
    ev = " ".join(A.fold(it.get("evidence") or "") for it in items).strip() if items else A.fold(c.text)   # không có bộ hiểu → cả câu
    if settings.planner_variant == "b2_jev" and (getattr(getattr(s, "reqs", None), "order_gate", None) or {}).get("why") == "target_ambiguous":
        # V42 (15/11): câu đặt không nêu món, còn nhiều đối tượng hợp lý → không thêm món theo ref model đoán vào giỏ (hỏi rõ trước)
        return [], "target_ambiguous", []
    if "ALL" in targets:
        if settings.planner_variant == "b2_jev":
            # C1 (15/11, B2): "ALL" không tự thành giỏ mua → không thêm; bước sau xin xác nhận liệt kê đúng các món (apply_order_gate)
            c.all_unconfirmed = list(dict.fromkeys(A._par(x) for x in s.discussed))
            return [], "ALL_unconfirmed", []
        return list(s.discussed), "ALL", []
    if "CART" in targets:
        return [], "CART", []
    if targets:
        picks = []
        for ref in targets:
            t = (getattr(s, "reqs", None) and s.reqs.refmap.get(ref)) or None
            if t and t.get("type") == "product":
                picks += [x for x in t.get("skus") or () if x not in picks]
        src = "target_ref"
    elif mentioned and not c.compare:
        picks, src = list(mentioned), "mentioned"
    else:
        return [], None, []

    def grounded(acc):
        if not ev:
            return len(mentioned) == 1
        return bool(A.ACC_WORD_RX.search(ev)) or any(x == acc for x in A.find_products(ev))
    unclear = []
    if src == "mentioned":
        for x in [p for p in picks if A.is_accessory(p)]:
            if not grounded(x):
                picks.remove(x); unclear.append(x)
    else:
        picked = {A._par(p) for p in picks}
        unclear = [x for x in mentioned if A.is_accessory(x) and A._par(x) not in picked and ev and grounded(x)]
    return picks, src, unclear


def _finish(c):
    """Hậu xử lý của _plan (L987–993)."""
    s = c.s
    if "no_info" in c.goals or "handoff" in c.goals:
        s.open_questions.append(s._record_view(c.text)[:200])
    s.fail_streak = s.fail_streak + 1 if "order_failed" in c.goals else 0
    # G1 (FINAL 10/11): đơn có kết quả chưa rõ → chuyển nhân viên đối soát ngay lần đầu (planner không tự đối soát/tạo lại)
    if "order_unresolved" in c.goals and "handoff" not in c.goals:
        c.facts["handoff"] = s._handoff(c.text, "loi_he_thong")      # ticket đã có thì không tạo lại (_handoff)
        c.goals.append("handoff"); s.outcome = "chuyen_may"
    if s.fail_streak >= 2 and "handoff" not in c.goals:
        c.facts["handoff"] = s._handoff(c.text, "loi_he_thong")
        c.goals = [g for g in c.goals if g != "order_failed"] + ["handoff"]; s.outcome = "chuyen_may"
    return list(dict.fromkeys(c.goals)), c.facts


def plan(s, text, slots, route, rows=None, owner=None):
    """Thay cho CallSession._plan. Ghi các dòng đã khớp vào s.table_rows (trace planner.table).

    owner (12/11, harness/planner_variants.py): chủ sở hữu tiến trình của biến thể B2/B3. None = B1 (bảng như cũ, không đổi
    hành vi). Có owner: dòng owner.owns(row) KHÔNG chạy bằng bảng; tới vị trí dòng đầu tiên của mỗi pha (owner.phase(row)) thì
    gọi owner.run(c, pha) đúng một lần. Các dòng chung (an toàn, danh tính, mở đầu, fallback…) vẫn chạy bằng bảng. Biến thể có
    owner luôn qua hậu xử lý _finish đúng một lần (quy tắc finalization: unresolved → handoff không bị mất)."""
    from harness import improve_hook
    c = Ctx(s, text, slots, route)
    s.table_rows = []
    s.semantic_plan = None
    rows = rows if rows is not None else load_rows(extra=improve_hook.planner_rows())
    _prepare_pre(c)
    if owner is not None:
        return _plan_owned(c, rows, owner)
    if settings.planner_selector != "rules":
        from harness.planner_executor import run
        _prepare(c)
        run(c)
        out = _finish(c)
        s.table_prev_goals = list(out[0])
        return out
    pre = [r for r in rows if r.get("stage") == "pre"]
    done_groups = set()
    for row in pre + [None] + [r for r in rows if r.get("stage") != "pre"]:
        if row is None:                      # hết các dòng stage=pre → giai đoạn 2 của bước chuẩn bị
            _prepare(c)
            if c.u is not None and target_safety(c) == "stop":
                s.table_rows.append("SAFETY")
                s.table_prev_goals = list(c.goals)
                return c.goals, c.facts
            continue
        g = row.get("group")
        if g and g in done_groups:
            continue
        if not matches(c, row.get("when") or {}):
            continue
        if g:
            done_groups.add(g)
        s.table_rows.append(row["id"])
        res = HANDLERS[row["do"]["handler"]](c, row)
        if row["mode"] == "terminal" or res == "stop":
            s.table_prev_goals = list(c.goals)
            return c.goals, c.facts          # như các lệnh return giữa chừng của _plan: không qua hậu xử lý
    out = _finish(c)
    s.table_prev_goals = list(out[0])
    return out


def _plan_owned(c, rows, owner):
    """Bảng với chủ sở hữu tiến trình (B2/B3). Dòng chung chạy như B1; dòng thuộc owner nhường cho owner.run theo pha."""
    s = c.s
    pre = [r for r in rows if r.get("stage") == "pre"]
    done_groups, ran = set(), []
    stopped, n_log = False, None
    post = getattr(owner, "post_stop_rows", frozenset())
    for row in pre + [None] + [r for r in rows if r.get("stage") != "pre"]:
        if row is None:
            _prepare(c)
            if c.u is not None and target_safety(c) == "stop":
                s.table_rows.append("SAFETY")
                s.table_prev_goals = list(c.goals)
                return c.goals, c.facts
            continue
        if stopped:
            # 13/11 (B2 S5): owner đã kết thúc phần sở hữu → chỉ các dòng phản hồi CHUNG trong allowlist của owner (R24a/b, R25,
            # R35) theo đúng predicate / group / thứ tự, mỗi dòng tối đa một lần. Không chạy E07 / R36 / dòng owner; không chạy
            # khi lượt đã chuyển nhân viên; R35 (hoãn) không chạy khi owner đã ghi trong lượt. Safety / danh tính đã return trước.
            if row["id"] not in post or owner.owns(row):
                continue
            if {"handoff", "cancel_handoff"} & set(c.goals):
                continue
            if row["id"] == "R35" and any(x.get("name") in ("order.create", "order.update", "schedule.callback", "handoff.transfer")
                                          for x in s.tools.log[n_log:]):
                continue
        if owner.owns(row):
            ph = owner.phase(row)
            if ph in ran:
                continue
            ran.append(ph)
            s.table_rows.append(f"{owner.name}:{ph}")
            n0 = len(s.tools.log)
            if owner.run(c, ph) == "stop":
                if not post:
                    break                            # B3: như v6 (không có dòng chung sau khi owner dừng)
                stopped, n_log = True, n0
                s.table_rows.append(f"{owner.name}:post_stop")
            continue
        g = row.get("group")
        if g and g in done_groups:
            continue
        if not matches(c, row.get("when") or {}):
            continue
        if g:
            done_groups.add(g)
        s.table_rows.append(row["id"])
        res = HANDLERS[row["do"]["handler"]](c, row)
        if row["mode"] == "terminal" or res == "stop":
            s.table_prev_goals = list(c.goals)
            return c.goals, c.facts          # dòng chung kết thúc lượt: y như B1 (không qua hậu xử lý)
    n_open = len(s.open_questions)
    out = _finish(c)
    if len(s.open_questions) > n_open and n_open and s.open_questions[-1] == s.open_questions[n_open - 1]:
        s.open_questions.pop()               # handler của owner đã ghi câu này (vd chuyển máy) → không ghi hai lần
    s.table_prev_goals = list(out[0])
    return out
