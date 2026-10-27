# Repository Guidelines

## Project Structure & Module Organization

This repository implements a Vietnamese call-center agent and its evaluation harness. Core runtime code lives in `harness/`, shared configuration and utilities in `core/`, and speech transcription in `asr/`. MCP services are in `mcp_servers/`; product and customer fixtures are in `catalog/`; policy content and schemas are in `policy/` and `schemas/`. Scenario generation is in `datagen/`, evaluation code in `eval/`, and runnable scenarios in `test_set/`. Automated checks live in `tests/`. Keep generated traces and local runtime data under `runs/` or `data/`, not alongside source modules.

## Build, Test, and Development Commands

Use Python 3 and install required packages with `pip install -r requirements.txt`. Create local configuration from `.env.example`; keep real credentials in `.env` and never commit them.

- `bash tests/smoke.sh` runs the offline and mocked integration checks without live API credentials.
- `python run_eval.py --scenarios test_set/public_sample --config full --out runs/local/full.jsonl` runs the full agent against the sample scenarios.
- `python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/local/full.jsonl` scores an evaluation trace.
- `python run_rag_eval.py --download` downloads the configured embedding model when preparing vector RAG evaluation.

The smoke script uses Bash; run it in a Bash-compatible environment such as Linux, WSL, or Git Bash.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, descriptive `snake_case` for modules, functions, and variables, and `PascalCase` for classes. Keep scenario and fixture formats consistent with neighboring JSON files and the schemas in `schemas/`. Prefer small changes that preserve existing CLI options and trace formats. No repository-wide formatter or linter is configured; match the surrounding code.

## Testing Guidelines

Add or update focused checks under `tests/` for behavior changes, and use descriptive names such as `*_check.py` or `*_parity.py` to match existing tests. Run the smoke suite for changes affecting runtime integration, evaluation, MCP behavior, privacy, or scenario handling. Keep checks deterministic and avoid requiring live services when a mock is sufficient.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects that describe one change (for example, `Fix MCP trace parity`). In pull requests, explain the behavior changed, list validation commands and their results, link the relevant issue or task, and include sample output or screenshots when they clarify an evaluation or user-visible change. Call out configuration or data format changes explicitly.

## Security & Configuration

Never commit API keys, `.env` files, customer secrets, or generated personal data. Use `.env.example` for documenting required variable names, without real values. Treat PII masking and trace logging behavior as privacy-sensitive when editing the agent or tools.
