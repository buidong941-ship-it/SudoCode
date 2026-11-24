"""Cấu hình duy nhất của hệ thống — đọc từ biến môi trường (và file .env nếu có).

Mọi thứ phụ thuộc máy chạy (khóa API, DB, model) nằm ở đây để code không biết mình chạy trên laptop hay server.
"""
import os
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv(path=os.path.join(ROOT, ".env")):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


if os.environ.get("RUN_PROFILE"):
    _prof = os.path.join(ROOT, "profiles", os.environ["RUN_PROFILE"] + ".env")
    if not os.path.exists(_prof):
        raise FileNotFoundError(f"RUN_PROFILE={os.environ['RUN_PROFILE']} nhưng không có {_prof}")
    _load_dotenv(_prof)
_load_dotenv()


def _env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _json_env(name, default):
    import json
    try:
        value = _env(name)
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def _check_choice(name, default, allowed):
    v = (_env(name, default) or default).lower()
    if v not in allowed:
        raise ValueError(f"{name}={v!r} không hợp lệ; chọn một trong {sorted(allowed)}")
    return v


def _check_set(name, allowed):
    items = frozenset(x.strip().lower() for x in (_env(name, "") or "").split(",") if x.strip())
    bad = items - allowed
    if bad:
        raise ValueError(f"{name} có giá trị lạ {sorted(bad)}; chỉ nhận {sorted(allowed)}")
    return items


