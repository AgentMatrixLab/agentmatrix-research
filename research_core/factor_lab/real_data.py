from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from research_core.data_loader.quant_api_client import QuantApiClient
from research_core.factor_lab.evaluation import build_factor_evaluation_report, compute_forward_returns
from research_core.factor_lab.libraries.factor_sets import (
    compute_factor_set,
    factor_set_library_name,
    factor_set_specs,
)
from research_core.factor_lab.registry import export_library_specs
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_local_env() -> None:
    for env_path in (PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env"):
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise ValueError("Quant API kline payload does not contain a data list.")
    return [item for item in data if isinstance(item, dict)]


def _discover_symbols(client: QuantApiClient, *, n_symbols: int) -> list[str]:
    payload = client.kline_1d(
        {
            "limit": max(n_symbols * 4, 100),
            "order": "asc",
            "order_by": "trade_date",
        }
    )
    symbols: list[str] = []
    for row in _records(payload):
        symbol = str(row.get("symbol", "")).strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= n_symbols:
            break
    if not symbols:
        raise ValueError("Quant API returned no symbols from ods_kline_1d.")
    return symbols


def fetch_quant_kline_panel(
    *,
    symbols: list[str] | None = None,
    n_symbols: int = 12,
    n_dates: int = 80,
    client: QuantApiClient | None = None,
) -> pd.DataFrame:
    load_local_env()
    api = client or QuantApiClient()
    selected = [item.strip() for item in symbols or [] if item.strip()]
    if not selected:
        selected = _discover_symbols(api, n_symbols=n_symbols)

    rows: list[dict[str, Any]] = []
    for symbol in selected[:n_symbols]:
        payload = api.kline_1d(
            {
                "symbol": symbol,
                "limit": n_dates,
                "order": "asc",
                "order_by": "trade_date",
            }
        )
        rows.extend(_records(payload))

    if not rows:
        raise ValueError("Quant API returned no kline rows for selected symbols.")

    panel = pd.DataFrame(rows).rename(columns={"symbol": "code", "trade_date": "date"})
    required = {"date", "code", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"Quant API kline rows are missing required columns: {missing}")

    panel["date"] = pd.to_datetime(panel["date"])
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column in panel.columns:
            panel[column] = pd.to_numeric(panel[column], errors="coerce")
    if "amount" not in panel.columns:
        panel["amount"] = panel["close"] * panel["volume"]
    panel["vwap"] = np.where(panel["volume"].replace(0, np.nan).notna(), panel["amount"] / panel["volume"], np.nan)
    panel = panel.dropna(subset=["date", "code", "open", "high", "low", "close", "volume", "amount"])
    panel = panel.sort_values(["code", "date"]).drop_duplicates(["date", "code"], keep="last").reset_index(drop=True)
    panel["returns"] = panel.groupby("code")["close"].pct_change()

    keep_cols = ["date", "code", "open", "high", "low", "close", "volume", "amount", "vwap", "returns"]
    return panel[keep_cols]


def build_long_short_backtest(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    *,
    factor_names: list[str],
    quantile: float = 0.2,
) -> dict[str, Any]:
    sorted_panel = panel[["date", "code", "close"]].sort_values(["code", "date"]).reset_index(drop=True)
    forward = sorted_panel.copy()
    forward["forward_return_1d"] = compute_forward_returns(sorted_panel, price_col="close")
    enriched = factor_frame.merge(forward[["date", "code", "forward_return_1d"]], on=["date", "code"], how="left")

    results: dict[str, Any] = {}
    for factor_name in factor_names:
        daily_rows: list[dict[str, Any]] = []
        previous_long: set[str] | None = None
        previous_short: set[str] | None = None
        turnovers: list[float] = []

        for date, date_slice in enriched[["date", "code", factor_name, "forward_return_1d"]].dropna().groupby("date"):
            if len(date_slice) < 5:
                continue
            ranks = date_slice[factor_name].rank(method="average", pct=True)
            long_codes = set(date_slice.loc[ranks >= 1.0 - quantile, "code"].astype(str))
            short_codes = set(date_slice.loc[ranks <= quantile, "code"].astype(str))
            if not long_codes or not short_codes:
                continue
            long_ret = float(date_slice.loc[date_slice["code"].isin(long_codes), "forward_return_1d"].mean())
            short_ret = float(date_slice.loc[date_slice["code"].isin(short_codes), "forward_return_1d"].mean())
            daily_ret = long_ret - short_ret
            daily_rows.append(
                {
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "long_return": long_ret,
                    "short_return": short_ret,
                    "long_short_return": daily_ret,
                    "long_count": len(long_codes),
                    "short_count": len(short_codes),
                }
            )
            if previous_long is not None and previous_short is not None:
                long_turnover = 1.0 - len(long_codes & previous_long) / max(len(long_codes | previous_long), 1)
                short_turnover = 1.0 - len(short_codes & previous_short) / max(len(short_codes | previous_short), 1)
                turnovers.append(float((long_turnover + short_turnover) / 2.0))
            previous_long = long_codes
            previous_short = short_codes

        returns = pd.Series([row["long_short_return"] for row in daily_rows], dtype=float)
        equity = (1.0 + returns.fillna(0.0)).cumprod() if len(returns) else pd.Series(dtype=float)
        drawdown = equity / equity.cummax() - 1.0 if len(equity) else pd.Series(dtype=float)
        mean = float(returns.mean()) if len(returns) else float("nan")
        std = float(returns.std(ddof=1)) if len(returns) > 1 else float("nan")
        results[factor_name] = {
            "daily": daily_rows,
            "summary": {
                "days": len(daily_rows),
                "mean_daily_return": mean,
                "annualized_return": float((1.0 + mean) ** 252 - 1.0) if pd.notna(mean) else float("nan"),
                "sharpe": float(np.sqrt(252) * mean / std) if pd.notna(std) and std != 0 else float("nan"),
                "max_drawdown": float(drawdown.min()) if len(drawdown) else float("nan"),
                "mean_turnover": float(np.mean(turnovers)) if turnovers else float("nan"),
                "final_equity": float(equity.iloc[-1]) if len(equity) else float("nan"),
            },
        }
    return {"quantile": quantile, "factors": results}


def _render_real_markdown(evaluation: dict[str, Any], strategy: dict[str, Any], *, factor_names: list[str]) -> str:
    lines = [
        f"# {evaluation.get('library', 'Factor')} Real Data Report",
        "",
        f"- Generated at: {now_iso()}",
        f"- Dataset rows: {evaluation['dataset']['rows']}",
        f"- Securities: {evaluation['dataset']['codes']}",
        f"- Dates: {evaluation['dataset']['dates']}",
        "",
        "| Factor | Coverage | Rank IC Mean | Rank IC IR | LS Mean | Sharpe | Max DD |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for factor_name in factor_names:
        metrics = evaluation["summary"]["metrics"][factor_name]
        backtest = strategy["factors"].get(factor_name, {}).get("summary", {})
        lines.append(
            f"| {factor_name} | {metrics['coverage_ratio']:.4f} | {metrics['rank_ic_mean']:.6f} | "
            f"{metrics['rank_ic_ir']:.6f} | {metrics['long_short_mean']:.6f} | "
            f"{backtest.get('sharpe', float('nan')):.6f} | {backtest.get('max_drawdown', float('nan')):.6f} |"
        )
    return "\n".join(lines) + "\n"


def run_factor_set_real_data_job(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()

    factor_set = str(request_payload.get("factor_set", "gtja191")).lower()
    specs = factor_set_specs(factor_set)
    available = [spec.factor_name for spec in specs]
    factor_names = request_payload.get("factor_names") or available[:3]
    invalid = [name for name in factor_names if name not in available]
    if invalid:
        raise ValueError(f"Unsupported {factor_set} factors: {invalid}")

    n_symbols = int(request_payload.get("n_symbols", 12))
    n_dates = int(request_payload.get("n_dates", 80))
    symbols = request_payload.get("symbols") or None
    quantile = float(request_payload.get("quantile", 0.2))

    catalog_key = factor_set
    library = factor_set_library_name(factor_set)
    export_library_specs(config=workspace, library=catalog_key, specs=specs)

    job_id = request_payload.get("job_id") or f"{factor_set}-real-{uuid4().hex[:10]}"
    panel = fetch_quant_kline_panel(symbols=symbols, n_symbols=n_symbols, n_dates=n_dates)
    factor_frame = compute_factor_set(panel, factor_set, factor_names=factor_names)
    evaluation_report = build_factor_evaluation_report(panel, factor_frame, factor_names=factor_names, library=library)
    strategy_report = build_long_short_backtest(panel, factor_frame, factor_names=factor_names, quantile=quantile)

    frame_path = workspace.frame_path(catalog_key, job_id)
    factor_frame.to_csv(frame_path, index=False, encoding="utf-8")
    panel_path = workspace.frame_path(catalog_key, f"{job_id}_panel")
    panel.to_csv(panel_path, index=False, encoding="utf-8")

    evaluation_json_path = workspace.report_path(f"{job_id}_evaluation", suffix=".json")
    evaluation_json_path.write_text(json.dumps(evaluation_report, ensure_ascii=False, indent=2), encoding="utf-8")
    strategy_json_path = workspace.report_path(f"{job_id}_strategy", suffix=".json")
    strategy_json_path.write_text(json.dumps(strategy_report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md_path = workspace.report_path(f"{job_id}_real_data_report", suffix=".md")
    report_md_path.write_text(_render_real_markdown(evaluation_report, strategy_report, factor_names=factor_names), encoding="utf-8")

    job = {
        "job_id": job_id,
        "library": library,
        "factor_set": factor_set,
        "status": "completed",
        "data_source": "quant_api",
        "generated_at": now_iso(),
        "requested_factors": factor_names,
        "dataset": {
            "n_dates_requested": n_dates,
            "n_symbols_requested": n_symbols,
            "rows": int(len(panel)),
            "dates": int(panel["date"].nunique()),
            "codes": int(panel["code"].nunique()),
            "symbols": sorted(panel["code"].astype(str).unique().tolist()),
        },
        "artifacts": {
            "panel_frame": str(panel_path),
            "factor_frame": str(frame_path),
            "evaluation_json": str(evaluation_json_path),
            "strategy_json": str(strategy_json_path),
            "research_report_markdown": str(report_md_path),
            "catalog": str(workspace.catalog_path(catalog_key)),
            "specs": str(workspace.specs_path(catalog_key)),
        },
        "summary": {
            "evaluation": evaluation_report["summary"]["metrics"],
            "strategy": {name: strategy_report["factors"][name]["summary"] for name in factor_names},
        },
    }
    workspace.job_path(job_id).write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job
