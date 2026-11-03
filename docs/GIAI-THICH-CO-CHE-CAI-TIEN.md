# Giải thích cơ chế cải tiến (02/11/2026)

Tài liệu giải thích, không phải quyết định mới. Kế hoạch và việc cụ thể nằm ở [PLAN-2026-11-01.md](PLAN-2026-11-01.md) mục D và E. Yêu cầu của đề nằm ở mục C.5 của [đề bài](../debaiSUDO.md). Code: `improve/` (gom lỗi, đề xuất, duyệt, nạp) và `harness/improve_hook.py` (điểm nối duy nhất với agent, tắt khi `IMPROVE_DIR` rỗng).

## 1. Tóm tắt một câu

Lượt lỗi (hoặc lượt tốt) trên **dev** → rút ra một **mẩu kiến thức hoặc hướng dẫn dùng lại được** → **người duyệt** → agent nạp bản đã duyệt → lần sau gặp **tình huống tương tự** (không nhất thiết cùng câu chữ) thì dùng → so chỉ số với vòng trước, tụt thì quay lui.

Cơ chế này **không** lưu câu trả lời đã sửa để phát lại nguyên văn.

## 2. Vòng đầy đủ

```
trace dev ──► improve/collect.py ──► gaps.jsonl ──► đề xuất (improve/pending/) ──► NGƯỜI DUYỆT (sửa / duyệt / loại)
                                                                                     │
vòng N+1 ◄── agent nạp improve/approved/ (qua harness/improve_hook.py) ◄─────────────┘
   │
   └─► so sánh với vòng N trên cùng bộ test: TSR tụt quá 3 điểm hoặc HR tăng → quay lui về bộ approved/ trước đó
```

- Feedback chỉ lấy từ **dev**. `improve/collect.py` từ chối mọi đường dẫn chứa `holdout` hoặc `out_nat/test` (`LeakError`).
- Các loại gap mà `collect.py` gom:

| Loại gap | Nghĩa |
|---|---|
| `no_info` | Agent trả "chưa có thông tin". Đây là đầu vào chính của Knowledge Gap Loop |
| `guardrail` | Guardrail phải sinh lại câu hoặc thay bằng câu mẫu |
| `repeat_question` | Agent hỏi lại slot khách đã nói |
| `customer_repeat` | Khách phải nhắc lại thông tin ("như chị nói rồi", "lúc nãy anh đã nói") |
| `claim_wrong` | Claim giá hoặc KM sai |
| `task_fail` | Cuộc gọi trượt TSR |

## 3. Thứ được lưu: bốn loại đề xuất

| Loại | Lưu cái gì | Lần sau dùng khi nào | Nguồn |
|---|---|---|---|
| `faq` | Nội dung trả lời cho một chủ đề (ví dụ: xuất hóa đơn VAT) | Câu khách **khớp chủ đề**, kể cả khác câu chữ (trùng từ khóa ≥ 50% và ít nhất 2 từ) | Lỗi |
| `playbook` | Hướng dẫn xử lý một tình huống (ví dụ: khách xin thông tin người khác thì từ chối và giải thích) | Câu khách khớp trigger | Lỗi |
| `cue` | Cụm từ nhận biết slot mà luật đã bỏ sót | Mọi câu có cụm đó. Cue loại này **chỉ mở cổng cho LLM xem lại**, không tự gán giá trị slot | Lỗi |
| `exemplar` | Câu mẫu về văn phong của agent | Lượt có cùng goal, tối đa 2 câu | Thành công |

Ở mọi loại, generator vẫn viết câu mới mỗi lượt. Giá, KM và tồn kho vẫn chỉ lấy từ tool.

**Ví dụ:**
1. Vòng 0, khách hỏi "bên em có xuất hóa đơn VAT không?", agent trả "chưa có thông tin".
2. `collect.py` ghi lượt này thành gap `no_info`. Từ gap đó, một đề xuất `faq` "hóa đơn VAT" được soạn và đưa vào `pending/`.
3. Người duyệt **kiểm hoặc bổ sung nội dung đúng từ chính sách thật**, rồi duyệt.
4. Vòng 1, một khách khác hỏi "mua máy này lấy VAT được không em" thì agent trả lời được, dù câu chữ khác hẳn.

## 4. Vì sao không phát lại đúng câu đã sửa

