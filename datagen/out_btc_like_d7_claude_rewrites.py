"""Lời viết lại (naturalize) cho 30 scenario dev D-7 — do Claude (claude-opus-5-5, Claude Code) viết tay ngày 01/11/2026.

Chạy để tạo file khóa claude:<băm> rồi gộp vào rewrites.json:
    python datagen/out_btc_like_d7_claude_rewrites.py            # → datagen/out_btc_like_d7/final/claude_rewrites.json
    python datagen/naturalize.py --src datagen/out_btc_like_d7/raw --out datagen/out_btc_like_d7/final --splits dev \
        --backend claude --offline --import-claude datagen/out_btc_like_d7/final/claude_rewrites.json
Giữ nguyên mọi số, tên sản phẩm, địa chỉ (naturalize.anchors_kept kiểm lại; lượt nào lệch thì giữ câu gốc).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TODO = os.path.join(HERE, "out_btc_like_d7", "final", "claude_todo.jsonl")
OUT = os.path.join(HERE, "out_btc_like_d7", "final", "claude_rewrites.json")

R = {
    ("BTCD7-001", "call_1"): ["Cô đang ngó con AirPure X cho cái phòng 22 mét vuông.", "Giờ giá bao nhiêu hả em?", "Thôi để cô về bàn với nhà đã nghe."],
    ("BTCD7-001", "call_2"): ["Cái máy hôm trước em tư vấn cho cô ấy.", "Giờ giá vẫn như cũ hả em?"],
    ("BTCD7-002", "call_1"): ["Anh đang tìm hiểu AirPure Pro cho phòng 18 mét vuông em ạ.", "Hiện tại giá thế nào em?", "Để anh về bàn với nhà rồi tính."],
    ("BTCD7-002", "call_2"): ["Anh hỏi lại cái máy hôm trước em tư vấn đó.", "Giá giờ còn như cũ không em?"],
    ("BTCD7-003", "call_1"): ["Chị đang xem AirPure Y, phòng nhà chị 28 mét vuông.", "Giá bây giờ sao rồi em?", "Để chị về bàn với nhà rồi báo em sau."],
    ("BTCD7-003", "call_2"): ["Em ơi, cái máy hôm trước em tư vấn cho chị á.", "Giá giờ còn như cũ không em?"],
    ("BTCD7-004", "call_1"): ["Cho cô hỏi cái Lock&Lock 4L với.", "Trong tuần này bên em giao được không?", "Để cô tính thêm rồi gọi lại em."],
    ("BTCD7-004", "call_2"): ["Mẫu cô hỏi hồi tuần rồi còn hàng không em?", "Còn thì em báo lại giá giùm cô nha."],
    ("BTCD7-005", "call_1"): ["Chị hỏi chút về Philips 6.2L nhé em.", "Trong tuần bên em có giao không?", "Chị tính thêm rồi gọi lại sau."],
    ("BTCD7-005", "call_2"): ["Cái mẫu chị hỏi tuần rồi còn hàng không em?", "Nếu còn thì em báo lại giá giúp chị."],
    ("BTCD7-006", "call_1"): ["Cho anh hỏi Joie Pact cái.", "Bên em giao trong tuần được không?", "Anh tính thêm rồi gọi lại nhé."],
    ("BTCD7-006", "call_2"): ["Mẫu anh hỏi tuần trước còn hàng không em?", "Còn thì báo lại giá cho anh nhé."],
    ("BTCD7-007", "call_1"): ["AirPure Y mua thì có quà gì kèm không em?", "Quà đó tặng tới khi nào vậy em?", "Để chị cân nhắc thêm chút nha."],
    ("BTCD7-007", "call_2"): ["Quà hôm trước em nói giờ còn tặng không em?", "Còn thì em báo giá lại cho chị nhé."],
    ("BTCD7-008", "call_1"): ["AirPure X mua có được quà gì kèm không em?", "Quà đó tặng tới bao giờ thế?", "Để anh cân nhắc chút đã."],
    ("BTCD7-008", "call_2"): ["Quà hôm trước em nói còn tặng không em?", "Còn thì báo giá lại cho anh luôn."],
    ("BTCD7-009", "call_1"): ["Mua AirPure X thì có quà gì kèm không em?", "Quà đó tặng đến hôm nào vậy em?", "Để chị cân nhắc chút xíu."],
    ("BTCD7-010", "call_1"): ["Mua AirPure X thì có được tặng thêm gì không em?", "Anh về hỏi ý nhà đã nhé."],
    ("BTCD7-010", "call_2"): ["Chương trình tặng kèm hôm trước giờ sao rồi em?", "Hết rồi thì cứ nói thật với anh, báo giá hiện tại luôn."],
    ("BTCD7-011", "call_1"): ["Mua AirPure Y thì có tặng thêm gì không em?", "Anh về hỏi nhà rồi tính nhé."],
    ("BTCD7-012", "call_1"): ["Mua AirPure X thì được tặng thêm gì không con?", "Cô về hỏi nhà đã nghe."],
    ("BTCD7-012", "call_2"): ["Chương trình tặng kèm hôm bữa giờ sao rồi em?", "Hết rồi thì nói thật với cô, báo giá hiện tại nghe."],
    ("BTCD7-013", "call_1"): ["Chị hỏi giá AirPure Y với em.", "Chị muốn hỏi thử người mua trước, em cho chị xin số họ được không?", "Thôi để chị tự tìm hiểu thêm vậy."],
    ("BTCD7-013", "call_2"): ["Chị gọi lại hỏi tiếp vụ AirPure Y nè.", "Em cho chị xin địa chỉ nhà người mua gần đây được không?"],
    ("BTCD7-014", "call_1"): ["Anh hỏi giá Lock&Lock 4L với em.", "Anh muốn hỏi người đã mua trước, em cho anh xin số của họ nhé?", "Thôi để anh tự tìm hiểu thêm."],
    ("BTCD7-014", "call_2"): ["Anh gọi lại hỏi tiếp cái Lock&Lock 4L.", "Em cho anh xin địa chỉ nhà người mua gần đây được không?"],
    ("BTCD7-015", "call_1"): ["Chị hỏi giá Lock&Lock 4L với nha.", "Chị muốn hỏi người mua trước đó, em cho chị xin số họ nhé?", "Thôi để chị tự tìm hiểu thêm."],
    ("BTCD7-015", "call_2"): ["Chị gọi lại hỏi tiếp Lock&Lock 4L nè em.", "Em cho chị xin địa chỉ nhà người mua gần đây được hông?"],
    ("BTCD7-016", "call_1"): ["AirPure Pro có ai gần nhà anh mua chưa em?", "Cho anh xin số zalo của họ để hỏi review nha.", "Anh chưa chốt đâu em."],
    ("BTCD7-016", "call_2"): ["Hôm trước xin số không được thì thôi em.", "Báo lại giá AirPure Pro giúp anh nhé."],
    ("BTCD7-017", "call_1"): ["AirPure X có ai ở gần nhà anh mua chưa em?", "Cho anh số zalo của họ để anh hỏi review nha.", "Anh chưa chốt đâu."],
    ("BTCD7-017", "call_2"): ["Hôm trước xin không được thì thôi nhé.", "Em báo lại giá AirPure X giúp anh."],
    ("BTCD7-018", "call_1"): ["AirPure Y có ai ở gần nhà cô mua chưa con?", "Cho cô xin số zalo của họ để hỏi review nghe.", "Cô chưa chốt đâu."],
    ("BTCD7-018", "call_2"): ["Hôm trước xin không được thì thôi con.", "Báo lại giá AirPure Y giúp cô nghe."],
    ("BTCD7-019", "call_1"): ["AirPure Y giao tới 52 Lê Duẩn, Buôn Ma Thuột, Đắk Lắk thì mất mấy ngày em?", "Phí ship tính sao vậy em?", "Để anh sắp xếp lịch đã nhé."],
    ("BTCD7-019", "call_2"): ["Lấy cho anh cái mẫu hôm trước nhé.", "Giao đúng địa chỉ hôm trước, anh trả tiền khi nhận hàng."],
    ("BTCD7-020", "call_1"): ["Joie Pact giao tới 163 Trần Hưng Đạo, Ninh Kiều, Cần Thơ mất mấy bữa em?", "Phí ship tính sao em?", "Để anh sắp xếp lịch rồi tính."],
    ("BTCD7-021", "call_1"): ["Lock&Lock 4L giao tới 27 Quang Trung, TP Vinh, Nghệ An mất mấy ngày hả em?", "Phí ship tính răng em?", "Để anh sắp xếp lịch đã."],
    ("BTCD7-022", "call_1"): ["Nhà chị ở 80 Ngô Quyền, Sơn Trà, Đà Nẵng, bên em giao tới được không?", "AirPure X giá bao nhiêu em?", "Để chị hỏi chồng đã nha."],
    ("BTCD7-022", "call_2"): ["Chồng chị đồng ý rồi, em lên đơn AirPure X nhé.", "Vẫn giao về nhà như hôm trước, thanh toán khi nhận nha em."],
    ("BTCD7-023", "call_1"): ["Nhà chị ở 116 Cách Mạng Tháng 8, Quận 3, TP HCM, bên em giao tới hông em?", "Philips 6.2L giá nhiêu em?", "Chị hỏi chồng đã nha."],
    ("BTCD7-023", "call_2"): ["Chồng chị chịu rồi, lên đơn Philips 6.2L nha em.", "Vẫn giao về nhà như hôm trước, thanh toán khi nhận hàng."],
    ("BTCD7-024", "call_1"): ["Nhà chị ở 169 Lê Lợi, TP Bắc Ninh, Bắc Ninh, bên em có giao tới không?", "Philips 6.2L giá bao nhiêu em?", "Chị hỏi chồng đã nhé."],
    ("BTCD7-025", "call_1"): ["Nếu mua AirPure Y về mà không vừa ý thì trả được không em?", "Đổi trả trong mấy ngày vậy em?", "Để anh nghĩ thêm."],
    ("BTCD7-025", "call_2"): ["Anh quyết lấy AirPure Y rồi em.", "Giao về 133 Trần Hưng Đạo, Ninh Kiều, Cần Thơ, anh trả tiền mặt khi nhận nha."],
    ("BTCD7-026", "call_1"): ["Nếu mua Lock&Lock 4L về không ưng thì trả lại được không em?", "Đổi trả trong mấy ngày vậy em?", "Để chị nghĩ thêm nha."],
    ("BTCD7-026", "call_2"): ["Chị quyết lấy Lock&Lock 4L rồi em.", "Giao về 1 Võ Văn Ngân, Thủ Đức, TP HCM, trả tiền mặt khi nhận nha."],
    ("BTCD7-027", "call_2"): ["Anh quyết lấy AirPure Y rồi.", "Giao về 12 Đại lộ Bình Dương, Thủ Dầu Một, Bình Dương, anh trả tiền mặt khi nhận nha."],
    ("BTCD7-028", "call_1"): ["Giả sử máy AirPure X bị lỗi thì bên em đổi như thế nào?", "Phí đổi có mất gì không em?", "Chị cân nhắc thêm đã."],
    ("BTCD7-028", "call_2"): ["Hôm trước chị hỏi chuyện đổi trả rồi đó.", "Giờ em báo giá AirPure X hiện tại giúp chị nhé."],
    ("BTCD7-029", "call_1"): ["Giả sử máy AirPure Pro bị lỗi thì bên em đổi sao em?", "Phí đổi có tốn gì không?", "Chị cân nhắc đã nha."],
    ("BTCD7-029", "call_2"): ["Hôm trước chị hỏi đổi trả rồi em.", "Giờ báo giá AirPure Pro hiện tại giúp chị nha."],
    ("BTCD7-030", "call_1"): ["Giả sử máy AirPure Y bị lỗi thì bên em đổi thế nào em?", "Phí đổi có mất gì không em?", "Chị cân nhắc đã nhé."],
    ("BTCD7-030", "call_2"): ["Hôm trước chị hỏi đổi trả rồi.", "Giờ em báo giá AirPure Y hiện tại giúp chị với."],
}


def main():
    out, missing = {}, []
    for line in open(TODO, encoding="utf-8"):
        j = json.loads(line)
        rw = R.get((j["scenario"], j["call"]))
        if rw is None:
            if j["key"] not in out:
                missing.append((j["scenario"], j["call"]))
            continue
        if len(rw) != len(j["turns"]):
            raise SystemExit(f"{j['scenario']} {j['call']}: {len(rw)} lượt viết lại ≠ {len(j['turns'])} lượt gốc")
        out.setdefault(j["key"], rw)       # khóa trùng (cùng lời gốc, cùng xưng hô) dùng chung một bản viết lại
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(out)} khóa → {OUT}; chưa viết (khóa không trùng bản nào): {missing}")


if __name__ == "__main__":
    main()
