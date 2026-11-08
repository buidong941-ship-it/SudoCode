# Triển khai Jev planner và goals/facts — 08/11/2026

Theo kế hoạch đã duyệt và điều chỉnh trong luồng chính: chỉ Full; không chạy 7 sample BTC, không chạy baseline; không dùng latency làm tiêu chí chấp nhận. Toàn bộ kiểm thử chạy Kaggle. Dừng ở bước nạp API DeepSeek/Jev, không thực hiện phép đo API thật.

## Luồng mới

`customer rules/CERT → LLM trích slot → prepare không ghi giỏ → snapshot → selector actions+flags → executor kiểm quyền/điều kiện → goals/facts validator → generator → guardrail/coverage → question/claim → memory/trace`.

- `PLANNER_SELECTOR=rules` giữ bảng làm mốc. `qwen`/`jev` dùng executor mới; `PLANNER_BACKEND` vẫn là fallback cũ, không thay selector.
- `JEV_SIMULATED=1` dùng Qwen cho mọi phần Jev; chặn khởi tạo client thật. Confidence giả lập để null trong quyết định, không coi boolean của Qwen là xác suất Jev.
- `GOAL_CONTRACT=1` bật kiểm registry và bằng chứng tool trước generator. Mốc tắt cờ vẫn dùng notes cũ.
- `EXTRACTOR_NO_JEV=1` bỏ Jev customer/claim; giữ question bằng cờ độc lập. Chứng nhận question không chứng nhận claim. Slot giữ span-check và khóa CERT2; claim giữ chính sách hợp nhất có dẫn chứng.
- Trace có `planner.semantic.selected_actions`, `executed_actions`, `blocked`, lỗi/fallback, backend thực tế; `planner.contract` có lỗi và provenance; `api_audit` ghi bộ đếm giả lập/chặn API.
- Tham số tool do code điền từ slot, memory, catalog và kết quả tool. Selector không sinh mã đơn/giá/tham số thực thi.

## Action → executor → kết quả

| Action | Đường thực thi | Goal chính / dữ kiện |
|---|---|---|
| ask_price | quote | quote / ask_size_for_price; quote |
| product_advice | recommend và quote | ask_need / recommend / quote; need_slots_missing, quote |
| add_to_cart | cart_add, cart_quote | cart_total; cart |
| cart_total | cart_quote | cart_total; cart |
| place_order | plan_order | ask_address / ask_payment / ask_variant / out_of_stock / cod_limit / order_created / order_exists / order_failed |
| give_delivery_info | tiếp tục pending buy, hoặc hỏi xác nhận | kết quả plan_order / confirm_order / ask_product |
| change_order_address | order.update update_address | address_updated / order_failed; address_update |
| exchange_order | plan_order_change action_override exchange | ask_new_size / exchange_offer / order_updated / exchange_window_passed / order_failed |
| return_order | plan_order_change action_override return | order_updated / exchange_window_passed / order_failed |
| order_status | order_status | order_status / order_not_found; orders |
| policy_question | knowledge.search theo ngày đơn khi có | policy_answer / no_info; policy |
| schedule_callback | plan_callback | callback_scheduled; callback giờ/ngày thực tế |
| defer_decision | defer_ack | defer_ack |
| greeting_closing | code theo lượt | greet / closing |
| unclear | ask_repeat | ask_repeat / chuyển nhân viên theo hậu xử lý |
| cancel_order | cancel_request, chuyển nhân viên vì mock không có hủy | cancel_handoff; không hứa đã hủy |
| request_handoff | handoff_scope | handoff và bản bàn giao |

Đa action được khử trùng và chạy theo thứ tự phụ thuộc. Thêm giỏ trước tính tổng; chốt loại add_to_cart trùng và không tạo hai lần; chào không lấn át nghiệp vụ; hỏi chính sách không tự sửa đơn. Thiếu requires ghi blocked và hỏi thông tin phù hợp. Lỗi selector không chạy tool ghi dữ liệu. Lỗi executor không tự retry thao tác có kết quả chưa xác định.

