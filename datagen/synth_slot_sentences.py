"""D-3: kiểm định dạng câu đơn theo slot do Claude viết, chia 70/30, cập nhật manifest (PLAN-2026-11-01 A-D2).

Script KHÔNG sinh câu (người viết là Claude trong phiên Claude Code, theo datagen/slot_specs.json). Nó chỉ:
  1. đọc mọi đợt `datagen/synth_slots/<đợt>.tsv` (cột: prompt_id label slot value span region style structure extra text);
  2. kiểm từng dòng: label hợp lệ, slot có trong đặc tả, positive phải có value + span nằm trong câu, hard_negative không
     có value, giá trị đúng kiểu (int / true / COD|bank / nhãn blocker / YYYY-MM-DDTHH:MM), không trùng câu;
  3. loại câu trùng n-gram với holdout / test / public_sample (scripts/check_overlap.py, chỉ đếm, không in nội dung);
  4. chia theo nhóm prompt_id trong từng slot (cả nhóm cùng một phía): ~70% `mine` (rút cue) / ~30% `eval` (đo);
  5. ghi `data/lexicon_corpus/synth/<slot>.jsonl` và manifest (`datagen/synth_slots/manifest.json`, commit được).

    python datagen/synth_slot_sentences.py            # kiểm + chia + ghi
    python datagen/synth_slot_sentences.py --check    # chỉ kiểm, không ghi
"""
import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
SRC = os.path.join(ROOT, "datagen", "synth_slots")
SPEC = os.path.join(ROOT, "datagen", "slot_specs.json")
OUT = os.path.join(ROOT, "data", "lexicon_corpus", "synth")
COLS = ["prompt_id", "label", "slot", "value", "span", "region", "style", "structure", "extra", "text"]
GENERATOR = "claude-opus-5-5 (Claude Code, viết tay trong phiên)"
BLOCKERS = {"can hoi chong", "can hoi vo", "can hoi nguoi nha", "so sanh gia", "can nhac"}


def assign_splits(rows):
    """Chia theo nhóm prompt_id, riêng từng slot: xếp nhóm theo sha1(prompt_id), ~30% nhóm đầu → eval (ít nhất 1 nhóm khi
    slot có ≥2 nhóm), còn lại → mine. Cả nhóm cùng một phía, nên câu rút cue và câu đo không cùng một lần viết."""
    groups = {}
    for r in rows:
        groups.setdefault(r["slot"], set()).add(r["prompt_id"])
    ev = set()
    for slot, gs in groups.items():
        order = sorted(gs, key=lambda g: hashlib.sha1(g.encode()).hexdigest())
        n = max(1, round(0.3 * len(order))) if len(order) >= 2 else 0
        ev |= {(slot, g) for g in order[:n]}
    for r in rows:
        r["split"] = "eval" if (r["slot"], r["prompt_id"]) in ev else "mine"


def parse_value(slot, raw):
    if slot in ("room_area_m2", "budget_vnd", "competitor_price_vnd", "claimed_price_vnd", "household_size"):
        return int(raw)
    if slot == "has_children":
        if raw != "true":
            raise ValueError("has_children chỉ nhận 'true'")
        return True
    if slot == "payment" and raw not in ("COD", "bank"):
        raise ValueError("payment phải là COD | bank")
    if slot == "blocker" and raw not in BLOCKERS:
        raise ValueError(f"blocker phải thuộc {sorted(BLOCKERS)}")
    if slot == "callback_requested" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", raw):
        raise ValueError("callback_requested phải dạng YYYY-MM-DDTHH:MM")
    return raw


