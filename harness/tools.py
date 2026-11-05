"""Lớp tool: bọc eval/mock_tools.py của BTC (logic tham chiếu) với đúng tên tool + tham số trong schemas/tools.schema.json.

Mọi lời gọi đi qua ToolBox.call() để: (1) gắn `on` = ngày của cuộc gọi, (2) ghi lại {name, args, result} cho trace,
(3) bắt lỗi tool (fallback), (4) reset trạng thái mock giữa các kịch bản.
Transport (TOOL_TRANSPORT / --transport): `mcp` → gọi qua MCP server `mcp-commerce` (mcp_servers/commerce_server.py);
`direct` → gọi hàm mock trong tiến trình. Hai đường cho cùng kết quả (tests/mcp_parity.py kiểm tra).
Dữ liệu catalog TĨNH (tên, biến thể, danh sách KM, ngày nghỉ) vẫn đọc trực tiếp để hiểu câu nói của khách;
mọi thao tác có trạng thái hoặc phụ thuộc ngày (giá, tồn kho, đơn, lịch, chuyển máy, tra CRM) đi qua tool.
"""
import importlib.util
import os
import re
import time

from core.config import settings
from harness.textnorm import fold

_spec = importlib.util.spec_from_file_location("mock_tools", os.path.join(settings.btc_dir, "eval", "mock_tools.py"))
mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt)

DATED = {"inventory.check", "pricing.get_quote", "order.create", "order.update"}


class ToolBox:
    def __init__(self, today):
        self.today = today
        self.log = []

    @staticmethod
    def reset_world():
        if settings.tool_transport == "mcp":
            from harness.mcp_client import connection
            connection("commerce").call("world.reset", {})
            return
        mt._ORDERS.clear(); mt._CALLBACKS.clear(); mt._TICKETS.clear(); mt._ONCE_USED.clear()

    def call(self, name, **args):
        args = {k: v for k, v in args.items() if v is not None}
        if name in DATED:
            args.setdefault("on", self.today)
        t0 = time.perf_counter()
        try:
            if settings.tool_transport == "mcp":
                from harness.mcp_client import McpToolError, connection
                try:
                    res = connection("commerce").call(name, args)
                except McpToolError as e:
                    res = {"error": "tool_exception", "detail": str(e)}
            else:
                res = mt.TOOLS[name](**args)
        except Exception as e:
            res = {"error": "tool_exception", "detail": f"{type(e).__name__}: {e}"}
        self.log.append({"name": name, "args": args, "result": res, "ms": int((time.perf_counter() - t0) * 1000)})
        return res

    def take_log(self):
        out, self.log = self.log, []
        return out


NAME_PREFIXES = ["máy lọc không khí", "máy lọc nước", "nồi chiên không dầu", "quạt đứng", "quạt tháp", "giày chạy bộ",
                 "giày sneaker", "giày trekking", "áo khoác gió", "áo phao lông vũ", "máy hút sữa điện đôi", "xe đẩy gấp gọn",
                 "xe đẩy 2 chiều", "máy hâm sữa", "máy tiệt trùng sấy khô", "bình sữa", "ghế ngồi ô tô cho bé"]
SPOKEN = {"airpure": ["e pia", "ea pia", "air pure"], "karofi": ["ca rô phi", "ka rô phi"], "kangaroo": ["kang ga ru"],
          "runlite": ["ran lai", "run lai"], "xiaomi": ["xiao mi", "sao mi"], "smart": ["sờ mát", "xờ mát"], "pro": ["pờ rô"], "sunhouse": ["san hao"],
          "panasonic": ["pa na so níc"], "philips": ["phi líp"], "spectra": ["spéc tra"], "medela": ["mê đê la"]}
COLORS = {"den": ["đen"], "trang": ["trắng"], "navy": ["navy", "xanh navy", "xanh than"], "xam": ["xám", "ghi"],
          "be": ["be", "kem"], "do": ["đỏ"], "xanh": ["xanh"]}