@dataclass
class Settings:
    router_backend: str = field(default_factory=lambda: _env("ROUTER_BACKEND", "jev"))
    typesafe_api_key: str = field(default_factory=lambda: _env("TYPESAFE_API_KEY"))
    jev_model: str = field(default_factory=lambda: _env("JEV_MODEL", "jev-latest"))  # 05/11: key TypeSafe chính thức (không đặt TYPESAFE_BASE_URL); proxy portixapi cần jev-1.14.0
    jev_base_url: str = field(default_factory=lambda: _env("TYPESAFE_BASE_URL"))
    jev_timeout_s: float = field(default_factory=lambda: float(_env("JEV_TIMEOUT_S", "8")))
    router_min_confidence: float = field(default_factory=lambda: float(_env("ROUTER_MIN_CONFIDENCE", "0.45")))
    laya_model: str = field(default_factory=lambda: _env("LAYA_MODEL", "convaiinnovations/laya"))
    laya_subfolder: str = field(default_factory=lambda: _env("LAYA_SUBFOLDER", "multilingual"))
    laya_device: str = field(default_factory=lambda: _env("LAYA_DEVICE", _env("EMBED_DEVICE", "auto")))
    laya_lang: str = field(default_factory=lambda: _env("LAYA_LANG", "vi"))

    generator_backend: str = field(default_factory=lambda: _env("GENERATOR_BACKEND", "deepseek"))
    deepseek_api_key: str = field(default_factory=lambda: _env("DEEPSEEK_API_KEY"))
    deepseek_base_url: str = field(default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    llm_temperature: float = field(default_factory=lambda: float(_env("LLM_TEMPERATURE", "0.3")))
    llm_max_tokens: int = field(default_factory=lambda: int(_env("LLM_MAX_TOKENS", "350")))
    reply_style: str = field(default_factory=lambda: _env("REPLY_STYLE", "normal"))
    gen_placeholders: bool = field(default_factory=lambda: _env("GEN_PLACEHOLDERS", "0") not in ("0", "off", "false"))
    gen_parallel_n: int = field(default_factory=lambda: max(1, min(2, int(_env("GEN_PARALLEL_N", "1")))))
    gen_adaptive_second: bool = field(default_factory=lambda: _env("GEN_ADAPTIVE_SECOND", "0") not in ("0", "off", "false"))
    extract_logprobs: bool = field(default_factory=lambda: _env("EXTRACT_LOGPROBS", "0") not in ("0", "off", "false"))
    extract_logprob_top_n: int = field(default_factory=lambda: max(1, min(5, int(_env("EXTRACT_LOGPROB_TOP_N", "5")))))
    extract_logprob_thresholds: dict = field(default_factory=lambda: _json_env("EXTRACT_LOGPROB_THRESHOLDS", {}))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("LLM_TIMEOUT_S", "30")))
    deepseek_thinking: str = field(default_factory=lambda: _env("DEEPSEEK_THINKING", "disabled"))

    qwen_base_url: str = field(default_factory=lambda: _env("QWEN_BASE_URL", "http://127.0.0.1:8000/v1"))
    qwen_model: str = field(default_factory=lambda: _env("QWEN_MODEL", "Qwen/Qwen3-8B-AWQ"))
    qwen_api_key: str = field(default_factory=lambda: _env("QWEN_API_KEY", "local"))
    qwen_thinking: str = field(default_factory=lambda: _env("QWEN_THINKING", "disabled"))

    extractor_backend: str = field(default_factory=lambda: _env("EXTRACTOR_BACKEND", "rules"))
    agent_question_backend: str = field(default_factory=lambda: _env("AGENT_QUESTION_BACKEND", "current").lower())
    agent_claim_backend: str = field(default_factory=lambda: _env("AGENT_CLAIM_BACKEND", "current").lower())
    extractor_llm: str = field(default_factory=lambda: _env("EXTRACTOR_LLM", "qwen"))
    extractor_timeout_s: float = field(default_factory=lambda: float(_env("EXTRACTOR_TIMEOUT_S", "10")))
    extractor_async: bool = field(default_factory=lambda: _env("EXTRACTOR_ASYNC", "1") not in ("0", "off", "false"))
    extractor_confidence_gate: bool = field(default_factory=lambda: _env("EXTRACTOR_CONFIDENCE_GATE", "0") not in ("0", "off", "false"))
    extractor_jev_hybrid: bool = field(default_factory=lambda: _env("EXTRACTOR_JEV_HYBRID", "0") not in ("0", "off", "false"))
    # A6: khi Jev không chọn slot address/payment mà luật đã cắt được giá trị:
    # accept = theo Jev (cũ) | qwen = để Qwen làm trọng tài | rules = giữ giá trị của luật
    jev_drop_policy: str = field(default_factory=lambda: _env("JEV_DROP_POLICY", "qwen").lower())
    # D18–D21: phiên bản chứng chỉ luật (harness/rule_confidence.py). 1 = hành vi cũ (mặc định tới khi D21 đạt điều kiện);
    # 2 = CERT v2 (NEG/QUES, sửa bug m2, ghép câu hỏi–trả lời, khớp bản có dấu, theo từng slot, thêm slot) + phủ định trong luật
    extractor_cert_version: int = field(default_factory=lambda: int(_env("EXTRACTOR_CERT_VERSION", "1")))
    # D16/D27: cờ CHỈ DÙNG KHI ĐO các bước nới CERT v2, cộng dồn, cách nhau dấu phẩy (blocker,budget). Rỗng = không nới (mặc định)
    cert_v2_relax: str = field(default_factory=lambda: _env("CERT_V2_RELAX", "").lower())
    # Mục E: thư mục improve/ có approved/ để agent nạp (harness/improve_hook.py). Rỗng = tắt (mặc định, cấu hình đo vòng 0)
    improve_dir: str = field(default_factory=lambda: _env("IMPROVE_DIR", ""))
    # B-H: planner hybrid có giới hạn (harness/planner_llm.py) — rules = tắt; jev = Jev chính, Qwen dự phòng; qwen = chỉ Qwen
    planner_backend: str = field(default_factory=lambda: _env("PLANNER_BACKEND", "rules").lower())
    # Bộ chọn hành động của planner. rules giữ đường bảng hiện tại để làm đối chứng A/B.
    jev_simulated: bool = field(default_factory=lambda: _env("JEV_SIMULATED", "0") == "1")
    goal_contract: bool = field(default_factory=lambda: _env("GOAL_CONTRACT", "0") == "1")
    extractor_no_jev: bool = field(default_factory=lambda: _env("EXTRACTOR_NO_JEV", "0") == "1")
    # 09/11: hợp đồng v2 — một luật stance chung (harness/stance.py) cho claim, slot lựa chọn của khách, guardrail và
    # action ghi dữ liệu; kiểm cam kết "đã làm" (harness/commitments.json); xác nhận ngắn chỉ hiệu lực khi có việc đang chờ;
    # (đối soát tạo đơn theo SKU/ngày đã bỏ 10/11, FINAL G1). D59 duyệt 10/11: mặc định BẬT; CONTRACT_V2=0 = hành vi cũ.
    contract_v2: bool = field(default_factory=lambda: _env("CONTRACT_V2", "1") == "1")
    planner_selector: str = field(default_factory=lambda: _check_choice("PLANNER_SELECTOR", "rules", {"rules", "qwen", "jev"}))
    planner_jev_min_conf: float = field(default_factory=lambda: float(_env("PLANNER_JEV_MIN_CONF", "0.6")))
    # D50 (PLAN-2026-11-05-PLANNER-TABLE): planner đọc bảng quyết định harness/planner_rules.json.
    # 1b (06/11): _plan if-else cũ đã bỏ, bảng là đường duy nhất; PLANNER_TABLE=0 không còn nghĩa → báo lỗi (xem _check_removed).
    # PLANNER_SKIP_SINCE: bỏ các dòng bảng có "since" thuộc danh sách (vd "D51" = planner như trước D51, dùng cho vòng 0 của mục 20b).
    # Rỗng = dùng mọi dòng (mặc định). Bảng bỏ D51 cho trace trùng bảng chỉ có nhánh cũ (tests/planner_table_parity.py).
    planner_skip_since: tuple = field(default_factory=lambda: tuple(x.strip() for x in _env("PLANNER_SKIP_SINCE", "").split(",") if x.strip()))
    # L1 (05/11): gọi router song song với bước trích slot (router không cần slot). D58: mặc định BẬT; =0 = nối tiếp như cũ (trace trùng, tests/latency_parallel_check.py).
    # Chỉ song song ở lượt không đọc SĐT và không đang hỏi danh tính (định danh có thể đổi tóm tắt phiên trước).
    parallel_router: bool = field(default_factory=lambda: _env("PARALLEL_ROUTER", "1") not in ("0", "off", "false"))
    # D68 (người dùng duyệt 10/11): DeepSeek flash quyết định khách có yêu cầu thao tác ghi hay không (harness/request_gate.py).
    # Rỗng = tắt (agent y hệt R0). REQUESTS_GATE=control (chặn tool ghi) | shadow (chỉ ghi trace).
    requests_backend: str = field(default_factory=lambda: _env("REQUESTS_BACKEND", ""))
    requests_gate: str = field(default_factory=lambda: _env("REQUESTS_GATE", "control"))
    requests_timeout_s: float = field(default_factory=lambda: float(_env("REQUESTS_TIMEOUT_S", "10")))
    # Kiến trúc đích (người dùng duyệt triển khai 11/11): UNDERSTANDING=deepseek → MỘT lần gọi DeepSeek Flash thay router +
    # nhận diện yêu cầu + trích slot khách (rules/CERT/Jev hybrid/Qwen) — harness/understanding.py. Rỗng = R0.
    understanding: str = field(default_factory=lambda: _env("UNDERSTANDING", ""))
    understanding_timeout_s: float = field(default_factory=lambda: float(_env("UNDERSTANDING_TIMEOUT_S", "20")))
    # Cấu hình ĐÍCH đầy đủ (11/11, NHAN-XET-VA-YEU-CAU-CHINH-SUA-KIEN-TRUC-DICH K01–K14): ARCH=target bật cùng lúc
    # bộ hiểu DeepSeek hợp đồng v2 + state yêu cầu/pending bằng code + chính sách an toàn bằng code + predicate có kiểu +
    # response blocks/renderer + MỘT pipeline audit câu cuối (Jev question, Qwen claim). Không CERT, không cascade Jev hybrid,
    # không cổng D68. Rỗng = R0/TG cũ (snapshot đối chứng). Cấu hình mâu thuẫn bị từ chối ở check_arch().
    arch: str = field(default_factory=lambda: _check_choice("ARCH", "", {"", "target"}))
    # 12/11 (THIET-KE-B1-B2-JEV-B3-WORKFLOW): chủ sở hữu tiến trình nghiệp vụ trên cấu hình đích. b1 = bảng hiện tại (đối chứng,
    # mặc định); b2_jev = Jev chọn từng bước (observe → decide → execute → observe); b3_workflow = workflow có guard theo từng
    # yêu cầu. Factory dựng planner MỘT lần khi mở session (harness/planner_variants.py); đổi biến thể = run/session mới.
    planner_variant: str = field(default_factory=lambda: _check_choice("PLANNER_VARIANT", "b1", {"b1", "b2_jev", "b3_workflow"}))
    # Ngân sách hữu hạn của vòng lập kế hoạch B2 (mục 4.4). Ghi vào <out>.config.json; áp dụng như nhau giữa các lần đo.
    # Cách đếm (v3, 12/11): MỘT quyết định = một lần gọi bộ quyết định Jev (kể cả lần bị validator / chống lặp từ chối);
    # tool call = mọi lời gọi ToolBox trong vòng (kể cả bên trong commit / answer_ask, kể cả lời gọi lỗi); trần tool kiểm TRƯỚC
    # mỗi hành động có thể gọi tool (không ngắt giữa một hành động); deadline tính từ lúc vào vòng tới trước quyết định kế tiếp.
    # 10 quyết định = cấu hình THĂM DÒ người dùng duyệt 12/11 (chưa phải ngân sách cuối); deadline chốt theo số E1.
    # PLANNER_B2_MIN_CONF: 0 = chưa áp ngưỡng (confidence Jev không phải xác suất đã hiệu chuẩn).
    b2_max_decisions: int = field(default_factory=lambda: int(_env("PLANNER_B2_MAX_DECISIONS", "10")))
    b2_max_tool_calls: int = field(default_factory=lambda: int(_env("PLANNER_B2_MAX_TOOL_CALLS", "13")))   # 13/11: người dùng duyệt nâng 12 → 13 (tư vấn danh mục 8 mẫu khi đang bàn một mẫu tốn tối đa 13)
    b2_deadline_s: float = field(default_factory=lambda: float(_env("PLANNER_B2_DEADLINE_S", "12")))
    b2_min_conf: float = field(default_factory=lambda: float(_env("PLANNER_B2_MIN_CONF", "0")))
    # Candidate B2-TT (17/11, docs/DE-XUAT/THIET-KE-CANDIDATE-B2TT-2026-11-17.md): tư vấn CHỈ ĐỌC hai tầng (Jev ngoài chọn tác vụ,
    # Jev trong chọn thao tác) trên PLANNER_VARIANT=b2_jev; giao dịch giữ nguyên luồng B2. Mặc định TẮT = hành vi bản chính.
    # Bật cờ cũng bật: has_children nhận label khong → False (định nghĩa slot đã có), và trường `consult` của bộ hiểu.
    b2_two_tier: bool = field(default_factory=lambda: _env("B2_TWO_TIER", "0") == "1")
    jev_write_gate: bool = field(default_factory=lambda: _env("JEV_WRITE_GATE", "0") == "1")
    # v6p7 (23/11): bộ hiểu trích lại MỘT lần khi output tự mâu thuẫn (mơ hồ dù mọi dòng có tên hợp lệ; số lượng không nguyên văn)
    understanding_retry: bool = field(default_factory=lambda: _env("UNDERSTANDING_RETRY", "0") == "1")
    # v6p11 (24/11): phạm vi địa chỉ (đơn hiện có / mặc định cho đơn sau) + lời khách kể trạng thái đơn, DeepSeek trích kèm căn cứ,
    # JEV phân loại kiểm chéo trong cùng lần gọi cổng ghi; tắt = hành vi v6p10 ở mọi tầng
    address_scope_gate: bool = field(default_factory=lambda: _env("ADDRESS_SCOPE_GATE", "0") == "1")
    # v6p12 (24/11): đường ghi — kiểu lời nói (mode) của đổi/trả có JEV kiểm chéo, điều kiện promo_active / fee_free theo dữ kiện
    # tool + DT-03, địa chỉ không mất khi yêu cầu bị giữ; tắt = hành vi v6p11
    write_path_gate: bool = field(default_factory=lambda: _env("WRITE_PATH_GATE", "0") == "1")
    # v6p13 vòng 2A (24/11, duyệt): mỗi cơ chế một cờ, tắt = hành vi v6p12
    nullable_evidence: bool = field(default_factory=lambda: _env("NULLABLE_EVIDENCE", "0") == "1")
    trial_total: bool = field(default_factory=lambda: _env("TRIAL_TOTAL", "0") == "1")
    pick_by_name: bool = field(default_factory=lambda: _env("PICK_BY_NAME", "0") == "1")
    claim_span: bool = field(default_factory=lambda: _env("CLAIM_SPAN", "0") == "1")
    done_no_handoff: bool = field(default_factory=lambda: _env("DONE_NO_HANDOFF", "0") == "1")
    # v6p14 vòng 2B (24/11, duyệt): trả lời câu hỏi chính sách / thông số bằng câu nguyên văn chọn từ tài liệu; tắt = v6p13
    doc_answer: bool = field(default_factory=lambda: _env("DOC_ANSWER", "0") == "1")
    b2tt_max_tool_calls: int = field(default_factory=lambda: int(_env("B2TT_MAX_TOOL_CALLS", "18")))
    b2tt_max_decisions: int = field(default_factory=lambda: int(_env("B2TT_MAX_DECISIONS", "4")))
    # Candidate kho hướng dẫn điều phối cho Jev (17/11, docs/DE-XUAT/KIEN-TRUC-RAG-HUONG-DAN-JEV-2026-11-17.md). Rỗng = TẮT.
    # Đường dẫn gói ĐÃ ĐÓNG (PACKAGE.json + approved/ chỉ loại planner_guidance), truyền tường minh; tách khỏi IMPROVE_DIR (FAQ).
    planner_guidance_dir: str = field(default_factory=lambda: _env("PLANNER_GUIDANCE_DIR", ""))
    guidance_fetch_k: int = field(default_factory=lambda: int(_env("GUIDANCE_FETCH_K", "15")))
    guidance_context_k: int = field(default_factory=lambda: int(_env("GUIDANCE_CONTEXT_K", "3")))
    guidance_min_score: float = field(default_factory=lambda: float(_env("GUIDANCE_MIN_SCORE", "1.0")))   # tạm, hiệu chỉnh trên dev trước freeze
    guidance_max_tokens: int = field(default_factory=lambda: int(_env("GUIDANCE_MAX_TOKENS", "800")))
    # 13/11 (duyệt): câu cuối gửi ra backend/UI ngay sau guardrail (callback on_emit); audit hậu kỳ chạy nền trên đúng câu đã
    # gửi. AUDIT_ASYNC=0: vẫn emit thật nhưng turn() đợi audit xong mới trả về (chẩn đoán). Hết phiên / job đợi audit tối đa
    # AUDIT_DRAIN_TIMEOUT_S rồi ghi audit_status=timeout (không bỏ im lặng).
    audit_async: bool = field(default_factory=lambda: _env("AUDIT_ASYNC", "1") == "1")
    audit_drain_timeout_s: float = field(default_factory=lambda: float(_env("AUDIT_DRAIN_TIMEOUT_S", "240")))
    # B3: MỘT bước = một hành động nguyên tử workflow chạy trong lượt (read_* / check_window / commit_request / clarify), cộng
    # dồn mọi pha và mọi yêu cầu của lượt; tới trần thì dừng (`max_steps`), yêu cầu còn lại giữ nguyên trạng thái.
    b3_max_steps: int = field(default_factory=lambda: int(_env("PLANNER_B3_MAX_STEPS", "8")))
    # Chỉ để kiểm tích hợp không có Secret: Qwen đóng vai DeepSeek ở bộ hiểu (trace ghi rõ). Không dùng cho số báo cáo.
    deepseek_simulated: bool = field(default_factory=lambda: _env("DEEPSEEK_SIMULATED", "0") == "1")
    # L3 (05/11): endpoint Qwen RIÊNG cho extractor + summarizer (vd vLLM thứ hai ở GPU 1), để không tranh GPU với generator.
    # Rỗng = dùng chung QWEN_BASE_URL như cũ. scripts/serve_llm.sh tự bật thêm server cho cổng này.
    qwen_extract_base_url: str = field(default_factory=lambda: _env("QWEN_EXTRACT_BASE_URL", ""))
    # D51: tầng tra sản phẩm mở rộng (harness/lexicon/products.json + dạng ASR của mã model + ưu tiên SKU combo). D58: mặc định BẬT; =0 = tra SP như cũ
    product_lexicon: bool = field(default_factory=lambda: _env("PRODUCT_LEXICON", "1") not in ("0", "off", "false"))
    # E04 (05/11): số lượng mua (slot qty, luật) → order.create qty, tổng tiền / hạn mức COD và KM theo số lượng (min_qty).
    # Mặc định BẬT (05/11): A/B offline 6 bộ dev 0 lượt khác trace, chỉ số giữ nguyên (tests/order_qty_ab.py)
    order_qty: bool = field(default_factory=lambda: _env("ORDER_QTY", "1") not in ("0", "off", "false"))
    planner_rules_path: str = field(default_factory=lambda: _env("PLANNER_RULES", os.path.join(ROOT, "harness", "planner_rules.json")))
    question_clf: bool = field(default_factory=lambda: _env("QUESTION_CLF", "0") not in ("0", "off", "false"))
    question_classifier_backend: str = field(default_factory=lambda: _env("QUESTION_CLF_BACKEND", "jev").lower())
    question_clf_tau: float = field(default_factory=lambda: float(_env("QUESTION_CLF_TAU", "0.75")))
    summary_backend: str = field(default_factory=lambda: _env("SUMMARY_BACKEND", "auto"))
    handoff_summary: str = field(default_factory=lambda: _env("HANDOFF_SUMMARY", "auto"))
    llm_cache_path: str = field(default_factory=lambda: _env("LLM_CACHE", os.path.join(ROOT, "data", "llm_cache.sqlite")))
    # Cờ ablation 04/11 (CHỈ DÙNG KHI ĐO; mặc định = hành vi cũ):
    # D39(a) STRIP_QUESTIONS=1: lỗi duy nhất là "không được đặt câu hỏi" → cắt câu hỏi bằng code, không sinh lại
    strip_questions: bool = field(default_factory=lambda: _env("STRIP_QUESTIONS", "0") not in ("0", "off", "false"))
    # GUARD_MODE=log: guardrail + coverage chỉ ghi lỗi vào trace, không sinh lại / không thay câu mẫu
    guard_mode: str = field(default_factory=lambda: _check_choice("GUARD_MODE", "enforce", {"enforce", "log"}))
    # MEM_ABLATE=profile,episodic,ttl,supersede: tắt từng tầng bộ nhớ khi ĐỌC (chỉ ảnh hưởng config full)
    mem_ablate: frozenset = field(default_factory=lambda: _check_set("MEM_ABLATE", {"profile", "episodic", "ttl", "supersede"}))

    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///" + os.path.join(ROOT, "data", "memory.db")))

    tool_transport: str = field(default_factory=lambda: _env("TOOL_TRANSPORT", "mcp"))
    mcp_timeout_s: float = field(default_factory=lambda: float(_env("MCP_TIMEOUT_S", "20")))

    btc_dir: str = field(default_factory=lambda: _env("BTC_DIR", ROOT))

    def describe(self):
        return {"run_profile": os.environ.get("RUN_PROFILE"), "router_backend": self.router_backend, "jev_model": self.jev_model,
                "jev_base_url": self.jev_base_url or None,     # ghi lại để biết lần chạy gọi Jev qua proxy nào
                "router_min_confidence": self.router_min_confidence,
                "laya": {"model": self.laya_model, "subfolder": self.laya_subfolder, "device": self.laya_device, "lang": self.laya_lang},
                "generator_backend": self.generator_backend, "deepseek_model": self.deepseek_model,
                "deepseek_base_url": self.deepseek_base_url, "llm_temperature": self.llm_temperature,
                "llm_max_tokens": self.llm_max_tokens, "reply_style": self.reply_style, "gen_placeholders": self.gen_placeholders,
                "gen_parallel_n": self.gen_parallel_n,
                "gen_adaptive_second": self.gen_adaptive_second,
                "extract_logprobs": self.extract_logprobs,
                "extract_logprob_top_n": self.extract_logprob_top_n,
                "extract_logprob_thresholds": self.extract_logprob_thresholds,
                "deepseek_thinking": self.deepseek_thinking,
                "qwen_model": self.qwen_model, "qwen_base_url": self.qwen_base_url, "qwen_thinking": self.qwen_thinking,
                "extractor_backend": self.extractor_backend, "extractor_llm": self.extractor_llm,
                "extractor_async": self.extractor_async, "extractor_confidence_gate": self.extractor_confidence_gate,
                "extractor_jev_hybrid": self.extractor_jev_hybrid, "jev_drop_policy": self.jev_drop_policy,
                "extractor_cert_version": self.extractor_cert_version, "cert_v2_relax": self.cert_v2_relax,
                "planner_backend": self.planner_backend, "planner_selector": self.planner_selector,
                "planner_jev_min_conf": self.planner_jev_min_conf, "jev_simulated": self.jev_simulated, "goal_contract": self.goal_contract, "extractor_no_jev": self.extractor_no_jev, "contract_v2": self.contract_v2, "requests_backend": self.requests_backend or None, "requests_gate": self.requests_gate, "understanding": self.understanding or None, "arch": self.arch or None, "deepseek_simulated": self.deepseek_simulated,
                "planner_variant": self.planner_variant,
                "planner_b2_budget": {"max_decisions": self.b2_max_decisions, "max_tool_calls": self.b2_max_tool_calls,
                                      "deadline_s": self.b2_deadline_s, "min_conf": self.b2_min_conf},
                "b2_two_tier": {"on": self.b2_two_tier, "max_tool_calls": self.b2tt_max_tool_calls, "max_decisions": self.b2tt_max_decisions},
                "planner_guidance": {"dir": self.planner_guidance_dir or None, "fetch_k": self.guidance_fetch_k,
                                     "context_k": self.guidance_context_k, "min_score": self.guidance_min_score,
                                     "max_tokens": self.guidance_max_tokens},
                "planner_b3_max_steps": self.b3_max_steps,
                "planner_skip_since": list(self.planner_skip_since), "product_lexicon": self.product_lexicon,
                "parallel_router": self.parallel_router, "order_qty": self.order_qty, "qwen_extract_base_url": self.qwen_extract_base_url or None,
                "improve_dir": self.improve_dir,
                "strip_questions": self.strip_questions, "guard_mode": self.guard_mode,
                "mem_ablate": sorted(self.mem_ablate),
                "question_clf": self.question_clf,
                "question_clf_backend": self.question_classifier_backend,
                "question_clf_tau": self.question_clf_tau,
                "summary_backend": self.summary_backend, "handoff_summary": self.handoff_summary, "tool_transport": self.tool_transport,
                "database": self.database_url.split("://", 1)[0],
                "rag": {k.lower(): _env(k) for k in ("RAG_MODE", "EMBED_MODEL", "RERANK_MODEL", "RAG_STORE")}}


def _check_removed():
    """1b (06/11): PLANNER_TABLE=0 từng chọn _plan cũ; đường đó đã bỏ. Báo lỗi thay vì lặng lẽ chạy bảng."""
    if _env("PLANNER_TABLE", "1").lower() in ("0", "off", "false"):
        raise ValueError("PLANNER_TABLE=0 không còn được hỗ trợ (_plan cũ đã bỏ 06/11). "
                         "Muốn planner như trước D51: PLANNER_SKIP_SINCE=D51")


# Cờ legacy chỉ còn ý nghĩa trên R0 / TG cũ. Trên ARCH=target chúng KHÔNG được đọc (hợp đồng: audit đích không gọi CERT /
# Jev hybrid / Qwen-sau-Jev; generator đích không dùng coverage→sinh lại). Ghi vào config để biết cờ nào bị bỏ qua.
TARGET_IGNORED_FLAGS = ("EXTRACTOR_CONFIDENCE_GATE", "EXTRACTOR_CERT_VERSION", "EXTRACTOR_JEV_HYBRID", "EXTRACTOR_NO_JEV",
                        "AGENT_CLAIM_BACKEND", "AGENT_QUESTION_BACKEND", "QUESTION_CLF", "STRIP_QUESTIONS", "JEV_DROP_POLICY",
                        "PLANNER_BACKEND", "PARALLEL_ROUTER")


