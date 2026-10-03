"""Shared TEST-ONLY fixtures.

The synthetic panel here exists purely to exercise code paths offline. It is not market data
and must never be used as factor-validity evidence.
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research_core.factor_lab.deterministic_validation import load_validation_config

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "validation_gates.yaml"


def synthetic_panel_frame() -> pd.DataFrame:
    """Deterministic, synthetic all-A-shaped panel: 30 codes x business days 2014-2019."""
    dates = pd.bdate_range("2014-01-02", "2019-12-31")
    codes = [f"{index:06d}.XSHE" for index in range(1, 31)]
    generator = np.random.default_rng(20261003)

    closes = []
    for position, _code in enumerate(codes):
        shocks = generator.normal(0.0004, 0.02, len(dates))
        level = 12.0 + position * 0.35
        closes.append(level * np.exp(np.cumsum(shocks)))
    close = np.concatenate(closes)
    volume = np.concatenate(
        [
            1_000_000.0
            + 1_000.0 * position
            + 10_000.0 * np.abs(np.sin(np.arange(len(dates)) / (7.0 + position)))
            for position in range(len(codes))
        ]
    )

    frame = pd.DataFrame(
        {
            "date": np.tile(dates.to_numpy(), len(codes)),
            "code": np.repeat(codes, len(dates)),
            "close": close,
            "volume": volume,
            "total_turnover": close * volume,
            "limit_up": close * 1.1,
            "limit_down": close * 0.9,
            "circulation_a": 100_000_000.0,
            "listed_date": pd.Timestamp("2010-01-04"),
            "de_listed_date": pd.NaT,
            "is_st": False,
            "is_suspended": False,
        }
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame["listed_date"] = pd.to_datetime(frame["listed_date"])
    frame["de_listed_date"] = pd.to_datetime(frame["de_listed_date"])
    return frame


def synthetic_validation_config() -> dict:
    """Repository gates config with the split moved onto the synthetic panel's date range."""
    config = copy.deepcopy(load_validation_config(CONFIG_PATH))
    config["split"] = {
        "train_start": "2016-01-01",
        "train_end": "2017-12-31",
        "oos_start": "2018-01-01",
        "oos_end": "2019-12-31",
    }
    return config


@pytest.fixture(scope="session")
def synthetic_panel() -> pd.DataFrame:
    return synthetic_panel_frame()


@pytest.fixture(scope="session")
def test_config() -> dict:
    return synthetic_validation_config()
