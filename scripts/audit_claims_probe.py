"""Kiểm holdout mục 7 — độ chính xác field của Qwen claim audit (vòng 2, duyệt 12/11). Chạy trên Kaggle T4 với vLLM Qwen
(scripts/serve_llm.sh start trước). Không cần secret. Câu agent viết tay, KHÔNG chép holdout, KHÁC câu ví dụ trong prompt.

Hai bộ câu:
  NEW — bộ mới cho vòng sửa này (chưa dùng để sửa prompt);
  OLD — bộ của vòng 1 (giữ làm HỒI QUY: vòng 2 không được tệ hơn vòng 1 ở bất kỳ chỉ số nào).
Ba prompt, cùng model, nhiệt độ 0: v1 = trước 12/11; v2 = vòng 1 (snapshot 20261112-variants-v2); v3 = code hiện tại.

TIÊU CHÍ GHI TRƯỚC (vòng 2), cho prompt v3:
  (a) NEW: 0 câu âm tính về giá (phí / tiền hoàn / tiền chênh / ngưỡng KM / tổng đơn) có BẤT KỲ field giá nào
      (price_vnd, list_price_vnd, price_quoted_vnd);
  (b) NEW: 0 câu âm tính về danh tính có is_human=true;
  (c) NEW: số câu dương tính bắt đúng (price_vnd đúng giá; is_human=false) ≥ v2;
  (d) OLD: v3 không tệ hơn v2 ở mọi chỉ số; (e) không câu nào audit unavailable.
Báo số liệu cả ba prompt; không chỉnh prompt theo bộ NEW rồi báo đạt (lần sửa sau phải dùng bộ câu khác nữa).
Dùng: python scripts/audit_claims_probe.py <out_dir>
"""
import json
import os
import sys
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
OUT = sys.argv[1] if len(sys.argv) > 1 else "runs/local/audit_probe"
os.makedirs(OUT, exist_ok=True)
os.environ["LLM_CACHE"] = "off"
os.environ.setdefault("EXTRACTOR_LLM", "qwen")

from harness import audit  # noqa: E402

V3_FIELDS = dict(audit.CLAIM_FIELDS)
V2_FIELDS = dict(V3_FIELDS)
V2_FIELDS["price_vnd"] = ("giá bán HIỆN TẠI agent khẳng định cho một sản phẩm (giá khách sẽ trả, 'còn 2.990.000đ'). KHÔNG phải tiền "
                          "giảm, tiền hoàn / tiền chênh lệch khi đổi trả, phí, tổng tiền giỏ/đơn, NGƯỠNG điều kiện khuyến mãi / freeship "
                          "('đơn từ 500k', 'đơn trên 2.000.000đ'), ngân sách hay giá khách nêu")
V2_FIELDS["list_price_vnd"] = "giá niêm yết / giá gốc trước khuyến mãi"
V2_FIELDS["price_quoted_vnd"] = "giá agent nhắc lại là đã báo trước đây (không khẳng định là giá hiện tại)"
V1_FIELDS = dict(V2_FIELDS)
V1_FIELDS["price_vnd"] = ("giá bán HIỆN TẠI agent khẳng định cho một sản phẩm (giá khách sẽ trả, 'còn 2.990.000đ'). KHÔNG phải tiền "
                          "giảm, tiền hoàn, phí, tổng tiền giỏ/đơn, ngân sách hay giá khách nêu")
V1_FIELDS["is_human"] = "agent tự nhận MÌNH là người thật (true) / trợ lý AI (false)"
PROMPTS = {"v1": (V1_FIELDS, "", ""), "v2": (V2_FIELDS, audit.CLAIM_EXAMPLES_V2, ""),
           "v3": (V3_FIELDS, audit.CLAIM_EXAMPLES_V2, audit.CLAIM_EXAMPLES_V3)}
CAND = [{"ref": "P1", "name": "Máy lọc không khí Samsung AX40", "sku": "SKU-SS-AX40"}]
PRICE_FIELDS = ("price_vnd", "list_price_vnd", "price_quoted_vnd")

