#!/usr/bin/env python3
"""Transcript hai phía (dataset/transcripts) → audio cuộc gọi bằng edge-tts + ground truth ASR theo định dạng BTC.

    pip install edge-tts av numpy
    python datagen/make_audio.py                         # mọi cuộc hotline trong dataset/transcripts
    python datagen/make_audio.py --limit 5               # thử nhanh
    python asr/transcribe.py --audio-dir dataset/audio --ground-truth dataset/asr/ground_truth.json \\
                             --out dataset/asr/hypotheses.json --only-listed --limit 24

Đầu ra:
    dataset/audio/<id>.mp3              16 kHz mono; hai giọng (khách / nhân viên khác giới để dễ phân biệt)
    dataset/audio/<id>.segments.json    [{speaker, start, end}] theo từng lượt (dùng cho diarization, M2)
    dataset/asr/ground_truth.json       cùng định dạng asr/ground_truth.json của BTC (dạng chữ, có entities, cờ noisy)

Cách làm:
- Lời thoại được đổi sang dạng đọc (`asr/itn.py: to_spoken`: "5.200.000đ" → "năm triệu hai trăm nghìn") rồi mới đưa vào TTS,
  nên ground truth dạng chữ khớp đúng với thứ được đọc ra.
- Khoảng `--noisy-ratio` số cuộc được làm "đường dây điện thoại": lọc băng 300–3400 Hz, hạ xuống 8 kHz rồi nâng lại,
  trộn nhiễu nền (SNR 8–15 dB). Chọn theo băm của id nên chạy lại ra cùng tập.
- Thực thể ground truth lấy từ dữ liệu có cấu trúc của kịch bản (`facts_established`) và SĐT khách, chỉ giữ thực thể
  có giá trị xuất hiện trong lời thoại — không dùng bộ trích của hệ thống để tự chấm mình.

Hạn chế: edge-tts tiếng Việt chỉ có 2 giọng (HoaiMy nữ, NamMinh nam), không chọn được giọng vùng miền; đa dạng người nói
chỉ đến từ tốc độ và cao độ. Trường `customer_region` là miền của khách trong CRM, không phải giọng đọc.
"""
import argparse
import asyncio
import glob
import hashlib
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "asr"))

from itn import to_spoken  # noqa: E402

SR = 16000
VOICE = {"f": "vi-VN-HoaiMyNeural", "m": "vi-VN-NamMinhNeural"}
GAP_S = 0.35


def _h(s, mod):
    return int(hashlib.sha1(s.encode()).hexdigest(), 16) % mod


def spoken(text):
    t = re.sub(r"\[[^\]]*\]", " ", text)
    t = re.sub(r"\*{2,}", " ", t)
    t = to_spoken(t.replace("*", " "))
    t = re.sub(r"/(?=[^\W\d])", " mỗi ", t)
    t = t.replace("%", " phần trăm").replace("&", " và ").replace("m²", " mét vuông")
    t = re.sub(r"(?<=\w)-(?=\w)", " ", t)
    t = re.sub(r"[()\"“”…]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


async def tts(text, voice, rate, pitch, path, retries=4):
    import edge_tts
    for i in range(retries):
        try:
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)
            if os.path.getsize(path) > 200:
                return
        except Exception as e:
            err = e
        await asyncio.sleep(1.5 * (i + 1))
    raise RuntimeError(f"edge-tts lỗi: {locals().get('err')}")


def decode(path):
    import av
    import numpy as np
    con = av.open(path)
    rs = av.AudioResampler(format="s16", layout="mono", rate=SR)
    buf = []
    for fr in con.decode(audio=0):
        for o in rs.resample(fr):
            buf.append(o.to_ndarray().reshape(-1))
    con.close()
    return np.concatenate(buf).astype(np.float32) / 32768.0 if buf else np.zeros(0, dtype=np.float32)


def encode_mp3(x, path, bitrate=32000):
    import av
    import numpy as np
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    out = av.open(path, "w")
    st = out.add_stream("libmp3lame", rate=SR)
    st.bit_rate = bitrate; st.layout = "mono"
    fr = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono"); fr.sample_rate = SR
    for p in st.encode(fr):
        out.mux(p)
    for p in st.encode(None):
        out.mux(p)
    out.close()


