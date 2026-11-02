"""D-4 (ràng buộc 3): kiểm nhãn hai lớp cho câu tự sinh — nhãn Claude đặt khi viết so với một bộ gán nhãn KHÁC Claude.

Lớp kiểm thứ hai mặc định là luật hiện tại (`customer_slots_rules`); có thể đổi sang `--checker hybrid` (Jev/Qwen chỉ đóng
vai bộ kiểm, cần khóa / server). Câu lệch nhãn → hàng đợi người duyệt `data/lexicon_corpus/review_queue.jsonl`.
Thêm một mẫu ngẫu nhiên ≥5% mỗi đợt → `data/lexicon_corpus/human_sample_<đợt>.jsonl` để người duyệt đọc và ghi tỷ lệ nhãn
sai vào nhật ký (>5% thì sửa đặc tả và viết lại đợt đó).

Lệch nhãn KHÔNG có nghĩa là nhãn Claude sai: luật bỏ sót chính là thứ lexicon cần học. Bảng in ra tách:
  luật_bỏ_sót   Claude: có slot · luật: không      → ứng viên cue (recall)
  luật_bắt_nhầm Claude: phản ví dụ · luật: có slot → ứng viên negative cue (precision)
  khác_giá_trị  cả hai có slot nhưng khác giá trị  → người duyệt xem ai đúng

    python scripts/label_crosscheck.py [--batch b1] [--sample-rate 0.05]
"""
import argparse
import glob
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "data", "lexicon_corpus")
TODAY = "2026-10-15"
RULE_KEY = {"claimed_price_vnd": "claimed_prices"}


def checker_slots(text, checker):
    from harness import extractor
    if checker == "rules":
        return extractor.customer_slots_rules(text, TODAY)
    os.environ["EXTRACTOR_BACKEND"] = checker
    extractor.settings.extractor_backend = checker
    return extractor.customer_slots(text, TODAY, {}, None)


def same(slot, gold, pred):
    from extract_eval import same as _same
    if slot == "claimed_price_vnd":
        return gold in (pred or [])
    return _same(slot, gold, pred)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--batch")
    ap.add_argument("--checker", default="rules", choices=["rules", "hybrid", "llm"])
    ap.add_argument("--sample-rate", type=float, default=0.05)
    a = ap.parse_args()
    rows = []
    for f in sorted(glob.glob(os.path.join(OUT, "synth", "*.jsonl"))):
        rows += [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    if a.batch:
        rows = [r for r in rows if r["batch"] == a.batch]
    if not rows:
        sys.exit("chưa có câu — chạy datagen/synth_slot_sentences.py trước")
    stats, queue = {}, []
    for r in rows:
        pred = checker_slots(r["text"], a.checker)
        k = RULE_KEY.get(r["slot"], r["slot"])
        have = pred.get(k)
        st = stats.setdefault(r["slot"], {"agree": 0, "luat_bo_sot": 0, "luat_bat_nham": 0, "khac_gia_tri": 0})
        if r["label"] == "hard_negative":
            kind = "luat_bat_nham" if have not in (None, [], "") else "agree"
        elif have in (None, [], ""):
            kind = "luat_bo_sot"
        else:
            kind = "agree" if same(r["slot"], r["value"], have) else "khac_gia_tri"
        for xs, xv in (r.get("extra") or {}).items():
            if not same(xs, xv, pred.get(RULE_KEY.get(xs, xs))) and kind == "agree":
                kind = "khac_gia_tri"
        st[kind] += 1
        if kind != "agree":
            queue.append({**r, "checker": a.checker, "checker_value": have, "disagreement": kind})
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "review_queue.jsonl"), "w", encoding="utf-8") as fh:
        for q in queue:
            fh.write(json.dumps(q, ensure_ascii=False, default=str) + "\n")
    rng = random.Random(20261101)
    for b in sorted({r["batch"] for r in rows}):
        br = [r for r in rows if r["batch"] == b]
        k = max(1, round(len(br) * a.sample_rate))
        with open(os.path.join(OUT, f"human_sample_{b}.jsonl"), "w", encoding="utf-8") as fh:
            for r in rng.sample(br, k):
                fh.write(json.dumps({**r, "human_ok": None, "human_note": ""}, ensure_ascii=False) + "\n")
    print(f"{'slot':<22}{'khớp':>6}{'luật bỏ sót':>13}{'luật bắt nhầm':>15}{'khác giá trị':>14}")
    for s, st in sorted(stats.items()):
        print(f"{s:<22}{st['agree']:>6}{st['luat_bo_sot']:>13}{st['luat_bat_nham']:>15}{st['khac_gia_tri']:>14}")
    tot = sum(sum(v.values()) for v in stats.values())
    print(f"{len(queue)}/{tot} câu lệch → {os.path.join(OUT, 'review_queue.jsonl')}; mẫu người duyệt → human_sample_<đợt>.jsonl")


if __name__ == "__main__":
    main()