def _aliases(p):
    name = p["name"].lower()
    short = name
    for pre in NAME_PREFIXES:
        if short.startswith(pre + " "):
            short = short[len(pre) + 1:]
            break
    al = {name, short, p["sku"].lower()}
    for brand, forms in SPOKEN.items():
        for a in list(al):
            if brand in a:
                al |= {a.replace(brand, f) for f in forms}
    b = p["brand"].lower()
    if b in short and not short.startswith(b):
        al.add(short[short.index(b):])
    for a in list(al):
        slim = re.sub(r"\b(smart|air purifier|inverter)\b\s*", "", a).strip()
        if slim != a and len(slim) >= 6:
            al.add(slim)
    for brand, forms in SPOKEN.items():
        for a in list(al):
            if brand in a:
                al |= {a.replace(brand, f) for f in forms}
    return {fold(a) for a in al if len(a) >= 3}


_INDEX = sorted(((a, p["sku"]) for p in mt.PRODUCTS for a in _aliases(p)), key=lambda x: -len(x[0]))


_DIGITS = {"khong": "0", "mot": "1", "hai": "2", "ba": "3", "bon": "4", "nam": "5", "sau": "6", "bay": "7", "tam": "8", "chin": "9", "muoi": "10"}


def _spoken_digits(f):
    return " ".join(_DIGITS.get(w, w) for w in f.split())


_DIGIT_WORD = {"0": "khong", "1": "mot", "2": "hai", "3": "ba", "4": "bon", "5": "nam", "6": "sau", "7": "bay", "8": "tam", "9": "chin"}
_LEX_INDEX = {"key": None, "index": None}


def _token_variants(tok):
    """D51 (tầng tra SP): cách ASR viết một mã model, sinh TỪ CATALOG (không theo câu cụ thể).
    's1' → 'smot' / 's 1'; '4l' → 'bonl' / '4 l'; '6.2l' → '6 cham hail' / '6 cham 2 l'. Chỉ chữ số đơn 0–9 mới có dạng chữ."""
    m = re.fullmatch(r"([a-z]*)(\d)(?:\.(\d))?([a-z]*)", tok)
    if not m:
        return [tok]
    pre, a, b, suf = m.groups()
    if b is None:
        glued = pre + _DIGIT_WORD[a] + suf
        spaced = " ".join(x for x in (pre, a, suf) if x)
        return list(dict.fromkeys([tok, glued, spaced]))
    return list(dict.fromkeys([tok, f"{pre}{a} cham {_DIGIT_WORD[b]}{suf}".strip(), " ".join(x for x in (pre + a, "cham", b, suf) if x)]))


def _lexicon_index():
    """Chỉ mục alias mở rộng khi PRODUCT_LEXICON=1: thêm cách đọc phiên âm thương hiệu (harness/lexicon/products.json, mục
    approved) và dạng ASR của mã model. Sắp alias dài trước như _INDEX."""
    from harness import improve_hook               # D52: cách đọc do người duyệt qua improve/ (loại product_alias)
    path = os.path.join(os.path.dirname(__file__), "lexicon", "products.json")
    extra = improve_hook.product_aliases()
    mtime = os.path.getmtime(path) if os.path.exists(path) else None
    key = (mtime, tuple(e["id"] for e in extra))
    if _LEX_INDEX["key"] == key and _LEX_INDEX["index"] is not None:
        return _LEX_INDEX["index"]
    import json
    lex = json.load(open(path, encoding="utf-8")) if mtime else {}
    spoken = {b: list(v) for b, v in SPOKEN.items()}
    for e in lex.get("spoken_brands", []) + [dict(x, status="approved") for x in extra]:
        if e.get("status") == "approved":
            spoken.setdefault(e["brand"].lower(), []).extend(e["forms"])
    # giữ NGUYÊN thứ tự của _INDEX (alias dài bằng nhau thì SP đứng trước trong catalog thắng, vd AirPure Pro trước
    # màng lọc AirPure Pro); alias mới thêm sau, sort ổn định theo độ dài → không đổi kết quả của câu không có cách đọc mới
    idx = dict.fromkeys(_INDEX)
    for p in mt.PRODUCTS:
        base = set(_aliases(p))
        name = p["name"].lower()
        raw = {name} | {name[len(pre) + 1:] for pre in NAME_PREFIXES if name.startswith(pre + " ")}
        for a in list(raw):
            for brand, forms in spoken.items():
                if brand in a:
                    raw |= {a.replace(brand, f) for f in forms}
        for a in raw | base:
            fa = fold(a)
            toks = fa.split()
            if not 1 <= len(toks) <= 8:
                continue
            variants = [""]
            for t in toks:
                variants = [(v + " " + x).strip() for v in variants for x in _token_variants(t)][:16]
            for v in variants:
                if len(v) >= 3:
                    idx.setdefault((v, p["sku"]))
    _LEX_INDEX.update(key=key, index=sorted(idx, key=lambda x: -len(x[0])))
    return _LEX_INDEX["index"]


