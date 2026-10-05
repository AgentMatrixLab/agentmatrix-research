"""TEST-ONLY guard: no live credential may be committed.

Written after I committed the ClickHouse password into every reconnaissance
script. The existing `test_only_no_baked_in_hosts.py` guards against a leaked host
address and an admin token, and it did catch the recon scripts -- but only for the
absolute home paths they contained, not for the password sitting on the same line.
A guard that looks for one shape of secret does not protect against another.

This one scans tracked files for the credentials actually in play on this project,
plus generic shapes: private keys, cloud access keys, and long high-entropy
assignments to a password-ish variable name.

It reads files only. It never connects anywhere.

NOTE FOR WHOEVER ROTATES THESE: the literals below are deliberately redacted to
their first few characters. The scan matches on longer fragments loaded from the
gitignored secrets file when it is present, and falls back to structural patterns
otherwise, so this test itself can live in the repository.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SECRETS_FILE = REPO_ROOT / "secrets" / "server-access.txt"

SCANNED_SUFFIXES = {
    ".py", ".md", ".yml", ".yaml", ".json", ".js", ".html", ".css",
    ".txt", ".sh", ".ps1", ".cfg", ".ini", ".toml", ".env",
}

# Files that legitimately contain the scan patterns because they define them.
SELF_PATH = "tests/test_only_no_secrets.py"

# Static-dashboard access gates. These are publishable by construction: the
# dashboards are served from GitHub Pages, so the "password" is readable by anyone
# who views source. The files say so themselves ("a convenience login screen, not a
# substitute for Supabase RLS or backend authentication"). Listed explicitly rather
# than silently, so the decision is visible and reviewable -- if a real secret is
# ever added to one of these files, widening this list is the wrong fix.
PUBLISHABLE_CLIENT_GATES = {
    "frontend/factor-lab-dashboard/config.js",
    "pages/factor-lab-dashboard/config.js",
    "pages/lifecycle-dashboard/index.html",
}

GENERIC_PATTERNS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "OpenAI-style secret key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "GitHub personal access token"),
    (re.compile(r"\bsk-admin-[A-Za-z0-9_\-]{8,}"), "admin token literal"),
)

# `password = "…"` with a long literal is almost always a real credential rather
# than a placeholder.
LONG_PASSWORD_LITERAL = re.compile(
    r"""(?:password|passwd|pwd|secret|token)\s*[:=]\s*["']([^"'\s]{12,})["']""",
    re.IGNORECASE,
)
# Placeholders are fine.
PLACEHOLDER = re.compile(
    r"^(?:\$\{?[A-Za-z_]|<|xxx|your|changeme|placeholder|test|dummy|fake|example|\*{3,})",
    re.IGNORECASE,
)


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / item for item in result.stdout.splitlines() if item.strip()]


def _known_credentials() -> list[str]:
    """Load real secret values from the gitignored file, if this machine has it.

    Only used to make the scan concrete where possible; the structural patterns
    above still run on every machine, including CI, where the file is absent.
    """
    if not SECRETS_FILE.is_file():
        return []
    found: list[str] = []
    for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        value = value.strip()
        if key.strip().lower() in {"password", "passphrase"} and len(value) >= 8:
            found.append(value)
    return found


def test_no_credential_is_committed() -> None:
    known = _known_credentials()
    problems: list[str] = []

    for path in _tracked_files():
        if path.suffix.lower() not in SCANNED_SUFFIXES or not path.exists():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative == SELF_PATH:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        ):
            for pattern, label in GENERIC_PATTERNS:
                if pattern.search(line):
                    problems.append(f"{relative}:{number} {label}")
            match = LONG_PASSWORD_LITERAL.search(line)
            if (
                match
                and not PLACEHOLDER.match(match.group(1))
                and relative not in PUBLISHABLE_CLIENT_GATES
            ):
                problems.append(f"{relative}:{number} hardcoded password literal")
            for secret in known:
                if secret and secret in line:
                    problems.append(f"{relative}:{number} live credential from secrets/server-access.txt")

    assert not problems, "credential material found in tracked files:\n" + "\n".join(problems)


def test_the_secrets_directory_is_gitignored() -> None:
    """A credential file must never be stageable by `git add -A`."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "secrets/server-access.txt"],
        cwd=REPO_ROOT, capture_output=True,
    )
    assert result.returncode == 0, "secrets/ is not gitignored"


def test_the_guard_scans_a_non_trivial_number_of_files() -> None:
    """If it scans nothing it proves nothing."""
    scanned = [
        path for path in _tracked_files()
        if path.suffix.lower() in SCANNED_SUFFIXES and path.exists()
    ]
    assert len(scanned) > 50
