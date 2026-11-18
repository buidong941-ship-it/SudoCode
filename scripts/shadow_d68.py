"""D68 shadow (chỉ đọc): một bộ hiểu lượt (Qwen) trả observations / requests / safety / ambiguity theo hợp đồng D68,
chấm với gold đã được người dùng duyệt (runs/shadow-d68/ra-codex-20261110/nhan_de_xuat.json); rules chỉ là đối chứng.

    python scripts/shadow_d68.py <gold.json> <phieu.csv> <rules_doi_chung.jsonl> <out_dir>

Không ghi gì vào world, không có executor; module KHÔNG được runtime import (bộ hiểu mới chưa điều khiển giao dịch).
Đặc tả chấm v1 (đóng băng trước khi chạy, theo mục 5 báo cáo rà):
- requests là Ý ĐỊNH khách (giữ cả khi thiếu đối tượng); thiếu target/điều kiện là việc của executor, không chấm ở đây.
- Lượt có issue `contract_gap` hoặc `missing_history` không chấm requests/ambiguity (gold chưa đủ hợp đồng / thiếu lịch sử).
- `annotation_boundary`: chấp nhận requests chính hoặc `alternative_requests`.
- safety không chấm ở lượt có `safety_label_gap` / `safety_definition_gap`.
- observations chỉ chấm slot lựa chọn: payment, address, size, color, qty, budget_vnd (khóa, không chấm giá trị nguyên văn).
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUESTS = ["place_order", "change_order_address", "exchange", "return", "cancel", "callback", "handoff", "forget_me", "order_status"]
WRITE_REQ = {"place_order", "change_order_address", "exchange", "return", "cancel", "callback"}
SAFETY = ["asks_internal_cost", "medical_question", "asks_other_customer", "wants_data_deleted", "asks_if_bot", "proxy_claim"]
OBS = ["payment", "address", "size", "color", "qty", "budget_vnd", "callback_time_text", "recipient_phone", "product_mention"]
SCORED_OBS = {"payment", "address", "size", "color", "qty", "budget_vnd"}

PROMPT = """Bạn là bộ hiểu một lượt nói của KHÁCH trong cuộc gọi bán hàng. Chỉ đọc câu khách hiện tại (câu nhân viên ngay trước chỉ để hiểu ngữ cảnh).
Trả JSON:
- observations: object {{slot: {{value, span}}}} cho thông tin khách NÓI RÕ trong câu này. slot thuộc {obs}. span là đoạn nguyên văn trong câu khách.
  payment value là "COD" hoặc "bank". Hỏi về một phương án (có COD không?) KHÔNG phải chọn phương án đó. size/color chỉ khi khách CHỌN.
- requests: danh sách hành động khách YÊU CẦU shop làm, thuộc {req}. Câu hỏi/giả định/cân nhắc không phải yêu cầu.
  "anh/chị gọi lại sau" là khách tự gọi, KHÔNG phải callback; "mai 9 giờ em gọi lại cho chị" là callback.
  Yêu cầu vẫn ghi dù thiếu mã đơn hay điều kiện ("về rồi thì giao" vẫn là place_order).
- safety: danh sách cờ thuộc {saf}, chỉ khi câu thể hiện rõ (asks_internal_cost: đòi giá nhập/giá sàn/giá nội bộ;
  asks_if_bot: hỏi có phải người máy/AI; proxy_claim: tự xưng người nhà/nhân viên/quản lý để đòi quyền).
- ambiguity: {{"level": "none" | "needs_clarification", "reason": "..."}} — chỉ needs_clarification khi ý nghĩa hoặc đối tượng chưa rõ cần hỏi lại.

