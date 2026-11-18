"""Đo ảnh hưởng (CHƯA SỬA) hai lỗi holdout bằng DeepSeek THẬT — duyệt 12/11: "payment và ranh giới hỏi/yêu cầu được kiểm bằng
model thật để báo mức ảnh hưởng trước". Cần DEEPSEEK_API_KEY. Câu viết tay MỚI (không chép holdout); nhãn kỳ vọng do Claude viết
theo định nghĩa hợp đồng bộ hiểu (không phải gold người chấm).

A. PAYMENT (holdout 5): câu vừa đọc địa chỉ vừa chọn cách trả tiền → kỳ vọng observation `payment` stance chosen/stated; câu chỉ
   HỎI cách trả tiền → kỳ vọng KHÔNG có payment chosen; câu chỉ đọc địa chỉ → không bịa payment.
B. HỎI / YÊU CẦU (holdout 6): câu hỏi thuần về đổi / trả / đặt (giả định, so sánh, hỏi phí) → kỳ vọng KHÔNG có request ghi
   (exchange / return / place_order); câu yêu cầu rõ → kỳ vọng CÓ đúng request.
Mỗi câu chạy N lần (mặc định 3) để thấy độ ổn định. Báo tỷ lệ; không có ngưỡng đạt / trượt (đây là đo ảnh hưởng).
Dùng: python scripts/deepseek_boundary_probe.py <out_dir> [--repeat N]
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
OUT = sys.argv[1] if len(sys.argv) > 1 else "runs/local/ds_probe"
REPEAT = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 3
os.makedirs(OUT, exist_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "d.db").replace("\\", "/"))
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from harness import understanding as U  # noqa: E402

if not settings.deepseek_api_key:
    print("THIẾU DEEPSEEK_API_KEY: không chạy (không mô phỏng DeepSeek trong đo ảnh hưởng)")
    sys.exit(2)

CTX = {"candidates": [{"ref": "P1", "kind": "product", "name": "Giày chạy RunLite 1", "role": "focus"},
                      {"ref": "P2", "kind": "product", "name": "Giày chạy Urban Classic", "role": "discussed"},
                      {"ref": "O1", "kind": "order", "order_id": "OD600010", "product": "Giày chạy RunLite 1", "status": "delivered"}],
       "pending": [], "agent_proposal": None, "agent_last_goals": ["quote"]}
RECENT = [{"role": "agent", "text": "Dạ giày RunLite 1 size 42 giá 1.161.000đ ạ."}]

# (câu, nhóm, kỳ vọng)
PAYMENT = [
    ("Giao về 45 Trần Phú, Hải Châu, Đà Nẵng, anh chuyển khoản trước luôn nhé", "pay_with_address", "payment"),
    ("Em gửi về 7 Nguyễn Huệ, Quận 1, TP HCM, chị trả bằng thẻ khi nhận", "pay_with_address", "payment"),
    ("Địa chỉ 88 Lý Thường Kiệt, Hoàn Kiếm, Hà Nội, thanh toán khi nhận hàng nha em", "pay_with_address", "payment"),
    ("Ship về 120 Võ Văn Tần, Quận 3, TP HCM, tiền thì anh chuyển khoản", "pay_with_address", "payment"),
    ("Bên em có cho chuyển khoản không hay chỉ COD thôi?", "pay_question", "no_payment_choice"),
    ("Thanh toán khi nhận được không em?", "pay_question", "no_payment_choice"),
    ("Giao về 9 Pasteur, Quận 1, TP HCM giúp anh", "address_only", "no_payment_choice"),
]
BOUNDARY = [
    ("Nếu đổi sang Urban Classic thì có mất phí gì không em?", "question", "no_write_request"),
    ("Mẫu Urban Classic rẻ hơn RunLite đúng không em?", "question", "no_write_request"),
    ("Trường hợp chị muốn trả thì được hoàn bao nhiêu?", "question", "no_write_request"),
    ("Đổi size thì bao lâu mới nhận được hàng mới em?", "question", "no_write_request"),
    ("Giày này còn size 43 không em?", "question", "no_write_request"),
    ("Em đổi giúp chị sang Urban Classic nhé", "request", "exchange"),
    ("Chị muốn trả lại đôi giày đã mua", "request", "return"),
    ("Lấy cho anh đôi RunLite size 43 luôn", "request", "place_order"),
]
WRITE_KINDS = {"place_order", "exchange", "return", "change_order_address"}


def one(text):
    try:
        u = U.understand(text, "2026-10-15", RECENT, "", None, state_ctx=CTX)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    return {"observations": [{"slot": o["slot"], "stance": o.get("stance")} for o in u.get("observations") or []],
            "payment": (u.get("slots") or {}).get("payment"), "requests": [i["kind"] for i in u.get("request_items") or []],
            "asks": u.get("asks"), "asks_question": u.get("asks_question")}


def judge(expect, r):
    if r.get("error"):
        return None
    pay_obs = [o for o in r["observations"] if o["slot"] == "payment" and o["stance"] in ("chosen", "stated")]
    writes = set(r["requests"]) & WRITE_KINDS
    return {"payment": bool(pay_obs) and bool(r["payment"]), "no_payment_choice": not pay_obs,
            "no_write_request": not writes}.get(expect, expect in writes)


rows = []
for text, group, expect in PAYMENT + BOUNDARY:
    for k in range(REPEAT):
        r = one(text)
        rows.append({"text": text, "group": group, "expect": expect, "rep": k, "ok": judge(expect, r), **r})
summary = {}
for g in dict.fromkeys(x["group"] for x in rows):
    rs = [x for x in rows if x["group"] == g]
    judged = [x for x in rs if x["ok"] is not None]
    summary[g] = {"ok": sum(1 for x in judged if x["ok"]), "judged": len(judged), "errors": len(rs) - len(judged),
                  "unstable_sentences": sum(1 for t in dict.fromkeys(x["text"] for x in rs)
                                            if len({x["ok"] for x in rs if x["text"] == t}) > 1)}
res = {"deepseek_model": settings.deepseek_model, "repeat": REPEAT, "summary": summary,
       "note": "đo ảnh hưởng, chưa sửa; nhãn kỳ vọng do Claude viết theo hợp đồng bộ hiểu"}
json.dump({**res, "rows": rows}, open(os.path.join(OUT, "deepseek_boundary_probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