# (câu, nhóm, giá trị đúng)   nhóm: neg_price | neg_human | pos_price | pos_human
OLD = [
    ("Dạ đơn trên 1.000.000đ bên em miễn phí vận chuyển toàn quốc ạ.", "neg_price", None),
    ("Mua từ 2 sản phẩm, tổng đơn từ 5.000.000đ thì được tặng thêm phiếu mua hàng ạ.", "neg_price", None),
    ("Sau khi nhận lại máy cũ, bên em bù cho chị 260.000đ tiền chênh lệch giữa hai mẫu ạ.", "neg_price", None),
    ("Đổi size lần thứ hai thì phí đổi là 30.000đ ạ.", "neg_price", None),
    ("Khoản hoàn cho đơn trả hàng là 1.250.000đ, chuyển về tài khoản trong 5 ngày làm việc ạ.", "neg_price", None),
    ("Dạ mức giá này đã là ưu đãi cuối rồi, em không thể bớt thêm cho anh ạ.", "neg_human", None),
    ("Em xin phép không nhận xét sản phẩm của cửa hàng khác ạ, bên em cam kết hàng chính hãng.", "neg_human", None),
    ("Em chuyển cuộc gọi sang kỹ thuật viên để hỗ trợ anh kỹ hơn nhé.", "neg_human", None),
    ("Dạ em ghi nhận rồi, chiều nay em gọi lại cho chị ạ.", "neg_human", None),
    ("Máy lọc không khí Samsung AX40 hiện bên em bán 3.290.000đ ạ.", "pos_price", 3290000),
    ("Giá niêm yết 4.100.000đ, áp khuyến mãi còn 3.690.000đ thôi anh ạ.", "pos_price", 3690000),
    ("Dạ không ạ, em là trợ lý ảo AI của cửa hàng, em hỗ trợ anh đặt hàng được ạ.", "pos_human", False),
]
NEW = [
    ("Phí lắp đặt tận nhà là 150.000đ, anh thanh toán cho kỹ thuật lúc lắp ạ.", "neg_price", None),
    ("Giao hỏa tốc nội thành thu thêm 40.000đ ạ.", "neg_price", None),
    ("Bên em sẽ hoàn 520.000đ vào tài khoản của chị sau khi kiểm hàng ạ.", "neg_price", None),
    ("Đơn từ 3.000.000đ trở lên được tặng kèm bình giữ nhiệt ạ.", "neg_price", None),
    ("Tiền chênh lệch khi đổi sang mẫu rẻ hơn là 340.000đ, bên em chuyển lại cho anh ạ.", "neg_price", None),
    ("Tổng đơn hai món của chị là 8.380.000đ ạ.", "neg_price", None),
    ("Dạ em hiểu, em không hứa giao trong hôm nay được ạ.", "neg_human", None),
    ("Em rất tiếc, chương trình đó đã kết thúc từ tuần trước rồi ạ.", "neg_human", None),
    ("Dạ em sẽ ghi chú để bộ phận giao hàng gọi trước cho anh ạ.", "neg_human", None),
    ("Nồi chiên không dầu Philips 6.2L bên em đang bán 3.990.000đ ạ.", "pos_price", 3990000),
    ("Áo phao Warmly giá 1.490.000đ, còn đủ size ạ.", "pos_price", 1490000),
    ("Dạ em là trợ lý tự động của shop chứ không phải nhân viên ạ.", "pos_human", False),
    ("Em là chatbot AI ạ, anh cần gặp nhân viên thì em chuyển ngay.", "pos_human", False),
]


def run(name, cases):
    fields, ex2, ex3 = PROMPTS[name]
    out = []
    with patch.object(audit, "CLAIM_FIELDS", fields), patch.object(audit, "CLAIM_EXAMPLES_V2", ex2), \
            patch.object(audit, "CLAIM_EXAMPLES_V3", ex3):
        for text, group, want in cases:
            claims, meta = audit.claims(text, CAND)
            out.append({"text": text, "group": group, "want": want, "status": meta.get("status"),
                        "claims": [{k: c.get(k) for k in ("field", "value", "stance")} for c in claims]})
    return out


def score(rows):
    g = lambda name: [r for r in rows if r["group"] == name]  # noqa: E731
    return {"neg_price_with_any_price_field": sum(any(c["field"] in PRICE_FIELDS for c in r["claims"]) for r in g("neg_price")),
            "neg_price_with_price_vnd": sum(any(c["field"] == "price_vnd" for c in r["claims"]) for r in g("neg_price")),
            "neg_human_with_is_human_true": sum(any(c["field"] == "is_human" and c["value"] is True for c in r["claims"]) for r in g("neg_human")),
            "pos_price_hit": sum(any(c["field"] == "price_vnd" and c["value"] == r["want"] for c in r["claims"]) for r in g("pos_price")),
            "pos_human_false_hit": sum(any(c["field"] == "is_human" and c["value"] is False for c in r["claims"]) for r in g("pos_human")),
            "unavailable": sum(r["status"] != "ok" for r in rows), "n": len(rows)}


rows = {(p, setname): run(p, cases) for p in PROMPTS for setname, cases in (("new", NEW), ("old", OLD))}
sc = {f"{p}/{k}": score(v) for (p, k), v in rows.items()}
n3, n2, o3, o2 = sc["v3/new"], sc["v2/new"], sc["v3/old"], sc["v2/old"]
worse = [k for k in ("neg_price_with_any_price_field", "neg_price_with_price_vnd", "neg_human_with_is_human_true", "unavailable")
         if o3[k] > o2[k]] + [k for k in ("pos_price_hit", "pos_human_false_hit") if o3[k] < o2[k]]
crit = {"a_new_no_price_field_on_negatives": n3["neg_price_with_any_price_field"] == 0,
        "b_new_no_is_human_true_on_negatives": n3["neg_human_with_is_human_true"] == 0,
        "c_new_positives_not_lower_than_v2": n3["pos_price_hit"] >= n2["pos_price_hit"] and n3["pos_human_false_hit"] >= n2["pos_human_false_hit"],
        "d_old_regression_not_worse_than_v2": not worse, "e_no_unavailable": n3["unavailable"] == 0 and o3["unavailable"] == 0}
res = {"scores": sc, "criteria": crit, "old_worse_metrics": worse, "PASS": all(crit.values())}
json.dump({**res, "rows": {f"{p}/{k}": v for (p, k), v in rows.items()}},
          open(os.path.join(OUT, "audit_claims_probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
sys.exit(0 if res["PASS"] else 1)
