"""Kiểm offline B3/B4/B5 của PLAN-2026-11-01 (router rules + generator offline, tool trực tiếp, DB tạm).

B3 (BTCL-016/017): khách nhắc lần trước nhưng không tìm được lịch sử → xin SĐT/tài khoản để tra, không hỏi lại sản phẩm.
B4 (BTCL-051/052): hỏi quà tặng kèm → trả lời KM quà của sản phẩm chính (còn / hết), không báo giá phụ kiện.
B5 (BTCL-031): "tầm 5 triệu rưỡi có vừa không?" → so ngân sách với giá tool; guardrail chặn đọc ngân sách như giá.
Câu khách lấy từ dev hoặc tự viết; không đọc holdout.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="b345_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "m.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")

from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, guardrails  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.textnorm import fold  # noqa: E402
from harness.tools import ToolBox  # noqa: E402

FAILS = []
R, G = Router("rules"), Generator("offline")


def ok(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)


def calls(name, script, phone="0911000111", channel="hotline", ident=None):
    """script: [(ngày, kênh, identity, [câu khách])] → [[row, ...] mỗi cuộc]"""
    mem = Memory(f"check:{name}")
    mem.wipe()
    ToolBox.reset_world()
    out = []
    for i, (day, ch, idt, turns) in enumerate(script, 1):
        s = agent.CallSession(memory=mem, today=day, call_name=f"call_{i}", session_id=f"{name}:{i}", channel=ch,
                              channel_identity=idt, phone=phone if ch == "hotline" else None, input_mode="text",
                              router=R, generator=G, config="full")
        s.start()
        out.append([s.turn(t) for t in turns])
        s.end()
    return out


def goals(row):
    return row["goals"]


def quoted(row):
    return [t["args"].get("sku") for t in row.get("tool_calls") or [] if t["name"] == "pricing.get_quote"]


# ---------- B5 ----------
(c1,) = calls("b5", [("2026-10-15", "hotline", None, ["Alo, cô muốn hỏi AirPure Y cho phòng 20 mét vuông.",
                                                     "Tầm 5 triệu rưỡi có vừa không em?"])])
t2 = c1[1]
ok("budget_fit" in goals(t2) and "quote" in goals(t2), f"B5: thiếu budget_fit/quote: {goals(t2)}")
ok("5.200.000" in t2["agent_text"] and "nằm trong" in t2["agent_text"], f"B5: câu trả lời sai: {t2['agent_text']}")
ok("closing" not in goals(t2), "B5: không được rơi xuống closing")
bad = "Dạ em thấy mức giá 5.500.000 đồng này vừa với ngân sách của chị lắm ạ."
good = "Dạ giá 5.200.000đ, nằm trong ngân sách 5.500.000đ của chị ạ."
ok(any("khách nêu như giá" in p for p in guardrails.check(bad, {5500000}, customer_money={5500000})),
   "B5: guardrail phải chặn 'mức giá <ngân sách khách>'")
ok(not guardrails.check(good, {5200000, 5500000}, customer_money={5500000}), "B5: nhắc ngân sách đúng ngữ cảnh phải được phép")
ok(not guardrails.check("Dạ giá bán là 5.200.000đ ạ.", {5200000}, customer_money=set()), "B5: giá tool phải được phép")

# ---------- B4 ----------
c1, c2 = calls("b4", [("2026-10-21", "hotline", None, ["Anh mua AirPure Y có tặng màng lọc không em?",
                                                       "Chương trình đó hết hạn khi nào vậy em?", "Anh cần bàn lại."]),
                      ("2026-10-23", "hotline", None, ["Anh gọi em hỏi xem quà màng lọc hôm nọ còn tặng không?"])])
a = c1[0]
ok(quoted(a) and all(s == "SKU-AP-Y" for s in quoted(a)), f"B4: cuộc 1 phải báo giá AirPure Y, không phải màng lọc: {quoted(a)}")
ok("Tặng 1 màng lọc" in a["agent_text"], f"B4: cuộc 1 phải nói quà đang tặng: {a['agent_text']}")
ok("gift_status" not in goals(a) and a["agent_text"].lower().count("tặng") == 1,
   f"B4: quà đang tặng đã có trong câu báo giá thì không nói lặp: {a['agent_text']}")
e = c1[1]
ok("quote" in goals(e) and "22/10" in e["agent_text"] and "ask_repeat" not in goals(e),
   f"B4: hỏi hạn chương trình phải đọc lại KM kèm ngày hết hạn: {goals(e)} {e['agent_text']}")
ok(not agent.PROMO_END_RX.search(fold("Bảo hành hết hạn thì sao em?")), "B4: hỏi hạn bảo hành không phải hỏi hạn KM")
b = c2[0]
ok("gift_status" in goals(b), f"B4: cuộc 2 thiếu gift_status: {goals(b)}")
ok("SKU-AP-FLT-X" not in quoted(b), f"B4: cuộc 2 không được báo giá màng lọc: {quoted(b)}")
ok("đã kết thúc" in b["agent_text"], f"B4: cuộc 2 (sau 22/10) phải nói chương trình đã kết thúc: {b['agent_text']}")
ok(not agent.GIFT_Q_RX.search(fold("Máy này đắt quá em ơi")), "B4: 'đắt quá' không phải câu hỏi quà")
ok(not agent.GIFT_Q_RX.search(fold("Màng lọc thay thế giá bao nhiêu em?")), "B4: hỏi giá màng lọc không phải câu hỏi quà")

# ---------- B3 ----------
(c2,) = calls("b3", [("2026-10-22", "hotline", None, ["Chị gọi lại về món giao tới nhà hôm trước.",
                                                     "Dựa trên địa chỉ đã đưa, mấy ngày nữa sẽ nhận được em?",
                                                     "Em xem lại giúp chị món hôm trước nhé?"])], phone="0970000999")
ok(goals(c2[0]) == ["ask_prior_contact"], f"B3: lượt 1 phải xin thông tin tra lịch sử: {goals(c2[0])}")
ok("ask_product" not in goals(c2[1]) and "ask_prior_contact" in goals(c2[1]), f"B3: lượt 2 không được hỏi lại sản phẩm: {goals(c2[1])}")
ok("ask_prior_contact" not in goals(c2[2]), "B3: chỉ xin tối đa 2 lần mỗi cuộc")
ok(all((r.get("question_slot") or "") != "product_advised" for r in c2[:2]), "B3: question_slot không được là product_advised")
(n,) = calls("b3n", [("2026-10-22", "hotline", None, ["Chào em, chị muốn hỏi nồi chiên."])], phone="0970000888")
ok("ask_prior_contact" not in goals(n[0]), f"B3: khách mới không nhắc lần trước thì không xin tra lịch sử: {goals(n[0])}")
# khách cũ (nhận ra được) nhắc "hôm trước" → dùng bộ nhớ, không xin tra
c1, c2 = calls("b3r", [("2026-10-19", "hotline", None, ["Chị đang tính mua Philips 6.2L.", "Để chị tính đã."]),
                       ("2026-10-22", "hotline", None, ["Chị gọi lại về món hôm trước."])], phone="0970000777")
ok("ask_prior_contact" not in goals(c2[0]) and "opening_returning" in goals(c2[0]), f"B3: khách cũ phải được nhận ra: {goals(c2[0])}")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
