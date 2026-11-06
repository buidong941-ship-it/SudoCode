# Bảng tra hàm của `core/log.py`

[core/log.py](../core/log.py) dựng hệ thống log cho harness, trên thư viện `logging` chuẩn của Python. Mọi logger của project nằm dưới tên gốc `cc` (`cc.run`, `cc.agent`, `cc.router`, `cc.llm`, `cc.extract`, `cc.summary`, `cc.rag`, `cc.mcp`, `cc.memory`).

Log đi tới hai nơi:

| Nơi | Mức mặc định | Bật thêm |
|---|---|---|
| **Màn hình** (stderr) | WARNING trở lên: router dùng luật dự phòng, guardrail chặn, lỗi API, traceback | `run_eval.py -v` hiện thêm khối từng lượt (INFO) |
| **File `<out>.log`** cạnh trace | `--log-level` / biến `LOG_LEVEL`, mặc định INFO | `-v` hoặc `--log-level DEBUG`: kết quả tool đầy đủ, prompt, dòng HTTP |

Ba tính chất:
- **Không trộn dòng khi chạy song song.** Mỗi kịch bản gom log vào bộ nhớ (`capture`). `run_eval.py` ghi file lần lượt theo `scenario_id` sau khi mọi worker xong.
- **Mỗi dòng có nhãn vị trí** `[GEN-T01-01 call_2 t3]` (đặt bằng `set_context`), nên `grep` được đúng một lượt.
- **Che PII trên mọi dòng:** SĐT thành `098****714`, địa chỉ thành `[địa chỉ]` (`core/pii.mask_for_log`). Khóa API không bao giờ được log. Trace JSONL cho BTC chấm thì giữ nguyên.

Số dòng ứng với code ngày 18/10/2026.

**Ai dùng file này:** `run_eval.py` (`setup`, `capture`, `set_context`, `get`); mọi module có log gọi `get(<tên>)`: `harness/agent.py`, `harness/llm_extract.py`, `harness/rag.py`, `harness/mcp_client.py`, `harness/memory.py`, `core/llm/deepseek.py`, `core/llm/router.py`, `core/llm/summarizer.py`.

## 1. Hằng số và biến cấp module

| Tên | Ý nghĩa |
|---|---|
| `LOGGER` [:14](../core/log.py#L14) | Tên logger gốc: `"cc"` |
| `FMT` [:15](../core/log.py#L15) | Khuôn một dòng: `giờ mức tên-logger [nhãn] nội dung`, ví dụ `14:49:41 WARNING cc.run    [SAMPLE-01 call_1 t2] guardrail … → regenerated` |
| `_tag` [:16](../core/log.py#L16) | Nhãn vị trí hiện tại, chung cho cả tiến trình; `set_context` ghi, `_TagFilter` đọc |
| `HTTP_LIBS` [:17](../core/log.py#L17) | Thư viện HTTP được cho log ở mức INFO khi bật DEBUG: `httpx`, `httpx2`, `openai`, `typesafe_sdk`. Chỉ INFO (dòng "POST … 200 OK", "Retrying request…"), không bao giờ DEBUG của chúng vì DEBUG có header và body |

## 2. Hàm cấp module

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `set_context(tag)` [:20](../core/log.py#L20) | Đặt nhãn vị trí cho các dòng log tiếp theo; gọi không tham số để xóa nhãn. `run_eval.py` đặt ba cấp: kịch bản, rồi `kịch bản call_N`, rồi `kịch bản call_N tK` | chuỗi nhãn, ví dụ `"GEN-T01-01 call_2 t3"` | không. Ghi `_tag = "[…]"` | |
| `get(name)` [:49](../core/log.py#L49) | Lấy logger con dưới `cc` | tên ngắn, ví dụ `"router"` | `logging.Logger` tên `cc.router` | `logging.getLogger` |
| `setup(file_level, verbose)` [:53](../core/log.py#L53) | Cấu hình log cho tiến trình, gọi được nhiều lần (handler màn hình chỉ gắn một lần). Mức log của file: DEBUG nếu `verbose`, không thì `file_level`. Logger gốc mở ở mức thấp hơn trong hai mức file / màn hình. Handler màn hình: INFO nếu `verbose`, không thì WARNING; có che PII và gắn nhãn. Tắt lan truyền lên root logger của Python. Thư viện HTTP ở INFO khi mức file là DEBUG, còn lại WARNING | mức của file (`"INFO"`…); có `-v` không | mức log của file (số nguyên của `logging`), truyền tiếp cho `capture` | `_MaskingFormatter`, `_TagFilter`, `logging.StreamHandler` |
| `capture(level)` [:72](../core/log.py#L72) | Context manager gom log của **một kịch bản** vào list trong bộ nhớ: gắn một `_ListHandler` (có che PII, có nhãn) vào logger `cc` và các logger HTTP, hạ mức logger gốc nếu cần; ra khỏi khối thì gỡ handler. `run_scenario` trả list này về tiến trình chính để ghi `<out>.log` theo thứ tự | mức log của file (từ `setup`) | list chuỗi (các dòng log đã định dạng), qua `with … as lines` | `_ListHandler`, `_MaskingFormatter`, `_TagFilter` |

## 3. Các lớp nội bộ

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_TagFilter.filter(record)` [:26](../core/log.py#L26) | Gắn nhãn vị trí hiện tại vào bản ghi log (trường `tag` mà `FMT` dùng). Luôn cho bản ghi đi qua | bản ghi log | `True` | đọc `_tag` |
| `_MaskingFormatter.format(record)` [:32](../core/log.py#L32) | Định dạng dòng theo `FMT` rồi che SĐT và địa chỉ trên cả dòng. Dùng cho cả màn hình lẫn file | bản ghi log | chuỗi đã che | `core.pii.mask_for_log` |
| `_ListHandler.__init__(level)` [:38](../core/log.py#L38) | Handler ghi vào list thay vì ra file / màn hình | mức log | không. Tạo `self.lines = []` | |
| `_ListHandler.emit(record)` [:42](../core/log.py#L42) | Định dạng bản ghi và thêm vào `self.lines`; lỗi định dạng thì để `logging` xử lý (không làm sập lượt thoại) | bản ghi log | không | `self.format`, `handleError` |

## 4. Luồng log trong một lần chạy `run_eval.py`

```
main()           setup(LOG_LEVEL, -v)                         # tiến trình chính: handler màn hình
  └─ run_scenario (mỗi kịch bản, trong worker)
       level = setup(...)                                     # worker cũng cấu hình một lần
       with capture(level) as lines:                          # gom log kịch bản này
           set_context("GEN-T01-01 call_2 t3"); ... log ...   # mọi dòng mang nhãn, đã che PII
       set_context()                                          # xóa nhãn
       return (scenario_id, rows, lines)
main()           ghi <out>.log: các `lines` sắp theo scenario_id
```

## 5. Ghi chú khi đọc code

- **`_tag` là biến chung của tiến trình,** không theo luồng. Thread của MCP client log trong lúc lượt đang chạy vẫn mang đúng nhãn vì mỗi worker chạy một kịch bản một lúc.
- **Che PII nằm ở bộ định dạng,** nên mọi dòng đều được che, kể cả dòng HTTP của thư viện ngoài.
- Cách khoanh vùng lỗi bằng log: [HARNESS.md](HARNESS.md) mục "Log và debug".
