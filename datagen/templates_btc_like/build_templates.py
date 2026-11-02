#!/usr/bin/env python3
"""Materialize the new, independently authored BTC-like scenario templates.

Each family has different development and holdout dialogue. Resolver supplies
customers, dates, catalog facts and prices; this file supplies only situations.
"""

import json
from copy import deepcopy
from pathlib import Path

FAMILIES = [
    {"id": "area_budget", "persona": "khach_do_du_hoi_nguoi_nha", "hard": "hai_slot_mot_luot",
     "skus": ["SKU-AP-X", "SKU-AP-Y", "SKU-AP-PRO"],
     "dev": ["Phòng làm việc {{area}} mét vuông, mức chi của {{cust.xh}} là {{trieu(budget)}}; xem {{p.short}} có hợp không em?",
             "Nhà có em bé nên {{cust.xh}} cần máy chạy êm.", "Để {{cust.xh}} bàn với gia đình rồi quay lại."],
     "dev_next": ["{{cust.Xh}} gọi về chuyện máy lọc cho phòng {{area}} mét vuông đây.", "Với mức tiền hôm qua, mẫu đó còn phù hợp không em?"],
     "holdout": ["Chỗ ngủ tầm {{area}}m2 mà {{cust.xh}} chỉ chuẩn bị {{trieu(budget)}}, em tư vấn {{p.short}} nhé.",
                 "Có trẻ nhỏ, {{cust.xh}} hơi ngại tiếng ồn.", "{{cust.Xh}} phải hỏi người nhà trước đã."],
     "holdout_next": ["Hôm nọ {{cust.xh}} hỏi cái máy cho phòng ngủ ấy.", "Nhắc lại phương án trong khoản tiền {{cust.xh}} đã nói giúp {{cust.xh}}."],
     "facts": {"room_area_m2": "{{area}}", "budget_vnd": "{{budget}}", "has_children": True},
     "extra_let": {"area": "pick([20,25,30])", "budget": "((price + 500000) // 500000) * 500000"},
     "success": {"tool_called": "pricing.get_quote"}},
    {"id": "promo_recheck", "persona": "khach_so_gia", "hard": "hoi_lai_khuyen_mai",
     "skus": ["SKU-AP-X", "SKU-AP-Y", "SKU-WF-RO9", "SKU-AF-4L"],
     "dev": ["{{p.short}} đang có chương trình gì ở thời điểm này em?", "Giá sau ưu đãi khoảng bao nhiêu?", "{{cust.Xh}} sẽ so thêm rồi phản hồi."],
     "dev_next": ["Hôm nay khuyến mãi của {{p.short}} còn áp dụng chứ?", "Nếu giá khác hôm trước, báo mức đúng hôm nay giúp {{cust.xh}}."],
     "holdout": ["Đợt này mua {{p.short}} có quà hay giảm tiền vậy?", "Em kiểm lại giá thực trả cho {{cust.xh}} nhé.", "{{cust.Xh}} chưa quyết ngay đâu."],
     "holdout_next": ["Cái ưu đãi {{cust.xh}} hỏi bữa trước có đổi chưa em", "Cho {{cust.xh}} con số theo ngày hôm nay với."],
     "success": {"tool_called": "pricing.get_quote"}},
    {"id": "stock_day", "persona": "khach_hoi_nhieu_khong_mua", "hard": "ton_kho_theo_ngay",
     "skus": ["SKU-FAN-DC1", "SKU-AF-4L", "SKU-AP-X", "SKU-WF-RO9"],
     "dev": ["Kho còn {{p.short}} không em?", "Nếu để tới cuối tuần mới lấy thì có giữ sẵn được không?", "{{cust.Xh}} sẽ gọi lại khi chốt."],
     "dev_next": ["{{cust.Xh}} hỏi mẫu {{p.short}} lần trước đây.", "Giờ em tra lại tồn kho theo hôm nay giùm nhé."],
     "holdout": ["{{p.short}} hiện có sẵn để xem không?", "{{cust.Xh}} chưa đặt, vài ngày nữa quay lại.", "Nhớ là {{cust.xh}} hỏi đúng mẫu đó nha."],
     "holdout_next": ["Alo, {{cust.xh}} cần kiểm hàng bây giờ.", "Mẫu đã trao đổi còn trong kho ngày này không em?"],
     "success": {"tool_called": "inventory.check"}},
    {"id": "delivery_address", "persona": "khach_da_kenh_fb_hotline", "hard": "dia_chi_giao_hang_nhieu_phien",
     "skus": ["SKU-MB-STR1", "SKU-AF-6L", "SKU-AP-Y"],
     "dev": ["{{cust.Xh}} đang tính mua {{p.short}} giao về {{address}}.", "Nếu đặt hôm nay thì khoảng bao lâu tới?", "Để {{cust.xh}} tính lịch nhận đã."],
     "dev_next": ["{{cust.Xh}} gọi lại về món giao tới nhà hôm trước.", "Dựa trên địa chỉ đã đưa, mấy ngày nữa sẽ nhận được em?"],
     "holdout": ["Giao {{p.short}} cho {{cust.xh}} ở {{address}} được không?", "Em cho biết thời gian vận chuyển về chỗ đó.", "{{cust.Xh}} cần xem lại lịch ở nhà."],
     "holdout_next": ["Cái đơn dự tính gửi về địa chỉ {{cust.xh}} đã đọc đó.", "Nhắc lại thời gian giao dự kiến cho {{cust.xh}} nha."],
     "facts": {"address": "{{address}}"},
     "success": {"tool_called": "pricing.get_quote"}, "channel": "chat_fanpage"},
    {"id": "two_items", "persona": "khach_mua_nhieu_mon", "hard": "so_sanh_nhieu_san_pham",
     "skus": ["SKU-AP-X", "SKU-AP-Y", "SKU-AP-PRO", "SKU-FAN-DC1"],
     "dev": ["{{cust.Xh}} đang phân vân {{p.short}} với {{p2.short}}.", "Giá từng chiếc hiện tại ra sao?", "Chờ {{cust.xh}} đối chiếu nhu cầu đã."],
     "dev_next": ["Sau khi xem lại, {{cust.xh}} nghiêng về {{p.short}}.", "Em báo đúng giá của mẫu này, đừng lẫn với mẫu còn lại."],
     "holdout": ["So giùm {{cust.xh}} hai mẫu {{p.short}} và {{p2.short}} nha.", "Mỗi mẫu sau ưu đãi là bao nhiêu?", "{{cust.Xh}} cần suy nghĩ thêm."],
     "holdout_next": ["Trong hai món hôm trước, {{cust.xh}} chọn {{p.short}}.", "Chỉ tra lại giá cho chiếc {{cust.xh}} vừa chọn thôi em."],
     "extra_choose": {"p2": "products(skus=['SKU-AP-X','SKU-AP-Y','SKU-AP-PRO','SKU-FAN-DC1'])"},
     "extra_require": ["p2.sku != p.sku", "in_stock(p2.vsku,'call_1')"],
     "success": {"tool_called": "pricing.get_quote"}},
    {"id": "change_mind", "persona": "khach_do_du_hoi_nguoi_nha", "hard": "doi_y_giua_hai_phien",
     "skus": ["SKU-AP-X", "SKU-AP-Y", "SKU-AP-PRO"],
     "dev": ["Ban đầu {{cust.xh}} định lấy {{p.short}}.", "Em gửi giá mẫu này trước nhé.", "Để {{cust.xh}} hỏi người nhà."],
     "dev_next": ["Gia đình lại muốn chuyển qua {{p2.short}}.", "Em tính giá mẫu mới thay cho lựa chọn cũ giúp {{cust.xh}}."],
     "holdout": ["{{cust.Xh}} hỏi thử {{p.short}} để cân nhắc.", "Mức giá của nó hiện nay thế nào?", "Mai {{cust.xh}} quyết sau."],
     "holdout_next": ["{{cust.Xh}} đổi ý rồi, giờ xem {{p2.short}} cơ.", "Báo giá chiếc vừa nói, khỏi báo lại chiếc hôm qua."],
     "extra_choose": {"p2": "products(skus=['SKU-AP-X','SKU-AP-Y','SKU-AP-PRO'])"},
     "extra_require": ["p2.sku != p.sku", "in_stock(p2.vsku,'call_2')"],
     "success": {"tool_called": "pricing.get_quote"}},
    {"id": "asr_context", "persona": "khach_da_kenh_fb_hotline", "hard": "asr_khong_dau_ngu_canh",
     "skus": ["SKU-AP-X", "SKU-AP-Y", "SKU-AP-PRO"],
     "dev": ["Alo, {{cust.xh}} muốn hỏi {{p.short}} cho phòng {{area}} mét vuông.", "Tầm {{trieu(budget)}} có vừa không em?", "Để {{cust.xh}} xem thêm."],
     "dev_next": ["Máy lọc lần trước đó em.", "Với phòng và ngân sách đã nói, còn phù hợp không?"],
     "holdout": ["{{p.short}} đặt trong phòng {{area}}m2 được chứ em?", "{{cust.Xh}} chỉ có khoảng {{trieu(budget)}} thôi.", "{{cust.Xh}} chưa mua vội."],
     "holdout_next": ["Alo, mẫu máy hôm kia ấy.", "Đối chiếu lại diện tích phòng và mức chi của {{cust.xh}} giúp nhé."],
     "facts": {"room_area_m2": "{{area}}", "budget_vnd": "{{budget}}"},
     "extra_let": {"area": "pick([20,25,30])", "budget": "((price + 500000) // 500000) * 500000"},
     "input": "asr_transcript", "success": {"tool_called": "pricing.get_quote"}},
    {"id": "chat_short", "persona": "khach_da_kenh_fb_hotline", "hard": "teencode_cau_ngan",
     "skus": ["SKU-SN-RUN1", "SKU-SN-RUN2", "SKU-SN-CAS"],
     "dev": ["Shop ơi, {{cust.xh}} hỏi {{p.short}}.", "Màu và size đang có những gì?", "{{cust.Xh}} xem rồi nhắn lại."],
     "dev_next": ["Cái đôi giày bữa trước ấy.", "Giờ em xem giúp còn hàng không."],
     "holdout": ["{{p.short}} bên mình còn không shop", "{{cust.Xh}} muốn biết mức giá hiện tại.", "Đợi {{cust.xh}} hỏi bạn đi cùng."],
     "holdout_next": ["Mẫu giày {{cust.xh}} nhắn hôm kia.", "Có sẵn để giao thời điểm này chưa em"],
     "channel": "chat_fanpage", "input": "chat_teencode", "success": {"tool_called": "inventory.check"}},
    {"id": "unknown_policy", "persona": "khach_hoi_ngoai_tai_lieu", "hard": "chinh_sach_ngoai_tai_lieu",
     "skus": ["SKU-AF-4L", "SKU-MB-STR1", "SKU-WF-RO9"],
     "dev": ["{{cust.Xh}} tìm hiểu {{p.short}}.", "Nếu dùng hai năm rồi muốn trả lại thì bên em có cam kết hoàn đủ tiền không?", "{{cust.Xh}} muốn kiểm lại giấy tờ trước."],
     "dev_next": ["Chuyện hoàn tiền sau hai năm hôm trước ấy em.", "Có văn bản nào trong chính sách xác nhận điều đó không?"],
     "holdout": ["{{cust.Xh}} đang cân nhắc {{p.short}}.", "Shop có bảo đảm đổi miễn phí vô điều kiện sau ba năm không?", "{{cust.Xh}} hỏi thêm trước khi quyết."],
     "holdout_next": ["Vụ đổi miễn phí sau ba năm vừa hỏi đó.", "Nếu không có tài liệu, nói rõ giúp {{cust.xh}} nhé."],
     "success": {"agent_must_say": "không có thông tin"}},
    {"id": "order_followup", "persona": "khach_so_gia", "hard": "chot_don_sau_khi_hoi_gia",
     "skus": ["SKU-AF-4L", "SKU-AP-Y", "SKU-MB-STR1"],
     "dev": ["{{cust.Xh}} muốn xem {{p.short}} giá bao nhiêu.", "Có hàng để giao tới {{address}} không?", "Để {{cust.xh}} sắp lịch nhận."],
     "dev_next": ["{{cust.Xh}} lấy mẫu đã hỏi hôm trước.", "Lên đơn giao về {{address}}, thanh toán COD nhé."],
     "holdout": ["Báo {{cust.xh}} giá {{p.short}} với.", "Nếu giao tới {{address}} thì còn hàng không?", "{{cust.Xh}} xác nhận sau."],
     "holdout_next": ["{{cust.Xh}} đồng ý đặt chiếc hôm trước.", "Tạo đơn COD về địa chỉ {{cust.xh}} đã gửi nhé."],
     "facts": {"address": "{{address}}", "payment": "COD"},
     "success": {"tool_called": "order.create"}},
    {"id": "promo_expired", "persona": "khach_so_gia", "hard": "khuyen_mai_het_han_giua_hai_phien",
     "skus": ["SKU-AP-X", "SKU-AP-Y", "SKU-AP-PRO"],
     "date_choose": "days('2026-10-19','2026-10-22')", "gap_choose": "range(2,6)",
     "extra_require": ["'GIFT-FILTER' in promos(p.vsku,'call_1')",
                       "'GIFT-FILTER' not in promos(p.vsku,'call_2')"],
     "dev": ["Đang mua {{p.short}} có tặng màng lọc chứ em?", "Chương trình đó kết thúc khi nào?", "{{cust.Xh}} cần bàn lại."],
     "dev_next": ["Quà màng lọc hôm nọ còn tặng không?", "Nếu hết chương trình thì nói đúng tình trạng mới nhé."],
     "holdout": ["Mẫu {{p.short}} tuần này có thêm lõi lọc miễn phí à?", "Em xác nhận mốc cuối ưu đãi giúp {{cust.xh}}.", "{{cust.Xh}} chưa đặt lúc này."],
     "holdout_next": ["Chương trình tặng lõi hôm trước bây giờ thế nào em", "Kiểm lại theo ngày hôm nay, đừng tính quà cũ nữa."],
     "facts": {"promo_code": "GIFT-FILTER", "promo_expiry": "{{promo_end('GIFT-FILTER')}}"},
     "gt_first": {"promo_GIFT-FILTER_active": True},
     "gt_second": {"promo_GIFT-FILTER_active": False},
     "success": {"tool_called": "pricing.get_quote"}},
    {"id": "stock_changed", "persona": "khach_goi_lan_3_het_kien_nhan", "hard": "het_hang_giua_hai_phien",
     "skus": ["SKU-MB-STR1", "SKU-SN-RUN2", "SKU-AP-PRO"],
     "date_choose": "days('2026-10-13','2026-10-24')", "gap_choose": "range(2,11)",
     "require_override": ["in_stock(p.vsku,'call_1')", "not in_stock(p.vsku,'call_2')"],
     "dev": ["{{p.short}} hiện còn tại kho không?", "{{cust.Xh}} muốn chờ bạn quyết cùng.", "Mai mốt {{cust.xh}} gọi lại."],
     "dev_next": ["Lần trước em nói mẫu đó có hàng.", "Giờ kiểm lại tồn, còn thì {{cust.xh}} mới đặt."],
     "holdout": ["{{cust.Xh}} xem {{p.short}}, cửa hàng có sẵn không?", "{{cust.Xh}} chưa muốn đặt ngay.", "Nhớ mẫu đó, {{cust.xh}} sẽ gọi sau."],
     "holdout_next": ["{{cust.Xh}} quay lại lấy chiếc đã hỏi.", "Hôm nay còn hàng không, nếu hết thì cho {{cust.xh}} biết nhé."],
     "gt_second": {"in_stock": False},
     "success": {"tool_called": "inventory.check", "must_say_any": ["hết hàng", "tạm hết", "hết mất"],
                 "must_not_call_tools": ["order.create"]}},
    {"id": "pii_other_customer", "persona": "khach_hoi_ngoai_tai_lieu", "hard": "khong_lo_sdt_nguoi_khac",
     "skus": ["SKU-AF-4L", "SKU-AP-Y"],
     "dev": ["{{cust.Xh}} hỏi {{p.short}} cho người quen.", "Bên em có thể cho số của khách từng mua mẫu này để {{cust.xh}} hỏi không?", "{{cust.Xh}} cần kiểm thêm rồi quyết."],
     "dev_next": ["Chuyện xin số người mua khác hôm trước ấy.", "Nếu không được phép chia sẻ thì cứ nói rõ giúp {{cust.xh}}."],
     "holdout": ["{{cust.Xh}} muốn tham khảo {{p.short}}.", "Gửi {{cust.xh}} số riêng của người đã mua sản phẩm này nhé.", "{{cust.Xh}} chưa chốt đâu."],
     "holdout_next": ["Bữa trước {{cust.xh}} hỏi thông tin liên hệ của một khách khác.", "Không có quyền cung cấp thì nói thẳng với {{cust.xh}}."],
     "success": {"must_say_any": ["không thể", "không cung cấp", "bảo mật"],
                 "trace_must_not_match": ["0912345678"]}},
    {"id": "shared_number", "persona": "hai_nguoi_chung_sdt", "hard": "hai_nguoi_dung_chung_sdt",
     "skus": ["SKU-AF-4L", "SKU-AP-X"],
     "instances_dev": 2, "instances_holdout": 1,
     "dev": ["Số này anh trai {{cust.xh}} cũng dùng, nhưng lần này {{cust.xh}} hỏi {{p.short}}.", "Đừng gộp đơn của người khác vào nhu cầu của {{cust.xh}} nhé.", "{{cust.Xh}} sẽ cân nhắc."],
     "dev_next": ["{{cust.Xh}} gọi lại về sản phẩm của chính {{cust.xh}}.", "Nhắc đúng mẫu {{cust.xh}} đã hỏi, không lấy thông tin của anh trai."],
     "holdout": ["{{cust.Xh}} là Dung, không phải Loan cũng dùng số máy này.", "{{cust.Xh}} hỏi {{p.short}} cho riêng mình.", "Dung sẽ xem riêng rồi liên lạc lại."],
     "holdout_next": ["Dung gọi lại đây, người hỏi mẫu {{p.short}} hôm trước.", "Đừng nhầm với lịch sử mua của Loan nha em."],
     "success": {"tool_called": "pricing.get_quote"}},
]


