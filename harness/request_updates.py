"""Thay đổi dự kiến từ nhãn có căn cứ; không suy ý khách bằng câu mẫu."""
import copy

from core.config import settings
import hashlib
import json

from harness.tools import mt, find_variant

PENDING = ("open", "conditional", "needs_target", "parked", "held")
WRITE_KINDS = ("place_order", "exchange", "return", "change_order_address", "callback")


def revision(requests, updates=None):
    state = {"items": requests.items, "proposal": requests.proposal, "refs": requests.refmap, "updates": updates}
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def payload_revision(request):
    state = {key: request.get(key) for key in ("kind", "lines", "condition", "selection", "on_unavailable")}
    if not request.get("selection"):
        state["target"] = request.get("target")
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _parent(sku):
    product, _ = mt._parent(sku)
    return product["sku"] if product else sku


def _pending(requests, kind, rid=None):
    rows = [r for r in requests.items if r["kind"] == kind and r["status"] in PENDING
            and (rid is None or r["id"] == rid)]
    return rows[0] if len(rows) == 1 else None


def _lines(session, requests, item, previous=None):
    out, error = [], None
    source = item.get("lines") or [{"target_ref": item.get("target_ref")}]
    for line in source:
        target = requests.refmap.get(line.get("target_ref")) or {}
        if target.get("type") != "product":
            error = "target_unresolved"
            continue
        for sku in target.get("skus") or ():
            old = next((x for x in previous or [] if _parent(x["sku"]) == _parent(sku)), {})
            product, variant = mt._parent(old.get("sku") or sku)
            size = line.get("size", (variant or {}).get("size"))
            color = line.get("color", (variant or {}).get("color"))
            resolved = find_variant(sku, "", size, color) if product and product.get("variants") else sku
            if resolved is None:
                resolved, error = _parent(sku), "variant"
            if line.get("qty_error"):
                # v6p4 (23/11): số lượng khách nói nhưng không kiểm được → giữ đúng món của dòng (không đổi thành mơ hồ), hỏi số lượng
                out.append({"sku": resolved, "qty": None, "size": size, "color": color, "qty_error": line["qty_error"]})
                error = error or "quantity"
                continue
            qty = line.get("qty", old.get("qty", 1))
            if type(qty) is not int or not 1 <= qty <= 20:
                error = "quantity"
                continue
            out.append({"sku": resolved, "qty": qty, "size": size, "color": color})
    if len({x["sku"] for x in out}) != len(out):
        error = "duplicate_line"
    return out, error


def _created_order_continuation(session, requests, raw):
    """v6p5: mọi mục mua của lượt là place_order / add_to_cart KHÔNG new_request, mỗi mục (và mỗi dòng) nhắm sản phẩm thuộc ĐÚNG MỘT
    đơn tạo trong cuộc, không có sửa giỏ, không còn yêu cầu mua đang chờ → ({order_id}, các mục đã dùng). Theo nhãn + trạng thái."""
    group = [x for x in raw if x.get("kind") in ("place_order", "add_to_cart", "edit_cart")]
    if not group or not getattr(session, "orders_created", None):
        return None
    if any(x.get("kind") == "edit_cart" or x.get("new_request") for x in group):
        return None
    if any(r["kind"] == "place_order" and r["status"] in PENDING for r in requests.items):
        return None

    def parents(item):
        refs = [item.get("target_ref")] + [ln.get("target_ref") for ln in item.get("lines") or []]
        out = set()
        for ref in refs:
            target = requests.refmap.get(ref) or {}
            if target.get("type") == "product":
                out |= {_parent(s) for s in target.get("skus", ())}
        return out

    hits = []
    for o in session.orders_created:
        skus = {_parent(ln["sku"]) for ln in o.get("lines") or [] if ln.get("sku")} or {_parent(x) for x in o.get("skus") or []}
        if all(parents(x) and parents(x) <= skus for x in group):
            hits.append(o)
    if len(hits) != 1:
        return None
    return {"order_id": hits[0]["order_id"]}, group


