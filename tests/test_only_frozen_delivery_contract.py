"""TEST-ONLY guards on the frozen 2026-10-07 delivery contract.

`configs/validation_gates.yaml` is frozen: the acceptance checklist makes any
change to `gates`, `portfolio.cost`, `statistics` or `split` an automatic
stop-and-escalate. Until now nothing in CI actually pinned those values, so a
well-meaning edit could have moved the goalposts silently.

These tests are deliberately brittle. If one fails, the question is not "how do
I update the test" but "who authorised changing the frozen contract".
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "validation_gates.yaml"

#: Values frozen by the acceptance checklist and referenced in the delivery docs.
FROZEN_SPLIT = {
    "train_start": "2020-01-02",
    "train_end": "2022-12-31",
    "oos_start": "2023-01-01",
    "oos_end": "2026-08-31",
}

FROZEN_GATE_ORDER = [
    "coverage",
    "rank_ic",
    "oos_seal",
    "style_r2",
    "residual_ic",
    "cost_adjusted_return",
    "dd_vol_ratio",
    "parameter_perturbation",
]

FROZEN_THRESHOLDS = {
    "coverage": {"minimum_daily_ratio": 0.95},
    "rank_ic": {"minimum_abs_mean": 0.01, "minimum_abs_t_stat": 1.65},
    "style_r2": {"maximum_mean": 0.80},
    "residual_ic": {"minimum_retention": 0.50},
    "cost_adjusted_return": {"minimum_annualized": 0.0},
    "dd_vol_ratio": {"maximum": 3.0},
}

FROZEN_COST = {
    "commission_per_side": 0.00015,
    "stamp_tax_sell": 0.001,
    "impact_per_side": 0.00085,
    "round_trip_total": 0.003,
}


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_split_is_the_frozen_split(config: dict) -> None:
    assert config["split"] == FROZEN_SPLIT


def test_gate_order_is_the_frozen_order(config: dict) -> None:
    assert config["gates"]["order"] == FROZEN_GATE_ORDER


def test_gate_thresholds_are_frozen(config: dict) -> None:
    for gate, expected in FROZEN_THRESHOLDS.items():
        assert config["gates"][gate] == expected, gate


def test_cost_model_is_frozen(config: dict) -> None:
    assert config["portfolio"]["cost"] == FROZEN_COST


def test_data_basis_is_frozen(config: dict) -> None:
    """Post-adjusted all-A daily bars: the price basis every result assumes."""
    data = config["data"]
    assert data["provider"] == "rqdata"
    assert data["universe"] == "all_a"
    assert data["adjust_type"] == "post"
    assert data["frequency"] == "1d"


def test_perturbation_multipliers_are_frozen(config: dict) -> None:
    assert config["perturbation"]["multipliers"] == [0.8, 1.2]


def test_forward_horizons_and_primary_are_frozen(config: dict) -> None:
    forward = config["forward_returns"]
    assert forward["horizons"] == [5, 10, 20]
    assert forward["primary_horizon"] == 10


def test_style_fields_are_frozen(config: dict) -> None:
    assert config["styles"]["fields"] == ["size", "momentum", "volatility", "liquidity"]


# ── the additive layer must not be able to weaken anything ──────────────

def test_robustness_layer_does_not_consult_the_gate_config() -> None:
    """`robustness.py` is additive evidence; it must not read the frozen gates.

    If it could read them it could, in principle, be written to bend around them.
    Keeping it config-free makes "stricter only" a structural property rather
    than a promise.

    Checked on the import graph rather than the raw text, so that prose in the
    module docstring is not mistaken for a dependency.
    """
    import ast

    source = (ROOT / "research_core" / "factor_lab" / "robustness.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
            imported.update(alias.name for alias in node.names)

    forbidden = {"yaml", "load_validation_config", "deterministic_validation"}
    assert not (imported & forbidden), (
        f"robustness.py imports {sorted(imported & forbidden)}; the additive layer "
        "must not depend on the frozen gate machinery"
    )


def test_frozen_pipeline_does_not_import_the_additive_layer() -> None:
    """The frozen validator must be unchanged by the new dimensions."""
    source = (
        ROOT / "research_core" / "factor_lab" / "deterministic_validation.py"
    ).read_text(encoding="utf-8")
    assert "robustness" not in source, (
        "the frozen validator now depends on the additive robustness layer; "
        "the additive layer must stay a post-processing step"
    )


def test_bh_correction_can_only_remove_factors_never_add_one() -> None:
    """The structural guarantee that makes the additive layer legitimate."""
    import numpy as np

    from research_core.factor_lab.robustness import benjamini_hochberg

    rng = np.random.default_rng(20261005)
    p_values = np.concatenate([rng.uniform(0.0, 0.05, 40), rng.uniform(0.05, 1.0, 160)])

    uncorrected = {i for i, value in enumerate(p_values) if value < 0.05}
    corrected = {
        i for i, accepted in enumerate(benjamini_hochberg(p_values, q=0.05).accepted) if accepted
    }
    assert corrected <= uncorrected
    assert corrected, "the correction should still admit the genuinely strong factors"
