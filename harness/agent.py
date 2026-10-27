"""Một cuộc gọi = CallSession. Vòng lặp mỗi lượt:

perceive → slot khách → ROUTER (Jev) quyết định intent/cờ → PLANNER gọi tool (giá/tồn/đơn chỉ từ tool) →
GENERATOR (DeepSeek) nói theo goals+facts → GUARDRAIL → EXTRACTOR (questions/claims/facts_used) → ghi BỘ NHỚ → trace.

Planner là code xác định (không để LLM tự chọn tham số tool): tham số order.create lấy từ báo giá tool vừa trả,
nên giá trong đơn luôn khớp mock của BTC. LLM chỉ lo câu chữ.
"""
import re
import time
from datetime import date, datetime, timedelta

from core import log as cclog
from core.config import settings
from core.llm.generator import Generator, question_slot
from core.llm.router import Router
from harness import extractor, guardrails, knowledge
from harness.coverage import coverage
from harness.textnorm import find_money, fold, perceive
from harness.tools import (ToolBox, find_by_model_token, find_products, find_variant, mt, product_name, public_view)

CATEGORY_WORDS = [("may loc khong khi", "gia-dung/may-loc-khong-khi"), ("may loc nuoc", "gia-dung/may-loc-nuoc"),
                  ("noi chien", "gia-dung/noi-chien"), ("quat", "gia-dung/quat"), ("giay", "thoi-trang/giay"),
                  ("ao khoac", "thoi-trang/ao"), ("may hut sua", "me-be"), ("xe day", "me-be"), ("binh sua", "me-be"),
                  ("may ham sua", "me-be"), ("ghe o to", "me-be")]
log = cclog.get("agent")
STACKABLE_SKIP = {"COD-0", "NAM-SHIP0"}
FILTER_OF = {"SKU-AP-X": "SKU-AP-FLT-X", "SKU-AP-Y": "SKU-AP-FLT-X", "SKU-AP-PRO": "SKU-AP-FLT-P",
             "SKU-XM-4L": "SKU-XM-FLT", "SKU-XM-4P": "SKU-XM-FLT"}


def _ddmm(d):
    return f"{int(d[8:10])}/{int(d[5:7])}"


MAX_CUSTOMER_CHARS = 600
ATTR_ASK_RX = re.compile(r"\b(chung nhan|chung chi|kiem dinh|xuat xu|san xuat o|nhap khau tu|thanh phan|"
                         r"tieu chuan [a-z]{2,5}|fda|iso|ce|rohs)\b")