def _created_order_amendment(session, requests, raw):
    """v6p3: mọi mục mua / sửa giỏ của lượt đều nhắm sản phẩm thuộc ĐÚNG MỘT đơn tạo trong cuộc, có ít nhất một sửa bỏ / đổi, và
    không còn yêu cầu mua nào đang chờ → (thông tin sửa đơn, các mục đã dùng). Chỉ theo nhãn có cấu trúc + trạng thái, không theo câu."""
    edits = [x for x in raw if x.get("kind") == "edit_cart" and x.get("operation") in ("remove", "update", "replace")]
    if not edits or not getattr(session, "orders_created", None):
        return None
    if any(r["kind"] == "place_order" and r["status"] in PENDING for r in requests.items):
        return None
    group = [x for x in raw if x.get("kind") in ("edit_cart", "place_order", "add_to_cart")]

    def parents(item):
        target = requests.refmap.get(item.get("target_ref")) or {}
        return {_parent(s) for s in target.get("skus", ())} if target.get("type") == "product" else set()

    hits = []
    for o in session.orders_created:
        skus = {_parent(ln["sku"]) for ln in o.get("lines") or [] if ln.get("sku")} or {_parent(x) for x in o.get("skus") or []}
        if all(parents(x) and parents(x) <= skus for x in group):
            hits.append((o, skus))
    if len(hits) != 1:
        return None
    order, skus = hits[0]
    touched = set().union(*(parents(x) for x in edits))
    operation = "remove" if all(x["operation"] == "remove" for x in edits) else "update"
    return ({"order_id": order["order_id"], "operation": operation, "products": sorted(touched),
             "keep": sorted(skus - touched), "evidence": " / ".join(x.get("evidence") or "" for x in group)}, group)


