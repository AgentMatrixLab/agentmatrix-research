"""TEST-ONLY tests for the server-side RQData export script.

The RQData calls themselves need the licensed environment and are exercised by
``--probe`` on the server. Everything here is the pure assembly and contract
layer, which is where a silent mistake would poison every downstream factor.
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

import export_rqsdk_panel as export  # noqa: E402

DATES = pd.bdate_range("2023-01-02", periods=6)
CODES = ["000001.XSHE", "600000.XSHG"]


def price_frame() -> pd.DataFrame:
    """A coherent post-adjusted panel, including one limit-up and one limit-down bar.

    Real all-A history always contains limit events; a fixture with none would
    trip the mixed-basis guard for the wrong reason.
    """
    rows = []
    last = len(DATES) - 1
    for index, code in enumerate(CODES):
        for offset, stamp in enumerate(DATES):
            close = 10.0 + index + offset * 0.1
            limit_up = close * 1.1
            limit_down = close * 0.9
            if offset == last and index == 0:
                close = limit_up  # closed limit-up
            elif offset == last and index == 1:
                close = limit_down  # closed limit-down
            rows.append(
                {
                    "date": stamp,
                    "code": code,
                    "open": close - 0.05,
                    "high": close * 1.02,
                    "low": close * 0.98,
                    "close": close,
                    "volume": 1_000_000.0 + offset,
                    "total_turnover": (1_000_000.0 + offset) * close,
                    "limit_up": limit_up,
                    "limit_down": limit_down,
                    "prev_close": close - 0.1,
                }
            )
    return pd.DataFrame(rows)


def flags_frame() -> pd.DataFrame:
    rows = []
    for code in CODES:
        for stamp in DATES:
            rows.append({"date": stamp, "code": code, "is_st": False, "is_suspended": False})
    return pd.DataFrame(rows)


def shares_frame() -> pd.DataFrame:
    rows = []
    for code in CODES:
        for stamp in DATES:
            rows.append({"date": stamp, "code": code, "circulation_a": 1e8, "total_shares": 1.5e8})
    return pd.DataFrame(rows)


def metadata_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_book_id": CODES,
            "trading_code": ["000001", "600000"],
            "listed_date": pd.to_datetime(["2000-01-04", "2000-01-04"]),
            "de_listed_date": pd.to_datetime([None, None]),
        }
    )


def industry_frame() -> pd.DataFrame:
    return pd.DataFrame({"code": CODES, "industry": ["bank", "industrial"]})


# ── helpers ─────────────────────────────────────────────────────────────

def test_normalize_index_frame_flattens_the_multiindex() -> None:
    frame = pd.DataFrame(
        {"close": [1.0, 2.0]},
        index=pd.MultiIndex.from_tuples(
            [(pd.Timestamp("2023-01-03"), "000001.XSHE"), (pd.Timestamp("2023-01-04"), "600000.XSHG")],
            names=["date", "order_book_id"],
        ),
    )
    result = export.normalize_index_frame(frame)
    assert list(result.columns) == ["date", "code", "close"]
    assert result["code"].tolist() == ["000001.XSHE", "600000.XSHG"]


def test_wide_boolean_to_long_melts_dates_by_codes() -> None:
    wide = pd.DataFrame(
        [[True, False], [False, True]],
        index=pd.DatetimeIndex(DATES[:2], name="date"),
        columns=CODES,
    )
    result = export.wide_boolean_to_long(wide, "is_st")
    assert set(result.columns) == {"date", "code", "is_st"}
    assert len(result) == 4
    assert result["is_st"].dtype == bool


# ── assembly ────────────────────────────────────────────────────────────

def test_assemble_panel_produces_every_required_column() -> None:
    panel, _ = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    missing = [c for c in export.REQUIRED_PANEL_COLUMNS if c not in panel.columns]
    assert missing == []
    assert len(panel) == len(DATES) * len(CODES)


def test_assemble_panel_renames_prev_close_to_pre_close() -> None:
    panel, _ = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    assert "pre_close" in panel.columns
    assert "prev_close" not in panel.columns


def test_assemble_panel_renames_total_a_to_total_shares() -> None:
    panel, _ = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    assert "total_shares" in panel.columns


def test_assemble_panel_records_vwap_provenance() -> None:
    _, provenance = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    assert "vwap" in provenance
    assert "total_turnover" in provenance["vwap"]


def test_assemble_panel_computes_vwap_when_the_source_omits_it() -> None:
    panel, _ = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    expected = panel["total_turnover"] / panel["volume"]
    assert np.allclose(panel["vwap"], expected)


def test_assemble_panel_deduplicates_date_code_pairs() -> None:
    prices = pd.concat([price_frame(), price_frame()], ignore_index=True)
    panel, _ = export.assemble_panel(
        prices, flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    assert not panel.duplicated(["date", "code"]).any()


def test_assemble_panel_marks_status_flags_non_null() -> None:
    panel, _ = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    for column in ("is_st", "is_suspended"):
        assert panel[column].dtype == bool
        assert not panel[column].isna().any()


# ── the mixed-basis guard ───────────────────────────────────────────────

def test_limit_hit_sanity_accepts_a_coherent_panel() -> None:
    panel, _ = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    result = export.limit_hit_sanity(panel)
    assert result["measured"] is True
    assert result["plausible"] is True


def test_limit_hit_sanity_rejects_a_mixed_price_basis() -> None:
    """Raw limit prices next to adjusted closes must not pass silently.

    This is the failure the runbook warns about: the pull would succeed, the
    columns would look fine, and every limit-up filter downstream would be wrong.
    """
    panel, _ = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    panel = panel.copy()
    panel["limit_up"] = panel["close"] * 10.0
    panel["limit_down"] = panel["close"] * 0.01
    result = export.limit_hit_sanity(panel)
    assert result["measured"] is True
    assert result["plausible"] is False
    assert "IMPLAUSIBLE" in result["note"]


def test_limit_hit_sanity_reports_when_it_cannot_measure() -> None:
    frame = pd.DataFrame({"close": [1.0], "limit_up": [np.nan], "limit_down": [np.nan]})
    result = export.limit_hit_sanity(frame)
    assert result["measured"] is False


# ── snapshot round-trip through the repo's own loader ───────────────────

def test_written_snapshot_round_trips_through_the_panel_loader(tmp_path: Path) -> None:
    """The whole point of the export: the pipeline must accept what it writes."""
    from research_core.factor_lab.panel_source import load_validation_panel

    panel, provenance = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    path = tmp_path / "validation_panel.parquet"
    export.write_snapshot(
        panel,
        path,
        {
            "source": "TEST_ONLY_SYNTHETIC",
            "dataset": export.PANEL_DATASET,
            "data_start": panel["date"].min().date().isoformat(),
            "data_end": panel["date"].max().date().isoformat(),
            "price_basis": "post_adjusted",
            "field_provenance": provenance,
        },
    )
    loaded = load_validation_panel(path, require_extended=True)
    assert len(loaded.frame) == len(panel)
    assert set(export.EXTENDED_PANEL_COLUMNS) <= set(loaded.extended_columns)


def test_sidecar_records_a_verifiable_hash(tmp_path: Path) -> None:
    panel, provenance = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    path = tmp_path / "validation_panel.parquet"
    metadata = export.write_snapshot(
        panel,
        path,
        {
            "source": "TEST_ONLY_SYNTHETIC",
            "dataset": export.PANEL_DATASET,
            "data_start": panel["date"].min().date().isoformat(),
            "data_end": panel["date"].max().date().isoformat(),
            "price_basis": "post_adjusted",
        },
    )
    assert metadata["sha256"] == export.sha256_file(path)
    on_disk = json.loads(Path(f"{path}.json").read_text(encoding="utf-8"))
    assert on_disk["sha256"] == metadata["sha256"]
    assert on_disk["row_count"] == len(panel)


def test_loader_rejects_a_panel_without_extended_columns(tmp_path: Path) -> None:
    """require_extended must be a real gate, not decoration."""
    from research_core.factor_lab.panel_source import (
        PanelSourceError,
        load_validation_panel,
    )

    panel, provenance = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    trimmed = panel[[c for c in panel.columns if c not in export.EXTENDED_PANEL_COLUMNS]]
    path = tmp_path / "validation_panel.parquet"
    export.write_snapshot(
        trimmed,
        path,
        {
            "source": "TEST_ONLY_SYNTHETIC",
            "dataset": export.PANEL_DATASET,
            "data_start": trimmed["date"].min().date().isoformat(),
            "data_end": trimmed["date"].max().date().isoformat(),
            "price_basis": "post_adjusted",
        },
    )
    load_validation_panel(path)  # still fine without the extension
    with pytest.raises(PanelSourceError, match="extended columns"):
        load_validation_panel(path, require_extended=True)


# ── no silent degradation ───────────────────────────────────────────────

class _FakeRQData:
    def __init__(self, drop: str | None = None) -> None:
        self.drop = drop

    def get_price(self, codes, **kwargs):  # noqa: ANN003, ANN201
        frame = price_frame()
        if self.drop:
            frame = frame.drop(columns=[self.drop])
        return frame.set_index(["date", "code"])


def test_pull_prices_raises_when_a_requested_field_is_absent() -> None:
    """A missing field must fail the pull, not quietly shrink the panel."""
    with pytest.raises(export.ExportError, match="limit_up"):
        export.pull_prices(
            _FakeRQData(drop="limit_up"), CODES, "2023-01-02", "2023-01-10", batch_size=100
        )


def test_pull_prices_succeeds_when_all_fields_are_present() -> None:
    panel = export.pull_prices(
        _FakeRQData(), CODES, "2023-01-02", "2023-01-10", batch_size=100
    )
    assert {"open", "close", "limit_up", "prev_close"} <= set(panel.columns)


# ── CLI surfaces that must work without the licensed environment ────────

def test_dry_run_prints_the_plan_and_exits_zero(capsys) -> None:  # noqa: ANN001
    assert export.main(["--dry-run", "--out-dir", "somewhere"]) == 0
    out = capsys.readouterr().out
    assert "plan:" in out
    assert "adjust_type=post" in out


def test_self_check_fails_clearly_on_a_missing_directory(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    assert export.self_check(tmp_path / "absent") == 1
    assert "FAILED" in capsys.readouterr().out


def test_self_check_passes_on_a_valid_snapshot(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    panel, provenance = export.assemble_panel(
        price_frame(), flags_frame(), shares_frame(), metadata_frame(), industry_frame()
    )
    export.write_snapshot(
        panel,
        tmp_path / "validation_panel.parquet",
        {
            "source": "TEST_ONLY_SYNTHETIC",
            "dataset": export.PANEL_DATASET,
            "data_start": panel["date"].min().date().isoformat(),
            "data_end": panel["date"].max().date().isoformat(),
            "price_basis": "post_adjusted",
            "field_provenance": provenance,
        },
    )
    assert export.self_check(tmp_path) == 0
    assert "rows=" in capsys.readouterr().out


def test_probe_reports_failures_without_raising() -> None:
    """--probe must survive a broken environment and summarise what failed."""

    class _Broken:
        def __getattr__(self, name):  # noqa: ANN204
            def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
                raise RuntimeError(f"{name} unavailable")

            return _boom

    assert export.probe(_Broken()) == 1
