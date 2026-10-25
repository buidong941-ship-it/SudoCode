# Sơ đồ kiến trúc code

Sơ đồ này vẽ theo code đang có trong repo: file nào gọi file nào, dữ liệu đi từ đâu đến đâu. Thiết kế chi tiết và lý do chọn nằm ở [ARCHITECTURE.md](ARCHITECTURE.md); cách chạy nằm ở [HARNESS.md](HARNESS.md).

```mermaid
flowchart TB
  subgraph DATA["1. Sinh kịch bản — datagen/"]
    TPL["templates/*.json<br/>27 template"]
    RES["resolver.py<br/>chọn khách, sản phẩm, ngày<br/>điền biến vào template"]
    VAL["validate.py<br/>kiểm đáp án khớp tool BTC"]
    NAT["naturalize.py<br/>DeepSeek viết lại lời khách"]
    TPL --> RES --> VAL --> NAT
  end

  SCN[("Kịch bản<br/>datagen/out_nat<br/>test_set/public_sample")]
  NAT --> SCN

  subgraph RUN["2. Chạy hội thoại — run_eval.py"]
    LOAD["harness/loader.py<br/>chỉ đưa lời khách cho agent<br/>ẩn đáp án"]
    subgraph SESSION["harness/agent.py — CallSession"]
      START["start()<br/>nhận diện khách<br/>dựng Call Brief"]
      PERC["textnorm.py<br/>chuẩn hóa số, ngày<br/>che CCCD / STK"]
      SLOT["extractor.py<br/>trích slot từ lời khách"]
      ROUTE["core/llm/router.py<br/>phân loại intent + cờ"]
      PLAN["_plan()<br/>chọn goals, gọi tool,<br/>tra chính sách"]
      GEN["core/llm/generator.py<br/>viết câu trả lời từ goals + facts"]
      GUARD["guardrails.py<br/>kiểm số tiền, PII, thông tin nội bộ"]
      EXTR["extractor.py<br/>questions / claims / facts_used"]
      REM["_remember() và end()<br/>ghi fact, tóm tắt phiên"]
      START --> PERC --> SLOT --> ROUTE --> PLAN --> GEN --> GUARD --> EXTR --> REM
      GUARD -. "sai: viết lại,<br/>vẫn sai: câu mẫu" .-> GEN
    end
    LOAD --> START
  end
  SCN --> LOAD

  subgraph SVC["3. Thứ agent dựa vào"]
    TOOLS["harness/tools.py<br/>ToolBox"]
    MEM["harness/memory.py<br/>bộ nhớ khách hàng"]
    KB["harness/knowledge.py<br/>harness/rag.py<br/>vector + BM25"]
    PII["core/pii.py<br/>Redactor: SĐT, địa chỉ thành mã"]
    MCPC["mcp-commerce<br/>mcp_servers/commerce_server.py"]
    MCPM["mcp-memory<br/>mcp_servers/memory_server.py"]
  end

  START --> TOOLS
  START --> MEM
  PLAN --> TOOLS
  PLAN --> KB
  REM --> MEM
  ROUTE --> PII
  GEN --> PII
  TOOLS -- "harness/mcp_client.py<br/>stdio" --> MCPC
  MEM -- "harness/mcp_client.py<br/>stdio" --> MCPM

  subgraph EXT["4. Dữ liệu và dịch vụ bên ngoài"]
    MOCK["eval/mock_tools.py<br/>9 tool của BTC"]
    CAT[("catalog/<br/>sản phẩm, KM, CRM")]
    POL[("policy/<br/>chính sách")]
    DB[("SQL<br/>6 bảng bộ nhớ")]
    API["DeepSeek / Jev<br/>core/llm/deepseek.py"]
  end

  MCPC --> MOCK --> CAT
  MCPM --> DB
  KB --> POL
  PII --> API

  TRACE[("Trace<br/>runs/*.jsonl")]
  REM --> TRACE

  subgraph AUDIO["5. Nhánh audio và ASR (offline)"]
    EXP["datagen/export_transcripts.py"]
    TRS[("dataset/transcripts")]
    MKA["datagen/make_audio.py<br/>edge-tts + nhiễu"]
    WAV[("dataset/audio")]
    ASR["asr/transcribe.py + asr/itn.py<br/>Whisper local, chuẩn hóa số"]
    HYP[("asr/hypotheses.json")]
    EXP --> TRS --> MKA --> WAV --> ASR --> HYP
  end
  TRACE --> EXP
  SCN --> EXP

  RAGE["run_rag_eval.py<br/>60 câu hỏi của BTC"]
  RAGE --> KB

  subgraph SCORE["6. Chấm — eval/reference_eval.py"]
    EVAL["5 chỉ số, guardrail, độ trễ<br/>WER / CER / Entity Accuracy<br/>Recall@k"]
    REP["report.json<br/>bảng A.6"]
    EVAL --> REP
  end
  TRACE --> EVAL
  SCN -- "đáp án" --> EVAL
  HYP --> EVAL
  RAGE -- "rag_results.json" --> EVAL
```