PLANNER_VARIANTS = ("b1", "b2_jev", "b3_workflow")


def check_variant(variant, s=None):
    """Tổ hợp mâu thuẫn bị từ chối rõ (mục 3): b2/b3 chỉ chạy trên ARCH=target; selector legacy giữ rules; B2 không dùng
    planner LLM dự phòng (PLANNER_BACKEND) và không fallback. Ngân sách B2 phải hữu hạn, dương."""
    s = s or settings
    if variant not in PLANNER_VARIANTS:
        raise ValueError(f"PLANNER_VARIANT={variant!r} không hợp lệ; chọn một trong {PLANNER_VARIANTS}")
    if variant == "b1":
        return
    if s.arch != "target":
        raise ValueError(f"PLANNER_VARIANT={variant} chỉ chạy với ARCH=target (dùng chung bộ hiểu DeepSeek + request_state)")
    if s.planner_selector != "rules":
        raise ValueError(f"PLANNER_VARIANT={variant} mâu thuẫn với PLANNER_SELECTOR={s.planner_selector} (selector legacy)")
    if s.planner_backend != "rules":
        raise ValueError(f"PLANNER_VARIANT={variant} mâu thuẫn với PLANNER_BACKEND={s.planner_backend} (planner LLM dự phòng cũ)")
    if variant == "b2_jev" and not (s.b2_max_decisions > 0 and s.b2_max_tool_calls > 0 and s.b2_deadline_s > 0):
        raise ValueError("PLANNER_VARIANT=b2_jev cần ngân sách hữu hạn > 0 (PLANNER_B2_MAX_DECISIONS/_MAX_TOOL_CALLS/_DEADLINE_S)")
    if s.b2_two_tier and variant != "b2_jev":
        raise ValueError("B2_TWO_TIER=1 chỉ chạy trên PLANNER_VARIANT=b2_jev (candidate B2-TT)")
    if s.planner_guidance_dir and variant != "b2_jev":
        raise ValueError("PLANNER_GUIDANCE_DIR chỉ dùng với PLANNER_VARIANT=b2_jev (hướng dẫn cho planner Jev)")
    if s.planner_guidance_dir and not (0 < s.guidance_context_k <= 3 and 0 < s.guidance_fetch_k <= 15 and 0 < s.guidance_max_tokens <= 800):
        raise ValueError("GUIDANCE_CONTEXT_K ≤ 3, GUIDANCE_FETCH_K ≤ 15, GUIDANCE_MAX_TOKENS ≤ 800 (thiết kế 17/11)")
    if s.b2_two_tier and not (s.b2tt_max_tool_calls > 0 and s.b2tt_max_decisions > 0):
        raise ValueError("B2_TWO_TIER=1 cần B2TT_MAX_TOOL_CALLS / B2TT_MAX_DECISIONS > 0")
    if variant == "b3_workflow" and s.b3_max_steps <= 0:
        raise ValueError("PLANNER_VARIANT=b3_workflow cần PLANNER_B3_MAX_STEPS > 0")


