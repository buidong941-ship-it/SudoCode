"""State yêu cầu / pending của cuộc gọi — MỘT chủ sở hữu bằng code (cấu hình đích ARCH=target, K01/K06/K07).

Thay ba nguồn cấp phép tự trị của TG/R0 (`open_requests` cộng dồn tên hành động, `buy_intent`, nhãn pending rời rạc) bằng
bản ghi yêu cầu có: kind, target, revision (biến thể / số lượng / giá đã chấp nhận), evidence + lượt nguồn, điều kiện, status.

Vòng đời:  open | conditional | needs_target  →  in_flight  →  done | partial | failed | unresolved
           (còn hiệu lực)  →  withdrawn (khách rút / từ chối / hoãn)  |  superseded (yêu cầu mới cùng loại)
- Yêu cầu CHỈ đến từ bộ hiểu (DeepSeek, đã kiểm căn cứ trong câu khách hiện tại) hoặc từ đồng ý (`response_to_agent=accept`, có
  căn cứ trong câu hiện tại) đối với ĐỀ NGHỊ nhân viên vừa nêu ở lượt trước (bảng PROPOSALS).
- Target: model chọn mã ứng viên sai → `needs_target` (không ghi, hỏi lại), KHÔNG hạ thành "chưa có target" rồi để code gắn.
  Yêu cầu chưa có target chỉ được gắn khi đối tượng KHÔNG mơ hồ: đặt hàng → lựa chọn hiện tại ngay trong lượt khách nói
  (hoặc cuối lượt đó); thao tác trên đơn → chỉ khi executor báo đúng một đơn ứng viên (`unique_target`).
- Revision: khi gắn target, ghi biến thể chính xác, số lượng (nếu khách nói) và giá đã báo theo từng sản phẩm. Lúc thực thi
  khác biến thể / số lượng / giá → `revision_changed`: không dùng đồng ý cũ, executor xin xác nhận lại.
- Điều kiện: căn cứ sai / không tách được → `unknown` (chưa xác định, không ghi). stock chỉ qua khi executor xác nhận còn hàng
  bằng tool trong lượt (`in_stock=True`); price_max so tổng hiện tại; approval / time / other / unknown → chờ, không ghi.
- Trạng thái sau tool theo `tool_outcome.classify` (K06): thành công xác nhận → done; lỗi chắc chắn → failed (không tự thử lại);
  không rõ (timeout / transport) → unresolved (không tạo lại, chờ nhân viên đối soát). Không tiêu thụ yêu cầu trước khi có kết quả.

Hoàn thiện 11/11 (PHAN-BIEN-VA-BAN-GIAO-HOAN-THIEN-PLANNER-TARGET, mục 4 + 9.1 + 9.2):
- Ứng viên cho bộ hiểu ưu tiên sản phẩm parser catalog thấy trong CÂU HIỆN TẠI; vượt giới hạn thì ghi `truncated` vào trace.
- Ref sản phẩm lưu ở mức sản phẩm cha (biến thể chốt lúc thực thi theo size/màu khách nói); đề nghị nhân viên giữ biến thể đã nói.
- Yêu cầu mới cùng loại: cùng đối tượng / bao trùm / một bên chưa có đối tượng → thay (cùng yêu cầu, đồng ý cũ không mang sang
  payload mới). Khác đối tượng: cùng lượt → giữ CẢ HAI ở trạng thái hiệu lực, executor hỏi trước khi ghi (không gộp union, không
  lấy yêu cầu cuối làm mất yêu cầu trước); khác lượt và khách không rút → yêu cầu cũ `parked`: không tự thực thi, không coi là
  khách đã rút, agent hỏi rõ (quyết định của Codex ở mục 9.1 — KHÔNG ghi là Claude đồng ý).
- Executor chọn đúng một yêu cầu (`select`) rồi xin quyền GHI bằng chính request ID đó (`authorize(req_id=...)`).
- Revision có thêm thanh toán / địa chỉ kèm NGUỒN; đổi giá trị mà không phải do khách nói từ lượt mở yêu cầu → revision_changed.
"""
import re

from core.config import settings
from harness.textnorm import fold
from harness.tools import mt, product_name

# ---------------------------------------------------------------------- F8 (duyệt 13/11, chỉ B2): cổng mở yêu cầu đặt hàng
# Chỉ áp cho place_order DO KHÁCH NÓI (không áp cho đồng ý đề nghị của nhân viên — đường accept). Không mở yêu cầu khi:
#  (1) lượt tự xưng hệ thống ("[Hệ thống]: …", "[SYSTEM] …"): lời khách, không phải lệnh hệ thống → không là xác nhận đặt;
#  (2) khách nêu số tiền không khớp giá tool nào đã đọc trong cuộc → khách chưa xác nhận giá thật (báo giá thật + xin xác nhận);
#  (3) không có lệnh đặt rõ (chỉ ý định / quyết định: "muốn mua", "định lấy", "quyết lấy rồi") → hỏi xác nhận (confirm_order).
# Lệnh đặt rõ có thể chưa kèm địa chỉ: vẫn tạo đơn rồi hỏi địa chỉ như cũ (D1 người dùng chốt 13/11).
ORDER_CMD_RX = re.compile(
    r"\b(len (lai )?don|len luon|chot|dat (hang|don|mua|luon|lien|ngay|cho|giup|nhe|nha|di|ho|1|mot|hai|2)"
    r"|dat\s+(\w+\s+){0,6}cho (anh|chi|em|minh|co|chu|bac|toi)"
    r"|lay (cho|giup|ho|luon|ngay|lien|1|mot|hai|2|ba|3)\b|lay\b(\s+\S+){0,6}?\s+(di|nhe|nha|luon|ngay|lien)\b"
    r"|lay\b(\s+\S+){0,6}?\s+cho (anh|chi|em|minh|co|chu|bac|toi)\b|lay (cai|chiec|mau|con|bo|loai) (do|nay|ay|kia)\b"
    r"|gui (cho|ve|hang)|giao (cho|ve|toi|den|vao|dung|tai|\d+)|mua luon|lam don|tao don|xuat don)\b")
PSEUDO_SYSTEM_RX = re.compile(r"^\s*[\[\(<]\s*(he thong|system|admin|quan tri|operator)\b")


def stated_vnd(f):
    """Số tiền khách tự nêu trong câu đã fold (bỏ dấu, chữ thường): "3 triệu 9", "6 triệu 790", "5 triệu rưỡi", "990.000đ",
    "1290k", "990 nghìn". Chỉ nhận số có đơn vị tiền hoặc có dấu phân cách hàng nghìn (không bắt SĐT, số nhà, size)."""
    out = []
    for m in re.finditer(r"(\d+)\s*(?:trieu|tr)\b\s*(ruoi|\d{1,3}(?![\d.,]))?", f):
        v = int(m.group(1)) * 1_000_000
        t = m.group(2)
        if t == "ruoi":
            v += 500_000
        elif t:
            v += int(t) * 10 ** (6 - len(t))
        out.append(v)
    for m in re.finditer(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+)(?![\d.,])", f):
        v = int(re.sub(r"[.,]", "", m.group(1)))
        if v >= 10_000:
            out.append(v)
    for m in re.finditer(r"(?<![\d.,])(\d+)\s*(?:k|nghin|ngan)\b", f):
        out.append(int(m.group(1)) * 1000)
    return out


def seen_prices(s):
    """Mọi mức giá tool đã trả trong cuộc (get_quote niêm yết / sau KM, quote_order tổng / từng đơn vị) + giá đã báo lưu trong
    bộ nhớ của khách (Full)."""
    log = list(getattr(s, "call_tool_log", []) or []) + list(getattr(getattr(s, "tools", None), "log", []) or [])
    out = set()
    for tc in log:
        r = tc.get("result")
        if not isinstance(r, dict):
            continue
        if tc.get("name") == "pricing.get_quote":
            out.update(x for x in (r.get("final_price_vnd"), r.get("list_price_vnd")) if x)
        elif tc.get("name") == "pricing.quote_order":
            out.update(x for x in [r.get("total_vnd")] + [u.get("final_price_vnd") for u in r.get("units") or []] if x)
    pq = (getattr(s, "known", {}) or {}).get("price_quoted_vnd")
    if pq:
        out.add(pq)
    return out


def order_gate(s, text):
    """→ (lý do chặn | None, số tiền không khớp). Thứ tự: tự xưng hệ thống → giá chưa khớp → không có lệnh đặt rõ."""
    f = fold(text or "")
    if PSEUDO_SYSTEM_RX.search(f):
        return "pseudo_system", []
    amounts = [v for v in stated_vnd(f) if v >= 100_000]
    if amounts:
        known = seen_prices(s)
        bad = [v for v in amounts if v not in known]
        if bad:
            return "price_unconfirmed", bad
    if not ORDER_CMD_RX.search(f):
        return "intent_only", []
    return None, []


# ---------------------------------------------------------------------- V41-1 (15/11, chỉ B2): kiểm CỨNG quyền tạo đơn
# Áp chung cho mọi đường tạo đơn (yêu cầu trực tiếp, C3 gắn đề nghị, đồng ý đề nghị). Nguồn cấp quyền KHÔNG đổi: chỉ là cấu trúc
# bộ hiểu đã kiểm (yêu cầu place_order / act=accept, evidence nguyên văn trong câu). Mọi kiểm dưới đây CHỈ CHẶN; không kiểm nào —
# kể cả tìm thấy từ khóa — là bằng chứng mua. Regex là kiểm phụ (giới hạn: plan §8.20 / §8.21).
ORDER_VERB_RX = re.compile(r"\b(len (lai )?don|chot|dat|lay|mua)\b")
# K6: hoãn (danh sách cố định §8.20; không mở rộng để đuổi từng câu)
DEFER_RX = re.compile(r"\b(de (chi|anh|em|minh|toi) (nghi|xem|tinh|can nhac|ban|hoi)|nghi them|xem them|can nhac|tinh sau|de sau"
                      r"|de mai|hom khac|lan sau|chua (voi|quyet|chot)|khoan)\b")
_LEAD_IN_RX = re.compile(r"(giao|gui|ship|chuyen)( hang)? (ve|toi|den|cho|ra|vao|vo)\s*$")
_DELIVERY_CMD_RX = re.compile(r"^(giao|gui)\b")
REFUSAL = ("negated", "deferred", "withdrawn")
# V43 (15/11, duyệt): chuẩn cấp quyền nhất quán accept / place_order / condition. Các tập dưới đây CHỈ dùng để chặn hoặc giới hạn
# miền hỗ trợ; không cái nào một mình cấp quyền (quyền vẫn cần cấu trúc của bộ hiểu + đề nghị mới / lệnh tại mệnh đề).
# Động từ thuật lời đứng TRƯỚC lệnh mua trong cùng mệnh đề ("… bảo chốt đơn …") → lời kể.
REPORT_VERB_RX = re.compile(r"\b(noi|bao(?! hanh| gia| nhieu| lau)|hua|ke|dan|cho biet|keu|nhac)\b")
# Chỉ ý định đứng trước động từ mua ("mới tính mua", "muốn lấy") — dùng cho yêu cầu có điều kiện không có lệnh F8
INTENT_MODAL_RX = re.compile(r"\b(muon|dinh|tinh|chac|co le|se|can nhac)\b")
# Marker xác nhận thuần cho đường accept (đi cùng: mọi từ còn lại là từ đệm / xưng hô của stance._ACK_TOK). "Dạ" không là marker.
ACCEPT_MARK = frozenset("ok oke okay okie u uh uhm um uk vang duoc".split())


