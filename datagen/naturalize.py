#!/usr/bin/env python3
"""Viết lại `customer_turns` (câu mẫu điền giá trị) cho tự nhiên bằng LLM, GIỮ NGUYÊN mọi thông tin cụ thể.

    python datagen/naturalize.py                       # out/{dev,test} → out_nat/{dev,test} (+ out_nat/rewrites.json)
    python datagen/naturalize.py --only GEN-T01-01
    python datagen/validate.py datagen/out_nat/dev datagen/out_nat/test    # đáp án không đổi → vẫn phải sạch lỗi

Nguyên tắc:
- Chỉ đổi câu chữ của khách. `facts_established`, `success_if`, `ground_truth_facts`… giữ nguyên, nên đáp án không đổi.
- Mỗi lượt viết lại phải giữ đủ "mỏ neo" của câu gốc: mọi con số (giá, size, m², SĐT, mã đơn, ngày), sản phẩm được nhắc,
  số tiền, và các từ viết hoa/Latin (COD, Zalo, tên hãng, tên đường). Lượt nào thiếu mỏ neo → giữ câu gốc
  (ghi trong `_meta.naturalized`). Phép kiểm này KHÔNG dùng bộ trích slot của harness, để không lọc bỏ những cách nói
  mà hệ thống chưa hiểu (đó là tín hiệu cho vòng cải tiến).
- Cuộc có `customer_turns_asr` (ASR lỗi / teencode) giữ nguyên: bản nhiễu được sinh từ câu gốc, viết lại sẽ lệch nhau.
  Cuộc trên kênh chat (Fanpage, Zalo) cũng giữ nguyên, vì teencode / không dấu ở đó là chủ ý của kịch bản.
- SĐT / địa chỉ được che ([SĐT_1], [ĐỊA_CHỈ_1]) trước khi gửi LLM và ghép lại sau.
- Kết quả LLM lưu ở out_nat/rewrites.json (khóa = băm câu gốc) → chạy lại không gọi API, bộ test không đổi giữa các vòng.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from core.config import settings  # noqa: E402
from core.pii import Redactor  # noqa: E402
from harness.textnorm import find_money  # noqa: E402
from harness.tools import find_products  # noqa: E402

PROMPT = """Bạn viết lại lời KHÁCH HÀNG trong một cuộc gọi/nhắn tin mua hàng online ở Việt Nam cho tự nhiên như người thật nói.

Khách xưng "{xh}", gọi nhân viên là "em". Kiểu khách: {style}. Kênh: {channel}.

YÊU CẦU BẮT BUỘC:
1. Giữ đúng số lượt và thứ tự; mỗi lượt giữ nguyên ý định và MỌI thông tin cụ thể của lượt gốc: con số (giá, size, mét vuông,
   số lượng, ngày giờ, mã đơn), tên sản phẩm/hãng viết đúng như gốc, màu, địa chỉ, người cần hỏi ý kiến (chồng/vợ/mẹ…),
   hình thức thanh toán. Không đổi cách viết con số (25 vẫn là 25, 4590k vẫn là 4590k).
2. Không thêm thông tin mới, không thêm câu hỏi mới, không trả lời thay nhân viên.
3. Các mã dạng [SĐT_1], [ĐỊA_CHỈ_1] phải chép nguyên.
4. Đổi cách diễn đạt: thêm từ đệm, ngập ngừng, đảo trật tự ý, câu nói đời thường. Mỗi lượt 1–2 câu, không dài quá 1,5 lần gốc.
5. Nếu kênh là hotline: văn nói. Nếu là chat: viết như nhắn tin nhưng vẫn có dấu.

Lượt gốc (JSON): {turns}

