"""Áp overlay candidate trong bản sao Kaggle; không chạm snapshot R0."""
from pathlib import Path
import hashlib
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent


def verify(path):
    bad = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        want, rel = line.split("  ", 1)
        file = ROOT / rel
        got = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else "missing"
        if got != want:
            bad.append(rel)
    if bad:
        raise SystemExit(f"Hash không khớp: {bad[:10]} ({len(bad)} file)")


if __name__ == "__main__":
    verify(BASE / "r0_code_sha256.txt")
    for src in (BASE / "overlay").rglob("*"):
        if src.is_file():
            dst = ROOT / src.relative_to(BASE / "overlay")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    if (BASE / "candidate_code_sha256.txt").exists():
        verify(BASE / "candidate_code_sha256.txt")
    print("Candidate overlay và hash: OK")