def load(spec):
    rows, errs, seen = [], [], set()
    for path in sorted(glob.glob(os.path.join(SRC, "*.tsv"))):
        batch = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8", newline="") as fh:
            rd = csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
            if rd.fieldnames != COLS:
                errs.append(f"{batch}: cột phải là {COLS}, có {rd.fieldnames}")
                continue
            for i, r in enumerate(rd, start=2):
                where = f"{batch}:{i}"
                r = {k: (v or "").strip() for k, v in r.items()}
                if r["label"] not in ("positive", "hard_negative", "multi"):
                    errs.append(f"{where}: label lạ {r['label']!r}"); continue
                if r["slot"] not in spec["slots"]:
                    errs.append(f"{where}: slot {r['slot']!r} không có trong slot_specs.json"); continue
                key = r["text"].lower()
                if key in seen:
                    errs.append(f"{where}: câu trùng"); continue
                seen.add(key)
                out = {"id": f"{batch}-{i:04d}", "batch": batch, "prompt_id": r["prompt_id"], "slot": r["slot"],
                       "label": "positive" if r["label"] == "multi" else r["label"], "multi": r["label"] == "multi",
                       "text": r["text"], "region": r["region"], "style": r["style"], "structure": r["structure"]}
                if r["label"] == "hard_negative":
                    if r["value"] or r["span"]:
                        errs.append(f"{where}: hard_negative không được có value/span"); continue
                    out["value"] = None
                else:
                    try:
                        out["value"] = parse_value(r["slot"], r["value"])
                    except ValueError as e:
                        errs.append(f"{where}: {e}"); continue
                    if not r["span"] or r["span"].lower() not in r["text"].lower():
                        errs.append(f"{where}: span {r['span']!r} không nằm trong câu"); continue
                    out["span"] = r["span"]
                if r["extra"]:
                    k, _, v = r["extra"].partition("=")
                    try:
                        out["extra"] = {k: parse_value(k, v)}
                    except (ValueError, KeyError) as e:
                        errs.append(f"{where}: extra {e}"); continue
                rows.append(out)
    assign_splits(rows)
    return rows, errs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    spec = json.load(open(SPEC, encoding="utf-8"))
    rows, errs = load(spec)
    for e in errs:
        print("LỖI", e)
    from check_overlap import overlapping
    bad = overlapping([r["text"] for r in rows])
    kept = [r for i, r in enumerate(rows) if i not in bad]
    print(f"{len(rows)} câu hợp lệ, {len(errs)} lỗi định dạng, {len(bad)} câu trùng n-gram với holdout/test (đã loại)")
    by = {}
    for r in kept:
        by.setdefault(r["slot"], []).append(r)
    for s, lst in sorted(by.items()):
        neg = sum(r["label"] == "hard_negative" for r in lst)
        print(f"  {s:<22} {len(lst):>4} câu · phản ví dụ {neg / len(lst):.0%} · eval {sum(r['split'] == 'eval' for r in lst)}")
    if a.check or errs:
        sys.exit(1 if errs else 0)
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "*.jsonl")):
        os.remove(f)
    for s, lst in by.items():
        with open(os.path.join(OUT, f"{s}.jsonl"), "w", encoding="utf-8") as fh:
            for r in lst:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    batches = sorted({r["batch"] for r in kept})
    manifest = {"generator": GENERATOR, "spec": "datagen/slot_specs.json", "updated": dt.date.today().isoformat(),
                "split_rule": "theo từng slot: nhóm prompt_id xếp theo sha1, ~30% nhóm đầu → eval (đo), còn lại → mine (rút cue)",
                "overlap_removed": len(bad), "batches": [
                    {"batch": b, "n": sum(r["batch"] == b for r in kept),
                     "by_slot": {s: sum(r["batch"] == b and r["slot"] == s for r in kept) for s in sorted(by)}}
                    for b in batches],
                "total": len(kept), "stop_rule": "dừng khi một đợt mới không cho cue mới được duyệt và không đổi "
                                                 "recall/precision trên real_ref.jsonl quá 1 điểm (PLAN A-D2)"}
    for p in (os.path.join(SRC, "manifest.json"), os.path.join(OUT, "manifest.json")):
        json.dump(manifest, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"→ {OUT} ({len(kept)} câu), manifest datagen/synth_slots/manifest.json")


if __name__ == "__main__":
    main()