def _prefer_bundle(f, out):
    """D51 (N05): câu có "combo / trọn bộ" và nhắc SP nằm trong một bundle → chọn SKU bundle (attributes.bundle_of)."""
    if not re.search(r"\b(combo|tron bo|tron goi)\b", f):
        return out
    for p in mt.PRODUCTS:
        parts = (p.get("attributes") or {}).get("bundle_of") or []
        if parts and (p["sku"] in out or any(mt._parent(s)[0] and mt._parent(s)[0]["sku"] in parts for s in out)):
            return [p["sku"]] + [s for s in out if s != p["sku"] and not (mt._parent(s)[0] and mt._parent(s)[0]["sku"] in parts)]
    return out


def find_products(text):
    f = " " + _spoken_digits(fold(text)) + " "
    hits, used = [], []
    index = _lexicon_index() if settings.product_lexicon else _INDEX
    for alias, sku in index:
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", f):
            if any(s <= m.start() < e for s, e in used):
                continue
            used.append((m.start(), m.end())); hits.append((m.start(), sku))
    seen, out = set(), []
    for _, s in sorted(hits):
        if s not in seen:
            seen.add(s); out.append(s)
    return _prefer_bundle(f, out) if settings.product_lexicon else out


def find_variant(sku, text, fallback_size=None, fallback_color=None):
    p, _ = mt._parent(sku)
    if not p or not p["variants"]:
        return sku
    from harness.extractor import ADDRESS_RX
    t = ADDRESS_RX.sub(" ", text).lower()
    sizes = {str(v["size"]).upper() for v in p["variants"]}
    m = re.search(r"(?:size|sai z|cỡ|số)\s*([0-9]{1,3}|xs|s|m|l|xl|xxl)\b", t)
    if not m:
        m = next((x for x in re.finditer(r"\b(3[5-9]|4[0-6])\b", t) if x.group(1) in sizes), None)
    size = m.group(1).upper() if m else fallback_size
    color = find_color(text) or fallback_color
    cands = [v for v in p["variants"] if (size is None or str(v["size"]).upper() == str(size).upper())
             and (color is None or v["color"] == color)]
    return cands[0]["variant_sku"] if len(cands) == 1 else (cands[0]["variant_sku"] if cands and size and color else None)


def find_color(text, prefix=""):
    """D31: câu CÓ DẤU thì so trên bản có dấu ("mẫu đó" không phải "màu đỏ", "em bé" không phải màu be);
    câu mất dấu (ASR/teencode) vẫn so trên bản fold như cũ."""
    import unicodedata
    ft, best = fold(text), (0, None)
    lt = unicodedata.normalize("NFC", (text or "").lower())
    accented = ft != re.sub(r"\s+", " ", lt).strip()
    pre = (r"(?:màu|mau)\s+" if accented else prefix) if prefix else ""
    for code, words in COLORS.items():
        for w in words:
            pat = pre + re.escape(w.lower() if accented else fold(w))
            if re.search(r"(?<![\wÀ-ỹ])" + pat + r"(?![\wÀ-ỹ])", lt if accented else ft) and len(w) > best[0]:
                best = (len(w), code)
    return best[1]


def product_name(sku):
    p, v = mt._parent(sku)
    if not p:
        return sku
    return p["name"] + (f" size {v['size']} màu {v['color']}" if v else "")


def find_by_model_token(text, family_sku):
    m = re.search(r"\b(?:mau|model|loai|ban)\s+([a-z0-9][a-z0-9-]{0,5})\b", fold(text))
    fam, _ = mt._parent(family_sku) if family_sku else (None, None)
    if not m or not fam:
        return None
    tok = m.group(1)
    for p in mt.PRODUCTS:
        if p["brand"] == fam["brand"] and p["category"] == fam["category"] and fold(p["name"]).split()[-1] == tok:
            return p["sku"]
    return None


def public_view(result):
    if isinstance(result, dict):
        return {k: public_view(v) for k, v in result.items() if not str(k).startswith("_")}
    if isinstance(result, list):
        return [public_view(x) for x in result]
    return result
