"""Diff the deployed library files against HEAD, reading UTF-8 explicitly.

PowerShell's `Get-Content` defaults to the ANSI code page, so reading a UTF-8 file produced
mojibake and made every non-ASCII line look changed. The byte-level sha256 comparison already
established that these files DO differ; this asks what the difference is, without an encoding
layer in the way.
"""

from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "snapshot_dir" / "research_core"

FILES = [
    "factor_lab/catalog_readiness.py",
    "factor_lab/delivery_manifest.py",
    "factor_lab/robustness.py",
    "factor_lab/scoring.py",
    "factor_lab/supplementary.py",
    "factor_lab/validation_result.py",
    "strategy_operations/signal_pipeline.py",
    "strategy_operations/strategy_backtest.py",
]


def head_text(path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:research_core/{path}"], cwd=ROOT, capture_output=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def summarise(name: str, head: str, server: str) -> None:
    head_lines = head.splitlines()
    server_lines = server.splitlines()
    diff = list(difflib.unified_diff(head_lines, server_lines, lineterm="", n=1))
    changes = [line for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    # Classify: a change confined to non-ASCII characters is a message/text difference, not logic.
    substantive = []
    for line in changes:
        stripped = line[1:]
        if stripped.isascii() and any(ch.isalnum() for ch in stripped):
            substantive.append(line)
    print(f"=== research_core/{name}")
    print(f"    HEAD {len(head_lines)} lines, server {len(server_lines)} lines, "
          f"{len(changes)} changed lines")
    if substantive:
        print(f"    SUBSTANTIVE (ASCII logic/plumbing) changes: {len(substantive)}")
        for line in substantive[:14]:
            print(f"      {line[:160]}")
    else:
        print("    SUBSTANTIVE changes: none -- only non-ASCII text differs")
        for line in changes[:6]:
            print(f"      (text) {line[:120]}")


def main() -> int:
    for name in FILES:
        server_path = SNAPSHOT / name
        if not server_path.is_file():
            print(f"=== research_core/{name}: snapshot missing")
            continue
        head = head_text(name)
        if head is None:
            print(f"=== research_core/{name}: not in HEAD")
            continue
        server = server_path.read_text(encoding="utf-8", errors="replace")
        summarise(name, head, server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
