"""Guard: tracked files must not bake in a data-host address or an admin token.

Regression guard for the leak cleaned up in the "redact server address" PR: this
public repository used to carry the data-server address in eight tracked files and
an admin API token in ``strategy_panel/engine/config.py``.

The check is intentionally repo-wide (not just changed files), so a hardcoded host or
token is caught even when it lands in a path that the PR Hygiene workflow does not watch.

Nothing here connects to the network; it only reads tracked files.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCANNED_SUFFIXES = {
    ".py",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".js",
    ".html",
    ".css",
    ".txt",
    ".sh",
    ".ps1",
    ".cfg",
    ".ini",
}

# Loopback / documentation hosts are legitimate defaults.
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "example.com", "testserver"}

# ``HOST = "http://1.2.3.4"`` or ``base_url: str = "http://1.2.3.4"``
HOST_DEFAULT = re.compile(
    r"(?:HOST|BASE_URL|API_BASE|host|base_url)\s*[:=]\s*[\"']?http://(\d{1,3}(?:\.\d{1,3}){3})"
)
# Admin tokens of the shape that leaked.
ADMIN_TOKEN = re.compile(r"sk-admin-[A-Za-z0-9_\-]{8,}")
# Absolute user-home paths (built from parts so this file does not match itself).
USER_HOME_PATH = re.compile("/" + r"(?:home|Users)" + r"/[A-Za-z0-9_.\-]+")

# The PR Hygiene workflow defines these very patterns, so it is expected to contain them.
PATTERN_DEFINITION_FILES = {".github/workflows/pr-hygiene.yml"}
# This guard only holds pattern definitions, which would otherwise match itself.
SELF_PATH = "tests/test_only_no_baked_in_hosts.py"

# Deployment-coupled files. Their entire purpose is to run against one specific
# server, so they necessarily name that server's paths; `USER_HOME_PATH` matches
# /home/<anything>, which is a filesystem path rather than the host address this
# guard exists to prevent. Listed one by one rather than as a directory glob, so a
# genuinely new hardcoded address elsewhere still fails.
DEPLOYMENT_COUPLED_FILES = {
    "scripts/prepare_server_panel.py",
    "scripts/dev/ssh_run.py",
    "scripts/dev/upload_repo.py",
    "scripts/dev/test_server_access.py",
    "scripts/dev/run_sharded.sh",
    "scripts/dev/run_pool.sh",
    "scripts/dev/run_one_shard.sh",
    "scripts/dev/run_downstream.sh",
    "scripts/dev/stop_and_deliver.sh",
    "scripts/dev/pool_watchdog.sh",
    "scripts/dev/resume_after_reboot.sh",
    "scripts/dev/verify_loader_memory.sh",
    "scripts/dev/retain_passing_values.py",
    "scripts/dev/mirror_runtime_data.py",
    "scripts/build_batch_candidates.py",
    "docs/delivery/2026-10-05-server-recon.md",
    "docs/delivery/2026-10-07-execution-findings.md",
}
DEPLOYMENT_COUPLED_PREFIXES = ("scripts/dev/recon/",)


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / item for item in result.stdout.splitlines() if item.strip()]


def test_no_baked_in_host_address_or_admin_token() -> None:
    problems: list[str] = []
    for path in _tracked_files():
        if path.suffix.lower() not in SCANNED_SUFFIXES or not path.exists():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative == SELF_PATH or relative in PATTERN_DEFINITION_FILES:
            continue
        deployment_coupled = relative in DEPLOYMENT_COUPLED_FILES or relative.startswith(
            DEPLOYMENT_COUPLED_PREFIXES
        )
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            match = HOST_DEFAULT.search(line)
            if match and match.group(1) not in ALLOWED_HOSTS:
                problems.append(f"{relative}:{number} hardcoded host default: {match.group(1)}")
            if ADMIN_TOKEN.search(line):
                problems.append(f"{relative}:{number} admin token literal")
            # The home-path rule is waived for deployment-coupled files only; the
            # host and token rules still apply to them.
            if (
                not deployment_coupled
                and USER_HOME_PATH.search(line)
                and "http://" not in line
                and "https://" not in line
            ):
                problems.append(f"{relative}:{number} absolute user-home path")

    assert not problems, "hardcoded host/token/home-path found:\n" + "\n".join(problems)


def test_guard_scans_a_non_trivial_number_of_files() -> None:
    """Keeps the guard honest: if it silently scans nothing, that is a bug."""
    scanned = [
        path
        for path in _tracked_files()
        if path.suffix.lower() in SCANNED_SUFFIXES and path.exists()
    ]
    assert len(scanned) > 50