- **Học tủ:** chỉ sửa đúng câu trong bộ test thì vòng 1 trên bộ đó sẽ đẹp, nhưng không mang sang được bộ test ẩn của BTC. Giám khảo sẽ thấy ngay khi phản biện. Vì vậy vòng 0 và vòng 1 đo trên cả dev lẫn holdout (bộ chưa từng nhìn).
- **Bịa giá:** câu trả lời cũ có thể chứa giá hoặc KM đã hết hạn. Loader (`improve/loader.py`) chặn khi nạp mọi đề xuất có số tiền, SĐT hay câu hứa hẹn.
- **Không bịa kiến thức:** nếu chính sách thật không có thông tin, người duyệt không được tự viết câu trả lời. Khi đó đề xuất đúng là một `playbook` kiểu "nói không có thông tin và chuyển nhân viên".
- **Không học "hứa đại để chốt":** một cuộc gọi chốt được đơn nhưng có claim sai thì không bao giờ được lấy làm exemplar.

## 5. Học từ hai phía

| | Knowledge Gap Loop | Exemplar Bank |
|---|---|---|
| Học từ | Lỗi: no-info, guardrail chặn, hỏi lại, khách nhắc lại, claim sai, scenario trượt | Thành công: lượt thuộc scenario đạt TSR, 0 vi phạm, 0 claim sai |
| Tạo ra | `faq`, `playbook`, `cue` | `exemplar` |
| Mức đề bài | M1 (đề khuyên làm đầu tiên) | M1 |

Có cả hai cơ chế thì đạt mức M1 và đã đi được một nửa yêu cầu M2 (M2 cần ít nhất 2 cơ chế, ít nhất 3 vòng, kèm phân tích các ca cải tiến gây hại).

## 6. Phân biệt cue của rule decision với few-shot của cơ chế cải tiến

| | Cue (rule decision) | Few-shot / exemplar (cơ chế cải tiến) |
|---|---|---|
| Là gì | Cụm từ trong **lời khách**: "ship về", "giao đến", "ck trước" | Cả **câu trả lời của agent** lấy từ cuộc gọi tốt |
| Phía | Đầu vào: hệ thống **hiểu** khách | Đầu ra: hệ thống **nói** với khách |
| Ai dùng | **Code** (luật extractor, `rule_confidence`). Không LLM nào đọc nó | **LLM generator**, qua `plan["EXEMPLARS"]` trong prompt |
| Quyết định gì | Câu có slot nào, giá trị bao nhiêu, CERT có đạt không, có phải gọi Jev/Qwen không. Từ đó ảnh hưởng tới bộ nhớ và planner | **Chỉ văn phong**: cách diễn đạt, độ dài, xưng hô. Không đổi goal, tool, giá hay slot |
| Kết quả | Tất định | Gián tiếp, câu ra vẫn dao động |
| Ảnh hưởng chỉ số | CCR, RQR, TSR | TSR, độ tự nhiên khi demo |
| Lấy từ đâu | `data_reference` (CSConDa), câu Claude tự sinh, người duyệt | Lượt agent đạt chuẩn trên dev |

**Ví dụ một lượt:** khách nói "ship về 12 Lê Lợi giúp chị nha".
- **Cue** "ship về" giúp luật nhận ra `address = 12 Lê Lợi` và ghi vào bộ nhớ.
- **Exemplar** của goal xác nhận đơn chỉ giúp generator viết câu xác nhận cho tự nhiên.

Bỏ cue thì hệ thống **hiểu sai**. Bỏ exemplar thì hệ thống chỉ **nói kém tự nhiên hơn**.

**Cue có hai nguồn, cách tính điểm khác nhau:**
1. **Lexicon nền** `harness/lexicon/slots.json`, làm **trước** ngày đóng băng. Đây là công việc phát triển, **không** tính là cải tiến.
2. **Cue do vòng cải tiến đề xuất** (loại `cue` trong `improve/approved/`), làm **sau** ngày đóng băng và có người duyệt. Cái này tính là cải tiến. Cue loại này chỉ mở cổng cho LLM, nên một cue sai không thể ghi bừa slot vào bộ nhớ.

## 7. Cách chấm (tiêu chí 5, 13%)

Đề không chia nhỏ 13% này. Theo câu chữ của đề, giám khảo kiểm ba điều:
1. Vòng lặp **hoạt động thật**: có code chạy được và artifact thật (`gaps.jsonl`, đề xuất, log duyệt).
2. **Có số**: bảng vòng 0 so với vòng 1 trên cùng bộ test, cùng model và tham số.
3. **Có người kiểm soát**: bước duyệt, log ai duyệt cái gì, cơ chế quay lui.

Điểm thưởng liên quan: ablation chỉ ra cơ chế nào thật sự tạo khác biệt; tầng Playbook tự đúc kết cách xử lý phản đối theo persona.