_SELF_PRON = frozenset("chi anh em minh toi con co chu bac".split())
_SELF_VERB = frozenset("lay dat mua".split())
_SELF_POST = frozenset("luon nhe nha a di em anh chi oi".split())


def self_command(clause_fold):
    """V44 (GEN-T27): TỰ-LỆNH toàn mệnh đề = [từ đệm / đồng ý ngắn]* + đại từ người nói + lấy | đặt | mua + [luôn / nhé / nha / ạ / đi
    / xưng hô]*, KHÔNG có từ nào khác ("Ừ chị lấy", "Ok anh lấy nhé"). "rồi" không được (chị lấy rồi = đã lấy); không modal / thuật
    lời / phủ định / hỏi vì mọi từ ngoài khuôn đều làm hỏng khớp. Chỉ dùng ở đường yêu cầu place_order (không mở rộng accept_pure)."""
    from harness.stance import _ACK_TOK
    toks = re.findall(r"[a-z0-9]+", clause_fold)
    pre_ok = _ACK_TOK - {"roi"}
    for k in range(len(toks) - 1):
        if toks[k] in _SELF_PRON and toks[k + 1] in _SELF_VERB:
            return all(x in pre_ok for x in toks[:k]) and all(x in _SELF_POST for x in toks[k + 2:])
    return False


# V44 (15/11): động từ của TỪNG thao tác đơn (trên chữ có dấu, chữ thường) — không dùng chung cổng mua hàng (giá / marker mua khác).
# Thiếu dấu → không khớp → hỏi lại (thu hẹp an toàn).
OP_VERB_RX = {
    "exchange": re.compile(r"(?<!\w)đổi(?!\w)(?! (lại )?địa chỉ)(?! sang địa chỉ)"),
    "return": re.compile(r"(?<!\w)(trả lại|trả hàng|trả máy|trả về|hoàn tiền|hoàn hàng|hoàn trả)(?!\w)"
                         r"|(?<!\w)trả(?!\w)(?! tiền)(?! góp)(?! lời)"),
    "change_order_address": re.compile(r"(?<!\w)(đổi|sửa|chuyển|cập nhật|thay)( lại)? địa chỉ|địa chỉ mới|chuyển nhà"
                                       r"|(?<!\w)giao (về|sang|tới|đến|qua)(?!\w)"),
}
_OP_FILLER = frozenset("giup cho voi ho di nhe".split())


def op_authority(s, u, text, ev, kind, *, accept, conditional):
    """V44: kiểm CỨNG quyền mở yêu cầu thao tác đơn (đổi / trả / đổi địa chỉ) — chỉ CHẶN, không cấp quyền; quyền vẫn đến từ yêu cầu /
    đồng ý của bộ hiểu. → why | None. Không có kiểm giá / phí (khác mua hàng; điều khoản kiểm ở _order_op_check / tool)."""
    from harness.stance import NEGATED, CONDITIONAL, AFFIRMED, QUESTION, _ACK_TOK, canon, pfold, stance_at, clauses
    if PSEUDO_SYSTEM_RX.search(fold(text or "")):
        return "pseudo_system"
    t = canon(text or "")
    low, f = t.lower(), pfold(t)
    fe = pfold(canon(ev or ""))
    i = f.find(fe) if fe else -1
    if i < 0:
        return "evidence_not_found"
    j = i + len(fe)
    rx = OP_VERB_RX[kind]
    spans, _unknown = delivery_spans(text, u)
    cls = clauses(t)
    if accept:
        if any(w.get("kind") == kind for w in (u or {}).get("withdrawn") or []):
            return "withdrawn"
        fm, has_verb = _mask(f, spans), False
        for m in rx.finditer(low):
            has_verb = True
            st = stance_at(text, m.start())
            if st == NEGATED:
                return "negated"
            fm = fm[:m.start()] + " " * (m.end() - m.start()) + fm[m.end():]
        for cs, ce, _q in cls:
            if DEFER_RX.search(fm[cs:ce]):
                return "deferred"
        toks = re.findall(r"[a-z0-9]+", fm)
        if any(x not in _ACK_TOK and x not in _OP_FILLER for x in toks):
            return "accept_not_pure"
        if not (has_verb or any(x in ACCEPT_MARK for x in toks) or re.search(r"\b(dong y|dung roi)\b", " ".join(toks))):
            return "accept_not_pure"            # "Dạ." / xưng hô không là đồng ý
        return None
    fmask = _mask(f, spans)
    found = False
    for cs, ce, _q in cls:
        if not (cs < j and i < ce):
            continue
        for m in rx.finditer(low[cs:ce]):
            p = cs + m.start()
            st = stance_at(text, p)
            if st == NEGATED:
                return "negated"
            if conditional and st in (QUESTION, CONDITIONAL):
                st = AFFIRMED
            if st != AFFIRMED:
                return f"stance_{st}"
            if REPORT_VERB_RX.search(f[cs:p]):
                return "stance_reported"
            if not conditional and DEFER_RX.search(fmask[cs:ce]):
                return "deferred"
            found = True
    return None if found else "op_no_command"


def op_refused(text, kind):
    """V44: câu hiện tại phủ định / hoãn đúng thao tác `kind` (vd "Thôi anh chưa đổi đâu") → yêu cầu đang chờ cùng loại không được
    dùng lại ở lượt sau."""
    from harness.stance import NEGATED, canon, pfold, stance_at, clauses
    t = canon(text or "")
    low, f = t.lower(), pfold(t)
    for m in OP_VERB_RX[kind].finditer(low):
        if stance_at(text, m.start()) == NEGATED:
            return True
        for cs, ce, _q in clauses(t):
            if cs <= m.start() < ce and DEFER_RX.search(f[cs:ce]):
                return True
    return False


def accept_pure(f, spans):
    """V43: câu đồng ý THUẦN = sau khi che phần thanh toán / địa chỉ và lệnh mua (ORDER_CMD_RX), mọi từ còn lại thuộc stance._ACK_TOK
    (từ đệm / xưng hô / từ đồng ý ngắn) VÀ có marker (ACCEPT_MARK, "đồng ý", "đúng rồi" hoặc một lệnh mua). Giới hạn: câu đồng ý dài
    / đảo trật tự / có nội dung khác → không thuần → hỏi lại (thu hẹp có chủ đích)."""
    from harness.stance import _ACK_TOK
    fm = _mask(f, spans)
    cmd = False
    for mc in ORDER_CMD_RX.finditer(fm):
        cmd = True
        fm = fm[:mc.start()] + " " * (mc.end() - mc.start()) + fm[mc.end():]
    toks = re.findall(r"[a-z0-9]+", fm)
    if not toks and not cmd:
        return False
    if not all(x in _ACK_TOK for x in toks):
        return False
    s = " ".join(toks)
    return cmd or any(x in ACCEPT_MARK for x in toks) or bool(re.search(r"\b(dong y|dung roi)\b", s))        # chặn kiểu từ chối / hoãn / rút → HỦY đề nghị (không giữ để vô tình chấp nhận)


def _names_cart(text):
    """V42: khách nói rõ GIỎ hàng ("cả giỏ", "giỏ hàng") — cần dấu: "giỏ" (bỏ dấu "gio" trùng "giờ"). Chỉ dùng để giữ ref CART là
    đối tượng có bằng chứng, không phải bằng chứng mua. Giới hạn: viết không dấu "gio hang" → không nhận → hỏi rõ (an toàn)."""
    import unicodedata
    return bool(re.search(r"(?<!\w)giỏ(?!\w)", unicodedata.normalize("NFC", text or "").lower()))


def _find_all(f, needle):
    out, i = [], f.find(needle) if needle else -1
    while i >= 0:
        out.append((i, i + len(needle)))
        i = f.find(needle, i + 1)
    return out


def delivery_spans(text, u):
    """→ (spans trên pfold(canon(text)), unknown). spans = span quan sát thanh toán / địa chỉ của model ∪ bộ dò luật CÓ SẴN
    (stance.PAY_RX, extractor.ADDRESS_RX), mỗi span địa chỉ kèm cụm dẫn "giao / gửi … về|tới|cho" đứng ngay trước.
    unknown = model nêu quan sát thanh toán / địa chỉ nhưng span bị loại (không định vị được) → người gọi xử lý fail-closed."""
    from harness.stance import PAY_RX, canon, pfold
    from harness.extractor import ADDRESS_RX
    t = canon(text)
    f = pfold(t)
    spans = []
    for o in (u or {}).get("observations") or []:
        if o.get("slot") in ("payment", "address") and o.get("span"):
            spans += [(a, b, o["slot"]) for a, b in _find_all(f, pfold(o["span"]))]
    spans += [(m.start(), m.end(), "payment") for m in PAY_RX.finditer(f)]
    spans += [(m.start(), m.end(), "address") for m in ADDRESS_RX.finditer(t)]
    out = []
    for a, b, slot in spans:
        if slot == "address":
            m = _LEAD_IN_RX.search(f[:a])
            a = m.start() if m else a
        out.append((a, b))
    unknown = any(d.get("slot") in ("payment", "address") for d in ((u or {}).get("meta") or {}).get("dropped") or [])
    return out, unknown


def _mask(f, spans):
    chars = list(f)
    for a, b in spans:
        for i in range(max(0, a), min(len(chars), b)):
            chars[i] = " "
    return "".join(chars)


def order_cmd_outside(f, spans, unknown):
    """Lệnh đặt rõ (ORDER_CMD_RX của F8) nằm NGOÀI phần giao hàng. unknown: không định vị được phần giao hàng → không tính các
    lệnh dạng "giao / gửi …" (có thể chính là phần địa chỉ)."""
    for m in ORDER_CMD_RX.finditer(_mask(f, spans)):
        if unknown and _DELIVERY_CMD_RX.match(m.group(0)):
            continue
        return True
    return False


