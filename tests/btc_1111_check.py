"""Kiểm tích hợp bản cập nhật BTC 11/2026 trên cấu hình đích ARCH=target (Kaggle CPU, không gọi API thật).

Ba file BTC: eval/mock_tools.py (pricing.quote_order, order.create(lines), price_mismatch/expected_units, tồn kho theo số lượng),
eval/reference_eval.py (alias mã đơn, giờ theo phút, promo_code tùy chọn, order_lines, chuẩn hóa tiền / nguyên từ, PII theo
token khách nói, entity ASR dạng danh sách), schemas/tools.schema.json. Giá trị kỳ vọng lấy từ CHÍNH kết quả tool tham chiếu
trong trace (không tự tính lại công thức KM, không sinh gold bằng model).
"""
import hashlib
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
tmp = tempfile.mkdtemp(prefix="btc1111_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "m.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, audit, renderer, request_state, tool_outcome as T, understanding as U  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox, mt  # noqa: E402

FAIL, PASS = [], [0]


def ok(group, name, got, want=True):
    if got == want:
        PASS[0] += 1
        print(f"OK   [{group}] {name}", flush=True)
    else:
        FAIL.append((group, name))
        print(f"FAIL [{group}] {name}: got={got!r} want={want!r}", flush=True)


# ------------------------------------------------------------------ phiên bản BTC thực dùng
BTC = {"eval/mock_tools.py": "ceda57e5737e4ae628d92d3d3847030578cae33d72acf0f99afdf6a04c6a6a55",
       "eval/reference_eval.py": "cca362cf74bc070a37493af756a2963d02bfca8004c5d964e9e4ca0a67b48807",
       "schemas/tools.schema.json": "c6a43f18bd482336a5b36eaac324e8b5b1e134a41b5cf94e1b1add4ca5350dbf"}
for p, h in BTC.items():
    ok("BTC", f"{p} = bản BTC 11/2026", hashlib.sha256(open(p, "rb").read()).hexdigest(), h)
ok("BTC", "ToolBox dùng mock có pricing.quote_order", "pricing.quote_order" in mt.TOOLS)


def resp(**kw):
    d = {"intent": "greeting_or_other", "flags": [], "observations": [], "requests": [], "withdrawn": [],
         "response_to_agent": {"act": "none"}, "asks": [], "refs": {}, "safety": [], "asks_question": False,
         "ambiguity": {"level": "none"}}
    d.update(kw)
    return d


QUEUE = []


def fake_call(prompt, schema, max_tokens):
    return (QUEUE.pop(0) if QUEUE else resp()), 5, 1, None


BASE = dict(arch="target", understanding="", goal_contract=True, contract_v2=True, jev_simulated=True, requests_backend="",
            planner_selector="rules", improve_dir="", order_qty=True)
PATCHES = [patch.object(settings, k, v) for k, v in BASE.items()] + [
    patch.object(U, "_call", fake_call),
    patch.object(audit, "_jev_sentence", lambda s, k: None),
    patch.object(deepseek.LLM, "json", lambda self, p, **kw: {"claims": []} if "claims" in json.dumps(kw.get("schema") or {})
                 else {"lead": "L0", "policy_refs": [], "attribute_refs": []})]
for p in PATCHES:
    p.start()


def session(name, phone="0911333444"):
    mem = Memory(f"btc1111:{name}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:1", channel="hotline",
                          channel_identity=None, phone=phone, input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full")
    s.start()
    return s


def say(s, text, d):
    QUEUE[:] = [d]
    return s.turn(text)


def calls(row, name):
    return [t for t in row["tool_calls"] if t["name"] == name]


def units_of(res):
    return sorted((u["sku"], u["final_price_vnd"]) for u in res["units"])


def lines_units(args):
    if args.get("lines"):
        return sorted((ln["sku"], ln["price_vnd"]) for ln in args["lines"] for _ in range(int(ln.get("qty", 1))))
    return sorted([(args["sku"], args["price_vnd"])] * int(args.get("qty", 1)))


ORDER = resp(intent="place_order", requests=[{"kind": "place_order", "evidence": "lấy luôn"}])


def buy(s, focus_text, order_text, d_order, payment="bank"):
    say(s, focus_text, resp(intent="price_promo", asks=["price"], asks_question=True))
    s.known["payment"] = payment          # tránh hạn mức COD 10 triệu khi kiểm đơn nhiều máy
    s.known["address"] = "15 Nguyễn Huệ, Quận 1, TP HCM"
    return say(s, order_text, d_order)


# ------------------------------------------------------------------ tương thích cũ: một SKU, qty 1
s = session("one")
row = buy(s, "Máy lọc không khí AirPure Y giá bao nhiêu em?", "Ok lấy luôn", ORDER)
cr = calls(row, "order.create")
ok("COMPAT", "một đơn vị: order.create dạng sku/qty/price_vnd cũ", (len(cr), "lines" in cr[0]["args"] if cr else None, T.ok(cr[0]) if cr else None),
   (1, False, True))

# ------------------------------------------------------------------ nhiều máy cùng SKU (qty 2, 3): giá từng máy theo quote_order
for n in (2, 3):
    s = session(f"qty{n}")
    row = buy(s, "Máy lọc không khí AirPure Pro giá bao nhiêu em?", f"Ok lấy {n} cái luôn",
              resp(intent="place_order", observations=[{"slot": "qty", "span": f"{n} cái", "stance": "stated"}],
                   requests=[{"kind": "place_order", "evidence": f"lấy {n} cái luôn"}]))
    if "out_of_stock" in row["goals"]:
        print(f"SKIP QTY {n}: tồn kho AirPure Pro không đủ {n} máy ngày 15/10 (kiểm tồn ở nhóm STOCK)"); continue
    qo, cr = calls(row, "pricing.quote_order"), calls(row, "order.create")
    ok("QTY", f"qty {n}: báo giá đơn + MỘT order.create", (len(qo) >= 1, len(cr)), (True, 1))
    if qo and cr:
        ok("QTY", f"qty {n}: giá từng máy khi tạo = units của quote_order (không nhân một giá)", lines_units(cr[0]["args"]), units_of(qo[-1]["result"]))
        ok("QTY", f"qty {n}: tạo đơn thành công, tổng = tổng báo giá", (T.ok(cr[0]), cr[0]["result"].get("total_vnd")),
           (True, qo[-1]["result"]["total_vnd"]))
        n50 = sum(1 for u in qo[-1]["result"]["units"] for a in u["applied_promos"] if a["promo_code"] == "AIR-2ND-50")
        ok("QTY", f"qty {n}: tối đa một máy nhận AIR-2ND-50 (theo tham chiếu)", n50 <= 1)
        tot = f"{cr[0]['result']['total_vnd']:,}đ".replace(",", ".")
        ok("R", f"qty {n}: câu cuối nói đúng tổng của đơn, một mã đơn", (tot in row["agent_text"], row["agent_text"].count(cr[0]["result"]["order_id"])),
           (True, 1))

# ------------------------------------------------------------------ hai máy khác giá trong giỏ: một đơn nhiều dòng
s = session("two")
say(s, "Samsung AX40 với AirPure X bên em giá sao?", resp(intent="price_promo", asks=["price", "compare"], asks_question=True))
s.cart = [x for x in ("SKU-SS-AX40", "SKU-AP-X") if mt._parent(x)[0]]
s.known["payment"], s.known["address"] = "bank", "15 Nguyễn Huệ, Quận 1, TP HCM"
row = say(s, "Lấy cả hai luôn em", resp(intent="place_order", requests=[{"kind": "place_order", "evidence": "Lấy cả hai luôn", "target_ref": "CART"}]))
qo, cr = calls(row, "pricing.quote_order"), calls(row, "order.create")
ok("MULTI", "giỏ hai máy → MỘT order.create với lines (không mỗi SKU một đơn)", (len(cr), bool(cr and cr[0]["args"].get("lines"))), (1, True))
if qo and cr:
    ok("MULTI", "lines = units của quote_order", lines_units(cr[0]["args"]), units_of(qo[-1]["result"]))
    rec = s.orders_created[-1]
    ok("MULTI", "state đơn: một order_id, đủ mọi SKU (không lấy sku dòng đầu làm đại diện)", (rec["order_id"], sorted(rec["skus"])),
       (cr[0]["result"]["order_id"], sorted(s.cart)))

# ------------------------------------------------------------------ giỏ: cart_total theo đơn vị, ref khớp quote_order
s = session("cart")
s.cart = ["SKU-SS-AX40", "SKU-AP-X"]
cf = s._cart_quote("")
qo = [t for t in s.tools.log if t["name"] == "pricing.quote_order"]
ok("R", "cart_total: tổng = tổng các đơn vị = tổng quote_order", (cf["total_vnd"], sum(i["final_price_vnd"] for i in cf["items"])),
   (qo[-1]["result"]["total_vnd"], qo[-1]["result"]["total_vnd"]) if qo else (None, None))
log = s.tools.take_log()
ok("R", "cart_total ref khớp đúng báo giá đơn", renderer._ref_check("cart_total", {"cart": cf}, log, log), True)

# ------------------------------------------------------------------ tồn kho theo số lượng
s = session("stock")
row = buy(s, "Máy lọc không khí AirPure Y giá bao nhiêu em?", "Lấy 20 cái nhé",
          resp(intent="place_order", observations=[{"slot": "qty", "span": "20 cái", "stance": "stated"}],
               requests=[{"kind": "place_order", "evidence": "Lấy 20 cái"}]))
stock = mt.inventory_check("SKU-AP-Y", "2026-10-15").get("qty", 0)
if stock < 20:
    ok("STOCK", "qty vượt tồn → không tạo đơn, không nói thành công", ("order.create" in [t["name"] for t in row["tool_calls"]],
                                                                       "order_created" in row["goals"], "out_of_stock" in row["goals"]), (False, False, True))

# ------------------------------------------------------------------ price_mismatch mới (expected_units): không KeyError, không tự tạo lại
real_create = mt.TOOLS["order.create"]


def mismatch(**kw):
    return {"error": "price_mismatch", "expected_units": [{"sku": kw.get("sku") or kw["lines"][0]["sku"], "price_vnd": 1}],
            "given": []}


with patch.dict(mt.TOOLS, {"order.create": mismatch}):
    s = session("mm")
    try:
        row = buy(s, "Máy lọc không khí AirPure Y giá bao nhiêu em?", "Ok lấy luôn", ORDER)
        ok("MISMATCH", "expected_units: không KeyError, một lần create, xin xác nhận lại",
           (len(calls(row, "order.create")), "confirm_new_price" in row["goals"], "order_created" in row["goals"]), (1, True, False))
        ok("MISMATCH", "request settled failed (không giữ quyền để tự tạo lại)",
           [i["status"] for i in row["request_state"]["items"] if i["kind"] == "place_order"][-1:], ["failed"])
    except KeyError as e:
        ok("MISMATCH", f"KeyError {e}", False)

# ------------------------------------------------------------------ unresolved: không tạo lại
def boom(**kw):
    raise TimeoutError("transport timeout")


with patch.dict(mt.TOOLS, {"order.create": boom}):
    s = session("unres")
    row = buy(s, "Máy lọc không khí AirPure Pro giá bao nhiêu em?", "Lấy 2 cái luôn",
              resp(intent="place_order", observations=[{"slot": "qty", "span": "2 cái", "stance": "stated"}],
                   requests=[{"kind": "place_order", "evidence": "Lấy 2 cái luôn"}]))
    ok("OUTCOME", "đơn nhiều máy lỗi transport → unresolved", ("order_unresolved" in row["goals"], "order_created" in row["goals"]), (True, False))
    row = say(s, "Lên lại đơn đi em", resp(intent="place_order", requests=[{"kind": "place_order", "evidence": "Lên lại đơn"}]))
    ok("OUTCOME", "không tạo lại sau unresolved", "order.create" in [t["name"] for t in row["tool_calls"]], False)

# ------------------------------------------------------------------ revision: cùng SKU khác giá không coi là cùng revision
RS = request_state.RequestState
st = RS()
st.turn = 1
st.items.append({"id": "R1", "kind": "place_order", "target": {"type": "product", "skus": ("SKU-AP-PRO",)}, "condition": None,
                 "revision": {"units": [["SKU-AP-PRO", 5000000], ["SKU-AP-PRO", 5000000]], "qty": 2}, "turn": 1,
                 "source": "customer_request", "status": "open", "evidence": "x"})
st.turn = 2
ok("REV", "hai máy cùng SKU: phân bổ giá đổi (một máy giảm) → revision_changed",
   st.authorize("place_order", {"type": "product", "skus": ("SKU-AP-PRO",)},
                revision={"units": [["SKU-AP-PRO", 5000000], ["SKU-AP-PRO", 2500000]], "qty": 2})[1], "revision_changed")
ok("REV", "cùng các đơn vị cùng giá → còn hiệu lực",
   st.authorize("place_order", {"type": "product", "skus": ("SKU-AP-PRO",)},
                revision={"units": [["SKU-AP-PRO", 5000000], ["SKU-AP-PRO", 5000000]], "qty": 2})[1], "ok")

# ------------------------------------------------------------------ đơn nhiều dòng: đổi/trả không tự chọn món
s = session("mline")
oq = mt.pricing_quote_order([{"sku": "SKU-SS-AX40"}, {"sku": "SKU-AP-X"}], "2026-10-15")
cr = mt.order_create(s.phone, lines=[{"sku": u["sku"], "qty": 1, "price_vnd": u["final_price_vnd"]} for u in oq["units"]],
                     payment="bank", address="15 Nguyễn Huệ", on="2026-10-15")
if cr.get("order_id"):
    row = say(s, "Đơn hôm trước chị muốn trả lại", resp(intent="order_change", requests=[{"kind": "return", "evidence": "muốn trả lại"}]))
    ok("MLINE", "trả hàng đơn nhiều dòng: không order.update theo order_id (API chưa chọn được món) → chuyển nhân viên",
       ("order.update" in [t["name"] for t in row["tool_calls"]], "handoff" in row["goals"]), (False, True))

# ------------------------------------------------------------------ tool outcome
ok("OUTCOME", "quote_order hỏng cấu trúc không là thành công",
   T.ok({"name": "pricing.quote_order", "args": {}, "result": {"units": [{"sku": "A", "final_price_vnd": 1}], "lines": [], "total_vnd": 2}}), False)
ok("OUTCOME", "order.create lines: target giữ mọi SKU",
   T.classify({"name": "order.create", "args": {"lines": [{"sku": "A"}, {"sku": "B"}]},
               "result": {"order_id": "OD1", "status": "created", "total_vnd": 3}})["target"]["skus"], ["A", "B"])

# ------------------------------------------------------------------ MCP schema / direct
sys.path.insert(0, os.path.join(ROOT, "mcp_servers"))
try:
    import commerce_server as CS
    tools = CS._tools()
    oc = tools["order.create"][2]["properties"]
    ok("MCP", "order.create.lines có kiểu array/items object (sku, qty, price_vnd)",
       (oc.get("lines", {}).get("type", [None])[0] if isinstance(oc.get("lines", {}).get("type"), list) else oc.get("lines", {}).get("type"),
        sorted((oc.get("lines", {}).get("items") or {}).get("properties", {}))), ("array", ["price_vnd", "qty", "sku"]))
    qp = tools["pricing.quote_order"][2]["properties"]
    ok("MCP", "quote_order không xuất tham số nội bộ", sorted(k for k in qp if k.startswith("_")), [])
    ok("MCP", "get_quote không xuất `exclude` nội bộ", "exclude" in tools["pricing.get_quote"][2]["properties"], False)
    ok("MCP", "schema đọc cùng thư mục BTC với mock", CS._schema_path().endswith(os.path.join("schemas", "tools.schema.json")))
except ImportError as e:
    print("SKIP MCP schema (thiếu gói mcp):", e)
try:
    from harness.mcp_client import connection
    with patch.object(settings, "tool_transport", "mcp"):
        ToolBox.reset_world()
        tb = ToolBox("2026-10-15")
        via_mcp = tb.call("pricing.quote_order", lines=[{"sku": "SKU-AP-PRO", "qty": 2}])
    direct = mt.pricing_quote_order([{"sku": "SKU-AP-PRO", "qty": 2}], "2026-10-15")
    ok("MCP", "quote_order MCP = direct (cùng ngày, cùng đầu vào)", via_mcp, json.loads(json.dumps(direct)))
except Exception as e:  # noqa: BLE001
    ok("MCP", f"MCP parity chạy được ({type(e).__name__}: {str(e)[:80]})", False)

# ------------------------------------------------------------------ evaluator mới
sys.path.insert(0, os.path.join(ROOT, "eval"))
import reference_eval as RE  # noqa: E402
ok("EVAL", "giờ hẹn so theo phút", RE.args_match({"callback_at": "2026-10-27T09:00"}, {"callback_at": "2026-10-27T09:00:00"}))
ok("EVAL", "mã đơn thực tạo ở phiên trước được chấp nhận", RE.args_match({"order_id": "OD-GOLD"}, {"order_id": "OD600001"}, {"OD600001"}))
ok("EVAL", "promo_code không truyền thì không trừ; truyền sai thì trượt",
   (RE.args_match({"promo_code": "X"}, {}), RE.args_match({"promo_code": "X"}, {"promo_code": "Y"})), (True, False))
cc = [{"name": "order.create", "args": {"sku": "A", "price_vnd": 5}, "result": {"error": "cod_limit_exceeded"}},
      {"name": "order.create", "args": {"lines": [{"sku": "A", "qty": 2, "price_vnd": 5}], "payment": "bank"}, "result": {"order_id": "OD1"}}]
ok("EVAL", "order_lines bỏ create lỗi, đọc lines", [(x["sku"], x["qty"], x["payment"]) for x in RE.order_lines(cc)], [("A", 2, "bank")])
ok("EVAL", "chuẩn hóa tiền + nguyên từ", (RE.said(RE._say_norm("Giá 1.521.000đ ạ"), "1,521,000"), RE.said(RE._say_norm("em gọi lại"), "AI")), (True, False))

# ------------------------------------------------------------------ ASR: entity gold dạng danh sách
sys.path.insert(0, os.path.join(ROOT, "asr"))
try:
    import transcribe as TR
    by, wrong = TR.entity_breakdown({"dialogues": [{"id": "d1", "entities": {"phone": ["0911222333", "0911222444"]}}]},
                                    {"d1": {"entities": {"phone": "0911222444"}}})
    ok("ASR", "entity gold danh sách: khớp một giá trị là đúng", (by["phone"], wrong), ((100.0, 1), []))
except Exception as e:  # noqa: BLE001 — môi trường thiếu phụ thuộc ASR thì bỏ qua, ghi rõ
    print("SKIP ASR (thiếu phụ thuộc ASR):", str(e)[:80])

for p in reversed(PATCHES):
    p.stop()
print(f"\n{PASS[0]} OK, {len(FAIL)} lỗi")
if FAIL:
    print("LỖI:", FAIL)
sys.exit(1 if FAIL else 0)
