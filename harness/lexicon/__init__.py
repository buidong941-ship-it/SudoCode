"""Lexicon nhận biết slot (PLAN-2026-11-01 mục A-L) — cue nằm trong file dữ liệu `slots.json`, không nhồi regex vào code.

Mỗi entry (trong `slots.<slot>.entries`):
    id          duy nhất, vd "address.neg.giao_khi_nao"
    kind        cue      chỉ báo "câu có thể mang slot" → chặn chứng nhận rỗng, mở cổng LLM (không tự đặt giá trị)
                value    cue đủ chắc để luật đặt `slot = value` (slot dạng nhãn: payment, blocker) khi luật chưa có
                trigger  mở rộng điều kiện kích hoạt của luật có parser riêng (callback_requested cần ngày giờ)
                negative ngữ cảnh phủ định: luật đã đặt slot nhưng câu khớp mẫu này → bỏ slot
                         (`drop_if_value_in_match`: chỉ bỏ khi giá trị slot nằm trong đoạn khớp)
    pattern     regex khớp trên chuỗi đã fold() (bỏ dấu, chữ thường) — đầu vào ASR mất dấu vẫn khớp
    value       (kind=value) giá trị đặt cho slot
    examples    [{"text": câu, "expect": {slot: giá trị | null}}] — tests/lexicon_check.py chạy luật trên từng câu;
                mỗi entry cần ≥1 câu entry có tác dụng và ≥1 phản ví dụ
    source      nguồn cue (vd "claude-synth-b1", "ref:hcmut-ura", "dev:BTCL-047", "demo C.6 (LOI-2026-11-01 L1)")
    added       ngày thêm · added_by · status (proposed | approved | rejected) · reviewed_by

`abbreviations`: bảng viết tắt / teencode → dạng đầy đủ, áp lên câu khách TRƯỚC khi chạy luật (chỉ trong extractor).

Chỉ entry `approved` được dùng lúc chạy. `LEXICON_INCLUDE=proposed` nạp thêm entry `proposed` để đo thử trước khi duyệt
(chỉ dùng khi đo, không dùng cho cấu hình nộp bài). Duyệt bằng `python scripts/lexicon_review.py`.
"""
import json
import os
import re
from functools import lru_cache

from harness.textnorm import fold

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slots.json")
KINDS = ("cue", "value", "trigger", "negative")
STATUSES = ("proposed", "approved", "rejected")


def _include():
    v = (os.environ.get("LEXICON_INCLUDE") or "approved").lower()
    return {"approved"} if v == "approved" else {"approved", "proposed"} if v == "proposed" else {"approved", "proposed", "rejected"}


def load_raw(path=PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=4)
def _compiled(path, include):
    data = load_raw(path)
    out = {"entries": [], "abbrev": []}
    for slot, spec in (data.get("slots") or {}).items():
        for e in spec.get("entries") or []:
            if e.get("status") in include:
                out["entries"].append({**e, "slot": slot, "rx": re.compile(e["pattern"])})
    for a in data.get("abbreviations") or []:
        if a.get("status") in include:
            out["abbrev"].append((re.compile(r"(?<![\w\d])" + re.escape(a["from"]) + r"(?![\w\d])", re.I), a["to"]))
    return out


def compiled(path=PATH):
    return _compiled(path, frozenset(_include()))


def reload():
    _compiled.cache_clear()


def normalize(text, path=PATH):
    """Thay viết tắt / teencode đã duyệt (ko → không, đc → được, ck → chuyển khoản…). Không đụng số tiền (500k)."""
    for rx, to in compiled(path)["abbrev"]:
        text = rx.sub(to, text)
    return text


def entries(slot=None, kind=None, path=PATH):
    return [e for e in compiled(path)["entries"] if (slot is None or e["slot"] == slot) and (kind is None or e["kind"] == kind)]


def cue_hit(text_fold, path=PATH):
    """Có cue / value / trigger nào khớp không (cho chứng nhận rỗng và cổng LLM). → id entry đầu tiên khớp, hoặc None."""
    for e in compiled(path)["entries"]:
        if e["kind"] in ("cue", "value", "trigger") and e["rx"].search(text_fold):
            return e["id"]
    from harness import improve_hook               # mục E: cue đã duyệt trong improve/approved (tắt mặc định)
    for cid, _slot, rx in improve_hook.cue_patterns():
        if rx.search(text_fold):
            return cid
    return None


def trigger(slot, text_fold, path=PATH):
    return any(e["rx"].search(text_fold) for e in entries(slot, "trigger", path))


def apply(text, out, path=PATH, hits=None):
    """Áp entry value / negative lên kết quả luật `out` (dict slot → giá trị). Trả `out` (sửa tại chỗ).
    `hits` (list) nhận id các entry đã tác động, để ghi trace."""
    f = fold(text)
    negs = {}
    for e in entries(kind="negative", path=path):
        m = e["rx"].search(f)
        if m:
            negs.setdefault(e["slot"], []).append((e, m))
    for slot, lst in negs.items():
        if slot not in out:
            continue
        for e, m in lst:
            if e.get("drop_if_value_in_match") and fold(str(out[slot])) not in m.group(0):
                continue
            out.pop(slot, None)
            if hits is not None:
                hits.append(e["id"])
            break
    for e in entries(kind="value", path=path):
        if e["slot"] in out or e["slot"] in negs:
            continue
        if e["rx"].search(f):
            out[e["slot"]] = e["value"]
            if hits is not None:
                hits.append(e["id"])
    return out


def validate(data):
    """Lỗi cấu trúc của slots.json (rỗng = hợp lệ). tests/lexicon_check.py gọi hàm này."""
    errs, seen = [], set()
    for slot, spec in (data.get("slots") or {}).items():
        for e in spec.get("entries") or []:
            eid = e.get("id")
            if not eid or eid in seen:
                errs.append(f"{slot}: id trống hoặc trùng ({eid})")
            seen.add(eid)
            if e.get("kind") not in KINDS:
                errs.append(f"{eid}: kind phải thuộc {KINDS}")
            if e.get("status") not in STATUSES:
                errs.append(f"{eid}: status phải thuộc {STATUSES}")
            if e.get("kind") == "value" and "value" not in e:
                errs.append(f"{eid}: kind=value cần trường value")
            for k in ("pattern", "source", "added", "added_by"):
                if not e.get(k):
                    errs.append(f"{eid}: thiếu {k}")
            try:
                rx = re.compile(e.get("pattern") or "")
                if rx.pattern != rx.pattern.lower() or fold(rx.pattern) != rx.pattern:
                    errs.append(f"{eid}: pattern phải viết dạng fold() (không dấu, chữ thường)")
            except re.error as ex:
                errs.append(f"{eid}: regex lỗi {ex}")
            ex = e.get("examples") or []
            if len(ex) < 2:
                errs.append(f"{eid}: cần ≥2 câu ví dụ (một câu entry có tác dụng, một phản ví dụ)")
            if e.get("status") == "approved" and not e.get("reviewed_by"):
                errs.append(f"{eid}: approved phải có reviewed_by")
    for a in data.get("abbreviations") or []:
        if not a.get("from") or not a.get("to") or a.get("status") not in STATUSES:
            errs.append(f"viết tắt {a}: thiếu from/to/status")
    return errs