def order_authority(s, u, text, ev, *, accept, conditional):
    """→ (why | None, stated_vnd). why ∈ pseudo_system | price_unconfirmed | evidence_not_found | negated | deferred | withdrawn |
    stance_question / stance_reported / stance_unknown / stance_conditional | delivery_span_unknown | accept_has_digits |
    accept_delivery_only | intent_only. None = không có lý do chặn (KHÔNG có nghĩa là có bằng chứng mua — quyền vẫn đến từ
    yêu cầu / đồng ý của bộ hiểu)."""
    from harness.stance import NEGATED, CONDITIONAL, AFFIRMED, QUESTION, REPORTED, canon, pfold, stance_at, clauses
    f0 = fold(text or "")
    if PSEUDO_SYSTEM_RX.search(f0):                                         # K1
        return "pseudo_system", []
    amounts = [v for v in stated_vnd(f0) if v >= 100_000]                   # K2
    if amounts:
        bad = [v for v in amounts if v not in seen_prices(s)]
        if bad:
            return "price_unconfirmed", bad
    t = canon(text or "")
    f = pfold(t)
    fe = pfold(canon(ev or ""))
    i = f.find(fe) if fe else -1
    if i < 0:
        return "evidence_not_found", []                                     # fail-closed (bộ hiểu đã kiểm; phòng lệch chuẩn hóa)
    j = i + len(fe)
    m = ORDER_VERB_RX.search(f, i, j)
    st = stance_at(text, m.start() if m else i)                             # K3: lập trường tại ĐỘNG TỪ ĐẶT trong evidence
    if st == NEGATED:
        return "negated", []
    if conditional:
        st = AFFIRMED    # yêu cầu CÓ điều kiện: mệnh đề điều kiện ("khi nào có hàng thì…") làm stance ra question / conditional —
        #                  giữ đường điều kiện cũ, chỉ phủ định (đã xét ở trên) mới chặn
    if st != AFFIRMED:
        return f"stance_{st}", []
    spans, unknown = delivery_spans(text, u)
    if not conditional:                                                     # K6 (không áp yêu cầu có điều kiện)
        fm = _mask(f, spans)                    # xét hoãn NGOÀI phần thanh toán / địa chỉ ("chuyển khoản" ≠ "khoan")
        for cs, ce, _q in clauses(t):
            c = fm[cs:ce]
            if ((cs < j and i < ce) or ORDER_VERB_RX.search(c)) and DEFER_RX.search(c):
                return "deferred", []
    if accept and any(w.get("kind") == "place_order" for w in (u or {}).get("withdrawn") or []):
        return "withdrawn", []                                              # K4
    # K5: spans / unknown đã tính ở trên
    if accept:
        if unknown:
            return "delivery_span_unknown", []
        if re.search(r"\d", f[i:j]):
            return "accept_has_digits", []          # số trong evidence đồng ý (số nhà / SĐT / số lượng) → không phải xác nhận thuần
        if any(a < j and i < b for a, b in spans) and not order_cmd_outside(f, spans, unknown):
            return "accept_delivery_only", []
        if not accept_pure(f, spans):
            return "accept_not_pure", []            # V43: câu không phải xác nhận thuần có marker → nhãn accept không tự cấp quyền
        return None, []
    # V43: lệnh mua phải có căn cứ TẠI mệnh đề chứa evidence (không quét "chốt" bất kỳ trong câu); lập trường tại chính vị trí lệnh;
    # động từ thuật lời đứng trước lệnh trong cùng mệnh đề → lời kể, không phải khách tự yêu cầu
    fm = _mask(f, spans)
    ev_cls = [(cs, ce) for cs, ce, _q in clauses(t) if cs < j and i < ce]
    found = False
    for cs, ce in ev_cls:
        for mc in ORDER_CMD_RX.finditer(fm[cs:ce]):
            if unknown and _DELIVERY_CMD_RX.match(mc.group(0)):
                continue
            p = cs + mc.start()
            stp = stance_at(text, p)
            if stp == NEGATED:
                return "negated", []
            if conditional and stp in (QUESTION, CONDITIONAL):
                stp = AFFIRMED
            if stp != AFFIRMED:
                return f"stance_{stp}", []
            if REPORT_VERB_RX.search(fm[cs:p]):
                return "stance_reported", []
            found = True
    if not found and not conditional:
        # V44 (GEN-T27): tự-lệnh toàn mệnh đề chứa evidence ("Ừ chị lấy"); lập trường tại động từ vẫn phải khẳng định
        for cs, ce in ev_cls:
            if self_command(fm[cs:ce]):
                mv = re.search(r"\b(lay|dat|mua)\b", fm[cs:ce])
                stp = stance_at(text, cs + mv.start())
                if stp == NEGATED:
                    return "negated", []
                if stp != AFFIRMED:
                    return f"stance_{stp}", []
                found = True
    if not found and conditional:
        # V43: điều kiện đã thỏa KHÔNG thay bằng chứng yêu cầu mua — mệnh đề phải có động từ mua của khách (không thuật lời,
        # không chỉ ý định "mới tính / muốn / định …")
        for cs, ce in ev_cls:
            for mv in ORDER_VERB_RX.finditer(fm[cs:ce]):
                pre_c = fm[cs:cs + mv.start()]
                if INTENT_MODAL_RX.search(pre_c) or REPORT_VERB_RX.search(pre_c) or stance_at(text, cs + mv.start()) in (NEGATED, REPORTED):
                    continue
                found = True
    if not found:
        return "intent_only", []
    return None, []


GATED =("place_order", "change_order_address", "exchange", "return", "callback")
ACTIVE = ("open", "conditional", "needs_target")
EXECUTABLE = ("open", "conditional")
PARKED = "parked"                 # yêu cầu cũ chưa rõ thay hay giữ: không tự thực thi, không coi là đã rút (mục 9.1)
ORDER_KINDS = ("change_order_address", "exchange", "return")
PROPOSALS = {"confirm_order": "place_order", "confirm_new_price": "place_order", "exchange_offer": "exchange",
             "ask_additional_order": "place_order", "ask_multi_request": "place_order"}
STATUS_OF = {"confirmed_success": "done", "confirmed_failure": "failed", "unresolved": "unresolved"}
MAX_PRODUCT_CANDIDATES = 6


def _parent(sku):
    p = mt._parent(sku)[0] if sku else None
    return p["sku"] if p else sku


def _is_variant(sku):
    return bool(sku) and _parent(sku) != sku


def _parents_of(target):
    if not target or target.get("type") != "product":
        return set()
    return {_parent(x) for x in target.get("skus") or ()}


# ---------------------------------------------------------------------- V45 (duyệt 15/11, MP1): căn cứ đơn đích của KHÁCH
# Đơn đích của đổi địa chỉ / đổi / trả chỉ từ căn cứ của khách; target_ref của bộ hiểu và ref Jev chỉ là gợi ý (không cấp đơn).
ORDER_ID_RX = re.compile(r"(?<![a-z0-9])od\s?(\d{6})(?![0-9])", re.I)              # D3: mã đơn OD + 6 chữ số
TARGET_BASES = ("order_id", "product", "variant", "focus", "single_order", "accepted_proposal")


def _skus_of_names(items):
    """V47 (I1): Call Brief của đơn nhiều dòng chỉ có `variant_sku` dòng đầu + `items` = tên MỌI sản phẩm nối ", " (do
    agent._order_products dựng từ product_name). Dựng lại SKU bằng khớp ĐÚNG NGUYÊN tên catalog giữa hai dấu phân cách."""
    if not items:
        return []
    txt = ", ".join(items) if isinstance(items, (list, tuple)) else str(items)
    pad = ", " + txt + ", "
    out = []
    for p in mt.PRODUCTS:
        for k in [v["variant_sku"] for v in p.get("variants") or []] + [p["sku"]]:
            if ", " + product_name(k) + ", " in pad and k not in out:
                out.append(k)
    return out


def _order_skus(o):
    """SKU (biến thể nếu có) của một đơn: dòng đơn → skus → sku / variant_sku; V47: cộng thêm SKU dựng từ `items` của Call Brief."""
    base = [ln.get("sku") for ln in o.get("lines") or [] if ln.get("sku")] or list(o.get("skus") or []) \
        or [x for x in (o.get("sku") or o.get("variant_sku"),) if x]
    return list(dict.fromkeys(base + _skus_of_names(o.get("items"))))


def known_orders(s):
    """Đơn của khách code đang biết (như context(): đơn tạo trong cuộc + đơn trong Call Brief), không trùng mã."""
    if getattr(s, "proxy_caller", False):
        return []
    out, seen = [], set()
    for o in list(getattr(s, "orders_created", None) or []) + list((getattr(s, "brief", None) or {}).get("orders") or []):
        oid = o.get("order_id")
        if oid and oid not in seen:
            seen.add(oid); out.append(o)
    return out


def _variant_hit(sku, text):
    """D1: câu khách nêu size / màu khớp ĐÚNG biến thể `sku` của đơn (parser có sẵn find_variant; phần câu tự đóng góp, không
    tính trường hợp chỉ nhờ giá trị của chính đơn)."""
    from harness.tools import find_variant
    p, v = mt._parent(sku)
    if not p or not v or not p.get("variants"):
        return False
    by_size = find_variant(p["sku"], text, None, v["color"]) == sku and find_variant(p["sku"], "", None, v["color"]) != sku
    by_color = find_variant(p["sku"], text, v["size"], None) == sku and find_variant(p["sku"], "", v["size"], None) != sku
    return by_size or by_color


ADDRESS_STANCES = ("stated", "chosen")      # V46 (duyệt 16/11): hợp đồng bộ hiểu dùng cả hai cho địa chỉ khách tự nêu / chọn


def _stated_address(u):
    """Địa chỉ khách TỰ nói trong lượt (observation address, stance stated | chosen, chủ thể self) — span nguyên văn, hoặc None.
    Không nhận asked / negated / conditional / reported hay chủ thể other."""
    obs = [o for o in (u or {}).get("observations") or [] if o.get("slot") == "address" and o.get("stance", "stated") in ADDRESS_STANCES
           and o.get("subject", "self") == "self" and o.get("span")]
    return obs[-1]["span"].strip(" ,.") if obs else None


