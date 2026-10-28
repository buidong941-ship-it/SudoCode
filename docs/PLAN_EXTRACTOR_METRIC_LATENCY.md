# Plan: Improve Extractor Metrics and Reduce Latency

## Objective

Continue improving the call-center agent extractor on two fronts:

1. Improve extraction quality for `questions`, `claims`, `customer_slots`, and `facts_used` without fine-tuning.
2. Reduce and measure end-to-end latency, including work that currently happens after the agent has prepared its reply.

This document is intended to be handed to a coding session. Inspect the current checkout first, preserve unrelated work, implement the remaining changes, and validate them against the project’s existing evaluation data and runtime.

## Repository context

- Runtime: `harness/agent.py`
- Rules and hybrid extraction: `harness/extractor.py`, `harness/llm_extract.py`
- Extractor evaluation: `scripts/extract_eval.py`
- Latency reporting: `scripts/latency_report.py`
- Trace schema: `schemas/trace_log.schema.json`
- Focused checks: `tests/extractor_quality_check.py`, `tests/llm_extract_check.py`, `tests/question_detection_check.py`, `tests/coverage_check.py`
- Run history and rationale: `docs/NHAT-KY-2026-10-27.md`, `docs/NHAT-KY-2026-10-28.md`

Repository-specific requirements are in `AGENTS.md`. Do not commit credentials, `.env`, customer secrets, or generated personal data. Keep local runs under `runs/` or `data/`.

## Findings from previous runs

Use these as historical baselines, not as claims about the current implementation:

- The previous Jev + rules held-out run on 40 test rows reported P=100%, R=80%, F1=88.9%, with 3 false negatives out of 15 positives; p95 extractor latency was about 275 ms.
- Existing hybrid dev evaluation reported strong performance: questions P/R 100/93.3%, claims 94.4/98.1%, customer slots 94.9/92.5%.
- An older Qwen + hybrid runtime trace with 129 turns and two generation workers reported response-ready latency p50/p95 around 4.64/8.16 s, post-processing p50/p95 around 8.07/13.00 s, and estimated end-to-end p50/p95 around 12.79/19.73 s. Older traces may not include `end_to_end_ms`; use `total_ms + post_ms` only as an estimate for those traces.
- The extractor itself was not the dominant contributor to that Qwen end-to-end latency. Do not claim a real Qwen latency reduction until a comparable real-model run is available.
- Fine-tuning is out of scope. Keep the default question classifier setting unchanged unless the evaluation shows a clear, measured reason to change it.
- `GEN_PARALLEL_N=2` can wait for the slower of two generated candidates. Do not change generation worker behavior without an explicit quality/latency ablation.

## Current implementation to inspect before editing

A previous pass has already made changes in the following areas. Verify these exist and work before reimplementing them:

- `harness/extractor.py`: expanded question/request and blocker cues; improved price, objection, and promotion rules; exact matching for nested tool arguments in `facts_used`; customer-LLM candidate gating.
- `harness/llm_extract.py`: hybrid customer-slot extraction can skip the LLM when there is no candidate signal.
- `harness/agent.py`: starts agent extraction concurrently with pending customer-slot collection; records `end_to_end_ms` and post-processing timing parts; reclassifies questions after customer slots become known.
- `schemas/trace_log.schema.json`: supports new latency fields while retaining backward compatibility.
- `scripts/extract_eval.py`: evaluates `facts_used.jsonl`.
- `scripts/latency_report.py`: reports response-ready, post, end-to-end, and post-part latency percentiles.
- `tests/extract_eval/facts_used.jsonl`, `tests/extractor_quality_check.py`: focused regression/gate fixtures.

Current dev-only numbers from the previous pass were P/R/F1 100/100/100 for rules questions, claims, and customer slots on the available labeled dev set; the small self-authored `facts_used` regression fixture also scored 100/100/100. These are regression signals, not independent or held-out proof. The customer-slot gate skipped 12 of 60 examples while preserving coverage of gold slots in that check.

## Work plan

### 1. Establish the starting state

1. Read `AGENTS.md`, the two diary files above, and the files listed under “Current implementation”.
2. Inspect `git status` and the current diff without changing global Git configuration. If Git reports an unsafe repository, continue by inspecting files directly; do not weaken repository safety settings.
3. Confirm which listed implementation changes are already present. Do not overwrite unrelated user changes or duplicate existing code.
4. Record exact commands, dataset paths, model/config, worker count, and baseline metrics used for all new comparisons.

### 2. Improve extractor quality safely