## Cách đọc

- **Đường chính** đi từ trên xuống: sinh kịch bản (1), chạy hội thoại (2), ghi trace, chấm (6).
- **Khối 2 là một lượt thoại.** `start()` chạy một lần đầu cuộc gọi; chuỗi từ `textnorm.py` đến `_remember()` lặp lại cho từng câu khách nói; `end()` chạy một lần cuối cuộc gọi.
- **Khối 3 và 4 là thứ agent gọi tới.** Với `--transport direct`, `tools.py` và `memory.py` gọi thẳng `mock_tools.py` và SQL, bỏ qua hai MCP server.
- **Khối 5 không nối vào agent.** Audio sinh ra từ transcript, chạy qua Whisper, rồi chỉ đi tới bước chấm.
- **Script chấm nhận hai đầu vào cho hội thoại:** trace của nhóm và đáp án trong kịch bản. Agent không bao giờ thấy đáp án, vì `loader.py` đã ẩn.

## Ghi chú

- `baseline_no_memory` dùng đúng các khối trên, chỉ tắt việc đọc bộ nhớ ở `start()`.
- Router có ba chế độ (Jev, DeepSeek, luật từ khóa); generator có hai (DeepSeek, câu mẫu). Chế độ không gọi API thì không đi qua `core/pii.py`.
- Các thư mục `eval/`, `catalog/`, `policy/`, `test_set/` là của BTC và không được sửa.
- Chưa có trong code nên không vẽ: cơ chế cải tiến (`improve/`) và giao diện Streamlit.

## Bổ sung 14/10/2026: model local, bộ trích LLM, chạy trên Kaggle/server

```mermaid
flowchart LR
  subgraph TURN["harness/agent.py — một lượt"]
    SLOT2["extractor.customer_slots<br/>rules | llm | hybrid"]
    ROUTE2["router: jev | llm | qwen | rules"]
    GEN2["generator: deepseek | qwen | offline<br/>lỗi → câu mẫu"]
    AG2["extractor.analyze_agent<br/>questions + claims"]
    END2["end(): tóm tắt phiên<br/>core/llm/summarizer.py"]
  end
  LX["harness/llm_extract.py<br/>LLM phân loại, code đọc giá trị,<br/>loại span bịa"]
  CL["core/llm/deepseek.py: LLM(provider)<br/>+ core/llm/cache.py"]
  VLLM["server vLLM<br/>Qwen3-8B-AWQ<br/>scripts/serve_llm.sh"]
  DS["API DeepSeek / Jev"]
  SLOT2 --> LX
  AG2 --> LX
  LX --> CL
  ROUTE2 --> CL
  GEN2 --> CL
  END2 --> CL
  CL -- qwen --> VLLM
  CL -- "deepseek (che PII)" --> DS

  subgraph RUN2["Chạy"]
    PROF["profiles/kaggle|server|local.env<br/>RUN_PROFILE"]
    SUITE["scripts/run_suite.py<br/>run_eval ×2 → reference_eval → summary.md"]
    KJ["scripts/kaggle_job.py (máy cá nhân)<br/>đóng gói → dataset riêng tư → kernel"]
    KR["kaggle/runner.py (trên Kaggle)<br/>setup_env.sh → run_suite.py"]
  end
  PROF --> SUITE
  KJ --> KR --> SUITE
  SUITE --> VLLM
```

Mọi backend dùng Qwen gọi chung một server vLLM. Các worker gửi HTTP request tới server đó, không nạp model trong tiến trình. Chi tiết: [CHAY-KAGGLE-SERVER.md](CHAY-KAGGLE-SERVER.md).
