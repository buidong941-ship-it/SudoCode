"""Orchestrator / Router: quyết định lượt này là việc gì (intent) + các cờ rủi ro. Ba backend cùng một giao diện:

- `jev`   : TypeSafe Jev (System One) — trả nhãn có kiểu + xác suất/độ tin cậy, không sinh văn bản. Mặc định.
- `llm`   : DeepSeek trả JSON (dự phòng khi không có Jev, và để so sánh Jev vs LLM trong báo cáo).
- `qwen`  : cùng prompt, model local qua vLLM, đầu ra ép theo JSON Schema (intent thuộc 11 nhãn, cờ 0..1), nhiệt độ 0 + cache.
            Dùng `qwen` cho cả router lẫn generator thì toàn bộ LLM chạy local.
- `laya`  : Laya (System One mã nguồn mở, checkpoint multilingual) chạy local — cùng câu hỏi Choice/Noul như Jev, không gọi
            mạng, không cần che PII. `LAYA_LANG=vi|en` chọn ngôn ngữ mô tả nhãn.
- `rules` : từ khóa, không gọi mạng — chỉ để kiểm thử pipeline / CI, KHÔNG dùng để báo cáo số liệu.

route() trả: {"intent", "confidence", "probabilities", "flags": {tên: xác suất}, "backend", "ms", "fallback"}
"""
import json
import re
import time

from core import log as cclog
from core.config import settings
from core.pii import Redactor
from harness.lexicon import rx as lexrx
from harness.textnorm import fold

# 06/11: intent, cờ, câu hỏi Laya và luật từ khóa nằm trong harness/lexicon/router.json (không nhồi vào code).
_R = lexrx.load("router")
INTENTS = {k: v["vi"] for k, v in _R["intents"].items()}
INTENTS_EN = {k: v["en"] for k, v in _R["intents"].items()}
FLAGS = {k: (v["yes"], v["no"]) for k, v in _R["flags"].items()}
FLAGS_EN = {k: (v["yes_en"], v["no_en"]) for k, v in _R["flags"].items()}
FLAGS_Q = {"vi": {k: v["q_vi"] for k, v in _R["flags"].items()},
           "en": {k: v["q_en"] for k, v in _R["flags"].items()}}

log = cclog.get("router")
_laya = {}


def laya_agent():
    key = (settings.laya_model, settings.laya_subfolder, settings.laya_device)
    if key not in _laya:
        import laya
        dev = settings.laya_device
        if dev == "auto":
            import torch
            dev = "cuda" if torch.cuda.is_available() else "cpu"
        t0 = time.perf_counter()
        _laya[key] = laya.load(settings.laya_model, subfolder=settings.laya_subfolder or None, device=dev)
        log.info("laya %s/%s nạp trên %s sau %.1fs", settings.laya_model, settings.laya_subfolder, dev, time.perf_counter() - t0)
    return _laya[key]


def laya_questions(lang=None):
    lang = lang or settings.laya_lang
    en, ask = lang.startswith("en"), lang.endswith("_q")
    intents, flags = (INTENTS_EN, FLAGS_EN) if en else (INTENTS, FLAGS)
    q = {"intent": {"type": "choice", "criteria": intents,
                    "instructions": ("What is the main intent of what the customer just said in this sales call?" if en else
                                     "Ý định chính của câu khách vừa nói trong cuộc gọi bán hàng là gì?")}}
    for name, (yes, no) in flags.items():
        q[name] = ({"type": "noul", "instructions": FLAGS_Q["en" if en else "vi"][name]} if ask else
                   {"type": "noul", "instructions": yes, "criteria": {"true": yes, "false": no}})
    return q


