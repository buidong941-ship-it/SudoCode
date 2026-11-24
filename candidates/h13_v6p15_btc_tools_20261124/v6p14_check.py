"""Kaggle only. v6p14 vòng 2B: S3 DOC_ANSWER (câu nguyên văn trong tài liệu, model chỉ chọn số thứ tự) và G7 mở rộng cho yêu cầu
handoff sau khi đơn đã hủy bằng tool (DONE_NO_HANDOFF). Cờ tắt → như v6p13."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.config import settings
from core.llm import deepseek
from core.llm import generator as GEN
from harness import agent
from harness import planner_table as T

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


SPEC = {"chunk_id": "SP-02", "text": "Joie Pact: nặng 6 kg, gấp một tay, tải 22 kg, có mái che UPF 50. Combi Sugocal: nặng 5,2 kg, 2 chiều."}
SHIP = {"chunk_id": "VC-02", "text": "- Đơn từ 500.000đ: miễn phí vận chuyển với ngành mẹ & bé.\n- Hàng cồng kềnh (máy lọc nước, xe đẩy, ghế ô tô): "
                                    "phụ thu 30.000đ ngoài nội thành."}
SEEN = {}


class FakeLLM:
    reply = {"answers": [0], "unknown": False}

    def __init__(self, *a, **k):
        pass

    def json(self, prompt, **k):
        SEEN["prompt"] = prompt
        if isinstance(FakeLLM.reply, Exception):
            raise FakeLLM.reply
        return FakeLLM.reply


def ctx(text, mentioned=(), focus=None):
    s = SimpleNamespace(focus=focus, _why=lambda *a: None)
    return SimpleNamespace(s=s, text=text, mentioned=list(mentioned), facts={}, goals=[])


with patch.object(deepseek, "LLM", FakeLLM):
    with patch.object(agent.knowledge, "search", lambda q, k=3, order_date=None: [SPEC, SHIP]):
        FakeLLM.reply = {"answers": [0], "unknown": True}
        c = ctx("Xe đẩy Joie Pact nặng mấy ký? Có kèm tấm che mưa không?")
        da = T.doc_answer(c, sku="SKU-MB-STR1")
        check("S3 doc: brand filter keeps only the product's chunk", da and [p["chunk_id"] for p in da["policy"]] == ["SP-02"])
        check("S3 doc: sentence is verbatim from the document", da and da["sentences"] == ["Joie Pact: nặng 6 kg, gấp một tay, tải 22 kg, có mái che UPF 50."])
        check("S3 doc: unknown part flagged", da and da["unknown"] is True)
        check("S3 doc: prompt numbers sentences, names product", "[0] Joie Pact" in SEEN["prompt"] and "Xe đẩy gấp gọn Joie Pact" in SEEN["prompt"])
        FakeLLM.reply = {"answers": [99, True, "1"], "unknown": False}
        check("S3 doc: invalid indexes ignored → none", T.doc_answer(ctx("phí ship?")) is None)
        FakeLLM.reply = {"answers": [3], "unknown": False}
        da = T.doc_answer(ctx("Mua RO Kangaroo về Thanh Hóa thì phí ship sao em?"), about="SKU-WF-RO10")
        check("S3 doc: list lines split into sentences, bulky fee picked",
              da and da["sentences"] == ["Hàng cồng kềnh (máy lọc nước, xe đẩy, ghế ô tô): phụ thu 30.000đ ngoài nội thành."])
        FakeLLM.reply = RuntimeError("down")
        check("S3 doc: LLM error → none (caller keeps old path)", T.doc_answer(ctx("phí ship?")) is None)
    with patch.object(agent.knowledge, "search", lambda q, k=3, order_date=None: []):
        check("S3 doc: no chunk → none", T.doc_answer(ctx("tổng đài làm mấy giờ")) is None)

TABLE = {"chunk_id": "SP-AIR-01", "text": "| SKU | CADR (m³/h) | Độ ồn min–max (dB) | Khóa trẻ em |\n|---|---|---|---|\n"
                                         "| SKU-AP-X | 250 | 24–52 | Không |\n| SKU-AP-Y | 300 | 23–50 | Có |"}
rows = T._doc_sentences(TABLE["text"], "SKU-AP-Y")
print("  table:", rows, flush=True)
check("S3 table: only the product's row, units from header, range keeps unit",
      len(rows) == 1 and "AirPure Y" in rows[0] and "Độ ồn min–max 23 dB – 50 dB" in rows[0] and "CADR 300 m³/h" in rows[0])
check("S3 table: no sku → every row", len(T._doc_sentences(TABLE["text"])) == 2)
check("S3 text: markdown bold removed", T._doc_sentences("Đơn từ **500.000đ**: miễn phí. Khác nữa.") == ["Đơn từ 500.000đ: miễn phí.", "Khác nữa."])
with patch.object(deepseek, "LLM", FakeLLM), patch.object(agent.knowledge, "search", lambda q, k=3, order_date=None: [SHIP, TABLE]):
    FakeLLM.reply = {"answers": [0], "unknown": True}
    da = T.doc_answer(ctx("AirPure Y chạy êm nhất bao nhiêu đề xi ben? Lọc được radon không?"), sku="SKU-AP-Y")
    check("S3 doc: spec table kept by SKU (no brand word), other chunk dropped",
          da and [p["chunk_id"] for p in da["policy"]] == ["SP-AIR-01"] and "23 dB" in da["sentences"][0])
txt = GEN.render_offline({"goals": ["doc_answer"], "facts": {"doc_answer": {"sentences": ["Joie Pact: nặng 6 kg, tải 22 kg."], "unknown": True}}})
print("  reply:", txt, flush=True)
check("S3 reply: reads sentence + says no info for the rest", "nặng 6 kg" in txt and "không có thông tin" in txt)
txt = GEN.render_offline({"goals": ["doc_answer"], "facts": {"doc_answer": {"sentences": [], "unknown": True}}})
check("S3 reply: nothing found → no info", "không có thông tin" in txt)

# S5: số tiền ở dòng sau của đoạn chính sách cũng là câu chính sách
claims = [{"field": "price_vnd", "value": 30000, "text": "Dạ theo thông tin bên em: Hàng cồng kềnh (máy lọc nước, xe đẩy, ghế ô tô): phụ thu 30.000đ ngoài nội thành."}]
check("S5: money from any policy line not a product price", agent._grounded_claims(claims, ["doc_answer"], [SHIP["text"]], {}) == [])


# ================================================================== G7 mở rộng: yêu cầu handoff
def g7_ctx(done=("OD600001",), told=None, active=False):
    items = [{"status": "open" if active else "done"}]
    s = SimpleNamespace(ext_cancelled=list(done), done_confirm_told=told, turn_no=2, reqs=SimpleNamespace(items=items))
    return SimpleNamespace(s=s, facts={}, goals=[])


c = g7_ctx()
check("G7 handoff after tool cancel: confirm first", T._confirm_done_first(c, {"handoff"}, {}) and c.goals == ["cancel_done_confirm"]
      and c.s.done_confirm_told == 2)
check("G7 handoff: already confirmed once → transfer", not T._confirm_done_first(g7_ctx(told=2), {"handoff"}, {}))
check("G7 handoff: nothing cancelled → transfer", not T._confirm_done_first(g7_ctx(done=()), {"handoff"}, {}))
check("G7 handoff: another request in turn → transfer", not T._confirm_done_first(g7_ctx(), {"handoff", "exchange"}, {}))
check("G7 handoff: customer also asks something → transfer", not T._confirm_done_first(g7_ctx(), {"handoff"}, {"asks": ["price"]}))
check("G7 handoff: open request remains → transfer", not T._confirm_done_first(g7_ctx(active=True), {"handoff"}, {}))

print("v6p14 checks:", passed, "PASS", flush=True)
assert not failed, failed
