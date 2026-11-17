"""MỘT pipeline audit câu agent cuối thực sự gửi (cấu hình đích ARCH=target, K11/K12/K14).

Hai nhánh, hai NHIỆM VỤ khác nhau, chạy song song trên cùng câu cuối, không nhánh nào phân xử lại output của nhánh kia:
- questions — Jev (TypeSafe `system_one`, mỗi câu một lời gọi): có hỏi / yêu cầu khách không, slot/topic, loại open/confirm/none.
  JEV_SIMULATED=1: provider mô phỏng CÙNG giao diện (Qwen, `qwen_simulated_jev`) — ghi rõ trong trace, không gọi là Jev thật.
- claims — Qwen: trích claim của câu cuối (giá bán / niêm yết / giá đã báo, KM, tồn kho, ngày giao, đổi trả, bảo hành, người thật),
  mỗi claim có span NGUYÊN VĂN, stance và target (mã ứng viên P#). Parser code chỉ cấp ứng viên số tiền / số ngày làm gợi ý và
  đo recall ứng viên; code kiểm span, chuẩn hóa giá trị, map target. Không có CERT, không Jev label claim → Qwen → rules,
  không regex đổi open thành confirm, không bộ lọc keyword "không/chưa" loại claim (stance do model trả, code chỉ dùng nó).
- Lỗi: thử lại một lần; hết thì nhánh đó `unavailable` — không trả rỗng như "không có câu hỏi / claim", không quay về rules.
  Trace `audit.status` = ok | partial | unavailable để tách lượt thiếu dữ liệu khỏi phép đo hoàn chỉnh.
Audit không ghi phát ngôn agent thành fact shop, không đổi state, không gọi tool.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

from core.config import settings
from core.pii import Redactor
from harness.textnorm import find_money, fold

STANCES = ["asserted", "negated", "question", "conditional", "reported"]
CLAIM_FIELDS = {
    "price_vnd": "giá bán HIỆN TẠI agent khẳng định cho MỘT SẢN PHẨM (giá khách sẽ trả cho món đó, 'còn 2.990.000đ'). Số tiền "
                 "KHÔNG phải giá của một sản phẩm thì KHÔNG ghi bất kỳ field giá nào: phí (phí đổi, phí giao, phí lắp…), tiền giảm, "
                 "tiền hoàn / tiền chênh lệch khi đổi trả, tổng tiền giỏ/đơn, NGƯỠNG điều kiện khuyến mãi / freeship "
                 "('đơn từ 500k'), ngân sách hay giá khách nêu",
    "list_price_vnd": "giá niêm yết / giá gốc trước khuyến mãi CỦA MỘT SẢN PHẨM",
    "price_quoted_vnd": "giá bán CỦA MỘT SẢN PHẨM mà agent nhắc lại là đã báo trước đây ('hôm trước em báo anh …'). KHÔNG dùng cho "
                        "tiền hoàn, phí, tổng đơn hay số tiền khác",
    "promo_active": "khẳng định ĐANG có (true) / KHÔNG có hoặc đã hết (false) khuyến mãi / quà tặng cho sản phẩm (freeship không tính)",
    "in_stock": "khẳng định còn hàng (true) / hết hàng (false)",
    "delivery_days": "số ngày giao hàng",
    "return_days": "hạn đổi trả tính bằng ngày",
    "warranty_months": "thời gian bảo hành chính hãng của sản phẩm (tháng; năm × 12)",
    "is_human": "CHỈ khi câu nói về DANH TÍNH của chính agent: tự nhận là người thật / nhân viên thật (true) hoặc là trợ lý AI / "
                "bot (false). Câu từ chối, câu xưng 'em' thông thường, câu về sản phẩm / giá / chuyển máy KHÔNG phải is_human",
}
POLARITY = ("promo_active", "in_stock", "is_human")
# Holdout mục 7 (duyệt 12/11): ví dụ phân biệt field theo NGHĨA (audit đúng nghĩa, không để làm đẹp số). Probe:
# scripts/audit_claims_probe.py so prompt cũ (định nghĩa cũ + chuỗi rỗng) với prompt mới trên câu MỚI (không lấy từ holdout).
CLAIM_EXAMPLES_V2 = ("Ngưỡng điều kiện KM ('freeship cho đơn từ 300.000đ') và tiền hoàn / chênh lệch khi đổi ('hoàn lại 450.000đ "
                     "tiền chênh') KHÔNG phải price_vnd. Câu từ chối ('em không giảm thêm được ạ', 'em không bình luận hàng bên "
                     "khác ạ') KHÔNG có is_human; chỉ câu như 'em là trợ lý AI của shop' mới có is_human (false).\n")
# Vòng sửa thứ hai (duyệt 12/11): probe v2 còn gắn 'phí đổi' thành price_vnd và tiền hoàn thành price_quoted_vnd. Ví dụ dưới đây
# KHÁC mọi câu trong bộ kiểm cũ và bộ kiểm mới của scripts/audit_claims_probe.py.
CLAIM_EXAMPLES_V3 = ("Phí và tiền hoàn KHÔNG phải claim giá: 'phí vận chuyển 25.000đ', 'phí bảo dưỡng 80.000đ', 'chị nhận lại "
                     "700.000đ' → không có price_vnd / list_price_vnd / price_quoted_vnd.\n")
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="audit")


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


# ------------------------------------------------------------------------------------------------ questions (Jev)

def _jev_sentence(sentence, known_values):
    """Một câu → (item | None). Ném lỗi khi Jev lỗi / nhãn không hợp lệ (caller thử lại / đánh dấu unavailable)."""
    from harness.question_classifiers.jev_slots import SLOT_CRITERIA, SLOT_INSTRUCTIONS, TYPE_CRITERIA, TYPE_INSTRUCTIONS
    safe = Redactor().redact({"agent_sentence": sentence, "known_values": known_values})
    if settings.jev_simulated:
        from harness.jev_adapter import infer
        schema = {"type": "object", "required": ["slot", "type"], "additionalProperties": False,
                  "properties": {"slot": {"type": "string", "enum": list(SLOT_CRITERIA)}, "type": {"type": "string", "enum": list(TYPE_CRITERIA)}}}
        res = infer(f"{SLOT_INSTRUCTIONS}\n{TYPE_INSTRUCTIONS}\nSlots: {SLOT_CRITERIA}\nTypes: {TYPE_CRITERIA}\nData: {safe}\nReturn JSON slot,type.", schema)
        slot, kind = res.get("slot"), res.get("type")
    else:
        from typesafe_sdk import Choice
        from harness.question_classifiers.jev_slots import _client
        res = _client().system_one(state={"role": "nhân viên chăm sóc khách hàng", **safe},
                                   questions={"slot": Choice(instructions=SLOT_INSTRUCTIONS, criteria=SLOT_CRITERIA),
                                              "type": Choice(instructions=TYPE_INSTRUCTIONS, criteria=TYPE_CRITERIA)},
                                   model=settings.jev_model)
        slot, kind = res.choices["slot"].choice, res.choices["type"].choice
    if slot not in SLOT_CRITERIA or kind not in TYPE_CRITERIA:
        raise ValueError("invalid_choice")
    if (slot == "none") != (kind == "none"):
        raise ValueError("slot_type_mismatch")
    return None if slot == "none" else {"slot": slot, "type": kind, "text": sentence}


def questions(text, known_values):
    """→ (questions, meta). Mỗi câu thử tối đa 2 lần; câu lỗi → không đoán, ghi vào unavailable."""
    sents = sentences(text)
    meta = {"backend": "qwen_simulated_jev" if settings.jev_simulated else f"jev:{settings.jev_model}",
            "calls": 0, "errors": [], "unavailable_sentences": []}
    t0 = time.perf_counter()

    def one(i_s):
        i, s = i_s
        calls, err = 0, None
        for _ in (1, 2):
            calls += 1
            try:
                return i, _jev_sentence(s, known_values), calls, None
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}:{str(e)[:40]}"
        return i, None, calls, err

    out = {}
    for i, item, calls, err in _POOL.map(one, list(enumerate(sents))):
        meta["calls"] += calls
        if err:
            meta["errors"].append(err); meta["unavailable_sentences"].append(i)
        elif item:
            out[i] = item
    meta["ms"] = int((time.perf_counter() - t0) * 1000)
    meta["status"] = "ok" if not meta["unavailable_sentences"] else ("unavailable" if len(meta["unavailable_sentences"]) == len(sents) else "partial")
    return [out[i] for i in sorted(out)], meta


# ------------------------------------------------------------------------------------------------ claims (Qwen)

def _candidates(sents):
    """Parser code: ứng viên số tiền / số ngày / tháng theo câu — chỉ để gợi ý cho model và đo recall ứng viên."""
    out = []
    for i, s in enumerate(sents):
        for st, en, v in find_money(s):
            out.append({"i": i, "kind": "money", "span": s[st:en], "value": v})
        for m in re.finditer(r"\d{1,3}\s*(?:-|–|đến|tới)?\s*\d{0,3}\s*(ngày|tháng|năm)", s):
            out.append({"i": i, "kind": "duration", "span": m.group(0)})
    return out


def _claim_value(field, span, value):
    from harness.llm_extract import MONEY_FIELDS, _claim_value as cv
    if field in POLARITY:
        return value if isinstance(value, bool) else None
    return cv(field, span, None)


def claims(text, candidates):
    """→ (claims, meta). Qwen trả claim cho MỌI câu (không bỏ câu không có cue); code kiểm span / giá trị / target."""
    from core.llm.deepseek import LLM
    sents = sentences(text)
    meta = {"backend": f"qwen:{settings.qwen_model}" if settings.extractor_llm == "qwen" else settings.extractor_llm,
            "calls": 0, "dropped": [], "status": "ok", "non_asserted": []}
    if not sents:
        return [], meta
    cand = _candidates(sents)
    refs = {c["ref"]: c for c in candidates}
    schema = {"type": "object", "required": ["claims"], "additionalProperties": False, "properties": {"claims": {
        "type": "array", "items": {"type": "object", "required": ["i", "field", "span", "stance"], "additionalProperties": False,
                                   "properties": {"i": {"type": "integer", "enum": list(range(len(sents)))},
                                                  "field": {"type": "string", "enum": list(CLAIM_FIELDS)},
                                                  "span": {"type": "string"},
                                                  "value": {"type": ["boolean", "null"]},
                                                  "stance": {"type": "string", "enum": STANCES},
                                                  "target_ref": {"type": ["string", "null"], "enum": list(refs) + [None]}}}}}}
    prompt = ("Trích CLAIM (khẳng định có thể kiểm chứng) trong lời NHÂN VIÊN bán hàng dưới đây. Xét MỌI câu.\n"
              "Mỗi claim: i = số thứ tự câu; field; span = đoạn NGUYÊN VĂN trong câu chứa giá trị (số tiền / số ngày / cụm khẳng định — BẮT BUỘC với mọi field, kể cả true/false); "
              "value = true/false CHỈ cho promo_active, in_stock, is_human (field khác để null); stance: asserted = nhân viên khẳng "
              "định; negated = câu phủ định / bác bỏ giá trị đó ('không phải 1.161.000đ'); question = nằm trong câu hỏi; "
              "conditional = chỉ đúng nếu điều kiện; reported = thuật lại lời khách / bên khác; target_ref = mã sản phẩm trong "
              "ỨNG VIÊN mà claim nói về (câu nhắc nhiều sản phẩm: gắn từng giá đúng sản phẩm của nó); không rõ thì null.\n"
              "Field:\n" + "\n".join(f"- {k}: {v}" for k, v in CLAIM_FIELDS.items()) + "\n"
              "Ví dụ: 'Giá gốc 2.190.000đ, giờ còn 1.990.000đ ạ.' → list_price_vnd span '2.190.000đ', price_vnd span '1.990.000đ'. "
              "'Tổng đơn 3.980.000đ' không phải price_vnd. 'Hoàn tiền trong 3–5 ngày' không phải delivery_days.\n"
              + CLAIM_EXAMPLES_V2 + CLAIM_EXAMPLES_V3 +
              f"ỨNG VIÊN: {[{'ref': c['ref'], 'name': c['name']} for c in candidates]}\n"
              f"Số trong câu (parser, chỉ gợi ý): {[{'i': c['i'], 'span': c['span']} for c in cand]}\n"
              "Lời nhân viên:\n" + "\n".join(f"[{i}] {s}" for i, s in enumerate(sents)) + "\nTrả JSON {\"claims\": [...]}; không có claim thì [].")
    t0 = time.perf_counter()
    d, err = None, None
    for _ in (1, 2):
        meta["calls"] += 1
        try:
            d = LLM(settings.extractor_llm if settings.extractor_llm in ("qwen", "deepseek") else "qwen", role="extract").json(
                prompt, schema=schema, max_tokens=600, cache=False, timeout=settings.extractor_timeout_s,
                system="Bạn là bộ trích claim cho cuộc gọi bán hàng tiếng Việt. Chỉ trả JSON hợp lệ.")
            if not isinstance(d, dict):
                raise ValueError("not_object")
            break
        except Exception as e:  # noqa: BLE001
            d, err = None, f"{type(e).__name__}:{str(e)[:60]}"
    meta["ms"] = int((time.perf_counter() - t0) * 1000)
    meta["candidates"] = len(cand)
    if d is None:
        meta.update(status="unavailable", error=err)
        return [], meta
    out, seen = [], set()
    for it in d.get("claims") or []:
        i, field = it.get("i"), it.get("field")
        if not isinstance(i, int) or not 0 <= i < len(sents) or field not in CLAIM_FIELDS:
            meta["dropped"].append({"why": "invalid"}); continue
        s, span = sents[i], str(it.get("span") or "")
        if not span or fold(span) not in fold(s):          # mọi claim (cả true/false) phải có căn cứ nguyên văn trong câu
            meta["dropped"].append({"i": i, "field": field, "why": "span_not_in_sentence"}); continue
        v = _claim_value(field, span or s, it.get("value"))
        if v is None:
            meta["dropped"].append({"i": i, "field": field, "why": "no_value"}); continue
        ref = it.get("target_ref")
        sku = refs[ref]["sku"] if ref in refs else None
        stance = it.get("stance") if it.get("stance") in STANCES else "asserted"
        rec = {"field": field, "value": v, "text": s, **({"sku": sku} if sku else {}), "stance": stance}
        key = (field, str(v), s, sku)
        if key in seen:
            continue
        seen.add(key)
        if stance == "asserted":
            out.append(rec)
        else:
            meta["non_asserted"].append({k: rec[k] for k in ("field", "value", "stance")})
    money_cand = {(c["i"], c["value"]) for c in cand if c["kind"] == "money"}
    money_claimed = {(sents.index(c["text"]), c["value"]) for c in out + [] if c["field"] in ("price_vnd", "list_price_vnd", "price_quoted_vnd")}
    meta["money_candidates"] = len(money_cand)
    meta["money_candidates_claimed"] = len(money_cand & money_claimed)
    return out, meta


# ------------------------------------------------------------------------------------------------ pipeline

def run(text, known_values, meta, candidates):
    """→ (questions, claims). meta["audit"] = {status, backend, question{...}, claim{...}}. Hai nhánh song song."""
    t0 = time.perf_counter()
    fq = _POOL.submit(questions, text, known_values)
    fc = _POOL.submit(claims, text, candidates)
    qs, qmeta = fq.result()
    cs, cmeta = fc.result()
    st = {qmeta["status"], cmeta["status"]}
    status = "ok" if st == {"ok"} else "unavailable" if st == {"unavailable"} else "partial"
    meta["audit"] = {"status": status, "pipeline": "target_v1",
                     "backend": f"questions={qmeta['backend']};claims={cmeta['backend']}",
                     "question": qmeta, "claim": cmeta, "ms": int((time.perf_counter() - t0) * 1000),
                     "cert": None, "cascade": None}
    meta["backend"] = meta["audit"]["backend"]
    meta["ms"] = meta["audit"]["ms"]
    if status != "ok":
        meta["fallback"] = None          # không có đường dự phòng: lượt thiếu audit được báo riêng qua audit.status
    return qs, cs
