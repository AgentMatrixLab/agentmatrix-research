"""Quant API 真实数据研究脚本

从 Quant API 拉取真实行情数据和因子数据，
支持复现 alpha101/gtja191 因子以及 Quant API 自带的 33 个因子。

用法：
    python scripts/quant_api_research.py --factors ret_1m,roe_ttm --symbols 000001.SZ --start-date 2023-01-01 --end-date 2024-01-01 --factor-set quant_api
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import numpy as np
import pandas as pd

from research_core.data_loader.quant_api_client import QuantApiClient
from research_core.factor_lab.libraries.alpha101 import compute_alpha101_factors
from research_core.factor_lab.libraries.gtja191 import compute_gtja191_alphas
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


QUANT_API_33_FACTORS = [
    "ret_1m", "ret_3m", "ret_6m", "ret_12m",
    "volatility_1m", "volatility_3m",
    "reversal", "momentum_12_1",
    "avg_amount_1m", "log_amount_1m",
    "max_ret_1m", "min_ret_1m",
    "up_ratio_1m",
    "ma_signal",
    "vol_convergence",
    "illiquidity",
    "log_price",
    "turnover_proxy",
    "volatility_6m",
    "volume_ratio",
    "high_low_1m",
    "rsi_14",
    "bb_position",
    "ret_3m_vol_adj",
    "amplitude_1m",
    "roe_ttm", "roa_ttm", "net_margin", "debt_to_asset",
    "revenue_yoy", "profit_yoy", "eps_yoy",
    "asset_turnover",
]


def _load_local_env() -> None:
    project_root = Path(__file__).resolve().parents[1]
    for env_path in (project_root / ".env.local", project_root / ".env"):
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def fetch_kline_data(client: QuantApiClient, symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    all_data = []
    for symbol in symbols:
        params = {
            "symbol": symbol,
            "order": "asc",
            "limit": 1000
        }
        try:
            data = client.kline_1d(params)
            if data.get("data"):
                df = pd.DataFrame(data["data"])
                all_data.append(df)
        except Exception as e:
            print(f"获取 {symbol} 数据失败: {e}")
    
    if not all_data:
        raise ValueError("未获取到任何行情数据")
    
    df = pd.concat(all_data, ignore_index=True)
    
    df = df.rename(columns={
        "trade_date": "date",
        "symbol": "code",
    })
    
    df["date"] = pd.to_datetime(df["date"])
    if "amount" not in df.columns:
        df["amount"] = df["close"] * df["volume"]
    df["vwap"] = df["amount"] / df["volume"].replace(0, np.nan)
    df["returns"] = df.groupby("code")["close"].pct_change()
    
    required_cols = ["date", "code", "open", "high", "low", "close", "volume", "amount", "vwap", "returns"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = np.nan
    
    df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
    
    return df[required_cols]


def fetch_quant_api_factors(client: QuantApiClient, symbols: list[str], factors: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    all_stock_dfs = []
    for symbol in symbols:
        stock_df = None
        for factor in factors:
            params = {
                "symbol": symbol,
                "factor": factor,
                "order": "asc",
            }
            try:
                data = client.factor_monthly(params)
                if data.get("data"):
                    df = pd.DataFrame(data["data"])
                    if factor in df.columns:
                        df = df[["symbol", "trade_date", factor]]
                        df = df.rename(columns={"trade_date": "date", "symbol": "code"})
                        df["date"] = pd.to_datetime(df["date"])
                        df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
                        
                        if stock_df is None:
                            stock_df = df
                        else:
                            stock_df = pd.merge(stock_df, df, on=["date", "code"], how="outer")
            except Exception as e:
                print(f"获取 {factor}@{symbol} 数据失败: {e}")
        
        if stock_df is not None:
            all_stock_dfs.append(stock_df)
    
    if not all_stock_dfs:
        raise ValueError("未获取到任何因子数据")
    
    merged_df = pd.concat(all_stock_dfs, ignore_index=True)
    return merged_df


def compute_ic(factor_series: pd.Series, returns: pd.Series) -> float:
    combined = pd.DataFrame({"factor": factor_series, "returns": returns}).dropna()
    if len(combined) < 2:
        return np.nan
    return combined["factor"].corr(combined["returns"])


def compute_rank_ic(factor_series: pd.Series, returns: pd.Series) -> float:
    combined = pd.DataFrame({"factor": factor_series, "returns": returns}).dropna()
    if len(combined) < 2:
        return np.nan
    return combined["factor"].rank().corr(combined["returns"].rank())


def compute_group_returns(factor_df: pd.DataFrame, num_groups: int = 5) -> pd.DataFrame:
    df = factor_df.copy().dropna(subset=["factor", "forward_return"])
    if len(df) == 0:
        return pd.DataFrame()
    
    df["group"] = df.groupby("date")["factor"].transform(
        lambda x: pd.qcut(x, num_groups, labels=False, duplicates="drop") + 1
    )
    
    group_returns = df.groupby(["date", "group"])["forward_return"].mean().unstack()
    if len(group_returns.columns) >= 2:
        max_group = group_returns.columns.max()
        min_group = group_returns.columns.min()
        group_returns["long_short"] = group_returns[max_group] - group_returns[min_group]
    return group_returns


def compute_max_drawdown(returns: pd.Series) -> float:
    if returns is None or len(returns) == 0:
        return np.nan
    cum_returns = (1 + returns).cumprod()
    running_max = cum_returns.cummax()
    drawdown = (cum_returns - running_max) / running_max
    return drawdown.min()


def compute_sharpe(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    if returns is None or len(returns) == 0:
        return np.nan
    excess_returns = returns - risk_free_rate
    return excess_returns.mean() / excess_returns.std() * math.sqrt(252)


def compute_turnover(factor_df: pd.DataFrame) -> float:
    df = factor_df.copy().dropna(subset=["factor"])
    if len(df) == 0:
        return np.nan
    
    df["rank"] = df.groupby("date")["factor"].rank(pct=True)
    rank_diff = df.groupby("code")["rank"].diff().abs()
    return rank_diff.mean()


def analyze_factor(factor_name: str, panel: pd.DataFrame, factor_df: pd.DataFrame) -> dict:
    if factor_name not in factor_df.columns:
        return {
            "factor_name": factor_name,
            "error": "因子不存在",
        }
    
    if len(factor_df) != len(panel):
        panel_monthly = panel.copy()
        panel_monthly["month"] = panel_monthly["date"].dt.to_period("M")
        monthly_returns = panel_monthly.groupby(["code", "month"])["returns"].sum().reset_index()
        monthly_returns["date"] = monthly_returns["month"].dt.to_timestamp(how="end")
        
        factor_df_filtered = factor_df[["code", "date", factor_name]].copy()
        factor_df_filtered["date"] = factor_df_filtered["date"].dt.to_period("M").dt.to_timestamp(how="end")
        
        merged = pd.merge(
            monthly_returns[["code", "date", "returns"]],
            factor_df_filtered,
            on=["date", "code"],
            how="inner"
        )
        
        df = merged.rename(columns={factor_name: "factor"})
        df["forward_return"] = df.groupby("code")["returns"].shift(-1)
    else:
        df = panel.copy()
        df["factor"] = factor_df[factor_name].values
        df["forward_return"] = df.groupby("code")["returns"].shift(-1)
    
    ic_values = []
    rank_ic_values = []
    dates = []
    for date, group in df.groupby("date"):
        ic_val = compute_ic(group["factor"], group["forward_return"])
        rank_ic_val = compute_rank_ic(group["factor"], group["forward_return"])
        if not np.isnan(ic_val):
            ic_values.append(ic_val)
            rank_ic_values.append(rank_ic_val)
            dates.append(date)
    ic_values = pd.Series(ic_values, index=dates)
    rank_ic_values = pd.Series(rank_ic_values, index=dates)
    
    group_returns = compute_group_returns(df)
    
    valid_factor = df["factor"].notna()
    coverage = valid_factor.sum() / len(df) if len(df) > 0 else 0
    
    ic_time_series = []
    for i in range(len(dates)):
        ic_time_series.append({
            "date": dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], "strftime") else str(dates[i]),
            "ic": float(ic_values.iloc[i]),
            "rank_ic": float(rank_ic_values.iloc[i]),
        })
    
    group_returns_data = {}
    if not group_returns.empty:
        for group in group_returns.columns:
            group_returns_data[str(group)] = []
            for date, val in group_returns[group].items():
                group_returns_data[str(group)].append({
                    "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
                    "return": float(val),
                })
    
    results = {
        "factor_name": factor_name,
        "coverage_ratio": float(coverage),
        "non_null_count": int(valid_factor.sum()),
        "mean": float(df["factor"].mean()),
        "std": float(df["factor"].std()),
        "abs_mean": float(df["factor"].abs().mean()),
        "rank_ic_mean": float(rank_ic_values.mean()),
        "rank_ic_std": float(rank_ic_values.std()),
        "rank_ic_ir": float(rank_ic_values.mean() / rank_ic_values.std()) if rank_ic_values.std() != 0 else np.nan,
        "pearson_ic_mean": float(ic_values.mean()),
        "long_short_mean": float(group_returns["long_short"].mean()) if not group_returns.empty and "long_short" in group_returns.columns else np.nan,
        "cross_section_count": int(len(dates)),
        "ic_time_series": ic_time_series,
        "group_returns": group_returns_data,
    }
    
    return results


def build_strategy_report(panel: pd.DataFrame, factor_frame: pd.DataFrame, factor_names: list[str]) -> dict:
    results = {}
    for factor_name in factor_names:
        if factor_name not in factor_frame.columns:
            continue
        
        if len(factor_frame) != len(panel):
            panel_monthly = panel.copy()
            panel_monthly["month"] = panel_monthly["date"].dt.to_period("M")
            monthly_returns = panel_monthly.groupby(["code", "month"])["returns"].sum().reset_index()
            monthly_returns["date"] = monthly_returns["month"].dt.to_timestamp(how="end")
            
            factor_df_filtered = factor_frame[["code", "date", factor_name]].copy()
            factor_df_filtered["date"] = factor_df_filtered["date"].dt.to_period("M").dt.to_timestamp(how="end")
            
            df = pd.merge(
                monthly_returns[["code", "date", "returns"]],
                factor_df_filtered,
                on=["date", "code"],
                how="inner"
            )
            df = df.rename(columns={factor_name: "factor"})
            df["forward_return"] = df.groupby("code")["returns"].shift(-1)
        else:
            df = panel.copy()
            df["factor"] = factor_frame[factor_name].values
            df["forward_return"] = df.groupby("code")["returns"].shift(-1)
        
        df = df.dropna(subset=["factor", "forward_return"])
        
        daily_rows = []
        previous_long = None
        previous_short = None
        turnovers = []
        
        for date, date_slice in df.groupby("date"):
            if len(date_slice) < 2:
                continue
            ranks = date_slice["factor"].rank(method="average", pct=True)
            long_codes = set(date_slice.loc[ranks >= 0.8, "code"].astype(str))
            short_codes = set(date_slice.loc[ranks <= 0.2, "code"].astype(str))
            if not long_codes or not short_codes:
                continue
            long_ret = float(date_slice.loc[date_slice["code"].isin(long_codes), "forward_return"].mean())
            short_ret = float(date_slice.loc[date_slice["code"].isin(short_codes), "forward_return"].mean())
            daily_ret = long_ret - short_ret
            daily_rows.append({
                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "long_return": long_ret,
                "short_return": short_ret,
                "long_short_return": daily_ret,
            })
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
        
        if len(daily_rows) >= 2:
            dates = pd.to_datetime([row["date"] for row in daily_rows])
            avg_interval_days = (dates[-1] - dates[0]).days / (len(dates) - 1)
            freq_multiplier = 252 / avg_interval_days if avg_interval_days > 0 else 12
        else:
            freq_multiplier = 12
        
        results[factor_name] = {
            "daily": daily_rows,
            "summary": {
                "days": len(daily_rows),
                "mean_daily_return": mean,
                "annualized_return": float((1.0 + mean) ** freq_multiplier - 1.0) if pd.notna(mean) else float("nan"),
                "sharpe": float(np.sqrt(freq_multiplier) * mean / std) if pd.notna(std) and std != 0 else float("nan"),
                "max_drawdown": float(drawdown.min()) if len(drawdown) else float("nan"),
                "mean_turnover": float(np.mean(turnovers)) if turnovers else float("nan"),
                "final_equity": float(equity.iloc[-1]) if len(equity) else float("nan"),
            },
        }
    
    return {"quantile": 0.2, "factors": results}


def run_research(factors: list[str], symbols: list[str], start_date: str, end_date: str, factor_set: str = "quant_api") -> dict:
    _load_local_env()
    
    client = QuantApiClient()
    
    print(f"[1/4] 从 Quant API 拉取行情数据...")
    panel = fetch_kline_data(client, symbols, start_date, end_date)
    print(f"  数据量: {len(panel)} 条, 股票数: {panel['code'].nunique()}")
    print(f"  时间范围: {panel['date'].min().date()} ~ {panel['date'].max().date()}")
    
    print(f"[2/4] 计算/拉取因子值...")
    if factor_set.lower() == "quant_api":
        factor_df = fetch_quant_api_factors(client, symbols, factors, start_date, end_date)
        factor_df = factor_df.sort_values(["date", "code"]).reset_index(drop=True)
        panel = panel.sort_values(["date", "code"]).reset_index(drop=True)
        for col in factors:
            if col not in factor_df.columns:
                factor_df[col] = np.nan
    elif factor_set.lower() in {"wq101", "alpha101"}:
        factor_df = compute_alpha101_factors(panel, factor_names=factors)
    elif factor_set.lower() in {"gtja191", "alpha191"}:
        factor_df = compute_gtja191_alphas(panel, factor_names=factors)
    else:
        raise ValueError(f"不支持的因子集: {factor_set}")
    
    print(f"[3/4] 分析因子表现...")
    metrics_by_factor = {}
    for factor in factors:
        metrics_by_factor[factor] = analyze_factor(factor, panel, factor_df)
        ic_str = f"{metrics_by_factor[factor]['rank_ic_mean']:.4f}" if not np.isnan(metrics_by_factor[factor]['rank_ic_mean']) else "NaN"
        ir_str = f"{metrics_by_factor[factor]['rank_ic_ir']:.4f}" if not np.isnan(metrics_by_factor[factor]['rank_ic_ir']) else "NaN"
        cov_str = f"{metrics_by_factor[factor]['coverage_ratio']:.1%}"
        ls_str = f"{metrics_by_factor[factor]['long_short_mean']:.4f}" if not np.isnan(metrics_by_factor[factor]['long_short_mean']) else "NaN"
        print(f"  {factor}: IC={ic_str}, IR={ir_str}, 覆盖率={cov_str}, 多空收益={ls_str}")
    
    print(f"[4/4] 保存产物...")
    workspace = FactorLabWorkspaceConfig()
    workspace.ensure_directories()
    
    job_id = f"{factor_set}-real-{uuid4().hex[:10]}"
    
    frame_path = workspace.frame_path(factor_set, job_id)
    factor_df.to_csv(frame_path, index=False, encoding="utf-8")
    panel_path = workspace.frame_path(factor_set, f"{job_id}_panel")
    panel.to_csv(panel_path, index=False, encoding="utf-8")
    
    evaluation_report = {
        "library": factor_set_library_name(factor_set),
        "dataset": {
            "rows": int(len(panel)),
            "codes": int(panel["code"].nunique()),
            "dates": int(panel["date"].nunique()),
        },
        "summary": {
            "factor_count": len(factors),
            "sample_count": len(panel),
            "forward_return_col": "forward_return_1d",
            "metrics": metrics_by_factor,
        },
    }
    
    strategy_report = build_strategy_report(panel, factor_df, factors)
    
    evaluation_json_path = workspace.report_path(f"{job_id}_evaluation", suffix=".json")
    evaluation_json_path.write_text(json.dumps(evaluation_report, ensure_ascii=False, indent=2), encoding="utf-8")
    strategy_json_path = workspace.report_path(f"{job_id}_strategy", suffix=".json")
    strategy_json_path.write_text(json.dumps(strategy_report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    library = factor_set_library_name(factor_set)
    
    job = {
        "job_id": job_id,
        "library": library,
        "factor_set": factor_set,
        "status": "completed",
        "data_source": "quant_api",
        "generated_at": now_iso(),
        "requested_factors": factors,
        "dataset": {
            "n_dates_requested": int(panel["date"].nunique()),
            "n_symbols_requested": len(symbols),
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
        },
        "summary": {
            "evaluation": metrics_by_factor,
            "strategy": {name: strategy_report["factors"][name]["summary"] for name in factors if name in strategy_report["factors"]},
        },
    }
    
    workspace.job_path(job_id).write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    
    simple_results = {}
    for factor, metrics in metrics_by_factor.items():
        simple_results[factor] = {
            "factor_name": factor,
            "coverage": metrics.get("coverage_ratio", 0) * 100,
            "ic_mean": metrics.get("pearson_ic_mean"),
            "ic_ir": metrics.get("rank_ic_ir"),
            "rank_ic_mean": metrics.get("rank_ic_mean"),
            "rank_ic_ir": metrics.get("rank_ic_ir"),
            "long_short_mean": metrics.get("long_short_mean"),
            "long_short_sharpe": strategy_report["factors"].get(factor, {}).get("summary", {}).get("sharpe"),
            "long_short_max_drawdown": strategy_report["factors"].get(factor, {}).get("summary", {}).get("max_drawdown"),
            "turnover": strategy_report["factors"].get(factor, {}).get("summary", {}).get("mean_turnover"),
            "group_returns_mean": {},
        }
    
    summary = {
        "job_id": job_id,
        "factor_set": factor_set,
        "factors": factors,
        "symbols": symbols,
        "start_date": start_date,
        "end_date": end_date,
        "total_records": len(panel),
        "num_symbols": panel["code"].nunique(),
        "results": simple_results,
        "output_dir": str(frame_path.parent),
    }
    
    return summary


def factor_set_library_name(factor_set: str) -> str:
    lower = factor_set.lower()
    if lower in {"wq101", "alpha101"}:
        return "Alpha101"
    if lower in {"gtja191", "alpha191"}:
        return "GTJA191"
    if lower == "quant_api":
        return "QuantAPI"
    return factor_set.capitalize()


def main():
    parser = argparse.ArgumentParser(description="Quant API 真实数据因子研究")
    parser.add_argument("--factors", default="ret_1m,roe_ttm", help="逗号分隔的因子名称")
    parser.add_argument("--symbols", default="000001.SZ,000002.SZ,000004.SZ,000005.SZ,000006.SZ", help="逗号分隔的股票代码")
    parser.add_argument("--start-date", default="2023-01-01", help="开始日期")
    parser.add_argument("--end-date", default="2024-01-01", help="结束日期")
    parser.add_argument("--factor-set", choices=["alpha101", "gtja191", "quant_api"], default="quant_api", help="因子集")
    
    args = parser.parse_args()
    
    factors = [f.strip() for f in args.factors.split(",") if f.strip()]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    
    if args.factor_set == "quant_api" and factors == ["ret_1m", "roe_ttm"]:
        factors = QUANT_API_33_FACTORS
    
    summary = run_research(factors, symbols, args.start_date, args.end_date, args.factor_set)
    
    print("\n" + "="*60)
    print("研究结果汇总")
    print("="*60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()