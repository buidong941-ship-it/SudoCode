"""Một cuộc gọi = CallSession. Vòng lặp mỗi lượt:

perceive → slot khách → ROUTER (Jev) quyết định intent/cờ → PLANNER gọi tool (giá/tồn/đơn chỉ từ tool) →
GENERATOR (DeepSeek) nói theo goals+facts → GUARDRAIL → EXTRACTOR (questions/claims/facts_used) → ghi BỘ NHỚ → trace.

Planner là code xác định (không để LLM tự chọn tham số tool): tham số order.create lấy từ báo giá tool vừa trả,
nên giá trong đơn luôn khớp mock của BTC. LLM chỉ lo câu chữ.
"""
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import date, datetime, timedelta

from core import log as cclog
from core.config import settings
from core.llm.generator import Generator, question_slot
from core.llm import generator as _gen_mod   # cụm 1: đọc PAYLOAD_DROPPED để ghi trace
from core.llm.router import Router
from harness import extractor, guardrails, improve_hook, knowledge, planner_table
from harness.coverage import NO_QUESTION, coverage
from harness.textnorm import find_money, fold, perceive
from harness.lexicon import rx as lexrx
from harness.tools import (ToolBox, find_by_model_token, find_products, find_variant, mention_spans, mt, product_name, public_view)

CATEGORY_WORDS = [("may loc khong khi", "gia-dung/may-loc-khong-khi"), ("may loc nuoc", "gia-dung/may-loc-nuoc"),
                  ("noi chien", "gia-dung/noi-chien"), ("quat", "gia-dung/quat"), ("giay", "thoi-trang/giay"),
                  ("ao khoac", "thoi-trang/ao"), ("may hut sua", "me-be"), ("xe day", "me-be"), ("binh sua", "me-be"),
                  ("may ham sua", "me-be"), ("ghe o to", "me-be")]
log = cclog.get("agent")
_POST_EXTRACTOR_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-extract")
_ROUTER_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-router")      # L1: PARALLEL_ROUTER=1


def _merge_agent_meta(dst, am, legacy):
    """Gộp meta phân tích câu agent (audit) vào meta extractor của lượt: ms, span bị bỏ, claim/slot bị loại theo stance,
    fallback; đường cũ còn ghi backend."""
    for key in ("ms", "dropped_spans"):
        dst[key] = int(dst.get(key, 0) or 0) + int(am.get(key, 0) or 0)
    for key in ("stance_dropped_claims", "stance_dropped_slots"):   # CONTRACT_V2: để đọc lại từng claim/slot bị loại
        if am.get(key):
            dst[key] = list(dst.get(key) or []) + list(am[key])
    if legacy and am.get("backend"):
        # kiến trúc đích: phía khách luôn là deepseek_unified; backend phân tích câu agent nằm riêng ở agent_backend
        dst["backend"] = am["backend"]
    fallbacks = [x for x in (dst.get("fallback"), am.get("fallback")) if x]
    if fallbacks:
        dst["fallback"] = " | ".join(dict.fromkeys(fallbacks))


def _timed_audit(fn, *args):
    """Chạy audit hậu kỳ trong pool, trả kèm mốc bắt đầu chạy / xong (để tách thời gian xếp hàng và thời gian audit)."""
    t0 = time.perf_counter()
    out = fn(*args)
    return out, t0, time.perf_counter()
STACKABLE_SKIP = {"COD-0", "NAM-SHIP0"}
FILTER_OF = {"SKU-AP-X": "SKU-AP-FLT-X", "SKU-AP-Y": "SKU-AP-FLT-X", "SKU-AP-PRO": "SKU-AP-FLT-P",
             "SKU-XM-4L": "SKU-XM-FLT", "SKU-XM-4P": "SKU-XM-FLT"}
ACCESSORY_CAT = "gia-dung/phu-kien"
ACC_WORD_RX = re.compile(r"\bmang loc\b")
# cụm phụ kiện ĐỨNG NGAY TRƯỚC tên máy: "màng lọc (thay thế) (cho / của / dành cho) (máy lọc không khí) <tên máy>"
ACC_BOUND_RX = re.compile(r"mang loc(?: thay the)?(?: (?:cho|cua|danh cho|ve|theo))?(?: (?:may loc khong khi|may loc|may))?\s*$")
GIFT_CUE_RX = re.compile(r"tặng|quà", re.I)


def _par(sku):
    p = mt._parent(sku)[0] if sku else None
    return p["sku"] if p else sku


def is_accessory(sku):
    p = mt._parent(sku)[0] if sku else None
    return bool(p) and p["category"].startswith(ACCESSORY_CAT)


def normalize_accessories(text, skus, focus=None):
    """13/11 (duyệt): chuẩn hóa mã PHỤ KIỆN trên danh sách sản phẩm parser thấy trong câu — MỘT hàm dùng chung cho ứng viên
    của bộ hiểu (turn_mentioned) và bước chuẩn bị (c.mentioned), để hai nơi thấy cùng đối tượng.
      - Câu nói quà tặng ("tặng" / "quà") hoặc không có "màng lọc" → giữ nguyên.
      - "màng lọc …" đứng NGAY TRƯỚC tên một máy có màng lọc (vd "màng lọc thay thế cho AirPure Y") → lần nhắc đó là PHỤ KIỆN:
        thay máy bằng SKU màng lọc của máy (máy chỉ giữ lại nếu còn được nhắc riêng ở chỗ khác trong câu).
      - "màng lọc" không gắn tên máy → thêm SKU màng lọc của máy DUY NHẤT có màng lọc trong câu (hoặc mẫu đang bàn khi câu
        không nhắc máy nào); nhiều máy → không đoán (ghi ambiguous).
    Chỉ xác định ĐỐI TƯỢNG được nhắc; không suy khách muốn mua (việc đó thuộc bước chuẩn bị giỏ). → (skus, ghi chú)."""
    note = {"bound": [], "added": [], "ambiguous": False}
    if not text or not ACC_WORD_RX.search(fold(text)) or GIFT_CUE_RX.search(text):
        return list(skus), note
    f, spans = mention_spans(text)
    out = []
    for sku in skus:
        acc = FILTER_OF.get(_par(sku))
        sp = spans.get(sku) or spans.get(_par(sku)) or []
        if acc and sp:
            bound = [ACC_BOUND_RX.search(f[:st]) is not None for st, _ in sp]
            if any(bound):
                note["bound"].append(sku)
                if not all(bound):
                    out.append(sku)
                out.append(acc)
                continue
        out.append(sku)
    if not any(is_accessory(x) for x in out):
        owners = list(dict.fromkeys(_par(x) for x in out if FILTER_OF.get(_par(x))))
        if len(owners) == 1:
            out.append(FILTER_OF[owners[0]]); note["added"].append(FILTER_OF[owners[0]])
        elif not owners and not out and focus and FILTER_OF.get(_par(focus)):
            out.append(FILTER_OF[_par(focus)]); note["added"].append(FILTER_OF[_par(focus)])
        elif len(owners) > 1:
            note["ambiguous"] = True
    return list(dict.fromkeys(out)), note

# 06/11: cue trên câu khách nằm trong harness/lexicon/cues.json (ghi chú nguồn + ví dụ khớp / không khớp ở đó).
# Regex tách giá trị (thời hạn DUR_RX, số lượng QTY_RX) vẫn ở đây, cạnh logic dùng nó.
GIFT_Q_RX = lexrx.rx("cues", "GIFT_Q_RX")
GIFT_SKUS = {p["gift_sku"] for p in mt.PROMOS if p.get("gift_sku")}
PROMO_END_RX = lexrx.rx("cues", "PROMO_END_RX")
PRIOR_REF_RX = lexrx.rx("cues", "PRIOR_REF_RX")
REFUND_RX = lexrx.rx("cues", "REFUND_RX")
HYPO_RX = lexrx.rx("cues", "HYPO_RX")
DOC_REF_RX = lexrx.rx("cues", "DOC_REF_RX")
DUR_RX = re.compile(r"\b(\d+|mot|hai|ba|bon|sau|bay|tam|chin|muoi|nua) (nam|thang|tuan|ngay)\b")
_NUM_WORD = {"mot": (1, "một"), "hai": (2, "hai"), "ba": (3, "ba"), "bon": (4, "bốn"), "sau": (6, "sáu"),
             "bay": (7, "bảy"), "tam": (8, "tám"), "chin": (9, "chín"), "muoi": (10, "mười"), "nua": (0.5, "nửa")}
_UNIT = {"nam": (365, "năm"), "thang": (30, "tháng"), "tuan": (7, "tuần"), "ngay": (1, "ngày")}
PROXY_CLAIM_RX = lexrx.rx("cues", "PROXY_CLAIM_RX")          # 1c J6: người gọi tự xưng người nhà của khách
PROXY_INFO_RX = lexrx.rx("cues", "PROXY_INFO_RX")
REFUSE_INTERNAL_OK_RX = lexrx.rx("cues", "REFUSE_INTERNAL_OK_RX")
REFUSE_INTERNAL_SENT = "Dạ, các mức giá nội bộ của shop được bảo mật, em không thể cung cấp ạ."
# Ý định router có thể dẫn tới tool ghi (order.create / order.update / schedule.callback): chờ trích slot xong mới lập kế hoạch
WRITE_INTENTS = ("place_order", "order_change", "callback")
GATED_REQUESTS = {"place_order", "change_order_address", "exchange", "return", "callback"}
OTHER_PII_RX = lexrx.rx("cues", "OTHER_PII_RX")


def _ddmm(d):
    return f"{int(d[8:10])}/{int(d[5:7])}"


def _strip_open_questions(text, known):
    """D39(a): bỏ các câu hỏi mở khỏi bản nháp; trả None nếu không còn gì đáng gửi."""
    out = text
    for q in extractor.agent_questions(text, known):
        if q["type"] == "open":
            out = out.replace(q["text"], "", 1)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out if len(out) >= 8 else None


# Slot do agent tự ghi về những gì đã tư vấn/báo giá/đặt đơn ở phiên trước (tầng episodic); còn lại là profile của khách
EPISODIC_SLOTS = frozenset({"product_advised", "price_quoted_vnd", "promo_code", "promo_expiry", "product_chosen",
                            "order_id", "variant_sku", "estimated_delivery"})


def _mem_layers(facts):
    """Ablation MEM_ABLATE (mặc định rỗng → trả nguyên): profile = bỏ fact về khách; episodic = bỏ fact về phiên trước.
    ttl / supersede xử lý trong Memory.current_facts."""
    # v6p12: exchanges:<mã đơn> là sổ đếm nội bộ cho fee_free, không phải thông tin về khách → không vào known / brief / prompt
    facts = {k: v for k, v in facts.items() if k != "phone_claim" and not k.startswith("exchanges:")}
    ablate = settings.mem_ablate
    if "profile" in ablate:
        facts = {k: v for k, v in facts.items() if k in EPISODIC_SLOTS}
    if "episodic" in ablate:
        facts = {k: v for k, v in facts.items() if k not in EPISODIC_SLOTS}
    return facts


MAX_CUSTOMER_CHARS = 600
ATTR_ASK_RX = lexrx.rx("cues", "ATTR_ASK_RX")
CLOSE_ORDER_RX = lexrx.rx("cues", "CLOSE_ORDER_RX")
CLOSING_RX = lexrx.rx("cues", "CLOSING_RX")


def _money_in_strings(obj):
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not str(k).startswith("_"):
                out |= _money_in_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _money_in_strings(v)
    elif isinstance(obj, str):
        out |= {v for _, _, v in find_money(obj)}
    return out


# Ý trả hàng trong lúc xử lý đơn đã có (V3-140; mẫu và phản ví dụ ở harness/lexicon/cues.json)
RETURN_RX = lexrx.rx("cues", "RETURN_RX")