1. Run `scripts/extract_eval.py` across the available labeled agent and customer dev data for `rules` and `hybrid` modes; save per-task TP/FP/FN and P/R/F1, not only aggregate scores.
2. Review false positives and false negatives by category. Prioritize high-impact misses in questions, claims, customer slots, and `facts_used`.
3. Add a focused regression case for each corrected error. Prefer real labeled examples already present in the repository; label synthetic cases clearly.
4. Keep regexes narrow and Vietnamese-aware. Check accent folding, word boundaries, negation, quoted text, and nearby entity scope. A higher dev score caused by broad matching is not an improvement.
5. For any hybrid LLM gate, test both the no-cue skip path and borderline short contextual replies. The gate must not drop gold-positive examples in the available coverage check.
6. Re-run the held-out Jev benchmark separately from dev. Report precision, recall, F1, TP/FP/FN, and latency for both rules-only and Jev + rules. Do not tune against the test split; use the tune split for changes and retain the test split for final reporting.
7. Avoid fine-tuning and avoid changing `QUESTION_CLF` defaults unless explicitly justified by measured results.

### 3. Reduce and measure end-to-end latency

1. Use `scripts/latency_report.py` on the existing Qwen trace and any newly generated traces. Report p50/p95 for response-ready, post, end-to-end, and each `post_parts_ms` field.
2. Preserve the distinction between `latency.total_ms` (reply ready) and `latency.end_to_end_ms` (work complete). For older traces without `end_to_end_ms`, show the value as an estimate from `total_ms + post_ms`.
3. Check that agent extraction and customer-slot extraction overlap instead of running sequentially. Ensure final question types are corrected after customer slot values arrive.
4. Use the customer-slot candidate gate only when the gate coverage check passes. Compare hybrid output quality and LLM request count before and after gating.
5. Profile the runtime before optimizing other components. Separate router, generation, extractor, memory, and logging time where available. Do not attribute Qwen generation time to the extractor.
6. Keep the generation candidate count and worker setting fixed during the latency comparison. If changing it is considered, run a paired quality/latency ablation and report the tradeoff.
7. Run a comparable real-Qwen workload before claiming a latency win: same scenarios, config, machine/environment, concurrency, and generation-worker setting. If credentials or service are unavailable, report implementation/integration validation only and leave real-model impact unverified.

### 4. Validate and report

Use focused commands first:

```powershell
venv/Scripts/python.exe -X utf8 tests/llm_extract_check.py
venv/Scripts/python.exe -X utf8 tests/extractor_quality_check.py
venv/Scripts/python.exe -X utf8 tests/question_detection_check.py
venv/Scripts/python.exe -X utf8 tests/coverage_check.py
venv/Scripts/python.exe -X utf8 -m py_compile harness/extractor.py harness/llm_extract.py harness/agent.py scripts/extract_eval.py scripts/latency_report.py
```

Then run extractor dev evaluation in rules and hybrid modes using the CLI help/current options, and produce a latency report for both the historical Qwen trace and the new trace. Run the repository smoke suite if the environment supports Bash (`bash tests/smoke.sh`). If unavailable, state the environment issue and run the applicable focused checks; do not claim the smoke suite passed.

Validate a representative generated JSONL record against `schemas/trace_log.schema.json` and verify:

- `end_to_end_ms >= total_ms` for new traces.
- `post_ms` is non-negative and timing parts are present when the corresponding work runs.
- Old trace records still parse and can be reported.
- No sensitive data or credentials were added to generated fixtures or logs.

## Acceptance criteria

- No regression in the existing focused checks or trace schema compatibility.
- Quality results are reported separately for dev, tune, and held-out test data. No test-set tuning.
- Each rule change has a corresponding regression case and no unexplained false-positive increase.
- The hybrid customer-slot gate demonstrates gold-slot coverage on the available labeled data and reports saved LLM calls.
- New traces report both response-ready and end-to-end latency, with useful post-processing breakdowns.
- A real latency improvement is claimed only after a comparable real-Qwen before/after run. Otherwise clearly state that the code path is implemented but the production-model speedup remains unmeasured.
- Final handoff lists changed files, exact validation commands/results, metric deltas, latency deltas, and remaining limitations.

## Guardrails

- Preserve existing CLI options and trace formats; schema additions should remain optional for old traces.
- Do not change model, generation-worker count, or routing behavior as an incidental optimization.
- Do not add broad rules merely to maximize dev scores.
- Do not add or commit generated real customer data, credentials, or `.env` files.
- Keep all generated evaluation output under `runs/` or `data/`.
