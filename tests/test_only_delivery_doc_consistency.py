"""TEST-ONLY guard against delivery-documentation drift.

The earlier repo audit found the same class of problem three times: two
repositories quoting different candidate counts (89 vs 91), a doc still saying a
question was undecided after it had been settled, and a portal advertising a
catalog size as if it were the delivery count. Every one was a document that had
quietly stopped matching reality, and every one was noticed by a human reading
two things side by side.

These tests do that reading mechanically. They assert that the headline figures in
the client-facing documents equal the numbers the tooling actually computes, so a
stale number fails CI instead of being found in a meeting.

Deliberately narrow: only figures that a reader would act on, and that have a
single authoritative source. Prose is not checked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "pages" / "factor-panel" / "data" / "panel.json"
DOCS = ROOT / "docs" / "delivery"


@pytest.fixture(scope="module")
def panel() -> dict:
    return json.loads(PANEL.read_text(encoding="utf-8"))


def _read(name: str) -> str:
    path = DOCS / name
    assert path.is_file(), f"missing delivery document: {name}"
    return path.read_text(encoding="utf-8")


def test_the_console_dataset_covers_the_whole_catalog(panel: dict) -> None:
    """Every factor must carry a verdict, or the counts below mean nothing."""
    assert panel["catalog"]["total"] == len(panel["factors"])
    counts = panel["catalog"]["readiness"]["counts"]
    assert sum(counts.values()) == panel["catalog"]["total"]


def test_the_runnable_figure_the_panel_shows_has_one_definition(panel: dict) -> None:
    """`runnable` must be the two verdicts that mean the engine can evaluate it."""
    summary = panel["catalog"]["readiness"]
    counts = summary["counts"]
    assert summary["runnable"] == counts["runnable_now"] + counts["alias_only"]
    assert "needs_fields" in counts, (
        "needs_fields is the verdict that keeps `runnable` honest; if it is gone, "
        "factors blocked on missing fields are being counted as deliverable again"
    )


def test_the_committed_console_dataset_matches_a_fresh_build(panel: dict) -> None:
    """The committed panel.json must not be a stale snapshot.

    There is a real trap here. The builder's own tests compare a fresh payload
    against itself, so they pass whether or not the committed file was ever
    regenerated. After the classifier was made honest the committed panel still
    advertised 971 runnable instead of 961, and only a check that reads the file
    on disk can see that.
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from build_factor_panel import build_payload

    fresh = build_payload()
    committed = panel["catalog"]["readiness"]
    assert committed["counts"] == fresh["catalog"]["readiness"]["counts"], (
        "pages/factor-panel/data/panel.json is stale; re-run scripts/build_factor_panel.py"
    )
    assert committed["runnable"] == fresh["catalog"]["readiness"]["runnable"]
    assert panel["catalog"]["total"] == fresh["catalog"]["total"]


def test_the_runbook_quotes_the_current_engine_coverage(panel: dict) -> None:
    """The number a reader plans against must match the one we computed."""
    total = panel["catalog"]["total"]
    runnable = panel["catalog"]["readiness"]["runnable"]
    percent = f"{runnable / total:.1%}"

    runbook = _read("2026-10-07-execution-runbook.md")
    assert f"{runnable} / {total}" in runbook, (
        f"runbook must quote the engine coverage as {runnable} / {total}"
    )
    assert percent in runbook, f"runbook must quote the coverage percentage as {percent}"


def test_the_runbook_quotes_the_delivery_target() -> None:
    runbook = _read("2026-10-07-execution-runbook.md")
    assert "300" in runbook


def test_no_document_still_claims_the_engine_gap_is_open(panel: dict) -> None:
    """The plan once listed engine coverage as an open gap at 77.1%.

    Leaving that line in place would make a reader think work remains that is
    finished, and worse, it understates what the batch will actually cover.
    """
    plan = _read("2026-10-07-system-plan.md")
    stale = "目录 1058 中只有 **816（77.1%）** 能被本仓库引擎算出来"
    assert stale not in plan, "the plan still describes the closed engine gap as open"


def test_the_frozen_contract_doc_matches_the_config() -> None:
    """The methodology doc quotes the frozen split; it must match the YAML."""
    import yaml

    config = yaml.safe_load(
        (ROOT / "configs" / "validation_gates.yaml").read_text(encoding="utf-8")
    )
    split = config["split"]
    methodology = _read("methodology.md")
    assert split["train_start"] in methodology
    assert split["train_end"] in methodology
    assert split["oos_start"] in methodology
    assert split["oos_end"] in methodology


def test_the_scoring_card_weights_match_the_implementation() -> None:
    """The card is quoted to the client; the module is what actually runs."""
    from research_core.factor_lab.scoring import SCORE_CARD, TOTAL_WEIGHT

    assert TOTAL_WEIGHT == 100
    card = _read("2026-10-07-scoring-card.md")
    for dimension in SCORE_CARD:
        assert str(dimension.weight) in card, (
            f"scoring card does not mention the {dimension.name} weight ({dimension.weight})"
        )


def test_the_documented_tier_cut_lines_match_the_code() -> None:
    from research_core.factor_lab.scoring import TIER_THRESHOLDS

    card = _read("2026-10-07-scoring-card.md")
    for tier, value in TIER_THRESHOLDS.items():
        assert f"{value:.0f}" in card, f"scoring card omits the {tier} cut line ({value})"


def test_the_synthetic_guard_declaration_is_present(panel: dict) -> None:
    """The console must state that it is not showing simulated data."""
    assert panel["honesty"]["simulated_data"] is False


def test_documents_do_not_promise_returns() -> None:
    """Compliance: no forward-looking performance language in the delivery docs.

    The acceptance checklist forbids guaranteeing future returns, Sharpe or
    drawdown. A sentence-level check is crude but catches the obvious slips.
    """
    offenders: list[str] = []
    banned = ("保证收益", "承诺收益", "预期年化收益", "必赚", "稳赚")
    for path in sorted(DOCS.glob("2026-10-07-*.md")):
        text = path.read_text(encoding="utf-8")
        for phrase in banned:
            if phrase in text:
                offenders.append(f"{path.name}: {phrase}")
    assert offenders == [], f"delivery docs contain performance promises: {offenders}"
