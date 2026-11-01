#!/usr/bin/env python3
"""Build an independent, BTC-shaped simulated benchmark from new templates.

The holdout is separated by template, never by instances of one template.
Use --freeze raw (or final after naturalization and validation) before evaluation.
"""

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datagen.resolver import Resolver, load_templates, spoken, teen  # noqa: E402

VERSION = 2
DEFAULT_TEMPLATES = ROOT / "datagen" / "templates_btc_like"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_calls_turns(scenario):
    calls = list(scenario["calls"].values())
    return len(calls), sum(len(call["customer_turns"]) for call in calls)


def freeze(out, source):
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["failures"]:
        raise SystemExit("Cannot freeze: scenario generation has failures")
    files = {}
    for item in manifest["scenarios"]:
        rel = f"{source}/{item['split']}/{item['scenario_id']}.json"
        path = out / rel
        if not path.is_file():
            raise SystemExit(f"Missing evaluation scenario: {rel}")
        scenario = json.loads(path.read_text(encoding="utf-8"))
        if scenario["scenario_id"] != item["scenario_id"]:
            raise SystemExit(f"Scenario ID changed: {rel}")
        files[rel] = digest(path)
    report = out / f"validate_{source}.json"
    if not report.is_file():
        raise SystemExit(f"Validate the {source} scenarios first: {report}")
    validation = json.loads(report.read_text(encoding="utf-8"))
    if validation.get("errors") or validation.get("warnings"):
        raise SystemExit(f"Validation is not clean: {report}")
    validated_ids = {item["scenario_id"] for item in validation.get("scenarios", [])}
    expected_ids = {item["scenario_id"] for item in manifest["scenarios"]}
    if validated_ids != expected_ids:
        raise SystemExit("Validation report does not cover exactly the evaluation scenarios")
    if report.stat().st_mtime_ns < max((out / rel).stat().st_mtime_ns for rel in files):
        raise SystemExit("Validation report is older than an evaluation scenario")
    previous = manifest.get("frozen")
    if previous and previous != {"source": source, "sha256": files}:
        raise SystemExit("Benchmark is already frozen with different bytes; create a new version")
    manifest["frozen"] = {"source": source, "sha256": files}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(files)} {source} scenarios in {manifest_path}")


def generate(args):
    previous = args.out / "manifest.json"
    if previous.is_file() and json.loads(previous.read_text(encoding="utf-8")).get("frozen"):
        raise SystemExit("Benchmark is frozen; use a new --out directory for a new version")
    templates = load_templates(str(args.templates))
    if not templates:
        raise SystemExit("No benchmark templates found")
    resolver = Resolver(str(ROOT), seed=args.seed)
    scenarios = []
    failures = []
    seen_ids = set()
    phones = collections.defaultdict(set)
    utterances = collections.defaultdict(set)
    coverage = collections.Counter()
    for template in templates:
        split = template.get("split")
        if split not in ("dev", "holdout"):
            raise SystemExit(f"{template['template_id']}: explicit dev/holdout split required")
        if template.get("scenario", {}).get("persona") not in resolver.personas:
            raise SystemExit(f"{template['template_id']}: unknown persona")
        for instance in range(template.get("instances", 1)):
            scenario_id = f"BTCL-{len(scenarios) + len(failures) + 1:03d}"
            scenario, stats = resolver.build(template, instance, split, scenario_id=scenario_id)
            if scenario is None:
                failures.append({"template_id": template["template_id"], "instance": instance,
                                 "leaves_tried": stats["leaves"], "last_error": stats["last_err"]})
                continue
            if scenario_id in seen_ids:
                raise SystemExit(f"Duplicate scenario_id: {scenario_id}")
            seen_ids.add(scenario_id)
            for call in scenario["calls"].values():
                mode = call.get("input_mode")
                if mode in ("asr_transcript", "chat_teencode"):
                    transform = spoken if mode == "asr_transcript" else teen
                    call["customer_turns_asr"] = [transform(s) for s in call["customer_turns"]]
            phone = scenario["customer_phone"]
            phones[split].add(phone)
            for call in scenario["calls"].values():
                for utterance in call["customer_turns"]:
                    utterances[split].add(utterance.strip().casefold())
                coverage[f"channel:{call.get('channel', 'hotline')}"] += 1
                coverage[f"input:{call.get('input_mode', 'text')}"] += 1
            if scenario.get("hard_case"):
                coverage[f"hard_case:{scenario['hard_case']}"] += 1
            n_calls, n_turns = count_calls_turns(scenario)
            path = args.out / "raw" / split / f"{scenario_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            scenarios.append({"scenario_id": scenario_id, "template_id": template["template_id"],
                              "template_file": template["_file"], "split": split,
                              "customer_phone": phone, "n_calls": n_calls, "n_turns": n_turns,
                              "hard_case": scenario.get("hard_case"), "sha256_raw": digest(path)})
    overlap_phones = phones["dev"] & phones["holdout"]
    overlap_text = utterances["dev"] & utterances["holdout"]
    if overlap_phones or overlap_text:
        raise SystemExit(f"Split leakage: {len(overlap_phones)} phones and {len(overlap_text)} identical turns")
    by_split = {split: {"scenarios": sum(s["split"] == split for s in scenarios),
                        "calls": sum(s["n_calls"] for s in scenarios if s["split"] == split),
                        "turns": sum(s["n_turns"] for s in scenarios if s["split"] == split)}
                for split in ("dev", "holdout")}
    manifest = {"generator_version": VERSION, "seed": args.seed,
                "provenance": "Team-created simulated BTC-like sample; not an official BTC sample or hidden test",
                "fact_sources": ["catalog/", "policy/", "eval/mock_tools.py"],
                "templates": [{"id": t["template_id"], "file": t["_file"], "split": t["split"],
                               "instances": t.get("instances", 1)} for t in templates],
                "splits": by_split, "coverage": dict(sorted(coverage.items())),
                "scenarios": scenarios, "failures": failures, "failed_count": len(failures)}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"splits": by_split, "failed_count": len(failures), "coverage": manifest["coverage"]},
                     ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(f"Failed to generate {len(failures)} scenarios; see manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES)
    parser.add_argument("--seed", type=int, default=20261030)
    parser.add_argument("--out", type=Path, required=True,
                        help="New output directory; a frozen benchmark cannot be overwritten")
    parser.add_argument("--freeze", choices=("raw", "final"))
    args = parser.parse_args()
    args.out = args.out.resolve()
    if args.freeze:
        freeze(args.out, args.freeze)
    else:
        generate(args)


if __name__ == "__main__":
    main()
