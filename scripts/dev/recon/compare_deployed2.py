"""Compare deployed files against the COMMITTED content, not the working tree.

The first version of this comparison was misleading: the working tree holds CRLF for many
files (git normalises to LF on checkout), while `upload_repo.py` deploys from `git archive`,
which writes the stored LF. So raw working-tree digests differ on line endings alone and every
such file looks undeployed.

This compares the server's bytes against `git show HEAD:<path>`, which is what a deploy would
actually write. A real difference then means real content.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def committed_hash(path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True
    )
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def working_hash(path: str) -> str | None:
    target = ROOT / path
    if not target.is_file():
        return None
    return hashlib.sha256(target.read_bytes()).hexdigest()


def server_hashes(dump: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for line in dump.read_text(encoding="utf-8").splitlines():
        if line.startswith("###END###"):
            break
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            hashes[parts[1].strip()] = parts[0]
    return hashes


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    server = server_hashes(Path(argv[1]))
    if not server:
        print("no server hashes parsed")
        return 2

    real: list[str] = []
    line_ending_only: list[str] = []
    absent: list[str] = []
    for path, digest in sorted(server.items()):
        committed = committed_hash(path)
        if committed is None:
            absent.append(path)
            continue
        if digest == committed:
            continue
        if working_hash(path) == digest:
            line_ending_only.append(path)
        else:
            real.append(path)

    print(f"server files compared: {len(server)}")
    print()
    if real:
        print(f"REAL DIFFERENCES ({len(real)}) -- server content is not HEAD:")
        for path in real:
            print(f"  {path}")
    else:
        print("REAL DIFFERENCES: none -- the server matches HEAD everywhere")
    print()
    if line_ending_only:
        print(f"LINE-ENDING DIFFERENCES ONLY ({len(line_ending_only)}):")
        for path in line_ending_only:
            print(f"  {path}")
    print()
    if absent:
        print(f"NOT IN HEAD ({len(absent)}):")
        for path in absent:
            print(f"  {path}")
    return 1 if real else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
