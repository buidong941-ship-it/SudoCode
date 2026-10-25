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


def find_products(text):
    f = " " + _spoken_digits(fold(text)) + " "
    hits, used = [], []
    for alias, sku in _INDEX:
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", f):
            if any(s <= m.start() < e for s, e in used):
                continue
            used.append((m.start(), m.end())); hits.append((m.start(), sku))
    seen, out = set(), []
    for _, s in sorted(hits):
        if s not in seen:
            seen.add(s); out.append(s)
    return out


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
    ft, best = fold(text), (0, None)
    for code, words in COLORS.items():
        for w in words:
            if re.search(r"\b" + prefix + re.escape(fold(w)) + r"\b", ft) and len(w) > best[0]:
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
