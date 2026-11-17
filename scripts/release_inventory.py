"""Read-only Git release inventory; retain every local file and print no file contents.

Usage: python scripts/release_inventory.py --out-dir runs/release-inventory
This does NOT stage, untrack, delete, commit or push. It is not a secret scanner.
"""
import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOTS = {
    "runs", "data", "dataset", "build", "workbench", "artifacts", "models",
    "venv", ".venv", ".vllm-venv", "_upload", "_download", ".git",
    ".claude", ".codex", ".agents", ".aws", ".pytest_cache", "__pycache__",
}
PROCESS_DOCS = ("docs/PLAN/", "docs/DE-XUAT/", "docs/NHAT-KY/")
SECRET_NAMES = {".env", "kaggle.json", "credentials.json", "token.json", "secrets.toml"}


def git_paths(*args):
    result = subprocess.run(
        ["git", "ls-files", "-z", *args], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        # Do not echo raw stderr, environment, auth configuration or file contents.
        hint = "git_read_failed"
        if b"unsafe repository" in result.stderr or b"dubious ownership" in result.stderr:
            hint = "git_ownership_check_failed; resolve trust explicitly; global config was not changed"
        raise RuntimeError(hint)
    return sorted(set(p.decode("utf-8", errors="surrogateescape") for p in result.stdout.split(b"\0") if p))


def reasons_for(path):
    p = Path(path)
    posix = p.as_posix()
    reasons = []
    if p.parts and p.parts[0] in LOCAL_ROOTS:
        reasons.append("local_runtime_or_artifact_root")
    if posix.startswith(PROCESS_DOCS):
        reasons.append("process_document_keep_locally_review_for_public_release")
    if p.name.lower() in SECRET_NAMES or (p.name.startswith(".env.") and not p.name.endswith(".example")):
        reasons.append("potential_credential_filename")
    if posix.startswith(".streamlit/") and p.name == "secrets.toml":
        reasons.append("streamlit_secret")
    if p.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".log", ".pyc", ".safetensors", ".gguf"}:
        reasons.append("generated_or_large_binary_type")
    if posix.startswith("datagen/out") or posix.startswith("asr/audio/"):
        reasons.append("dataset_or_audio_artifact")
    if posix.startswith("datagen/datasets/releases/") and any(
        part in {"raw", "final", "templates"} for part in p.parts
    ):
        reasons.append("guarded_or_generated_release_content")
    if posix == "datagen/datasets/index.jsonl" or posix.endswith("/resolved/holdout_h13.json"):
        reasons.append("review_sealed_dataset_metadata_exposure_without_opening_cases")
    if posix.startswith("kaggle/jobs/") or posix.startswith("improve/approved/"):
        reasons.append("review_curated_release_subset_not_entire_experiment_history")
    if p.name == "CLAUDE_HANDOFF_UI_C5_RELEASE.md":
        reasons.append("local_handoff_instructions")
    return reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="runs/release-inventory")
    parser.add_argument("--large-mib", type=float, default=20)
    args = parser.parse_args()
    out = Path(args.out_dir)
    if not out.is_absolute():
        out = ROOT / out
    out = out.resolve()
    repo = ROOT.resolve()
    if out != repo and repo not in out.parents:
        parser.error("out-dir must stay inside the project")
    if out == repo or out == repo / ".git" or repo / ".git" in out.parents:
        parser.error("use a separate report directory outside .git")
    if args.large_mib <= 0:
        parser.error("large-mib must be positive")
    out.mkdir(parents=True, exist_ok=True)
    try:
        tracked = git_paths("--cached")
        untracked = git_paths("--others", "--exclude-standard")
        tracked_ignored = git_paths("--cached", "--ignored", "--exclude-standard")
    except (RuntimeError, OSError) as exc:
        error = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        (out / "inventory_error.json").write_text(
            json.dumps({"status": "failed", "reason": error, "mutated_git": False}, indent=2),
            encoding="utf-8",
        )
        print("Inventory failed; no Git mutations. See inventory_error.json.")
        return 2
    review = []
    large = []
    for path in sorted(set(tracked + untracked)):
        reasons = reasons_for(path)
        if reasons:
            review.append({"path": path, "tracked": path in tracked, "reasons": reasons})
        try:
            size = (ROOT / path).lstat().st_size
        except OSError:
            continue
        if size >= args.large_mib * 1024 * 1024:
            large.append({"path": path, "bytes": size, "tracked": path in tracked})
    report = {
        "status": "review_required", "mutated_git": False,
        "scope": "Git working-tree paths only; ignored untracked files and history are not scanned",
        "not_a_secret_scan": True, "tracked": tracked, "untracked_not_ignored": untracked,
        "tracked_matching_gitignore": tracked_ignored, "review_candidates": review,
        "large_files": large,
    }
    (out / "inventory.json").write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    lines = [
        "# GitHub release inventory", "", "Read-only inventory. No local file or Git index was removed.",
        "This lists paths, not file contents. It is not a credential scan or release approval.", "",
        f"Tracked: {len(tracked)}; untracked not ignored: {len(untracked)}; "
        f"tracked matching ignore: {len(tracked_ignored)}; review candidates: {len(review)}.",
        "", "## Tracked files still covered by ignore rules", "",
    ]
    lines.extend(f"- `{p}`" for p in tracked_ignored)
    lines += ["", "## Candidate paths for review; do not delete automatically", ""]
    lines.extend(f"- `{r['path']}` ({'tracked' if r['tracked'] else 'untracked'}): "
                 + ", ".join(r["reasons"]) for r in review)
    lines += ["", "## Large files", ""]
    lines.extend(f"- `{r['path']}`: {r['bytes']} bytes" for r in large)
    (out / "inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Inventory written: {out.relative_to(repo).as_posix()}; review required; no Git mutations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