CLOSE_ORDER_RX = re.compile(r"\b(chot|len don|dat (hang|luon|don)|lay (du|ca|het|tat ca)|vay thoi|the thoi|giao (ve|cho|toi))\b")
CLOSING_RX = re.compile(r"\b(cam on|tam biet|chao (em|nhe|nha)|vang|da vang|ok|oke|duoc roi|the thoi|vay nhe|nhe em|bye|hen gap|"
                        r"khong can|thoi em|de (chi|anh) xem)\b")


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
        self.candidates = []
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
            self.carried = {k: v["value"] for k, v in self.mem.current_facts(cid, self.today).items()}
            self.known = dict(self.carried)
            self.prev_quotes = self.mem.past_quotes(cid)
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
        past = self.mem.past_sessions(cid, self.session_id) if cid else []
        facts = self.mem.current_facts(cid, self.today, include_expired=True) if cid else {}
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
        t_start = time.perf_counter()
        self.turn_no += 1
        if self.input_mode == "asr_transcript":
            from asr.itn import itn
            raw = itn(raw)
        p = perceive(raw, self.today)
        text = p["text"]
        t_perceive = time.perf_counter()
        ext_meta = {}
        last_agent = next((h["text"] for h in reversed(self.history) if h["role"] == "agent"), None)
        slots, pending = extractor.customer_slots_start(text, self.today, meta=ext_meta, context=last_agent)
        t_slots = time.perf_counter()
        if p["phone"] and self.customer and self.customer.get("customer_id") and not self.candidates:
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
        route = self.router.route(text, ctx)
        t_route = time.perf_counter()
        knowledge.spent_ms = 0.0
        if pending is not None and extractor.customer_slots_finish(pending, slots, 0) is not None:
            pending = None
        goals, facts = self._plan(text, slots, route)
        t_plan = time.perf_counter()
        rag_ms = knowledge.spent_ms
        tools_ms = sum(tc.get("ms", 0) for tc in self.tools.log)
        tool_log = (self.start_tool_log if self.turn_no == 1 else []) + self.tools.take_log()
        plan = {"honorific": (self.customer or {}).get("honorific") or "anh/chị", "customer_name": (self.customer or {}).get("name"),
                "call": self.call_name, "is_returning": bool(self.brief and self.brief["is_returning"]),
                "customer_said": text, "intent": route["intent"], "goals": goals, "facts": facts,
                "KNOWN": {k: v for k, v in self.known.items() if k not in ("self_name",)},
                "question_slot": question_slot(goals, facts)}
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
        from core.llm.generator import render_offline
        guard = {"problems": [], "action": None}
        t_gen = time.perf_counter()
        try:
            candidates = self.gen.generate_candidates(plan)
            total_gen = candidates[0].get("parallel_total", candidates[0]["total"])
            ttft = min(c["ttft"] for c in candidates)
            usage = candidates[0]["usage"]
            text_out = candidates[0]["text"]
            problems = cov = None
            for i, candidate in enumerate(candidates):
                self.gen.fill_problems = candidate["fill_problems"]
                p = guardrails.check(candidate["text"], allowed, internal, forbidden, stale, goals) + self.gen.fill_problems
                c = coverage(candidate["text"], plan)
                if not p and not c:
                    text_out, problems, cov = candidate["text"], p, c
                    usage = candidate["usage"]
                    if i:
                        guard["action"] = "parallel_candidate"
                    break
            if problems is None:
                self.gen.fill_problems = candidates[0]["fill_problems"]
                problems = guardrails.check(text_out, allowed, internal, forbidden, stale, goals) + self.gen.fill_problems
                cov = coverage(text_out, plan)
                if len(candidates) > 1:
                    guard["candidate_rejections"] = [{"temperature": c["temperature"],
                                                       "problems": guardrails.check(c["text"], allowed, internal, forbidden, stale, goals)
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
            problems = guardrails.check(text_out, allowed, internal, forbidden, stale, goals) + self.gen.fill_problems
            cov = coverage(text_out, plan)
        t_guard = time.perf_counter()
        guard["problems"], guard["coverage"] = problems, cov
        if problems or cov:
            guard["rejected"] = [text_out[:400]]
            bad = sorted({v for _, _, v in find_money(text_out)} - (allowed - forbidden))
            note = "; ".join(problems + cov) + ("" if not bad else ". Viết lại và KHÔNG được có các số: "
                                               + ", ".join(f"{v:,}đ".replace(",", ".") for v in bad))
            try:
                text2, ttft2, tot2, _ = self.gen.generate(plan, retry_note=note)
            except Exception as e:
                log.error("generator %s lỗi khi sinh lại → câu mẫu: %s", self.gen.backend, type(e).__name__)
                text2, tot2 = render_offline(plan), 0
            p2 = guardrails.check(text2, allowed, internal, forbidden, stale, goals) + self.gen.fill_problems
            c2 = [] if p2 else coverage(text2, plan)
            if not p2 and not c2:
                text_out, guard["action"] = text2, "regenerated"
            else:
                guard["rejected"].append(text2[:400])
                text_out, guard["action"] = render_offline(plan), "safe_template" if p2 else "coverage_template"
            total_gen += tot2
        t_ready = time.perf_counter()
        if pending is not None:
            late = extractor.customer_slots_finish(pending, slots, settings.extractor_timeout_s)
            for k, v in late.items():
                if k not in ("self_name", "claimed_prices"):
                    self.known[k] = v
            if late.get("self_name") and self.customer and not self.customer.get("name"):
                self.customer["name"] = late["self_name"]
        known_for_q = {k: v for k, v in self.known.items()}
        questions, claims = extractor.analyze_agent(text_out, known_for_q, meta=ext_meta, focus_sku=self.focus)
        used = extractor.facts_used(text_out, [tc["args"] for tc in tool_log], self.carried)
        mem_writes = self._remember(slots, route)
        self.history += [{"role": "customer", "text": text}, {"role": "agent", "text": text_out}]
        if self.customer and self.customer.get("customer_id"):
            self.mem.log_turn(self.session_id, self.turn_no, text, text_out, {"focus": self.focus, "intent": route["intent"]})
        pre_ms = int((t_gen - t_start) * 1000)
        total_ms = int((t_ready - t_start) * 1000)
        post_ms = int((time.perf_counter() - t_ready) * 1000)
        ms = lambda a, b: int((b - a) * 1000)
        parts = {"perceive_ms": ms(t_start, t_perceive), "slots_ms": ms(t_perceive, t_slots), "identity_ms": ms(t_slots, t_identity),
                 "router_ms": ms(t_identity, t_route), "plan_ms": ms(t_route, t_plan), "plan_tools_ms": int(tools_ms),
                 "plan_rag_ms": int(rag_ms), "prompt_ms": ms(t_plan, t_gen), "llm_ttft_ms": llm1_ttft,
                 "llm_gen_ms": max(0, llm1_total - llm1_ttft), "guard_ms": ms(t_gen1, t_guard), "regen_ms": ms(t_guard, t_ready)}
        row = {"customer_text": text, "agent_text": text_out, "questions": questions, "facts_used": used, "claims": claims,
               "tool_calls": [{"name": tc["name"], "args": tc["args"], "result": tc["result"]} for tc in tool_log],
               "latency": {"ttft_ms": pre_ms + ttft, "total_ms": total_ms, "ttfa_ms": None, "post_ms": post_ms, "parts": parts},
               "memory_writes": mem_writes,
               "customer_input_mode": {"asr_transcript": "asr_transcript", "chat_teencode": "chat_teencode"}.get(self.input_mode, "clean"),
               "router": {k: route.get(k) for k in ("intent", "confidence", "flags", "backend", "ms", "fallback")},
               "goals": goals, "question_slot": plan["question_slot"], "guardrail": guard, "llm_usage": usage,
               "extractor": {"backend": ext_meta.get("backend", "rules"), "ms": ext_meta.get("ms", 0),
                             "fallback": ext_meta.get("fallback"), "dropped_spans": ext_meta.get("dropped_spans", 0)}}
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

    def _plan(self, text, slots, route):
        it, fl = route["intent"], route.get("flags", {})
        goals, facts = [], {}
        c = self.customer or {}
        y = lambda k, th=0.6: fl.get(k, 0) >= th
        for k, v in slots.items():
            if k not in ("self_name", "claimed_prices"):
                self.known[k] = v
        if self.candidates:
            return ["ask_identity"], facts
        f = fold(text)
        mentioned = find_products(text)
        if re.search(r"\bmang loc\b", f):
            base = mentioned or ([self.focus] if self.focus else [])
            mentioned = [FILTER_OF.get(mt._parent(x)[0]["sku"], x) for x in base]
        alt = None if mentioned else (find_by_model_token(text, self.focus) if self.focus else None)
        sents = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]
        last = fold(sents[-1]) if sents else f
        asking = sents[-1].rstrip().endswith("?") if sents else False
        asking = asking or (bool(re.search(r"\b(bao nhieu|duoc khong|the nao)\b", last))
                            and not re.search(r"\b(len don|chot|dat hang)\b", last))
        takes = bool(re.search(r"\b(lay|them|chot|mua (luon|them|ca|cho|nhe|nha))\b", f))
        compare = bool(alt) or bool(mentioned and self.focus and mt._parent(mentioned[-1])[0]["sku"] != mt._parent(self.focus)[0]["sku"]
                                    and re.search(r"\bcon\b", f) and not takes)
        prev_focus = self.focus
        new_focus = None
        if mentioned and not compare:
            new_focus = mentioned[-1]
            self.focus, self.focus_by = new_focus, "customer"
        if takes and mentioned and not compare:
            for m_ in mentioned:
                self._cart_add(m_)
        if re.search(r"lay (du|ca|het|tat ca)|ca hai|ca 2|lay du", f):
            for d in self.discussed:
                self._cart_add(d)
        if self.turn_no == 1:
            if self.brief and self.brief["is_returning"] and prev_focus:
                last = self.brief["last_session"]
                need = {k: self.carried[k] for k in ("room_area_m2", "baby_age", "household_size") if self.carried.get(k)}
                facts["brief"] = {"product_name": product_name(prev_focus), "price_quoted_vnd": self.known.get("price_quoted_vnd"),
                                  "last_date_ddmm": _ddmm(last["date"]) if last else None, "blocker": self.known.get("blocker"),
                                  "need": dict(list(need.items())[:1]), "objection": self.carried.get("objection"),
                                  "stale_warnings": self.brief["stale_warnings"]}
                goals.append("opening_returning")
                if any("KM" in w for w in self.brief["stale_warnings"]):
                    goals.append("stale_promo")
        if y("asks_if_bot") or (it == "meta" and not y("wants_data_deleted")):
            goals.append("is_bot")
        if y("wants_data_deleted"):
            if c.get("customer_id"):
                self.mem.forget_customer(c["customer_id"])
            self.known, self.carried, self.deleted, self._deleted_turn = {}, {}, True, self.turn_no
            facts["deleted"] = True; goals.append("data_deleted")
            return goals, facts
        if it == "out_of_scope" or y("medical_question", 0.7):
            self.open_questions.append(text[:200])
            brief = self._handoff_brief(text, "cau_hoi_y_te" if y("medical_question", 0.5) else "khach_yeu_cau_gap_nguoi")
            facts["handoff"] = self.tools.call("handoff.transfer", brief=brief)
            goals.append("handoff"); self.outcome = "chuyen_may"
            return goals, facts
        if y("asks_internal_cost"):
            goals.append("refuse_internal")
        if it == "order_change" and self.buy_intent and not self.orders_created and slots.get("address"):
            it = "place_order"
        if it == "order_change" and self.orders_created and slots.get("address"):
            return goals + self._update_address(slots["address"], facts), facts
        if it == "order_change":
            g = self._plan_order_change(text, facts)
            if g != ["WINDOW_PASSED"]:
                return goals + g, facts
            if not self.window_told:
                self.window_told = True; goals.append("exchange_window_passed")
            it = "product_inquiry"
        if it == "order_status":
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
            goals.append("order_status")
            return goals, facts
        if self.updates_done and re.search(r"\b(hoan|chenh|bu them)\b", f):
            facts["update"] = list(self.updates_done.values())[-1]; goals.append("order_updated")
        if it == "policy_question" or (it == "greeting_or_other" and "?" in text and not self.focus):
            order_date = None
            if re.search(r"\b(don (hang|cu|truoc)|da mua|mua (hom|tu|thang|tuan|dot))\b", f):
                past = self._customer_orders()
                order_date = (past[-1].get("created_on") or past[-1].get("date")) if past else None
            hits = knowledge.search(text, k=2, order_date=order_date)
            facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
            goals.append("policy_answer" if hits else "no_info")
        terms = [m.group(0) for m in ATTR_ASK_RX.finditer(f)]
        if asking and terms and "no_info" not in goals and "policy_answer" not in goals:
            specific = [t for t in terms if t in ("fda", "iso", "ce", "rohs") or t.startswith("tieu chuan")] or terms
            par = mt._parent((mentioned or [self.focus])[-1])[0] if (mentioned or self.focus) else None
            known_txt = fold(str((par or {}).get("attributes", {}))) + " " + " ".join(
                fold(h["text"]) for h in knowledge.search(text, k=3))
            missing = [t for t in specific if not re.search(rf"\b{re.escape(t)}\b", known_txt)]
            if missing:
                goals.append("no_info"); facts["unknown_topic"] = missing[0]
        if re.search(r"\bbao hanh\b", f) and (mentioned or self.focus):
            par = mt._parent((mentioned or [self.focus])[-1])[0]
            if par and par["attributes"].get("warranty_months"):
                facts["product_warranty"] = {"product": par["name"], "warranty_months": par["attributes"]["warranty_months"]}
        sales_turn = it not in ("order_change", "order_status", "meta", "out_of_scope")
        profile_news = any(k in slots for k in ("room_area_m2", "has_children", "budget_vnd"))
        if sales_turn and not mentioned and not alt and (self.focus is None or (self.focus_by == "recommend" and profile_news)):
            rec = self._recommend(text)
            if rec == "ASK_NEED":
                goals.append("ask_need"); facts["need_slots_missing"] = [k for k in ("has_children", "budget_vnd", "room_area_m2") if k not in self.known]
                rec = None
            elif rec and rec != self.focus:
                old = self.focus
                self.focus, self.focus_by = rec, "recommend"
                facts["quote"] = self._quote(self._resolve_variant(rec, text), "advised"); goals.append("recommend")
                if old:
                    facts["alternative"] = self._quote(old, "alternative")
            if not rec and self.focus is None and "ask_need" not in goals and it in ("product_inquiry", "price_promo"):
                goals.append("ask_product")
        asks_price = it in ("price_promo", "negotiate", "product_inquiry") or (new_focus and new_focus != prev_focus) or bool(alt) or compare \
            or (it == "place_order" and asking) or "exchange_window_passed" in goals
        ask_size_after = False
        if sales_turn and "recommend" not in goals and asks_price:
            target = (alt or mentioned[-1]) if compare else self.focus
            if target and not compare and self._price_depends_on_size(target, text):
                if not self.size_asked:
                    self.size_asked = True
                    if self._promo_depends_on_size(target):
                        goals.append("ask_size_for_price"); target = None
                    else:
                        facts["size_note"] = "giá này cho size thường; size lớn có phụ thu"
                        ask_size_after = True
                else:
                    facts["size_note"] = "giá này cho size thường; size lớn có phụ thu và không áp một số khuyến mãi"
            if target:
                q = self._quote(self._resolve_variant(target, text), "alternative" if compare else "advised")
                if q.get("discontinued") and q.get("successor_sku"):
                    facts["discontinued_name"], facts["successor_name"] = q["name"], product_name(q["successor_sku"])
                    goals.append("discontinued")
                    if not compare:
                        self.focus = q["successor_sku"]
                    q = self._quote(self._resolve_variant(q["successor_sku"], text), "advised")
                if compare:
                    facts["alternative"] = q; goals.append("alternative_quote")
                else:
                    facts["quote"] = q
                    if q.get("in_stock") is False:
                        goals.append("out_of_stock"); facts["restock_expected"] = q.get("restock_expected")
                    else:
                        goals.append("quote")
                    if ask_size_after:
                        goals.append("ask_size_for_price")
                    claimed = [v for v in slots.get("claimed_prices", []) if v != q.get("final_price_vnd")]
                    if claimed and q.get("expired_promos"):
                        facts["claimed_price_vnd"] = claimed[0]; goals.append("explain_price_change")
        if self.cart and asking and re.search(r"\b(tong|het bao nhieu|tat ca|ca hai|giam gi|duoc giam)\b", f):
            facts["cart"] = self._cart_quote(text); goals.append("cart_total")
        if asking and re.search(r"\b(cod|thanh toan khi nhan)\b", f):
            tot = (facts.get("cart") or self._cart_quote(text) if self.cart else {}).get("total_vnd") if self.cart else (facts.get("quote") or {}).get("final_price_vnd")
            facts["cod_total_vnd"] = tot
            goals.append("cod_limit" if tot and tot > 10_000_000 else "cod_ok")
        if "?" in text and sales_turn and it != "place_order":
            hits = knowledge.search(text, k=2)
            if hits:
                facts.setdefault("policy", [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits])
        if it == "negotiate":
            goals.append("no_competitor_comment" if y("mentions_competitor", 0.5) else "refuse_discount")
        elif (y("mentions_competitor", 0.5) or re.search(r"\b(ben (do|kia|khac)|san thuong mai|shopee|lazada)\b", f)) and \
                re.search(r"\b(hang gia|hang nhai|kem chat luong|uy tin|chinh hang|duoc gi hon|khac gi|hon gi)\b", f):
            goals.append("no_competitor_comment")
        adding = bool(re.search(r"\b(lay them|them (cho|mot|1|cai)|mua them)\b", f)) and not CLOSE_ORDER_RX.search(f)
        wants = it == "place_order" and (y("agrees_to_buy", 0.5) or self.router.backend == "rules") and not adding
        if adding and self.cart and "cart_total" not in goals:
            facts["cart"] = self._cart_quote(text); goals.append("cart_total")
        if self.cart and "budget_vnd" in slots and "cart_total" not in goals:
            facts["cart"] = self._cart_quote(text); goals.append("cart_total")
        if wants:
            self.buy_intent = True
            if not self.cart and self.focus:
                self._cart_add(self.focus)
        pending = self.buy_intent and not asking and it not in ("callback", "negotiate", "order_change", "order_status") \
            and any(k in slots for k in ("address", "payment", "size", "color"))
        if self.orders_created and slots.get("address"):
            goals += self._update_address(slots["address"], facts)
        elif (wants and not asking) or pending:
            stale = [w for w in (self.brief or {}).get("stale_warnings", []) if self.focus and mt._parent(self.focus)[0]
                     and mt._parent(self.focus)[0]["sku"] in w and ("KM" in w or "giá" in w)]
            if stale and not self.price_change_told:
                self.price_change_told = True
                facts["quote"] = facts.get("quote") or self._quote(self._resolve_variant(self.focus, text), "advised")
                goals += ["stale_promo", "quote", "confirm_new_price"]
            else:
                goals += self._plan_order(text, facts)
        elif wants and asking and "quote" in goals:
            goals.append("confirm_order")
        if "stale_promo" in goals and not self.price_change_told:
            self.price_change_told = True
            if self.focus and "quote" not in facts:
                facts["quote"] = self._quote(self._resolve_variant(self.focus, text), "advised")
            goals.append("quote")
        if slots.get("callback_requested"):
            goals += self._plan_callback(slots["callback_requested"], facts)
        elif (it == "callback" and y("defers_decision", 0.5)) or y("defers_decision", 0.8):
            goals.append("defer_ack"); self.outcome = self.outcome or "hen_goi_lai"
        if not goals:
            garbled = self.input_mode == "asr_transcript" and route.get("confidence", 1) < 0.6
            if self.turn_no == 1:
                goals.append("greet")
            elif not slots and not mentioned and not CLOSING_RX.search(f) and (asking or garbled) and self.repeat_asked < 2:
                self.repeat_asked += 1
                goals.append("ask_repeat")
            else:
                goals.append("closing")
        if "no_info" in goals or "handoff" in goals:
            self.open_questions.append(text[:200])
        self.fail_streak = self.fail_streak + 1 if "order_failed" in goals else 0
        if self.fail_streak >= 2 and "handoff" not in goals:
            facts["handoff"] = self.tools.call("handoff.transfer", brief=self._handoff_brief(text, "loi_he_thong"))
            goals = [g for g in goals if g != "order_failed"] + ["handoff"]; self.outcome = "chuyen_may"
        return list(dict.fromkeys(goals)), facts

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
        total = sum(q["final_price_vnd"] or 0 for q in quotes)
        if any(q.get("in_stock") is False for q in quotes):
            bad = next(q for q in quotes if q.get("in_stock") is False)
            facts["quote"], facts["restock_expected"] = bad, bad.get("restock_expected")
            return ["out_of_stock"]
        cod_before = sum(o.get("total_vnd") or 0 for o in self.orders_created if o.get("payment") == "COD")
        if payment == "COD" and total + cod_before > 10_000_000:
            total += cod_before
            facts["cod_total_vnd"] = total; facts["cart"] = {"items": [{"name": q["name"], "final_price_vnd": q["final_price_vnd"]} for q in quotes], "total_vnd": total}
            return ["cod_limit"]
        made = []
        for q in quotes:
            args = dict(customer_phone=c.get("phone") or self.phone, sku=q["sku"], qty=1, price_vnd=q["final_price_vnd"],
                        promo_code=(q["promo_codes"] or [None])[0], payment=payment, address=self.known.get("address"),
                        basket_skus=[x for x in new if x != q["sku"]] or None)
            r = self.tools.call("order.create", **args)
            if r.get("error") == "price_mismatch":
                args["price_vnd"] = r["expected_price_vnd"]; r = self.tools.call("order.create", **args)
            if r.get("error"):
                facts["order_error"] = r["error"]; return ["order_failed"]
            made.append({**r, "sku": q["sku"], "price_vnd": args["price_vnd"], "payment": payment})
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
        if not self.known.get("address"):
            goals.append("ask_address")
        return goals

    def _customer_orders(self):
        c = self.customer or {}
        r = self.tools.call("order.status", customer_phone=c.get("phone") or self.phone)
        return r.get("orders", [])

    def _plan_order_change(self, text, facts):
        orders = self._customer_orders()
        if not orders:
            hits = knowledge.search(text, k=2)
            facts["policy"] = [{"chunk_id": h["chunk_id"], "text": h["text"][:600]} for h in hits]
            return ["policy_answer"] if hits else ["order_not_found"]
        want = self.known.get("variant_sku") or self.known.get("product_chosen")
        o = next((x for x in reversed(orders) if want and x.get("sku") == want), orders[-1])
        f = fold(text)
        od = o.get("created_on") or o.get("date")
        if od and (date.fromisoformat(self.today) - date.fromisoformat(od)).days > 7 + 4:
            facts["old_order"] = {"order_id": o["order_id"], "product": product_name(o["sku"]), "date": od}
            if not self.window_told:
                self.focus, self.focus_by = o["sku"], "memory"
            return ["WINDOW_PASSED"]
        if re.search(r"\bdia chi\b", f) and not re.search(r"tra hang|hoan tien|tra lai|\b(size|co|mau)\b", f) and not find_products(text):
            eta = self.known.get("estimated_delivery") if o["order_id"] == self.known.get("order_id") else None
            facts["order"] = {"order_id": o["order_id"], "product": product_name(o["sku"]), "address": self.known.get("address") or o.get("address"),
                              "estimated_delivery_ddmm": _ddmm(eta) if eta else None}
            return ["confirm_delivery_address"]
        if re.search(r"tra hang|hoan tien|khong dung nua|tra lai", f):
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