Nhân viên vừa nói: {prev}
Khách: {text}"""

SCHEMA = {"type": "object", "required": ["observations", "requests", "safety", "ambiguity"], "additionalProperties": False,
          "properties": {"observations": {"type": "object"},
                         "requests": {"type": "array", "items": {"type": "string", "enum": REQUESTS}},
                         "safety": {"type": "array", "items": {"type": "string", "enum": SAFETY}},
                         "ambiguity": {"type": "object", "required": ["level"],
                                       "properties": {"level": {"type": "string", "enum": ["none", "needs_clarification"]},
                                                      "reason": {"type": "string"}}}}}


BACKEND = os.environ.get("SHADOW_BACKEND", "qwen")   # qwen (giả lập, mặc định) | deepseek | jev (API thật, cần key)
CALLS = {"requests": 0, "errors": 0}

# Jev là bộ phân loại (Choice), không sinh JSON tự do: mỗi nhãn là một câu hỏi yes/no, cùng quy tắc như PROMPT.
REQ_DESC = {"place_order": "asks the shop to place/create an order now (still yes if item/condition is missing, e.g. 'ship it when back in stock')",
            "change_order_address": "asks to change the delivery address of an existing order",
            "exchange": "asks to exchange an item of an existing order", "return": "asks to return an item / get a refund",
            "cancel": "asks to cancel an order", "callback": "asks the SHOP to call the customer back later "
            "('call me at 9 tomorrow' = yes; 'I will call you back later' = the customer calls, so no)",
            "handoff": "asks to be transferred to a human staff member", "forget_me": "asks the shop to delete their personal data",
            "order_status": "asks about the status/delivery of an existing order"}
SAF_DESC = {"asks_internal_cost": "demands internal cost / import price / floor price", "medical_question": "asks a medical/health question",
            "asks_other_customer": "asks for information about another customer", "wants_data_deleted": "wants their data deleted",
            "asks_if_bot": "asks whether the agent is a robot/AI",
            "proxy_claim": "claims to be a relative / staff / manager to obtain rights"}
OBS_DESC = {"payment": "states a CHOSEN payment method (COD or bank transfer); asking whether COD exists is not choosing",
            "address": "states a delivery address", "size": "chooses a size", "color": "chooses a color",
            "qty": "states a quantity to buy", "budget_vnd": "states a budget amount"}


def _jev(prev, text):
    from typesafe_sdk import Choice
    from core.config import settings
    from core.pii import Redactor
    from harness.question_classifiers.jev_slots import _client
    safe = Redactor().redact({"sentence": text, "context": prev or ""})
    yn = {"yes": "Clearly present in the current customer sentence", "no": "Not present / only a question, hypothesis or consideration"}
    q = {f"req__{k}": Choice(instructions=f"Is the CUSTOMER requesting the shop to act: {d}? A question, hypothesis or "
                             "consideration is not a request. Restating something already done is not a new request.", criteria=yn)
         for k, d in REQ_DESC.items()}
    q.update({f"saf__{k}": Choice(instructions=f"Does the current customer sentence clearly show: {d}?", criteria=yn) for k, d in SAF_DESC.items()})
    q.update({f"obs__{k}": Choice(instructions=f"Does the current customer sentence explicitly state: {d}? Privacy codes like "
                                  "[ĐỊA_CHỈ_1] stand for a real masked address.", criteria=yn) for k, d in OBS_DESC.items()})
    q["ambiguity"] = Choice(instructions="Is the meaning or target of the customer sentence unclear so the agent must ask to clarify?",
                            criteria={"none": "Clear enough to act or answer", "needs_clarification": "Unclear meaning/target, must ask"})
    r = _client().system_one(state={"role": "customer", "sentence": safe["sentence"], "previous_agent_sentence": safe["context"]},
                             questions=q, model=settings.jev_model)
    ch = {k: r.choices[k].choice for k in q}
    pick = lambda pre: sorted(k.split("__", 1)[1] for k, v in ch.items() if k.startswith(pre) and v == "yes")
    return {"observations": {k: {"value": None, "span": None} for k in pick("obs__")}, "requests": pick("req__"),
            "safety": pick("saf__"), "ambiguity": {"level": ch["ambiguity"] if ch["ambiguity"] in ("none", "needs_clarification") else "none"}}


def understand(prev, text):
    from core.llm.deepseek import LLM
    CALLS["requests"] += 1
    if BACKEND == "jev":
        return _jev(prev, text)
    if BACKEND == "deepseek":     # API ngoài: che SĐT/địa chỉ trước khi gửi, như đường generator
        from core.pii import Redactor
        safe = Redactor().redact({"prev": prev or "", "text": text})
        prev, text = safe["prev"], safe["text"]
    prompt = PROMPT.format(obs=", ".join(OBS), req=", ".join(REQUESTS), saf=", ".join(SAFETY), prev=prev or "(đầu cuộc gọi)", text=text)
    llm = LLM("deepseek") if BACKEND == "deepseek" else LLM("qwen", role="extract")
    d = llm.json(prompt, schema=SCHEMA, cache=False, max_tokens=400)
    obs = {k: v for k, v in (d.get("observations") or {}).items() if k in OBS}
    return {"observations": obs, "requests": sorted(set(d.get("requests") or []) & set(REQUESTS)),
            "safety": sorted(set(d.get("safety") or []) & set(SAFETY)), "ambiguity": d.get("ambiguity") or {"level": "none"}}


def rules_view(r):
    """Đối chứng: rules thực sự LÀM gì ở lượt đó (goal/tool/cờ router), quy về cùng từ vựng. Không phải nhãn ý định."""
    g, tools = set(r.get("goals") or []), set(r.get("tools") or [])
    req = set()
    if "order.create" in tools or g & {"order_created", "order_partial", "order_unresolved"}:
        req.add("place_order")
    if g & {"order_updated"}:
        req.add("return")
    if "address_updated" in g:
        req.add("change_order_address")
    if "schedule.callback" in tools or "callback_scheduled" in g:
        req.add("callback")
    if "handoff.transfer" in tools or "handoff" in g:
        req.add("handoff")
    if "order_status" in g:
        req.add("order_status")
    if "data_deleted" in g:
        req.add("forget_me")
    fl = r.get("flags") or {}
    saf = {k for k in ("asks_internal_cost", "medical_question", "wants_data_deleted", "asks_if_bot") if fl.get(k, 0) >= 0.6}
    return {"requests": sorted(req), "safety": sorted(saf)}


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": None if p is None else round(p, 3), "recall": None if r is None else round(r, 3),
            "f1": None if f is None else round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def score(gold, pred, fields=("requests", "safety", "observations", "ambiguity")):
    c = {f: [0, 0, 0] for f in ("requests", "safety", "observations")}
    false_write, amb_ok, amb_n, n_req, n_saf, details = 0, 0, 0, 0, 0, []
    for gi in gold:
        p = pred.get(gi["turn_id"])
        if p is None:
            continue
        iss = set(gi["issues"])
        row = {"turn_id": gi["turn_id"]}
        if "requests" in fields and not iss & {"contract_gap", "missing_history"}:
            n_req += 1
            gs, ps = set(gi["requests"]), set(p["requests"])
            if "annotation_boundary" in iss and gi.get("alternative_requests"):
                alts = [set(a if isinstance(a, list) else [a]) for a in gi["alternative_requests"]]
                gs = next((a for a in [gs] + alts if a == ps), gs)
            c["requests"][0] += len(gs & ps); c["requests"][1] += len(ps - gs); c["requests"][2] += len(gs - ps)
            fw = sorted((ps & WRITE_REQ) - gs) if not gs & WRITE_REQ else []
            false_write += bool(fw)
            row.update(gold_requests=sorted(gs), pred_requests=sorted(ps), false_write=fw)
        if "safety" in fields and not iss & {"safety_label_gap", "safety_definition_gap"}:
            n_saf += 1
            gs, ps = set(gi["safety"]), set(p["safety"])
            c["safety"][0] += len(gs & ps); c["safety"][1] += len(ps - gs); c["safety"][2] += len(gs - ps)
            row.update(gold_safety=sorted(gs), pred_safety=sorted(ps))
        if "observations" in fields and "observations" in p:
            gs = set(gi["observations"]) & SCORED_OBS
            ps = set(p["observations"]) & SCORED_OBS
            c["observations"][0] += len(gs & ps); c["observations"][1] += len(ps - gs); c["observations"][2] += len(gs - ps)
            row.update(gold_obs=sorted(gs), pred_obs=sorted(ps))
        if "ambiguity" in fields and "ambiguity" in p and not iss & {"contract_gap", "missing_history"}:
            amb_n += 1
            amb_ok += (p["ambiguity"].get("level") == gi["ambiguity"]["level"])
        details.append(row)
    out = {f: prf(*c[f]) for f in c if f in fields}
    out.update(turns_scored_requests=n_req, turns_scored_safety=n_saf, false_write_turns=false_write)
    if "ambiguity" in fields:
        out["ambiguity_accuracy"] = round(amb_ok / amb_n, 3) if amb_n else None
    return out, details


def main():
    gold_path, csv_path, rules_path, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    from core.config import settings
    if BACKEND in ("jev", "deepseek"):   # API thật: thiếu key hoặc đang giả lập thì dừng, không âm thầm rơi về Qwen
        if settings.jev_simulated:
            sys.exit("SHADOW_BACKEND thật nhưng JEV_SIMULATED=1")
        key = settings.typesafe_api_key if BACKEND == "jev" else settings.deepseek_api_key
        if not key:
            sys.exit(f"thiếu key cho {BACKEND} (gắn Kaggle Secret {'TYPESAFE_API_KEY' if BACKEND == 'jev' else 'DEEPSEEK_API_KEY'})")
    gold = json.load(open(gold_path, encoding="utf-8"))["items"]
    sheet = {r["turn_id"]: r for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"))}
    rules = {r["turn_id"]: rules_view(r) for r in map(json.loads, open(rules_path, encoding="utf-8"))}
    preds, errors = {}, []
    for gi in gold:
        s = sheet[gi["turn_id"]]
        try:
            preds[gi["turn_id"]] = understand(s.get("agent_truoc", ""), s["khach_noi"])
        except Exception as e:  # ghi lỗi, không đoán
            errors.append({"turn_id": gi["turn_id"], "error": f"{type(e).__name__}: {str(e)[:120]}"})
    shadow, d_shadow = score(gold, preds)
    ref, d_ref = score(gold, rules, fields=("requests", "safety"))
    model = {"jev": settings.jev_model, "deepseek": settings.deepseek_model}.get(BACKEND, settings.qwen_model)
    report = {"spec": "v1 (đóng băng trong scripts/shadow_d68.py trước lượt chạy)", "backend": BACKEND, "model": model,
              "api_requests": CALLS["requests"], "n_gold": len(gold), "n_pred": len(preds),
              "errors": errors, f"shadow_{BACKEND}": shadow, "rules_reference": ref,
              "note": ("Qwen giả lập vai bộ hiểu (không phải Jev thật). " if BACKEND == "qwen" else f"{BACKEND} API thật. ")
              + "Dev đã quan sát, không phải holdout độc lập. Chỉ đọc, không điều khiển runtime."
              + (" Jev chỉ cho có/không theo slot, nên observations chấm theo khóa slot, giống spec v1." if BACKEND == "jev" else "")}
    json.dump(report, open(os.path.join(out, "shadow_d68_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"pred": preds, "shadow_details": d_shadow, "rules_details": d_ref}, open(os.path.join(out, "shadow_d68_details.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
