"""Một cuộc gọi = CallSession. Vòng lặp mỗi lượt:

perceive → slot khách → ROUTER (Jev) quyết định intent/cờ → PLANNER gọi tool (giá/tồn/đơn chỉ từ tool) →
GENERATOR (DeepSeek) nói theo goals+facts → GUARDRAIL → EXTRACTOR (questions/claims/facts_used) → ghi BỘ NHỚ → trace.

Planner là code xác định (không để LLM tự chọn tham số tool): tham số order.create lấy từ báo giá tool vừa trả,
nên giá trong đơn luôn khớp mock của BTC. LLM chỉ lo câu chữ.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from core import log as cclog
from core.config import settings
from core.llm.generator import Generator, question_slot
from core.llm.router import Router
from harness import extractor, guardrails, improve_hook, knowledge, planner_table
from harness.coverage import NO_QUESTION, coverage
from harness.textnorm import find_money, fold, perceive
from harness.lexicon import rx as lexrx
from harness.tools import (ToolBox, find_by_model_token, find_products, find_variant, mt, product_name, public_view)

CATEGORY_WORDS = [("may loc khong khi", "gia-dung/may-loc-khong-khi"), ("may loc nuoc", "gia-dung/may-loc-nuoc"),
                  ("noi chien", "gia-dung/noi-chien"), ("quat", "gia-dung/quat"), ("giay", "thoi-trang/giay"),
                  ("ao khoac", "thoi-trang/ao"), ("may hut sua", "me-be"), ("xe day", "me-be"), ("binh sua", "me-be"),
                  ("may ham sua", "me-be"), ("ghe o to", "me-be")]
log = cclog.get("agent")
_POST_EXTRACTOR_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-extract")
_ROUTER_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-router")      # L1: PARALLEL_ROUTER=1
STACKABLE_SKIP = {"COD-0", "NAM-SHIP0"}
FILTER_OF = {"SKU-AP-X": "SKU-AP-FLT-X", "SKU-AP-Y": "SKU-AP-FLT-X", "SKU-AP-PRO": "SKU-AP-FLT-P",
             "SKU-XM-4L": "SKU-XM-FLT", "SKU-XM-4P": "SKU-XM-FLT"}

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


class CallSession:
    def __init__(self, *, memory, today, call_name, session_id, channel, channel_identity, phone, input_mode,
                 router=None, generator=None, config="full"):
        self.mem, self.today, self.call_name, self.session_id = memory, today, call_name, session_id
        self.channel, self.channel_identity, self.phone, self.input_mode = channel or "hotline", channel_identity, phone, input_mode
        self.router, self.gen, self.config = router or Router(), generator or Generator(), config
        self.tools = ToolBox(today)
        self.customer = None
        self.contact_phone = None  # shipping contact only, not identity verification
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
        kind, val = ("fb_id", self.channel_identity) if self.channel == "chat_fanpage" else \
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
        sid = s["session_id"]
        if any(p["session_id"] == sid for p in self.mem.past_sessions(cid)):
            return
        self.mem.add_session(sid, cid, s.get("channel"), s.get("date"), s.get("outcome"), s.get("summary"), source="crm")
        text, d = s.get("summary", ""), s.get("date") or self.today
        slots = extractor.customer_slots(text, d)
        prods = find_products(text)
        if prods: slots["product_advised"] = prods[0]
        money = find_money(text)
        if money and prods: slots["price_quoted_vnd"] = money[0][2]
        for k in ("blocker", "callback_requested", "self_name", "competitor_price_vnd"):
            slots.pop(k, None)
        for k, v in slots.items():
            self.mem.write_fact(cid, k, v, f"crm:{sid}", sid, self.today, confidence=0.8, valid_from=d)

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
                                                 "estimated_delivery": o.get("estimated_delivery")}.items() if v is not None})
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
        self.turn_no += 1
        if self.input_mode == "asr_transcript":
            from asr.itn import itn
            raw = itn(raw)
        p = perceive(raw, self.today)
        text = p["text"]
        t_perceive = time.perf_counter()
        # L1: router chỉ cần lời khách + lịch sử + tóm tắt phiên trước, không cần slot → gọi song song với bước trích slot.
        # Lượt có SĐT hoặc đang hỏi danh tính thì vẫn nối tiếp: định danh có thể đổi brief (tóm tắt) mà router dùng.
        early_route = None
        if settings.planner_selector == "rules" and settings.parallel_router and not p["phone"] and not self.candidates:
            ctx_early = {"recent": self.history[-4:],
                         "summary": (self.brief or {}).get("last_session") and self.brief["last_session"]["summary"] or ""}
            early_route = _ROUTER_POOL.submit(self.router.route, text[:MAX_CUSTOMER_CHARS], ctx_early)
        ext_meta = {}
        recent_context = "\n".join(f"{h['role']}: {h['text']}" for h in self.history[-8:])
        session_summary = ((self.brief or {}).get("last_session") or {}).get("summary", "")
        extraction_context = "\n".join(part for part in (
            f"Tóm tắt phiên trước: {session_summary}" if session_summary else "",
            f"Hội thoại gần đây:\n{recent_context}" if recent_context else "",
        ) if part)
        slots, pending = extractor.customer_slots_start(
            text, self.today, meta=ext_meta, context=extraction_context or None,
            asked=self.last_q_slot)          # CERT v2 (3.3): slot agent vừa hỏi ở lượt trước (question_slot của planner)
        t_slots = time.perf_counter()
        proxy_now = bool(PROXY_CLAIM_RX.search(fold(text)))
        if proxy_now and not self.proxy_caller:
            self.proxy_caller = True
            self._why("proxy_caller", "người gọi tự xưng người nhà của khách khác; không gắn hồ sơ theo SĐT đọc trong câu")
        from harness.identity_permissions import may_bind_spoken_phone
        unverified_phone = bool(settings.planner_selector != 'rules' and p['phone'] and not may_bind_spoken_phone(self, p['phone']))
        if unverified_phone and not proxy_now:
            self.contact_phone = p['phone']
        if p["phone"] and (proxy_now or unverified_phone):
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
        text = text[:MAX_CUSTOMER_CHARS]
        ctx = {"recent": self.history[-4:], "summary": (self.brief or {}).get("last_session") and self.brief["last_session"]["summary"] or ""}
        t_identity = time.perf_counter()
        route = (early_route.result() if early_route is not None else self.router.route(text, ctx)) if settings.planner_selector == "rules" else {"intent": "meta", "confidence": 1.0, "flags": {}, "backend": "selector", "ms": 0, "fallback": None}
        t_route = time.perf_counter()
        knowledge.spent_ms = 0.0
        if pending is not None and extractor.customer_slots_finish(pending, slots, settings.extractor_timeout_s if settings.planner_selector != 'rules' else 0) is not None:
            pending = None
        # 1b (06/11): planner chỉ còn bảng quyết định (harness/planner_rules.json). _plan if-else cũ đã bỏ
        # (bản cuối ở commit ce171ac); bảng chỉ có nhánh cũ từng trùng trace 100 % với nó (D50).
        goals, facts = planner_table.plan(self, text, slots, route)
        t_plan = time.perf_counter()
        rag_ms = knowledge.spent_ms
        tools_ms = sum(tc.get("ms", 0) for tc in self.tools.log)
        tool_log = (self.start_tool_log if self.turn_no == 1 else []) + self.tools.take_log()
        plan = {"honorific": (self.customer or {}).get("honorific") or "anh/chị", "customer_name": (self.customer or {}).get("name"),
                "call": self.call_name, "is_returning": bool(self.brief and self.brief["is_returning"]),
                "customer_said": text, "intent": route["intent"], "goals": goals, "facts": facts,
                "KNOWN": {k: v for k, v in self.known.items() if k not in ("self_name",)},
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
        post_parts = {}
        agent_meta = {}
        known_for_q = {k: v for k, v in self.known.items()}
        agent_started = time.perf_counter()
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
        for key in ("ms", "dropped_spans"):
            ext_meta[key] = int(ext_meta.get(key, 0) or 0) + int(agent_meta.get(key, 0) or 0)
        if agent_meta.get("backend"):
            ext_meta["backend"] = agent_meta["backend"]
        fallbacks = [x for x in (ext_meta.get("fallback"), agent_meta.get("fallback")) if x]
        if fallbacks:
            ext_meta["fallback"] = " | ".join(dict.fromkeys(fallbacks))
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
        total_ms = int((t_ready - t_start) * 1000)
        post_ms = int((time.perf_counter() - t_ready) * 1000)
        end_to_end_ms = int((time.perf_counter() - t_start) * 1000)
        ms = lambda a, b: int((b - a) * 1000)
        parts = {"perceive_ms": ms(t_start, t_perceive), "slots_ms": ms(t_perceive, t_slots), "identity_ms": ms(t_slots, t_identity),
                 "router_ms": ms(t_identity, t_route), "plan_ms": ms(t_route, t_plan), "plan_tools_ms": int(tools_ms),
                 "plan_rag_ms": int(rag_ms), "prompt_ms": ms(t_plan, t_gen), "llm_ttft_ms": llm1_ttft,
                 "llm_gen_ms": max(0, llm1_total - llm1_ttft), "guard_ms": ms(t_gen1, t_guard), "regen_ms": ms(t_guard, t_ready)}
        row = {"customer_text": text, "agent_text": text_out, "questions": questions, "facts_used": used, "claims": claims,
               "tool_calls": [{"name": tc["name"], "args": tc["args"], "result": tc["result"]} for tc in tool_log],
               "latency": {"ttft_ms": pre_ms + ttft, "total_ms": total_ms, "end_to_end_ms": end_to_end_ms,
                           "ttfa_ms": None, "post_ms": post_ms, "parts": parts, "post_parts_ms": post_parts},
               "memory_writes": mem_writes,
               "customer_input_mode": {"asr_transcript": "asr_transcript", "chat_teencode": "chat_teencode"}.get(self.input_mode, "clean"),
               "router": {k: route.get(k) for k in ("intent", "confidence", "flags", "backend", "ms", "fallback")
                          + (("improve",) if route.get("improve") else ())},
               "goals": goals, "planner": {"backend": settings.planner_backend, "selector": settings.planner_selector, "simulated": settings.jev_simulated, "contract": plan.get("contract"), "semantic": self.semantic_plan,
                                                    **({"semantic": self.semantic_plan} if self.semantic_plan else {}), "branches": list(self.plan_why),
                                                    **({"llm": self.llm_plan} if self.llm_plan else {}),
                                                    "table": list(self.table_rows)},
               "question_slot": plan["question_slot"], "guardrail": guard, "llm_usage": usage,
               "extractor": {"backend": ext_meta.get("backend", settings.extractor_backend), "ms": ext_meta.get("ms", 0),
                             "fallback": ext_meta.get("fallback"), "dropped_spans": ext_meta.get("dropped_spans", 0)}}
        if improve_hook.enabled():
            row["improve"] = improve_hook.stamp(improve_used + [h["chunk_id"][4:] for h in facts.get("policy") or []
                                                                if str(h.get("chunk_id", "")).startswith("FAQ:")])
        if "jev_slot_requests" in agent_meta:
            row["extractor"].update({"question_backend": agent_meta.get("question_backend", "jev_slots_experimental"),
                                     "jev_slot_requests": agent_meta["jev_slot_requests"],
                                     "jev_slot_ms": agent_meta["jev_slot_ms"],
                                     "jev_slot_errors": agent_meta["jev_slot_errors"]})
        if settings.jev_simulated:
            from harness.jev_adapter import COUNTS
            row['api_audit'] = dict(COUNTS)
            row['extractor']['simulated'] = True
        if settings.extractor_jev_hybrid:
            row["extractor"].update({"jev_hybrid": True,
                                     "jev_label_requests": ext_meta.get("jev_label_requests", 0) + agent_meta.get("jev_label_requests", 0),
                                     "jev_customer_labels": ext_meta.get("jev_customer_labels"),
                                     "jev_claim_labels": agent_meta.get("jev_claim_labels", []),
                                     "jev_customer_error": ext_meta.get("jev_label_error"),
                                     "jev_agent_error": agent_meta.get("jev_label_error"),
                                     # A6: slot luật cắt được mà Jev bỏ (address/payment) + chính sách đã áp
                                     "jev_dropped_rule_slots": ext_meta.get("jev_dropped_rule_slots"),
                                     "jev_drop_policy": settings.jev_drop_policy})
        if agent_meta.get("agent_qwen_skipped"):
            row["extractor"]["agent_claim_backend"] = settings.agent_claim_backend
            row["extractor"]["agent_qwen_skipped"] = True
        if settings.extractor_confidence_gate:
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
            row["call_brief_latency_ms"] = self.brief_ms if self.call_name != "call_1" else None
            row["call_brief"] = self.brief
        return row

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
                "discontinued": inv.get("discontinued"), "successor_sku": inv.get("successor_sku")}
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

    def _llm_fallback(self, text, facts):
        """B-H: LLM đề xuất goal trong danh sách đóng; code kiểm điều kiện rồi mới thực thi. Ghi cả đề xuất lẫn quyết định."""
        from harness import planner_llm
        state = {"focus": self.focus, "turn_no": self.turn_no,
                 "has_orders": bool(self.orders_created or (self.brief or {}).get("orders") or self.known.get("order_id"))}
        recent = [f"{h['role']}: {h['text']}" for h in self.history[-4:]]
        s = planner_llm.suggest(text, recent, state)
        goals, why = self._apply_llm_goal(s.get("goal"), text, facts)
        self.llm_plan = {**{k: s.get(k) for k in ("goal", "confidence", "backend", "fallback", "ms", "abstain")},
                         "accepted": bool(goals), "reason": why}
        if goals:
            self._why(f"llm_{s['backend']}", f"{s['goal']} ({why})")
        return goals

    def _apply_llm_goal(self, g, text, facts):
        """Code kiểm điều kiện cho goal LLM chọn. → (goals, lý do). Không goal nào tạo / sửa đơn."""
        if not g:
            return [], "abstain"
        if g == "quote":
            if not self.focus:
                return [], "từ chối: chưa có sản phẩm đang tư vấn"
            q = self._quote(self._resolve_variant(self.focus, text), "advised")
            if not q.get("final_price_vnd"):
                return [], "từ chối: tool không trả giá"
            facts["quote"] = q
            return ["quote"], "giá từ pricing.get_quote"
        if g == "order_status":
            goals = self._order_status(facts)
            return (goals, "order.status") if facts.get("orders") else ([], "từ chối: không có đơn")
        if g == "policy_answer":
            hits = knowledge.search(text, k=2)
            if not hits:
                return [], "từ chối: không có tài liệu khớp"
            facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
            return ["policy_answer"], "knowledge.search"
        if g == "defer_ack":
            self.outcome = self.outcome or "hen_goi_lai"
            return ["defer_ack"], "ok"
        if g == "ask_product":
            return (["ask_product"], "ok") if not self.focus else ([], "từ chối: đã có sản phẩm")
        if g in ("ask_repeat", "closing"):
            return [g], "ok"
        return [], f"từ chối: goal {g} không nằm trong danh sách được phép"

    def _order_status(self, facts):
        c = self.customer or {}
        r = self.tools.call("order.status", customer_phone=c.get("phone") or self.phone)
        facts["orders"] = [{**{k: o.get(k) for k in ("order_id", "sku", "status", "tracking", "created_on", "date", "estimated_delivery", "address")
                               if o.get(k) is not None}, "product": product_name(o["sku"]) if o.get("sku") else None,
                            "estimated_delivery_ddmm": _ddmm(o["estimated_delivery"]) if o.get("estimated_delivery") else None}
                           for o in r.get("orders", [])]
        for o in facts["orders"]:
            if not o.get("estimated_delivery") and o["order_id"] == self.known.get("order_id") and self.known.get("estimated_delivery"):
                o["estimated_delivery"] = self.known["estimated_delivery"]; o["estimated_delivery_ddmm"] = _ddmm(o["estimated_delivery"])
            if o["order_id"] == self.known.get("order_id") and self.known.get("address"):
                o["address"] = self.known["address"]
        return ["order_status"]

    def _ask_prior_contact(self, f):
        """B3 (BTCL-016/017): khách nhắc lần trao đổi trước nhưng không tìm được lịch sử (vd chat fanpage rồi gọi hotline
        số khác) → xin SĐT / tài khoản đã dùng để tra lại, thay vì hỏi lại nhu cầu từ đầu. Tối đa 2 lần mỗi cuộc."""
        if self.focus is not None or (self.brief or {}).get("is_returning") or self.prior_contact_asked >= 2 \
                or not PRIOR_REF_RX.search(f):
            return []
        self.prior_contact_asked += 1
        self._why("prior_contact_unknown", f"lần hỏi {self.prior_contact_asked}")
        return ["ask_prior_contact"]

    def _policy_gap(self, text, f, asking=True):
        """Hỏi hoàn/trả với thời hạn dài hơn mọi thời hạn hoàn/đổi/trả trong tài liệu (hoặc hỏi văn bản cho chính câu đó)."""
        if self.policy_gap and DOC_REF_RX.search(f):
            return self.policy_gap if asking else None
        m = DUR_RX.search(f)
        if not m or not (REFUND_RX.search(f) or re.search(r"\bcam ket\b", f)):
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
        return find_variant(p["sku"], text, self.known.get("size"), self.known.get("color")) or sku

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
        qs = [self._quote(s, "chosen", basket=[x for x in items if x != s]) for s in items]
        return {"items": [{"name": q["name"], "final_price_vnd": q["final_price_vnd"], "promo_names": q["promo_names"]} for q in qs],
                "total_vnd": sum(q["final_price_vnd"] or 0 for q in qs), "budget_vnd": self.known.get("budget_vnd")}

    def _update_address(self, address, facts):
        if all(fold(o.get("address") or "") == fold(address) for o in self.orders_created):
            self._why("address_same", "địa chỉ trùng địa chỉ trong đơn, không gọi order.update")
            return self._plan_order("", facts)
        self._why("address_update")
        out = []
        for o in self.orders_created:
            r = self.tools.call("order.update", order_id=o["order_id"], action="update_address", reason=f"địa chỉ mới: {address}")
            out.append(r)
        facts["address_update"] = {"orders": [o["order_id"] for o in self.orders_created], "address": address}
        return ["address_updated"]

    def _plan_order(self, text, facts):
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
        new = [s for s in resolved if not any(o["sku"] == s for o in self.orders_created)]
        if not new:
            o = self.orders_created[-1]
            facts["order"] = {"order_id": o["order_id"], "total_vnd": o["total_vnd"], "estimated_delivery": o.get("estimated_delivery"),
                              "estimated_delivery_ddmm": _ddmm(o["estimated_delivery"]) if o.get("estimated_delivery") else None,
                              "payment": self.known.get("payment", "COD"), "address": self.known.get("address"), "items": [product_name(o["sku"])]}
            return ["order_exists"]
        if not self.known.get("address") and self.expired.get("address") and re.search(r"(dia chi cu|cho cu|nhu cu)", fold(text)):
            if self.old_addr_asked:
                self.known["address"] = self.expired["address"]
            else:
                self.old_addr_asked = True
                facts["old_address"] = self.expired["address"]
                return ["confirm_old_address"]
        payment = self.known.get("payment", "COD")
        quotes = [self._quote(s, "chosen", basket=[x for x in new if x != s]) for s in new]
        # E04 (ORDER_QTY): chỉ áp số lượng khi chốt đúng 1 SKU; nhiều SKU thì mỗi SKU 1 cái như cũ
        qty = 1
        if settings.order_qty and len(new) == 1:
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
        made = []
        # D13 (02/11, SAMPLE-06): kênh chat/Zalo chưa có SĐT → ToolBox bỏ đối số None nên order.create thiếu customer_phone
        # và mock báo tool_exception. Vẫn lên đơn (khách đã chốt) với SĐT rỗng, rồi xin SĐT ngay để shipper liên hệ.
        phone = c.get("phone") or self.phone or getattr(self, "contact_phone", None) or ""
        for q in quotes:
            args = dict(customer_phone=phone, sku=q["sku"], qty=qty, price_vnd=q["final_price_vnd"],
                        promo_code=(q["promo_codes"] or [None])[0], payment=payment, address=self.known.get("address"),
                        basket_skus=[x for x in new if x != q["sku"]] or None)
            r = self.tools.call("order.create", **args)
            if r.get("error") == "price_mismatch":
                args["price_vnd"] = r["expected_price_vnd"]; r = self.tools.call("order.create", **args)
            if r.get("error"):
                facts["order_error"] = r["error"]
                if made:
                    self.orders_created += made
                    self.known['order_id'] = made[0]['order_id']
                    self.known['product_chosen'] = made[0]['sku']
                    facts['partial_orders'] = [{'order_id': o['order_id'], 'total_vnd': o['total_vnd']} for o in made]
                    return ['order_partial']
                return ["order_failed"]
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
        decision = exchange_window(o, self.today) if settings.planner_selector != "rules" else None
        if decision is not None:
            facts["exchange_policy"] = decision
        if (decision is not None and decision["eligible"] is False) or (decision is None and od and (date.fromisoformat(self.today) - date.fromisoformat(od)).days > 7 + 4):
            facts["old_order"] = {"order_id": o["order_id"], "product": product_name(o["sku"]), "date": od}
            if not self.window_told:
                self.focus, self.focus_by = o["sku"], "memory"
            return ["WINDOW_PASSED"]
        if action_override is None and re.search(r"\bdia chi\b", f) and not RETURN_RX.search(f) and not re.search(r"\b(size|co|mau)\b", f) and not find_products(text):
            eta = self.known.get("estimated_delivery") if o["order_id"] == self.known.get("order_id") else None
            facts["order"] = {"order_id": o["order_id"], "product": product_name(o["sku"]), "address": self.known.get("address") or o.get("address"),
                              "estimated_delivery_ddmm": _ddmm(eta) if eta else None}
            return ["confirm_delivery_address"]
        if action_override == "return" or (action_override is None and RETURN_RX.search(f)):
            key = (o["order_id"], "return", None)
            if key in self.updates_done:
                facts["update"] = self.updates_done[key]
                return ["order_updated"]
            r = self.tools.call("order.update", order_id=o["order_id"], action="return", reason="khach yeu cau tra hang")
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
            r = self.tools.call("order.update", order_id=o["order_id"], action=action, new_variant_sku=new_sku)
            if not r.get("error"):
                self.updates_done[key] = public_view(r)
        if r.get("error"):
            facts["order_error"] = r["error"]
            if r.get("restock_expected"): facts["restock_expected"] = r["restock_expected"]
            return ["out_of_stock" if "out_of_stock" in r["error"] else "order_failed"]
        facts["update"] = public_view(r)
        return ["order_updated"]

    def _plan_callback(self, when, facts):
        c = self.customer or {}
        dt = datetime.fromisoformat(when)
        reason = None
        while dt.date().isoformat() in mt.HOLIDAYS or dt.weekday() == 6:
            reason = f"ngày {_ddmm(dt.date().isoformat())} bên em nghỉ" if dt.date().isoformat() in mt.HOLIDAYS else "chủ nhật bên em nghỉ"
            dt += timedelta(days=1)
        at = dt.strftime("%Y-%m-%dT%H:%M")
        r = self.tools.call("schedule.callback", customer_phone=c.get("phone") or self.phone, callback_at=at,
                            note=f"hẹn gọi lại: {self.known.get('blocker') or ''}".strip())
        facts["callback"] = {**r, "moved_reason": reason, "weekday": ["thứ hai", "thứ ba", "thứ tư", "thứ năm", "thứ sáu", "thứ bảy", "chủ nhật"][dt.weekday()],
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
                "don_da_len": [{"ma_don": o["order_id"], "tong_vnd": o.get("total_vnd"), "san_pham": product_name(o["sku"])}
                               for o in self.orders_created],
                "rao_can": self.known.get("blocker"), "hen_goi_lai": self.known.get("callback_requested"),
                "ket_qua": self.outcome or "khac",
                "thong_tin_khach": {k: v for k, v in self.known.items() if k in ("room_area_m2", "has_children", "budget_vnd", "size", "color")},
                "cau_chua_tra_loi": self.open_questions}

    def _handoff_brief(self, text, reason):
        c = self.customer or {}
        conv = " / ".join(h["text"] for h in self.history[-6:]) or text
        fallback = f"Khách {c.get('name') or ''} ({self.call_name}): {conv}"[:780].ljust(20, ".")
        from core.llm.summarizer import summarize
        hist = self.history + [{"role": "customer", "text": text}]
        s = summarize("handoff", {**self._summary_facts(), "ly_do_chuyen": reason, "cau_khach_vua_hoi": text}, hist,
                      self.seen_money | {v for v in self.known.values() if isinstance(v, int)}, self.gen.backend, 800)
        self.last_sentiment = (s or {}).get("sentiment")
        name = product_name(self.focus) if self.focus else "sản phẩm khách quan tâm"
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
                "next_action": f"trả lời câu hỏi chuyên môn của khách rồi tiếp tục tư vấn/chốt {name}",
                "history_refs": [self.session_id], "generated_at": datetime.now().isoformat(timespec="seconds")}

    def _remember(self, slots, route):
        c = self.customer or {}
        cid = c.get("customer_id")
        if not cid or self.candidates or self.deleted:
            return [{"key": "*", "value": None, "op": "delete", "source": f"{self.call_name}#turn{self.turn_no}", "customer_id": cid}] \
                if self.deleted and self.turn_no == self._deleted_turn else []
        src = f"{self.call_name}#turn{self.turn_no}"
        writes = []
        for k, v in slots.items():
            if settings.planner_selector != 'rules' and self.proxy_caller and k in ('address', 'phone', 'self_name'):
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
            if qs and qp and qs != qp["sku"] and fp and qp["sku"] in (self.focus, fp["sku"]) and not self.orders_created:
                self.known["variant_sku"] = qs
        for k in ("product_chosen", "order_id", "variant_sku", "estimated_delivery"):
            if self.known.get(k):
                w = self.mem.write_fact(cid, k, self.known[k], src, self.session_id, self.today)
                if w: writes.append(w)
        return writes

    def end(self):
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
        s = summarize("session", self._summary_facts(), self.history,
                      self.seen_money | {v for v in self.known.values() if isinstance(v, int)}, self.gen.backend, 500)
        if s:
            summary = head + s["summary"]
        open_q = list(dict.fromkeys(self.open_questions + ((s or {}).get("open_questions") or [])))[:5]
        blockers = [self.known["blocker"]] if self.known.get("blocker") and self.outcome != "chot_don" else []
        next_action = ("gọi lại theo lịch hẹn " + self.known["callback_requested"]) if self.known.get("callback_requested") \
            else ("trả lời: " + open_q[0]) if open_q else None
        self.mem.add_session(self.session_id, c["customer_id"], self.channel, self.today, self.outcome or "khac", summary, blockers,
                             next_action=next_action, open_questions=open_q)