def check_arch(s=None):
    """K08/K11: ARCH=target không được khởi động thêm một bộ hiểu thứ hai. Cấu hình mâu thuẫn → ValueError (từ chối rõ),
    không lặng lẽ gọi thêm API. → dict mô tả cờ legacy bị bỏ qua (ghi vào <out>.config.json)."""
    s = s or settings
    check_variant(s.planner_variant, s)
    if s.arch != "target":
        return {}
    if s.requests_backend:
        raise ValueError("ARCH=target không chạy cùng REQUESTS_BACKEND (cổng D68 cũ = bộ hiểu thứ hai). Để trống REQUESTS_BACKEND.")
    if s.understanding not in ("", "deepseek"):
        raise ValueError(f"ARCH=target chỉ dùng bộ hiểu DeepSeek; UNDERSTANDING={s.understanding!r} mâu thuẫn")
    if s.planner_selector != "rules":
        raise ValueError("ARCH=target dùng bảng planner với predicate có kiểu; PLANNER_SELECTOR khác 'rules' là selector Jev/Qwen cũ")
    # C.5 (16/11): target CHỈ được nạp gói FAQ đã duyệt (harness/improve_hook.approved() từ chối gói có loại khác khi mở phiên).
    # IMPROVE_DIR rỗng = C.5 tắt (vòng R0); đặt IMPROVE_DIR = thư mục gói FAQ = vòng R1.
    return {"ignored_legacy_flags": {k: os.environ.get(k) for k in TARGET_IGNORED_FLAGS if os.environ.get(k) not in (None, "")},
            **({"improve": {"dir": s.improve_dir, "scope": "faq_only"}} if s.improve_dir else {})}


_check_removed()
settings = Settings()