def telephone(x, seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < 300) | (f > 3400)] = 0
    y = np.fft.irfft(X, len(x)).astype(np.float32)
    y = np.repeat(y[::2], 2)[:len(x)]
    w = np.fft.rfft(rng.standard_normal(len(x)))
    w /= np.maximum(np.sqrt(np.fft.rfftfreq(len(x), 1 / SR)), 1.0)
    noise = np.fft.irfft(w, len(x)).astype(np.float32)
    noise += 0.3 * np.sin(2 * np.pi * 50 * np.arange(len(x)) / SR).astype(np.float32) * noise.std()
    snr = float(rng.uniform(8, 15))
    sig_p = float(np.mean(y[np.abs(y) > 0.01] ** 2)) if np.any(np.abs(y) > 0.01) else 1e-6
    noise *= np.sqrt(sig_p / (10 ** (snr / 10)) / max(float(np.mean(noise ** 2)), 1e-12))
    return np.clip(y + noise, -1, 1), round(snr, 1)


def gt_entities(rec, phone):
    blob = " ".join(t["text"] for t in rec["turns"])
    digits = re.sub(r"[.\s]", "", blob)
    facts = rec.get("facts_established") or {}
    ent = {}

    def said(v):
        v = int(v)
        forms = {str(v), f"{v:,}".replace(",", ".")}
        if v % 1000 == 0:
            forms.add(f"{v // 1000}k")
        if v % 1_000_000 == 0:
            forms |= {f"{v // 1_000_000} triệu", f"{v // 1_000_000}tr"}
        elif v % 100_000 == 0:
            forms |= {f"{v / 1_000_000:g} triệu".replace(".", ","), f"{v / 1_000_000:g} triệu"}
        return any(f in blob for f in forms)
    for src, key in (("price_quoted_vnd", "price_vnd"), ("budget_vnd", "budget_vnd"), ("competitor_price_vnd", "competitor_price_vnd")):
        if isinstance(facts.get(src), int) and said(facts[src]):
            ent[key] = facts[src]
    if isinstance(facts.get("room_area_m2"), int) and re.search(rf"\b{facts['room_area_m2']}\s*(?:m2|m²|mét)", blob):
        ent["room_area_m2"] = facts["room_area_m2"]
    if phone and phone in digits:
        ent["phone"] = phone
    return ent


