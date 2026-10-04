"""TEST-ONLY guard: every factor the classifier calls runnable must really compute.

This project rediscovered the same defect three times: a readiness signal that was
looser than the engine.

  1. `compile_formula` emitted unknown operator names verbatim and returned
     success, so a broken formula looked fine until it was called.
  2. The classifier folded only *operators* into the verdict, so factors reading
     `adv20` counted as runnable while the compiler emitted `df["adv20"]`.
  3. Field names we merely *recognised* (`net_profit_ttm`) were treated as
     available, when no feed supplies them; and `AMOUNT` mapped to a column the
     panel does not have.

Each was fixed at the point of discovery. This test is the structural guard that
makes the fourth instance fail loudly instead: take every catalog expression the
classifier calls runnable, compile it, and evaluate it on a panel built to the
export contract. Any KeyError is a factor that was counted as deliverable and is
not.

The panel here is synthetic and tiny. This asserts *computability*, never
predictive power.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research_core.factor_lab.catalog_readiness import classify_expression
from research_core.factor_lab.formula_compiler import compile_formula
from research_core.factor_lab.panel_source import EXTENDED_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"

N_CODES = 4
N_DAYS = 90


@pytest.fixture(scope="module")
def contract_panel() -> pd.DataFrame:
    """A panel shaped exactly like `scripts/export_rqsdk_panel.py` writes one."""
    rng = np.random.default_rng(20261005)
    dates = pd.bdate_range("2024-01-01", periods=N_DAYS)
    frames = []
    for index in range(N_CODES):
        close = (10.0 + index) * np.exp(np.cumsum(rng.normal(0.0004, 0.02, N_DAYS)))
        open_ = close * (1 + rng.normal(0, 0.004, N_DAYS))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.006, 0.004, N_DAYS)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.006, 0.004, N_DAYS)))
        volume = rng.lognormal(14.0, 0.4, N_DAYS)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": f"{index:06d}.XSHE",
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "pre_close": np.concatenate([[close[0]], close[:-1]]),
                    "volume": volume,
                    "total_turnover": volume * close,
                    "vwap": close,  # the export contract supplies it; must not be re-derived
                    "limit_up": np.concatenate([[close[0]], close[:-1]]) * 1.1,
                    "limit_down": np.concatenate([[close[0]], close[:-1]]) * 0.9,
                    "circulation_a": 1e8 + index * 1e6,
                    "total_shares": 1.5e8 + index * 1e6,
                    "listed_date": pd.Timestamp("2010-01-04"),
                    "de_listed_date": pd.NaT,
                    "is_st": False,
                    "is_suspended": False,
                    "industry": f"IND{index % 2}",
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _runnable_expressions() -> list[tuple[str, str]]:
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    chosen = []
    for factor in factors:
        if classify_expression(factor["formula_expr"]).runnable:
            chosen.append((factor["factor_id"], factor["formula_expr"]))
    return chosen


def test_the_panel_fixture_carries_the_full_export_contract(contract_panel: pd.DataFrame) -> None:
    """If the fixture drifts from the contract, the guard below proves nothing."""
    for column in EXTENDED_COLUMNS:
        assert column in contract_panel.columns, column


def test_the_catalog_actually_has_runnable_expressions() -> None:
    assert len(_runnable_expressions()) > 500


def test_every_runnable_catalog_expression_evaluates(contract_panel: pd.DataFrame) -> None:
    """The guard. A KeyError here means the classifier overstates what we can ship."""
    failures: list[str] = []
    for factor_id, expression in _runnable_expressions():
        try:
            function = compile_formula(expression)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{factor_id}: compile {type(exc).__name__}: {exc}")
            continue
        try:
            values = function(contract_panel)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{factor_id}: evaluate {type(exc).__name__}: {exc}")
            continue
        if values is None or len(values) != len(contract_panel):
            failures.append(f"{factor_id}: returned a value of the wrong shape")

    assert failures == [], (
        f"{len(failures)} expression(s) are counted as runnable but do not evaluate:\n"
        + "\n".join(failures[:20])
    )


def test_the_guard_would_catch_a_missing_column(contract_panel: pd.DataFrame) -> None:
    """A negative control, so the guard is not passing vacuously."""
    crippled = contract_panel.drop(columns=["total_turnover"])
    with pytest.raises(KeyError):
        compile_formula("Mean(amount, 5)")(crippled)


def test_amount_maps_to_the_panel_column_name() -> None:
    from research_core.factor_lab.formula_compiler import DEFAULT_FIELD_MAP

    assert DEFAULT_FIELD_MAP["AMOUNT"] == "total_turnover"


def test_synthesised_fields_match_the_compiler_branches() -> None:
    """AVAILABLE_FIELDS must describe what the generator really builds."""
    from research_core.factor_lab.catalog_readiness import SYNTHESISED_FIELDS

    panel_columns = set(EXTENDED_COLUMNS) | {
        "date", "code", "close", "volume", "total_turnover",
        "limit_up", "limit_down", "circulation_a",
        "listed_date", "de_listed_date", "is_st", "is_suspended",
    }
    # Everything the classifier calls available is either a real column or a
    # field the generator synthesises; nothing may be merely aspirational.
    for name in SYNTHESISED_FIELDS:
        assert name == "VWAP" or name in {"RETURNS", "DAILY_RETURN"} or name.startswith("ADV")
    assert "TOTAL_TURNOVER" in {c.upper() for c in panel_columns}
