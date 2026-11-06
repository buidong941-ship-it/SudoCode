# BTC-like benchmark and confidence gate

The team-created sample is a simulation, not an official BTC sample or hidden
test. The **only retained benchmark** is `datagen/out_btc_like_final_v1/`:
`raw/` holds the generator output, `final/` holds the reviewed Qwen wording,
and `manifest.json` freezes SHA-256 hashes of all 68 final scenarios. It has
28 dev scenarios (140 customer turns) and 40 holdout scenarios (200 turns).
`curation_review.jsonl` records the 41 rewrites restored to raw after manual
review; `rewrite_review.jsonl` lists all 156 turns changed by Qwen. Both
splits pass strict validation without errors or warnings and have no exact
customer-turn overlap. The raw and final scenarios are deliberately in one
directory; the cancelled pilot benchmark copies were removed.

## Reproduce and validate

Templates are in `datagen/templates_btc_like/`. To generate a fresh raw copy,
choose a new output path, then validate and freeze it:

```bash
python datagen/templates_btc_like/build_templates.py
python datagen/generate_btc_like_benchmark.py --seed 20261030 --out runs/btc_like_rebuild
python datagen/validate.py runs/btc_like_rebuild/raw/dev runs/btc_like_rebuild/raw/holdout --strict --report runs/btc_like_rebuild/validate_raw.json
python datagen/generate_btc_like_benchmark.py --out runs/btc_like_rebuild --freeze raw
python tests/btc_like_benchmark_check.py
```

`scripts/naturalize_btc_like_job.py` runs `datagen/naturalize.py --backend
qwen` on Kaggle; the source notebook was
`midzid/sudocode-btc-naturalize-v2`. The generator rejects overwriting a
frozen benchmark; choose a new output path for any new naturalization run.
Keep credentials outside the repository.

## Runtime and evaluation

`EXTRACTOR_CONFIDENCE_GATE=1` enables six-check rule certificates for clear
customer slots and agent questions under `--extractor hybrid`. Uncertified
turns can use `EXTRACTOR_JEV_HYBRID=1` with `TYPESAFE_API_KEY`: Jev classifies
customer slot labels, agent question labels, and claim labels. Local rules
must ground values in the original sentence; unresolved labels and Jev errors
fall back to the existing span-checked Qwen extractor. Jev classification of
customer slots and claims still needs independent quality validation before
using it for a production decision. Both experimental flags default to off.

The paired dev run uses the frozen `final/dev` path:
`felicityabby/sudocode-btc-confidence-final-dev-paired`, with identical
`full` and `baseline_no_memory` scenarios for current and gate variants.
That completed run predates `EXTRACTOR_JEV_HYBRID` and does not measure Jev
extractor quality. A new dev run with the Kaggle Jev secret is required.
Use `scripts/btc_like_report.py` with this manifest to check trace counts and
hashes before comparing scores. Select a design on dev before opening the
frozen holdout once. Do not enable the gate by default without whole-agent
metric and latency evidence.
