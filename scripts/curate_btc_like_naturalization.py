#!/usr/bin/env python3
"""Review Qwen rewrites and restore turns whose intent or speaker changed.

Run after downloading the completed btc-naturalize-v2 Kaggle output. This
creates a new benchmark version; it never edits the frozen raw or Kaggle copy.
"""

import argparse
import copy
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "datagen" / "out_btc_like_final_v1" / "raw"
DEFAULT_QWEN = ROOT / "runs" / "kaggle" / "btc-naturalize-v2" / "out" / "btc-naturalize-v2" / "benchmark"

# Manually reviewed against the raw turn and the scenario's expected facts.
# Reasons are recorded in curation_review.jsonl for a reproducible audit.
REVERT = {
    "BTCL-002/call_1/1": "Turns a request for a purifier into buying the room",
    "BTCL-006/call_2/2": "Adds an unrequested refusal to buy",
    "BTCL-007/call_2/1": "Drops the request to confirm today's promotion",
    "BTCL-007/call_2/2": "Adds an unrequested refusal to buy",
    "BTCL-010/call_1/2": "Changes customer request into agent's offer",
    "BTCL-010/call_2/1": "Changes whether the promotion changed into whether it can be exchanged",
    "BTCL-011/call_1/1": "Changes customer speaker into agent",
    "BTCL-013/call_2/1": "Confuses customer and agent speaker",
    "BTCL-014/call_1/1": "Adds wrong speaker address",
    "BTCL-014/call_1/3": "Adds agent claim that the item was recorded",
    "BTCL-015/call_1/1": "Adds wrong speaker address",
    "BTCL-015/call_1/3": "Adds agent claim that the item was recorded",
    "BTCL-019/call_2/2": "Changes request to agent into customer self-reminder",
    "BTCL-020/call_2/2": "Changes request to agent into customer self-reminder",
    "BTCL-022/call_1/2": "Addresses customer instead of agent",
    "BTCL-023/call_1/3": "Replaces decision to wait with a price question",
    "BTCL-024/call_1/1": "Changes comparison request into intent to buy both items",
    "BTCL-025/call_1/1": "Drops the comparison request",
    "BTCL-026/call_2/1": "Adds replacement of an owned item instead of a change in choice",
    "BTCL-041/call_1/2": "Changes return/refund question into exchange/refund question",
    "BTCL-041/call_2/1": "Turns earlier question into an unsupported hearsay claim",
    "BTCL-042/call_2/1": "Turns earlier question into an unsupported hearsay claim",
    "BTCL-046/call_1/2": "Duplicates negation in delivery availability question",
    "BTCL-047/call_1/1": "Changes customer speaker into agent",
    "BTCL-047/call_1/3": "Adds a delivery-time request",
    "BTCL-047/call_2/1": "Drops customer's choice to take the item",
    "BTCL-048/call_1/1": "Addresses customer instead of agent",
    "BTCL-050/call_1/1": "Addresses customer instead of agent",
    "BTCL-051/call_1/3": "Adds a price-negotiation intent",
    "BTCL-052/call_2/2": "Changes customer request into agent's offer",
    "BTCL-053/call_2/2": "Confuses customer and agent speaker",
    "BTCL-054/call_1/2": "Adds wrong speaker address",
    "BTCL-056/call_1/1": "Addresses customer instead of agent",
    "BTCL-056/call_1/2": "Changes friend into wife and adds a new purchase question",
    "BTCL-056/call_2/2": "Changes request to agent into customer self-check",
    "BTCL-057/call_1/1": "Addresses customer instead of agent",
    "BTCL-057/call_2/2": "Changes request to agent into customer self-check",
    "BTCL-065/call_1/1": "Adds unsupported claim about another buyer",
    "BTCL-065/call_1/2": "Moves a statement from a later turn",
    "BTCL-065/call_1/3": "Replaces decision to wait with a request for details",
    "BTCL-068/call_2/1": "Invents a time for the prior call",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--qwen", type=Path, default=DEFAULT_QWEN)
    parser.add_argument("--out", type=Path, required=True, help="New benchmark version directory")
    args = parser.parse_args()
    raw_root, qwen, out = args.raw.resolve(), args.qwen.resolve(), args.out.resolve()
    if out.exists():
        raise SystemExit(f"Output exists; refuse to overwrite: {out}")
    manifest = json.loads((qwen / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("frozen", {}).get("source") != "final":
        raise SystemExit("Qwen benchmark must be frozen before curation")
    reviewed = {f"{r['scenario_id']}/{r['call']}/{r['turn']}": r
                for line in (qwen / "rewrite_review.jsonl").read_text(encoding="utf-8").splitlines()
                if (r := json.loads(line))}
    if set(REVERT) - set(reviewed):
        raise SystemExit(f"Missing reviewed rewrites: {set(REVERT) - set(reviewed)}")
    shutil.copytree(qwen / "final", out / "final")
    shutil.copytree(raw_root, out / "raw")
    reviewed_rows = []
    for item in manifest["scenarios"]:
        rel = Path(item["split"]) / f"{item['scenario_id']}.json"
        path = out / "final" / rel
        scenario = json.loads(path.read_text(encoding="utf-8"))
        raw = json.loads((raw_root / rel).read_text(encoding="utf-8"))
        for call_name, call in scenario["calls"].items():
            for i, turn in enumerate(call["customer_turns"], 1):
                key = f"{item['scenario_id']}/{call_name}/{i}"
                if key in REVERT:
                    original = raw["calls"][call_name]["customer_turns"][i - 1]
                    if turn == original:
                        raise SystemExit(f"Expected a rewrite at {key}")
                    call["customer_turns"][i - 1] = original
                    reviewed_rows.append({"key": key, "reason": REVERT[key],
                                          "qwen": turn, "restored": original})
        path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = copy.deepcopy(manifest)
    del manifest["frozen"]
    manifest["naturalization_review"] = {
        "reviewed_changed_turns": len(reviewed),
        "restored_raw_turns": len(reviewed_rows),
        "review_file": "curation_review.jsonl",
        "source": "midzid/sudocode-btc-naturalize-v2",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "curation_review.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in reviewed_rows) + "\n", encoding="utf-8")
    (out / "rewrite_review.jsonl").write_bytes((qwen / "rewrite_review.jsonl").read_bytes())
    print(f"Created {out}; reviewed {len(reviewed)} rewrites and restored {len(reviewed_rows)} turns")


if __name__ == "__main__":
    main()
