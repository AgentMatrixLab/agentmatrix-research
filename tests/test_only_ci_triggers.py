"""Guards for the CI wiring itself.

Two properties that are easy to break silently and expensive to notice:

1. ``Factor Validation`` runs the unit-test suite (``pytest research_core/factor_lab/ tests/``),
   so a pull request that only changes ``tests/**`` must still trigger it. It did not until
   ``tests/**`` was added to the workflow's ``pull_request.paths``.
2. ``PR Hygiene`` scans changed files for machine-specific paths, and its own workflow file
   defines those very patterns, so it must keep excluding itself from that scan
   (introduced by PR #42, 2026-07-09).

These are plain text/YAML assertions: no network, no CI API calls.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTOR_VALIDATION = REPO_ROOT / ".github" / "workflows" / "factor-validation.yml"
PR_HYGIENE = REPO_ROOT / ".github" / "workflows" / "pr-hygiene.yml"
HYGIENE_WORKFLOW_PATH = ".github/workflows/pr-hygiene.yml"


def _workflow_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(config, dict), f"{path.name} did not parse into a mapping"
    return config


def _pull_request_paths(config: dict) -> list[str]:
    # PyYAML resolves the YAML 1.1 key ``on`` to the boolean True.
    triggers = config.get("on", config.get(True))
    assert isinstance(triggers, dict), "workflow has no trigger mapping"
    pull_request = triggers.get("pull_request")
    assert isinstance(pull_request, dict), "workflow has no pull_request trigger"
    paths = pull_request.get("paths")
    assert isinstance(paths, list), "pull_request trigger has no paths filter"
    return [str(item) for item in paths]


def test_factor_validation_triggers_on_test_changes() -> None:
    paths = _pull_request_paths(_workflow_config(FACTOR_VALIDATION))
    assert "tests/**" in paths, (
        "Factor Validation runs the test suite but does not trigger on tests/** changes, "
        "so a pull request that only edits tests would skip it entirely"
    )


def test_factor_validation_still_runs_the_test_suite() -> None:
    """The trigger above only matters because the workflow actually runs pytest."""
    text = FACTOR_VALIDATION.read_text(encoding="utf-8")
    assert "pytest" in text, "Factor Validation no longer runs pytest"
    assert "tests/" in text, "Factor Validation no longer includes the tests/ directory in pytest"


def test_pr_hygiene_path_gate_excludes_its_own_workflow() -> None:
    text = PR_HYGIENE.read_text(encoding="utf-8")
    assert "excluded" in text, "PR Hygiene path gate lost its exclusion set"
    assert HYGIENE_WORKFLOW_PATH in text, (
        "PR Hygiene must exclude its own workflow file from the path scan: the file defines "
        "the user-home path patterns themselves, so editing it would otherwise always fail"
    )
