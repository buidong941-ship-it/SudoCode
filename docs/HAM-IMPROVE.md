# `improve/`: khung cơ chế cải tiến (plan 01/11, mục D)

Phần này **tách biệt hoàn toàn với core**. `improve/` chỉ đọc trace và report đã chấm, rồi quản lý đề xuất. Nó không import `harness/`, `core/`, `eval/`, `mcp_servers/`, và chiều ngược lại cũng vậy. `tests/improve_check.py` kiểm tra cả hai chiều import này. Hiện agent **chưa nạp** gì từ `improve/`. Điểm nối duy nhất là `improve/loader.py`, chỉ đọc `approved/`. Điểm nối này sẽ được móc vào agent ở mục E, sau ngày đóng băng, qua một cờ mặc định tắt. Khi cờ tắt, trace phải giống hệt bản không có cờ.

## Luồng

```
trace + report (dev) ─collect─► gaps.jsonl ─(Claude viết đề xuất)─► propose ─► pending/
                                                                             │ review approve/reject (--by bắt buộc)
                                                                             ▼
                              rounds/<vòng>/ ◄─round save─ approved/ ──loader──► agent (mục E)
                                    ▲                              │
                                    └──── check / rollback (D5) ◄──┘ report vòng mới
```

## Lệnh

| Việc | Lệnh |
|---|---|
| D1: gom lỗi | `python -m improve collect --trace <dev>/full.jsonl --report <dev>/report.json [--append]` |
| Xem gap | `python -m improve gaps [--type no_info\|guardrail\|repeat_question\|customer_repeat\|claim_wrong\|task_fail]` |
| D2: thêm đề xuất | `python -m improve propose de_xuat.json` (một đề xuất hoặc danh sách) |
| D3: duyệt | `python -m improve review`, `review show <id>`, `review approve <id> --by <tên> --reason ...`, `review reject ...`, `review -i --by <tên>` |
| D4: so vòng | `python scripts/compare_rounds.py --round improve/rounds/r0 --round improve/rounds/r1 [--spread c5.json]` |
| D5: chụp vòng | `python -m improve round save r0 --report dev=<report> --report holdout=<report> --by <tên>` |
| D5: quyết quay lui | `python -m improve check --prev r0 --report dev=<report mới> [--apply --by <tên>]`. Mã thoát 2 nghĩa là nên quay lui |
| D5: quay lui tay | `python -m improve rollback --to r0 --by <tên> --reason ...` |
| Tình trạng | `python -m improve status` |

Mọi lệnh đều nhận `--root DIR` hoặc env `IMPROVE_ROOT`. Test dùng thư mục tạm, không đụng `improve/` thật.

## Đề xuất

Mỗi đề xuất có dạng `{id, kind, title, payload, source_gaps, author, created_at, status, review}`. `id = P-<kind>-<sha1 nội dung>`, nên đề xuất trùng nội dung không bị tạo lần hai.

| kind | payload | Dùng cho |
|---|---|---|
| `faq` | `topic, question, answer, policy_refs[]` | Knowledge Gap Loop: bổ sung kiến thức, **không** sửa `policy/` của BTC |
| `playbook` | `trigger, instruction` | cách xử lý một tình huống |
| `exemplar` | `customer_text, agent_text, goals[], source` | Exemplar Bank (few-shot) |
| `cue` | `slot, pattern` | cue lexicon cho extractor |

Ba luật chặn ngay từ lúc đề xuất. `loader` kiểm lại các luật này khi nạp, nên file `approved/` bị sửa tay cho vi phạm luật cũng bị bỏ qua:

- `faq`, `playbook` và `exemplar` không được chứa số tiền, phần trăm, "giảm/bớt + số" hay số điện thoại. Giá và KM chỉ được lấy từ tool.
- `exemplar` không được là câu "hứa để chốt" (cam kết, đảm bảo, chắc chắn, 100%…).
- `cue` phải là regex hợp lệ.

## Gap (D1)

| type | Nguồn | Ghi chú |
|---|---|---|
| `no_info` | trace, goal `no_info` | Kèm lý do của nhánh planner (B7). Đây là đầu vào chính của Gap Loop |
| `guardrail` | trace, guardrail action/problems | subtype là `regenerated`, `safe_template`, `coverage_template` hoặc `llm_error_template` |
| `customer_repeat` | trace, cue "như anh đã nói", "nói rồi"… | Dấu hiệu khách phải nhắc lại thông tin |
| `repeat_question` | report, ví dụ RQR | |
| `claim_wrong` | report, ví dụ HR | |
| `task_fail` | report, failures TSR | Kèm toàn bộ các lượt của cuộc gọi |

Chỉ gom từ **dev**: đường dẫn hay `run_id` có `holdout` hoặc `out_nat/test` đều bị từ chối (`LeakError`). Report holdout vẫn được dùng ở `round save`, `check` và `compare_rounds`, vì đó là bước đo chứ không phải feedback.

Chạy thử trên trace dev của lần ③ ra 89 gap: 70 gap guardrail (34 `coverage_template`, 31 `regenerated`, 5 `safe_template`), 9 `claim_wrong`, 2 `repeat_question`, 8 `task_fail` và 0 `no_info`. Lần ③ chưa có B1, nên chưa có `no_info`.
