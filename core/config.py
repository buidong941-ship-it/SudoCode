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
    planner_jev_min_conf: float = field(default_factory=lambda: float(_env("PLANNER_JEV_MIN_CONF", "0.6")))
    # D50 (PLAN-2026-11-05-PLANNER-TABLE): planner đọc bảng quyết định harness/planner_rules.json thay cho _plan bằng code.
    # D58 (duyệt 05/11): mặc định BẬT. PLANNER_TABLE=0 = _plan cũ; bảng chỉ có nhánh cũ phải cho trace trùng 100 % (tests/planner_table_parity.py)
    planner_table: bool = field(default_factory=lambda: _env("PLANNER_TABLE", "1") not in ("0", "off", "false"))
    # L1 (05/11): gọi router song song với bước trích slot (router không cần slot). D58: mặc định BẬT; =0 = nối tiếp như cũ (trace trùng, tests/latency_parallel_check.py).
    # Chỉ song song ở lượt không đọc SĐT và không đang hỏi danh tính (định danh có thể đổi tóm tắt phiên trước).
    parallel_router: bool = field(default_factory=lambda: _env("PARALLEL_ROUTER", "1") not in ("0", "off", "false"))
    # L3 (05/11): endpoint Qwen RIÊNG cho extractor + summarizer (vd vLLM thứ hai ở GPU 1), để không tranh GPU với generator.
    # Rỗng = dùng chung QWEN_BASE_URL như cũ. scripts/serve_llm.sh tự bật thêm server cho cổng này.
    qwen_extract_base_url: str = field(default_factory=lambda: _env("QWEN_EXTRACT_BASE_URL", ""))
    # D51: tầng tra sản phẩm mở rộng (harness/lexicon/products.json + dạng ASR của mã model + ưu tiên SKU combo). D58: mặc định BẬT; =0 = tra SP như cũ
    product_lexicon: bool = field(default_factory=lambda: _env("PRODUCT_LEXICON", "1") not in ("0", "off", "false"))
    # E04 (05/11): số lượng mua (slot qty, luật) → order.create qty, tổng tiền / hạn mức COD và KM theo số lượng (min_qty).
    # Mặc định tắt cho tới khi A/B offline xong (tests/order_qty_ab.py)
    order_qty: bool = field(default_factory=lambda: _env("ORDER_QTY", "0") not in ("0", "off", "false"))
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
                "planner_backend": self.planner_backend, "planner_jev_min_conf": self.planner_jev_min_conf,
                "planner_table": self.planner_table, "product_lexicon": self.product_lexicon,
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


settings = Settings()