Trả về JSON đúng dạng {{"turns": ["...", "..."]}} với đúng {n} phần tử."""

_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_CAP = re.compile(r"\b[A-ZĐ][A-Za-z0-9Đđ\-]*[A-Za-z0-9]\b|\b[A-Z]{2,}\b")


def _numbers(s):
    return sorted(re.sub(r"[.,]", "", m) for m in _NUM.findall(s))


def _latin_caps(s):
    out = set()
    for m in _CAP.finditer(s):
        head = s[:m.start()].rstrip()
        if m.start() == 0 or head.endswith((".", "?", "!", ":")):
            continue
        out.add(m.group().lower())
    return out


def anchors_kept(orig, new):
    if not new or not new.strip():
        return False, "rỗng"
    if len(new) > 2.5 * len(orig) + 40:
        return False, "quá dài"
    if _numbers(orig) != _numbers(new):
        return False, f"số: {_numbers(orig)} → {_numbers(new)}"
    if find_products(orig) != find_products(new):
        return False, f"sản phẩm: {find_products(orig)} → {find_products(new)}"
    if sorted(m[2] for m in find_money(orig)) != sorted(m[2] for m in find_money(new)):
        return False, "số tiền"
    miss = [w for w in _latin_caps(orig) if w not in new.lower()]
    if miss:
        return False, f"mất tên riêng: {miss}"
    if "{{" in new or "[SĐT" in new or "[ĐỊA_CHỈ" in new:
        return False, "còn mã che/placeholder"
    return True, ""


def keep_as_is(spec):
    return bool(spec.get("customer_turns_asr")) or spec.get("channel", "hotline") != "hotline"


def _key(sc, cname, turns):
    return hashlib.sha1(json.dumps([sc["persona"], sc["honorific"], cname, turns], ensure_ascii=False).encode()).hexdigest()[:16]


def rewrite_call(sc, cname, spec, styles, client, model, temperature, extra_body=None):
    turns = spec["customer_turns"]
    red = Redactor()
    safe = red.redact({"turns": turns})["turns"]
    prompt = PROMPT.format(xh=sc["honorific"], style=styles.get(sc["persona"], "bình thường"),
                           channel=spec.get("channel", "hotline"), turns=json.dumps(safe, ensure_ascii=False), n=len(turns))
    kwargs = {"model": model, "temperature": temperature, "max_tokens": 2000,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": "Chỉ trả về JSON hợp lệ."},
                           {"role": "user", "content": prompt}]}
    if extra_body:
        kwargs["extra_body"] = extra_body
    r = client.chat.completions.create(**kwargs)
    out = json.loads(r.choices[0].message.content or "{}").get("turns") or []
    return [red.restore(t) if isinstance(t, str) else "" for t in out]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.path.join(HERE, "out"))
    ap.add_argument("--out", default=os.path.join(HERE, "out_nat"))
    ap.add_argument("--splits", nargs="*", default=["dev", "test"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--backend", choices=("deepseek", "qwen", "claude"), default="deepseek",
                    help="deepseek qua API, Qwen trên vLLM, hoặc claude: CHỈ ĐỌC cache — lời viết lại do Claude viết trong "
                         "phiên Claude Code (PLAN-2026-11-01 D-7), không gọi API")
    ap.add_argument("--offline", action="store_true", help="chỉ dùng rewrites.json đã có, không gọi API")
    ap.add_argument("--import-claude", help="(backend claude) file JSON {khóa: [lượt viết lại]} do Claude viết → gộp vào rewrites.json")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    cache_p = os.path.join(a.out, "rewrites.json")
    cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}
    def cache_key(sc, cname, turns):
        key = _key(sc, cname, turns)
        return key if a.backend == "deepseek" else f"{a.backend}:{key}"
    if a.import_claude:
        if a.backend != "claude":
            sys.exit("--import-claude chỉ dùng với --backend claude")
        new = json.load(open(a.import_claude, encoding="utf-8"))
        bad = [k for k in new if not k.startswith("claude:") or not isinstance(new[k], list)]
        if bad:
            sys.exit(f"khóa phải dạng claude:<băm> và giá trị là danh sách lượt: {bad[:5]}")
        cache.update(new)
        json.dump(cache, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"gộp {len(new)} lời viết lại của Claude vào {cache_p}")
    styles = {p["persona_id"]: p["style"] for p in
              json.load(open(os.path.join(ROOT, "simulator", "personas.json"), encoding="utf-8"))["personas"]}

    scs = []
    for sp in a.splits:
        for f in sorted(glob.glob(os.path.join(a.src, sp, "*.json"))):
            sc = json.load(open(f, encoding="utf-8"))
            if not a.only or sc["scenario_id"] in a.only:
                scs.append((sp, os.path.basename(f), sc))

    jobs = []
    for _, _, sc in scs:
        for cname, spec in sc["calls"].items():
            if keep_as_is(spec):
                continue
            k = cache_key(sc, cname, spec["customer_turns"])
            if len(cache.get(k) or []) != len(spec["customer_turns"]):
                jobs.append((k, sc, cname, spec))
    if jobs and a.backend == "claude":
        # không gọi API: ghi việc cần viết để Claude viết trong phiên, rồi chạy lại với --import-claude
        todo_p = os.path.join(a.out, "claude_todo.jsonl")
        with open(todo_p, "w", encoding="utf-8") as fh:
            for k, sc, cname, spec in jobs:
                fh.write(json.dumps({"key": k, "scenario": sc["scenario_id"], "call": cname, "honorific": sc["honorific"],
                                     "style": styles.get(sc["persona"], "bình thường"), "channel": spec.get("channel", "hotline"),
                                     "turns": spec["customer_turns"]}, ensure_ascii=False) + "\n")
        print(f"{len(jobs)} cuộc gọi chưa có lời viết lại của Claude → {todo_p} (viết xong: --import-claude <file>)")
    elif jobs and not a.offline:
        from openai import OpenAI
        if a.backend == "deepseek":
            if not settings.deepseek_api_key:
                sys.exit("DEEPSEEK_API_KEY chưa đặt (hoặc dùng --offline)")
            client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, timeout=90, max_retries=2)
            model, extra_body = settings.deepseek_model, None
        else:
            client = OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url, timeout=90, max_retries=2)
            model = settings.qwen_model
            extra_body = {"chat_template_kwargs": {"enable_thinking": settings.qwen_thinking == "enabled"}}

        def run(job):
            k, sc, cname, spec = job
            try:
                return k, rewrite_call(sc, cname, spec, styles, client, model, a.temperature, extra_body), None
            except Exception as e:
                return k, None, f"{type(e).__name__}: {str(e)[:200]}"
        with ThreadPoolExecutor(a.workers) as ex:
            for k, out, err in ex.map(run, jobs):
                if err:
                    print(f"[LỖI API] {k}: {err}", file=sys.stderr)
                else:
                    cache[k] = out
        json.dump(cache, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n_turn = n_new = n_skip_asr = 0
    rejected = []
    for sp, name, sc in scs:
        meta = sc.setdefault("_meta", {})
        nat, tpl = {}, {}
        for cname, spec in sc["calls"].items():
            turns = spec["customer_turns"]
            n_turn += len(turns)
            if keep_as_is(spec):
                n_skip_asr += len(turns); continue
            new = cache.get(cache_key(sc, cname, turns))
            if not new or len(new) != len(turns):
                rejected += [(sc["scenario_id"], cname, i + 1, "LLM trả sai số lượt / chưa có") for i in range(len(turns))]
                continue
            flags, res = [], []
            for i, (o, n) in enumerate(zip(turns, new)):
                ok, why = anchors_kept(o, n)
                flags.append(ok); res.append(n.strip() if ok else o)
                if not ok:
                    rejected.append((sc["scenario_id"], cname, i + 1, why))
            n_new += sum(flags)
            tpl[cname], nat[cname] = turns, flags
            spec["customer_turns"] = res
        meta["naturalized"], meta["template_turns"] = nat, tpl
        os.makedirs(os.path.join(a.out, sp), exist_ok=True)
        json.dump(sc, open(os.path.join(a.out, sp, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    rep = {"scenarios": len(scs), "turns": n_turn, "rewritten": n_new, "kept_asr_teencode_chat": n_skip_asr,
           "kept_original_after_check": len(rejected),
           "rejected": [{"scenario_id": s, "call": c, "turn": t, "why": w} for s, c, t, w in rejected]}
    json.dump(rep, open(os.path.join(a.out, "naturalize_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(scs)} kịch bản, {n_turn} lượt khách: viết lại {n_new}, giữ nguyên {n_skip_asr} (ASR/teencode/chat), "
          f"giữ câu gốc vì mất thông tin {len(rejected)} → {a.out}")
    for s, c, t, w in rejected[:15]:
        print(f"  giữ gốc {s} {c} lượt {t}: {w}")


if __name__ == "__main__":
    main()