_QTY_WORD = {"hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}
# E04: số + đơn vị đếm sản phẩm ("lấy 2 cái", "hai đôi", "3 máy"). Không bắt số người / tháng / m² / size / tiền vì đơn vị khác.
QTY_RX = re.compile(r"\b(\d{1,2}|hai|ba|bon|nam|sau|bay|tam|chin|muoi)\s+(cai|chiec|may|doi|bo|hop|thung|cuon|goi|bich|chai|tui|cap|san pham)\b")


def order_qty(texts):
    """Số lượng khách muốn mua, đọc từ câu khách mới nhất trở về trước (texts: mới nhất trước). None = không nói."""
    for t in texts:
        f = fold(t or "")
        if re.search(r"\bthem\b", f):          # "lấy thêm 1 cái nữa" = thêm vào giỏ, không phải số lượng của SKU đang chốt
            continue
        m = QTY_RX.search(f)
        if m:
            n = int(m.group(1)) if m.group(1).isdigit() else _QTY_WORD[m.group(1)]
            return n if 1 <= n <= 20 else None
    return None


def _promo_safe_plan(plan, problems):
    """D33 (05/11): khi sinh lại vẫn nói KM đã hết hạn như còn hiệu lực / giá cũ như giá hiện tại, câu mẫu an toàn báo rõ KM đã hết
    và giá hiện tại (lấy từ tool trong lượt), thay vì chỉ "Dạ em cảm ơn" (BTCL-051/052 call_2 lượt 2)."""
    if not any("đã hết hạn như còn hiệu lực" in p or p.startswith("nói giá cũ") for p in problems):
        return plan
    goals = [g for g in plan.get("goals", []) if g != "stale_promo"]
    goals.insert(0, "stale_promo")
    if (plan.get("facts") or {}).get("quote") and "quote" not in goals and "recommend" not in goals:
        goals.insert(1, "quote")
    return {**plan, "goals": goals}


def _next_action(last, blockers, open_q, orders, advised, stale):
    if open_q:
        return "trả lời câu khách hỏi lần trước chưa có câu trả lời: " + "; ".join(open_q[:2])
    pending = [o for o in orders if o.get("status") not in ("delivered", "cancelled", "returned")]
    if pending:
        return f"hỏi khách cần hỗ trợ gì với đơn {pending[-1]['order_id']} ({pending[-1].get('status')})"
    if blockers:
        return "xác nhận tiếp nối, giải quyết rào cản rồi chốt"
    if advised:
        return ("báo lại giá hiện tại vì có thay đổi, rồi chốt" if stale else "xác nhận tiếp nối mẫu đã tư vấn rồi chốt")
    if last:
        return "hỏi nhu cầu mới, không hỏi lại thông tin đã có trong profile_facts"
    return None


SEED_TRANSIENT = ("blocker", "callback_requested", "self_name", "competitor_price_vnd")
# BTC 11/2026 (2.2): tên field của seed_history.facts khác tên slot bộ nhớ của nhóm. Chỉ ánh xạ field BTC đã công bố; field trùng
# tên slot dùng thẳng; field lạ → bỏ + ghi log (không đoán), summary vẫn được trích như cũ.
SEED_FIELD_ALIASES = {"interest_sku": "product_advised"}
SEED_INT_SLOTS = ("room_area_m2", "budget_vnd", "household_size", "price_quoted_vnd", "competitor_price_vnd")
SEED_BOOL_SLOTS = ("has_children",)
SEED_SKU_SLOTS = ("product_advised", "owned_product", "unresolved_order_sku")


def _seed_value(slot, value):
    if slot in SEED_INT_SLOTS:
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
    if slot in SEED_BOOL_SLOTS:
        return value if isinstance(value, bool) else None
    if slot in SEED_SKU_SLOTS:
        return value if isinstance(value, str) and mt._parent(value)[0] else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _seed_facts(raw, session_date):
    """→ ([(as_of, slot, value)], [lý do bỏ]). as_of thiếu / sai định dạng → ngày của phiên."""
    from harness.memory import TTL_DAYS
    out, bad = [], []
    for f in raw if isinstance(raw, list) else []:
        if not isinstance(f, dict):
            bad.append("not_object"); continue
        field = str(f.get("field") or "")
        slot = SEED_FIELD_ALIASES.get(field, field)
        if slot not in TTL_DAYS or slot in SEED_TRANSIENT:
            bad.append(f"unknown_field:{field[:40]}"); continue
        value = _seed_value(slot, f.get("value"))
        if value is None:
            bad.append(f"bad_value:{field[:40]}"); continue
        asof = str(f.get("as_of") or "")
        try:
            date.fromisoformat(asof)
        except ValueError:
            asof = session_date
        out.append((asof, slot, value))
    return out, bad



# S5 v6p13: câu do agent tự sinh theo goal → claim chỉ giữ khi goal của lượt có thể sinh ra khẳng định đó
_IDENTITY_GOALS = ("is_bot",)
_PRODUCT_PRICE_FIELDS = ("price_vnd", "list_price_vnd", "price_quoted_vnd")


def _grounded_claims(claims, goals, policy_texts, row):
    """is_human chỉ từ goal danh tính; số tiền trong câu chép từ tài liệu chính sách không phải giá của sản phẩm."""
    from harness.audit import sentences
    quoted = [fold(x) for t in policy_texts for line in (t or "").splitlines() for x in sentences(line.replace("**", "").strip(" -*#|")) if len(x) >= 20]
    keep, dropped = [], []
    for c in claims:
        from_policy = any(q in fold(c.get("text") or "") for q in quoted)
        not_identity = c["field"] == "is_human" and not set(goals) & set(_IDENTITY_GOALS)
        if not_identity or (c["field"] in _PRODUCT_PRICE_FIELDS and from_policy):
            dropped.append({"field": c["field"], "why": "goal_not_claim_source"})
        else:
            keep.append(c)
    if dropped:
        row.setdefault("claim_grounding", []).extend(dropped)
    return keep

class CallSession:
    def __init__(self, *, memory, today, call_name, session_id, channel, channel_identity, phone, input_mode,
                 router=None, generator=None, config="full", planner_variant=None, planner_decider=None, on_emit=None):
        self.mem, self.today, self.call_name, self.session_id = memory, today, call_name, session_id
        # 13/11: đường gửi phản hồi — on_emit(msg) là callback của backend / UI, được gọi NGAY khi câu cuối đã qua guardrail;
        # outbox giữ bản đã gửi (kiểm: audit chạy đúng trên nội dung này). _audits: audit nền chưa ghi vào trace (theo thứ tự lượt).
        self.on_emit, self.outbox, self._audits = on_emit, [], []
        self.channel, self.channel_identity, self.phone, self.input_mode = channel or "hotline", channel_identity, phone, input_mode
        self.router, self.gen, self.config = router or Router(), generator or Generator(), config
        if settings.arch == "target":
            from core.config import check_arch
            check_arch(settings)                 # K08: cấu hình mâu thuẫn bị từ chối, không lặng lẽ chạy hai bộ hiểu
        from harness import planner_variants
        # 12/11: chủ sở hữu tiến trình dựng MỘT lần cho session (b1 | b2_jev); đổi biến thể = session mới
        self.planner = planner_variants.make(planner_variant, decider=planner_decider)
        self.planner_loop = None
        self.tools = ToolBox(today)
        self.crm_import_log = []
        self.call_tool_log = []              # mọi lời gọi tool của cuộc gọi (ref nguồn cho response blocks)
        self.customer = None
        self.contact_phone = None  # shipping contact only, not identity verification
        # G1 (FINAL 10/11): (phone, sku) order.create có kết quả chưa rõ (lỗi transport). Một đơn cùng SKU/ngày tra được sau đó
        # không chứng minh correlation → không tự đối soát, không tự tạo lại; nhân viên xử lý (handoff ở planner_table._finish).
        self.unresolved_writes = set()
        self.open_requests, self.req_turn, self.req_blocked = set(), None, []   # D68 cổng yêu cầu (request_gate) — R0/TG cũ
        from harness.request_state import RequestState
        self.reqs = RequestState()          # cấu hình đích: MỘT chủ sở hữu state yêu cầu / pending (K01/K06)
        self.qty_obs = None                 # (lượt, số lượng) khách nói, từ observation có căn cứ (thay order_qty đọc lịch sử)
        self.u_turn = None
        self.turn_mentioned = []            # sản phẩm parser catalog thấy trong câu hiện tại (ứng viên ưu tiên cho bộ hiểu)
        self.known_src = {}                 # nguồn của giá trị trong known: customer:tN (khách nói ở lượt N) | memory | default
        self._addr_dispatched = False       # lượt này đã xử lý yêu cầu đổi địa chỉ đơn (dấu điều phối, không là quyền)
        self.sensitive_views = {}    # lời khách nhạy cảm → mô tả trung tính cho bản ghi (_record_view)
        self.handoff_tickets = {}    # lý do chuyển máy → ticket đã xác nhận trong cuộc gọi này (_handoff)
        self.candidates = []
        self.table_rows = []                # D50: các dòng bảng planner đã khớp ở lượt gần nhất (PLANNER_TABLE=1)
        self.semantic_plan = None
        self.table_prev_goals = []          # D51: goal của lượt trước (dòng N03, E12 cần biết lượt trước đã từ chối / xin xác nhận)
        self.carried = {}
        self.known = {}
        self.focus = None
        self.quote = None
        self.prev_quotes = []
        self.orders_created, self.history, self.turn_no = [], [], 0
        self.brief, self.brief_ms, self.start_tool_log = None, None, []
        self.outcome, self.blockers = None, []
        self.focus_by, self.price_change_told, self.category, self.updates_done = None, False, None, {}
        self.pending_size, self.buy_intent, self.deleted = None, False, False
        self.cart, self.discussed, self.expired, self._deleted_turn = [], [], {}, None
        self.size_asked, self.window_told, self.old_addr_asked = False, False, False
        self.open_questions, self.repeat_asked, self.fail_streak = [], 0, 0
        self.seen_money = set()
        self.last_sentiment = None
        self.policy_gap, self.privacy_refused, self.plan_why, self.llm_plan = None, False, [], None
        self.proxy_caller = False           # 1c J6: người gọi tự xưng người nhà của khách khác
        self.prior_contact_asked = 0
        self.last_q_slot = None
        self.call_promo_active, self.call_promo_expired = set(), set()

    def _warranty_months(self, facts):
        """1c J1 (06/11): `warranty_months` (catalog) của các sản phẩm đang nói trong cuộc gọi — cho guardrail bảo hành."""
        skus = {self.focus, (facts.get("quote") or {}).get("sku"), *self.discussed, *self.cart}
        out = set()
        for sku in skus:
            par = mt._parent(sku)[0] if sku else None
            w = ((par or {}).get("attributes") or {}).get("warranty_months")
            if isinstance(w, int) and w > 0:
                out.add(w)
        return out

    def _call_promos(self, tool_log):
        """D22: KM theo kết quả tool của CẢ cuộc gọi (lượt chào kết không gọi tool vẫn kiểm được); bỏ COD-0/freeship."""
        for tc in tool_log:
            r = tc.get("result")
            if not isinstance(r, dict) or "applied_promos" not in r:
                continue
            self.call_promo_active |= {a["promo_code"] for a in r.get("applied_promos") or []
                                       if a.get("type") not in ("freecod", "freeship") and a["promo_code"] not in STACKABLE_SKIP}
            self.call_promo_expired |= {x.get("promo_code") if isinstance(x, dict) else x for x in r.get("expired_promos") or []}
        by_code = {x["promo_code"]: x for x in mt.PROMOS}

        def view(code):
            pr = dict(by_code.get(code) or {"promo_code": code})
            if pr.get("gift_sku"):
                pr["gift_name"] = product_name(pr["gift_sku"])
            return pr
        return {"active": [view(c) for c in sorted(self.call_promo_active)],
                "expired": [view(c) for c in sorted(self.call_promo_expired - self.call_promo_active)]}

    def start(self):
        t0 = time.perf_counter()
        if improve_hook.enabled():
            improve_hook.preflight()                 # C.5: gói sai phạm vi (target chỉ FAQ) → từ chối mở phiên
        # 17/11 candidate: khóa gói hướng dẫn điều phối cho CẢ phiên (PLANNER_GUIDANCE_DIR rỗng → None); gói sai → từ chối mở phiên
        from harness import guidance as _guidance
        self.guidance_pin = _guidance.pin()
        kind, val =("fb_id", self.channel_identity) if self.channel == "chat_fanpage" else \
                    ("zalo_id", self.channel_identity) if self.channel == "zalo_oa" else ("phone", self.phone)
        if not val:
            kind, val = "phone", self.phone
        r = self.tools.call("crm.get_customer", **{kind: val})
        if r.get("found") and r.get("ambiguous"):
            self.candidates = r["candidates"]
        elif r.get("found"):
            self._bind(r["customer_id"], r.get("name"), r.get("honorific"), r.get("phone") or self.phone, r)
        else:
            ids = self.mem.lookup(kind, val) if val else []
            if ids:
                self._bind(ids[0], None, None, self.phone, None)
            elif val:
                self._bind(f"N-{val}", None, None, self.phone, None)
        self.brief = self._build_brief()
        self.brief_ms = int((time.perf_counter() - t0) * 1000)
        self.brief["latency_ms"] = self.brief_ms
        self.start_tool_log = self.tools.take_log()
        return self.brief

    def _bind(self, cid, name, honorific, phone, crm):
        self.customer = {"customer_id": cid, "name": name, "honorific": honorific or "anh/chị", "phone": phone}
        ids = [("phone", phone)]
        if crm:
            ids += [("zalo_id", (crm.get("identities") or {}).get("zalo_id")), ("fb_id", (crm.get("identities") or {}).get("fb_id"))]
        if self.channel_identity:
            ids.append(("fb_id" if self.channel == "chat_fanpage" else "zalo_id", self.channel_identity))
        self.mem.upsert_customer(cid, name, honorific, phone, ids)
        for kind, value in ids:
            for other in (self.mem.lookup(kind, value) if value else []):
                if other != cid and other.startswith("N-"):
                    self.mem.merge_customer(other, cid)
        for s in (crm or {}).get("sessions", []) or []:
            self.import_old_session(s, cid)
        if self.mem.read_enabled and self.mem.status(cid) != "deletion_requested":
            self.carried = {k: v["value"] for k, v in _mem_layers(self.mem.current_facts(cid, self.today)).items()}
            self.known = dict(self.carried)
            self.prev_quotes = [] if "episodic" in settings.mem_ablate else self.mem.past_quotes(cid)
            self.focus = self.known.get("product_chosen") or self.known.get("product_advised")
            self.focus_by = "memory" if self.focus else None

    def import_old_session(self, s, cid):
        if not hasattr(self, "_seed_asof"):
            self._seed_asof = {}
        sid = s["session_id"]
        if any(p["session_id"] == sid for p in self.mem.past_sessions(cid)):
            return
        self.mem.add_session(sid, cid, s.get("channel"), s.get("date"), s.get("outcome"), s.get("summary"), source="crm")
        text, d = s.get("summary", ""), s.get("date") or self.today
        if settings.arch == "target":
            # đích: cùng hợp đồng observations của bộ hiểu DeepSeek (kiểm span + chuẩn hóa bằng code), không rules/CERT/hybrid.
            from harness import understanding
            slots, umeta = understanding.understand_record(text, d)
            self.crm_import_log.append({"session_id": sid, **{k: umeta.get(k) for k in ("calls", "ms", "error")},
                                        "slots": sorted(slots)})
        else:
            slots = extractor.customer_slots(text, d)
            prods = find_products(text)
            if prods: slots["product_advised"] = prods[0]
            money = find_money(text)
            if money and prods: slots["price_quoted_vnd"] = money[0][2]
        for k in SEED_TRANSIENT:
            slots.pop(k, None)
        structured, unmapped = _seed_facts(s.get("facts"), d)
        if unmapped:
            self.crm_import_log.append({"session_id": sid, "facts_unmapped": unmapped})
        writes = [(d, k, v, 0.8, f"crm:{sid}") for k, v in slots.items() if k not in {x[1] for x in structured}]
        writes += [(asof, k, v, 1.0, f"crm:{sid}:facts") for asof, k, v in structured]
        for asof, k, v, conf, src in sorted(writes, key=lambda w: w[0]):
            if not self._seed_newer(cid, k, asof):
                continue
            self.mem.write_fact(cid, k, v, src, sid, self.today, confidence=conf, valid_from=asof)
            self._seed_asof[(cid, k)] = asof

    def _seed_newer(self, cid, slot, asof):
        """BTC 11/2026 (2.2): cùng field mâu thuẫn → as_of mới nhất thắng, bất kể thứ tự nạp phiên. Fact học từ cuộc gọi thật
        (nguồn không phải crm:) mới hơn mọi phiên seed → không bị seed ghi đè."""
        if not hasattr(self, "_seed_asof"):
            self._seed_asof = {}
        prev = self._seed_asof.get((cid, slot))
        if prev is not None:
            return asof >= prev
        cur = self.mem.current_facts(cid, self.today, include_expired=True).get(slot)
        return cur is None or str(cur.get("source") or "").startswith("crm:")

    def _build_brief(self):
        c = self.customer or {}
        cid = c.get("customer_id")
        past = self.mem.past_sessions(cid, self.session_id) if cid and "episodic" not in settings.mem_ablate else []
        facts = _mem_layers(self.mem.current_facts(cid, self.today, include_expired=True)) if cid else {}
        stale, advised = [], []
        for slot, fct in facts.items():
            if fct["expired"]:
                stale.append(f"{slot} đã quá hạn (ghi ngày {fct.get('expires_on')}) — chỉ hỏi xác nhận")
                self.known.pop(slot, None); self.expired[slot] = fct["value"]
        seen = set()
        for q in reversed(self.prev_quotes):
            if q["sku"] in seen or q["role"] not in ("advised", "chosen"):
                continue
            seen.add(q["sku"])
            now = public_view(self.tools.call("pricing.get_quote", sku=q["sku"], customer_phone=c.get("phone")))
            inv = self.tools.call("inventory.check", sku=q["sku"])
            active = bool(q["promo_code"]) and any(a["promo_code"] == q["promo_code"] for a in now.get("applied_promos", []))
            if q["promo_code"] and not active:
                stale.append(f"KM {q['promo_code']} báo cho {q['sku']} đã hết hạn")
            if now.get("final_price_vnd") != q["final_price_vnd"]:
                stale.append(f"giá {q['sku']} đổi {q['final_price_vnd']} → {now.get('final_price_vnd')}")
            if not inv.get("in_stock"):
                stale.append(f"{q['sku']} đang hết hàng")
            advised.append({"sku": q["sku"], "price_quoted_vnd": q["final_price_vnd"], "promo_code": q["promo_code"],
                            "promo_still_active": active if q["promo_code"] else None, "quoted_on": q["quoted_on"],
                            "current_price_vnd": now.get("final_price_vnd"), "in_stock_now": inv.get("in_stock")})
        last = past[-1] if past else None
        must_not_ask = sorted(k for k, v in facts.items() if not v["expired"])
        blockers = [self.known["blocker"]] if self.known.get("blocker") else []
        orders = []
        phone = c.get("phone") or self.phone
        if phone:
            for o in (self.tools.call("order.status", customer_phone=phone).get("orders") or []):
                orders.append({k: v for k, v in {"order_id": o.get("order_id"), "variant_sku": o.get("sku"), "status": o.get("status"),
                                                 "created_on": o.get("created_on") or o.get("date"),
                                                 "estimated_delivery": o.get("estimated_delivery"),
                                                 # BTC 11/2026: đơn nhiều dòng — `sku` cấp đơn chỉ là dòng đầu
                                                 "items": self._order_products(o) if len(o.get("lines") or []) > 1 else None}.items() if v is not None})
        open_q = list((last or {}).get("open_questions") or [])
        opening = None
        if last and self.focus:
            opening = f"Dạ em chào {c.get('honorific')} {c.get('name') or ''}, hôm {_ddmm(last['started_on'])} bên em có tư vấn mẫu {product_name(self.focus)}."
        return {"customer_phone": c.get("phone") or self.phone, "customer_name": c.get("name"), "honorific": c.get("honorific"),
                "is_returning": bool(past), "n_previous_sessions": len(past),
                "last_session": {"session_id": last["session_id"], "date": last["started_on"], "channel": last["channel"],
                                 "summary": last["summary"], "outcome": last["outcome"] or "khac"} if last else None,
                "profile_facts": {k: v["value"] for k, v in facts.items() if not v["expired"]},
                "products_advised": advised, "orders": orders, "open_blockers": blockers, "open_questions": open_q,
                "must_not_ask": must_not_ask, "stale_warnings": stale, "suggested_opening": opening,
                "suggested_next_action": _next_action(last, blockers, open_q, orders, advised, stale),
                "generated_at": datetime.now().isoformat(timespec="seconds"), "latency_ms": None,
                "precomputed_parts": ["sessions.summary", "facts"], "ambiguous_candidates": [x["name"] for x in self.candidates]}

    def turn(self, raw):
        if settings.jev_simulated:
            from harness.jev_adapter import block_real_api
            block_real_api()
        t_start = time.perf_counter()
        self._collect_audits()          # audit nền của lượt trước đã xong → ghi vào trace của lượt đó (không đợi)
        self.turn_no += 1
        self.planner_loop = None
        if self.input_mode == "asr_transcript":
            from asr.itn import itn
            raw = itn(raw)
        # G2 (FINAL 10/11): một phép cắt duy nhất cho câu khách, TRƯỚC mọi tầng (PII/SĐT, extractor, router, planner) để không tầng
        # nào đọc một ý khác tầng kia. Câu bị cắt thì planner không chạy (không thực hiện giao dịch khi chưa đọc hết câu, có thể
        # mất phủ định ở phần sau) — xin khách nói gọn lại. Câu khách đánh giá dài nhất hiện có 478 ký tự (V3 dev).
        truncated = len(raw) > MAX_CUSTOMER_CHARS
        if truncated:
            raw = raw[:MAX_CUSTOMER_CHARS]
        p = perceive(raw, self.today)
        text = p["text"]
        truncated = truncated or len(text) > MAX_CUSTOMER_CHARS     # chuẩn hóa teencode có thể làm câu dài thêm
        text = text[:MAX_CUSTOMER_CHARS]
        target = settings.arch == "target"
        self.req_turn, self.req_blocked = None, []
        t_perceive = time.perf_counter()
        # L1: router chỉ cần lời khách + lịch sử + tóm tắt phiên trước, không cần slot → gọi song song với bước trích slot.
        # Lượt có SĐT hoặc đang hỏi danh tính thì vẫn nối tiếp: định danh có thể đổi brief (tóm tắt) mà router dùng.
        early_route = None
        from harness import understanding
        if settings.planner_selector == "rules" and settings.parallel_router and not p["phone"] and not self.candidates \
                and not understanding.enabled():
            ctx_early = {"recent": self.history[-4:],
                         "summary": (self.brief or {}).get("last_session") and self.brief["last_session"]["summary"] or ""}
            early_route = _ROUTER_POOL.submit(self.router.route, text, ctx_early)
        ext_meta = {}
        recent_context = "\n".join(f"{h['role']}: {h['text']}" for h in self.history[-8:])
        session_summary = ((self.brief or {}).get("last_session") or {}).get("summary", "")
        extraction_context = "\n".join(part for part in (
            f"Tóm tắt phiên trước: {session_summary}" if session_summary else "",
            f"Hội thoại gần đây:\n{recent_context}" if recent_context else "",
        ) if part)
        self.u_turn = None
        if understanding.enabled():
            # kiến trúc đích (11/11): MỘT lần gọi DeepSeek Flash thay router + trích slot khách (rules/CERT/Jev hybrid/Qwen)
            # + nhận diện yêu cầu. Lỗi → không quay về pipeline cũ (xem nhánh ask_repeat bên dưới).
            self._addr_dispatched = False
            if target:
                # 4.3: sản phẩm parser catalog thấy trong câu hiện tại vào ứng viên TRƯỚC khi gọi bộ hiểu (không để mẫu đã bàn cũ
                # chiếm hết giới hạn); parser chỉ tra tên / mã mẫu, không quyết khách muốn mua hay hỏi
                # 13/11 (duyệt): chuẩn hóa mã phụ kiện TRƯỚC khi dựng ứng viên cho DeepSeek (cùng hàm với bước chuẩn bị); mã quà
                # tặng chỉ bị loại khỏi ứng viên khi câu nói quà tặng
                found = find_products(text)
                base = ([x for x in found if x not in GIFT_SKUS] or found) if GIFT_CUE_RX.search(text) else found
                self.turn_mentioned, self.accessory_norm = normalize_accessories(text, base, self.focus)
            try:
                state_ctx = self.reqs.context(self) if target else None          # K07: state/pending/ứng viên gọn từ code
                self.u_turn = understanding.understand(text, self.today, self.history[-6:], session_summary, self.last_q_slot,
                                                       state_ctx=state_ctx)
                slots, pending = dict(self.u_turn["slots"]), None
                ext_meta.update(backend="deepseek_unified", ms=self.u_turn["meta"]["ms"])
                if settings.pick_by_name and target and not self.turn_mentioned:
                    # S2 v6p13: tên khách gọi khớp đúng MỘT mẫu catalog → mẫu được nhắc của lượt (cùng chỗ parser ghi)
                    picked = (self.u_turn.get("name_pick") or {}).get("skus") or []
                    if len(picked) == 1:
                        self.turn_mentioned = list(picked)
                if target:
                    q = slots.pop("qty", None)                 # số lượng: chỉ cho đơn của yêu cầu đặt cùng / sau lượt này
                    if q:
                        self.qty_obs = (self.turn_no, q)
                    self.u_turn["route"]["understanding"]["targets"] = [
                        it["target_ref"] for it in self.u_turn.get("request_items") or []
                        if it["kind"] in ("place_order", "add_to_cart") and it.get("target_ref")]
            except Exception as e:
                self.u_turn = {"error": f"{type(e).__name__}: {str(e)[:200]}", "safety": [], "requests": []}
                slots, pending = {}, None
                ext_meta.update(backend="deepseek_unified", ms=0)
            if target and truncated:
                self.reqs.events, self.reqs.hold = [], "input_truncated"     # câu bị cắt: không mở / dùng yêu cầu nào
            elif target:
                self.turn_text = text                          # F8 (B2): cổng mở yêu cầu đặt hàng đọc đúng câu khách của lượt
                gate = None
                if settings.jev_write_gate and settings.planner_variant == "b2_jev" and not self.u_turn.get("error"):
                    from harness.jev_write_gate import assess, normalize
                    self.u_turn, normalization = normalize(self, self.u_turn, self.reqs)
                    gate = assess(self, self.u_turn, self.reqs, self.turn_no)
                else:
                    normalization = None
                self.reqs.ingest(self, self.u_turn, self.turn_no, gate=gate, normalization=normalization)
        else:
            slots, pending = extractor.customer_slots_start(
                text, self.today, meta=ext_meta, context=extraction_context or None,
                asked=self.last_q_slot)          # CERT v2 (3.3): slot agent vừa hỏi ở lượt trước (question_slot của planner)
        t_slots = time.perf_counter()
        proxy_now = ("proxy_claim" in self.u_turn["safety"]) if self.u_turn else bool(PROXY_CLAIM_RX.search(fold(text)))
        if proxy_now and not self.proxy_caller:
            self.proxy_caller = True
            self._why("proxy_caller", "người gọi tự xưng người nhà của khách khác; không gắn hồ sơ theo SĐT đọc trong câu")
        from harness.identity_permissions import may_bind_spoken_phone
        phone_link = None
        if settings.jev_write_gate and p['phone'] and not may_bind_spoken_phone(self, p['phone']):
            from harness.identity_permissions import link_new_spoken_phone
            phone_link = link_new_spoken_phone(self, p['phone'])
        unverified_phone = bool(p['phone'] and not may_bind_spoken_phone(self, p['phone']))
        if unverified_phone and not proxy_now:
            self.contact_phone = p['phone']
            if settings.jev_write_gate and self.customer and self.customer.get("customer_id"):
                # Claim thuộc kênh hiện tại; không gắn identity SĐT hay cấp quyền đọc hồ sơ của số đó.
                self.mem.write_fact(self.customer["customer_id"], "phone_claim",
                                    {"phone": p["phone"], "channel": self.channel, "session_id": self.session_id,
                                     "status": "unverified"}, f"customer_claim:t{self.turn_no}",
                                    self.session_id, self.today, confidence=0.0)
        identity_note = {"branch": "spoken_phone_contact_only", "reason": "SĐT khách tự đọc không khớp danh tính kênh: chỉ là số liên hệ"} \
            if unverified_phone and not proxy_now else None
        if phone_link:
            identity_note = {"branch": "demo_phone_link", "reason": phone_link["reason"], "linked": phone_link["linked"]}
        if phone_link and phone_link["linked"]:
            pass
        elif p["phone"] and (proxy_now or unverified_phone):
            pass                            # 1c J6: SĐT của người khác → không gắn / gộp hồ sơ
        elif p["phone"] and self.customer and self.customer.get("customer_id") and not self.candidates:
            cid = self.customer["customer_id"]
            self.mem.upsert_customer(cid, identities_=[("phone", p["phone"])])
            self.customer["phone"] = self.customer.get("phone") or p["phone"]
            if cid.startswith("N-"):
                r = self.tools.call("crm.get_customer", phone=p["phone"])
                if r.get("found") and not r.get("ambiguous"):
                    self.mem.merge_customer(cid, r["customer_id"])
                    keep = dict(self.known)
                    self._bind(r["customer_id"], r.get("name"), r.get("honorific"), p["phone"], r)
                    self.known.update(keep)
        elif p["phone"] and not self.customer and not self.candidates:
            self.phone = p["phone"]
            r = self.tools.call("crm.get_customer", phone=p["phone"])
            keep = dict(self.known)
            if r.get("found") and r.get("ambiguous"):
                self.candidates = r["candidates"]
            elif r.get("found"):
                self._bind(r["customer_id"], r.get("name"), r.get("honorific"), p["phone"], r)
            else:
                ids = self.mem.lookup("phone", p["phone"])
                self._bind(ids[0] if ids else f"N-{p['phone']}", None, None, p["phone"], None)
            self.known.update(keep)
        if self.candidates and slots.get("self_name"):
            self._resolve_candidate(slots["self_name"])
        elif slots.get("self_name") and self.customer and str(self.customer.get("customer_id", "")).startswith("N-"):
            said, stored = fold(slots["self_name"]), fold(str(self.carried.get("self_name") or ""))
            if stored and said != stored:
                old = self.customer["customer_id"]
                log.warning("tên tự xưng %r khác hồ sơ %s (%r) → tách hồ sơ, không dùng bộ nhớ cũ", slots["self_name"], old, stored)
                self.customer = {**self.customer, "customer_id": f"{old.split('~')[0]}~{said.replace(' ', '')}", "name": None}
                self.mem.upsert_customer(self.customer["customer_id"], None, None, self.customer.get("phone"), [])
                self.carried, self.known, self.prev_quotes, self.focus, self.focus_by = {}, {}, [], None, None
            if not self.customer.get("name"):
                self.customer["name"] = slots["self_name"]
        if self.customer and not self.customer.get("name") and self.known.get("self_name"):
            self.customer["name"] = self.known["self_name"]
        ctx ={"recent": self.history[-4:], "summary": (self.brief or {}).get("last_session") and self.brief["last_session"]["summary"] or ""}
        t_identity = time.perf_counter()
        if self.u_turn is not None:
            route = {**(self.u_turn.get("route") or {"intent": "greeting_or_other", "confidence": 0.0, "probabilities": {}, "flags": {}}),
                     "backend": "deepseek_unified", "ms": (self.u_turn.get("meta") or {}).get("ms", 0), "fallback": None}
        else:
            route = (early_route.result() if early_route is not None else self.router.route(text, ctx)) if settings.planner_selector == "rules" else {"intent": "meta", "confidence": 1.0, "flags": {}, "backend": "selector", "ms": 0, "fallback": None}
        t_route = time.perf_counter()
        knowledge.spent_ms = 0.0
        # 10/11 (V3-132): trên đường rules bước trích Qwen chạy nền không được chờ, nên order.create có thể chạy trước khi địa chỉ
        # khách vừa đọc được trích xong (đơn thiếu địa chỉ rồi hỏi lại). Lượt có ý định dẫn tới thao tác ghi thì chờ hiểu xong
        # câu khách rồi mới lập kế hoạch; lượt khác giữ chạy song song như cũ để không tăng độ trễ.
        wait_full = settings.planner_selector != 'rules' or route.get("intent") in WRITE_INTENTS
        if pending is not None and extractor.customer_slots_finish(pending, slots, settings.extractor_timeout_s if wait_full else 0) is not None:
            pending = None
        t_req0 = time.perf_counter()
        self.req_turn = None
        if self.u_turn is not None:
            # yêu cầu lấy từ bộ hiểu thống nhất; câu mơ hồ không mở yêu cầu ghi mới; lỗi API → không yêu cầu nào (không ghi)
            amb = (self.u_turn.get("ambiguity") or {}).get("level") == "needs_clarification"
            self.req_turn = {"requests": [] if amb else list(self.u_turn.get("requests") or []), "backend": "deepseek_unified",
                             **({"error": self.u_turn["error"]} if self.u_turn.get("error") else {})}
        req_wait_ms = int((time.perf_counter() - t_req0) * 1000)
        if target:
            self.req_turn = None          # đích: quyền ghi do request_state (bản ghi có target/điều kiện/status), không còn tập tên
        elif self.req_turn and not self.req_turn.get("fallback"):
            self.open_requests |= set(self.req_turn["requests"]) & GATED_REQUESTS
        # 1b (06/11): planner chỉ còn bảng quyết định (harness/planner_rules.json). _plan if-else cũ đã bỏ
        # (bản cuối ở commit ce171ac); bảng chỉ có nhánh cũ từng trùng trace 100 % với nó (D50).
        if self.u_turn is not None and self.u_turn.get("error") and not truncated:
            self.plan_why, self.llm_plan = [], None
            self._why("understanding_error", "bộ hiểu lỗi sau khi thử lại: không lập kế hoạch thao tác, xin khách nói lại")
            goals, facts = ["ask_repeat"], {}
        elif truncated:
            self.plan_why, self.llm_plan = [], None     # planner_table.plan (không chạy) là nơi reset mỗi lượt
            self._why("input_truncated", f"câu khách dài hơn {MAX_CUSTOMER_CHARS} ký tự: không lập kế hoạch thao tác trên câu đã cắt")
            goals, facts = ["ask_repeat"], {}
        else:
            goals, facts = self.planner.plan(self, text, slots, route)
        if target:
            self.reqs.bind_unbound(self)
        if identity_note:
            self.plan_why.insert(0, identity_note)       # planner_table.plan reset plan_why mỗi lượt → ghi sau khi lập kế hoạch
        t_plan = time.perf_counter()
        rag_ms = knowledge.spent_ms
        tools_ms = sum(tc.get("ms", 0) for tc in self.tools.log)
        tool_log = (self.start_tool_log if self.turn_no == 1 else []) + self.tools.take_log()
        if target:
            self.call_tool_log += [{**entry, "_turn": self.turn_no} for entry in tool_log]  # ref nguồn + lượt phát sinh
        plan = {"honorific": (self.customer or {}).get("honorific") or "anh/chị", "customer_name": (self.customer or {}).get("name"),
                "call": self.call_name, "is_returning": bool(self.brief and self.brief["is_returning"]),
                "customer_said": text, "intent": route["intent"], "goals": goals, "facts": facts,
                "KNOWN": {k: v for k, v in self.known.items() if k not in ("self_name", "unresolved_order_sku")},
                "question_slot": question_slot(goals, facts)}
        if settings.goal_contract:
            from harness.goal_contract import enforce
            plan = enforce(plan, tool_log)
            goals, facts = plan["goals"], plan["facts"]
        improve_used = improve_hook.apply_to_plan(plan, text, goals)   # mục E: tắt mặc định → không đổi plan
        self.last_q_slot = plan["question_slot"]
        promos = self._call_promos(tool_log)
        wok = self._warranty_months(facts)
        allowed = set(p["money"]) | {v for v in self.known.values() if isinstance(v, int)}
        internal = set()
        for tc in tool_log:
            allowed |= guardrails.collect_numbers(tc["result"])
            internal |= {int(v) for k, v in (tc["result"] or {}).items() if str(k).startswith("_") and isinstance(v, (int, float))} if isinstance(tc["result"], dict) else set()
        for q in self.prev_quotes:
            allowed |= {q["final_price_vnd"], q["list_price_vnd"]}
        allowed |= guardrails.collect_numbers(facts)
        for ch in facts.get("policy") or []:
            allowed |= {v for _, _, v in find_money(ch["text"])}
        allowed |= _money_in_strings(facts)
        self.seen_money |= allowed
        cur = (facts.get("quote") or {}).get("final_price_vnd")
        tool_now = set().union(*(guardrails.collect_numbers(tc["result"]) for tc in tool_log)) if tool_log else set()
        forbidden = {v for v in slots.get("claimed_prices", []) if cur and v != cur and v not in tool_now}
        stale = {v for q in self.prev_quotes for v in (q["final_price_vnd"],) if v and cur and v != cur and v not in tool_now}
        # số tiền do khách nói (ngân sách, giá bên khác) — được nhắc lại, nhưng không được đọc như giá sản phẩm (B5)
        cust_money = (set(p["money"]) | {self.known[k] for k in ("budget_vnd", "competitor_price_vnd") if isinstance(self.known.get(k), int)}) \
            - tool_now - guardrails.collect_numbers(facts) - {q["final_price_vnd"] for q in self.prev_quotes}
        from core.llm.generator import render_offline
        guard = {"problems": [], "action": None}
        adaptive_second = (settings.gen_adaptive_second and settings.gen_parallel_n == 2
                           and self.gen.backend in ("deepseek", "qwen"))
        if adaptive_second:
            guard["candidate_strategy"] = "adaptive"
        t_gen = time.perf_counter()
        if target:
            # K13: response blocks + renderer theo bằng chứng; LLM chỉ compose phần xã giao / chọn câu chính sách theo ID.
            from harness import renderer
            rend = renderer.render(plan, tool_log, self.call_tool_log, self.gen.backend,
                                   bool((self.u_turn or {}).get("asks_question")), asks=(self.u_turn or {}).get("asks") or [],
                                   focus=self.focus)
            text_out, usage = rend["text"], None
            problems = guardrails.check(text_out, allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok)
            from harness.coverage import content as _content     # đích: chỉ kiểm nội dung bắt buộc; câu hỏi do block code sở hữu
            cov = _content(text_out, goals, facts)
            guard.update(action="rendered_blocks", problems=problems, coverage=cov)
            if problems:
                # phần compose vi phạm guardrail → chỉ block code (render mặc định cùng registry), không sinh lại
                guard["rejected"] = [text_out[:400]]
                rend = renderer.render(plan, tool_log, self.call_tool_log, "offline", False)
                text_out, guard["action"] = rend["text"], "blocks_only"
                guard["problems_after"] = guardrails.check(text_out, allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok)
            # pending phản ánh câu THỰC SỰ gửi: chỉ block đề nghị có trong câu cuối mới thành đề nghị khách có thể "ok" ở lượt sau
            # (block bị chặn / thay bằng contract_error / fallback blocks_only không còn đề nghị → không có pending).
            self.reqs.set_proposal(self, [b["kind"] for b in rend["blocks"]], facts)
            guard["render"] = {k: rend[k] for k in ("blocks", "blocked", "policy_refs", "attribute_refs", "compose")}
            ttft = total_gen = int((time.perf_counter() - t_gen) * 1000)      # compose không stream: TTFT = cả bước render
            llm1_ttft, llm1_total = ttft, total_gen
            t_gen1 = t_guard = time.perf_counter()
        else:
            problems = cov = None
            try:
                candidates = self.gen.generate_candidates(
                    plan, count=1, first_temperature=0.0) if adaptive_second else self.gen.generate_candidates(plan)
                total_gen = candidates[0].get("parallel_total", candidates[0]["total"])
                ttft = min(c["ttft"] for c in candidates)
                usage = candidates[0]["usage"]
                text_out = candidates[0]["text"]
                for i, candidate in enumerate(candidates):
                    self.gen.fill_problems = candidate["fill_problems"]
                    p = guardrails.check(candidate["text"], allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok) + self.gen.fill_problems
                    c = coverage(candidate["text"], plan)
                    if not p and not c:
                        text_out, problems, cov = candidate["text"], p, c
                        usage = candidate["usage"]
                        if i:
                            guard["action"] = "parallel_candidate"
                        break
                if problems is None:
                    self.gen.fill_problems = candidates[0]["fill_problems"]
                    problems = guardrails.check(text_out, allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok) + self.gen.fill_problems
                    cov = coverage(text_out, plan)
                    if len(candidates) > 1:
                        guard["candidate_rejections"] = [{"temperature": c["temperature"],
                                                           "problems": guardrails.check(c["text"], allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok)
                                                           + c["fill_problems"], "coverage": coverage(c["text"], plan)}
                                                          for c in candidates]
            except Exception as e:
                log.error("generator %s lỗi → câu mẫu: %s: %s", self.gen.backend, type(e).__name__, str(e)[:160])
                text_out, usage = render_offline(plan), None
                ttft = total_gen = int((time.perf_counter() - t_gen) * 1000)
                guard["action"] = "llm_error_template"
            t_gen1 = time.perf_counter()
            llm1_ttft, llm1_total = ttft, int((t_gen1 - t_gen) * 1000)
            if problems is None:
                problems = guardrails.check(text_out, allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok) + self.gen.fill_problems
                cov = coverage(text_out, plan)
            t_guard = time.perf_counter()
            guard["problems"], guard["coverage"] = problems, cov
            if settings.strip_questions and not problems and cov and set(cov) == {NO_QUESTION}:
                stripped = _strip_open_questions(text_out, plan["KNOWN"])
                if stripped and not guardrails.check(stripped, allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok) \
                        and not coverage(stripped, plan):
                    guard["rejected"] = [text_out[:400]]
                    text_out, guard["action"], problems, cov = stripped, "stripped_question", [], []
            if (problems or cov) and settings.guard_mode == "log":
                guard["action"] = "logged_only"          # ablation: ghi lỗi, giữ nguyên câu, không sinh lại
            elif problems or cov:
                guard["rejected"] = [text_out[:400]]
                bad = sorted({v for _, _, v in find_money(text_out)} - (allowed - forbidden))
                note = "; ".join(problems + cov) + ("" if not bad else ". Viết lại và KHÔNG được có các số: "
                                                   + ", ".join(f"{v:,}đ".replace(",", ".") for v in bad))
                try:
                    text2, ttft2, tot2, _ = self.gen.generate(
                        plan, retry_note=note, temperature=0.7 if adaptive_second else None)
                except Exception as e:
                    log.error("generator %s lỗi khi sinh lại → câu mẫu: %s", self.gen.backend, type(e).__name__)
                    text2, tot2 = render_offline(plan), 0
                p2 = guardrails.check(text2, allowed, internal, forbidden, stale, goals, cust_money, promos, warranty=wok) + self.gen.fill_problems
                c2 = [] if p2 else coverage(text2, plan)
                if not p2 and not c2:
                    text_out, guard["action"] = text2, "regenerated"
                else:
                    guard["rejected"].append(text2[:400])
                    text_out, guard["action"] = render_offline(_promo_safe_plan(plan, p2)), "safe_template" if p2 else "coverage_template"
                total_gen += tot2
            if "refuse_internal" in goals and not REFUSE_INTERNAL_OK_RX.search(fold(text_out)):
                # 1c / V3-093, V3-095 (06/11): đã có goal refuse_internal nhưng câu sinh ra không từ chối rõ ("em chưa có thông tin
                # về giá nhập") → chèn câu từ chối cố định ở đầu (không có số nào nên không cần qua lại guardrail số tiền)
                rest = re.sub(r"^\s*dạ\s*[,.]?\s*", "", text_out, flags=re.I)
                text_out = REFUSE_INTERNAL_SENT + (" " + rest[:1].upper() + rest[1:] if rest else "")
                guard["refuse_internal_prefix"] = True
        t_ready = time.perf_counter()
        # 13/11 (duyệt): GỬI câu cuối — đã qua renderer + guardrail bắt buộc — ra backend / UI NGAY bằng callback thật
        # (on_emit, ghi outbox). TTFT / Total đo tại lần emit này (không stream → TTFT = Total). Audit hậu kỳ phụ thuộc câu đã
        # sinh xong nên chỉ bắt đầu SAU khi câu được gửi; nó chạy nền trên ĐÚNG chuỗi đã gửi, không sửa câu đã gửi, kết quả
        # ghi vào trace của chính lượt này (finalize theo thứ tự lượt, không ghi đè trạng thái lượt mới).
        emitted = self._emit(text_out)
        t_emit = time.perf_counter()
        post_parts = {}
        agent_meta = {}
        known_for_q = {k: v for k, v in self.known.items()}
        agent_started = time.perf_counter()
        audit_rec = None
        if target:
            # K11/K12/K14: MỘT pipeline audit câu cuối thực sự gửi — Jev: questions; Qwen: claims. Không CERT, không cascade.
            from harness import audit
            audit_rec = {"turn": self.turn_no, "sha256": emitted["sha256"], "agent_meta": agent_meta, "t_start": t_start,
                         "t_submit": agent_started}
            if settings.claim_span:
                audit_rec["goals"] = list(goals)
                audit_rec["policy_texts"] = [p["text"] for p in facts.get("policy") or [] if isinstance(p, dict) and p.get("text")]
            audit_rec["future"] = _POST_EXTRACTOR_POOL.submit(_timed_audit, audit.run, emitted["text"], known_for_q, agent_meta,
                                                            self._audit_candidates(tool_log))
            questions, claims = [], []       # điền khi audit xong (_finalize_audit), không trước
        else:
            # đường cũ (không phải kiến trúc đích): giữ phân tích câu agent đồng bộ; câu đã emit ở trên nên latency vẫn đo tại
            # lần gửi, còn phần chờ này nằm trong end_to_end_ms
            agent_future = _POST_EXTRACTOR_POOL.submit(
                extractor.analyze_agent, text_out, known_for_q, agent_meta, self.focus)
            if pending is not None:
                customer_wait_started = time.perf_counter()
                late = extractor.customer_slots_finish(pending, slots, settings.extractor_timeout_s)
                post_parts["customer_slot_wait_ms"] = int((time.perf_counter() - customer_wait_started) * 1000)
                for k, v in late.items():
                    if k not in ("self_name", "claimed_prices"):
                        self.known[k] = v
                if late.get("self_name") and self.customer and not self.customer.get("name"):
                    self.customer["name"] = late["self_name"]
            questions, claims = agent_future.result()
            post_parts["agent_extraction_wall_ms"] = int((time.perf_counter() - agent_started) * 1000)
            # Customer slots may have completed while agent extraction was running. Recheck
            # confirmation labels against the final known-value set without another model call.
            known_for_q = {k: v for k, v in self.known.items()}
            from harness.extractor import CONFIRM_RX, mentions_known
            for question in questions:
                if mentions_known(question["text"], question["slot"], known_for_q) or CONFIRM_RX.search(fold(question["text"])):
                    question["type"] = "confirm"
            _merge_agent_meta(ext_meta, agent_meta, legacy=self.u_turn is None)
        used = extractor.facts_used(text_out, [tc["args"] for tc in tool_log], self.carried)
        memory_started = time.perf_counter()
        mem_writes = self._remember(slots, route)
        post_parts["memory_write_ms"] = int((time.perf_counter() - memory_started) * 1000)
        self.history += [{"role": "customer", "text": text}, {"role": "agent", "text": text_out}]
        turn_log_ms = 0
        if self.customer and self.customer.get("customer_id"):
            turn_log_started = time.perf_counter()
            self.mem.log_turn(self.session_id, self.turn_no, text, text_out, {"focus": self.focus, "intent": route["intent"]})
            turn_log_ms = int((time.perf_counter() - turn_log_started) * 1000)
        post_parts["turn_log_ms"] = turn_log_ms
        pre_ms = int((t_gen - t_start) * 1000)
        total_ms = int((t_emit - t_start) * 1000)            # ranh giới thật: backend / UI đã nhận câu trả lời (emit)
        ms = lambda a, b: int((b - a) * 1000)
        parts = {"perceive_ms": ms(t_start, t_perceive), "slots_ms": ms(t_perceive, t_slots), "identity_ms": ms(t_slots, t_identity),
                 "router_ms": ms(t_identity, t_route), "plan_ms": ms(t_route, t_plan), "plan_tools_ms": int(tools_ms),
                 "plan_rag_ms": int(rag_ms), "prompt_ms": ms(t_plan, t_gen), "llm_ttft_ms": llm1_ttft,
                 "llm_gen_ms": max(0, llm1_total - llm1_ttft), "guard_ms": ms(t_gen1, t_guard), "regen_ms": ms(t_guard, t_ready)}
        row = {"customer_text": text, "agent_text": text_out, "questions": questions, "facts_used": used, "claims": claims,
               "tool_calls": [{"name": tc["name"], "args": tc["args"], "result": tc["result"]} for tc in tool_log],
               # 13/11: TTFT = Total = tới lần emit thật (không stream). Chẩn đoán riêng: response_ready (câu xong, chưa gửi),
               # emit, post (việc đồng bộ sau gửi), end_to_end (turn() trả về), audit (nền) và turn_complete (cả lượt kể cả audit)
               "latency": {"ttft_ms": total_ms, "total_ms": total_ms, "ttfa_ms": None, "measure": "emit_v1",
                           "response_ready_ms": ms(t_start, t_ready), "emit_ms": ms(t_ready, t_emit),
                           "post_ms": None, "end_to_end_ms": None, "audit_ms": None, "audit_run_ms": None,
                           "turn_complete_ms": None, "llm_first_output_ms": pre_ms + ttft, "emit_wall_ts": emitted["wall_ts"],
                           "parts": parts, "post_parts_ms": post_parts},
               "emitted": {"sha256": emitted["sha256"], "error": emitted["error"]},
               "memory_writes": mem_writes,
               "customer_input_mode": {"asr_transcript": "asr_transcript", "chat_teencode": "chat_teencode"}.get(self.input_mode, "clean"),
               "router": {k: route.get(k) for k in ("intent", "confidence", "flags", "backend", "ms", "fallback")
                          + (("improve",) if route.get("improve") else ())},
               "goals": goals, "planner": {"backend": settings.planner_backend, "selector": settings.planner_selector, "simulated": settings.jev_simulated, "contract": plan.get("contract"), "semantic": self.semantic_plan,
                                                    **({"semantic": self.semantic_plan} if self.semantic_plan else {}), "branches": list(self.plan_why),
                                                    **({"payload_dropped": sorted(set(_gen_mod.PAYLOAD_DROPPED))} if _gen_mod.PAYLOAD_DROPPED else {}),
                                                    **({"llm": self.llm_plan} if self.llm_plan else {}),
                                                    "table": list(self.table_rows), "variant": self.planner.name,
                                                    **({"loop": self.planner_loop} if self.planner_loop else {})},
               "question_slot": plan["question_slot"], "guardrail": guard, "llm_usage": usage,
               "extractor": {"backend": ext_meta.get("backend", settings.extractor_backend), "ms": ext_meta.get("ms", 0),
                             "fallback": ext_meta.get("fallback"), "dropped_spans": ext_meta.get("dropped_spans", 0),
                             **{k: ext_meta[k] for k in ("stance_dropped_claims", "stance_dropped_slots") if ext_meta.get(k)}}}
        if self.req_turn is not None:
            row["request_gate"] = {**self.req_turn, "mode": "control" if self.u_turn is not None else settings.requests_gate,
                                   "wait_ms": req_wait_ms, "open": sorted(self.open_requests), "blocked": list(self.req_blocked)}
        if self.u_turn is not None:
            u = self.u_turn
            row["understanding"] = {"backend": "deepseek_unified", "model": settings.deepseek_model, "simulated": settings.deepseek_simulated, "calls": (u.get("meta") or {}).get("attempts", 2 if u.get("error") else 1),
                                    **({"error": u["error"]} if u.get("error") else {
                                        "intent": u["route"]["intent"], "flags": sorted(k for k, v in u["route"]["flags"].items() if v),
                                        # trace không chứa giá trị slot / chữ số của khách (bộ chấm quét PII trên toàn trace)
                                        "requests": u["requests"], "request_evidence": {k: re.sub(r"\d", "#", v) for k, v in u["request_evidence"].items()},
                                        "safety": u["safety"], "asks_question": u["asks_question"],
                                        "ambiguity": {"level": u["ambiguity"]["level"]},
                                        "observations": [o["slot"] for o in u["observations"]],
                                        "dropped": [{"slot": x.get("slot") or x.get("request") or x.get("withdrawn") or x.get("response_to_agent")
                                                     or ("intent" if "intent" in x else "?"), "why": x.get("why", "invalid"), **({"raw": x["raw"]} if x.get("raw") else {}),
                                                     # v6p7b: đường dẫn trường sai kiểu (không có giá trị khách) để chẩn đoán type_invalid
                                                     **({"field": x["field"], "got": x.get("got")} if x.get("field") else {})}
                                                    for x in u["meta"]["dropped"]][:8], "ms": u["meta"]["ms"],
                                        **({"type_hold": u["meta"]["type_hold"]} if u["meta"].get("type_hold") else {}),
                                        **({"retry": {"reasons": u["meta"]["retry"].get("reasons"), "still": u["meta"]["retry"].get("still"),
                                                      "error": u["meta"]["retry"].get("error"), "first_ms": u["meta"]["retry"].get("first_ms")}}
                                           if u["meta"].get("retry") else {}),
                                        **({"contract": "v2", "asks": u.get("asks"), "refs": {k: v for k, v in (u.get("refs") or {}).items() if v},
                                            "response": (u.get("response") or {}).get("act"),
                                            "withdrawn": [w["kind"] for w in u.get("withdrawn") or []],
                                            "request_items": [{"kind": it["kind"], "target_ref": it.get("target_ref"),
                                                               "condition": (it.get("condition") or {}).get("type")}
                                                              for it in u.get("request_items") or []],
                                            "observation_stance": {o["slot"]: o["stance"] for o in u["observations"]}} if target else {})})}
        if target:
            row["request_state"] = {**self.reqs.trace(), "blocked": list(self.req_blocked),
                                    **({"order_gate": self.reqs.order_gate} if getattr(self.reqs, "order_gate", None) else {}),
                                    "turn_mentioned": list(self.turn_mentioned or [])}    # F2: kiểm báo giá đúng mẫu được nhắc
            row["audit"], row["audit_status"] = None, "pending"         # _finalize_audit điền khi audit nền xong
            row["extractor"].update(backend="deepseek_unified", customer_backend="deepseek_unified", agent_backend=None)
            if self.turn_no == 1 and self.crm_import_log:
                row["crm_import"] = list(self.crm_import_log)
        if improve_hook.enabled():
            faq_ret = [h["chunk_id"][4:] for h in facts.get("policy") or [] if str(h.get("chunk_id", "")).startswith("FAQ:")]
            if improve_hook.faq_only():
                # C.5 (16/11): FAQ "dùng" = renderer đã chọn câu của FAQ đó vào câu cuối (policy_refs), không chỉ được tra thấy
                refs = ((guard.get("render") or {}).get("policy_refs") or []) if isinstance(guard, dict) else []
                faq_used = [str(p.get("chunk"))[4:] for p in refs if str(p.get("chunk", "")).startswith("FAQ:")]
                row["improve"] = improve_hook.faq_stamp(faq_ret, faq_used)
            else:
                row["improve"] = improve_hook.stamp(improve_used + faq_ret)
        if "jev_slot_requests" in agent_meta:
            row["extractor"].update({"question_backend": agent_meta.get("question_backend", "jev_slots_experimental"),
                                     "jev_slot_requests": agent_meta["jev_slot_requests"],
                                     "jev_slot_ms": agent_meta["jev_slot_ms"],
                                     "jev_slot_errors": agent_meta["jev_slot_errors"]})
        if settings.jev_simulated:
            from harness.jev_adapter import COUNTS
            row['api_audit'] = dict(COUNTS)
            row['extractor']['simulated'] = True
        if settings.extractor_jev_hybrid and not target:      # đích: cờ legacy không đọc (config.TARGET_IGNORED_FLAGS)
            row["extractor"].update({"jev_hybrid": True,
                                     "jev_label_requests": ext_meta.get("jev_label_requests", 0) + agent_meta.get("jev_label_requests", 0),
                                     "jev_customer_labels": ext_meta.get("jev_customer_labels"),
                                     "jev_claim_labels": agent_meta.get("jev_claim_labels", []),
                                     "jev_customer_error": ext_meta.get("jev_label_error"),
                                     "jev_agent_error": agent_meta.get("jev_label_error"),
                                     # A6: slot luật cắt được mà Jev bỏ (address/payment) + chính sách đã áp
                                     "jev_dropped_rule_slots": ext_meta.get("jev_dropped_rule_slots"),
                                     "jev_drop_policy": settings.jev_drop_policy})
        if agent_meta.get("agent_qwen_skipped") and not target:
            row["extractor"]["agent_claim_backend"] = settings.agent_claim_backend
            row["extractor"]["agent_qwen_skipped"] = True
        if settings.extractor_confidence_gate and not target:
            row["extractor"]["confidence_gate"] = True
            row["extractor"]["customer_confidence"] = ext_meta.get("customer_confidence")
            row["extractor"]["customer_empty_confidence"] = ext_meta.get("customer_empty_confidence")
            row["extractor"]["agent_confidence"] = agent_meta.get("agent_confidence", [])
            row["extractor"]["rule_certified_sentences"] = agent_meta.get("rule_certified_sentences", 0)
            row["extractor"]["customer_qwen_skipped"] = ext_meta.get("customer_qwen_skipped", False)
            row["extractor"]["customer_llm_requests"] = ext_meta.get("request_count", 0)
            row["extractor"]["agent_llm_requests"] = agent_meta.get("request_count", 0)
            row["extractor"]["request_count"] = (ext_meta.get("request_count", 0) +
                                                   agent_meta.get("request_count", 0) +
                                                   agent_meta.get("jev_slot_requests", 0) +
                                                   ext_meta.get("jev_label_requests", 0) +
                                                   agent_meta.get("jev_label_requests", 0))
            row["extractor"]["customer_backend"] = ext_meta.get("backend", settings.extractor_backend)
            row["extractor"]["agent_backend"] = agent_meta.get("backend", settings.extractor_backend)
            row["extractor"]["claim_route"] = agent_meta.get("claim_route", "current_hybrid")
        if self.turn_no == 1:
            # 13/11: ghi cho MỌI cuộc gọi (kể cả call_1 — khách cũ có lịch sử seed vẫn cần brief). Đo trong start(): tra CRM /
            # bộ nhớ + bind + dựng brief + kiểm freshness (giá / KM / tồn / đơn bằng tool) tới khi object brief cuối sẵn sàng;
            # nạp lịch sử seed là bước offline TRƯỚC start(), không tính
            row["call_brief_latency_ms"] = self.brief_ms
            row["call_brief"] = self.brief
        t_return = time.perf_counter()
        row["latency"]["post_ms"] = int((t_return - t_emit) * 1000)
        row["latency"]["end_to_end_ms"] = int((t_return - t_start) * 1000)
        if audit_rec is not None:
            audit_rec.update(row=row, t_return=t_return)
            self._audits.append(audit_rec)
            if not settings.audit_async:
                # chế độ đồng bộ: turn() chỉ trả về sau khi audit xong → end_to_end / post phải gồm phần chờ này
                self.drain_audits()
                t_return = time.perf_counter()
                audit_rec["t_return"] = t_return
                row["latency"]["post_ms"] = int((t_return - t_emit) * 1000)
                row["latency"]["end_to_end_ms"] = int((t_return - t_start) * 1000)
                row["latency"]["turn_complete_ms"] = max(row["latency"].get("turn_complete_ms") or 0, row["latency"]["end_to_end_ms"])
        else:
            row["latency"]["turn_complete_ms"] = row["latency"]["end_to_end_ms"]
            row["audit_status"] = "sync_legacy"
        return row

    # ------------------------------------------------------------------ đường gửi phản hồi + audit hậu kỳ (13/11)
    def _emit(self, text):
        """Gửi câu cuối cho backend / UI (callback on_emit) và ghi outbox. Lỗi callback → ghi error, không nuốt im lặng."""
        msg = {"session_id": self.session_id, "call": self.call_name, "turn": self.turn_no, "text": text,
               "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "wall_ts": time.time(), "error": None}
        if self.on_emit is not None:
            try:
                self.on_emit(dict(msg))
            except Exception as e:
                msg["error"] = f"{type(e).__name__}: {str(e)[:160]}"
                log.error("on_emit lỗi ở lượt %s: %s", self.turn_no, msg["error"])
        self.outbox.append(msg)
        return msg

    def _finalize_audit(self, rec, status=None, error=None):
        """Ghi kết quả audit nền vào trace của ĐÚNG lượt đã sinh ra nó (rec["row"]); không đụng trạng thái phiên / lượt mới."""
        row, am = rec["row"], rec["agent_meta"]
        questions, claims, t_run0, t_done = [], [], None, None
        if status is None:
            try:
                (questions, claims), t_run0, t_done = rec["future"].result(timeout=0)
                status = "ok"
            except Exception as e:
                status, error, t_done = "error", f"{type(e).__name__}: {str(e)[:200]}", time.perf_counter()
        if settings.claim_span and "goals" in rec:
            claims = _grounded_claims(claims, rec["goals"], rec["policy_texts"], row)
        row["questions"], row["claims"] = questions, claims
        row["audit"] = am.get("audit") if status == "ok" else {"status": status, "error": error, "pipeline": "target_v1",
                                                               "cert": None, "cascade": None}
        row["audit_status"] = status
        if error:
            row["audit_error"] = error
        ex = row.get("extractor") or {}
        _merge_agent_meta(ex, am, legacy=False)
        ex["agent_backend"] = (am.get("audit") or {}).get("backend") if status == "ok" else None
        lat = row["latency"]
        if t_done is not None:
            lat["audit_ms"] = int((t_done - rec["t_submit"]) * 1000)
            lat["audit_run_ms"] = int((t_done - t_run0) * 1000) if t_run0 is not None else None
            lat["turn_complete_ms"] = int((max(t_done, rec["t_return"]) - rec["t_start"]) * 1000)
        rec["final"] = status

    def _collect_audits(self):
        """Ghi các audit ĐÃ xong theo thứ tự lượt (dừng ở audit đầu tiên chưa xong để giữ thứ tự). Không chờ."""
        while self._audits and self._audits[0]["future"].done():
            self._finalize_audit(self._audits.pop(0))

    def drain_audits(self, timeout_s=None):
        """Đợi mọi audit nền của phiên (hết phiên / hết job) rồi ghi vào trace theo thứ tự lượt. Quá hạn → audit_status=timeout
        (claims / questions rỗng, ghi rõ), kết quả về muộn sau đó không được ghi vào trace nữa."""
        limit = settings.audit_drain_timeout_s if timeout_s is None else timeout_s
        deadline = time.perf_counter() + limit
        while self._audits:
            rec = self._audits.pop(0)
            try:
                rec["future"].result(timeout=max(0.0, deadline - time.perf_counter()))
            except FutTimeout:
                self._finalize_audit(rec, "timeout", f"audit chưa xong sau {limit:.0f}s khi đợi kết thúc phiên")
                continue
            except Exception:
                pass                                   # lỗi audit: _finalize_audit ghi audit_status=error
            self._finalize_audit(rec)

    def _audit_candidates(self, tool_log):
        """Đối tượng ứng viên cho attribution claim (K12): sản phẩm đang bàn / đã bàn / trong giỏ / vừa báo giá lượt này.
        Chỉ để gắn target; KHÔNG quyết định câu được nhận diện thế nào."""
        skus = []
        for tc in tool_log:
            if tc.get("name") == "pricing.get_quote" and (tc.get("args") or {}).get("sku"):
                skus.append(tc["args"]["sku"])
        skus += ([self.focus] if self.focus else []) + list(self.cart) + list(self.discussed)
        out, seen = [], set()
        for sku in skus:
            par = mt._parent(sku)[0] if sku else None
            key = sku
            if not sku or key in seen or len(out) >= 8:
                continue
            seen.add(key)
            out.append({"ref": f"P{len(out) + 1}", "sku": sku, "name": product_name(sku),
                        "parent": par["sku"] if par else sku})
        return out

    def _resolve_candidate(self, name):
        for c in self.candidates:
            if fold(c["name"]) == fold(name):
                full = self.tools.call("crm.get_customer", phone=self.phone)
                self._bind(c["customer_id"], c["name"], c["honorific"], self.phone, {"sessions": c.get("sessions", []), "identities": {}})
                self.candidates = []
                return

    def _quote(self, sku, role="advised", basket=None):
        c = self.customer or {}
        q = public_view(self.tools.call("pricing.get_quote", sku=sku, customer_phone=c.get("phone"),
                                        address=self.known.get("address"), basket_skus=basket))
        inv = self.tools.call("inventory.check", sku=sku)
        promos = [a["promo_code"] for a in q.get("applied_promos", []) if a["promo_code"] not in STACKABLE_SKIP]
        names = []
        for code in promos:
            pr = next((x for x in mt.PROMOS if x["promo_code"] == code), None)
            if pr: names.append(f"{pr['name']} (đến {_ddmm(pr['end'])})")
        view = {"sku": sku, "name": product_name(sku), "list_price_vnd": q.get("list_price_vnd"), "final_price_vnd": q.get("final_price_vnd"),
                "promo_codes": promos, "promo_names": names, "freeship": q.get("freeship"),
                "expired_promos": [x.get("promo_code") if isinstance(x, dict) else x for x in q.get("expired_promos", [])],
                "in_stock": inv.get("in_stock"), "restock_expected": inv.get("restock_expected"),
                "discontinued": inv.get("discontinued"), "successor_sku": inv.get("successor_sku"),
                **({"stock_qty": inv["qty"]} if settings.arch == "target" and isinstance(inv.get("qty"), int) else {})}
        if settings.planner_variant == "b2_jev":
            # F1 (13/11, B2): tình trạng KM không áp dụng / đã hết hạn, nguyên văn từ pricing.get_quote (chỉ thêm trường; giá không đổi)
            pname = {x["promo_code"]: x.get("name") for x in mt.PROMOS}
            view["ineligible_promos"] = [{"code": x.get("promo_code"), "name": pname.get(x.get("promo_code")), "reason": x.get("reason")}
                                         for x in q.get("ineligible_promos") or [] if isinstance(x, dict)]
            view["expired_promo_names"] = [pname.get(x) for x in view["expired_promos"] if pname.get(x)]
            # F1b (13/11): có KM loại quà tặng đang áp dụng không (catalog/promotions.json type = gift)
            ptype = {x["promo_code"]: x.get("type") for x in mt.PROMOS}
            view["has_gift"] = any(ptype.get(c) == "gift" for c in promos)
        p, _ = mt._parent(sku)
        if p: view["attributes"] = {k: v for k, v in p["attributes"].items() if not str(k).startswith("_")}
        pr_end = next((x["end"] for x in mt.PROMOS if promos and x["promo_code"] == promos[0]), None)
        view["promo_end"] = pr_end
        if role in ("advised", "chosen"):
            self.quote = view
        par = p["sku"] if p else sku
        if par not in [mt._parent(d)[0]["sku"] for d in self.discussed if mt._parent(d)[0]]:
            self.discussed.append(sku)
        if q.get("final_price_vnd") and self.customer and self.customer.get("customer_id"):
            self.mem.add_quote(self.customer["customer_id"], self.session_id, sku, role, q.get("list_price_vnd"), q["final_price_vnd"],
                               promos[0] if promos else None, pr_end, self.today)
        return view

    def _recommend(self, text):
        f = fold(text)
        cat = next((c for w, c in CATEGORY_WORDS if w in f), None) or self.category
        if not cat:
            return None
        self.category = cat
        if cat == "gia-dung/may-loc-khong-khi" and not ({"has_children", "budget_vnd"} & set(self.known)):
            return "ASK_NEED"
        area, budget, kids = self.known.get("room_area_m2"), self.known.get("budget_vnd"), self.known.get("has_children")
        res = self.tools.call("catalog.search", category=cat)
        items = res.get("items") or []
        self.tools.log[-1]["result"] = {"total": len(items)}
        cands = []
        for it in items:
            a = it["attributes"]
            if it["list_price_vnd"] < 400000 or not self.tools.call("inventory.check", sku=it["sku"]).get("in_stock"):
                continue
            if area and a.get("room_area_m2") and a["room_area_m2"] < area:
                continue
            score = (2 if kids and a.get("child_safe_lock") else 0) - (1 if budget and it["list_price_vnd"] > budget * 1.1 else 0)
            cands.append((-score, it["list_price_vnd"], it["sku"]))
        return sorted(cands)[0][2] if cands else None

    def _why(self, branch, reason=""):
        """B7: ghi nhánh planner đã đi qua và lý do, để phân tích lỗi và làm feedback."""
        self.plan_why.append({"branch": branch, "reason": reason} if reason else {"branch": branch})

    def _order_status(self, facts):
        c = self.customer or {}
        r = self.tools.call("order.status", customer_phone=c.get("phone") or self.phone)
        return self._orders_view(r.get("orders", []), facts)

    def _orders_view(self, raw, facts):
        """View đơn cho câu trả lời từ kết quả order.status đã đọc (tách 12/11 để hành động read_order không gọi tool hai lần)."""
        r = {"orders": raw}
        facts["orders"] = [{**{k: o.get(k) for k in ("order_id", "sku", "status", "tracking", "created_on", "date", "estimated_delivery", "address")
                               if o.get(k) is not None}, "product": self._order_products(o),
                            "estimated_delivery_ddmm": _ddmm(o["estimated_delivery"]) if o.get("estimated_delivery") else None}
                           for o in r.get("orders", [])]
        for o in facts["orders"]:
            if not o.get("estimated_delivery") and o["order_id"] == self.known.get("order_id") and self.known.get("estimated_delivery"):
                o["estimated_delivery"] = self.known["estimated_delivery"]; o["estimated_delivery_ddmm"] = _ddmm(o["estimated_delivery"])
            if o["order_id"] == self.known.get("order_id") and self.known.get("address"):
                o["address"] = self.known["address"]
        return ["order_status"]

    def _ask_prior_contact(self, f, typed=None):
        """B3 (BTCL-016/017): khách nhắc lần trao đổi trước nhưng không tìm được lịch sử (vd chat fanpage rồi gọi hotline
        số khác) → xin SĐT / tài khoản đã dùng để tra lại, thay vì hỏi lại nhu cầu từ đầu. Tối đa 2 lần mỗi cuộc.
        typed (đích): refs.previous_contact của bộ hiểu thay PRIOR_REF_RX."""
        mentions = typed if typed is not None else bool(PRIOR_REF_RX.search(f))
        if self.focus is not None or (self.brief or {}).get("is_returning") or self.prior_contact_asked >= 2 \
                or not mentions:
            return []
        self.prior_contact_asked += 1
        self._why("prior_contact_unknown", f"lần hỏi {self.prior_contact_asked}")
        return ["ask_prior_contact"]

    def _policy_gap(self, text, f, asking=True, typed=None):
        """Hỏi hoàn/trả với thời hạn dài hơn mọi thời hạn hoàn/đổi/trả trong tài liệu (hoặc hỏi văn bản cho chính câu đó).
        typed (đích): bộ hiểu xác nhận khách hỏi chính sách đổi trả / hoàn tiền (thay REFUND_RX / "cam kết"); DUR_RX chỉ còn là
        parser thời hạn. Hỏi lại văn bản cho đúng khoảng trống đã nêu: asks return_policy / policy (thay DOC_REF_RX)."""
        if self.policy_gap and (typed if typed is not None else DOC_REF_RX.search(f)):
            return self.policy_gap if asking else None
        m = DUR_RX.search(f)
        if not m or not (typed if typed is not None else (REFUND_RX.search(f) or re.search(r"\bcam ket\b", f))):
            return None
        n, unit = m.group(1), m.group(2)
        num, num_txt = (int(n), n) if n.isdigit() else _NUM_WORD[n]
        asked_days = num * _UNIT[unit][0]
        hits = knowledge.search(text, k=3)
        windows = []
        for h in hits:
            for sent in re.split(r"(?<=[.;\n])\s*", fold(h["text"])):
                if re.search(r"\b(doi|tra|hoan)\b", sent):
                    windows += [int(x) * _UNIT[u][0] for x, u in re.findall(r"(\d+)\s*(ngay|thang)", sent)]
        if not windows or asked_days <= max(windows):
            return None
        return {"topic": f"cam kết hoàn tiền / trả hàng sau {num_txt} {_UNIT[unit][1]}",
                "policy": [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits[:2]]}

    def _cart_add(self, sku):
        if sku and sku not in self.cart and mt._parent(sku)[0]:
            par = mt._parent(sku)[0]["sku"]
            self.cart = [x for x in self.cart if mt._parent(x)[0]["sku"] != par] + [sku]

    def _resolve_variant(self, sku, text):
        p, v = mt._parent(sku)
        if not p or not p["variants"] or v:
            return sku
        found = find_variant(p["sku"], text, self.known.get("size"), self.known.get("color"))
        if found:
            return found
        # 10/11 (V3-018): D54 nhớ variant_sku khách đã chọn và được báo giá nhưng chưa lên đơn, để lần sau chốt đúng biến thể
        # mà không hỏi lại — nhưng trước đây chỉ size/màu được đọc lại. Dùng variant_sku nhớ được khi cùng sản phẩm cha và
        # không trái size/màu đã biết (khách nói size/màu khác trong cuộc này thì known đã đổi → không dùng bản nhớ).
        mem = self.known.get("variant_sku")
        mp, mv = mt._parent(mem) if mem else (None, None)
        if mv and mp and mp["sku"] == p["sku"] and \
                (self.known.get("size") is None or str(mv.get("size")).upper() == str(self.known["size"]).upper()) and \
                (self.known.get("color") is None or mv.get("color") == self.known["color"]):
            return mem
        return sku

    def _price_depends_on_size(self, sku, text):
        p, v = mt._parent(sku)
        if not p or not p["variants"] or v or self._resolve_variant(sku, text) != sku:
            return False
        return any(x.get("price_delta_vnd") for x in p["variants"]) or self._promo_depends_on_size(sku)

    def _promo_depends_on_size(self, sku):
        p, _ = mt._parent(sku)
        for pr in mt.PROMOS:
            if (p["sku"] in pr.get("applies_to", []) or any(p["category"].startswith(c) for c in pr.get("applies_to_categories", []))) \
                    and (pr.get("conditions") or {}).get("exclude_variant_size"):
                return True
        return False

    def _cart_quote(self, text):
        items = [self._resolve_variant(s, text) for s in self.cart]
        if settings.arch == "target":
            # BTC 11/2026: tổng / giá từng máy của giỏ từ pricing.quote_order (một máy được AIR-2ND-50, TRADE-IN tối đa một máy)
            for s in items:
                self._quote(s, "chosen")              # thông tin từng mẫu + giá một máy cho bộ nhớ (không basket)
            oq = self._quote_order([{"sku": s, "qty": 1} for s in items]) if items else None
            return self._cart_facts(oq) if oq else {"items": [], "total_vnd": None, "budget_vnd": self.known.get("budget_vnd")}
        qs = [self._quote(s, "chosen", basket=[x for x in items if x != s]) for s in items]
        return {"items": [{"name": q["name"], "final_price_vnd": q["final_price_vnd"], "promo_names": q["promo_names"],
                           **({"sku": q["sku"]} if settings.arch == "target" else {})} for q in qs],   # đích: ref từng món → báo giá của chính SKU
                "total_vnd": sum(q["final_price_vnd"] or 0 for q in qs), "budget_vnd": self.known.get("budget_vnd")}

    def _update_address(self, address, facts):
        if settings.arch == "target":
            return self._update_address_target(address, facts)
        if all(fold(o.get("address") or "") == fold(address) for o in self.orders_created):
            self._why("address_same", "địa chỉ trùng địa chỉ trong đơn, không gọi order.update")
            return self._plan_order("", facts)
        # đơn vừa tạo chưa có địa chỉ: khách đọc địa chỉ là hoàn tất yêu cầu đặt hàng, không phải ĐỔI địa chỉ → không qua cổng
        # (t-1110-rg: 10 ca V3 + RT-09 bị chặn nhầm, đơn mất địa chỉ). Chỉ đổi một địa chỉ đã có mới cần khách yêu cầu.
        if all(o.get("address") for o in self.orders_created) and not self._req_ok("change_order_address"):
            facts["old_address"] = self.orders_created[-1].get("address") or self.known.get("address") or ""
            return ["confirm_old_address"]
        self._req_done("change_order_address")
        self._why("address_update")
        from harness import tool_outcome
        done = []
        for o in self.orders_created:
            args = dict(order_id=o["order_id"], action="update_address", reason=f"địa chỉ mới: {address}")
            r = self.tools.call("order.update", **args)
            if tool_outcome.ok({"name": "order.update", "args": args, "result": r}):
                done.append(o["order_id"])
        if not done:
            # G1: không báo "đã cập nhật" khi tool không xác nhận (trước 10/11 kết quả order.update bị bỏ qua)
            return ["contract_error"]
        facts["address_update"] = {"orders": done, "address": address}
        return ["address_updated"]

    def _update_address_target(self, address, facts):
        """K01 (đích): tách HOÀN TẤT địa chỉ còn thiếu của đơn vừa đặt (tiếp tục yêu cầu đặt hàng đã thực hiện, không cần yêu
        cầu mới) khỏi THAY địa chỉ đã có (cần yêu cầu change_order_address có căn cứ, đúng đơn đích). Không sửa mọi đơn."""
        from harness import tool_outcome
        lacking = [o for o in self.orders_created if not o.get("address")]
        having = [o for o in self.orders_created if o.get("address") and fold(o["address"]) != fold(address)]
        if not lacking and not having:
            self._why("address_same", "địa chỉ trùng địa chỉ trong đơn, không gọi order.update")
            return self._plan_order("", facts)
        todo, req = [], None
        if lacking and self.reqs.done_orders_ok():
            todo += lacking
            self._why("address_complete", "bổ sung địa chỉ cho đơn vừa đặt (cùng yêu cầu đặt hàng)")
        if having:
            tgt = having[0] if len(having) == 1 else None
            req = self._req_ok("change_order_address", target={"type": "order", "order_id": tgt["order_id"]} if tgt else None,
                               unique_target=tgt is not None)
            if req is not None:
                oid = (req.get("target") or {}).get("order_id")
                pick = [o for o in having if o["order_id"] == oid] if oid else ([tgt] if tgt else [])
                if not pick:
                    facts["which_orders"] = [{"order_id": o["order_id"], "product": self._order_products(o)} for o in having]
                    return ["ask_which_order"]
                todo += pick
            elif not todo:
                facts["old_address"] = having[-1].get("address") or self.known.get("address") or ""
                return self._blocked_goals("change_order_address", facts, ["confirm_old_address"], orders=having)
        if not todo:
            return self._blocked_goals("place_order", facts, ["confirm_order"])
        if req:
            self.reqs.begin(req)
        done, statuses = [], []
        for o in todo:
            args = dict(order_id=o["order_id"], action="update_address", reason=f"địa chỉ mới: {address}")
            r = self.tools.call("order.update", **args)
            st = tool_outcome.classify({"name": "order.update", "args": args, "result": r})["status"]
            statuses.append(st)
            if st == "confirmed_success":
                done.append(o["order_id"])
                o["address"] = address                  # state đơn của cuộc gọi theo kết quả tool đã xác nhận
        if req:
            ok_req = any(o["order_id"] in done for o in todo if o in having)
            self.reqs.settle(req, "confirmed_success" if ok_req else "unresolved" if "unresolved" in statuses else "confirmed_failure")
        completed = [o for o in lacking if o["order_id"] in done and o in todo]
        if completed:
            # khách đọc địa chỉ để HOÀN TẤT đơn vừa đặt; bộ hiểu có thể ghi đó là place_order (đúng hợp đồng) — yêu cầu đó đã được
            # thực hiện bằng chính thao tác bổ sung địa chỉ này, không để mở rồi lượt sau thành "đặt thêm"
            from harness.request_state import _parents_of, _parent as par
            done_par = {par(s) for o in completed for s in (o.get("skus") or [o["sku"]])}
            for x in self.reqs.active("place_order"):
                if x["turn"] == self.reqs.turn and (x["target"] is None or _parents_of(x["target"]) <= done_par):
                    self.reqs.settle(x, "confirmed_success", {"continuation_of": completed[0]["order_id"], "via": "address_completion"})
        self.known["address"] = address if done else self.known.get("address")
        if not done:
            return ["contract_error"]
        facts["address_update"] = {"orders": done, "address": address}
        return ["address_updated"]

    def _plan_address_change_target(self, text, facts, address):
        """T01 (đích, mục 4.5): yêu cầu change_order_address CÓ CĂN CỨ, cho mọi đơn của khách (kể cả đơn phiên trước), chạy trước
        chính sách đổi/trả. Đơn đích: target của yêu cầu (O#) khớp ĐÚNG mã trong order.status(customer_phone = khách của phiên);
        không ref → chỉ khi khách có đúng một đơn; ref sai / nhiều đơn → hỏi đơn nào. Không có địa chỉ mới → xin địa chỉ. Một lần
        order.update; trạng thái theo kết quả tool. Không đọc known.address của đơn khác để trả lời. → goals (None nếu không có yêu cầu)."""
        from harness import tool_outcome
        r, why = self.reqs.select("change_order_address")
        if r is None and why == "no_request":
            return None
        self._addr_dispatched = True
        orders = self._customer_orders()
        if r is None:                                              # nhiều yêu cầu đổi địa chỉ khác đơn trong cùng lượt / hold
            if why in ("ambiguous_turn", "understanding_error", "input_truncated"):
                return ["ask_repeat"]
            facts["which_orders"] = [{"order_id": o["order_id"], "product": self._order_products(o)} for o in orders[-5:]]
            return ["ask_which_order"] if orders else ["order_not_found"]
        if not orders:
            return ["order_not_found"]
        oid = (r.get("target") or {}).get("order_id")
        o = next((x for x in orders if oid and x.get("order_id") == oid), None)
        unique = False
        if o is None:
            if oid is None and r["status"] != "needs_target" and len(orders) == 1:
                o, unique = orders[0], True
            else:
                self._why("order_target_unresolved", f"{r['id']}: {'ref không thuộc đơn của khách' if oid else r['status']}")
                facts["which_orders"] = [{"order_id": x["order_id"], "product": self._order_products(x)} for x in orders[-5:]]
                return ["ask_which_order"]
        if r["target"] is None:
            r["target"] = {"type": "order", "order_id": o["order_id"]}      # đơn duy nhất của khách: gắn để lượt sau xin địa chỉ
        mine = next((x for x in self.orders_created if x["order_id"] == o["order_id"]), None)
        current = (mine or {}).get("address") or o.get("address")
        if not address:
            self._why("address_change_missing_address", o["order_id"])
            facts["address_change"] = {"order_id": o["order_id"]}
            return ["ask_address"]
        if current and fold(current) == fold(address):
            self.reqs.settle(r, "confirmed_success", {"order_id": o["order_id"], "no_change": True})
            facts["order"] = {"order_id": o["order_id"], "product": self._order_products(o), "address": current,
                              "estimated_delivery_ddmm": _ddmm(o["estimated_delivery"]) if o.get("estimated_delivery") else None}
            return ["confirm_delivery_address"]
        req = self._req_ok("change_order_address", target={"type": "order", "order_id": o["order_id"]}, unique_target=unique, req_id=r["id"])
        if not req:
            return self._blocked_goals("change_order_address", facts, ["confirm_old_address"] if current else ["ask_which_order"],
                                       orders=orders) if current or orders else ["contract_error"]
        self.reqs.begin(req)
        args = dict(order_id=o["order_id"], action="update_address", reason=f"địa chỉ mới: {address}")
        res = self.tools.call("order.update", **args)
        st = tool_outcome.classify({"name": "order.update", "args": args, "result": res})["status"]
        self.reqs.settle(req, st, {"order_id": o["order_id"], "action": "update_address"})
        if st != "confirmed_success":
            self._why("address_change_" + st, o["order_id"])
            return ["contract_error"]
        if mine is not None:
            mine["address"] = address
        facts["address_update"] = {"orders": [o["order_id"]], "address": address}
        if o.get("estimated_delivery"):
            facts["address_update"]["estimated_delivery_ddmm"] = _ddmm(o["estimated_delivery"])
        goals = ["address_updated"]
        asks = set((self.u_turn or {}).get("asks") or [])
        if "delivery_time" in asks and not o.get("estimated_delivery"):
            # câu hỏi giao hàng độc lập vẫn được trả lời trong phạm vi nguồn có sẵn (tài liệu vận chuyển), không bị thao tác nuốt mất
            hits = knowledge.search(text, k=2)
            if hits:
                facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
                goals.append("policy_answer")
        return goals

    def _plan_order(self, text, facts):
        if settings.arch == "target":
            return self._plan_order_target(text, facts)
        c = self.customer or {}
        items = list(self.cart) or ([self.focus] if self.focus else [])
        if not items:
            return ["ask_product"]
        resolved = []
        for sku in items:
            r = self._resolve_variant(sku, text)
            p, v = mt._parent(r)
            if p and p["variants"] and not v:
                facts["need_variant_for"] = product_name(sku)
                return ["ask_variant"]
            resolved.append(r)
        new = [s for s in resolved if not any(s in (o.get("skus") or [o["sku"]]) for o in self.orders_created)]
        if not new:
            o = self.orders_created[-1]
            facts["order"] = {"order_id": o["order_id"], "total_vnd": o["total_vnd"], "estimated_delivery": o.get("estimated_delivery"),
                              "estimated_delivery_ddmm": _ddmm(o["estimated_delivery"]) if o.get("estimated_delivery") else None,
                              "payment": self.known.get("payment", "COD"), "address": self.known.get("address"),
                              "items": [product_name(s) for s in (o.get("skus") or [o["sku"]])]}
            return ["order_exists"]
        target = settings.arch == "target"
        wants_old = bool(((self.u_turn or {}).get("refs") or {}).get("previous_address")) if target \
            else bool(re.search(r"(dia chi cu|cho cu|nhu cu)", fold(text)))
        if not self.known.get("address") and self.expired.get("address") and wants_old:
            if self.old_addr_asked:
                self.known["address"] = self.expired["address"]
            else:
                self.old_addr_asked = True
                facts["old_address"] = self.expired["address"]
                return ["confirm_old_address"]
        payment = self.known.get("payment", "COD")
        # đích (BTC 11/2026): basket của get_quote không phân định đúng AIR-2ND-50 → giá đơn lấy từ pricing.quote_order;
        # get_quote (không basket) chỉ cho thông tin từng mẫu (tên, tồn kho, KM của một máy)
        quotes = [self._quote(s, "chosen", basket=None if target else [x for x in new if x != s]) for s in new]
        # E04 (ORDER_QTY): chỉ áp số lượng khi chốt đúng 1 SKU; nhiều SKU thì mỗi SKU 1 cái như cũ
        qty = 1
        if settings.order_qty and len(new) == 1 and target:
            # đích: số lượng từ observation có căn cứ, chỉ khi nói cùng hoặc sau lượt mở yêu cầu đặt hàng đang hiệu lực
            act = next((r for r in reversed(self.reqs.items) if r["kind"] == "place_order" and r["status"] in ("open", "conditional")), None)
            if act and self.qty_obs and self.qty_obs[0] >= act["turn"] and 1 <= self.qty_obs[1] <= 20:
                qty = self.qty_obs[1]
                self.known["qty"] = qty
        elif settings.order_qty and len(new) == 1:
            said = [text] + [h["text"] for h in reversed(self.history[-8:]) if h.get("role") == "customer"]
            qty = order_qty(said) or 1
            if qty > 1:
                self.known["qty"] = qty
        total = sum(q["final_price_vnd"] or 0 for q in quotes) * qty
        if any(q.get("in_stock") is False for q in quotes):
            bad = next(q for q in quotes if q.get("in_stock") is False)
            facts["quote"], facts["restock_expected"] = bad, bad.get("restock_expected")
            return ["out_of_stock"]
        if settings.planner_selector != "rules":
            if not self.known.get("address"):
                return ["ask_address"]
            if not self.known.get("payment"):
                return ["ask_payment"]
        cod_before = sum(o.get("total_vnd") or 0 for o in self.orders_created if o.get("payment") == "COD")
        if payment == "COD" and total + cod_before > 10_000_000:
            total += cod_before
            facts["cod_total_vnd"] = total; facts["cart"] = {"items": [{"name": q["name"], "final_price_vnd": q["final_price_vnd"]} for q in quotes], "total_vnd": total}
            return ["cod_limit"]
        self._req_total = total
        from harness.request_state import _parent as _rs_parent
        rev = {"units": [[q["sku"], q["final_price_vnd"]] for q in quotes], "qty": qty}
        req = self._req_ok("place_order", target={"type": "product", "skus": tuple(resolved)}, total=total,
                           in_stock=all(q.get("in_stock") is True for q in quotes), revision=rev)
        if not req:
            if target and len(quotes) == 1:
                facts.setdefault("quote", quotes[0])          # đổi giá / biến thể / số lượng: báo lại đúng giá hiện tại
            return self._blocked_goals("place_order", facts, ["confirm_order"]) if target else ["confirm_order"]
        self._req_done("place_order")
        if target:
            self.reqs.begin(req)
        goals = self._create_orders(quotes, new, qty, payment, facts, c)
        if target:
            st = "confirmed_success" if "order_created" in goals else "partial" if "order_partial" in goals \
                else "unresolved" if "order_unresolved" in goals else "confirmed_failure"
            self.reqs.settle(req, st, {"orders": [o["order_id"] for o in self.orders_created if o["sku"] in new]})
        return goals

    # ------------------------------------------------------------------ đích: executor đặt hàng lấy đối tượng từ YÊU CẦU (11/11)
    def _target_variant(self, sku, text):
        """Biến thể cho đối tượng của yêu cầu: size/màu khách nói TRONG LƯỢT này thắng biến thể cũ (ref sản phẩm ở mức cha,
        hoặc biến thể của đề nghị đã nêu); còn lại theo size/màu đã biết (parser find_variant)."""
        p, v = mt._parent(sku)
        said = (self.u_turn or {}).get("slots") or {}
        if p and v and (("size" in said and str(said["size"]).upper() != str(v.get("size")).upper())
                        or ("color" in said and said["color"] != v.get("color"))):
            sku = p["sku"]
        return self._resolve_variant(sku, text)

    def _pay_terms(self):
        """Thanh toán / địa chỉ sẽ ghi vào đơn KÈM NGUỒN (5.4/9.2): customer:tN | memory | default."""
        out = {}
        for k, default in (("payment", "COD"), ("address", None)):
            if self.known.get(k):
                out[k] = {"value": self.known[k], "src": self.known_src.get(k, "memory")}
            elif default:
                out[k] = {"value": default, "src": "default"}
        return out

    def _order_overlap(self, resolved):
        """Holdout mục 2 (duyệt 12/11): đơn đã tạo trong cuộc có CÙNG tập sản phẩm (`same`) hoặc CHỨA một phần sản phẩm của lựa
        chọn mới (`overlap`, so ở mức sản phẩm cha). → (đơn | None, quan hệ). Trước đây chỉ bắt `same`, nên đơn sau chứa lại sản
        phẩm đã đặt ở đơn trước bị tạo trùng (V3-058)."""
        from harness.request_state import _parent as par
        want = {par(x) for x in resolved}
        owned = [(o, {par(x) for x in (o.get("skus") or [o["sku"]])}) for o in reversed(self.orders_created)]
        same = next((o for o, have in owned if have == want), None)
        if same is not None:
            return same, "same"
        part = next((o for o, have in owned if have & want), None)
        return (part, "overlap") if part is not None else (None, None)

    def _ask_overlap_order(self, r, dup, resolved, facts):
        """Lựa chọn mới chứa sản phẩm đã có trong đơn vừa tạo: không ghi, giữ yêu cầu (parked) và hỏi khách có đặt thêm đơn gồm
        cả sản phẩm đó không. Khách đồng ý (đề nghị additional) thì mới tạo; không tự bỏ dòng trùng."""
        from harness.request_state import _parent as par
        have = {par(x) for x in (dup.get("skus") or [dup["sku"]])}
        overlap = [x for x in resolved if par(x) in have]
        self.reqs.park(r, "overlaps_existing_order")
        self._why("duplicate_order_check", f"{r['id']} chứa sản phẩm đã có trong đơn {dup['order_id']} → hỏi, không ghi")
        facts["additional_order"] = {"products": [product_name(x) for x in resolved], "order_id": dup["order_id"],
                                     "overlap": [product_name(x) for x in overlap]}
        facts["proposal"] = {"skus": tuple(resolved), "names": [product_name(x) for x in resolved], "additional": True}
        return self._order_exists_goals(dup, facts) + ["ask_additional_order"]

    def _order_exists_goals(self, o, facts):
        facts["order"] = {"order_id": o["order_id"], "total_vnd": o.get("total_vnd"), "estimated_delivery": o.get("estimated_delivery"),
                          "estimated_delivery_ddmm": _ddmm(o["estimated_delivery"]) if o.get("estimated_delivery") else None,
                          "payment": o.get("payment"), "address": o.get("address"),
                          "items": [product_name(s) for s in (o.get("skus") or [o["sku"]])]}
        return ["order_exists"]

    def _ask_product_target(self, r, facts):
        """Yêu cầu đặt hàng chưa rõ đối tượng (ref sai / không ref mà mơ hồ): KHÔNG ghi. Một ứng viên → xin xác nhận ĐÚNG sản
        phẩm đó (đề nghị có đối tượng); nhiều → hỏi chọn; không có → hỏi sản phẩm."""
        from harness.request_state import _parent as par
        cands = list(dict.fromkeys(par(x) for x in list(self.turn_mentioned) + ([self.focus] if self.focus else []) + list(self.cart) if x))[:3]
        self._why("order_target_unresolved", f"{r['id']}: {r['status']}, {len(cands)} ứng viên")
        if len(cands) == 1:
            facts["proposal"] = {"skus": (cands[0],), "names": [product_name(cands[0])]}
            return ["confirm_order"]
        if cands:
            facts["which_products"] = [product_name(x) for x in cands]
            return ["ask_which_product"]
        return ["ask_product"]

    def _plan_order_target(self, text, facts):
        """Đặt hàng trên cấu hình đích (mục 4.1/4.2/9.1): chọn đúng MỘT yêu cầu còn hiệu lực; đối tượng = target của yêu cầu
        (hoặc lựa chọn không mơ hồ khi yêu cầu không có ref) — KHÔNG đọc cart/focus làm payload; tồn kho / báo giá chỉ cho đối tượng
        đó; ghi bằng chính request ID; giỏ / mẫu đang bàn / known không liên quan không đổi payload."""
        from harness.request_state import RequestState, _parent as par
        c = self.customer or {}
        r, why = self.reqs.select("place_order")
        if r is None:
            if why == "multi_request":
                act = self.reqs.active("place_order")
                skus = tuple(dict.fromkeys(par(s) for x in act for s in ((x.get("target") or {}).get("skus") or ())))
                self._why("request_multi", ", ".join(x["id"] for x in act) + ": nhiều yêu cầu đặt hàng khác đối tượng → hỏi, không gộp")
                if len(skus) < 2:
                    return ["ask_which_product"] if skus else ["ask_product"]
                facts["multi_request"] = {"products": [product_name(s) for s in skus]}
                facts["proposal"] = {"skus": skus, "names": [product_name(s) for s in skus]}
                # giá khi lên CHUNG một đơn (quote_order phân bổ KM theo đơn vị) đọc cho khách trước khi xin xác nhận: đồng ý lượt sau
                # mới đúng nội dung đã nghe (revision của đề nghị = báo giá này)
                oq = self._quote_order([{"sku": x, "qty": 1} for x in skus])
                if oq is not None:
                    facts["cart"] = self._cart_facts(oq)
                    return ["cart_total", "ask_multi_request"]
                return ["ask_multi_request"]
            if why in ("ambiguous_turn", "understanding_error", "input_truncated"):
                return ["ask_repeat"]
            self._req_why = why
            self._why("request_blocked", f"place_order: {why}")
            if self.orders_created:
                return self._order_exists_goals(self.orders_created[-1], facts)
            sel = RequestState.unambiguous_selection(self)
            if sel:
                facts["proposal"] = {"skus": sel, "names": [product_name(x) for x in sel]}
            return ["confirm_order"]
        if r["status"] == "needs_target" or r["target"] is None:
            sel = None if r["status"] == "needs_target" else RequestState.unambiguous_selection(self, r.get("inherit"))
            if sel is None:
                return self._ask_product_target(r, facts)
            skus, picked = tuple(sel), True
        else:
            skus, picked = tuple(r["target"]["skus"]), False
        resolved = []
        for sku in skus:
            rv = self._target_variant(sku, text)
            p, v = mt._parent(rv)
            if p and p["variants"] and not v:
                facts["need_variant_for"] = product_name(sku)
                return ["ask_variant"]
            resolved.append(rv)
        if not r.get("additional"):
            dup, rel = self._order_overlap(resolved)
            if dup is not None and rel == "overlap":
                return self._ask_overlap_order(r, dup, resolved, facts)
            if dup is not None:
                u = self.u_turn or {}
                completes = bool(set(u.get("slots") or {}) & {"address", "payment"}) or bool((u.get("refs") or {}).get("previous_address"))
                if completes:
                    # khách đọc thêm thông tin cho ĐƠN VỪA ĐẶT cùng tập sản phẩm: là hoàn tất đơn đó, không tạo đơn mới
                    self.reqs.settle(r, "confirmed_success", {"continuation_of": dup["order_id"]})
                    self._why("order_continuation", f"{r['id']} → {dup['order_id']}")
                    return self._order_exists_goals(dup, facts)
                # cùng sản phẩm với đơn đã tạo mà không có thông tin bổ sung: có thể là xác nhận lặp hoặc đặt THÊM một đơn — hợp đồng
                # chưa phân biệt được → không ghi, hỏi rõ; khách đồng ý thì mới tạo (không chặn hẳn yêu cầu đặt thêm hợp lệ)
                self.reqs.park(r, "same_products_as_existing_order")
                self._why("duplicate_order_check", f"{r['id']} trùng sản phẩm đơn {dup['order_id']} → hỏi đặt thêm, không ghi")
                facts["additional_order"] = {"products": [product_name(x) for x in resolved], "order_id": dup["order_id"]}
                facts["proposal"] = {"skus": tuple(resolved), "names": [product_name(x) for x in resolved], "additional": True}
                return self._order_exists_goals(dup, facts) + ["ask_additional_order"]
        facts["proposal"] = {"skus": tuple(resolved), "names": [product_name(x) for x in resolved]}
        quotes = [self._quote(s, "chosen") for s in resolved]
        qty = 1
        if settings.order_qty and len(resolved) == 1 and self.qty_obs and self.qty_obs[0] >= r["turn"] and 1 <= self.qty_obs[1] <= 20:
            qty = self.qty_obs[1]                     # số lượng từ observation có căn cứ, nói cùng / sau lượt mở yêu cầu
            self.known["qty"] = qty
        goals = self._order_target(facts, c, r, resolved, quotes, qty, self._pay_terms(), unique=picked)
        parked = self.reqs.parked_now("place_order")
        if parked and not any(question_slot([g], facts) for g in goals):
            names = [self.reqs._target_name(x["target"]) for x in parked if x.get("target")]
            if names:
                facts["parked_request"] = {"products": names}
                goals = goals + ["ask_parked_request"]
        return goals

    # ------------------------------------------------------------------ BTC 11/2026: đơn nhiều đơn vị trên cấu hình đích
    @staticmethod
    def _order_products(o):
        """Tên MỌI sản phẩm của một đơn (BTC 11/2026: đơn nhiều dòng có `lines`; trường `sku` cấp đơn chỉ là dòng đầu)."""
        skus = [ln.get("sku") for ln in o.get("lines") or [] if ln.get("sku")] or list(o.get("skus") or []) \
            or ([o["sku"]] if o.get("sku") else [])
        return ", ".join(dict.fromkeys(product_name(s) for s in skus)) or None

    def _cart_facts(self, oq):
        """Giỏ theo TỪNG đơn vị từ pricing.quote_order (hai máy cùng SKU có thể khác giá) — không nhân một giá cho số lượng."""
        names = {x["promo_code"]: x["name"] for x in mt.PROMOS}
        items = [{"sku": u["sku"], "name": product_name(u["sku"]), "final_price_vnd": u["final_price_vnd"],
                  "promo_names": [names.get(a["promo_code"], a["promo_code"]) for a in u.get("applied_promos") or []
                                  if a.get("promo_code") not in STACKABLE_SKIP]} for u in oq["units"]]
        return {"items": items, "total_vnd": oq["total_vnd"], "budget_vnd": self.known.get("budget_vnd")}

    def _quote_order(self, lines):
        """Một nguồn báo giá cho đơn (BTC pricing.quote_order). → (result | None). Response hỏng → None (không đoán giá)."""
        from harness import tool_outcome
        c = self.customer or {}
        phone = c.get("phone") or self.phone or getattr(self, "contact_phone", None)
        r = self.tools.call("pricing.quote_order", lines=lines, customer_phone=phone, address=self.known.get("address"))
        if not tool_outcome.ok({"name": "pricing.quote_order", "args": {"lines": lines}, "result": r}):
            self._why("quote_order_invalid", str((r or {}).get("error") if isinstance(r, dict) else "no_response")[:40])
            return None
        return r

    def _order_target(self, facts, c, r, resolved, quotes, qty, terms, unique=False):
        """Tạo đơn trên cấu hình đích theo hợp đồng BTC 11/2026, cho ĐÚNG yêu cầu r (đã select/resolve):
        - giá / phân bổ KM / tổng lấy từ pricing.quote_order (từng đơn vị), không tự tính lại công thức KM;
        - tồn kho theo SỐ LƯỢNG đặt; - MỘT order.create cho cả đối tượng (lines; một đơn vị → dạng sku cũ), một order_id;
        - snapshot thực thi (req_id, đối tượng, đơn vị, số lượng, thanh toán / địa chỉ kèm nguồn) gắn vào bản ghi yêu cầu; payload
          dựng TỪ snapshot; quyền ghi kiểm bằng chính request ID;
        - price_mismatch (expected_units): KHÔNG tự sửa giá rồi tạo lại — báo giá lại, revision cũ hết hiệu lực, xin xác nhận;
        - timeout / transport → unresolved, không tạo lại."""
        from harness import tool_outcome
        if settings.jev_write_gate and self.proxy_caller:
            self._why("order_identity_blocked", "proxy_claim")
            return ["refuse_other_customer"]
        if settings.jev_write_gate and self.contact_phone and not self.phone and not (self.customer or {}).get("phone"):
            self._why("order_identity_blocked", "phone_claim chưa xác minh")
            facts["handoff"] = self._handoff(self.turn_text, "khac")
            self.outcome = "chuyen_may"
            return ["handoff"]
        new = list(resolved)
        payment = (terms.get("payment") or {}).get("value") or "COD"
        line_qty = {line["sku"]: line["qty"] for line in r.get("lines") or []} if r.get("semantic") else {}
        n_of = {s: line_qty.get(s, qty if len(new) == 1 else 1) for s in new}
        for q in quotes:
            stock = q.get("stock_qty")
            if q.get("in_stock") is False or (isinstance(stock, int) and stock < n_of.get(q["sku"], 1)):
                facts["quote"], facts["restock_expected"] = q, q.get("restock_expected")
                self._why("stock_insufficient", f"{q['sku']}: cần {n_of.get(q['sku'], 1)}, tồn {stock}")
                return ["out_of_stock"]
        lines = [{"sku": s, "qty": n_of[s]} for s in new]
        oq = self._quote_order(lines)
        if oq is None:
            return ["contract_error"]
        units = [(u["sku"], u["final_price_vnd"]) for u in oq["units"]]
        total = oq["total_vnd"]
        if len(units) > 1:
            facts["cart"] = self._cart_facts(oq)
        cod_before = sum(o.get("total_vnd") or 0 for o in self.orders_created if o.get("payment") == "COD")
        if payment == "COD" and total + cod_before > 10_000_000:
            facts["cod_total_vnd"] = total + cod_before
            return ["cod_limit"]
        self._req_total = total
        rev = {"units": sorted(units), "qty": qty, **{k: v for k, v in terms.items() if k in ("payment", "address")}}
        req = self._req_ok("place_order", target={"type": "product", "skus": tuple(resolved)}, total=total, in_stock=True, revision=rev,
                           req_id=r["id"], unique_target=unique)
        if not req:
            if len(quotes) == 1 and len(units) == 1:
                facts.setdefault("quote", quotes[0])          # đổi giá / biến thể / số lượng: báo lại đúng giá hiện tại
            goals = self._blocked_goals("place_order", facts, ["confirm_order"])
            return (["cart_total"] + goals) if "cart" in facts and goals == ["confirm_order"] else goals
        # snapshot thực thi gắn vào CHÍNH bản ghi yêu cầu (không phải ledger thứ hai); LLM không sửa; payload dựng từ đây
        snap = {"req_id": req["id"], "skus": list(new), "units": [list(u) for u in units], "qty": qty, "total_vnd": total,
                "payment": terms.get("payment"), "address": terms.get("address"),
                "quote_ref": {"tool": "pricing.quote_order", "total_vnd": total}}
        req["snapshot"] = snap
        payment = snap["payment"]["value"] if snap.get("payment") else "COD"
        address = (snap.get("address") or {}).get("value")
        self.reqs.begin(req)
        phone = c.get("phone") or self.phone or getattr(self, "contact_phone", None) or ""
        if any((phone, s) in self.unresolved_writes or self.known.get("unresolved_order_sku") == s for s in new):
            self._why("order_create_blocked_unresolved", ",".join(new))
            facts["unresolved_order"] = {"product": ", ".join(product_name(s) for s in new)}
            self.reqs.settle(req, "unresolved", {"reason": "previous_create_unresolved"})
            return ["order_unresolved"]
        if len(units) == 1:
            args = dict(customer_phone=phone, sku=units[0][0], qty=1, price_vnd=units[0][1], payment=payment, address=address)
            olines = [{"sku": units[0][0], "qty": 1, "price_vnd": units[0][1]}]
        else:
            olines = []
            for sku, price in units:                       # giữ thứ tự đơn vị; gộp đơn vị liền kề CÙNG SKU CÙNG GIÁ
                if olines and olines[-1]["sku"] == sku and olines[-1]["price_vnd"] == price:
                    olines[-1]["qty"] += 1
                else:
                    olines.append({"sku": sku, "qty": 1, "price_vnd": price})
            args = dict(customer_phone=phone, lines=olines, payment=payment, address=address)
        r = self.tools.call("order.create", **args)
        status = tool_outcome.classify({"name": "order.create", "args": args, "result": r})["status"]
        if status == "unresolved":
            for s in new:
                self.unresolved_writes.add((phone, s))
            self.known["unresolved_order_sku"] = new[0]
            self._why("order_outcome_unresolved", ",".join(new))
            facts["unresolved_order"] = {"product": ", ".join(product_name(s) for s in new)}
            self.reqs.settle(req, "unresolved")
            return ["order_unresolved"]
        if status != "confirmed_success":
            err = (r or {}).get("error") if isinstance(r, dict) else None
            self.reqs.settle(req, "confirmed_failure", {"reason": err})
            if err == "price_mismatch":
                # giá / phân bổ đã đổi so với lúc khách đồng ý: không tự thay giá rồi tạo lại; báo lại và xin xác nhận mới
                self._why("price_mismatch", "báo giá lại theo pricing.quote_order, xin khách xác nhận")
                oq2 = self._quote_order(lines)
                if oq2 is None:
                    return ["contract_error"]
                if len(oq2["units"]) > 1:
                    facts["cart"] = self._cart_facts(oq2)
                    return ["cart_total", "confirm_new_price"]
                facts["quote"] = self._quote(new[0], "chosen")
                return ["quote", "confirm_new_price"]
            if err == "out_of_stock":
                facts["quote"] = quotes[0] if len(quotes) == 1 else None
                facts["restock_expected"] = (r or {}).get("restock_expected")
                return ["out_of_stock"]
            if err == "cod_limit_exceeded":
                facts["cod_total_vnd"] = total
                return ["cod_limit"]
            facts["order_error"] = err
            return ["order_failed"]
        rec = {"order_id": r["order_id"], "sku": new[0], "skus": list(new), "lines": olines, "total_vnd": r["total_vnd"],
               "price_vnd": units[0][1], "payment": payment, "address": args.get("address"), "status": "created",
               **({"estimated_delivery": r["estimated_delivery"]} if r.get("estimated_delivery") else {})}
        self.orders_created.append(rec)
        facts["order"] = {"order_id": r["order_id"], "total_vnd": r["total_vnd"], "estimated_delivery": r.get("estimated_delivery"),
                          "estimated_delivery_ddmm": _ddmm(r["estimated_delivery"]) if r.get("estimated_delivery") else None,
                          "payment": payment, "address": address,
                          "items": [product_name(ln["sku"]) + (f" x{ln['qty']}" if ln["qty"] > 1 else "") for ln in olines],
                          # D2 (13/11, B2): khách chưa chọn thanh toán → vẫn COD như tool mặc định, câu xác nhận nói rõ
                          **({"payment_default": True} if (snap.get("payment") or {}).get("src") == "default"
                             and settings.planner_variant == "b2_jev" else {})}
        self.reqs.settle(req, "confirmed_success", {"orders": [r["order_id"]]})
        self._why("order_terms_source", f"payment={payment} ({(snap.get('payment') or {}).get('src')}), "
                                        f"address={'có' if address else 'thiếu'} ({(snap.get('address') or {}).get('src', '-')})")
        sku = new[0]
        self.known["product_chosen"] = sku
        self.known["order_id"] = r["order_id"]
        if r.get("estimated_delivery"):
            self.known["estimated_delivery"] = r["estimated_delivery"]
        if sku != mt._parent(sku)[0]["sku"]:
            self.known["variant_sku"] = sku
        self.outcome = "chot_don"
        goals = ["order_created"]
        if not phone:
            goals.append("ask_phone")
        elif not address:
            goals.append("ask_address")
        return goals

    def _create_orders(self, quotes, new, qty, payment, facts, c):
        made = []
        # D13 (02/11, SAMPLE-06): kênh chat/Zalo chưa có SĐT → ToolBox bỏ đối số None nên order.create thiếu customer_phone
        # và mock báo tool_exception. Vẫn lên đơn (khách đã chốt) với SĐT rỗng, rồi xin SĐT ngay để shipper liên hệ.
        phone = c.get("phone") or self.phone or getattr(self, "contact_phone", None) or ""
        from harness import tool_outcome
        for q in quotes:
            args = dict(customer_phone=phone, sku=q["sku"], qty=qty, price_vnd=q["final_price_vnd"],
                        promo_code=(q["promo_codes"] or [None])[0], payment=payment, address=self.known.get("address"),
                        basket_skus=[x for x in new if x != q["sku"]] or None)
            status = "unresolved"
            if (phone, q["sku"]) in self.unresolved_writes or self.known.get("unresolved_order_sku") == q["sku"]:
                # cụm 2: nhớ qua phiên (memory) — cuộc sau cũng không tạo lại khi lần trước chưa rõ kết quả
                # G1 (FINAL 10/11): lần tạo trước chưa rõ kết quả → không tạo lại tự động (có thể trùng đơn), chờ nhân viên đối soát
                self._why("order_create_blocked_unresolved", q["sku"])
                r = None
            else:
                r = self.tools.call("order.create", **args)
                if r.get("error") == "price_mismatch" and "expected_price_vnd" in r:      # mock cũ; mock 11/2026 trả expected_units → không tự sửa giá
                    args["price_vnd"] = r["expected_price_vnd"]; r = self.tools.call("order.create", **args)
                status = tool_outcome.classify({"name": "order.create", "args": args, "result": r})["status"]
                if status == "unresolved":
                    self.unresolved_writes.add((phone, q["sku"]))
                    self.known["unresolved_order_sku"] = q["sku"]
                    self._why("order_outcome_unresolved", q["sku"])
            if status != "confirmed_success":
                if status == "unresolved":
                    facts["unresolved_order"] = {"product": product_name(q["sku"])}
                else:
                    facts["order_error"] = r["error"]
                if made:
                    self.orders_created += made
                    self.known['order_id'] = made[0]['order_id']
                    self.known['product_chosen'] = made[0]['sku']
                    facts['partial_orders'] = [{'order_id': o['order_id'], 'total_vnd': o['total_vnd']} for o in made]
                    return ['order_partial']
                return ["order_unresolved" if status == "unresolved" else "order_failed"]
            made.append({**r, "sku": q["sku"], "price_vnd": args["price_vnd"], "payment": payment, "address": args["address"]})
        self.orders_created += made
        facts["order"] = {"order_id": ", ".join(o["order_id"] for o in made), "total_vnd": sum(o["total_vnd"] for o in made),
                          "estimated_delivery": made[0].get("estimated_delivery"),
                          "estimated_delivery_ddmm": _ddmm(made[0]["estimated_delivery"]) if made[0].get("estimated_delivery") else None,
                          "payment": payment,
                          "address": self.known.get("address"), "items": [product_name(o["sku"]) for o in made]}
        sku = made[0]["sku"]
        self.known["product_chosen"] = sku
        self.known["order_id"] = made[0]["order_id"]
        if made[0].get("estimated_delivery"):
            self.known["estimated_delivery"] = made[0]["estimated_delivery"]
        if sku != mt._parent(sku)[0]["sku"]:
            self.known["variant_sku"] = sku
        self.outcome = "chot_don"
        goals = ["order_created"]
        if not phone:
            goals.append("ask_phone")
        elif not self.known.get("address"):
            goals.append("ask_address")
        return goals

    def _customer_orders(self):
        c = self.customer or {}
        r = self.tools.call("order.status", customer_phone=c.get("phone") or self.phone)
        return r.get("orders", [])

    def _plan_order_change(self, text, facts, action_override=None):
        if settings.arch == "target":
            return self._plan_order_change_target(text, facts)
        orders = self._customer_orders()
        if not orders:
            hits = knowledge.search(text, k=2)
            facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
            return ["policy_answer"] if hits else ["order_not_found"]
        want = self.known.get("variant_sku") or self.known.get("product_chosen")
        o = next((x for x in reversed(orders) if want and x.get("sku") == want), orders[-1])
        f = fold(text)
        od = o.get("created_on") or o.get("date")
        from harness.planner_policy import exchange_window
        # cụm 2 (10/11): một cách tính hạn cho MỌI selector (trước đây rules dùng heuristic ngày đặt + 11)
        decision = exchange_window(o, self.today) if od else None
        if decision is not None:
            facts["exchange_policy"] = decision
        if decision is not None and decision["eligible"] is False:
            facts["old_order"] = {"order_id": o["order_id"], "product": product_name(o["sku"]), "date": od}
            if not self.window_told:
                self.focus, self.focus_by = o["sku"], "memory"
            return ["WINDOW_PASSED"]
        if action_override is None and re.search(r"\bdia chi\b", f) and not RETURN_RX.search(f) and not re.search(r"\b(size|co|mau)\b", f) and not find_products(text):
            eta = self.known.get("estimated_delivery") if o["order_id"] == self.known.get("order_id") else None
            facts["order"] = {"order_id": o["order_id"], "product": product_name(o["sku"]), "address": self.known.get("address") or o.get("address"),
                              "estimated_delivery_ddmm": _ddmm(eta) if eta else None}
            return ["confirm_delivery_address"]
        if decision is not None and decision["eligible"] is None:
            # G2 + cụm 2: chưa xác định được hạn (thiếu ngày nhận, giữa hai mốc chắc chắn) → không tạo yêu cầu đổi HAY trả
            # (trước đây chỉ chặn trả hàng); trả lời theo chính sách, không ghi.
            self._why("exchange_window_undetermined", o["order_id"])
            hits = knowledge.search("thời hạn đổi trả tính từ ngày nhận hàng", k=2)
            facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
            return ["policy_answer"] if hits else ["contract_error"]
        if action_override is None and self.u_turn is not None and not self.u_turn.get("error"):
            # kiến trúc đích: trả hay đổi theo yêu cầu bộ hiểu thống nhất, không theo RETURN_RX
            ureq = set(self.u_turn.get("requests") or [])
            if "return" in ureq and "exchange" not in ureq:
                action_override = "return"
            elif "exchange" in ureq:
                action_override = "exchange"
        if action_override == "return" or (action_override is None and RETURN_RX.search(f)):
            key = (o["order_id"], "return", None)
            if key in self.updates_done:
                facts["update"] = self.updates_done[key]
                return ["order_updated"]
            if not self._req_ok("return", "exchange"):
                return self._req_policy(text, facts)
            r = self.tools.call("order.update", order_id=o["order_id"], action="return", reason="khach yeu cau tra hang")
            self._req_done("return", "exchange")
            if not r.get("error"):
                self.updates_done[key] = public_view(r)
        else:
            parent, ov = mt._parent(o["sku"])
            m = None
            other = [s for s in find_products(text) if s != parent["sku"]]
            if other:
                new_sku = find_variant(other[0], text, None, None) or other[0]
                action = "exchange_product"
            else:
                m = re.search(r"(?:đổi|lên|sang|lấy|thành)\s*(?:size|cỡ|số)?\s*(\d{2}|xs|s|m|l|xl|xxl)\b", text.lower())
                if not m and self.updates_done:
                    facts["update"] = list(self.updates_done.values())[-1]
                    return ["order_updated"]
                size = m.group(1).upper() if m else self.pending_size
                if not ov or not size or str(size) == str(ov["size"]).upper():
                    facts["current_variant"] = product_name(o["sku"])
                    return ["ask_new_size"]
                self.pending_size = size
                new_sku = next((v["variant_sku"] for v in parent["variants"] if str(v["size"]).upper() == size and v["color"] == ov["color"]), None)
                if not new_sku:
                    return ["ask_variant"]
                action = "exchange_size"
            key = (o["order_id"], action, new_sku)
            if key in self.updates_done:
                facts["update"] = self.updates_done[key]
                return ["order_updated"]
            if not re.search(r"(lam thu tuc|doi (cho|giup|luon)|dong y|ok|duoc|chot)", f) and m and "?" in text:
                facts["exchange_preview"] = {"order_id": o["order_id"], "new_variant": product_name(new_sku),
                                             "in_stock": self.tools.call("inventory.check", sku=new_sku).get("in_stock")}
                hits = knowledge.search("đổi size phí lần đầu", k=1)
                facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
                return ["exchange_offer"]
            if not self._req_ok("exchange", "return"):
                return self._req_policy(text, facts)
            r = self.tools.call("order.update", order_id=o["order_id"], action=action, new_variant_sku=new_sku)
            self._req_done("exchange", "return")
            if not r.get("error"):
                self.updates_done[key] = public_view(r)
        from harness import tool_outcome
        status = tool_outcome.classify({"name": "order.update", "args": {"order_id": o["order_id"], "action": key[1]}, "result": r})["status"]
        if status == "unresolved":
            self.updates_done.pop(key, None)
            self._why("order_update_unresolved", o["order_id"])
            return ["contract_error"]          # G1: không biết yêu cầu đã tạo chưa → không báo đã tạo, không báo thất bại
        if r.get("error"):
            facts["order_error"] = r["error"]
            if r.get("restock_expected"): facts["restock_expected"] = r["restock_expected"]
            return ["out_of_stock" if "out_of_stock" in r["error"] else "order_failed"]
        facts["update"] = public_view(r)
        return ["order_updated"]

    def _plan_order_change_target(self, text, facts):
        """Đổi / trả trên cấu hình đích (K05/K06): loại thao tác theo yêu cầu có căn cứ của bộ hiểu (không RETURN_RX, không regex
        size, không regex 'hỏi hay chốt'); đơn đích theo target_ref (O#) nếu có; quyền ghi theo request_state đúng LOẠI;
        trạng thái theo kết quả tool."""
        from harness import tool_outcome
        from harness.planner_policy import exchange_window
        u = self.u_turn or {}
        reqs, asks = set(u.get("requests") or []), set(u.get("asks") or [])
        if self._addr_dispatched and not (reqs & {"exchange", "return"}) \
                and not any(self.reqs.has_active(k) for k in ("exchange", "return")):
            return []        # lượt này chỉ đổi địa chỉ (T01 đã xử lý): không đi qua hạn đổi trả / đọc chính sách không liên quan
        orders = self._customer_orders()
        if not orders:
            hits = knowledge.search(text, k=2)
            facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
            return ["policy_answer"] if hits else ["order_not_found"]
        # đơn đích: mã ứng viên khách nhắm (O#) trong lượt, hoặc target của yêu cầu đổi/trả còn hiệu lực; chỉ tự chọn khi khách
        # có ĐÚNG MỘT đơn. Nhiều đơn mà chưa rõ → hỏi khách đơn nào (không tự lấy đơn mới nhất / đơn khớp sản phẩm đang bàn).
        ref_oid = None
        for it in u.get("request_items") or []:
            t = self.reqs.refmap.get(it.get("target_ref")) if it.get("target_ref") else None
            if it["kind"] in ("exchange", "return", "change_order_address") and t and t.get("type") == "order":
                ref_oid = t["order_id"]
        if ref_oid is None:
            prev = next((r for r in reversed(self.reqs.items) if r["kind"] in ("exchange", "return") and r["status"] in ("open", "conditional")
                         and (r.get("target") or {}).get("type") == "order"), None)
            ref_oid = (prev or {}).get("target", {}).get("order_id") if prev else None
        unique = len(orders) == 1
        o = next((x for x in orders if ref_oid and x.get("order_id") == ref_oid), None) or (orders[0] if unique else None)
        if o is None:
            if (reqs & {"exchange", "return", "change_order_address"}) or any(self.reqs.has_active(k) for k in ("exchange", "return")) \
                    or "delivery_address" in asks:
                facts["which_orders"] = [{"order_id": x["order_id"], "product": product_name(x["sku"]) if x.get("sku") else None}
                                         for x in orders[-5:]]
                self._why("order_target_unresolved", "nhiều đơn, khách chưa nói rõ đơn nào → hỏi lại, không ghi")
                return ["ask_which_order"]
            return self._req_policy(text, facts)                      # hỏi chung về đổi trả, không gắn đơn nào
        wants_change = bool(reqs & {"exchange", "return"}) or any(self.reqs.has_active(k) for k in ("exchange", "return"))
        if wants_change and len({ln.get("sku") for ln in o.get("lines") or []}) > 1:
            # Giới hạn API BTC 11/2026: order.update chỉ nhận order_id, chưa có tham số chọn MỘT món trong đơn nhiều dòng →
            # không tự chọn món, không tự chia tiền hoàn, không nói đã đổi/trả một món; chuyển nhân viên xử lý đúng món.
            self._why("multi_line_order_change_limit", o["order_id"])
            facts["handoff"] = self._handoff(text, "khac")
            self.open_questions.append(self._record_view(text)[:200])
            self.outcome = "chuyen_may"
            return ["handoff"]
        od = o.get("created_on") or o.get("date")
        decision = exchange_window(o, self.today) if od else None
        if decision is not None:
            facts["exchange_policy"] = decision
        if decision is not None and decision["eligible"] is False:
            facts["old_order"] = {"order_id": o["order_id"], "product": self._order_products(o), "date": od}
            if not self.window_told:
                self.focus, self.focus_by = o["sku"], "memory"
            return ["WINDOW_PASSED"]
        kinds = reqs & {"exchange", "return"}
        active = [k for k in ("exchange", "return") if self.reqs.has_active(k)]
        kind = "return" if kinds == {"return"} else "exchange" if kinds == {"exchange"} else None
        if kinds == {"exchange", "return"} or (kind is None and len(active) == 2):
            self._why("exchange_return_conflict", "khách nói cả đổi và trả → hỏi rõ, không ghi")
            return ["ask_exchange_or_return"]
        if kind is None and len(active) == 1:
            kind = active[0]                           # yêu cầu còn hiệu lực từ lượt trước (vd lượt này chỉ đọc size)
        if kind is None:
            if "delivery_address" in asks:
                # CHỈ ĐỌC: địa chỉ của CHÍNH đơn này (bản ghi đơn trong cuộc hoặc order.status) — không đọc known.address của đơn khác.
                # Yêu cầu đổi địa chỉ có căn cứ đi dispatch T01, không vào nhánh đọc này.
                mine = next((x for x in self.orders_created if x["order_id"] == o["order_id"]), None)
                eta = (mine or {}).get("estimated_delivery") or o.get("estimated_delivery")
                facts["order"] = {"order_id": o["order_id"], "product": self._order_products(o),
                                  "address": (mine or {}).get("address") or o.get("address"),
                                  "estimated_delivery_ddmm": _ddmm(eta) if eta else None}
                return ["confirm_delivery_address"] if facts["order"]["address"] else self._order_status(facts)
        if decision is not None and decision["eligible"] is None:
            # 5.1: thiếu ngày nhận → CHƯA XÁC ĐỊNH (không coi là đủ điều kiện, không coi là quá hạn). Nói đúng phiên bản / số ngày theo
            # ngày tạo của CHÍNH đơn này; truy hồi tài liệu theo ngày đó (không theo bản hiện hành).
            self._why("exchange_window_undetermined", o["order_id"])
            facts["exchange_window"] = {"order_id": o["order_id"], "created_ddmm": _ddmm(od), "days": decision["days"],
                                        "version": decision["version"], "action": "trả hàng" if kind == "return" else "đổi hàng"}
            return ["exchange_window_info"]
        tgt = {"type": "order", "order_id": o["order_id"]}
        if kind == "return":
            key = (o["order_id"], "return", None)
            if key in self.updates_done:
                facts["update"] = self.updates_done[key]
                return ["order_updated"]
            req = self._req_ok("return", target=tgt, unique_target=unique)
            if not req:
                return self._blocked_goals("return", facts, None) or self._req_policy(text, facts)
            self.reqs.begin(req)
            args = dict(order_id=o["order_id"], action="return", reason="khach yeu cau tra hang")
        else:
            parent, ov = mt._parent(o["sku"])
            other = [s for s in find_products(text) if s != parent["sku"]]          # parser catalog: mẫu khác được nhắc
            size = (u.get("slots") or {}).get("size") or (self.pending_size if kind == "exchange" else None)
            if other:
                new_sku = find_variant(other[0], text, None, None) or other[0]
                action = "exchange_product"
            else:
                if not size:
                    if kind is None:
                        return self._req_policy(text, facts)                          # hỏi chung về đổi trả, không ghi
                    if self.updates_done:
                        facts["update"] = list(self.updates_done.values())[-1]
                        return ["order_updated"]
                    facts["current_variant"] = product_name(o["sku"])
                    return ["ask_new_size"]
                size = str(size).upper()
                if not ov or size == str(ov["size"]).upper():
                    facts["current_variant"] = product_name(o["sku"])
                    return ["ask_new_size"]
                self.pending_size = size
                new_sku = next((v["variant_sku"] for v in parent["variants"] if str(v["size"]).upper() == size and v["color"] == ov["color"]), None)
                if not new_sku:
                    return ["ask_variant"]
                action = "exchange_size"
            key = (o["order_id"], action, new_sku)
            if key in self.updates_done:
                facts["update"] = self.updates_done[key]
                return ["order_updated"]
            if kind is None:
                # khách HỎI về đổi (chưa yêu cầu): xem trước tồn kho + chính sách, xin xác nhận; không ghi
                facts["exchange_preview"] = {"order_id": o["order_id"], "new_variant": product_name(new_sku), "new_variant_sku": new_sku,
                                             "in_stock": self.tools.call("inventory.check", sku=new_sku).get("in_stock")}
                hits = knowledge.search("đổi size phí lần đầu", k=1)
                facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
                return ["exchange_offer"]
            req = self._req_ok("exchange", target=tgt, unique_target=unique, revision={"new_variant": new_sku})
            if not req:
                return self._blocked_goals("exchange", facts, None) or self._req_policy(text, facts)
            self.reqs.begin(req)
            args = dict(order_id=o["order_id"], action=action, new_variant_sku=new_sku)
        r = self.tools.call("order.update", **args)
        status = tool_outcome.classify({"name": "order.update", "args": args, "result": r})["status"]
        self.reqs.settle(req, status, {"order_id": o["order_id"], "action": key[1]})
        if status == "unresolved":
            self._why("order_update_unresolved", o["order_id"])
            return ["contract_error"]
        if r.get("error"):
            facts["order_error"] = r["error"]
            if r.get("restock_expected"): facts["restock_expected"] = r["restock_expected"]
            return ["out_of_stock" if "out_of_stock" in r["error"] else "order_failed"]
        self.updates_done[key] = public_view(r)
        facts["update"] = public_view(r)
        return ["order_updated"]

    # Quyền ghi: đích theo request_state; UNDERSTANDING=deepseek ngoài đích theo tập yêu cầu bộ hiểu cấp (cổng D68 đã xóa 24/11)
    def _req_ok(self, *kinds, target=None, total=None, **kw):
        if settings.arch == "target":
            # đích: chỉ yêu cầu còn hiệu lực, ĐÚNG loại (kinds[0], không cấp chéo đổi/trả), đúng đối tượng + revision, đủ điều kiện
            r, why = self.reqs.authorize(kinds[0], target, total, **kw)
            self._req_why = why
            if r is None:
                self.req_blocked.append(f"{kinds[0]}:{why}")
                self._why("request_blocked", f"{kinds[0]}: {why}")
            elif settings.jev_write_gate:
                self._why("request_allowed", f"{kinds[0]}: {r['id']}, target={r.get('target')}")
            return r
        r = getattr(self, "req_turn", None)
        if settings.understanding != "deepseek" or r is None or r.get("fallback"):
            return True                       # tắt, hoặc lỗi/quá hạn API ở lượt này → theo rules như R0
        if self.open_requests & set(kinds):
            return True
        self.req_blocked.append(kinds[0])
        self._why("request_gate_blocked", f"{kinds[0]}: bộ hiểu không thấy khách yêu cầu")
        return False

    def _req_done(self, *kinds):
        if settings.arch == "target":
            return                     # đích: trạng thái chỉ đổi theo kết quả tool (reqs.settle), không tiêu thụ trước khi chạy
        self.open_requests = getattr(self, "open_requests", set()) - set(kinds)

    def _blocked_goals(self, kind, facts, default, orders=None):
        """Goal khi request_state không cấp quyền ghi (đích). Không goal nào ghi; hỏi lại / nêu điều kiện / trả lời."""
        why = getattr(self, "_req_why", None)
        cand = self.reqs.last_blocked or {}
        cond = cand.get("condition") or {}
        if why == "condition_pending":
            facts["condition"] = {"type": cond.get("type"), "text": cond.get("span") or None}
            return ["condition_pending"]
        if why == "condition_unmet":
            facts["condition"] = {"type": "price_max", "max_vnd": cond.get("max_vnd"), "total_vnd": getattr(self, "_req_total", None)}
            return ["condition_unmet"]
        if why == "conflicting_exchange_return":
            return ["ask_exchange_or_return"]
        if why == "multi_request" and kind in ("change_order_address", "exchange", "return") and orders:
            facts["which_orders"] = [{"order_id": o["order_id"], "product": product_name(o.get("sku")) if o.get("sku") else None}
                                     for o in orders[-5:]]
            return ["ask_which_order"]
        if why in ("ambiguous_turn", "understanding_error", "input_truncated"):
            return ["ask_repeat"]
        if why == "target_unresolved" and kind in ("change_order_address", "exchange", "return") and orders:
            facts["which_orders"] = [{"order_id": o["order_id"], "product": product_name(o.get("sku")) if o.get("sku") else None}
                                     for o in orders[-5:]]
            return ["ask_which_order"]
        if why == "revision_changed" and kind == "place_order" and facts.get("quote"):
            return ["quote", "confirm_new_price"]
        return default

    def _req_policy(self, text, facts):
        hits = knowledge.search(text, k=2)
        facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
        return ["policy_answer"] if hits else ["no_info"]

    def _plan_callback(self, when, facts):
        c = self.customer or {}
        dt = datetime.fromisoformat(when)
        reason = None
        while dt.date().isoformat() in mt.HOLIDAYS or dt.weekday() == 6:
            reason = f"ngày {_ddmm(dt.date().isoformat())} bên em nghỉ" if dt.date().isoformat() in mt.HOLIDAYS else "chủ nhật bên em nghỉ"
            dt += timedelta(days=1)
        at = dt.strftime("%Y-%m-%dT%H:%M")
        args = dict(customer_phone=c.get("phone") or self.phone, callback_at=at, note=f"hẹn gọi lại: {self.known.get('blocker') or ''}".strip())
        req = self._req_ok("callback")
        if not req:
            return ["defer_ack"]
        if settings.arch == "target":
            self.reqs.begin(req)
        r = self.tools.call("schedule.callback", **args)
        self._req_done("callback")
        from harness import tool_outcome
        st = tool_outcome.classify({"name": "schedule.callback", "args": args, "result": r})["status"]
        if settings.arch == "target":
            self.reqs.settle(req, st, {"callback_at": (r or {}).get("callback_at") if isinstance(r, dict) else None})
        if st != "confirmed_success":
            return ["contract_error"]          # G1: lịch hẹn chưa được tool xác nhận → không báo đã hẹn
        facts["callback"] = {**r, **({"moved_reason": reason} if reason else {}), "weekday": ["thứ hai", "thứ ba", "thứ tư", "thứ năm", "thứ sáu", "thứ bảy", "chủ nhật"][dt.weekday()],
                             "ddmm": _ddmm(dt.date().isoformat())}
        self.known["callback_requested"] = at
        self.outcome = self.outcome or "hen_goi_lai"
        return ["callback_scheduled"]

    def _summary_facts(self):
        q = self.quote or {}
        return {"khach": (self.customer or {}).get("name"), "xung_ho": (self.customer or {}).get("honorific"),
                "kenh": self.channel, "ngay": self.today, "cuoc_goi": self.call_name,
                "san_pham_dang_ban": product_name(self.focus) if self.focus else None,
                "gia_da_bao_vnd": q.get("final_price_vnd") or self.known.get("price_quoted_vnd"),
                "khuyen_mai": q.get("promo_names") or [], "cac_san_pham_da_nhac": [product_name(s) for s in self.discussed],
                "don_da_len": [{"ma_don": o["order_id"], "tong_vnd": o.get("total_vnd"), "san_pham": self._order_products(o)}
                               for o in self.orders_created],
                "rao_can": self.known.get("blocker"), "hen_goi_lai": self.known.get("callback_requested"),
                "ket_qua": self.outcome or "khac",
                "thong_tin_khach": {k: v for k, v in self.known.items() if k in ("room_area_m2", "has_children", "budget_vnd", "size", "color")},
                "cau_chua_tra_loi": self.open_questions}

    # G2 (FINAL 10/11, D64): projection cho bản ghi (brief chuyển máy, open_questions, tóm tắt/memory). Lượt khách thuộc loại
    # nhạy cảm (đòi xác nhận công dụng chữa bệnh) được ghi bằng mô tả trung tính thay cho nguyên văn, để bản ghi của shop không
    # mang lời khẳng định y tế như một dữ kiện. Lời khách vẫn nằm nguyên trong trace (customer_text); chỉ đổi bản ghi do agent sinh.
    SENSITIVE_VIEW = {"cau_hoi_y_te": "Khách đề nghị xác nhận công dụng y tế/chữa bệnh của sản phẩm (agent không xác nhận; cần chuyên viên trả lời)"}

    def _mark_sensitive(self, text, reason):
        if reason in self.SENSITIVE_VIEW:
            self.sensitive_views[text] = self.SENSITIVE_VIEW[reason]

    def _record_view(self, text):
        return self.sensitive_views.get(text, text)

    def _history_view(self, hist):
        return [{**h, "text": self._record_view(h["text"])} if h.get("role") == "customer" else h for h in hist]

    def _handoff(self, text, reason):
        """Một nơi duy nhất gọi handoff.transfer (G3, FINAL 10/11). Ticket đã được tool xác nhận (queued) cho cùng lý do trong cuộc
        gọi này thì không tạo ticket mới mỗi lượt khách nói tiếp (trace 09/11: V3-093/097 hai ticket, RT-12 ba ticket)."""
        from harness import tool_outcome
        # 14/11 (GEN-T18, duyệt: theo trạng thái): cuộc gọi đã có ticket được tool xác nhận — DÙ khác lý do (y tế rồi khách đòi
        # gặp người) — thì không chuyển máy lần hai; báo lại ticket đang có (goal handoff đọc already_queued, contract đã cho phép).
        done = self.handoff_tickets.get(reason) or next(iter(self.handoff_tickets.values()), None)
        if done:
            self._why("handoff_already_queued", done["ticket_id"] + ("" if reason in self.handoff_tickets else f" (lý do mới: {reason})"))
            return {**done, "already_queued": True}
        brief = self._handoff_brief(text, reason)
        r = self.tools.call("handoff.transfer", brief=brief)
        if tool_outcome.ok({"name": "handoff.transfer", "args": {}, "result": r}):
            self.handoff_tickets[reason] = {"ticket_id": r["ticket_id"], "status": r["status"]}
        return r

    def _handoff_brief(self, text, reason):
        c = self.customer or {}
        self._mark_sensitive(text, reason)
        view = self._record_view(text)
        conv = " / ".join(h["text"] for h in self._history_view(self.history[-6:])) or view
        fallback = f"Khách {c.get('name') or ''} ({self.call_name}): {conv}"[:780].ljust(20, ".")
        from core.llm.summarizer import summarize
        hist = self._history_view(self.history + [{"role": "customer", "text": text}])
        text = view
        s = summarize("handoff", {**self._summary_facts(), "ly_do_chuyen": reason, "cau_khach_vua_hoi": text}, hist,
                      self.seen_money | {v for v in self.known.values() if isinstance(v, int)}, self.gen.backend, 800)
        self.last_sentiment = (s or {}).get("sentiment")
        name = product_name(self.focus) if self.focus else "sản phẩm khách quan tâm"
        task = getattr(self, "handoff_task", None)
        if not task and getattr(self, "ext_cancelled", None):
            # v6p9b: chuyển nhân viên SAU khi đã hủy bằng order.cancel trong cuộc → brief nêu rõ đơn đã hủy (không để nhân viên hiểu
            # là yêu cầu hủy còn chờ)
            task = {"action": "cancel_confirm", "order_id": self.ext_cancelled[-1], "evidence": text[:160], "already_cancelled_by_tool": True}
        next_action = ("Tiếp nhận yêu cầu " + {"cancel": "hủy đơn", "exchange": "đổi hàng", "return": "trả hàng",
                                                "amend_lines": "sửa món trong đơn vừa tạo (đơn chưa thay đổi)",
                                                "cancel_confirm": "xác nhận lại với khách việc hủy đơn (đơn ĐÃ hủy bằng order.cancel)"}.get(
            task.get("action"), "hỗ trợ") + ": " + str(task) + "; kiểm tra và xử lý, sau đó thông báo kết quả cho khách") if task else \
            "Xử lý nội dung khách vừa yêu cầu: " + text
        return {"customer_phone": c.get("phone") or self.phone, "customer_name": c.get("name"), "customer_id": c.get("customer_id"),
                "channel": self.channel if self.channel in ("hotline", "chat_fanpage", "zalo_oa") else "other",
                "escalation_reason": reason, "escalation_reason_detail": text,
                "conversation_summary": s["summary"] if s else fallback,
                "summary_source": s["source"] if s else "template",
                "product_advised": self.focus or self.known.get("product_advised"),
                "price_quoted_vnd": (self.quote or {}).get("final_price_vnd") or self.known.get("price_quoted_vnd"),
                "facts_confirmed": {k: v for k, v in self.known.items() if k != "self_name"},
                "open_questions": list(dict.fromkeys([text] + ((s or {}).get("open_questions") or []))),
                "sentiment": (s or {}).get("sentiment") or "binh_thuong",
                "next_action": next_action,
                "history_refs": [self.session_id], "generated_at": datetime.now().isoformat(timespec="seconds")}

    def _remember(self, slots, route):
        c = self.customer or {}
        cid = c.get("customer_id")
        if not cid or self.candidates or self.deleted:
            return [{"key": "*", "value": None, "op": "delete", "source": f"{self.call_name}#turn{self.turn_no}", "customer_id": cid}] \
                if self.deleted and self.turn_no == self._deleted_turn else []
        src = f"{self.call_name}#turn{self.turn_no}"
        writes = list(self.__dict__.pop("_addr_profile_writes", None) or [])
        # v6p11: lượt có yêu cầu đổi địa chỉ → slot address chỉ vào hồ sơ qua _save_profile_address (profile_default đã xác nhận)
        addr_req = settings.address_scope_gate and any(
            i.get("kind") == "change_order_address" for i in (self.u_turn or {}).get("request_items") or [])
        for k, v in slots.items():
            if settings.planner_selector != 'rules' and self.proxy_caller and k in ('address', 'phone', 'self_name'):
                continue
            if addr_req and k == "address":
                continue
            if k == "claimed_prices" or (k == "self_name" and not cid.startswith("N-")):
                continue
            w = self.mem.write_fact(cid, k, v, src, self.session_id, self.today)
            if w: writes.append(w)
        if self.focus:
            q = self.quote if self.quote and self.quote["sku"] in (self.focus, mt._parent(self.focus)[0] and mt._parent(self.focus)[0]["sku"]) else None
            for k, v in (("product_advised", self.focus), ("price_quoted_vnd", q and q["final_price_vnd"]),
                         ("promo_code", q and (q["promo_codes"] or [None])[0]), ("promo_expiry", q and q["promo_end"])):
                if v is not None:
                    w = self.mem.write_fact(cid, k, v, src, self.session_id, self.today)
                    if w: writes.append(w); self.known[k] = v
            # D54 (05/11): khách đã chọn đúng một biến thể (size/màu) và đã được báo giá biến thể đó nhưng CHƯA lên đơn
            # (vd "để chị nhắn Zalo chốt sau", E15) → vẫn nhớ variant_sku, để lần sau chốt đúng biến thể mà không hỏi lại.
            # focus thường là SKU cha (SKU-JK-WND), còn báo giá là SKU biến thể (SKU-JK-WND-S-NAVY).
            qs = (self.quote or {}).get("sku")
            qp = mt._parent(qs)[0] if qs else None
            fp = mt._parent(self.focus)[0]
            if qs and qp and qs != qp["sku"] and fp and qp["sku"] in (self.focus, fp["sku"]) and not self.orders_created \
                    and not (self.quote or {}).get("representative"):     # bước 2: biến thể đại diện không phải khách chọn
                self.known["variant_sku"] = qs
        for k in ("product_chosen", "order_id", "variant_sku", "estimated_delivery", "unresolved_order_sku"):
            if self.known.get(k):
                w = self.mem.write_fact(cid, k, self.known[k], src, self.session_id, self.today)
                if w: writes.append(w)
        if settings.write_path_gate:
            writes += self._remember_exchanges(cid, src)
        return writes

    def _remember_exchanges(self, cid, src):
        """v6p12 (fee_free, DT-03): số lần đổi của đơn AGENT theo dõi — 0 khi order.create thành công, +1 sau order.update đổi hàng
        thành công. Đơn không có fact (CRM, lịch sử ngoài hệ thống) KHÔNG được khởi tạo ở đây → fee_free coi là chưa xác minh.
        shortcut: đếm từ nhật ký tool của cuộc gọi; nguồn có thẩm quyền lâu dài là lịch sử đơn của hệ thống đơn hàng."""
        from harness import tool_outcome
        writes = []
        for tc in self.call_tool_log:
            if tc.get("_turn") != self.turn_no or not isinstance(tc.get("result"), dict) or tc["result"].get("error"):
                continue
            name, args, res = tc.get("name"), tc.get("args") or {}, tc["result"]
            if name == "order.create" and res.get("order_id"):
                key, value = f"exchanges:{res['order_id']}", 0
                if key in self.mem.current_facts(cid, self.today):
                    continue
            elif name == "order.update" and str(args.get("action", "")).startswith("exchange") \
                    and tool_outcome.classify(tc)["status"] == "confirmed_success":
                key = f"exchanges:{args.get('order_id')}"
                cur = (self.mem.current_facts(cid, self.today).get(key) or {}).get("value")
                if type(cur) is not int:
                    continue
                value = cur + 1
            else:
                continue
            w = self.mem.write_fact(cid, key, value, src, self.session_id, self.today)
            if w:
                writes.append(w)
        return writes

    def end(self):
        self.drain_audits()             # hết phiên: đợi + ghi đủ audit nền (claims / questions) trước khi đóng phiên
        c = self.customer or {}
        if not c.get("customer_id") or self.deleted:
            return
        parts = []
        if self.focus:
            parts.append(f"tư vấn {product_name(self.focus)}" + (f" giá {self.known.get('price_quoted_vnd'):,}đ".replace(",", ".") if self.known.get("price_quoted_vnd") else ""))
        if self.orders_created:
            parts.append("đã lên đơn " + ", ".join(o["order_id"] for o in self.orders_created))
        if self.known.get("blocker") and self.outcome != "chot_don":
            parts.append(f"rào cản: {self.known['blocker']}")
        if self.known.get("callback_requested"):
            parts.append(f"hẹn gọi lại {self.known['callback_requested']}")
        head = f"{self.call_name} ({_ddmm(self.today)}, {self.channel}): "
        summary = head + "; ".join(parts or ["trao đổi chung"])
        from core.llm.summarizer import summarize
        s = summarize("session", self._summary_facts(), self._history_view(self.history),
                      self.seen_money | {v for v in self.known.values() if isinstance(v, int)}, self.gen.backend, 500)
        if s:
            summary = head + s["summary"]
        open_q = list(dict.fromkeys(self.open_questions + ((s or {}).get("open_questions") or [])))[:5]
        blockers = [self.known["blocker"]] if self.known.get("blocker") and self.outcome != "chot_don" else []
        next_action = ("gọi lại theo lịch hẹn " + self.known["callback_requested"]) if self.known.get("callback_requested") \
            else ("trả lời: " + open_q[0]) if open_q else None
        self.mem.add_session(self.session_id, c["customer_id"], self.channel, self.today, self.outcome or "khac", summary, blockers,
                             next_action=next_action, open_questions=open_q)
