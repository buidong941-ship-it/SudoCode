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


@dataclass
class Settings:
    router_backend: str = field(default_factory=lambda: _env("ROUTER_BACKEND", "jev"))
    typesafe_api_key: str = field(default_factory=lambda: _env("TYPESAFE_API_KEY"))
    jev_model: str = field(default_factory=lambda: _env("JEV_MODEL", "jev-latest"))
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
    extractor_llm: str = field(default_factory=lambda: _env("EXTRACTOR_LLM", "qwen"))
    extractor_timeout_s: float = field(default_factory=lambda: float(_env("EXTRACTOR_TIMEOUT_S", "10")))
    extractor_async: bool = field(default_factory=lambda: _env("EXTRACTOR_ASYNC", "1") not in ("0", "off", "false"))
    question_clf: bool = field(default_factory=lambda: _env("QUESTION_CLF", "0") not in ("0", "off", "false"))
    question_clf_path: str = field(default_factory=lambda: _env("QUESTION_CLF_PATH", os.path.join(ROOT, "models", "question_clf", "model.pkl")))
    question_classifier_backend: str = field(default_factory=lambda: _env("QUESTION_CLF_BACKEND", "local").lower())
    question_clf_tau: float = field(default_factory=lambda: float(_env("QUESTION_CLF_TAU", "0.5")))
    summary_backend: str = field(default_factory=lambda: _env("SUMMARY_BACKEND", "auto"))
    handoff_summary: str = field(default_factory=lambda: _env("HANDOFF_SUMMARY", "auto"))
    llm_cache_path: str = field(default_factory=lambda: _env("LLM_CACHE", os.path.join(ROOT, "data", "llm_cache.sqlite")))

    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///" + os.path.join(ROOT, "data", "memory.db")))

    tool_transport: str = field(default_factory=lambda: _env("TOOL_TRANSPORT", "mcp"))
    mcp_timeout_s: float = field(default_factory=lambda: float(_env("MCP_TIMEOUT_S", "20")))

    btc_dir: str = field(default_factory=lambda: _env("BTC_DIR", ROOT))

    def describe(self):
        return {"run_profile": os.environ.get("RUN_PROFILE"), "router_backend": self.router_backend, "jev_model": self.jev_model,
                "router_min_confidence": self.router_min_confidence,
                "laya": {"model": self.laya_model, "subfolder": self.laya_subfolder, "device": self.laya_device, "lang": self.laya_lang},
                "generator_backend": self.generator_backend, "deepseek_model": self.deepseek_model,
                "deepseek_base_url": self.deepseek_base_url, "llm_temperature": self.llm_temperature,
                "llm_max_tokens": self.llm_max_tokens, "reply_style": self.reply_style, "gen_placeholders": self.gen_placeholders,
                "gen_parallel_n": self.gen_parallel_n,
                "extract_logprobs": self.extract_logprobs,
                "extract_logprob_top_n": self.extract_logprob_top_n,
                "extract_logprob_thresholds": self.extract_logprob_thresholds,
                "deepseek_thinking": self.deepseek_thinking,
                "qwen_model": self.qwen_model, "qwen_base_url": self.qwen_base_url, "qwen_thinking": self.qwen_thinking,
                "extractor_backend": self.extractor_backend, "extractor_llm": self.extractor_llm, "extractor_async": self.extractor_async,
                "question_clf": self.question_clf,
                "question_clf_backend": self.question_classifier_backend,
                "question_clf_tau": self.question_clf_tau,
                "summary_backend": self.summary_backend, "handoff_summary": self.handoff_summary, "tool_transport": self.tool_transport,
                "database": self.database_url.split("://", 1)[0],
                "rag": {k.lower(): _env(k) for k in ("RAG_MODE", "EMBED_MODEL", "RERANK_MODEL", "RAG_STORE")}}


settings = Settings()
