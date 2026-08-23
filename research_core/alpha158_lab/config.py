from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from common.paths import REPO_ROOT, data_path, runtime_path

load_dotenv(REPO_ROOT / ".env")


@dataclass(slots=True)
class SmartDataConfig:
    host: str = "127.0.0.1"
    port: int = 19000
    user: str = "smartdata_ro"
    password: str = ""
    database: str = "amazingdata"

    @classmethod
    def from_env(cls) -> SmartDataConfig:
        return cls(
            host=os.getenv("SMARTDATA_CH_HOST", "127.0.0.1"),
            port=int(os.getenv("SMARTDATA_CH_PORT", "19000")),
            user=os.getenv("SMARTDATA_CH_USER", "smartdata_ro"),
            password=os.getenv("SMARTDATA_CH_PASSWORD", ""),
            database=os.getenv("SMARTDATA_CH_DATABASE", "amazingdata"),
        )


@dataclass(slots=True)
class Alpha158ResearchConfig:
    """Alpha158 research config.

    Two independent windows:
    - ``request_start`` / ``request_end`` (+ resolved ``start_date`` / ``end_date``):
      SmartData factor computation and IC/backtest cover this full range.
    - ``validation_end`` (with ``overlap_*``): qlib truth accuracy check only.
      Defaults to local cn_data calendar end; pass ``--validation-end`` on CLI when
      qlib data is extended — this does NOT shrink production factor output dates.
    """
    # Requested compute window; resolved to DB min/max on pipeline start.
    request_start: str = "2020-01-01"
    request_end: str = "2026-12-31"
    start_date: str = "2020-01-01"
    end_date: str = "2026-12-31"
    # Qlib truth overlap cap (accuracy check only; factor compute uses end_date above).
    validation_end: str = "2021-06-11"
    universe: str = "all_a"
    qlib_provider_uri: str = ""
    output_dir: Path = runtime_path("alpha158_lab")

    def __post_init__(self) -> None:
        if not self.qlib_provider_uri:
            self.qlib_provider_uri = str(data_path("qlib", "cn_data"))
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def overlap_start(self) -> str:
        return self.start_date

    @property
    def overlap_end(self) -> str:
        return min(self.end_date, self.validation_end)

    @property
    def compute_range_label(self) -> str:
        return f"{self.start_date} ~ {self.end_date}"

    @property
    def validation_range_label(self) -> str:
        return f"{self.overlap_start} ~ {self.overlap_end}"


DEFAULT_CONFIG = Alpha158ResearchConfig()