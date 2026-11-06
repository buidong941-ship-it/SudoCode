"""Regex dạng dữ liệu (06/11): từ vựng dùng để ra quyết định nằm trong file JSON cạnh file này, không nằm trong code.

    router.json      intent + cờ của router (mô tả gửi Jev / Laya / LLM, câu hỏi Laya) và luật từ khóa của router `rules`
    cues.json        cue trên câu khách mà agent / bảng planner dùng làm điều kiện (predicate của planner_rules.json)
    guardrails.json  mẫu kiểm câu trả lời của agent trước khi gửi khách

Mỗi mẫu trong `patterns`:
    pattern   chuỗi regex, hoặc danh sách mảnh (nối liền, để xuống dòng cho dễ đọc). Khớp trên chuỗi đã fold()
              (bỏ dấu, chữ thường) trừ khi `note` nói khác. `@TÊN@` được thay bằng mẫu dùng chung trong `defs`.
    flags     (tùy chọn) cờ của `re`, vd "I"
    note      vì sao có mẫu này / nguồn (mã quyết định, kịch bản)
    examples  (tùy chọn) {"match": [...], "no_match": [...]} — tests/lexicon_rx_check.py kiểm trên chuỗi đã fold()

Regex TÁCH GIÁ TRỊ (số tiền, ngày giờ, địa chỉ, số lượng, thời hạn) vẫn ở trong code, cạnh logic dùng nó.
Mẫu sai cú pháp → ValueError ngay lúc import, kèm tên file và tên mẫu.
"""
import json
import os
import re
from functools import lru_cache

DIR = os.path.dirname(os.path.abspath(__file__))


def join(p):
    return "".join(p) if isinstance(p, list) else p


@lru_cache(maxsize=None)
def load(name):
    with open(os.path.join(DIR, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def pattern(name, key):
    """Chuỗi regex của mẫu `key` trong `<name>.json`, đã thay `@TÊN@` bằng mẫu trong `defs`."""
    doc = load(name)
    s = join(doc["patterns"][key]["pattern"])
    for k, v in (doc.get("defs") or {}).items():
        s = s.replace(f"@{k}@", join(v["pattern"] if isinstance(v, dict) else v))
    return s


@lru_cache(maxsize=None)
def rx(name, key):
    e = load(name)["patterns"][key]
    flags = 0
    for f in e.get("flags", ""):
        flags |= getattr(re, f)
    try:
        return re.compile(pattern(name, key), flags)
    except re.error as err:
        raise ValueError(f"harness/lexicon/{name}.json: mẫu {key} sai cú pháp: {err}") from err


def all_patterns(name):
    return list(load(name)["patterns"])