def prepare(session, understanding, requests):
    """Dựng payload dự kiến; giao dịch thật chỉ đổi sau quyết định và kiểm revision."""
    u = copy.deepcopy(understanding)
    plans, seq = [], requests.seq
    raw = u.get("request_items") or []
    session.amend_created = None
    found = _created_order_amendment(session, requests, raw)
    if found:
        # v6p3 (23/11): khách bỏ / đổi món của đơn VỪA tạo trong cuộc → thao tác trên đơn đã có (planner: X_AMEND_ORDER), không
        # dựng lại thành yêu cầu mua mới từ giỏ (H13-025–028: request mua mới bị giữ, agent xin khách nói lại).
        amend, consumed = found
        session.amend_created = {**amend, "turn": session.turn_no}
        requests._event("amend_created_order", order_id=amend["order_id"], operation=amend["operation"])
        raw = [x for x in raw if not any(x is y for y in consumed)]
    session.order_continuation = None
    cont = _created_order_continuation(session, requests, raw)
    if cont:
        # v6p5 (23/11): lời đặt hàng nhắm món đã có trong đơn VỪA tạo (không "đặt thêm") → tiếp tục đơn đó (địa chỉ / thanh toán bổ
        # sung cho đơn), không mở yêu cầu mua mới (H13-026/027: hỏi lại "muốn lấy mẫu nào" sau khi chuyển yêu cầu sửa đơn)
        info, consumed = cont
        session.order_continuation = {**info, "turn": session.turn_no}
        requests._event("continuation_of_created_order", order_id=info["order_id"])
        raw = [x for x in raw if not any(x is y for y in consumed)]
    purchases = [x for x in raw if x["kind"] in ("place_order", "add_to_cart", "edit_cart")]
    orders = {}
    for item in purchases:
        key = item.get("order_group") or item.get("request_id") or "current_order"
        orders.setdefault(key, []).append(item)
    grouped = list(orders.values()) + [[x] for x in raw if x["kind"] in WRITE_KINDS and x not in purchases]
    for group in grouped:
        item = group[0]
        kind = "place_order" if item["kind"] in ("place_order", "add_to_cart", "edit_cart") else item["kind"]
        old = None if item.get("new_request") else _pending(requests, kind, item.get("request_id"))
        seq += old is None
        rid = old["id"] if old else f"R{seq}"
        plan = {"kind": kind, "request_id": rid, "evidence": " / ".join(x["evidence"] for x in group),
                "source_turn": session.turn_no, "action": "update", "target": copy.deepcopy((old or {}).get("target")),
                "condition": copy.deepcopy((old or {}).get("condition")), "lines": copy.deepcopy((old or {}).get("lines") or []),
                "selection": copy.deepcopy((old or {}).get("selection")),
                "purchase_consent": bool((old or {}).get("purchase_consent")), "error": None,
                "on_unavailable": copy.deepcopy((old or {}).get("on_unavailable"))}
        plan["additional"] = bool(item.get("new_request")) or bool((old or {}).get("additional"))
        if item.get("request_id") and old is None:
            plan["error"] = "request_unresolved"
        if not old and sum(r["kind"] == kind and r["status"] in PENDING for r in requests.items) > 1:
            plan["error"] = "request_unresolved"
        for part in group:
            if part.get("target_invalid"):
                plan["error"] = "target_unresolved"
            cond = part.get("condition")
            if cond is not None:
                if cond.get("type") == "none":
                    if part.get("condition_changed"):
                        plan["condition"] = None
                elif plan["condition"] and any(cond.get(k) != plan["condition"].get(k)
                        for k in ("type", "attribute", "expected", "max_vnd")) and not part.get("condition_changed"):
                    plan["error"] = "condition_unresolved"
                else:
                    plan["condition"] = {**cond, "source_turn": session.turn_no}
            if part.get("on_unavailable"):
                plan["on_unavailable"] = part["on_unavailable"]
            if kind != "place_order":
                plan["target"] = copy.deepcopy(requests.refmap.get(part.get("target_ref")))
                plan["basis"] = "model_context"
                if settings.address_scope_gate and kind == "change_order_address":
                    plan.update({k: part.get(k) for k in ("address_scope", "address_scope_span", "order_state_claim", "order_state_span")})
                if settings.write_path_gate and kind in ("exchange", "return"):
                    plan.update(mode=part.get("mode") or "unclear", mode_span=part.get("mode_span") or "")
                if kind != "callback" and plan["target"] and plan["target"].get("type") != "order":
                    plan["error"] = "order_target"
                continue
            if part["kind"] == "edit_cart":
                if not plan["lines"]:
                    plan["lines"] = [{"sku": sku, "qty": 1} for sku in session.cart]
                target = requests.refmap.get(part.get("target_ref")) or {}
                matches = [x for x in plan["lines"] if _parent(x["sku"]) in target.get("skus", ())]
                operation = part.get("operation")
                if operation != "add" and len(matches) != 1:
                    plan["error"] = "cart_line_unresolved"
                    continue
                if operation == "remove":
                    plan["lines"].remove(matches[0])
                elif operation in ("add", "replace", "update"):
                    replacement = copy.deepcopy(part)
                    if operation == "replace":
                        replacement["lines"] = [{**(part.get("lines") or [{}])[0], "target_ref": part.get("replacement_ref")}]
                    additions, error = _lines(session, requests, replacement, matches)
                    plan["error"] = error or plan["error"]
                    if operation != "add":
                        plan["lines"].remove(matches[0])
                    plan["lines"].extend(additions)
                else:
                    plan["error"] = "cart_operation_unresolved"
            else:
                additions, error = _lines(session, requests, part, plan["lines"])
                plan["error"] = error or plan["error"]
                if part["kind"] == "place_order":
                    if not any(x["kind"] == "edit_cart" for x in group) or not plan["lines"]:
                        if part is group[0]:
                            plan["lines"] = []
                        plan["lines"].extend(additions)
                    plan["purchase_consent"] = True
                else:
                    plan["lines"].extend(x for x in additions if x["sku"] not in {v["sku"] for v in plan["lines"]})
                selection = requests.selection_criteria(session, u)
                if selection:
                    # v6p4 (23/11): yêu cầu chọn theo tiêu chí chỉ nhận số lượng gắn vào dòng của chính yêu cầu (quantity có căn cứ),
                    # không lấy số lượng tự do của lượt (H13-046: "hai cái máy bữa trước" → đơn 2 máy)
                    marked = [x for x in part.get("lines") or [] if x.get("qty") or x.get("qty_error")]
                    plan["error"] = None if error == "target_unresolved" else plan["error"]
                    if any(x.get("qty_error") for x in marked) or len({x.get("qty") for x in marked}) > 1:
                        plan["error"] = "quantity"
                    elif marked:
                        selection = {**selection, "qty": marked[0]["qty"]}
                    plan["selection"] = selection
                basis = part.get("target_basis") or ("named" if session.turn_mentioned else "context")
                plausible = {v["skus"][0] for k, v in requests.refmap.items() if k.startswith("P") and v.get("type") == "product"}
                accepted = (u.get("response") or {}).get("act") == "accept" and requests.proposal
                if basis == "unknown" or (basis == "context" and len(plausible) > 1 and not old and not accepted and not selection):
                    plan["error"] = "target_unresolved"
                # v6p6 (23/11): lời TIẾP TỤC đúng yêu cầu đang mở đã có đối tượng rõ, không nêu món mới (vd chỉ bổ sung thanh toán) →
                # giữ đối tượng cũ dù model gắn basis=named mà câu không nhắc tên (H13-025 lượt 3). Yêu cầu cũ còn mơ hồ (chưa có
                # đối tượng / đang thiếu đối tượng) thì giữ mơ hồ, không tự chọn món.
                old_target = {_parent(x) for x in ((old or {}).get("target") or {}).get("skus", ())}                     if old and (old.get("missing") or None) not in ("target_unresolved", "cart_line_unresolved") else set()
                continuing = bool(old_target) and bool(additions) and all(_parent(x["sku"]) in old_target for x in additions)
                if continuing and basis == "named":
                    requests._event("target_kept_on_continuation", id=old["id"])
                if basis == "named" and not continuing                         and any(_parent(x["sku"]) not in {_parent(s) for s in session.turn_mentioned} for x in additions):
                    plan["error"] = "target_unresolved"
                plan["basis"] = basis
        if kind == "place_order":
            plan["target"] = {"type": "product", "skus": tuple(x["sku"] for x in plan["lines"])} if plan["lines"] else None
            if not plan["target"] and not plan["selection"]:
                plan["error"] = "target_unresolved"
        plans.append(plan)
    for withdrawn in u.get("withdrawn") or []:
        old = _pending(requests, withdrawn["kind"], withdrawn.get("request_id"))
        plans.append({"kind": withdrawn["kind"], "request_id": old["id"] if old else "none", "action": "withdraw",
                      "evidence": withdrawn["evidence"], "target": (old or {}).get("target"),
                      "error": None if old else "withdraw_target_ambiguous"})
    touched = {p["request_id"] for p in plans}
    prop, response = requests.proposal, u.get("response") or {}
    if prop and response.get("act") in ("accept", "decline", "defer") and not plans:
        old = _pending(requests, prop["kind"])
        seq += old is None
        plan = {"kind": prop["kind"], "request_id": old["id"] if old else f"R{seq}",
                "action": "update" if response["act"] == "accept" else "withdraw", "target": prop.get("target"),
                "lines": [{"sku": sku, "qty": (prop.get("revision") or {}).get("qty", 1)} for sku in (prop.get("target") or {}).get("skus", ())],
                "condition": (old or {}).get("condition"), "selection": (old or {}).get("selection"),
                "evidence": response.get("evidence"), "purchase_consent": response["act"] == "accept", "basis": "accepted_proposal",
                "proposal_revision": prop.get("revision"), "error": "accept_stale" if prop.get("carried") else None}
        plans.append(plan); touched.add(plan["request_id"])
    if not u.get("error") and (u.get("ambiguity") or {}).get("level") != "needs_clarification":
        for old in requests.items:
            if old["status"] in PENDING and old["id"] not in touched and old["kind"] in WRITE_KINDS:
                plan = {**copy.deepcopy(old), "request_id": old["id"], "action": "continue",
                        "error": old.get("missing") if old.get("missing") not in (None, "jev_hold") else None}
                choices = {key: value for key, value in (u.get("slots") or {}).items() if key in ("size", "color", "qty")}
                if old["kind"] == "place_order" and choices:
                    if len(plan.get("lines") or []) == 1:
                        line = plan["lines"][0]
                        line.update(choices)
                        product, variant = mt._parent(line["sku"])
                        size = line.get("size", (variant or {}).get("size"))
                        color = line.get("color", (variant or {}).get("color"))
                        sku = find_variant(line["sku"], "", size, color) if product and product.get("variants") else line["sku"]
                        if sku:
                            line["sku"] = sku
                            plan["target"] = {"type": "product", "skus": (sku,)}
                            if plan["error"] == "variant":
                                plan["error"] = None
                        else:
                            plan["error"] = "variant"
                    else:
                        plan["error"] = "cart_line_unresolved"
                plans.append(plan)
    for plan in plans:
        if sum(p["request_id"] == plan["request_id"] for p in plans) > 1:
            plan["error"] = "conflicting_request_updates"
    for i, plan in enumerate(plans):
        ref = f"U{i + 1}"
        if plan.get("target"):
            requests.refmap[ref] = plan["target"]
        plan["target_ref"] = ref if plan.get("target") else "none"
    u["updates"] = plans
    return u, {"raw": {"request_items": understanding.get("request_items"), "withdrawn": understanding.get("withdrawn")},
               "normalized": {"updates": plans}, "reasons": ["structured_request_updates"] if plans else []}


