"""TEST-ONLY contract tests for the local validation-panel loader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from research_core.factor_lab.panel_source import PanelSourceError, load_validation_panel


def _panel_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-03", "2023-01-04"]),
            "code": ["000001.XSHE", "000001.XSHE"],
            "close": [10.0, 10.2],
            "volume": [1000.0, 1200.0],
            "total_turnover": [10000.0, 12240.0],
            "limit_up": [11.0, 11.2],
            "limit_down": [9.0, 9.2],
            "circulation_a": [100_000_000.0, 100_000_000.0],
            "listed_date": pd.to_datetime(["2000-01-01", "2000-01-01"]),
            "de_listed_date": pd.to_datetime([None, None]),
            "is_st": [False, True],
            "is_suspended": [False, False],
        }
    )


def _write_panel(tmp_path: Path, frame: pd.DataFrame | None = None, **sidecar_overrides) -> Path:
    table = _panel_frame() if frame is None else frame
    path = tmp_path / "test_only_validation_panel.parquet"
    table.to_parquet(path, index=False)
    metadata = {
        "source": "TEST_ONLY_SYNTHETIC",
        "dataset": "validation_panel",
        "data_start": pd.to_datetime(table["date"]).min().date().isoformat(),
        "data_end": pd.to_datetime(table["date"]).max().date().isoformat(),
        "row_count": int(len(table)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "price_basis": "TEST_ONLY; post-adjusted close in production",
    }
    metadata.update(sidecar_overrides)
    Path(f"{path}.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return path


def test_only_loads_valid_local_panel(tmp_path: Path) -> None:
    path = _write_panel(tmp_path)

    loaded = load_validation_panel(path, expected_start="2023-01-03", expected_end="2023-01-04")

    assert len(loaded.frame) == 2
    assert loaded.frame["date"].tolist() == list(pd.to_datetime(["2023-01-03", "2023-01-04"]))
    assert loaded.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded.price_basis


def test_only_rejects_parquet_hash_mismatch(tmp_path: Path) -> None:
    path = _write_panel(tmp_path)
    with path.open("ab") as stream:
        stream.write(b"changed after sidecar")

    with pytest.raises(PanelSourceError, match="SHA-256"):
        load_validation_panel(path)


def test_only_rejects_missing_required_column(tmp_path: Path) -> None:
    path = _write_panel(tmp_path, _panel_frame().drop(columns=["circulation_a"]))

    with pytest.raises(PanelSourceError, match="circulation_a"):
        load_validation_panel(path)


def test_only_rejects_duplicate_date_code_key(tmp_path: Path) -> None:
    frame = _panel_frame()
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    path = _write_panel(tmp_path, frame)

    with pytest.raises(PanelSourceError, match="duplicate"):
        load_validation_panel(path)


def test_only_rejects_non_boolean_status_column(tmp_path: Path) -> None:
    frame = _panel_frame()
    frame["is_st"] = [0, 1]
    path = _write_panel(tmp_path, frame)

    with pytest.raises(PanelSourceError, match="is_st.*boolean"):
        load_validation_panel(path)


def test_only_rejects_sidecar_date_range_mismatch(tmp_path: Path) -> None:
    path = _write_panel(tmp_path, data_start="2023-01-02")

    with pytest.raises(PanelSourceError, match="date range"):
        load_validation_panel(path)


def test_only_rejects_row_count_mismatch(tmp_path: Path) -> None:
    path = _write_panel(tmp_path, row_count=7)

    with pytest.raises(PanelSourceError, match="row_count mismatch"):
        load_validation_panel(path)


def test_only_rejects_missing_price_basis(tmp_path: Path) -> None:
    path = _write_panel(tmp_path, price_basis="")

    with pytest.raises(PanelSourceError, match="price_basis"):
        load_validation_panel(path)


def test_only_rejects_expected_range_mismatch(tmp_path: Path) -> None:
    path = _write_panel(tmp_path)

    with pytest.raises(PanelSourceError, match="expected_start mismatch"):
        load_validation_panel(path, expected_start="2023-01-02")


def test_only_rejects_missing_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "test_only_missing_sidecar.parquet"
    _panel_frame().to_parquet(path, index=False)

    with pytest.raises(PanelSourceError, match="sidecar file does not exist"):
        load_validation_panel(path)
