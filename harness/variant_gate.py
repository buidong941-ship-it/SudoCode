"""Bước 2 (QUYET-DINH-KIEN-TRUC-SAU-UI5, 18/11): điều kiện PHÁT GIÁ theo biến thể. Chỉ dùng khi B2_TWO_TIER (candidate).

Tách việc ĐỌC báo giá khỏi việc CÔNG BỐ giá: khi giá bán / điều kiện KM phụ thuộc thuộc tính biến thể (size …) mà khách chưa xác định,
không công bố giá mẫu gốc; chỉ hỏi thuộc tính CÓ ảnh hưởng và CÒN thiếu. Mọi biến thể liên quan cùng giá + cùng điều kiện → trả lời
ngay (không hỏi). Khách nêu giá trị không có trong catalog → nói rõ phần thiếu (không đoán).

"Ảnh hưởng" tính bằng code trên dữ liệu BTC (catalog/products.json + catalog/promotions.json qua eval/mock_tools), không theo tên SKU /
câu mẫu / mã kịch bản: chữ ký của một biến thể = (price_delta_vnd, có bị KM đang hiệu lực loại trừ theo size không). Thuộc tính f có ảnh
hưởng khi tập chữ ký khác nhau giữa các giá trị của f trong các biến thể còn phù hợp với điều khách đã nói."""
from harness.tools import mt, product_name

FIELDS = ("size", "color")
FIELD_VI = {"size": "size", "color": "màu"}


def _norm(v):
    return str(v).strip().lower() if v is not None else None


def _promos_excluding(p, today):
    """Các KM đang hiệu lực ngày `today` áp cho sản phẩm và có điều kiện loại trừ size → {size đã chuẩn hóa}."""
    out = set()
    for pr in mt.PROMOS:
        applies = p["sku"] in (pr.get("applies_to") or []) or any(p["category"].startswith(c) for c in pr.get("applies_to_categories") or [])
        if not applies:
            continue
        if today and ((pr.get("start") and today < pr["start"]) or (pr.get("end") and today > pr["end"])):
            continue
        for x in (pr.get("conditions") or {}).get("exclude_variant_size") or []:
            out.add(_norm(x))
    return out


def _sig(v, excl):
    return (int(v.get("price_delta_vnd") or 0), _norm(v.get("size")) in excl)


def known_values(s, text):
    """Giá trị thuộc tính khách đã nêu: slot của bộ hiểu trong lượt (ưu tiên) rồi known của cuộc gọi."""
    said = (getattr(s, "u_turn", None) or {}).get("slots") or {}
    return {f: (said.get(f) if said.get(f) is not None else (s.known or {}).get(f)) for f in FIELDS}


def analyze(s, sku, text):
    """→ dict state ∈ no_variants | resolved | uniform | needs | unavailable.
    resolved/uniform: "sku" = SKU dùng để báo giá (biến thể đã rõ / đại diện của nhóm cùng giá-điều kiện / SKU cha khi mọi biến thể như
    nhau); needs: "fields" = thuộc tính có ảnh hưởng còn thiếu (thứ tự FIELDS), "options" = giá trị hợp lệ; unavailable: khách nêu giá trị
    không có, "options" = giá trị có."""
    p, v = mt._parent(sku) if sku else (None, None)
    if not p or not p.get("variants"):
        return {"state": "no_variants", "sku": sku}
    if v:
        return {"state": "resolved", "sku": sku}
    r = s._resolve_variant(p["sku"], text)
    if r and r != p["sku"]:
        return {"state": "resolved", "sku": r}
    vs = p["variants"]
    excl = _promos_excluding(p, getattr(s, "today", None))
    known = known_values(s, text)
    rel = [x for x in vs if all(known[f] is None or _norm(x.get(f)) == _norm(known[f]) for f in FIELDS)]
    base = {"target": p["sku"], "name": product_name(p["sku"]), "known": {f: known[f] for f in FIELDS if known[f] is not None}}
    if not rel:
        bad = [f for f in FIELDS if known[f] is not None and _norm(known[f]) not in {_norm(x.get(f)) for x in vs}]
        return {**base, "state": "unavailable", "fields": bad or [f for f in FIELDS if known[f] is not None],
                "options": {f: sorted({str(x.get(f)) for x in vs}, key=_order) for f in (bad or FIELDS)}}
    sigs = {_sig(x, excl) for x in rel}
    if len(sigs) == 1:
        if len(rel) == len(vs):
            return {**base, "state": "uniform", "sku": p["sku"], "basis": "all_variants_same_price_and_conditions"}
        return {**base, "state": "uniform", "sku": rel[0].get("variant_sku") or p["sku"], "basis": "relevant_variants_same"}
    fields = []
    for f in FIELDS:
        if known[f] is not None:
            continue
        by = {}
        for x in rel:
            by.setdefault(_norm(x.get(f)), set()).add(_sig(x, excl))
        if len({frozenset(z) for z in by.values()}) > 1:
            fields.append(f)
    basis = sorted({"price_delta" for x in rel if x.get("price_delta_vnd")} | ({"promo_excludes_size"} if excl else set()))
    return {**base, "state": "needs", "fields": fields, "basis": basis,
            "options": {f: sorted({str(x.get(f)) for x in rel}, key=_order) for f in fields}}


def _order(x):
    return (0, float(x)) if str(x).replace(".", "", 1).isdigit() else (1, str(x))


def withhold(s, sku, text):
    """Có phải giữ giá (không công bố) cho SKU này không → analysis | None."""
    a = analyze(s, sku, text)
    return a if a["state"] in ("needs", "unavailable") else None


def present(view, a):
    """Báo giá bằng SKU ĐẠI DIỆN (nhóm biến thể cùng giá + điều kiện, khách mới nêu một phần thuộc tính): tên chỉ nêu thuộc tính khách
    đã nói (không nêu màu / size tùy chọn của biến thể đại diện) và đánh dấu representative — agent không ghi biến thể này như lựa
    chọn của khách (D54 bỏ qua). Sửa tại chỗ, trả lại view."""
    if not isinstance(view, dict) or not a or a.get("state") != "uniform" or view.get("sku") == a.get("target"):
        return view
    view["representative"] = True
    view["name"] = a["name"] + "".join(f" {FIELD_VI.get(f, f)} {v}" for f, v in (a.get("known") or {}).items())
    return view
