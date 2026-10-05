"""Compare local and server-side hashes of the deployed Python modules.

The full-chain rehearsal caught a real deployment gap: `research_core/factor_lab/
delivery_manifest.py` had the corrected inclusion rule in git and the OLD tier-gated rule on
the server, so the delivery reported 50 factors where 74 had passed. Nothing detected that,
because every rehearsal before it ran the manifest step against the deployed module and got a
plausible number.

A one-off fix would leave the same trap open for every other file, so this compares every
`.py` under `research_core/` and `scripts/` and lists what differs.

    python -X utf8 scripts/dev/recon/compare_deployed.py SERVER_HASH_DUMP.txt
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def local_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for sub in ("research_core", "scripts"):
        for path in sorted((ROOT / sub).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


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
    # The dump lists paths as `research_core/...`; local keys are the same shape.
    local = local_hashes()
    if not server:
        print("no server hashes parsed -- did the dump run?")
        return 2

    only_local = sorted(set(local) - set(server))
    only_server = sorted(set(server) - set(local))
    differing = sorted(name for name in set(local) & set(server) if local[name] != server[name])

    print(f"local files : {len(local)}")
    print(f"server files: {len(server)}")
    print()
    if differing:
        print(f"DIFFERENT CONTENT ({len(differing)}) -- these are NOT deployed:")
        for name in differing:
            print(f"  {name}")
    else:
        print("DIFFERENT CONTENT: none -- every shared file matches byte for byte")
    print()
    if only_local:
        print(f"LOCAL ONLY ({len(only_local)}) -- never uploaded (fine if unused server-side):")
        for name in only_local:
            print(f"  {name}")
    print()
    if only_server:
        print(f"SERVER ONLY ({len(only_server)}) -- written on the server:")
        for name in only_server:
            print(f"  {name}")
    return 1 if differing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