def order_basis(s, text, orders):
    """V45: căn cứ đơn đích trong CÂU KHÁCH trên danh sách đơn `orders`. → {"basis": order_id|product|variant|None,
    "order_id", "why"}; why (khi không có căn cứ): order_not_owned (mã không thuộc khách) | multi_order_ids | ambiguous (khớp
    nhiều đơn) | named_not_in_orders | None (câu không nêu đơn nào)."""
    from harness.agent import CATEGORY_WORDS
    from harness.extractor import ADDRESS_RX
    from harness.tools import find_products
    by_id = {str(o.get("order_id") or "").upper(): o for o in orders if o.get("order_id")}
    said = list(dict.fromkeys("OD" + m for m in ORDER_ID_RX.findall(text or "")))
    if said:
        if any(x not in by_id for x in said):
            return {"basis": None, "why": "order_not_owned", "said": said}
        if len(said) > 1:
            return {"basis": None, "why": "multi_order_ids", "said": said}
        return {"basis": "order_id", "order_id": by_id[said[0]]["order_id"]}
    t = ADDRESS_RX.sub(" ", text or "")
    f = " " + fold(t) + " "
    pars = {_parent(x) for x in find_products(t) if x}
    cats = {c for w, c in CATEGORY_WORDS if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", f)}

    def named(o):
        for k in _order_skus(o):
            p = mt._parent(k)[0]
            if _parent(k) in pars or (p and any(p["category"].startswith(c) for c in cats)):
                return True
        return False
    cand = [o for o in orders if named(o)] if (pars or cats) else list(orders)
    if (pars or cats) and len(cand) == 1:
        return {"basis": "product", "order_id": cand[0]["order_id"]}
    var = [o for o in cand if any(_variant_hit(k, t) for k in _order_skus(o))]
    if len(var) == 1:
        return {"basis": "variant", "order_id": var[0]["order_id"]}
    if pars or cats:
        return {"basis": None, "why": "ambiguous" if cand else "named_not_in_orders"}
    return {"basis": None, "why": "ambiguous" if len(var) > 1 else None}


def _relation(old, new):
    """Quan hệ hai đối tượng của hai yêu cầu cùng loại: same | covers (mới bao trùm cũ) | unknown (một bên chưa có) | differ."""
    if not old or not new:
        return "unknown"
    if old.get("type") != new.get("type"):
        return "differ"
    if old["type"] == "order":
        return "same" if old.get("order_id") == new.get("order_id") else "differ"
    po, pn = _parents_of(old), _parents_of(new)
    if po == pn:
        return "same"
    return "covers" if po and po <= pn else "differ"


class RequestState:
    def __init__(self):
        self.items, self.seq = [], 0
        self.refmap = {}                 # ref → target (dựng lại mỗi lượt ở context())
        self.proposal = None             # đề nghị nhân viên vừa nêu: {"goal", "kind", "target", "revision"}
        self.hold = None                 # lý do không ghi lượt này (câu mơ hồ / lỗi bộ hiểu / câu bị cắt)
        self.events = []                 # sự kiện của lượt hiện tại (trace)
        self.turn = 0
        self.last_blocked = None         # yêu cầu vừa bị từ chối cấp quyền (để executor nêu điều kiện)
        self.truncated = {}              # ứng viên bị cắt vì vượt giới hạn (trace; model không được chọn chúng)
        self.order_gate = None           # F8 (B2): yêu cầu đặt của khách bị cổng chặn ở lượt này {"why", "target", "stated_vnd"}
        self.turn_act = None             # C2 (15/11): response_to_agent.act của lượt hiện tại (để biết đề nghị đã được trả lời chưa)
        self.op_gate = None              # V44 (15/11): yêu cầu thao tác đơn bị chặn ở lượt này
        self.order_focus = None          # V45: đơn đã xác định duy nhất bằng căn cứ của khách trong cuộc gọi {"order_id","turn","basis"}
        self.turn_basis = None           # V45: căn cứ đơn trong câu khách của lượt hiện tại (order_basis)
        self.write_hold = None           # V45 §8.4: lượt chỉ thiếu đơn đích (phục hồi từ needs_clarification) → cấm mọi ghi trong lượt
        # V48 (16/11): địa chỉ có chủ — câu hỏi địa chỉ THỰC SỰ đã gửi {"owner": ("req", id) | ("complete", order_id), "slot", "turn"};
        # ý định hỏi trong lượt (ghi lúc dựng câu hỏi, chỉ thành pending_q khi câu cuối có câu hỏi đó); binding bổ sung địa chỉ cho
        # đơn vừa tạo của lượt {"order_id", "value", "span", "turn", "via"}
        self.pending_q = None
        self.q_intent = []
        self.completion = None
        self._prop0 = None

    # ------------------------------------------------------------------ ngữ cảnh gọn cho bộ hiểu (K07)
    def context(self, s):
        """Ứng viên cho bộ hiểu: sản phẩm parser catalog thấy trong CÂU HIỆN TẠI (s.turn_mentioned) xếp trước, rồi mẫu đang
        bàn, giỏ, mẫu đã bàn; tối đa MAX_PRODUCT_CANDIDATES sản phẩm cha. Ref sản phẩm lưu mức sản phẩm cha."""
        cands, self.refmap, self.truncated = [], {}, {}
        seen, cut = [], []
        mentioned = list(getattr(s, "turn_mentioned", None) or [])
        prop = getattr(s, "b2tt_proposal", None) if settings.b2_two_tier else None
        roles = [(x, "mentioned") for x in mentioned] + ([(s.focus, "focus")] if s.focus else []) \
            + ([(prop["sku"], "agent_proposed")] if prop and prop.get("sku") else []) \
            + [(x, "cart") for x in s.cart] + [(x, "discussed") for x in s.discussed]
        for sku, role in roles:
            par = _parent(sku)
            if not sku or par in seen or par in cut:
                continue
            if len(seen) >= MAX_PRODUCT_CANDIDATES:
                cut.append(par)
                continue
            seen.append(par)
            ref = f"P{len(seen)}"
            self.refmap[ref] = {"type": "product", "skus": (par,)}
            cands.append({"ref": ref, "kind": "product", "name": product_name(par), "role": role})
        if cut:
            self.truncated["products"] = cut
        if not getattr(s, "proxy_caller", False):          # người tự xưng người nhà: không đưa đơn của khách vào ngữ cảnh
            orders, oseen = [], set()
            for o in list(s.orders_created) + list((s.brief or {}).get("orders") or []):
                oid = o.get("order_id")
                if oid and oid not in oseen:
                    oseen.add(oid); orders.append(o)
            if len(orders) > 5:
                self.truncated["orders"] = [o["order_id"] for o in orders[:-5]]
            for i, o in enumerate(orders[-5:], 1):
                ref = f"O{i}"
                sku = o.get("sku") or o.get("variant_sku")
                self.refmap[ref] = {"type": "order", "order_id": o["order_id"]}
                cands.append({"ref": ref, "kind": "order", "order_id": o["order_id"], "product": product_name(sku) if sku else None,
                              "status": o.get("status"), "has_address": bool(o.get("address")) if o in s.orders_created else None})
        if s.cart:
            self.refmap["CART"] = {"type": "product", "skus": tuple(dict.fromkeys(_parent(x) for x in s.cart))}
        if s.discussed:
            self.refmap["ALL"] = {"type": "product", "skus": tuple(dict.fromkeys(_parent(x) for x in s.discussed))}
        pending = [{"id": r["id"], "kind": r["kind"], "status": r["status"], "target": self._target_name(r["target"]),
                    "condition": (r.get("condition") or {}).get("type")} for r in self.items if r["status"] in ACTIVE + (PARKED,)]
        # B (15/11, GEN-T16): nội dung các nhóm CART / ALL và các món của đề nghị đang chờ khách xác nhận — chỉ là dữ kiện cho bộ
        # hiểu chọn đúng đối tượng; không cấp quyền gì
        groups = {k: [product_name(x) for x in self.refmap[k]["skus"]] for k in ("CART", "ALL") if k in self.refmap}
        ptgt = (self.proposal or {}).get("target")
        return {"candidates": cands, "pending": pending, "groups": groups,
                "agent_proposal": (self.proposal or {}).get("goal"),
                "agent_proposal_items": [product_name(x) for x in (ptgt or {}).get("skus") or ()]
                if ptgt and ptgt.get("type") == "product" else None,
                "agent_last_goals": list(s.table_prev_goals or [])[:6]}

    @staticmethod
    def _target_name(t):
        if not t:
            return None
        if t.get("type") == "product":
            return ", ".join(product_name(x) for x in t.get("skus") or ())
        return t.get("order_id")

    # ------------------------------------------------------------------ nhận kết quả bộ hiểu
    def ingest(self, s, u, turn):
        """u = kết quả understanding.understand (đã kiểm). Không có quyền nào được cấp từ lỗi / mơ hồ."""
        self.events, self.hold, self.turn, self.last_blocked = [], None, turn, None
        self.order_gate = None
        self.op_gate = None              # V44: yêu cầu thao tác đơn bị chặn ở lượt này {"why", "kind"} → hỏi lại (apply_order_gate)
        self.write_hold = None
        self.q_intent, self.completion, self._prop0 = [], None, self.proposal
        self._bound_turn = set()         # V49: địa chỉ (đã fold) được gắn cho một chủ cụ thể trong lượt này
        if settings.planner_variant == "b2_jev":
            # V45 §8.2: căn cứ đơn trong câu khách (chỉ câu khách) + hiệu lực order_focus của cuộc gọi
            self.turn_basis = order_basis(s, getattr(s, "turn_text", "") or "", known_orders(s))
            tb = self.turn_basis
            if tb["basis"]:
                if (self.order_focus or {}).get("order_id") != tb["order_id"]:
                    self._event("order_focus", order_id=tb["order_id"], basis=tb["basis"])
                self.order_focus = {"order_id": tb["order_id"], "turn": turn, "basis": tb["basis"]}
            elif tb.get("why") and self.order_focus:
                self._event("order_focus_cleared", why=tb["why"])
                self.order_focus = None
        if u is None or u.get("error"):
            self.hold = "understanding_error"
            return
        if (u.get("ambiguity") or {}).get("level") == "needs_clarification":
            if self._target_only(s, u):
                # V45 §8.4: câu rõ thao tác + lệnh, CHỈ thiếu đơn đích → mở yêu cầu (chưa có đơn), cấm mọi ghi trong lượt, hỏi đơn nào
                self.write_hold = "target_only_turn"
                self._event("hold_target_only")
            else:
                # câu mơ hồ: không mở yêu cầu mới VÀ không dùng yêu cầu cũ để ghi trong lượt này (phải hỏi lại cho rõ)
                self.hold = "ambiguous_turn"
                self._event("hold", reason="ambiguous_turn")
                if settings.planner_variant == "b2_jev":
                    self._conflict_check(s, u, turn)              # V49: câu mơ hồ có địa chỉ khác cũng treo binding cũ
                return
        for w in u.get("withdrawn") or []:
            self._withdraw(w["kind"], turn, f"withdrawn:{w['evidence'][:40]}")
        act = (u.get("response") or {}).get("act")
        self.turn_act = act
        prop = self.proposal
        if prop and act in ("decline", "defer"):
            self._withdraw(prop["kind"], turn, f"{act}:{prop['goal']}")
        new = list(u.get("request_items") or [])
        b2 = settings.planner_variant == "b2_jev"
        text = getattr(s, "turn_text", "") or ""
        if b2:
            # V44: yêu cầu thao tác đơn đang chờ (mở ở lượt trước) mà câu hiện tại phủ định / hoãn đúng thao tác đó → rút, không để
            # lượt sau (vd khách đọc size) dùng lại yêu cầu cũ
            for k in ORDER_KINDS:
                if any(r["kind"] == k and r["status"] in ACTIVE + (PARKED,) and r["turn"] < turn for r in self.items) and op_refused(text, k):
                    self._withdraw(k, turn, "refused_op")
                    if (self.proposal or {}).get("kind") == k:
                        self.proposal = None
                        prop = None if (prop or {}).get("kind") == k else prop
        if b2 and prop and prop.get("kind") == "place_order" and any(w["kind"] == "place_order" for w in u.get("withdrawn") or []):
            # V41 (15/11): khách rút yêu cầu đặt → hủy luôn đề nghị đặt đang chờ (không giữ để lượt sau vô tình chấp nhận)
            self._cancel_proposal(turn, "withdrawn")
            prop = None
        accept_ok = None                                     # V41-1: đồng ý cùng lượt qua kiểm cứng chưa (None = không có đồng ý)
        if b2 and prop and act == "accept" and prop.get("kind") == "place_order":
            why_a, bad_a = order_authority(s, u, text, (u.get("response") or {}).get("evidence") or "", accept=True, conditional=False)
            # V43: "ok" chỉ trả lời đề nghị MỚI (vừa nói ở lượt trước, không phải đề nghị mang qua lượt xen), có revision ĐÃ NÓI (giá
            # từng đơn vị), và không nêu mẫu ngoài đề nghị
            men_a = {_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x}
            if why_a is None and prop.get("carried"):
                why_a = "accept_stale"
            if why_a is None and not (prop.get("revision") or {}).get("units"):
                why_a = "accept_no_revision"
            if why_a is None and men_a - _parents_of(prop.get("target")):
                why_a = "accept_target_mismatch"
            accept_ok = why_a is None
            if not accept_ok:
                self._event("accept_blocked", why=why_a)
                if why_a in REFUSAL:
                    self._cancel_proposal(turn, why_a)       # câu phủ định / hoãn / rút: coi như từ chối đề nghị
                    prop = None
                else:
                    self.turn_act = "accept_blocked"         # chưa trả lời đề nghị → C2 giữ đề nghị; nhân viên xin xác nhận lại
                    if not any(r["kind"] == "place_order" for r in new):
                        self.order_gate = {"why": why_a if why_a in ("pseudo_system", "price_unconfirmed") else "accept_unconfirmed",
                                           "target": prop.get("target"), "stated_vnd": bad_a}
        if prop and act == "accept" and accept_ok is not False and not any(r["kind"] == prop["kind"] for r in new):
            new.append({"kind": prop["kind"], "evidence": u["response"]["evidence"], "target_ref": None, "condition": None,
                        "_target": prop.get("target"), "_revision": prop.get("revision"), "_source": f"accept:{prop['goal']}",
                        "_additional": bool(prop.get("additional"))})
        men = {_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x}
        for it in new:
            if it["kind"] not in GATED:
                self._event("request_seen", kind=it["kind"])     # handoff / cancel / forget_me / order_status: chính sách xử lý
                continue
            target = it.get("_target") or (self.refmap.get(it["target_ref"]) if it.get("target_ref") else None)
            if it.get("target_invalid"):
                target = None
            if b2 and it["kind"] in ORDER_KINDS and self._answer_pending(it["kind"], turn):
                # V45 §8.5: lượt ngay sau câu hỏi chọn đơn của CHÍNH yêu cầu cùng loại → câu trả lời, không mở yêu cầu mới (gắn đơn ở
                # _bind_answer sau vòng lặp, theo căn cứ trong câu khách); không qua op_gate
                self._event("answer_item_merged", kind=it["kind"])
                continue
            if b2 and it["kind"] in ORDER_KINDS:
                # V44: thao tác đơn (đổi / trả / đổi địa chỉ) — đồng ý đề nghị hoặc yêu cầu trực tiếp đều qua kiểm cứng RIÊNG của
                # thao tác; qua thì ghi bằng chứng kiểm (consent) GẮN vào chính yêu cầu (kind / nguồn / lượt / đơn) để authorize kiểm lại
                is_acc = str(it.get("_source", "")).startswith("accept:")
                why_o = op_authority(s, u, text, it.get("evidence") or "", it["kind"], accept=is_acc, conditional=bool(it.get("condition")))
                if why_o is None and is_acc and it["kind"] == "exchange" and not (it.get("_revision") or {}).get("new_variant"):
                    why_o = "accept_no_revision"
                if why_o:
                    self._event("op_blocked", kind=it["kind"], why=why_o)
                    if why_o in REFUSAL:
                        self._withdraw(it["kind"], turn, f"refused:{why_o}")
                        if (self.proposal or {}).get("kind") == it["kind"]:
                            self.proposal = None
                    else:
                        self.op_gate = {"why": why_o, "kind": it["kind"]}
                    continue
                it = {**it, "_consent": {"rule": "op_v44", "kind": it["kind"], "evidence": (it.get("evidence") or "")[:60]}}
                # V45 §2: đơn đích CHỈ từ căn cứ của khách; target_ref của bộ hiểu là gợi ý (ghi lại để trace), không cấp đơn
                tb = self.turn_basis or {}
                hint = self.refmap.get(it["target_ref"]) if it.get("target_ref") else None
                basis, block = None, None
                if is_acc and (it.get("_target") or {}).get("type") == "order":
                    target, basis = it["_target"], "accepted_proposal"       # đề nghị nhân viên nêu cho đơn cụ thể, khách đồng ý
                elif tb.get("basis"):
                    target, basis = {"type": "order", "order_id": tb["order_id"]}, tb["basis"]
                elif tb.get("why") == "order_not_owned":
                    target, block = None, "order_not_owned"
                elif tb.get("why") is None and self.order_focus:
                    target, basis = {"type": "order", "order_id": self.order_focus["order_id"]}, "focus"
                else:
                    target = None
                    if tb.get("why"):
                        block = None                                          # mơ hồ / nêu món không có trong đơn → hỏi đơn nào
                it = {**it, "target_invalid": False, "_basis": basis, "_block": block, "_ambiguous": bool(tb.get("why")),
                      "_hint": (hint or {}).get("order_id") if (hint or {}).get("type") == "order" else it.get("target_ref")}
                if hint and target and hint != target:
                    self._event("model_ref_ignored", ref=it.get("target_ref"), basis=basis)
            bound_prop = False
            if it["kind"] == "place_order" and not it.get("_source") and b2:
                ptgt = (prop or {}).get("target") if (prop or {}).get("kind") == "place_order" else None
                if ptgt and ptgt.get("type") == "product" and not men:
                    # C3 (15/11): đang có đề nghị đặt nhóm T mà câu đặt KHÔNG nêu sản phẩm nào → đối tượng là T (không theo ref
                    # model chọn, vd màng lọc / CART); câu có nêu mẫu → xử lý như yêu cầu mới. Cổng F8 bên dưới vẫn quyết lệnh rõ.
                    if target is None or not _same_target(target, ptgt) or it.get("target_invalid"):
                        self._event("bound_to_proposal", ref=it.get("target_ref"), proposal=prop.get("goal"))
                    # V41-2: mang revision của đề nghị (giá / món ĐÃ NÓI) → authorize so như đường đồng ý (revision_changed)
                    it = {**it, "target_invalid": False, "_revision": prop.get("revision"), "_bound": prop.get("goal")}
                    target, bound_prop = ptgt, True
            if it["kind"] == "place_order" and not it.get("_source") and b2:
                # F8 + V41-1: kiểm cứng chung (giả danh, giá, lập trường, hoãn, phần giao hàng). Đồng ý cùng lượt chỉ bỏ qua
                # intent_only khi chính đồng ý đó qua kiểm cứng (accept_ok)
                accepted = bool(prop and act == "accept" and prop.get("kind") == "place_order" and accept_ok)
                why, bad = order_authority(s, u, text, it.get("evidence") or "", accept=False, conditional=bool(it.get("condition")))
                if why in REFUSAL:
                    # câu đặt bị phủ định / hoãn ("chị chưa chốt đâu"): không mở yêu cầu, không xin xác nhận; hủy đề nghị đang chờ
                    self._event("order_refused", why=why)
                    if prop and prop.get("kind") == "place_order":
                        self._cancel_proposal(turn, why)
                        prop = None
                    continue
                if why not in ("pseudo_system", "price_unconfirmed") and not bound_prop and it.get("target_ref") != "ALL" and not men:
                    # V42 (15/11, GEN-T16): câu đặt KHÔNG nêu món, không có đề nghị đang chờ, mà còn NHIỀU đối tượng hợp lý (các
                    # món đã bàn ∪ giỏ) → không dùng ref model đoán (vd CART chỉ có màng lọc), không xin xác nhận một giỏ hệ thống đoán:
                    # hỏi rõ + liệt kê lựa chọn. Khách nói rõ "giỏ" (ref CART) là có bằng chứng đối tượng → giữ đường cũ.
                    opts = self.plausible_objects(s)
                    if len(opts) > 1 and not (it.get("target_ref") == "CART" and _names_cart(text)):
                        why, bad = "target_ambiguous", []
                        self.order_gate = {"why": why, "target": None, "options": opts, "stated_vnd": []}
                        self._event("order_gate", why=why, options=len(opts))
                        continue
                if why != "pseudo_system" and it.get("target_ref") == "ALL" and not bound_prop:
                    # C1 (15/11): "ALL" (mọi mẫu đã bàn) không tự thành đơn / giỏ mua → xin xác nhận liệt kê đúng từng món
                    why, bad = "all_unconfirmed", []
                # yêu cầu CÓ ĐIỀU KIỆN ("khi nào có hàng thì lấy …") là cam kết của khách, chờ điều kiện — không phải chỉ bày tỏ ý định
                # V43: yêu cầu có điều kiện KHÔNG còn được miễn intent_only (đã kiểm lệnh / động từ mua tại mệnh đề trong
                # order_authority); chỉ đồng ý ĐÃ QUA kiểm cứng (accept_ok) mới thay cho lệnh rõ
                if why and not (accepted and why == "intent_only"):
                    self.order_gate = {"why": why, "target": target, "stated_vnd": bad}
                    self._event("order_gate", why=why, **({"stated_vnd": bad} if bad else {}))
                    continue
            inherit, restated = None, None
            cond = it.get("condition")
            for r in self.items:
                if r["kind"] != it["kind"] or r["status"] not in ACTIVE + (PARKED,):
                    continue
                rel = _relation(r["target"], target)
                if r["status"] == PARKED and rel not in ("same", "covers"):
                    continue                                    # yêu cầu đang chờ làm rõ: chỉ đóng khi khách nhắc lại / rút
                if r["turn"] == turn and r["status"] != PARKED:
                    # CÙNG LƯỢT: chỉ thay khi cùng / bao trùm đối tượng; câu lặp lại không đối tượng, không điều kiện (vd "ok lấy
                    # luôn, chốt nhé" thành hai mục) là nhắc lại mục đã có. Khác đối tượng → giữ cả hai, executor hỏi trước khi ghi.
                    if rel == "unknown" and target is None and not cond and not it.get("target_invalid") and r["target"]:
                        restated = r; break
                    if rel in ("same", "covers") or (rel == "unknown" and r["target"] is None and not r.get("condition")):
                        r["status"] = "superseded"; r["closed_turn"] = turn
                        self._event("superseded", id=r["id"])
                    continue
                if rel in ("same", "covers", "unknown") or it.get("target_invalid"):
                    # lượt sau, cùng đối tượng / bao trùm / một bên chưa có đối tượng → yêu cầu mới THAY yêu cầu cũ (cùng một việc);
                    # đồng ý cũ không mang sang payload mới (revision của yêu cầu mới tính lại bên dưới)
                    if rel == "unknown" and target is None and r["target"] and not it.get("target_invalid"):
                        inherit = r["target"]                   # "chốt nhé" không nêu đối tượng: kế thừa đối tượng của yêu cầu bị thay
                    r["status"] = "superseded"; r["closed_turn"] = turn
                    self._event("superseded", id=r["id"])
                else:
                    r["status"] = PARKED; r["parked_turn"] = turn; r["park_reason"] = "new_request_other_target"
                    self._event("parked", id=r["id"], why="new_request_other_target")
            if restated is not None:
                self._event("restated_in_turn", id=restated["id"])
                continue
            self.seq += 1
            status = "needs_target" if it.get("target_invalid") else "conditional" if cond else "open"
            rev = it.get("_revision")
            if rev is None and target and target.get("type") == "product":
                rev = self.selection_revision(s, target.get("skus") or ())     # giá / số lượng ĐÃ BÁO lúc khách đồng ý
            if it["kind"] == "place_order":
                rev = {**(rev or {}), **self.delivery_terms(s)}
            r = {"id": f"R{self.seq}", "kind": it["kind"], "target": target, "revision": rev, "condition": cond,
                 "evidence": it["evidence"][:120], "turn": turn, "source": it.get("_source", "customer_request"), "status": status}
            if inherit:
                r["inherit"] = inherit
            if it.get("_additional"):
                r["additional"] = True                          # khách xác nhận đặt THÊM một đơn cùng sản phẩm (đề nghị đã nêu)
            if it.get("_bound"):
                r["bound"] = it["_bound"]                       # V41-2: gắn đề nghị qua C3 → authorize so revision như đồng ý
            if it.get("_consent"):
                # V44: bằng chứng kiểm gắn ĐÚNG yêu cầu này (không phải cờ chung): kind + nguồn + lượt + đơn đích lúc mở
                r["consent"] = {**it["_consent"], "source": r["source"], "turn": turn,
                                "target": (target or {}).get("order_id") if (target or {}).get("type") == "order" else None}
            if b2 and it["kind"] in ORDER_KINDS:
                # V45: căn cứ đơn đích (None = chưa có → executor hỏi đơn nào, trừ khi khách có đúng một đơn), mã lạ chặn hẳn,
                # gợi ý của model (chỉ trace), địa chỉ khách nói cho yêu cầu (dùng tiếp khi khách trả lời câu hỏi chọn đơn)
                r["target_basis"] = it.get("_basis") if target else None
                r["target_block"] = it.get("_block")
                r["target_ambiguous"] = bool(it.get("_ambiguous")) and not target
                r["model_ref"] = it.get("_hint")
                if it["kind"] == "change_order_address":
                    self._bind_command(s, u, r, turn)          # V48 L1: chỉ khi lượt một mục đích
            self.items.append(r)
            self._event("opened", id=r["id"], kind=r["kind"], source=r["source"], status=status)
        if b2:
            self._bind_answer(u, turn)
            self._bind_answer_address(s, u, turn)              # V48 L2 / bổ sung đơn vừa tạo: trả lời đúng câu hỏi địa chỉ đã gửi
            self._conflict_check(s, u, turn)                   # V49: địa chỉ mới chưa có chủ trái binding đang có → treo binding

    # ------------------------------------------------------------------ V45: đơn đích
    def _answer_pending(self, kind, turn):
        """§8.5: đúng một yêu cầu thao tác đơn cùng loại, chưa có đơn đích, nhân viên vừa hỏi chọn đơn ở lượt ngay trước."""
        rs = [r for r in self.items if r["kind"] in ORDER_KINDS and r["status"] in ACTIVE and r.get("target") is None]
        return len(rs) == 1 and rs[0]["kind"] == kind and rs[0].get("asked_target_turn") == turn - 1

    def _bind_answer(self, u, turn):
        """§8.5: lượt ngay sau câu hỏi chọn đơn: câu khách có căn cứ (mã đơn / sản phẩm / size–màu) → gắn đơn vào CHÍNH yêu cầu cũ
        (giữ địa chỉ đã lưu, cập nhật nếu khách nói địa chỉ mới). Không có căn cứ → giữ nguyên (lại hỏi đơn nào)."""
        rs = [r for r in self.items if r["kind"] in ORDER_KINDS and r["status"] in ACTIVE and r.get("target") is None]
        if len(rs) != 1 or rs[0].get("asked_target_turn") != turn - 1:
            return
        r, tb = rs[0], self.turn_basis or {}
        if tb.get("why") == "order_not_owned":
            r["target_block"] = "order_not_owned"
            self._event("answer_rejected", id=r["id"], why="order_not_owned")
            return
        if not tb.get("basis"):
            return
        r["target"] = {"type": "order", "order_id": tb["order_id"]}
        r["target_basis"], r["target_ambiguous"], r["target_block"] = tb["basis"], False, None
        if r["status"] == "needs_target":
            r["status"] = "open"
        if r["kind"] == "change_order_address":
            # V48: chọn đơn KHÔNG ghi đè địa chỉ đã gắn. Lượt trả lời nêu địa chỉ khác (sửa? hay địa chỉ để nhận diện đơn?) → không
            # đoán: bỏ binding, hỏi lại địa chỉ. Gắn đơn khác với đơn lúc gắn địa chỉ → binding không mang sang.
            b = r.get("addr")
            a = [o for o in (u or {}).get("observations") or [] if o.get("slot") == "address"]
            if b and a and not (len(a) == 1 and fold(str(a[0].get("value") or a[0].get("span") or "")) == fold(str(b["value"]))):
                self._suspend(r, "answer_conflict", turn)
            elif b and b.get("order_id") and b["order_id"] != tb["order_id"]:
                self._suspend(r, "retarget", turn)
            elif b and not b.get("order_id") and b.get("status", "valid") == "valid":
                b["order_id"] = tb["order_id"]
        self._event("target_answer", id=r["id"], order_id=tb["order_id"], basis=tb["basis"])

    def mark_asked_target(self, r, turn):
        """Executor dựng câu hỏi chọn đơn cho yêu cầu r (ask_which_order). V48: chỉ là Ý ĐỊNH; set_proposal xác nhận khi câu cuối thật
        sự có câu hỏi đó → lượt sau mới được coi là câu trả lời (§8.5)."""
        r["asked_target_intent"] = turn

    def note_question(self, r, slot, turn):
        """V48: executor dựng câu hỏi `slot` (address) cho đúng yêu cầu r — ý định, xác nhận ở set_proposal."""
        if r is not None and ("req", r["id"]) not in self.q_intent:
            self.q_intent.append(("req", r["id"]))

    def _confirm_questions(self, s, goals):
        """V48: câu hỏi chỉ được coi là đã hỏi khi có trong câu THỰC SỰ gửi (goals = block của câu cuối, sau fallback)."""
        turn = self.turn
        if "ask_which_order" in goals:
            for r in self.items:
                if r.get("asked_target_intent") == turn:
                    r["asked_target_turn"] = turn
        pq = None
        if "ask_address" in goals:
            owners = list(self.q_intent)
            lacking = [o["order_id"] for o in getattr(s, "orders_created", None) or [] if not o.get("address")]
            if not owners and len(lacking) == 1 and self.done_orders_ok():
                owners = [("complete", lacking[0])]          # hỏi địa chỉ cho ĐÚNG đơn vừa tạo còn thiếu
            if len(owners) == 1:
                pq = {"owner": owners[0], "slot": "address", "turn": turn}
            else:
                self._event("address_question_unowned", owners=len(owners))
        self.pending_q = pq

    # ------------------------------------------------------------------ V48: địa chỉ có chủ (binding dương)
    @staticmethod
    def _one_address(u):
        """Đúng MỘT observation địa chỉ trong lượt (mọi stance), và nó stance stated | chosen, chủ thể self → {value, span}."""
        a = [o for o in (u or {}).get("observations") or [] if o.get("slot") == "address"]
        if len(a) != 1:
            return None
        o = a[0]
        if o.get("stance", "stated") not in ADDRESS_STANCES or o.get("subject", "self") != "self":
            return None
        v = o.get("value") or (o.get("span") or "").strip(" ,.")
        return {"value": v, "span": o.get("span")} if v else None

    def _single_purpose(self, s, u, kinds, parents):
        """V48: lượt CHỈ phục vụ một việc thuộc `kinds`: mọi request item thô (trước cổng, kể cả bị chặn) thuộc kinds, tối đa một;
        không rút; không từ chối / hoãn / đồng ý đề nghị loại khác; sản phẩm khách nhắc ⊆ `parents`. Không suy từ "không thấy đối
        thủ" ở danh sách yêu cầu đã mở."""
        raw = list(u.get("request_items") or [])
        if len(raw) > 1 or any(i.get("kind") not in kinds for i in raw) or u.get("withdrawn"):
            return False
        act = (u.get("response") or {}).get("act")
        if act in ("decline", "defer") or (act == "accept" and self._prop0 and self._prop0.get("kind") not in kinds):
            return False
        men = {_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x}
        return not (men - set(parents))

    @staticmethod
    def _order_parents(orders):
        return {_parent(k) for o in orders for k in _order_skus(o)}

    @staticmethod
    def _is_current_address(s, value):
        """Địa chỉ trùng địa chỉ hiện có của một đơn trong cuộc → có thể là địa chỉ để NHẬN DIỆN đơn, không là địa chỉ mới."""
        return any(o.get("address") and fold(o["address"]) == fold(value) for o in getattr(s, "orders_created", None) or [])

    def _scope_parents(self, s, r):
        oid = (r.get("target") or {}).get("order_id")
        orders = known_orders(s)
        return self._order_parents([o for o in orders if o.get("order_id") == oid] if oid else orders)

    def _bind_command(self, s, u, r, turn):
        """L1: khách ra lệnh đổi địa chỉ (request mở ở lượt này) và lượt một mục đích → địa chỉ thuộc request này."""
        a = self._one_address(u)
        if not a:
            return
        if not self._single_purpose(s, u, ("change_order_address",), self._scope_parents(s, r)):
            self._event("address_not_bound", id=r["id"], why="multi_purpose")
            return
        if self._is_current_address(s, a["value"]):
            self._event("address_not_bound", id=r["id"], why="current_address")
            return
        r["addr"] = {**a, "turn": turn, "via": "command", "order_id": (r.get("target") or {}).get("order_id"), "status": "valid"}
        self._bound_turn.add(fold(str(a["value"])))
        self._event("address_bound", id=r["id"], via="command")

    def _bind_answer_address(self, s, u, turn):
        """L2: lượt ngay sau câu hỏi địa chỉ ĐÃ GỬI cho đúng chủ (request đổi địa chỉ / đơn vừa tạo thiếu địa chỉ), lượt một mục đích."""
        pq = self.pending_q
        if not pq or pq.get("slot") != "address" or pq.get("turn") != turn - 1:
            return
        a = self._one_address(u)
        if not a:
            return
        kind, ref = pq["owner"]
        if kind == "req":
            r = next((x for x in self.items if x["id"] == ref and x["kind"] == "change_order_address" and x["status"] in ACTIVE), None)
            if r is None or self.bound_address(r):
                return
            if not self._single_purpose(s, u, ("change_order_address",), self._scope_parents(s, r)) \
                    or self._is_current_address(s, a["value"]):
                self._event("address_not_bound", id=r["id"], why="answer_not_single")
                return
            if r.get("addr"):
                r.setdefault("addr_history", []).append(dict(r["addr"]))
            r["addr"] = {**a, "turn": turn, "via": "answer_address", "order_id": (r.get("target") or {}).get("order_id"),
                         "q_turn": pq["turn"], "status": "valid"}
            self._bound_turn.add(fold(str(a["value"])))
            self._event("address_bound", id=r["id"], via="answer_address")
        elif kind == "complete":
            o = next((x for x in getattr(s, "orders_created", None) or [] if x["order_id"] == ref and not x.get("address")), None)
            if o is None or self.has_active("change_order_address"):
                return
            if not self._single_purpose(s, u, ("place_order",), self._order_parents([o])):
                self._event("completion_not_bound", order_id=ref, why="answer_not_single")
                return
            self.completion = {**a, "order_id": ref, "turn": turn, "via": "answer_address", "q_turn": pq["turn"]}
            self._bound_turn.add(fold(str(a["value"])))
            self._event("completion_bound", order_id=ref)

    def completion_for(self, s):
        """Binding bổ sung địa chỉ còn hiệu lực ở lượt này cho đúng một đơn vừa tạo còn thiếu địa chỉ, hoặc None."""
        cb = self.completion
        if not cb or cb.get("turn") != self.turn or self.has_active("change_order_address"):
            return None
        o = next((x for x in getattr(s, "orders_created", None) or [] if x["order_id"] == cb["order_id"] and not x.get("address")), None)
        return (cb, o) if o is not None else None

    def bound_address(self, r):
        """Địa chỉ đã gắn với CHÍNH request đổi địa chỉ r và CÒN HIỆU LỰC (readiness, clarify và commit cùng đọc), hoặc None.
        V49: binding bị treo (xung đột chưa giải quyết) không dùng được."""
        b = r.get("addr") or {}
        return b.get("value") if b.get("status", "valid") == "valid" else None

    def suspended_in_turn(self):
        """V50: request đổi địa chỉ còn hiệu lực có binding VỪA bị treo ở lượt này (để hỏi lại đúng request đó). Chỉ đọc."""
        return [r for r in self.items if r["kind"] == "change_order_address" and r["status"] in ACTIVE + (PARKED,)
                and (r.get("addr") or {}).get("status") == "suspended" and r["addr"].get("suspended_turn") == self.turn]

    def _suspend(self, r, why, turn):
        """V49: treo binding địa chỉ của r — giữ lịch sử để giải thích, KHÔNG còn là địa chỉ dùng để ghi. Không tự hết treo theo
        lượt; chỉ binding mới hợp lệ (lệnh rõ → request mới, hoặc trả lời câu hỏi địa chỉ đã gửi) thay được."""
        b = r.get("addr")
        if not b or b.get("status", "valid") != "valid":
            return
        r.setdefault("addr_history", []).append(dict(b))
        b.update(status="suspended", suspended_turn=turn, suspend_why=why)
        self._event("address_suspended", id=r["id"], why=why)

    def _clearly_other(self, s, u, r):
        """Địa chỉ của lượt thuộc RÕ việc khác (lượt chỉ đặt hàng / thêm giỏ một sản phẩm không có trong đơn đích của r)."""
        raw = list(u.get("request_items") or [])
        men = {_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x}
        return bool(raw) and all(i.get("kind") in ("place_order", "add_to_cart") for i in raw) and bool(men) \
            and not (men & self._scope_parents(s, r))

    def _conflict_check(self, s, u, turn):
        """V49: lượt có địa chỉ khách tự nêu (stated / chosen, self) KHÁC binding còn hiệu lực của một request đổi địa chỉ, mà địa
        chỉ đó không được gắn cho chủ nào trong lượt và không thuộc rõ việc khác → treo binding (hỏi lại, không dùng X, không tự
        dùng Y). Địa chỉ trùng X hoặc câu hỏi (asked) không phải xung đột."""
        vals = {fold(str(o.get("value") or o.get("span") or "")) for o in (u or {}).get("observations") or []
                if o.get("slot") == "address" and o.get("stance", "stated") in ADDRESS_STANCES and o.get("subject", "self") == "self"}
        vals = {v for v in vals if v} - self._bound_turn
        if not vals:
            return
        for r in self.items:
            if r["kind"] != "change_order_address" or r["status"] not in ACTIVE + (PARKED,):
                continue
            x = self.bound_address(r)
            if not x or (r["addr"].get("turn") == turn) or not (vals - {fold(str(x))}):
                continue
            if self._clearly_other(s, u, r):
                self._event("address_other_work", id=r["id"])
                continue
            self._suspend(r, "conflict", turn)

    def _target_only(self, s, u):
        """§8.4: câu bị đánh dấu needs_clarification nhưng CHỈ thiếu đơn đích → True (mở yêu cầu, cấm ghi trong lượt, hỏi đơn nào)."""
        if settings.planner_variant != "b2_jev":
            return False
        items = list(u.get("request_items") or [])
        if not items or any(i.get("kind") not in ORDER_KINDS for i in items) or u.get("withdrawn"):
            return False
        if (u.get("response") or {}).get("act") in ("accept", "decline", "defer"):
            return False
        tb = self.turn_basis or {}
        if tb.get("basis") or tb.get("why"):
            return False
        if len(known_orders(s)) < 2:
            return False
        text = getattr(s, "turn_text", "") or ""
        return all(op_authority(s, u, text, i.get("evidence") or "", i["kind"], accept=False, conditional=bool(i.get("condition"))) is None
                   for i in items)

    @staticmethod
    def delivery_terms(s):
        """Thanh toán / địa chỉ đang biết lúc mở yêu cầu, kèm NGUỒN (customer:tN | memory | default) — để khi thực thi ở lượt sau
        biết giá trị có đổi mà khách không nói hay không (mục 9.2)."""
        src = getattr(s, "known_src", {}) or {}
        known = getattr(s, "known", {}) or {}
        out = {}
        for k in ("payment", "address"):
            if known.get(k):
                out[k] = {"value": known[k], "src": src.get(k, "unknown")}
        return out

    @staticmethod
    def plausible_objects(s):
        """V42: đối tượng hợp lý cho câu đặt không nêu món = SKU cha của các món đã bàn ∪ giỏ (giữ thứ tự, không tự thêm vào giỏ)."""
        return list(dict.fromkeys(_parent(x) for x in list(getattr(s, "discussed", None) or []) + list(getattr(s, "cart", None) or [])
                                  if x))

    def _cancel_proposal(self, turn, why):
        """V41 (15/11): khách từ chối / hoãn / rút → hủy đề nghị đặt đang chờ + rút yêu cầu đặt còn mở; lượt này coi như đã trả lời
        (decline) nên C2 không mang đề nghị sang lượt sau."""
        if self.proposal:
            self._event("proposal_cancelled", goal=self.proposal.get("goal"), why=why)
        self.proposal = None
        self._withdraw("place_order", turn, f"refused:{why}")
        self.turn_act = "decline"

    def _withdraw(self, kind, turn, why):
        for r in self.items:
            if r["kind"] == kind and r["status"] in ACTIVE + (PARKED,):
                r["status"] = "withdrawn"; r["closed_turn"] = turn
                self._event("withdrawn", id=r["id"], why=why)

    @staticmethod
    def selection_revision(s, skus):
        """Revision của một lựa chọn: giá TỪNG ĐƠN VỊ đã báo gần nhất trong cuộc (BTC 11/2026). Ưu tiên pricing.quote_order
        khớp đúng lựa chọn (phân bổ AIR-2ND-50 / TRADE-IN theo đơn vị); không có thì giá một máy của get_quote (không basket)
        từng sản phẩm. Kèm số lượng khách nói cùng lượt."""
        log = list(getattr(s, "call_tool_log", []) or []) + list(getattr(getattr(s, "tools", None), "log", []) or [])
        want = sorted(_parent(x) for x in skus)
        units = None
        for tc in reversed(log):
            r = tc.get("result")
            if tc.get("name") == "pricing.quote_order" and isinstance(r, dict) and isinstance(r.get("units"), list):
                if sorted({_parent(u["sku"]) for u in r["units"]}) == sorted(set(want)):
                    units = sorted([_parent(u["sku"]), u["final_price_vnd"]] for u in r["units"])
                    break
        if units is None:
            last = {}
            for tc in log:
                r = tc.get("result")
                a = tc.get("args") or {}
                if tc.get("name") == "pricing.get_quote" and isinstance(r, dict) and r.get("final_price_vnd") and not a.get("basket_skus"):
                    if _parent(a.get("sku")) in want:
                        last[_parent(a["sku"])] = r["final_price_vnd"]
            units = sorted([p, last[p]] for p in want if p in last)
        qo = getattr(s, "qty_obs", None)
        return {"units": units, "qty": qo[1] if qo and qo[0] == getattr(s, "turn_no", None) else None}

    @staticmethod
    def unambiguous_selection(s, inherited=None):
        """Đối tượng của yêu cầu đặt hàng KHÔNG có ref, chỉ khi không mơ hồ (mục 4.3): đúng MỘT sản phẩm parser catalog thấy
        trong câu hiện tại → sản phẩm đó; nhiều sản phẩm trong câu → mơ hồ. Không nhắc sản phẩm: đối tượng kế thừa của yêu cầu
        cùng loại vừa bị thay → mẫu đang bàn khi giỏ rỗng / chỉ chứa chính nó → món duy nhất trong giỏ khi không có mẫu đang bàn.
        Còn lại → None (hỏi lại). KHÔNG lấy toàn giỏ."""
        men = list(dict.fromkeys(_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x))
        if men:
            return (men[0],) if len(men) == 1 else None
        if inherited and inherited.get("type") == "product" and inherited.get("skus"):
            return tuple(inherited["skus"])
        if RequestState.proposal_ambiguity(s):
            return None                      # b2tt-2: mơ hồ giữa mẫu đang bàn và mẫu agent vừa đề xuất → hỏi lại, không lấy focus
        cart = list(dict.fromkeys(_parent(x) for x in s.cart))
        focus = _parent(s.focus) if s.focus else None
        if focus and (not cart or cart == [focus]):
            return (focus,)
        if not focus and len(cart) == 1:
            return (cart[0],)
        return None

    @staticmethod
    def proposal_ambiguity(s):
        """b2tt-2 (18/11, QUYET-DINH-KIEN-TRUC-SAU-UI5): chỉ khi B2_TWO_TIER. Lượt NGAY SAU khi tầng tư vấn đề xuất một mẫu KHÁC mẫu
        khách đang bàn (đề xuất không thay focus — s.b2tt_proposal) thì lời đặt không nêu mẫu là mơ hồ giữa hai mẫu.
        → (sku cha đang bàn | None, sku cha đề xuất) | None. Khách nêu tên mẫu / chọn ref → không qua đây (dùng ref mới)."""
        if not settings.b2_two_tier:
            return None
        p = getattr(s, "b2tt_proposal", None)
        if not p or p.get("turn") is None or p.get("turn") != (getattr(s, "turn_no", 0) or 0) - 1:
            return None
        focus = _parent(s.focus) if s.focus else None
        prop = _parent(p.get("sku"))
        return (focus, prop) if prop and prop != focus else None

    def select(self, kind):
        """Yêu cầu sẽ thực thi cho loại này → (request | None, lý do). Nhiều yêu cầu cùng loại còn hiệu lực (khác đối tượng,
        cùng lượt) → multi_request: hỏi trước khi ghi, không lấy yêu cầu cuối."""
        if self.hold:
            return None, self.hold
        act = [r for r in self.items if r["status"] in ACTIVE and r["kind"] == kind]
        if not act:
            return None, "no_request"
        if len(act) > 1:
            return None, "multi_request"
        return act[0], ("target_unresolved" if act[0]["status"] == "needs_target" else "ok")

    def active(self, kind):
        return [r for r in self.items if r["status"] in ACTIVE and r["kind"] == kind]

    def park(self, r, reason):
        """Executor tạm giữ yêu cầu (không tự thực thi lượt sau, không coi là khách rút) và hỏi rõ."""
        r["status"] = PARKED; r["parked_turn"] = self.turn; r["park_reason"] = reason
        self._event("parked", id=r["id"], why=reason)

    def parked_now(self, kind, reason="new_request_other_target"):
        return [r for r in self.items if r["kind"] == kind and r["status"] == PARKED and r.get("parked_turn") == self.turn
                and r.get("park_reason") == reason]

    def bind_unbound(self, s):
        """Cuối lượt: yêu cầu đặt hàng mở TRONG LƯỢT NÀY chưa có đối tượng → gắn khi lựa chọn KHÔNG mơ hồ (unambiguous_selection,
        không lấy toàn giỏ) kèm revision — để lượt sau khách đổi mẫu / size / số lượng / giá thì đồng ý cũ không áp."""
        for r in self.items:
            if r["status"] in EXECUTABLE and r["target"] is None and r["kind"] == "place_order" and r["turn"] == self.turn:
                sel = self.unambiguous_selection(s, r.get("inherit"))
                if sel:
                    r["target"] = {"type": "product", "skus": sel}
                    r["revision"] = {**(r.get("revision") or {}), **self.selection_revision(s, sel)}
                    self._event("bound", id=r["id"], target=self._target_name(r["target"]))

    def set_proposal(self, s, goals, facts):
        """Ghi đề nghị nhân viên nêu ở lượt này (để lượt sau 'ok em' chỉ xác nhận đúng đề nghị đó, đúng revision đã nói).
        Đối tượng lấy từ NỘI DUNG đã render: facts.proposal (executor ghi sản phẩm của câu xác nhận) hoặc báo giá của chính lượt
        (confirm_new_price đi cùng block giá) — không lấy giỏ / mẫu đang bàn; không có thì đề nghị không có đối tượng."""
        if settings.planner_variant == "b2_jev":
            self._confirm_questions(s, goals)
        prev, self.proposal = self.proposal, None
        for g in goals:
            kind = PROPOSALS.get(g)
            if not kind:
                continue
            additional = False
            if kind == "place_order":
                p = facts.get("proposal") or {}
                sel = tuple(p.get("skus") or ())
                if not sel and (facts.get("quote") or {}).get("sku"):
                    sel = (facts["quote"]["sku"],)
                target = {"type": "product", "skus": sel} if sel else None
                rev = self.selection_revision(s, sel) if sel else None
                additional = bool(p.get("additional")) and g == "ask_additional_order"
            else:
                ep = facts.get("exchange_preview") or {}
                target = {"type": "order", "order_id": ep.get("order_id")} if ep.get("order_id") else None
                rev = {"new_variant": ep.get("new_variant_sku")} if ep.get("new_variant_sku") else None
            self.proposal = {"goal": g, "kind": kind, "target": target, "revision": rev, "additional": additional}
            break
        if self.proposal is None and prev and self._keep_proposal(s, prev):
            self.proposal = {**prev, "carried": int(prev.get("carried") or 0) + 1}
            self._event("proposal_kept", goal=prev["goal"], carried=self.proposal["carried"])

    def _keep_proposal(self, s, prev):
        """C2 (15/11, B2): đề nghị đặt hàng (có đối tượng) còn hiệu lực qua lượt xen giữa (khách hỏi COD, nói thanh toán, đọc địa
        chỉ) cho tới khi: khách trả lời đề nghị (accept / decline / defer), rút yêu cầu, có yêu cầu đặt mở / bị cổng chặn / thực
        hiện trong lượt, nhân viên nêu đề nghị mới (xử lý ở trên), hoặc khách nêu tên mẫu NGOÀI đề nghị. Thanh toán / địa chỉ ở lượt
        xen giữa chỉ là thông tin đơn (known), không phải xác nhận."""
        if settings.planner_variant != "b2_jev" or prev.get("kind") != "place_order":
            return False
        tgt = prev.get("target")
        if not tgt or tgt.get("type") != "product":
            return False
        if self.turn_act in ("accept", "decline", "defer"):
            return False
        if any(e["event"] in ("withdrawn", "opened", "settled", "order_gate") for e in self.events):
            return False
        men = {_parent(x) for x in (getattr(s, "turn_mentioned", None) or []) if x}
        return not (men - _parents_of(tgt))

    # ------------------------------------------------------------------ cấp quyền ghi cho executor
    def authorize(self, kind, target=None, total_vnd=None, *, unique_target=False, in_stock=None, revision=None, req_id=None,
                  address=None):
        """→ (request | None, lý do). target: {"type":"product","skus":(...)} hoặc {"type":"order","order_id":...}.
        unique_target: executor xác nhận chỉ có đúng một đối tượng ứng viên (cho phép gắn yêu cầu chưa có target).
        in_stock: executor đã kiểm tồn kho bằng tool trong lượt. revision: {"units": [[cha, giá từng đơn vị]...], "qty": n,
        "new_variant": sku, "payment"/"address": {"value", "src"}}. req_id: executor đã chọn yêu cầu (select) → kiểm CHÍNH yêu
        cầu đó còn hiệu lực, không chọn lại theo loại sau khi đã lấy dữ liệu."""
        self.last_blocked = None
        if self.hold:
            return None, self.hold
        if self.write_hold:
            return None, self.write_hold                    # V45 §8.4: lượt chỉ thiếu đơn đích → không ghi gì trong lượt
        act = [r for r in self.items if r["status"] in ACTIVE and r["kind"] == kind]
        if kind in ("exchange", "return"):
            other = "return" if kind == "exchange" else "exchange"
            if any(r["status"] in ACTIVE and r["kind"] == other for r in self.items) and act:
                return None, "conflicting_exchange_return"
        if req_id is not None:
            r = next((x for x in self.items if x["id"] == req_id), None)
            if r is None or r["kind"] != kind or r["status"] not in ACTIVE:
                return None, "request_closed"
        else:
            if not act:
                return None, "no_request"
            if len(act) > 1:
                self.last_blocked = act[-1]
                return None, "multi_request"
            r = act[-1]
        self.last_blocked = r
        if r["status"] == "needs_target":
            return None, "target_unresolved"
        if kind in ORDER_KINDS and settings.planner_variant == "b2_jev":
            # V44: trước order.update — yêu cầu phải mang bằng chứng kiểm của CHÍNH nó, đúng loại thao tác và nguồn; đơn đích lúc kiểm
            # (nếu có) không được bị đổi sang đơn khác
            cs = r.get("consent") or {}
            if cs.get("kind") != r["kind"] or cs.get("source") != r.get("source"):
                return None, "consent_missing"
            tgt_now = (target or {}).get("order_id") if (target or {}).get("type") == "order" else None
            if cs.get("target") and tgt_now and tgt_now != cs["target"]:
                return None, "consent_target_changed"
            # V45 (MP1) — kiểm tại biên ghi, trước order.update: đơn sắp ghi phải là đơn của CĂN CỨ của khách (mã đơn / sản phẩm /
            # size–màu / focus / đồng ý đề nghị cho đơn đó / đơn duy nhất do executor xác nhận trên order.status của lượt)
            if r.get("target_block"):
                return None, r["target_block"]
            basis = r.get("target_basis") if r.get("target") else ("single_order" if unique_target and not r.get("target_ambiguous") else None)
            if basis not in TARGET_BASES:
                return None, "target_basis_missing"
            if r.get("target") and tgt_now and r["target"].get("order_id") != tgt_now:
                return None, "target_basis_mismatch"
            if r.get("target") is None:
                r["target_basis"] = basis
            if kind == "change_order_address":
                # V48: payload địa chỉ phải đúng binding của CHÍNH request, đúng đơn lúc gắn (nếu đã có)
                b = r.get("addr") or {}
                if not b.get("value"):
                    return None, "address_unbound"
                if b.get("status", "valid") != "valid":
                    return None, "address_suspended"          # V49: xung đột chưa giải quyết
                if address is None or fold(str(address)) != fold(str(b["value"])):
                    return None, "address_binding_mismatch"
                if b.get("order_id") and tgt_now and b["order_id"] != tgt_now:
                    return None, "address_binding_order"
                if not b.get("order_id") and tgt_now:
                    b["order_id"] = tgt_now
        if kind == "callback":
            pass                                                # gọi lại không có đơn / sản phẩm đích; giờ hẹn là nội dung yêu cầu
        elif r["target"] is None:
            same_turn_order = kind == "place_order" and r["turn"] == self.turn
            if target is None or not (same_turn_order or unique_target):
                return None, "target_unresolved"
        elif target is not None and not _same_target(r["target"], target):
            return None, "target_mismatch"
        # so revision chỉ khi đồng ý có TỪ TRƯỚC lần thực thi này (yêu cầu lượt trước, hoặc "ok" cho đề nghị đã nêu): nội dung khách
        # đã nghe khác nội dung sắp ghi → không dùng đồng ý cũ. Khách nói yêu cầu và thực thi cùng lượt thì revision là chính lượt này.
        prior = r["turn"] < self.turn or str(r.get("source", "")).startswith("accept:") or bool(r.get("bound"))
        if prior and r.get("revision") and revision and _revision_changed(r["revision"], revision, r["turn"]):
            return None, "revision_changed"
        cond = r.get("condition")
        if cond and kind == "callback" and cond["type"] == "time":
            cond = None                                         # giờ hẹn là nội dung của chính yêu cầu gọi lại, không phải điều kiện
        if cond:
            if cond["type"] == "stock":
                if in_stock is not True:
                    return None, "condition_pending"        # chưa có kết quả tồn kho xác nhận trong lượt
            elif cond["type"] == "price_max" and cond.get("max_vnd") and total_vnd is not None:
                if total_vnd > cond["max_vnd"]:
                    return None, "condition_unmet"
            else:
                return None, "condition_pending"            # chờ người nhà / thời điểm / điều kiện code không tự đánh giá được
        if r["target"] is None and target is not None:
            r["target"] = target
            self._event("bound", id=r["id"], target=self._target_name(target))
        if revision and not prior:
            r["revision"] = revision        # thực thi ngay trong lượt khách đồng ý: revision = đúng giá / số lượng vừa báo
        self.last_blocked = None
        return r, "ok"

    def begin(self, r):
        r["status"] = "in_flight"
        self._event("in_flight", id=r["id"])

    def settle(self, r, status, detail=None):
        """status: confirmed_success | confirmed_failure | unresolved | partial (theo tool_outcome)."""
        r["status"] = STATUS_OF.get(status, status)
        if detail:
            r["outcome"] = detail
        self._event("settled", id=r["id"], status=r["status"])
        if settings.planner_variant == "b2_jev" and r["kind"] == "place_order" and status != "confirmed_failure" \
                and not (detail or {}).get("continuation_of"):
            self._orders_changed(r)                             # V48: tiếp tục / bổ sung đơn đã có không phải đơn mới

    def _orders_changed(self, r):
        """V47 (I2): cuộc gọi vừa (có thể) tạo thêm đơn → "đơn đang nói đến" (order_focus) hết hiệu lực; yêu cầu thao tác đơn chưa
        thực hiện mà đơn đích chỉ lấy từ focus → bỏ đơn đích (executor hỏi lại đơn nào)."""
        if self.order_focus:
            self._event("order_focus_cleared", why="orders_changed")
            self.order_focus = None
        for x in self.items:
            if x["kind"] in ORDER_KINDS and x["status"] in ACTIVE and x.get("target_basis") == "focus":
                x["target"], x["target_basis"], x["target_ambiguous"] = None, None, True
                self._event("focus_target_dropped", id=x["id"], by=r["id"])

    def has_active(self, kind):
        return any(r["status"] in ACTIVE and r["kind"] == kind for r in self.items)

    def done_orders_ok(self):
        """Có yêu cầu đặt hàng đã thực hiện trong cuộc (để bổ sung địa chỉ còn thiếu của chính đơn đó không cần yêu cầu mới)."""
        return any(r["kind"] == "place_order" and r["status"] in ("done", "partial") for r in self.items)

    def _event(self, ev, **kw):
        self.events.append({"event": ev, **kw})

    def trace(self):
        return {"hold": self.hold, "events": list(self.events), "proposal": (self.proposal or {}).get("goal"),
                **({"truncated_candidates": self.truncated} if self.truncated else {}),
                "items": [{k: (self._target_name(v) if k in ("target", "inherit") else v) for k, v in r.items() if k != "evidence"}
                          for r in self.items[-8:]]}


def _same_target(a, b):
    """Đúng đối tượng: đơn → cùng mã đơn; sản phẩm → cùng tập sản phẩm, và biến thể đã chốt (size/màu) phải trùng chính xác."""
    if a.get("type") != b.get("type"):
        return False
    if a["type"] == "order":
        return a.get("order_id") == b.get("order_id")
    ma = {_parent(x): x for x in a.get("skus") or ()}
    mb = {_parent(x): x for x in b.get("skus") or ()}
    if set(ma) != set(mb):
        return False
    return all(not (_is_variant(ma[p]) and _is_variant(mb[p])) or ma[p] == mb[p] for p in ma)


def _norm_units(rev):
    """Đơn vị chuẩn hóa: [[SKU cha, giá], ...] (hai máy cùng SKU khác giá là hai đơn vị khác nhau)."""
    return sorted([_parent(u[0]), u[1]] for u in rev.get("units") or [])


def _said_since(src, turn):
    """Nguồn 'customer:tN' với N ≥ lượt mở yêu cầu = khách tự nói giá trị đó sau khi yêu cầu (không phải thay đổi ngầm)."""
    s = str(src or "")
    if not s.startswith("customer:t"):
        return False
    try:
        return int(s[len("customer:t"):]) >= int(turn or 0)
    except ValueError:
        return False


def _revision_changed(old, new, since_turn=None):
    ou, nu = _norm_units(old), _norm_units(new)
    if ou and nu and ou != nu:
        return True                     # giá / phân bổ KM / số đơn vị khác nội dung khách đã nghe
    if old.get("qty") and new.get("qty") and old["qty"] != new["qty"]:
        return True
    if old.get("new_variant") and new.get("new_variant") and old["new_variant"] != new["new_variant"]:
        return True
    from harness.textnorm import fold
    for k in ("payment", "address"):    # 9.2: thanh toán / địa chỉ đổi mà KHÔNG phải do khách nói từ lượt mở yêu cầu
        o, n = old.get(k) or {}, new.get(k) or {}
        if o.get("value") and n.get("value") and fold(str(o["value"])) != fold(str(n["value"])) \
                and not _said_since(n.get("src"), since_turn):
            return True
    return False
