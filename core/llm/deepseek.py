"""Client LLM tương thích OpenAI — dùng chung cho DeepSeek (API ngoài) và Qwen local (vLLM).

- `chat()`  : streaming để đo TTFT (generator).
- `json()`  : đầu ra JSON, nhiệt độ 0 (router `llm`/`qwen`, bộ trích LLM, tóm tắt). Truyền `schema` thì vLLM ép đúng JSON Schema
              (structured output — model không thể trả nhãn ngoài danh sách); DeepSeek chỉ hỗ trợ `json_object` nên schema được
              đưa vào prompt và kiểm lại phía code. Có cache theo mã băm request (core/llm/cache.py).

Khác nhau giữa hai provider chỉ là cấu hình: base_url, khóa, model, cách tắt chế độ suy luận
(deepseek-v4-flash: `thinking: {type: disabled}`; Qwen3 trên vLLM: `chat_template_kwargs: {enable_thinking: false}`).
"""
import json
import time

from core import log as cclog
from core.config import settings

log = cclog.get("llm")
EXTERNAL = {"deepseek"}


class LLM:
    _clients = {}
    _rr = None

    def __init__(self, provider="deepseek"):
        self.provider = provider
        if provider == "deepseek":
            key, base, self.model = settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model
            if not key:
                raise RuntimeError("DEEPSEEK_API_KEY chưa đặt")
            self.extra = {"thinking": {"type": settings.deepseek_thinking}} if settings.deepseek_thinking in ("disabled", "enabled") else None
        elif provider == "qwen":
            key, base, self.model = settings.qwen_api_key, settings.qwen_base_url, settings.qwen_model
            urls = [u.strip() for u in base.split(",") if u.strip()]
            if len(urls) > 1:
                import os
                if LLM._rr is None:
                    LLM._rr = os.getpid()
                LLM._rr += 1
                base = urls[LLM._rr % len(urls)]
            self.extra = {"chat_template_kwargs": {"enable_thinking": settings.qwen_thinking == "enabled"}}
        else:
            raise ValueError(f"provider LLM không hỗ trợ: {provider}")
        ck = (provider, base)
        if ck not in LLM._clients:
            from openai import OpenAI
            LLM._clients[ck] = OpenAI(api_key=key, base_url=base, timeout=settings.llm_timeout_s, max_retries=1)
        self.c = LLM._clients[ck]

    @property
    def external(self):
        return self.provider in EXTERNAL

    def chat(self, messages, max_tokens=None, temperature=None):
        t0 = time.perf_counter(); ttft = None; parts = []; usage = None
        log.debug("%s.chat model=%s prompt=%s", self.provider, self.model, json.dumps(messages, ensure_ascii=False)[:2000])
        try:
            stream = self.c.chat.completions.create(model=self.model, messages=messages, stream=True,
                                                    temperature=settings.llm_temperature if temperature is None else temperature,
                                                    max_tokens=max_tokens or settings.llm_max_tokens,
                                                    stream_options={"include_usage": True}, extra_body=self.extra)
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = {"prompt_tokens": chunk.usage.prompt_tokens, "completion_tokens": chunk.usage.completion_tokens}
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content or ""
                if delta and ttft is None:
                    ttft = time.perf_counter()
                parts.append(delta)
        except Exception as e:
            log.error("%s.chat lỗi sau %dms: %s", self.provider, (time.perf_counter() - t0) * 1000, _api_error(e))
            raise
        t1 = time.perf_counter()
        log.debug("%s.chat %dms ttft=%dms usage=%s", self.provider, (t1 - t0) * 1000, ((ttft or t1) - t0) * 1000, usage)
        return "".join(parts).strip(), int(((ttft or t1) - t0) * 1000), int((t1 - t0) * 1000), usage

    def json(self, prompt, max_tokens=300, schema=None, system="Chỉ trả về JSON hợp lệ.", timeout=None, cache=True):
        from core.llm import cache as llm_cache
        if schema is not None and self.provider != "qwen":
            prompt += "\n\nJSON phải đúng schema sau:\n" + json.dumps(schema, ensure_ascii=False)
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        rf = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}} if schema is not None and self.provider == "qwen" \
            else {"type": "json_object"}
        key = llm_cache.make_key(self.model, msgs, max_tokens=max_tokens, response_format=rf, extra=self.extra) if cache else None
        if key:
            hit = llm_cache.get(key)
            if hit is not None:
                return hit
        t0 = time.perf_counter()
        c = self.c.with_options(timeout=timeout) if timeout else self.c
        attempts = [(rf, msgs)]
        if rf["type"] == "json_schema":
            attempts.append(({"type": "json_object"},
                             [msgs[0], {"role": "user", "content": prompt + "\n\nJSON (viết gọn trên một dòng) đúng schema:\n"
                                        + json.dumps(schema, ensure_ascii=False)}]))
        for i, (fmt, m) in enumerate(attempts):
            try:
                r = c.chat.completions.create(model=self.model, temperature=0, max_tokens=max_tokens, response_format=fmt,
                                              extra_body=self.extra, messages=m)
                out = r.choices[0].message.content or "{}"
                log.debug("%s.json %dms → %s", self.provider, (time.perf_counter() - t0) * 1000, out[:500])
                d = json.loads(out)
                break
            except json.JSONDecodeError as e:
                if i + 1 < len(attempts):
                    log.warning("%s.json: JSON hỏng (%s) → thử lại không ép schema", self.provider, str(e)[:80])
                    continue
                log.error("%s.json lỗi sau %dms: %s", self.provider, (time.perf_counter() - t0) * 1000, _api_error(e))
                raise
            except Exception as e:
                log.error("%s.json lỗi sau %dms: %s", self.provider, (time.perf_counter() - t0) * 1000, _api_error(e))
                raise
        if key:
            llm_cache.put(key, self.model, d)
        return d


class DeepSeek(LLM):
    def __init__(self):
        super().__init__("deepseek")


def _api_error(e):
    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    return f"{type(e).__name__}" + (f" HTTP {status}" if status else "") + f": {str(e)[:300]}"