Quyền/danh tính, proxy, nội bộ, xóa dữ liệu, y tế giữ kiểm bằng code; công cụ và guardrail hiện có tiếp tục áp dụng. Hạn đổi trả dùng planner_policy cho mọi selector mới, không chỉ Qwen. Generator dùng kết quả thực thi, không dùng action như bằng chứng thành công.

## Dữ liệu và job

- v3 dev: 81 kịch bản, là dev đã quan sát; không dùng làm đánh giá cuối độc lập.
- redteam: 14 kịch bản hiện có.
- `datagen/out_jev1108_new/dev`: 12 ca mới viết trước lần chạy, có seed/nguồn và SHA-256 tại manifest. Đây là dev bổ sung, không phải holdout hoặc dữ liệu BTC.
- function probe phần D và gold extractor: chỉ chẩn đoán; nhãn không truyền vào runtime.
- `JEV1108-SOURCE-MANIFEST.json`: hash source/data, không chứa khóa. Job thực tế còn có BUILD_INFO và cấu hình được runner lưu.

| Job | Account | Mục đích | Trạng thái |
|---|---|---|---|
| jev1108-contract-cpu | midzid | 6 nhóm kiểm tra hàm/hợp đồng, không sample/baseline | Hoàn thành, 6/6 qua; đã kéo kết quả |
| jev1108-s01 | carterbryleeaqul | Full v3 dev: mốc giả lập và hợp đồng goals/facts | Đã đẩy |
| jev1108-diagnostics | midzid | Probe action + gold extractor, Qwen giả lập | Đang đẩy |

Giai đoạn tiếp theo phụ thuộc kết quả: Full selector mới, sau đó Full extractor tách riêng; dev/redteam/câu mới. Không giữ thay đổi chỉ vì chỉ số đẹp hơn nếu vi phạm điều kiện bắt buộc. Không sửa đáp án, không mở holdout cũ để chọn cấu hình.

`scripts/jev1108_watch.py` chỉ báo trạng thái kết thúc/lỗi, tự tải output. Không in trạng thái lặp. `scripts/jev1108_api_ready.py` chỉ nạp các Secrets được đặt tên, ghi present/missing và dừng; không gọi model. `profiles/jev1108-api-pending.env` là cấu hình cho bước API tiếp theo, không chứa khóa.

Graphify CLI không có trong môi trường nên chưa query/update được graph. Không tự commit hoặc push Git. Các thay đổi có sẵn của người dùng được giữ; bản gốc những file migration đầu tiên có tại build/jev1108_original (không đóng gói).


## Completed and downloaded - 2026-11-08 17:55

All jobs COMPLETE. Re-downloaded s01, s23, final-sim and permissions-sim successfully. Raw artifacts: `runs/kaggle/jev1108-*`; official report aggregation: `runs/jev1108/quality.md` and `quality.json`.

V3 TSR: S0 rules=90.1%, S1 rules+contract=91.4%, S2 new selector=70.4%, S3 new selector+extractor=71.6%; final after fixes=66/81 (81.5%). Final CCR74.1%, RQR0%, price/promotion HR12.1%, official guardrail1. New selector has not exceeded rules. S2/S3 share a snapshot; final includes later fixes, so these are not all single-variable comparisons.

Final and permissions: redteam12/14 (85.7%), new dev11/12 (91.7%). Permissions: identity1/1, CPU10/10 groups. Final V3 predates the last identity gate; latest source has Full targeted regression27 scenarios, not another V3 run. CRM permissions require trusted transport/channel identity; self-declared contact phone cannot rebind CRM identity. Test includes a gate-bypass control.

Remaining failures: COD misclassified as give_delivery_info; RT-01 negative warranty statement still extracted as warranty36. RT-12 official regex matches trace although delivered agent_text refuses medical claims; scores and evaluator preserved. V3 still has order creation/update and price-memory errors. No production-readiness claim.

Diagnostics-fixed: claim52 and customer slot40 with no FP/FN on small gold set; question precision75%, recall100%, slot/type86.7%. Probe raw20/50, compatible20/39; taxonomy differs from old probe. These are Qwen simulations, not real Jev measurements.

No BTC7 samples, no latency acceptance, no live Jev/DeepSeek requests. API readiness stopped at credential_loading; DEEPSEEK_API_KEY and TYPESAFE_API_KEY absent, api_calls0. No Git commit/push.
