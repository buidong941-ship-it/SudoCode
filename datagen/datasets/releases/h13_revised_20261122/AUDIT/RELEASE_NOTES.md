# H13 revised 2026-11-22 — fixture revision, not an agent result

This is a new, known diagnostic suite derived from the locked 84-case H13 suite. The old suite, R0/D1 traces, candidate traces, BTC evaluator, BTC mock tools, schema, and public samples remain untouched. H13 is already exposed and this release cannot serve as an independent holdout.

## What changed

- H13-029–032 now explicitly test editing a draft cart before the customer submits it. The customer does not ask the agent to create an order until the final positive confirmation; the negative branches retain the no-order requirement when the requested variant is unavailable.
- H13-085 tests changing the variant of an existing order through `order.update`. H13-086 tests a cancellation request on an existing order; because the BTC mock has no cancel action, success means handoff with the request and next action in the brief. A handoff ticket is not described as a completed cancellation.
- H13-047/048 and H13-067/068 accept additional direct clarification phrasings while preserving the prohibition on `order.create` for unresolved product/channel identity. `must_say_any` remains lexical; the AUDIT checks include a negative example where a matching phrase is not a real clarification.
- The scalar `ground_truth_facts.price_vnd` was removed only for H13-025–028 and H13-045–048 call_1, where two differently priced products are requested. Per-SKU quotes, call date, promotions, and any basket total are in `AUDIT/SUPPLEMENTAL_TRUTH.jsonl`. The product/transaction assertions were not relaxed. Removing those scalar fields reduces BTC evaluator HR coverage; do not compare HR with the old release as if it were the same denominator.
- H13-037–040 order and total assertions remain unchanged; item prices are added to the supplemental truth ledger. H13-045/046 cheaper-item expectations, H13-055/056 product-condition constraints, and H13-065/066 cross-channel expectations remain unchanged.

## Review limits / unresolved

The case ledger marks all copied cases that were not individually re-audited. Dates, prices, inventory, promotions, and all 84 source dialogues have not been manually re-certified. Identity controls for a same-number self-claim, proxy/other-person claim, multiple claims, and absent linkage are left undecided: the current scenario schema lacks a reliable verification event, so adding expected outcomes without an explicit identity contract would encode assumptions. The modified phrase criteria are lexical and need human review for semantic false positives.

No agent was run on this release and no score is reported. Kaggle fixture validation completed on the private kernel `midzid/sudocode-h13-revised-fixture-validation`, version 2. It checked 86 scenarios, 162 calls, and 346 customer turns: 0 errors and 0 warnings. H13-086 has one informational `brief_extra` notice for the optional `escalation_reason_detail` field; it is an allowed schema property and is explicitly checked by `brief_must_contain`. The report is `runs/kaggle/h13-revised-fixture-validation/out/h13_revised_validation.json`. The first kernel attempt exited after validation because its report directory did not exist; version 2 corrected the output path and completed. No agent was run and no score was produced.
