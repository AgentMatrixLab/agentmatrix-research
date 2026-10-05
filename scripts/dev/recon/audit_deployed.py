"""Audit whether the server is running the committed code, for EVERY file.

A deployment gap cost real time this session: the delivery's inclusion rule was correct in git
and stale on the server, and only running the whole chain exposed it (the delivery reported 50
where 74 had passed). Fixing that one file leaves the question open for the other 240.

The server hashes `tr -d '\\r' < file`, which strips carriage returns, and this hashes
`git show HEAD:path`. A byte comparison without that step is misleading -- git normalises to LF
on checkout while the working tree holds CRLF, so every such file looks undeployed -- so the
comparison is on normalised content, where a difference means a difference.

    python -X utf8 scripts/dev/recon/audit_deployed.py NORM_HASH_DUMP.txt
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

#: Files the delivery chain runs. A semantic difference in one of these is a delivery risk;
#: a difference in a dev/recon script is not.
CHAIN_CRITICAL = (
    "research_core/factor_lab/delivery_manifest.py",
    "research_core/factor_lab/supplementary.py",
    "research_core/factor_lab/scoring.py",
    "research_core/factor_lab/robustness.py",
    "research_core/factor_lab/validation_result.py",
    "research_core/factor_lab/catalog_readiness.py",
    "research_core/factor_lab/streaming_supplement.py",
    "research_core/factor_lab/factor_value_stream.py",
    "research_core/factor_lab/merge_batches.py",
    "research_core/strategy_operations/signal_pipeline.py",
    "research_core/strategy_operations/strategy_backtest.py",
    "scripts/build_delivery_manifest.py",
    "scripts/build_strategy_demos.py",
    "scripts/build_live_signals.py",
    "scripts/build_delivery_readme.py",
    "scripts/build_batch_candidates.py",
    "scripts/build_factor_values.py",
    "scripts/consolidate_factor_values.py",
    "scripts/merge_batch_manifests.py",
    "scripts/package_delivery.py",
    "scripts/cross_check_delivery.py",
    "scripts/run_robustness_supplement.py",
    "scripts/reconcile_signals.py",
)


def committed_normalised(path: str) -> str | None:
    result = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True)
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout.replace(b"\r", b"")).hexdigest()


def parse(dump: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in dump.read_text(encoding="utf-8").splitlines():
        if line.startswith("###END###"):
            break
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            out[parts[1].strip()] = parts[0]
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    server = parse(Path(argv[1]))
    if not server:
        print("no hashes parsed")
        return 2

    differing: list[str] = []
    for path, digest in sorted(server.items()):
        committed = committed_normalised(path)
        if committed is not None and committed != digest:
            differing.append(path)

    critical = [p for p in differing if p in CHAIN_CRITICAL]
    harmless = [p for p in differing if p not in CHAIN_CRITICAL]

    print(f"deployed .py files audited : {len(server)}")
    print(f"content differences        : {len(differing)}")
    print()
    if critical:
        print(f"CHAIN-CRITICAL DIFFERENCES ({len(critical)}) -- these affect the delivery:")
        for path in critical:
            print(f"  {path}")
    else:
        print("CHAIN-CRITICAL DIFFERENCES: none -- every module the chain runs matches HEAD")
    print()
    if harmless:
        print(f"OTHER DIFFERENCES ({len(harmless)}) -- not used by the delivery chain:")
        for path in harmless:
            print(f"  {path}")

    missing = [p for p in CHAIN_CRITICAL if p not in server]
    if missing:
        print()
        print(f"CHAIN FILES MISSING ON SERVER ({len(missing)}):")
        for path in missing:
            print(f"  {path}")

    return 1 if critical or missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
