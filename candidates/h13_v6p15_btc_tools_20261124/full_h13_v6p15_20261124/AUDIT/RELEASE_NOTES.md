# H13 UTF-8 correction release r3

Supersedes `h13_revised_20261122` r2. Its Kaggle structure validator passed, but that result did not verify Vietnamese text. The r2 runtime text is corrupted in 10 cases (029–032, 047/048, 067/068, 085/086); six other cases have corrupted notes. Use this new release for future runs.

85 text fields were restored in 16 scenarios, including dialogue, clarification criteria, notes, addresses and synthetic customer identity. `UTF8_REPAIR_LEDGER.json` records each original and corrected string. H13-086's name `H?` is ambiguous; the new fixture explicitly uses the synthetic name Hà. No numeric, tool, order, price or guardrail assertions were changed. The old release and blocked canary remain preserved as evidence.

Fresh checks on Kaggle must verify strict UTF-8, embedded/repeated question marks, exact text-only scope, declared hashes, protected BTC hashes and all 86 fixtures with `datagen/validate.py`. The repair ledger intentionally retains damaged before-text outside runtime. Legitimate sentence-final question marks remain in customer questions.

No agent run or score is included. H13 is a known diagnostic set. Original unre-audited cases and unresolved identity controls remain listed in the original decision ledger; this correction does not certify their semantics.
