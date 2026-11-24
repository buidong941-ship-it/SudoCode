"""Ứng viên quyền ghi: Jev chỉ phân loại, executor vẫn kiểm mọi dữ kiện trước tool."""
import json
import time

from core.config import settings
from core.pii import Redactor


def normalize(session, understanding, requests):
    from harness.request_updates import prepare
    return prepare(session, understanding, requests)


def _product_evidence(session, requests):
    """Bằng chứng công khai theo SKU; giá cũ không được trình bày như giá vừa kiểm."""
    rows = {}
    for tool in list(getattr(session, "call_tool_log", [])) + list(getattr(session, "start_tool_log", [])) + list(getattr(getattr(session, "tools", None), "log", [])):
        name, args, result = tool.get("name"), tool.get("args") or {}, tool.get("result")
        if name not in ("pricing.get_quote", "inventory.check") or not isinstance(result, dict) or result.get("error"):
            continue
        sku = args.get("sku")
        if not sku or args.get("basket_skus"):
            continue
        row = rows.setdefault(sku, {"sku": sku})
        key = "quote" if name == "pricing.get_quote" else "stock"
        fields = ("final_price_vnd", "list_price_vnd") if key == "quote" else ("in_stock", "qty", "restock_expected")
        row[key] = {k: result[k] for k in fields if k in result}
        row[key].update(source=name, checked_turn=tool.get("_turn"),
                        on=args.get("on"), scope="unit" if key == "quote" else "sku",
                        checked_this_turn=tool.get("_turn") == session.turn_no)
    return {"products": list(rows.values()),
            "refs": {ref: value for ref, value in requests.refmap.items() if value.get("type") == "product"}}


ADDRESS_SCOPE_CRITERIA = {
    "existing_order": "Khách muốn đổi địa chỉ giao của một đơn đang có.",
    "profile_default": "Khách dặn địa chỉ mới cho các đơn sau / hồ sơ, không nhắm đổi một đơn đang giao.",
    "unclear": "Chưa rõ là đơn đang có hay các đơn sau.",
}
ORDER_STATE_CRITERIA = {
    "delivered": "Khách kể đơn đích đã nhận / đã giao.",
    "cancelled": "Khách kể đơn đích đã hủy.",
    "returned": "Khách kể đơn đích đã trả hàng.",
    "none": "Khách không kể trạng thái đơn.",
    "unclear": "Khách có kể nhưng không rõ trạng thái nào.",
}
MODE_CRITERIA = {
    "direct": "Khách yêu cầu làm thao tác đổi / trả ngay.",
    "conditional": "Khách chỉ muốn làm nếu đạt một điều kiện khách nêu.",
    "ask_info": "Khách mới hỏi thông tin (phí, điều kiện, có được không) trước khi quyết, chưa yêu cầu làm.",
    "defer": "Khách nói để sau / chưa quyết.",
    "unclear": "Chưa rõ khách yêu cầu làm hay chỉ hỏi.",
}