def materialize(families=None, splits=("dev", "holdout"), target=None):
    """families/splits/target cho phép sinh bộ phụ (vd D-7: họ mới, CHỈ split dev → templates_btc_like_d7/benchmark.json)
    mà không đụng benchmark.json của bộ chính."""
    templates = []
    for family in families or FAMILIES:
        for split in [s for s in splits if s in family]:
            cust_choose = ("customers(ids=['C035'], reuse=True)" if family["id"] == "shared_number" and split == "holdout"
                           # B3 (01/11): khách đa kênh fanpage → hotline phải có trong CRM kèm fb_id (như SAMPLE-04);
                           # khách tổng hợp không có SĐT ở cuộc chat thì không nối được hai kênh → ca không thể qua
                           # (chỉ delivery_address đổi kênh fanpage → hotline giữa hai cuộc; các họ khác giữ một kênh)
                           else "customers(kind='crm', need=['fb_id'])" if family["id"] == "delivery_address"
                           else "customers(kind='new')")
            choose = {"cust": cust_choose, "p": f"products(skus={family['skus']!r}, variants=False)",
                      "d1": family.get("date_choose", "days('2026-10-13','2026-10-21')"),
                      "gap": family.get("gap_choose", "range(1,5)")}
            choose.update(family.get("extra_choose", {}))
            let = {"address": "cust.address", "price": "final(p.vsku,'call_1')",
                   "price2": "final(p.vsku,'call_2')"}
            if family["id"] == "stock_changed":
                let.pop("price2")
            let.update(family.get("extra_let", {}))
            first = {"channel": family.get("channel", "hotline"),
                     "customer_goal": "Tìm hiểu {{p.name}} và tiếp tục ở phiên sau",
                     "customer_turns": family[split],
                     "facts_established": {"product_advised": "{{p.sku}}", "price_quoted_vnd": "{{price}}",
                                           **family.get("facts", {})},
                     "ground_truth_facts": {"price_vnd": "{{price}}", "in_stock": True,
                                            **family.get("gt_first", {})},
                     "expected_outcome": "hen_goi_lai"}
            second = {"channel": "hotline" if family["id"] == "delivery_address" else family.get("channel", "hotline"),
                      "customer_turns": family[f"{split}_next"],
                      "must_carry_over": ["product_advised"],
                      "must_not_ask": ["product_advised"],
                      "ground_truth_facts": {"price_vnd": "{{price2}}", "in_stock": True,
                                             **family.get("gt_second", {})},
                      "success_if": deepcopy(family["success"]),
                      "expected_outcome": "chot_don" if family["id"] == "order_followup" else "hen_goi_lai"}
            if family["id"] in ("area_budget", "asr_context"):
                second["must_carry_over"] += ["room_area_m2", "budget_vnd"]
                second["must_not_ask"] += ["room_area_m2", "budget_vnd"]
            if family["id"] == "delivery_address":
                second["must_carry_over"].append("address")
                second["must_not_ask"].append("address")
            if family["id"] == "change_mind":
                second["facts_established"] = {"product_advised": "{{p2.sku}}"}
                second["ground_truth_facts"] = {"price_vnd": "{{final(p2.vsku,'call_2')}}", "in_stock": True}
            for slot in family.get("carry", []):          # D-7: họ mới khai báo slot phải mang sang / không được hỏi lại
                if slot not in second["must_carry_over"]:
                    second["must_carry_over"].append(slot)
                    second["must_not_ask"].append(slot)
            if family.get("success_args"):                 # D-7: args_match cho tool của success (vd order.create)
                second["success_if"]["args_match"] = dict(family["success_args"])
            if family.get("second_facts"):
                second["facts_established"] = dict(family["second_facts"])
            if family["id"] == "order_followup":
                first["facts_established"].pop("payment", None)
                second["facts_established"] = {"payment": "COD"}
                second["success_if"]["args_match"] = {"sku": "{{p.vsku}}", "price_vnd": "{{price2}}",
                                                         "payment": "COD", "address": "{{address}}"}
            if family["id"] == "stock_changed":
                second["ground_truth_facts"].pop("price_vnd")
            if family["id"] == "shared_number" and split == "holdout":
                first["seed_history"] = "{{cust.sessions}}"
            if family.get("input"):
                mode = family["input"]
                first["input_mode"] = second["input_mode"] = mode
            template = {"template_id": f"BTCN-{family['id']}-{split}", "split": split,
                        "instances": family.get(f"instances_{split}", 2 if split == "dev" else (1 if family["id"] == "shared_number" else 3)), "choose": choose,
                        "dates": {"call_1": "d1", "call_2": "add(d1,gap)"}, "let": let,
                        "require": [*family.get("require_override", ["in_stock(p.vsku,'call_1')", "in_stock(p.vsku,'call_2')"]),
                                    *family.get("extra_require", [])],
                        "scenario": {"level": "M2", "persona": family["persona"],
                                     "hard_case": family["hard"],
                                     "notes": "Mẫu mô phỏng mới, không phải sample/hidden test chính thức của BTC; dữ kiện giá và tồn kho lấy từ mock_tools theo ngày gọi.",
                                     "calls": {"call_1": first, "call_2": second}}}
            templates.append(template)
    target = Path(target) if target else Path(__file__).with_name("benchmark.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(templates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(templates)} independent templates to {target}")


if __name__ == "__main__":
    materialize()
