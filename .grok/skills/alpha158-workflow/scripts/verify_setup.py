#!/usr/bin/env python3
"""Pre-flight checks for Alpha158 workflow. Run from agentmatrix-research repo root."""

from __future__ import annotations

import socket
import sys
from pathlib import Path


def _repo_root() -> Path:
    # scripts/verify_setup.py -> .grok/skills/alpha158-workflow/scripts -> repo root
    return Path(__file__).resolve().parents[4]


def check_port(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True, f"{host}:{port} reachable"
    except OSError as exc:
        return False, f"{host}:{port} not reachable ({exc})"


def check_imports() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    for name in ("pandas", "pyarrow", "numpy", "qlib", "clickhouse_driver", "matplotlib"):
        try:
            __import__(name)
            results.append((name, True, "ok"))
        except ImportError as exc:
            results.append((name, False, str(exc)))
    return results


def check_qlib_data(repo: Path) -> tuple[bool, str]:
    cn_data = repo / "data" / "qlib" / "cn_data"
    instruments = cn_data / "instruments" / "all.txt"
    if not cn_data.is_dir():
        return False, f"missing {cn_data}"
    if not instruments.is_file():
        return False, f"missing {instruments}"
    return True, str(cn_data)


def check_clickhouse() -> tuple[bool, str]:
    try:
        import os

        from clickhouse_driver import Client
        from dotenv import load_dotenv

        load_dotenv(_repo_root() / ".env")

        client = Client(
            host=os.getenv("SMARTDATA_CH_HOST", "127.0.0.1"),
            port=int(os.getenv("SMARTDATA_CH_PORT", "19000")),
            user=os.getenv("SMARTDATA_CH_USER", "smartdata_ro"),
            password=os.getenv("SMARTDATA_CH_PASSWORD", ""),
            database=os.getenv("SMARTDATA_CH_DATABASE", "amazingdata"),
            connect_timeout=5,
            send_receive_timeout=10,
        )
        version = client.execute("SELECT version()")[0][0]
        return True, f"ClickHouse {version}"
    except Exception as exc:
        return False, str(exc)


def check_alpha158_module(repo: Path) -> tuple[bool, str]:
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    try:
        from research_core.alpha158_lab.config import Alpha158ResearchConfig

        cfg = Alpha158ResearchConfig()
        return True, f"output_dir={cfg.output_dir}"
    except Exception as exc:
        return False, str(exc)


def check_skill_bundled(repo: Path) -> tuple[bool, str]:
    skill = repo / ".grok" / "skills" / "alpha158-workflow" / "SKILL.md"
    if skill.is_file():
        return True, str(skill)
    return False, "missing — git pull or clone agentmatrix-research with .grok/skills/"


def main() -> int:
    repo = _repo_root()
    print(f"Repo root: {repo}")
    print("=" * 60)

    checks: list[tuple[str, bool, str]] = []

    ok, msg = check_skill_bundled(repo)
    checks.append(("alpha158-workflow skill (repo)", ok, msg))

    ok, msg = check_port("127.0.0.1", 19000)
    checks.append(("SSH tunnel (19000)", ok, msg))

    ok, msg = check_clickhouse()
    checks.append(("SmartData ClickHouse", ok, msg))

    ok, msg = check_qlib_data(repo)
    checks.append(("qlib cn_data", ok, msg))

    for name, ok, msg in check_imports():
        checks.append((f"import {name}", ok, msg))

    ok, msg = check_alpha158_module(repo)
    checks.append(("alpha158_lab module", ok, msg))

    workspace = repo / "runtime" / "alpha158_lab"
    checks.append(
        (
            "workspace dir",
            workspace.is_dir(),
            str(workspace) if workspace.is_dir() else f"missing — run: python -m research_core.alpha158_lab init-workspace",
        )
    )

    failed = 0
    for label, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{status}] {label}: {detail}")

    print("=" * 60)
    if failed:
        print(f"{failed} check(s) failed. Fix before running batches.")
        return 1
    print("All checks passed. Ready to run Alpha158 pipeline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())