def apply(requests, session, u, gate, turn):
    """Áp quyết định trên đúng trạng thái đã xét; không đọc lại ý khách bằng regex."""
    from harness.request_state import ACTIVE, ORDER_KINDS
    requests.turn_act = (u.get("response") or {}).get("act")
    if u.get("error") or (u.get("ambiguity") or {}).get("level") == "needs_clarification":
        requests.hold = "understanding_error" if u.get("error") else "ambiguous_turn"
        return
    if not gate or gate.get("state_revision") != revision(requests, u.get("updates")):
        if u.get("updates"):
            requests.hold = "jev_request_revision"
        return
    if len(u.get("updates") or []) != len(gate.get("updates") or []):
        requests.hold = "jev_request_revision"
        return
    session.semantic_cart_before = list(session.cart)
    old_held = []
    for plan, decision in zip(u.get("updates") or [], gate.get("updates") or []):
        rid = plan["request_id"]
        old = next((r for r in requests.items if r["id"] == rid and r["status"] in PENDING), None)
        if decision.get("request_id") != rid or decision.get("error"):
            decision = {**decision, "decision": "hold_and_clarify"}
        if plan["action"] == "withdraw" or (plan["action"] == "continue" and decision["decision"] == "reject_or_withdraw"):
            if old and decision["decision"] == "reject_or_withdraw" and not plan.get("error"):
                requests._withdraw(old["kind"], turn, "semantic_withdraw", req_id=rid)
                requests.proposal = None
                if old is requests.held_candidate:
                    requests.held_candidate = None
            elif old is None and not requests.held_candidate \
                    and not any(r["kind"] == plan["kind"] and r["status"] in PENDING for r in requests.items):
                # v6p2 (23/11): không có yêu cầu nào cùng loại đang chờ → rút/hoãn không có đối tượng, không có gì để hỏi lại
                # (H13-047/048: khách hoãn sau câu hỏi chọn mẫu, agent hỏi lặp). Không ghi gì, không giữ lượt.
                requests._event("withdraw_nothing_pending", kind=plan["kind"])
            else:
                requests.hold = "withdraw_target_ambiguous"
            continue
        if settings.address_scope_gate and plan["kind"] == "change_order_address":
            from harness.request_state import _address_scope_check
            why = _address_scope_check(u, plan, {"updates": [{**decision, "kind": "change_order_address"}]})
            if why == "profile_default":
                requests.address_profile = {"turn": turn, "evidence": (plan.get("evidence") or "")[:60],
                                            "scope_span": plan.get("address_scope_span")}
                requests._event("address_profile_default", id=rid)
                continue
            if why:
                if why == "deferred" and old:
                    requests._withdraw(old["kind"], turn, "deferred", req_id=rid)
                requests.op_gate = {"why": why, "kind": "change_order_address"}
                requests._event("op_blocked", kind="change_order_address", why=why)
                continue
        if settings.write_path_gate and plan["kind"] in ("exchange", "return") and plan["action"] != "continue" \
                and decision["decision"] == "open_or_update_request" and not decision.get("error"):
            from harness.request_state import _op_mode_check
            why = _op_mode_check(u, plan, decision)
            if why:
                if why == "deferred" and old:
                    requests._withdraw(old["kind"], turn, "deferred", req_id=rid)
                if why == "ask_info":
                    requests._event("op_ask_info", kind=plan["kind"], id=rid)      # chỉ trả lời câu hỏi, không mở yêu cầu ghi
                else:
                    requests.op_gate = {"why": why, "kind": plan["kind"]}
                    requests._event("op_blocked", kind=plan["kind"], why=why)
                continue
        if old is None:
            requests.seq += 1
            if rid != f"R{requests.seq}":
                requests.hold = "jev_request_revision"
                continue
            old = {"id": rid, "created_turn": turn}
            requests.items.append(old)
        allowed = decision["decision"] == "open_or_update_request" and not decision.get("error") and not plan.get("error")
        data = {k: copy.deepcopy(v) for k, v in plan.items() if k not in ("request_id", "action", "error", "status", "write_gate")}
        old.update(data, turn=turn, source="semantic_customer_request", semantic=True)
        old["missing"] = plan.get("error") or ("jev_hold" if not allowed else None)
        old["intent_authorized"] = allowed and (plan["kind"] != "place_order" or bool(plan.get("purchase_consent")))
        old["status"] = ("conditional" if old.get("condition") else "open") if old["intent_authorized"] else "held"
        old["revision"] = plan.get("proposal_revision") or (plan.get("revision") if plan["action"] == "continue" else None) or (requests.selection_revision(session, (plan.get("target") or {}).get("skus", ()))
                            if plan["kind"] == "place_order" else None)
        old["bound"] = plan["action"] == "continue" or bool(plan.get("proposal_revision"))
        if plan["kind"] == "place_order":
            old["revision"] = {**(old.get("revision") or {}), **requests.delivery_terms(session)}
        old.pop("write_gate", None)
        if old["intent_authorized"]:
            old["write_gate"] = {"request_id": rid, "evidence_turn": turn, "target_ref": plan["target_ref"],
                                 "revision": decision["revision"], "selected_request_id": rid,
                                 "payload_revision": payload_revision(old)}
        else:
            old_held.append(old)
        if plan["kind"] in ORDER_KINDS:
            old.update(target_basis="model_context" if plan.get("target") else None, target_block=None,
                       target_ambiguous=bool(plan.get("error")), consent={"kind": plan["kind"], "source": old["source"],
                       "turn": turn, "target": (plan.get("target") or {}).get("order_id")})
            if plan["kind"] == "change_order_address":
                requests._bind_command(session, u, old, turn)
        if plan["kind"] == "place_order" and allowed:
            session.cart = [line["sku"] for line in plan["lines"]]
        requests.proposal = None
        requests._event("request_updated", id=rid, kind=old["kind"], status=old["status"], missing=old["missing"])
    requests.held_candidate = old_held[0] if old_held else None
    requests._bind_answer_address(session, u, turn)
    requests._conflict_check(session, u, turn)
