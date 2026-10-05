#!/usr/bin/env python3
"""Tree-filter body: replace credential literals in every revision's tree.

Run by `git filter-branch --tree-filter`, so it operates on whatever the current
revision's checkout is. Exits 0 always so a missing file in an old revision does
not abort the rewrite.
"""
from __future__ import annotations

import pathlib
import sys

REPLACEMENTS = [
    ("<redacted>", "<redacted>"),
    ("<server-ip>", "<server-ip>"),
    ("<server-password>", "<server-password>"),
]

SUFFIXES = {".py", ".sh", ".md", ".txt", ".yaml", ".yml", ".json", ".ps1", ".cfg", ".ini", ".js", ".html"}
SKIP_PARTS = {".git", "node_modules", "__pycache__", "secrets"}

root = pathlib.Path(".")
touched = 0
for path in root.rglob("*"):
    try:
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    original = text
    for needle, replacement in REPLACEMENTS:
        if needle in text:
            text = text.replace(needle, replacement)
    if text != original:
        path.write_text(text, encoding="utf-8")
        touched += 1

if touched:
    sys.stderr.write(f"scrubbed {touched} file(s)\n")
sys.exit(0)
