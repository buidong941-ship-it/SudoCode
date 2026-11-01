"""Check frozen BTC-like sample integrity and source separation offline."""

import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.btc_like_report import verify_manifest  # noqa: E402


def turns(root):
    found = set()
    for path in root.glob("*.json"):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        found.update(text.casefold().strip() for call in scenario["calls"].values()
                     for text in call["customer_turns"])
    return found


def run():
    manifest_path = ROOT / "datagen" / "out_btc_like_final_v1" / "manifest.json"
    manifest, dev = verify_manifest(manifest_path, "dev")
    _, holdout = verify_manifest(manifest_path, "holdout")
    assert len(dev) == 28 and len(holdout) == 40
    assert sum(x["n_turns"] for x in holdout) == 200
    assert manifest["failed_count"] == 0
    raw = manifest_path.parent / "raw"
    for item in manifest["scenarios"]:
        path = raw / item["split"] / f"{item['scenario_id']}.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256_raw"]
    dev_text = turns(manifest_path.parent / "final" / "dev")
    holdout_text = turns(manifest_path.parent / "final" / "holdout")
    assert not dev_text & holdout_text
    phones = [{item["customer_phone"] for item in side} for side in (dev, holdout)]
    assert not phones[0] & phones[1]
    older = turns(ROOT / "test_set" / "public_sample")
    older |= turns(ROOT / "datagen" / "out_nat" / "dev")
    older |= turns(ROOT / "datagen" / "out_nat" / "test")
    assert not (dev_text | holdout_text) & older
    print("frozen BTC-like benchmark checks OK")


if __name__ == "__main__":
    run()