def assess(session, understanding, requests, turn, decider=None):
    """JEV xét từng thay đổi đã có đối tượng; một lỗi không cấp quyền ghi."""
    from harness.request_updates import revision
    expected = revision(requests, understanding.get("updates"))
    decisions = {
        "open_or_update_request": "Khách yêu cầu thao tác này hoặc tiếp tục đúng yêu cầu còn hiệu lực. Điều kiện đã hiểu nhưng chưa đọc tool vẫn được mở có điều kiện; executor kiểm trước ghi.",
        "hold_and_clarify": "Chưa rõ ý, đối tượng hoặc thay đổi; không suy lựa chọn từ focus hay địa chỉ/COD.",
        "reject_or_withdraw": "Khách rút rõ chính yêu cầu chưa ghi này; không dùng cho bỏ một dòng hay đổi/hủy đơn đã tạo.",
    }
    results = []
    hidden = ("address_scope", "address_scope_span", "order_state_claim", "order_state_span", "mode", "mode_span")
    shown_all = [{k: v for k, v in x.items() if k not in hidden} for x in understanding.get("updates") or []]
    for update in understanding.get("updates") or []:
        rid, ref = update["request_id"], update["target_ref"]
        scoped = settings.address_scope_gate and update.get("kind") == "change_order_address"
        moded = settings.write_path_gate and update.get("kind") in ("exchange", "return") and update.get("action") != "continue"
        out = {"decision": "hold_and_clarify", "request_id": rid, "target_ref": ref,
               "revision": expected, "evidence_turn": turn, "ms": 0}
        if update.get("error"):
            results.append({**out, "error": update["error"]})
            continue
        state = Redactor().redact({
            "customer_text": session.turn_text, "customer_turn": turn, "recent_turns": session.history[-6:],
            "proposed_update": {k: v for k, v in update.items() if k not in hidden} if scoped or moded else update,
            "all_updates": shown_all if settings.address_scope_gate or settings.write_path_gate else understanding.get("updates"),
            "requests": requests.items, "agent_proposal": requests.proposal,
            "response": understanding.get("response"), "safety": understanding.get("safety"),
            "revision": expected, "product_refs": requests.refmap,
            "product_evidence": _product_evidence(session, requests),
        })
        started = time.perf_counter()
        try:
            if set(understanding.get("safety") or []) & {"prompt_injection", "asks_other_customer", "proxy_claim"}:
                raise ValueError("unsafe_identity_or_instruction")
            if decider is None:
                if settings.jev_simulated:
                    raise RuntimeError("JEV unavailable")
                from typesafe_sdk import Choice
                from harness.question_classifiers.jev_slots import _client
                questions = {
                    "decision": Choice(instructions="Xét ý khách trên đúng proposed_update; không tạo dữ liệu tool hoặc tự chọn mẫu khác. Khi action=continue, chỉ tiếp tục nếu cam kết cũ còn hiệu lực và câu mới không rút/hoãn nó.", criteria=decisions),
                    "request_id": Choice(instructions="Giữ đúng ID của proposed_update.", criteria={rid: rid}),
                    "target_ref": Choice(instructions="Đối tượng của proposed_update; none nếu chưa phân giải.", criteria={ref: ref}),
                    "revision": Choice(instructions="Phiên bản trạng thái đang xét.", criteria={expected: expected}),
                }
                if scoped:
                    questions["address_scope"] = Choice(instructions="Phạm vi địa chỉ khách vừa nói trong customer_text.",
                                                        criteria=ADDRESS_SCOPE_CRITERIA)
                    questions["order_state_claim"] = Choice(instructions="Khách có KỂ trạng thái của đơn đích trong customer_text không.",
                                                            criteria=ORDER_STATE_CRITERIA)
                if moded:
                    questions["mode"] = Choice(instructions="Kiểu lời khách trong customer_text đối với thao tác đổi / trả này.",
                                               criteria=MODE_CRITERIA)
                raw = _client().system_one(state=state, questions=questions, model=settings.jev_model)
                result = {key: raw.choices[key].choice for key in questions}
            else:
                opts = {"decisions": decisions, "request_ids": [rid], "target_refs": [ref], "revision": expected}
                if scoped:
                    opts.update(address_scope=list(ADDRESS_SCOPE_CRITERIA), order_state_claim=list(ORDER_STATE_CRITERIA))
                if moded:
                    opts.update(mode=list(MODE_CRITERIA))
                result = decider(state, opts)
            result = json.loads(json.dumps(result))
            keys = {"decision", "request_id", "target_ref", "revision"} | ({"address_scope", "order_state_claim"} if scoped else set()) \
                | ({"mode"} if moded else set())
            if set(result) != keys or result["decision"] not in decisions \
                    or result["request_id"] != rid or result["target_ref"] != ref or result["revision"] != expected:
                raise ValueError("invalid_choice_or_revision")
            if scoped and (result["address_scope"] not in ADDRESS_SCOPE_CRITERIA or result["order_state_claim"] not in ORDER_STATE_CRITERIA):
                raise ValueError("invalid_address_scope_choice")
            if moded and result["mode"] not in MODE_CRITERIA:
                raise ValueError("invalid_mode_choice")
            if scoped or moded:
                out["kind"] = update.get("kind")
            if result["decision"] == "reject_or_withdraw" and update["action"] != "withdraw":
                # A pending request may also be deferred by the current customer turn.
                if update["action"] != "continue":
                    raise ValueError("withdraw_scope_mismatch")
            out.update(result)
        except Exception as exc:
            out["error"] = f"{type(exc).__name__}:{str(exc)[:120]}"
        out["ms"] = int((time.perf_counter() - started) * 1000)
        results.append(out)
    first = results[0] if len(results) == 1 else {"decision": "hold_and_clarify", "request_id": "none", "target_ref": "none"}
    return {**first, "updates": results, "state_revision": expected, "evidence_turn": turn}
