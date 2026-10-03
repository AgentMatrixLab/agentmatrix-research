from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from research_core.data_loader.rqdata_panel import (
    RQDataPanelError,
    load_rqdata_benchmark,
    load_rqdata_panel,
)


def _panel_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-03", "2023-01-04"]),
            "code": ["000001.XSHE", "000001.XSHE"],
            "open": [10.0, 10.2],
            "high": [10.4, 10.5],
            "low": [9.9, 10.1],
            "close": [10.3, 10.4],
            "volume": [1000, 1200],
            "amount": [10300.0, 12480.0],
            "adjustment_factor": [1.0, 1.02],
            "is_suspended": [False, False],
            "is_st": [False, True],
            "listing_date": pd.to_datetime(["2000-01-01", "2000-01-01"]),
            "delisting_date": pd.to_datetime([None, None]),
            "limit_up": [11.0, 11.2],
            "limit_down": [9.0, 9.2],
        }
    )


def _write_parquet_and_sidecar(
    tmp_path: Path,
    frame: pd.DataFrame,
    *,
    dataset: str,
    extra_metadata: dict | None = None,
) -> Path:
    path = tmp_path / f"test_only_{dataset}.parquet"
    frame.to_parquet(path, index=False)
    metadata = {
        "source": "TEST_ONLY_SYNTHETIC",
        "dataset": dataset,
        "data_start": frame["date"].min().date().isoformat(),
        "data_end": frame["date"].max().date().isoformat(),
        "row_count": len(frame),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    metadata.update(extra_metadata or {})
    Path(f"{path}.json").write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _write_test_panel(tmp_path: Path, frame: pd.DataFrame | None = None, **metadata) -> Path:
    return _write_parquet_and_sidecar(
        tmp_path,
        frame if frame is not None else _panel_frame(),
        dataset="daily_panel",
        extra_metadata={
            "price_basis": "unadjusted_ohlc_with_adjustment_factor",
            "adjustment_factor_definition": "TEST_ONLY; not RQData evidence",
            **metadata,
        },
    )


def test_only_loads_valid_local_panel_and_checks_sidecar_hash(tmp_path: Path) -> None:
    path = _write_test_panel(tmp_path)

    loaded = load_rqdata_panel(
        path,
        expected_start="2023-01-03",
        expected_end="2023-01-04",
    )

    assert len(loaded) == 2
    assert loaded["date"].tolist() == list(pd.to_datetime(["2023-01-03", "2023-01-04"]))
    assert loaded["code"].tolist() == ["000001.XSHE", "000001.XSHE"]


def test_only_rejects_missing_required_column(tmp_path: Path) -> None:
    frame = _panel_frame().drop(columns=["amount"])
    path = _write_test_panel(tmp_path, frame)

    with pytest.raises(RQDataPanelError, match="amount"):
        load_rqdata_panel(path)


def test_only_rejects_non_numeric_market_column(tmp_path: Path) -> None:
    frame = _panel_frame()
    frame["close"] = ["10.3", "10.4"]
    path = _write_test_panel(tmp_path, frame)

    with pytest.raises(RQDataPanelError, match="close.*numeric"):
        load_rqdata_panel(path)


def test_only_rejects_non_boolean_status_column(tmp_path: Path) -> None:
    frame = _panel_frame()
    frame["is_st"] = [0, 1]
    path = _write_test_panel(tmp_path, frame)

    with pytest.raises(RQDataPanelError, match="is_st.*boolean"):
        load_rqdata_panel(path)


def test_only_rejects_timezone_aware_trading_dates(tmp_path: Path) -> None:
    frame = _panel_frame()
    frame["date"] = frame["date"].dt.tz_localize("Asia/Shanghai")
    path = _write_test_panel(tmp_path, frame)

    with pytest.raises(RQDataPanelError, match="timezone-aware"):
        load_rqdata_panel(path)


def test_only_rejects_duplicate_date_code_key(tmp_path: Path) -> None:
    frame = _panel_frame()
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    path = _write_test_panel(tmp_path, frame)

    with pytest.raises(RQDataPanelError, match="duplicate"):
        load_rqdata_panel(path)


def test_only_rejects_sidecar_date_range_mismatch(tmp_path: Path) -> None:
    path = _write_test_panel(tmp_path, data_start="2023-01-02")

    with pytest.raises(RQDataPanelError, match="date range"):
        load_rqdata_panel(path)


def test_only_rejects_sidecar_row_count_mismatch(tmp_path: Path) -> None:
    path = _write_test_panel(tmp_path, row_count=3)

    with pytest.raises(RQDataPanelError, match="row_count mismatch"):
        load_rqdata_panel(path)


def test_only_rejects_expected_range_mismatch(tmp_path: Path) -> None:
    path = _write_test_panel(tmp_path)

    with pytest.raises(RQDataPanelError, match="expected_start mismatch"):
        load_rqdata_panel(path, expected_start="2023-01-02")


def test_only_rejects_parquet_hash_mismatch(tmp_path: Path) -> None:
    path = _write_test_panel(tmp_path)
    with path.open("ab") as stream:
        stream.write(b"changed after sidecar")

    with pytest.raises(RQDataPanelError, match="SHA-256"):
        load_rqdata_panel(path)


def test_only_rejects_missing_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "test_only_missing_sidecar.parquet"
    _panel_frame().to_parquet(path, index=False)

    with pytest.raises(RQDataPanelError, match="sidecar file does not exist"):
        load_rqdata_panel(path)


def test_only_loads_000985_benchmark_with_explicit_return_type(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-03", "2023-01-04"]),
            "return": [0.01, -0.005],
        }
    )
    path = _write_parquet_and_sidecar(
        tmp_path,
        frame,
        dataset="benchmark_daily_return",
        extra_metadata={"benchmark_code": "000985", "return_type": "price_return"},
    )

    loaded = load_rqdata_benchmark(path)

    assert loaded["return"].tolist() == [0.01, -0.005]


def test_only_rejects_wrong_benchmark_identity(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-03"]),
            "return": [0.01],
        }
    )
    path = _write_parquet_and_sidecar(
        tmp_path,
        frame,
        dataset="benchmark_daily_return",
        extra_metadata={"benchmark_code": "000300", "return_type": "price_return"},
    )

    with pytest.raises(RQDataPanelError, match="benchmark_code"):
        load_rqdata_benchmark(path)


def test_only_rejects_duplicate_benchmark_date(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-03", "2023-01-03"]),
            "return": [0.01, 0.02],
        }
    )
    path = _write_parquet_and_sidecar(
        tmp_path,
        frame,
        dataset="benchmark_daily_return",
        extra_metadata={"benchmark_code": "000985", "return_type": "total_return"},
    )

    with pytest.raises(RQDataPanelError, match="duplicate"):
        load_rqdata_benchmark(path)