async def build_call(rec, phone, out_dir, noisy, sem):
    import numpy as np
    cg = rec["customer"]["gender"]
    ag = "m" if cg == "f" else "f"
    ck = rec["scenario_id"]
    c_rate, c_pitch = f"{_h(ck + 'r', 16) - 4:+d}%", f"{_h(ck + 'p', 25) - 12:+d}Hz"
    a_rate, a_pitch = "+6%", "+0Hz"
    tmp = tempfile.mkdtemp()

    async def one(i, t):
        txt = spoken(t["text"])
        if not re.search(r"\w", txt):
            return None
        p = os.path.join(tmp, f"{i}.mp3")
        async with sem:
            if t["speaker"] == "C":
                await tts(txt, VOICE[cg], c_rate, c_pitch, p)
            else:
                await tts(txt, VOICE[ag], a_rate, a_pitch, p)
        return txt, p
    parts = await asyncio.gather(*(one(i, t) for i, t in enumerate(rec["turns"])))
    wav, segs, gt_turns, cur = [], [], [], 0.0
    gap = np.zeros(int(GAP_S * SR), dtype=np.float32)
    for t, part in zip(rec["turns"], parts):
        if part is None:
            continue
        txt, p = part
        x = decode(p)
        os.remove(p)
        segs.append({"speaker": t["speaker"], "start": round(cur, 2), "end": round(cur + len(x) / SR, 2)})
        gt_turns.append({"idx": len(gt_turns) + 1, "speaker": t["speaker"], "text": txt.lower()})
        wav += [x, gap]; cur += (len(x) + len(gap)) / SR
    x = np.concatenate(wav)
    snr = None
    if noisy:
        x, snr = telephone(x, _h(rec["id"], 2 ** 31))
    encode_mp3(x, os.path.join(out_dir, rec["id"] + ".mp3"))
    json.dump({"id": rec["id"], "sample_rate": SR, "duration_s": round(len(x) / SR, 2), "segments": segs},
              open(os.path.join(out_dir, rec["id"] + ".segments.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"id": rec["id"], "customer_region": rec["customer"].get("region"), "customer_gender": cg, "agent_gender": ag,
            "scenario_ref": f"{rec['scenario_id']} {rec['call']}", "noisy": bool(noisy), "snr_db": snr,
            "note": f"{rec['persona']} — {rec.get('category') or ''}", "duration_s": round(len(x) / SR, 2),
            "voices": {"customer": VOICE[cg], "agent": VOICE[ag], "customer_rate": c_rate, "customer_pitch": c_pitch},
            "turns": gt_turns, "full_text": " ".join(t["text"] for t in gt_turns), "entities": gt_entities(rec, phone)}


async def amain(a):
    recs = []
    for f in sorted(glob.glob(os.path.join(a.transcripts, "*.json"))):
        r = json.load(open(f, encoding="utf-8"))
        if r["channel"] == "hotline":
            recs.append(r)
    if a.only:
        recs = [r for r in recs if r["id"] in a.only or r["scenario_id"] in a.only]
    if a.limit:
        recs = recs[:a.limit]
    os.makedirs(a.audio_dir, exist_ok=True)
    os.makedirs(os.path.dirname(a.ground_truth), exist_ok=True)
    gt = json.load(open(a.ground_truth, encoding="utf-8")) if os.path.exists(a.ground_truth) else None
    done = {d["id"]: d for d in (gt or {}).get("dialogues", [])}
    phones = {}
    for d in (os.path.join(HERE, "out_nat", "dev"), os.path.join(HERE, "out_nat", "test"), os.path.join(ROOT, "test_set", "public_sample")):
        for f in glob.glob(os.path.join(d, "*.json")):
            s = json.load(open(f, encoding="utf-8"))
            phones[s["scenario_id"]] = s.get("customer_phone")
    sem = asyncio.Semaphore(a.concurrency)
    todo = [r for r in recs if a.force or r["id"] not in done or not os.path.exists(os.path.join(a.audio_dir, r["id"] + ".mp3"))]
    print(f"{len(recs)} cuộc hotline, cần sinh {len(todo)}", file=sys.stderr)
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        res = await asyncio.gather(*(build_call(r, phones.get(r["scenario_id"]), a.audio_dir,
                                                _h(r["id"] + "noise", 100) < a.noisy_ratio * 100, sem) for r in chunk),
                                   return_exceptions=True)
        for r, d in zip(chunk, res):
            if isinstance(d, Exception):
                print(f"[LỖI] {r['id']}: {type(d).__name__}: {d}", file=sys.stderr)
            else:
                done[d["id"]] = d
        save(a, done)
        print(f"  {min(i + a.batch, len(todo))}/{len(todo)}", file=sys.stderr)
    save(a, done)
    ds = list(done.values())
    tot = sum(d["duration_s"] for d in ds)
    print(f"{len(ds)} cuộc có audio, {tot / 60:.1f} phút ({tot / 3600:.2f} giờ), {sum(d['noisy'] for d in ds)} cuộc nhiễu "
          f"({100 * sum(d['noisy'] for d in ds) / max(1, len(ds)):.0f}%), {sum(len(d['entities']) for d in ds)} thực thể → {a.audio_dir}")


def save(a, done):
    json.dump({"description": "Ground truth ASR của nhóm: audio sinh bằng edge-tts từ transcript hai phía (datagen/make_audio.py). "
                              "Cùng định dạng asr/ground_truth.json của BTC.",
               "hypotheses_format": "{\"<id>\": {\"text\": \"...\", \"entities\": {...}}}",
               "normalization_rule": "lowercase, NFC, bỏ dấu câu, gộp khoảng trắng; số viết bằng chữ như lời nói; entity so exact-match sau ITN",
               "reference_date": "2026-10-15",
               "dialogues": [done[k] for k in sorted(done)]},
              open(a.ground_truth, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcripts", default=os.path.join(ROOT, "dataset", "transcripts"))
    ap.add_argument("--audio-dir", default=os.path.join(ROOT, "dataset", "audio"))
    ap.add_argument("--ground-truth", default=os.path.join(ROOT, "dataset", "asr", "ground_truth.json"))
    ap.add_argument("--noisy-ratio", type=float, default=0.25)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true")
    asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    main()