class Router:
    def __init__(self, backend=None):
        self.backend = backend or settings.router_backend
        self._client = None
        if self.backend == "laya":
            laya_agent()

    def route(self, text, context):
        t0 = time.perf_counter()
        fallback = None
        try:
            if self.backend == "jev":
                out = self._jev(text, context)
            elif self.backend == "laya":
                out = self._laya(text, context)
            elif self.backend in ("llm", "qwen"):
                out = self._llm(text, context, provider="deepseek" if self.backend == "llm" else "qwen")
            else:
                out = _rules(text)
        except Exception as e:
            fallback = f"{type(e).__name__}: {str(e)[:160]}"
            log.warning("router %s lỗi → dùng luật từ khóa: %s", self.backend, fallback)
            log.debug("router traceback", exc_info=True)
            out = _rules(text)
        if self.backend != "rules" and fallback is None and out["confidence"] < settings.router_min_confidence:
            rule = _rules(text)
            if rule["confidence"] >= 0.8:
                fallback = f"low_confidence {out['intent']}:{out['confidence']:.2f}"
                log.warning("router %s không chắc (%s) → dùng luật: %s", self.backend, fallback, rule["intent"])
                out = {**rule, "flags": {**out["flags"], **{k: v for k, v in rule["flags"].items() if v >= 0.9}}}
        from harness import improve_hook               # D52: cue router đã duyệt qua improve/ (tắt mặc định → không làm gì)
        used = improve_hook.apply_router_cues(text, out, self.backend if fallback is None else "rules") if improve_hook.enabled() else []
        if used:
            out["improve"] = used
        out.update(backend=self.backend, ms=int((time.perf_counter() - t0) * 1000), fallback=fallback)
        log.debug("router %s %dms intent=%s probs=%s usage=%s", self.backend, out["ms"], out["intent"],
                  out.get("probabilities"), out.get("usage"))
        return out

    def _jev(self, text, context):
        from typesafe_sdk import Choice, Noul, TypeSafeClient
        if self._client is None:
            if not settings.typesafe_api_key:
                raise RuntimeError("TYPESAFE_API_KEY chưa đặt")
            self._client = TypeSafeClient(api_key=settings.typesafe_api_key, timeout=settings.jev_timeout_s,
                                          model=settings.jev_model, base_url=settings.jev_base_url,
                                          headers={"Connection": "close"})
        questions = {"intent": Choice(instructions="Ý định chính của câu khách vừa nói trong cuộc gọi bán hàng là gì?",
                                      criteria=INTENTS)}
        for name, (yes, no) in FLAGS.items():
            questions[name] = Noul(instructions=yes, criteria={"true": yes, "false": no})
        state = Redactor().redact({"customer_said": text, "recent_dialogue": context.get("recent", [])[-4:],
                                   "known_context": context.get("summary", "")})
        r = self._client.system_one(state=state, questions=questions, model=settings.jev_model)
        ch = r.choices["intent"]
        return {"intent": ch.choice, "confidence": float(ch.confidence), "probabilities": dict(ch.probabilities),
                "flags": {k: float(v.noul) for k, v in r.nouls.items()},
                "usage": {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens}}

    def _laya(self, text, context, lang=None):
        state = {"customer_said": text, "recent_dialogue": context.get("recent", [])[-4:],
                 "known_context": context.get("summary", "")}
        r = laya_agent().system_one(state, laya_questions(lang))
        a, usage = r["answers"], r.get("usage") or {}
        if usage.get("truncated"):
            log.warning("laya cắt bớt state: %s token bị bỏ", usage.get("state_tokens_dropped"))
        ch = a["intent"]
        return {"intent": ch["choice"], "confidence": float(ch.get("answer_confidence", ch["confidence"])),
                "probabilities": dict(ch["probabilities"]), "flags": {k: float(a[k]["noul"]) for k in FLAGS},
                "usage": {"input_tokens": usage.get("input_tokens"), "truncated": usage.get("truncated"),
                          "laya_confidence": float(ch["confidence"])}}

    def _llm(self, text, context, provider="deepseek"):
        from core.llm.deepseek import LLM
        llm = LLM(provider)
        recent = context.get("recent", [])[-4:]
        if llm.external:
            text, recent = Redactor().redact([text, recent])
        prompt = ("Phân loại câu khách trong cuộc gọi bán hàng. Trả JSON {\"intent\": <một nhãn>, \"confidence\": 0..1, "
                  "\"flags\": {<cờ>: 0..1}}.\nNhãn intent:\n" + "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())
                  + "\nCờ:\n" + "\n".join(f"- {k}: {v[0]}" for k, v in FLAGS.items())
                  + f"\n\nNgữ cảnh: {json.dumps(recent, ensure_ascii=False)}\nCâu khách: {text}")
        d = llm.json(prompt, schema=ROUTE_SCHEMA if provider == "qwen" else None)
        intent = d.get("intent") if d.get("intent") in INTENTS else "greeting_or_other"
        return {"intent": intent, "confidence": _unit(d.get("confidence", 0.5)), "probabilities": {},
                "flags": {k: _unit((d.get("flags") or {}).get(k, 0)) for k in FLAGS}}


ROUTE_SCHEMA = {"type": "object", "required": ["intent", "confidence", "flags"], "additionalProperties": False,
                "properties": {"intent": {"type": "string", "enum": list(INTENTS)},
                               "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                               "flags": {"type": "object", "required": list(FLAGS), "additionalProperties": False,
                                         "properties": {k: {"type": "number", "minimum": 0, "maximum": 1} for k in FLAGS}}}}


def _unit(v):
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _b(rx):
    return re.compile(r"\b(?:" + rx + r")\b")


# luật từ khóa của router `rules` (harness/lexicon/router.json: intent_rules theo thứ tự, flag_rules)
_RULES = [(r["intent"], _b(lexrx.join(r["pattern"]))) for r in _R["intent_rules"]]
_FLAG_RULES = {k: _b(lexrx.join(p)) for k, p in _R["flag_rules"].items()}


def _rules(text):
    f = fold(text)
    intent, conf = "greeting_or_other", 0.5
    for name, rx in _RULES:
        if re.search(rx, f):
            intent, conf = name, 0.85
            break
    flags = {k: (0.95 if re.search(rx, f) else 0.05) for k, rx in _FLAG_RULES.items()}
    return {"intent": intent, "confidence": conf, "probabilities": {}, "flags": flags}
