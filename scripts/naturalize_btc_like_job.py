#!/usr/bin/env python3
"""Naturalize the frozen raw BTC-like sample on Kaggle and validate final bytes.

The output directory is meant for /kaggle/working/out so it can be downloaded.
No API credentials, source facts, or assertions are written into job arguments.
"""

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datagen.naturalize import anchors_kept  # noqa: E402


def run(*args):
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True)


def audit(raw_root, final_root, manifest, target):
    changed = []
    for item in manifest["scenarios"]:
        rel = Path(item["split"]) / f"{item['scenario_id']}.json"
        raw = json.loads((raw_root / rel).read_text(encoding="utf-8"))
        final = json.loads((final_root / rel).read_text(encoding="utf-8"))
        comparable = copy.deepcopy(final)
        comparable["_meta"] = raw["_meta"]
        for name, call in raw["calls"].items():
            original = call["customer_turns"]
            rewritten = final["calls"][name]["customer_turns"]
            if len(original) != len(rewritten):
                raise ValueError(f"Turn count changed: {rel} {name}")
            for index, (old, new) in enumerate(zip(original, rewritten), 1):
                if old != new:
                    kept, reason = anchors_kept(old, new)
                    if not kept:
                        raise ValueError(f"Anchor lost: {rel} {name} #{index}: {reason}")
                    changed.append({"scenario_id": item["scenario_id"], "split": item["split"],
                                    "call": name, "turn": index, "original": old, "rewritten": new})
            comparable["calls"][name]["customer_turns"] = original
        if comparable != raw:
            raise ValueError(f"Non-dialogue scenario data changed: {rel}")
    target.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in changed) + "\n", encoding="utf-8")
    if not changed:
        raise ValueError("No dialogue was rewritten; inspect Qwen and the naturalize report")
    print(f"Audited {len(changed)} rewritten turns; review each line in {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "datagen" / "out_btc_like_final_v1")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    source = args.source.resolve()
    target = args.out.resolve() / "benchmark"
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    # The curated benchmark also retains exact raw bytes and their source hashes.
    for item in manifest["scenarios"]:
        path = source / "raw" / item["split"] / f"{item['scenario_id']}.json"
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256_raw"]:
            raise SystemExit(f"Raw source missing or changed: {path}")
    manifest.pop("frozen")
    manifest["naturalized_backend"] = "qwen"
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run(ROOT / "datagen" / "naturalize.py", "--src", source / "raw", "--out", target / "final",
        "--splits", "dev", "holdout", "--workers", args.workers, "--backend", "qwen")
    audit(source / "raw", target / "final", manifest, target / "rewrite_review.jsonl")
    run(ROOT / "datagen" / "validate.py", target / "final" / "dev", target / "final" / "holdout",
        "--strict", "--report", target / "validate_final.json")
    run(ROOT / "datagen" / "generate_btc_like_benchmark.py", "--out", target, "--freeze", "final")
    print(f"Naturalized benchmark ready for review at {target}")


if __name__ == "__main__":
    main()
