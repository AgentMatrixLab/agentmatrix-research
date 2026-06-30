from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from research_core.alpha158_lab.factors.specs import ALPHA158_FIRST_10
from research_core.qlib_lab.runtime import QlibWorkspaceConfig, init_qlib_workspace


def export_qlib_alpha158_truth(
    *,
    start_date: str,
    end_date: str,
    instruments: str = "all",
    output_dir: str | Path,
    factor_names: list[str] | None = None,
) -> dict[str, Any]:
    factor_names = list(factor_names or ALPHA158_FIRST_10)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    init_qlib_workspace(QlibWorkspaceConfig.from_env(), require_package=True, require_data=True)
    from qlib.contrib.data.handler import Alpha158
    from qlib.data.dataset import DatasetH

    handler = Alpha158(
        instruments=instruments,
        start_time=start_date,
        end_time=end_date,
        fit_start_time=start_date,
        fit_end_time=end_date,
    )
    handler.setup_data()
    dataset = DatasetH(handler=handler, segments={"truth": (start_date, end_date)})
    frame = dataset.prepare("truth", col_set="feature")
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [str(col) for col in frame.columns.get_level_values(-1)]

    missing = [name for name in factor_names if name not in frame.columns]
    if missing:
        raise KeyError(f"Qlib Alpha158 truth missing factors: {missing}")

    truth = frame.reset_index()
    truth = truth.rename(columns={"datetime": "date", "instrument": "code"})
    truth["date"] = pd.to_datetime(truth["date"])
    keep = ["date", "code", *factor_names]
    truth = truth[keep]
    out_path = output_dir / f"qlib_truth_{start_date}_{end_date}.parquet"
    truth.to_parquet(out_path, index=False)

    summary = {
        "path": str(out_path.resolve()),
        "rows": int(len(truth)),
        "codes": int(truth["code"].nunique()),
        "date_min": str(truth["date"].min()),
        "date_max": str(truth["date"].max()),
        "factors": factor_names,
    }
    (output_dir / f"qlib_truth_{start_date}_{end_date}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary