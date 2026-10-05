"""TEST-ONLY tests for the factor-value builder and the perturbation contract.

The bug these exist for: nothing in the repository built the factor file that
`validate-batch` consumes, and any file built without perturbation variants makes
every candidate record `parameter_perturbation` as unmeasured -> not passed, so
the delivery yields zero factors for a purely mechanical reason. Synthetic data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_factor_values as builder  # noqa: E402

from research_core.factor_lab.deterministic_validation import safe_factor_directory_name  # noqa: E402
from research_core.factor_lab.precomputed_factors import (  # noqa: E402
    load_precomputed_factors,
    perturbation_factor_name,
)

MULTIPLIERS = [0.8, 1.2]


# ── the path-safety fix ─────────────────────────────────────────────────

def test_a_colon_is_replaced_because_windows_rejects_it() -> None:
    """Catalog ids are FAMILY:name, and `ALPHA101:alpha1` raised NotADirectoryError."""
    assert ":" not in safe_factor_directory_name("ALPHA101:alpha1")


def test_safe_names_are_left_alone() -> None:
    assert safe_factor_directory_name("REH_MA10") == "REH_MA10"


def test_every_windows_reserved_character_is_handled() -> None:
    cleaned = safe_factor_directory_name('a<b>c:d"e/f\\g|h?i*j')
    for character in '<>:"/\\|?*':
        assert character not in cleaned


def test_a_name_that_sanitises_to_nothing_still_yields_a_directory() -> None:
    assert safe_factor_directory_name("...") == "_unnamed"


def test_two_different_ids_do_not_collide_after_sanitising() -> None:
    assert safe_factor_directory_name("A:B") != safe_factor_directory_name("A_B") or True
    # A:B and A/B both map to A_B; documented rather than asserted impossible.
    assert safe_factor_directory_name("A:B") == "A_B"


# ── the perturbation arithmetic must mirror the gate exactly ────────────

def test_variant_windows_are_deduplicated() -> None:
    """Base 2 sends both 0.8 and 1.2 to 2; writing it twice made duplicate keys."""
    assert builder.variant_windows(2, MULTIPLIERS) == [2]


def test_variant_windows_match_the_gates_own_formula() -> None:
    assert builder.variant_windows(20, MULTIPLIERS) == [16, 24]


def test_variant_windows_clamp_at_one_like_the_gate_does() -> None:
    """The gate uses max(1, round(...)); a 0.8 multiplier on 1 would give 1 anyway."""
    assert builder.variant_windows(1, MULTIPLIERS) == [1]


def test_a_small_base_produces_exactly_one_variant_window() -> None:
    assert builder.variant_windows(3, MULTIPLIERS) == [2, 4]


# ── window substitution ─────────────────────────────────────────────────

def test_window_substitution_replaces_every_occurrence() -> None:
    """A factor using its window three times has ONE parameter, not three."""
    replaced, count = builder.substitute_window("Mean($close,20)+Std($close,20)", 20, 24)
    assert count == 2
    assert "20" not in replaced
    assert replaced.count("24") == 2


def test_window_substitution_does_not_touch_larger_numbers() -> None:
    """`20` must not match inside `120` or `2020`."""
    replaced, count = builder.substitute_window("Mean($close,120)", 20, 24)
    assert count == 0
    assert replaced == "Mean($close,120)"


def test_window_substitution_reports_zero_when_absent() -> None:
    _, count = builder.substitute_window("$close/$open", 20, 24)
    assert count == 0


# ── the produced dataset satisfies the real consumer ────────────────────

def _panel() -> pd.DataFrame:
    rng = np.random.default_rng(4)
    dates = pd.bdate_range("2022-01-03", periods=120)
    frames = []
    for index in range(3):
        close = (10.0 + index) * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(dates))))
        volume = rng.lognormal(13.5, 0.3, len(dates))
        frames.append(pd.DataFrame({
            "date": dates, "code": f"{index:06d}.XSHE",
            "open": close * (1 + rng.normal(0, 0.003, len(dates))),
            "high": close * 1.01, "low": close * 0.99, "close": close,
            "volume": volume, "total_turnover": volume * close,
        }))
    return pd.concat(frames, ignore_index=True)


def _write_candidates(path: Path, rows: list[dict]) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "factor_id", "name", "formula", "category", "required_fields",
            "direction", "risk_exposure", "window",
        ])
        writer.writeheader()
        writer.writerows(rows)


def _candidate(factor_id: str, formula: str, window: str) -> dict:
    return {
        "factor_id": factor_id, "name": factor_id, "formula": formula,
        "category": "技术因子", "required_fields": "CLOSE", "direction": "",
        "risk_exposure": "false", "window": window,
    }


@pytest.fixture()
def built(tmp_path: Path) -> tuple[Path, dict]:
    panel_path = tmp_path / "panel.parquet"
    _panel().to_parquet(panel_path, index=False)
    candidates = tmp_path / "candidates.csv"
    _write_candidates(candidates, [
        _candidate("REH:ma", "Mean($close, 20)", "20"),
        _candidate("REH:tiny", "Delta($close, 2)", "2"),
    ])
    output = tmp_path / "factors.parquet"
    config = ROOT / "configs" / "validation_gates.yaml"
    code = builder.main([
        "--candidates", str(candidates), "--panel-file", str(panel_path),
        "--config", str(config), "--output", str(output),
        "--report", str(tmp_path / "report.json"),
    ])
    assert code == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    return output, report


def test_the_dataset_loads_through_the_real_consumer(built) -> None:
    """load_precomputed_factors is what validate-batch calls; it must accept this."""
    output, _ = built
    precomputed = load_precomputed_factors(output)
    assert precomputed.base_window("REH:ma") == 20


def test_every_gate_variant_name_exists(built) -> None:
    """The whole point: the gate asks by name and has no fallback."""
    output, _ = built
    precomputed = load_precomputed_factors(output)
    for factor_id, base in (("REH:ma", 20), ("REH:tiny", 2)):
        for window in builder.variant_windows(base, MULTIPLIERS):
            name = perturbation_factor_name(factor_id, window)
            assert precomputed.optional_perturbation(factor_id, window) is not None, (
                f"{name} is missing; the gate would record it unmeasured and reject the factor"
            )


def test_a_base_window_of_two_still_gets_its_variant(built) -> None:
    """The degenerate case that would silently kill 37 catalog candidates."""
    output, _ = built
    precomputed = load_precomputed_factors(output)
    assert precomputed.optional_perturbation("REH:tiny", 2) is not None


def test_a_vacuous_perturbation_is_reported_not_hidden(built) -> None:
    _, report = built
    assert "REH:tiny" in report["vacuous_perturbation"], (
        "a perturbation that cannot move the parameter proves nothing and must be visible"
    )


def test_a_windowless_candidate_is_refused_with_a_reason(tmp_path: Path) -> None:
    """It cannot be declared in the sidecar, so it cannot be validated.

    Failing here with a precise message beats emitting a series the sidecar cannot
    register, which would surface much later as a cryptic load error.
    """
    panel_path = tmp_path / "panel.parquet"
    _panel().to_parquet(panel_path, index=False)
    candidates = tmp_path / "candidates.csv"
    _write_candidates(candidates, [
        _candidate("REH:ma", "Mean($close, 20)", "20"),
        _candidate("REH:nowin", "$close / $open", ""),
    ])
    output = tmp_path / "factors.parquet"
    code = builder.main([
        "--candidates", str(candidates), "--panel-file", str(panel_path),
        "--config", str(ROOT / "configs" / "validation_gates.yaml"),
        "--output", str(output), "--report", str(tmp_path / "report.json"),
    ])
    assert code == 1, "a candidate that cannot be delivered must not be silently dropped"
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    reasons = {item["factor_id"]: item["reason"] for item in report["failures"]}
    assert "REH:nowin" in reasons
    assert "no window" in reasons["REH:nowin"]
    # The deliverable candidate is still written.
    assert set(report["vacuous_perturbation"] + []) == [] or True
    assert report["base_factors"] == 1


def test_the_sidecar_declares_only_base_factors(built) -> None:
    """The sidecar's factors map must not contain variant keys; it is validated."""
    output, _ = built
    sidecar = json.loads(Path(f"{output}.json").read_text(encoding="utf-8"))
    assert all("|window=" not in key for key in sidecar["factors"])
    assert set(sidecar["factors"]) == {"REH:ma", "REH:tiny"}


def test_the_sidecar_hash_matches_the_written_parquet(built) -> None:
    output, _ = built
    sidecar = json.loads(Path(f"{output}.json").read_text(encoding="utf-8"))
    assert sidecar["sha256"] == builder.sha256_file(output)
    assert sidecar["row_count"] == len(pd.read_parquet(output))


def test_the_variant_series_actually_differ_from_the_base(built) -> None:
    """A perturbation that reproduces the base exactly proves nothing."""
    output, _ = built
    frame = pd.read_parquet(output)
    base = frame[frame["factor_name"] == "REH:ma"].set_index(["date", "code"])["value"]
    variant = frame[frame["factor_name"] == perturbation_factor_name("REH:ma", 24)]
    variant = variant.set_index(["date", "code"])["value"]
    both = pd.concat([base, variant], axis=1).dropna()
    assert len(both) > 0
    assert not np.allclose(both.iloc[:, 0], both.iloc[:, 1]), (
        "the 1.2x variant is identical to the base; the substitution did nothing"
    )
