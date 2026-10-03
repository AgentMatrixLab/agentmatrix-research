from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml

from research_core.factor_lab.panel_source import load_validation_panel
from research_core.factor_lab.precomputed_factors import (
    PrecomputedFactorError,
    PrecomputedFactorSet,
    load_precomputed_factors,
    perturbation_factor_name,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SEGMENTS = ("train", "oos")


class MissingDataError(RuntimeError):
    def __init__(self, message: str, *, missing_fields: Iterable[str] = (), details: dict[str, Any] | None = None):
        super().__init__(message)
        self.missing_fields = sorted(set(missing_fields))
        self.details = details or {}


@dataclass(frozen=True)
class ValidationPaths:
    root: Path
    report: Path
    result: Path
    manifest: Path
    needs_human: Path


def load_validation_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Validation config must be a mapping: {config_path}")
    required = {
        "data",
        "split",
        "factor",
        "forward_returns",
        "styles",
        "portfolio",
        "perturbation",
        "gates",
        "statistics",
        "release",
        "output",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Validation config is missing sections: {missing}")
    return payload


def _canonical_json(payload: Any) -> str:
    return json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(payload: bytes | str) -> str:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(raw).hexdigest()


def _json_safe(value: Any, *, precision: int = 12) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item, precision=precision) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, precision=precision) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return round(number, precision) if math.isfinite(number) else None
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _frame_hash(frame: pd.DataFrame) -> str:
    columns = ["date", "code", *sorted(column for column in frame.columns if column not in {"date", "code"})]
    ordered = frame[columns].copy()
    ordered = ordered.sort_values(["date", "code"]).reset_index(drop=True)
    for column in ordered.columns:
        if pd.api.types.is_datetime64_any_dtype(ordered[column]):
            ordered[column] = ordered[column].dt.strftime("%Y-%m-%d")
    header = _canonical_json({"columns": list(ordered.columns), "dtypes": [str(dtype) for dtype in ordered.dtypes]})
    row_hashes = pd.util.hash_pandas_object(ordered, index=False, categorize=True).values.tobytes()
    return _sha256(header.encode("utf-8") + row_hashes)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _paths(config: dict[str, Any], factor_id: str, *, segment: str = "oos") -> ValidationPaths:
    output = config["output"]
    root = PROJECT_ROOT / output["root"] / factor_id
    if segment != "oos":
        root = root / segment
    return ValidationPaths(
        root=root,
        report=root / output["report_filename"],
        result=root / output["result_filename"],
        manifest=root / output["manifest_filename"],
        needs_human=root / output["needs_human_filename"],
    )


def _require_factor_coverage(precomputed: PrecomputedFactorSet, config: dict[str, Any]) -> None:
    """The factor export must cover the frozen train..oos range; gaps are not silently filled."""
    span_start, span_end = precomputed.coverage_span()
    split = config["split"]
    required_start = date.fromisoformat(str(split["train_start"]))
    required_end = date.fromisoformat(str(split["oos_end"]))
    if span_start > required_start or span_end < required_end:
        raise PrecomputedFactorError(
            "precomputed factor file does not cover the frozen train..oos range "
            f"(file {span_start}..{span_end}, required {required_start}..{required_end})"
        )


def _write_json(path: Path, payload: dict[str, Any], *, precision: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload, precision=precision), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _normalize_index_frame(frame: pd.DataFrame, value_name: str | None = None) -> pd.DataFrame:
    normalized = frame.reset_index()
    rename = {"order_book_id": "code", "tradedate": "date", "datetime": "date"}
    normalized = normalized.rename(columns=rename)
    if "date" not in normalized.columns or "code" not in normalized.columns:
        raise MissingDataError(
            "RQData response is missing its date/code index.",
            missing_fields=["date", "code"],
            details={"columns": list(normalized.columns)},
        )
    if value_name and value_name not in normalized.columns and len(normalized.columns) == 3:
        candidate = next(column for column in normalized.columns if column not in {"date", "code"})
        normalized = normalized.rename(columns={candidate: value_name})
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.normalize()
    normalized["code"] = normalized["code"].astype(str)
    return normalized


def _wide_boolean_to_long(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    if frame.index.name is None:
        frame.index.name = "date"
    result = frame.rename_axis("date").reset_index().melt(id_vars="date", var_name="code", value_name=value_name)
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    result["code"] = result["code"].astype(str)
    result[value_name] = result[value_name].astype(bool)
    return result


class RQDataPanelLoader:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def load(self, factor_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
        data_config = self.config["data"]
        request = {
            "provider": data_config["provider"],
            "universe": data_config["universe"],
            "frequency": data_config["frequency"],
            "adjust_type": data_config["adjust_type"],
            "warmup_start": data_config["warmup_start"],
            "validation_end": data_config["validation_end"],
            "price_fields": data_config["price_fields"],
            "limit_up_field": data_config["limit_up_field"],
            "limit_down_field": data_config["limit_down_field"],
            "turnover_field": data_config["turnover_field"],
            "shares_field": data_config["shares_field"],
            "factor_id": factor_id,
        }
        cache_path = PROJECT_ROOT / data_config["cache_dir"] / f"{_sha256(_canonical_json(request))}.pkl"
        if data_config["cache_enabled"] and cache_path.exists():
            cached = pd.read_pickle(cache_path)
            return cached, {"provider": "rqdata", "cache_hit": True, "fallback_reason": None}

        try:
            import rqdatac

            rqdatac.init()
        except Exception as exc:
            raise MissingDataError(
                "RQData initialization failed. Check local environment credentials and entitlement.",
                details={"error_type": type(exc).__name__},
            ) from exc

        metadata = rqdatac.all_instruments(type="CS")
        required_metadata = list(data_config["required_metadata_fields"])
        missing_metadata = sorted(set(required_metadata) - set(metadata.columns))
        if missing_metadata:
            raise MissingDataError("RQData instrument metadata is incomplete.", missing_fields=missing_metadata)

        metadata = metadata[list(required_metadata)].copy()
        metadata["listed_date"] = pd.to_datetime(metadata["listed_date"], errors="coerce")
        metadata["de_listed_date"] = pd.to_datetime(metadata["de_listed_date"], errors="coerce")
        end = pd.Timestamp(data_config["validation_end"])
        start = pd.Timestamp(data_config["warmup_start"])
        metadata = metadata[
            metadata["listed_date"].notna()
            & (metadata["listed_date"] <= end)
            & (metadata["de_listed_date"].isna() | (metadata["de_listed_date"] >= start))
        ].copy()
        excluded_prefixes = tuple(str(value) for value in data_config["excluded_security_prefixes"])
        metadata = metadata[~metadata["trading_code"].astype(str).str.startswith(excluded_prefixes)].copy()
        codes = sorted(metadata["order_book_id"].astype(str).unique())
        if not codes:
            raise MissingDataError("RQData returned an empty all-A universe.")

        frames: list[pd.DataFrame] = []
        turnover_error: str | None = None

        for batch in _batches(codes, int(data_config["batch_size"])):
            try:
                prices = rqdatac.get_price(
                    batch,
                    start_date=data_config["warmup_start"],
                    end_date=data_config["validation_end"],
                    frequency=data_config["frequency"],
                    fields=data_config["price_fields"],
                    adjust_type=data_config["adjust_type"],
                    skip_suspended=False,
                    expect_df=True,
                )
                batch_panel = _normalize_index_frame(prices)
                shares = rqdatac.get_shares(
                    batch,
                    start_date=data_config["warmup_start"],
                    end_date=data_config["validation_end"],
                    fields=data_config["shares_field"],
                    expect_df=True,
                )
                batch_panel = batch_panel.merge(
                    _normalize_index_frame(shares, data_config["shares_field"]),
                    on=["date", "code"],
                    how="left",
                )
                batch_panel = batch_panel.merge(
                    _wide_boolean_to_long(
                        rqdatac.is_st_stock(batch, data_config["warmup_start"], data_config["validation_end"]),
                        "is_st",
                    ),
                    on=["date", "code"],
                    how="left",
                )
                batch_panel = batch_panel.merge(
                    _wide_boolean_to_long(
                        rqdatac.is_suspended(batch, data_config["warmup_start"], data_config["validation_end"]),
                        "is_suspended",
                    ),
                    on=["date", "code"],
                    how="left",
                )
                if factor_id == self.config["factor"]["primary"] and turnover_error is None:
                    try:
                        turnover = rqdatac.get_turnover_rate(
                            batch,
                            data_config["warmup_start"],
                            data_config["validation_end"],
                            fields=data_config["turnover_field"],
                            expect_df=True,
                        )
                        batch_panel = batch_panel.merge(
                            _normalize_index_frame(turnover, "turnover_rate"),
                            on=["date", "code"],
                            how="left",
                        )
                    except Exception as exc:
                        turnover_error = type(exc).__name__
                frames.append(batch_panel)
            except MissingDataError:
                raise
            except Exception as exc:
                raise MissingDataError(
                    "RQData panel fetch failed. Check data entitlement and requested date coverage.",
                    details={"error_type": type(exc).__name__},
                ) from exc

        panel = pd.concat(frames, ignore_index=True)
        if turnover_error and "turnover_rate" in panel.columns:
            panel = panel.drop(columns=["turnover_rate"])
        metadata = metadata.rename(columns={"order_book_id": "code"})
        panel = panel.merge(metadata, on="code", how="left", validate="many_to_one")
        panel = panel.sort_values(["date", "code"]).drop_duplicates(["date", "code"], keep="last").reset_index(drop=True)

        if data_config["cache_enabled"]:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            panel.to_pickle(cache_path)
        return panel, {
            "provider": "rqdata",
            "cache_hit": False,
            "fallback_reason": f"turnover_rate_unavailable:{turnover_error}" if turnover_error else None,
        }


def _batches(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], context: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise MissingDataError(f"Missing fields for {context}.", missing_fields=missing, details={"context": context})


def _eligible_panel(panel: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    data_config = config["data"]
    required = [
        "date",
        "code",
        *data_config["price_fields"],
        data_config["shares_field"],
        "listed_date",
        "de_listed_date",
        "is_st",
        "is_suspended",
    ]
    _require_columns(panel, required, "universe filtering")
    clean = panel.copy()
    clean["date"] = pd.to_datetime(clean["date"]).dt.normalize()
    clean["listed_date"] = pd.to_datetime(clean["listed_date"], errors="coerce")
    clean["de_listed_date"] = pd.to_datetime(clean["de_listed_date"], errors="coerce")
    age = (clean["date"] - clean["listed_date"]).dt.days
    eligible = (
        clean["listed_date"].notna()
        & (age >= int(data_config["minimum_listing_days"]))
        & (clean["de_listed_date"].isna() | (clean["date"] <= clean["de_listed_date"]))
        & ~clean["is_st"].astype(bool)
        & ~clean["is_suspended"].astype(bool)
        & (pd.to_numeric(clean["volume"], errors="coerce") > 0)
    )
    clean = clean.loc[eligible].copy()
    numeric_columns = [*data_config["price_fields"], data_config["shares_field"]]
    for column in numeric_columns:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    limit_up = data_config["limit_up_field"]
    limit_down = data_config["limit_down_field"]
    clean = clean[
        clean[limit_up].notna()
        & clean[limit_down].notna()
        & (clean["close"] < clean[limit_up])
        & (clean["close"] > clean[limit_down])
    ].copy()
    clean = clean.sort_values(["code", "date"]).reset_index(drop=True)
    if clean.empty:
        raise MissingDataError("No rows remain after all-A eligibility filters.")
    return clean


def _rolling_factor(panel: pd.DataFrame, factor_id: str, config: dict[str, Any], *, window: int | None = None) -> pd.Series:
    definitions = config["factor"]["definitions"]
    if factor_id not in definitions:
        raise ValueError(f"Unsupported deterministic factor: {factor_id}")
    definition = definitions[factor_id]
    source = definition["source_field"]
    _require_columns(panel, [source], factor_id)
    selected_window = int(window or definition["window"])
    min_periods = int(math.ceil(selected_window * float(definition["minimum_period_ratio"])))
    source_values = pd.to_numeric(panel[source], errors="coerce")
    if definition["transform"] == "negative_pct_change":
        _require_columns(panel, ["date", "code", "is_suspended"], factor_id)
        ordered = panel.reset_index(drop=True).copy()
        ordered["date"] = pd.to_datetime(ordered["date"]).dt.normalize()
        ordered["_source_value"] = pd.to_numeric(ordered[source], errors="coerce")
        ordered["_row_position"] = np.arange(len(ordered), dtype=np.int64)
        ordered = ordered.sort_values(["code", "date"], kind="mergesort")
        ordered["_session_position"] = pd.factorize(ordered["date"], sort=True)[0]
        grouped = ordered.groupby("code", sort=False)
        previous_close = grouped["_source_value"].shift(selected_window)
        previous_position = grouped["_session_position"].shift(selected_window)
        consecutive_sessions = (
            ordered["_session_position"] - previous_position == selected_window
        )
        valid_observation = (
            ordered["_source_value"].notna()
            & (ordered["_source_value"] > 0)
            & ordered["is_suspended"].eq(False)
        )
        valid_window = (
            valid_observation.groupby(ordered["code"], sort=False)
            .rolling(selected_window + 1, min_periods=selected_window + 1)
            .sum()
            .reset_index(level=0, drop=True)
            .sort_index()
            .eq(selected_window + 1)
        )
        factor = -(ordered["_source_value"] / previous_close - 1.0)
        factor = factor.where(consecutive_sessions & valid_window)
        return pd.Series(
            factor.to_numpy()[np.argsort(ordered["_row_position"].to_numpy())],
            index=panel.reset_index(drop=True).index,
            dtype=float,
        )

    rolled = source_values.groupby(panel["code"], sort=False).rolling(selected_window, min_periods=min_periods).mean()
    rolled = rolled.reset_index(level=0, drop=True).sort_index()
    if definition["transform"] == "rolling_mean_log":
        rolled = np.log(rolled.where(rolled > 0))
    elif definition["transform"] != "rolling_mean":
        raise ValueError(f"Unsupported factor transform: {definition['transform']}")
    return rolled.replace([np.inf, -np.inf], np.nan)


def _factor_lookup(
    panel: pd.DataFrame,
    factor_id: str,
    config: dict[str, Any],
    *,
    window: int | None = None,
) -> pd.Series:
    source_panel = panel.reset_index(drop=True).copy()
    source_panel["date"] = pd.to_datetime(source_panel["date"]).dt.normalize()
    values = _rolling_factor(source_panel, factor_id, config, window=window)
    keys = pd.MultiIndex.from_frame(source_panel[["date", "code"]])
    return pd.Series(values.to_numpy(), index=keys)


def _map_factor_values(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    keys = pd.MultiIndex.from_frame(
        pd.DataFrame(
            {
                "date": pd.to_datetime(frame["date"]).dt.normalize().to_numpy(),
                "code": frame["code"].to_numpy(),
            }
        )
    )
    return pd.Series(values.reindex(keys).to_numpy(), index=frame.index, dtype=float)


def _build_styles(panel: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    styles = config["styles"]
    shares_field = styles["size_shares_field"]
    _require_columns(panel, ["close", "total_turnover", shares_field], "style factors")
    frame = panel.sort_values(["code", "date"]).copy()
    grouped = frame.groupby("code", sort=False)
    returns = grouped["close"].pct_change(fill_method=None)
    frame["size"] = np.log((frame["close"] * frame[shares_field]).where(lambda value: value > 0))
    frame["momentum"] = grouped["close"].pct_change(
        periods=int(styles["momentum_window"]),
        fill_method=None,
    )
    frame["volatility"] = (
        returns.groupby(frame["code"], sort=False)
        .rolling(
            int(styles["volatility_window"]),
            min_periods=int(styles["volatility_minimum_periods"]),
        )
        .std()
        .reset_index(level=0, drop=True)
        .sort_index()
    )
    liquidity = (
        frame["total_turnover"]
        .groupby(frame["code"], sort=False)
        .rolling(
            int(styles["liquidity_window"]),
            min_periods=int(styles["liquidity_minimum_periods"]),
        )
        .mean()
        .reset_index(level=0, drop=True)
        .sort_index()
    )
    frame["liquidity"] = np.log(liquidity.where(liquidity > 0))
    return frame


def _attach_forward_returns(frame: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    enriched = frame.sort_values(["code", "date"]).copy()
    grouped = enriched.groupby("code", sort=False)
    for horizon in horizons:
        future_price = grouped["close"].shift(-int(horizon))
        future_date = grouped["date"].shift(-int(horizon))
        enriched[f"forward_return_{horizon}d"] = future_price / enriched["close"] - 1.0
        enriched[f"target_date_{horizon}d"] = future_date
    return enriched


def _bounded_period(frame: pd.DataFrame, start: str, end: str, horizons: list[int]) -> pd.DataFrame:
    period = frame[(frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))].copy()
    boundary = pd.Timestamp(end)
    for horizon in horizons:
        target_col = f"target_date_{horizon}d"
        return_col = f"forward_return_{horizon}d"
        period.loc[period[target_col] > boundary, return_col] = np.nan
    return period


def _daily_rank_ic(
    frame: pd.DataFrame,
    factor_col: str,
    return_col: str,
    *,
    minimum_cross_section: int,
) -> pd.Series:
    values: dict[pd.Timestamp, float] = {}
    for date, group in frame[["date", factor_col, return_col]].dropna().groupby("date", sort=True):
        if len(group) < minimum_cross_section:
            continue
        values[pd.Timestamp(date)] = float(group[factor_col].corr(group[return_col], method="spearman"))
    return pd.Series(values, dtype=float).sort_index()


def _ic_summary(series: pd.Series, ddof: int) -> dict[str, Any]:
    clean = series.replace([np.inf, -np.inf], np.nan).dropna()
    mean = float(clean.mean()) if len(clean) else float("nan")
    std = float(clean.std(ddof=ddof)) if len(clean) > ddof else float("nan")
    t_stat = mean / (std / math.sqrt(len(clean))) if len(clean) > ddof and std > 0 else float("nan")
    yearly: dict[str, Any] = {}
    if len(clean):
        for year, values in clean.groupby(clean.index.year):
            year_std = float(values.std(ddof=ddof)) if len(values) > ddof else float("nan")
            yearly[str(year)] = {
                "mean": float(values.mean()),
                "ic_ir": float(values.mean() / year_std) if year_std > 0 else float("nan"),
                "t_stat": float(values.mean() / (year_std / math.sqrt(len(values)))) if year_std > 0 else float("nan"),
                "days": int(len(values)),
            }
    return {
        "mean": mean,
        "ic_ir": float(mean / std) if std > 0 else float("nan"),
        "t_stat": t_stat,
        "days": int(len(clean)),
        "yearly": yearly,
    }


def _neutralize_styles(
    frame: pd.DataFrame,
    factor_col: str,
    style_fields: list[str],
    minimum_cross_section: int,
) -> tuple[pd.Series, pd.Series]:
    residual = pd.Series(np.nan, index=frame.index, dtype=float)
    r2 = pd.Series(dtype=float)
    r2_values: dict[pd.Timestamp, float] = {}
    columns = [factor_col, *style_fields]
    for date, group in frame[["date", *columns]].groupby("date", sort=True):
        valid = group[columns].dropna()
        if len(valid) < minimum_cross_section:
            continue
        y = valid[factor_col].astype(float)
        x = valid[style_fields].astype(float)
        std = x.std(ddof=0).replace(0, np.nan)
        x = ((x - x.mean()) / std).dropna(axis=1)
        if x.empty or len(valid) <= len(x.columns) + 1:
            continue
        matrix = np.column_stack([np.ones(len(x)), x.to_numpy()])
        beta, _, _, _ = np.linalg.lstsq(matrix, y.loc[x.index].to_numpy(), rcond=None)
        fitted = matrix @ beta
        errors = y.loc[x.index].to_numpy() - fitted
        residual.loc[x.index] = errors
        total = float(np.square(y.loc[x.index].to_numpy() - y.loc[x.index].mean()).sum())
        r2_values[pd.Timestamp(date)] = 1.0 - float(np.square(errors).sum()) / total if total > 0 else float("nan")
    r2 = pd.Series(r2_values, dtype=float).sort_index()
    return residual, r2


def _portfolio_metrics(
    frame: pd.DataFrame,
    factor_col: str,
    return_col: str,
    direction: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    portfolio = config["portfolio"]
    quantiles = int(portfolio["quantiles"])
    stride = int(portfolio["rebalance_stride"])
    cost = float(portfolio["cost"]["round_trip_total"])
    dates = sorted(frame["date"].dropna().unique())[::stride]
    rows: list[dict[str, Any]] = []
    previous_long: set[str] | None = None
    previous_short: set[str] | None = None
    for date in dates:
        group = frame.loc[frame["date"] == date, ["code", factor_col, return_col]].dropna().copy()
        if len(group) < quantiles:
            continue
        group["_signal"] = direction * group[factor_col]
        group["_bucket"] = pd.qcut(
            group["_signal"].rank(method="first"),
            quantiles,
            labels=False,
            duplicates="drop",
        )
        long_codes = set(group.loc[group["_bucket"] == quantiles - 1, "code"])
        short_codes = set(group.loc[group["_bucket"] == 0, "code"])
        if not long_codes or not short_codes:
            continue
        gross = float(group.loc[group["code"].isin(long_codes), return_col].mean())
        gross -= float(group.loc[group["code"].isin(short_codes), return_col].mean())
        if previous_long is None or previous_short is None:
            turnover = 1.0
        else:
            long_turnover = 1.0 - len(long_codes & previous_long) / max(len(previous_long), 1)
            short_turnover = 1.0 - len(short_codes & previous_short) / max(len(previous_short), 1)
            turnover = (long_turnover + short_turnover) / 2.0
        rows.append({"date": pd.Timestamp(date), "gross_return": gross, "turnover": turnover, "net_return": gross - turnover * cost})
        previous_long, previous_short = long_codes, short_codes

    result = pd.DataFrame(rows)
    if result.empty:
        raise MissingDataError("No valid OOS portfolio observations were produced.")
    net = result["net_return"]
    periods_per_year = float(portfolio["annual_trading_days"]) / stride
    annualized = float((np.prod(1.0 + net) ** (periods_per_year / len(net))) - 1.0) if (net > -1.0).all() else -1.0
    annualized_vol = float(net.std(ddof=int(config["statistics"]["standard_deviation_ddof"])) * math.sqrt(periods_per_year))
    nav = (1.0 + net).cumprod()
    max_drawdown = float((nav / nav.cummax() - 1.0).min())
    ratio = abs(max_drawdown) / annualized_vol if annualized_vol > 0 else float("inf")
    return {
        "observations": int(len(result)),
        "gross_annualized": float((np.prod(1.0 + result["gross_return"]) ** (periods_per_year / len(result))) - 1.0),
        "net_annualized": annualized,
        "annualized_volatility": annualized_vol,
        "max_drawdown": max_drawdown,
        "dd_vol_ratio": ratio,
        "mean_turnover": float(result["turnover"].mean()),
        "round_trip_cost": cost,
    }


def _gate(name: str, passed: bool, actual: Any, threshold: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "threshold": threshold}


def _training_segment_result(
    train: pd.DataFrame,
    clean: pd.DataFrame,
    config: dict[str, Any],
    *,
    requested_factor: str,
    selected_factor: str,
    fallback_reason: str | None,
    source_metadata: dict[str, Any] | None,
    split: dict[str, Any],
    scope: list[str],
) -> dict[str, Any]:
    """Training-period statistics only.

    This path deliberately never touches the sealed out-of-sample window: it exists so that a
    cluster representative can be picked without inspecting OOS results. No gate is evaluated
    here and no OOS metric is computed or written.
    """
    release = config["release"]
    stats_config = config["statistics"]
    minimum_cross_section = int(stats_config["minimum_ic_cross_section"])
    ddof = int(stats_config["standard_deviation_ddof"])
    horizons = [int(value) for value in config["forward_returns"]["horizons"]]
    primary_horizon = int(config["forward_returns"]["primary_horizon"])
    primary_return = f"forward_return_{primary_horizon}d"

    rank_ic: dict[str, Any] = {}
    for horizon in horizons:
        series = _daily_rank_ic(
            train,
            "factor_value",
            f"forward_return_{horizon}d",
            minimum_cross_section=minimum_cross_section,
        )
        rank_ic[f"{horizon}d"] = _ic_summary(series, ddof)
    primary_mean = rank_ic[f"{primary_horizon}d"]["mean"]
    if not math.isfinite(float(primary_mean)):
        raise MissingDataError("Training period produced no valid RankIC observations.")

    coverage_by_date = train.groupby("date")["factor_value"].apply(
        lambda values: float(values.notna().mean())
    )
    coverage_actual = float(coverage_by_date.mean()) if len(coverage_by_date) else float("nan")
    return {
        "status": "train_only",
        "segment": "train",
        "requested_factor": requested_factor,
        "factor_id": selected_factor,
        "fallback_reason": fallback_reason,
        "release_classification": release["mode"],
        "license_checked": bool(release["license_checked"]),
        "scope": list(scope),
        "data": {
            "provider": (source_metadata or {}).get("provider", "provided_panel"),
            "universe": config["data"]["universe"],
            "frequency": config["data"]["frequency"],
            "adjust_type": config["data"]["adjust_type"],
            "eligible_rows": int(len(clean)),
            "eligible_codes": int(clean["code"].nunique()),
            "eligible_dates": int(clean["date"].nunique()),
        },
        "training": {
            "direction": 1.0 if float(primary_mean) >= 0 else -1.0,
            "primary_rank_ic_mean": primary_mean,
            "statistics_scope": [split["train_start"], split["train_end"]],
        },
        "train_rank_ic": rank_ic,
        "coverage": {
            "mean_daily_coverage": coverage_actual,
            "minimum_daily_coverage": float(coverage_by_date.min()) if len(coverage_by_date) else float("nan"),
        },
        "gates": [],
        "failed_gates": [],
        "note": (
            "training segment only: no out-of-sample statistic is computed, and no gate is "
            "evaluated. Not usable as factor-validity evidence."
        ),
    }


def validate_panel(
    panel: pd.DataFrame,
    requested_factor: str,
    config: dict[str, Any],
    *,
    source_metadata: dict[str, Any] | None = None,
    precomputed: PrecomputedFactorSet | None = None,
    segment: str = "oos",
    base_window_override: int | None = None,
) -> tuple[dict[str, Any], str]:
    if segment not in SEGMENTS:
        raise ValueError(f"segment must be one of {SEGMENTS}, got {segment!r}")
    release = config["release"]
    if release["mode"] == release["external_mode"] and not bool(release["license_checked"]):
        raise MissingDataError(
            "External release is blocked until data licensing is explicitly checked.",
            details={"release_mode": release["mode"], "license_checked": False},
        )

    costs = config["portfolio"]["cost"]
    component_total = (
        float(costs["commission_per_side"]) * 2.0
        + float(costs["stamp_tax_sell"])
        + float(costs["impact_per_side"]) * 2.0
    )
    tolerance = float(config["statistics"]["numeric_tolerance"])
    if not math.isclose(component_total, float(costs["round_trip_total"]), rel_tol=0.0, abs_tol=tolerance):
        raise ValueError("Configured transaction-cost components do not equal round_trip_total.")

    selected_factor = requested_factor
    fallback_reason = (source_metadata or {}).get("fallback_reason")
    if (
        precomputed is None
        and requested_factor == config["factor"]["primary"]
        and "turnover_rate" not in panel.columns
    ):
        selected_factor = config["factor"]["fallback"]
        fallback_reason = fallback_reason or "turnover_rate_field_missing"

    clean = _eligible_panel(panel, config)
    if precomputed is not None:
        # Factor values come from a validated local export; the pipeline only maps them
        # onto the eligible panel. No transform, threshold or split logic is bypassed.
        clean["factor_value"] = _map_factor_values(clean, precomputed.require(selected_factor))
    elif config["factor"]["definitions"][selected_factor]["transform"] == "negative_pct_change":
        clean["factor_value"] = _map_factor_values(
            clean,
            _factor_lookup(panel, selected_factor, config),
        )
    else:
        clean["factor_value"] = _rolling_factor(clean, selected_factor, config)
    clean = _build_styles(clean, config)
    horizons = [int(value) for value in config["forward_returns"]["horizons"]]
    enriched = _attach_forward_returns(clean, horizons)
    split = config["split"]
    train = _bounded_period(enriched, split["train_start"], split["train_end"], horizons)
    if segment == "train":
        if train.empty:
            raise MissingDataError(
                "Configured training period has no eligible rows.",
                details={"train_rows": len(train)},
            )
        train_result = _training_segment_result(
            train,
            clean,
            config,
            requested_factor=requested_factor,
            selected_factor=selected_factor,
            fallback_reason=fallback_reason,
            source_metadata=source_metadata,
            split=split,
            scope=[split["train_start"], split["train_end"]],
        )
        return train_result, _frame_hash(panel)
    oos = _bounded_period(enriched, split["oos_start"], split["oos_end"], horizons)
    if train.empty or oos.empty:
        raise MissingDataError(
            "Configured train or sealed OOS period has no eligible rows.",
            details={"train_rows": len(train), "oos_rows": len(oos)},
        )

    stats_config = config["statistics"]
    minimum_cross_section = int(stats_config["minimum_ic_cross_section"])
    ddof = int(stats_config["standard_deviation_ddof"])
    primary_horizon = int(config["forward_returns"]["primary_horizon"])
    primary_return = f"forward_return_{primary_horizon}d"
    train_ic_raw = _daily_rank_ic(
        train,
        "factor_value",
        primary_return,
        minimum_cross_section=minimum_cross_section,
    )
    train_mean = float(train_ic_raw.mean()) if len(train_ic_raw) else float("nan")
    if not math.isfinite(train_mean):
        raise MissingDataError("Training period produced no valid RankIC observations.")
    direction = 1.0 if train_mean >= 0 else -1.0

    rank_ic: dict[str, Any] = {}
    oos_ic_series: dict[int, pd.Series] = {}
    for horizon in horizons:
        series = _daily_rank_ic(
            oos,
            "factor_value",
            f"forward_return_{horizon}d",
            minimum_cross_section=minimum_cross_section,
        )
        oos_ic_series[horizon] = series
        rank_ic[f"{horizon}d"] = _ic_summary(series * direction, ddof)

    coverage_by_date = oos.groupby("date")["factor_value"].apply(lambda values: float(values.notna().mean()))
    coverage_actual = float(coverage_by_date.mean()) if len(coverage_by_date) else float("nan")

    style_fields = list(config["styles"]["fields"])
    residual, style_r2 = _neutralize_styles(
        oos,
        "factor_value",
        style_fields,
        int(config["styles"]["minimum_cross_section"]),
    )
    oos = oos.copy()
    oos["residual_factor"] = residual
    residual_series = _daily_rank_ic(
        oos,
        "residual_factor",
        primary_return,
        minimum_cross_section=minimum_cross_section,
    )
    residual_summary = _ic_summary(residual_series * direction, ddof)
    raw_primary_mean = rank_ic[f"{primary_horizon}d"]["mean"]
    raw_primary_unoriented_mean = float(oos_ic_series[primary_horizon].mean())
    residual_mean = residual_summary["mean"]
    retention = abs(residual_mean / raw_primary_mean) if raw_primary_mean and math.isfinite(raw_primary_mean) else 0.0
    residual_sign_ok = bool(raw_primary_mean * residual_mean > 0)

    portfolio_metrics = _portfolio_metrics(oos, "factor_value", primary_return, direction, config)

    perturbation: dict[str, Any] = {}
    base_sign = int(np.sign(raw_primary_unoriented_mean))
    perturbation_passed = base_sign != 0
    base_window = (
        int(base_window_override)
        if base_window_override is not None
        else (
            precomputed.base_window(selected_factor)
            if precomputed is not None
            else int(config["factor"]["definitions"][selected_factor]["window"])
        )
    )
    unmeasured_variants: list[str] = []
    for multiplier in config["perturbation"]["multipliers"]:
        window = max(1, int(round(base_window * float(multiplier))))
        perturbed = enriched.copy()
        if precomputed is not None:
            # Ruling (接龙10, 扰动 A+B): the export should carry "<factor_id>|window=<w>".
            # When it does not, the gate is recorded as unmeasured and therefore NOT passed;
            # it must never abort the run and must never be treated as a pass.
            variant_values = precomputed.optional_perturbation(selected_factor, window)
            if variant_values is None:
                missing_name = perturbation_factor_name(selected_factor, window)
                unmeasured_variants.append(missing_name)
                perturbation[str(multiplier)] = {
                    "window": window,
                    "rank_ic_mean": None,
                    "sign_matches": False,
                    "measured": False,
                    "missing_factor_name": missing_name,
                }
                perturbation_passed = False
                continue
            perturbed["perturbed_factor"] = _map_factor_values(perturbed, variant_values)
        elif config["factor"]["definitions"][selected_factor]["transform"] == "negative_pct_change":
            perturbed["perturbed_factor"] = _map_factor_values(
                perturbed,
                _factor_lookup(panel, selected_factor, config, window=window),
            )
        else:
            perturbed["perturbed_factor"] = _rolling_factor(clean, selected_factor, config, window=window)
        perturbed_oos = _bounded_period(perturbed, split["oos_start"], split["oos_end"], horizons)
        series = _daily_rank_ic(
            perturbed_oos,
            "perturbed_factor",
            primary_return,
            minimum_cross_section=minimum_cross_section,
        )
        mean = float(series.mean()) if len(series) else float("nan")
        sign_matches = bool(math.isfinite(mean) and int(np.sign(mean)) == base_sign)
        perturbation[str(multiplier)] = {"window": window, "rank_ic_mean": mean, "sign_matches": sign_matches}
        perturbation_passed = perturbation_passed and sign_matches

    gate_config = config["gates"]
    perturbation_actual: Any = perturbation
    perturbation_threshold: dict[str, Any] = {"require_same_rank_ic_sign": True}
    if unmeasured_variants:
        perturbation_actual = {
            "measured": False,
            "unmeasured_variants": sorted(set(unmeasured_variants)),
            "reason": (
                "the precomputed factor export does not provide the perturbed parameterization; "
                "per ruling A+B this gate is not measured and therefore not passed"
            ),
            "variants": perturbation,
        }
        perturbation_threshold = {
            "require_same_rank_ic_sign": True,
            "unmeasured_counts_as": "not_passed",
        }
    rank_threshold = gate_config["rank_ic"]
    primary_ic = rank_ic[f"{primary_horizon}d"]
    valid_train_labels = train[primary_return].notna()
    max_train_target = train.loc[valid_train_labels, f"target_date_{primary_horizon}d"].dropna().max()
    oos_sealed = bool(
        train["date"].max() <= pd.Timestamp(split["train_end"])
        and oos["date"].min() >= pd.Timestamp(split["oos_start"])
        and (pd.isna(max_train_target) or max_train_target <= pd.Timestamp(split["train_end"]))
    )
    mean_style_r2 = float(style_r2.mean()) if len(style_r2) else float("nan")
    gates = {
        "coverage": _gate(
            "coverage",
            coverage_actual >= float(gate_config["coverage"]["minimum_daily_ratio"]),
            {"mean_daily_coverage": coverage_actual, "minimum_daily_coverage": float(coverage_by_date.min())},
            gate_config["coverage"],
        ),
        "rank_ic": _gate(
            "rank_ic",
            abs(primary_ic["mean"]) >= float(rank_threshold["minimum_abs_mean"])
            and abs(primary_ic["t_stat"]) >= float(rank_threshold["minimum_abs_t_stat"]),
            {"horizon": primary_horizon, **primary_ic},
            rank_threshold,
        ),
        "oos_seal": _gate(
            "oos_seal",
            oos_sealed,
            {
                "train_range": [str(train["date"].min().date()), str(train["date"].max().date())],
                "maximum_train_label_date": str(max_train_target.date()) if pd.notna(max_train_target) else None,
                "oos_range": [str(oos["date"].min().date()), str(oos["date"].max().date())],
            },
            split,
        ),
        "style_r2": _gate(
            "style_r2",
            math.isfinite(mean_style_r2) and mean_style_r2 <= float(gate_config["style_r2"]["maximum_mean"]),
            {"mean": mean_style_r2, "days": int(style_r2.notna().sum())},
            gate_config["style_r2"],
        ),
        "residual_ic": _gate(
            "residual_ic",
            residual_sign_ok and retention >= float(gate_config["residual_ic"]["minimum_retention"]),
            {
                "raw_rank_ic": raw_primary_mean,
                "residual_rank_ic": residual_mean,
                "retention": retention,
                "sign_matches": residual_sign_ok,
            },
            gate_config["residual_ic"],
        ),
        "cost_adjusted_return": _gate(
            "cost_adjusted_return",
            portfolio_metrics["net_annualized"] > float(gate_config["cost_adjusted_return"]["minimum_annualized"]),
            portfolio_metrics["net_annualized"],
            gate_config["cost_adjusted_return"],
        ),
        "dd_vol_ratio": _gate(
            "dd_vol_ratio",
            portfolio_metrics["dd_vol_ratio"] <= float(gate_config["dd_vol_ratio"]["maximum"]),
            portfolio_metrics["dd_vol_ratio"],
            gate_config["dd_vol_ratio"],
        ),
        "parameter_perturbation": _gate(
            "parameter_perturbation",
            perturbation_passed,
            perturbation_actual,
            perturbation_threshold,
        ),
    }
    ordered_gates = [gates[name] for name in gate_config["order"]]
    failed = [item for item in ordered_gates if not item["passed"]]
    status = "rejected" if failed else "validated"
    result = {
        "status": status,
        "requested_factor": requested_factor,
        "factor_id": selected_factor,
        "fallback_reason": fallback_reason,
        "release_classification": release["mode"],
        "license_checked": bool(release["license_checked"]),
        "data": {
            "provider": (source_metadata or {}).get("provider", "provided_panel"),
            "universe": config["data"]["universe"],
            "frequency": config["data"]["frequency"],
            "adjust_type": config["data"]["adjust_type"],
            "eligible_rows": int(len(clean)),
            "eligible_codes": int(clean["code"].nunique()),
            "eligible_dates": int(clean["date"].nunique()),
        },
        "training": {
            "direction": direction,
            "primary_rank_ic_mean": train_mean,
            "statistics_scope": [split["train_start"], split["train_end"]],
        },
        "rank_ic": rank_ic,
        "style": {
            "fields": style_fields,
            "r2_mean": mean_style_r2,
            "residual_ic": residual_summary,
            "retention": retention,
        },
        "portfolio": portfolio_metrics,
        "perturbation": perturbation,
        "gates": ordered_gates,
        "failed_gates": [item["name"] for item in failed],
    }
    # Provenance is recorded in run_manifest.json only, so that result_hash stays a pure
    # function of the numbers: the native transform and the precomputed channel must produce
    # the same result_hash for the same data.
    return result, _frame_hash(panel)


def _report_markdown(result: dict[str, Any]) -> str:
    failed = result["failed_gates"]
    if failed:
        first = next(item for item in result["gates"] if item["name"] == failed[0])
        first_line = f"status=rejected failed_gate={first['name']} actual={_canonical_json(first['actual'])}"
    else:
        first_line = f"status={result['status']}"
    lines = [
        first_line,
        "",
        f"# Deterministic Factor Validation: {result['factor_id']}",
        "",
        f"- Requested factor: `{result['requested_factor']}`",
        f"- Release classification: `{result['release_classification']}`",
        f"- License checked: `{str(result['license_checked']).lower()}`",
        f"- Data: `{result['data']['universe']}`, `{result['data']['frequency']}`, `{result['data']['adjust_type']}` adjusted",
        f"- Failed gates: `{', '.join(failed) if failed else 'none'}`",
        "",
        "| Gate | Status | Actual | Threshold |",
        "|---|---|---|---|",
    ]
    for gate in result["gates"]:
        lines.append(
            f"| {gate['name']} | {'passed' if gate['passed'] else 'rejected'} | "
            f"`{_canonical_json(gate['actual'])}` | `{_canonical_json(gate['threshold'])}` |"
        )
    lines.extend(
        [
            "",
            "## RankIC" if "rank_ic" in result else "## RankIC (training segment)",
            "",
            "| Horizon | Mean | IC_IR | t-stat | Days |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    rank_ic_table = result.get("rank_ic") or result.get("train_rank_ic") or {}
    for horizon, values in rank_ic_table.items():
        lines.append(
            f"| {horizon} | {_format_metric(values['mean'])} | {_format_metric(values['ic_ir'])} | "
            f"{_format_metric(values['t_stat'])} | {values['days']} |"
        )
    return "\n".join(lines) + "\n"


def _format_metric(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.6f}"


def execute_validation(
    factor_id: str,
    *,
    config_path: str | Path = PROJECT_ROOT / "configs" / "validation_gates.yaml",
    panel: pd.DataFrame | None = None,
    source_metadata: dict[str, Any] | None = None,
    factor_file: str | Path | None = None,
    factor_sidecar: str | Path | None = None,
    panel_file: str | Path | None = None,
    panel_sidecar: str | Path | None = None,
    precomputed: PrecomputedFactorSet | None = None,
    extra_manifest: dict[str, Any] | None = None,
    segment: str = "oos",
    base_window_override: int | None = None,
) -> dict[str, Any]:
    if segment not in SEGMENTS:
        raise ValueError(f"segment must be one of {SEGMENTS}, got {segment!r}")
    if panel is not None and panel_file is not None:
        raise ValueError("pass either panel or panel_file, not both")
    if precomputed is not None and factor_file is not None:
        raise ValueError("pass either factor_file or precomputed, not both")
    panel_provenance: dict[str, Any] = {}
    config = load_validation_config(config_path)
    paths = _paths(config, factor_id, segment=segment)
    paths.root.mkdir(parents=True, exist_ok=True)
    if paths.needs_human.exists():
        paths.needs_human.unlink()
    precision = int(config["output"]["float_precision"])

    precomputed_set = precomputed
    if factor_file is not None:
        # Contract violations raise PrecomputedFactorError, which is intentionally not
        # caught here: a bad factor export must stop the run, never degrade silently.
        precomputed_set = load_precomputed_factors(factor_file, sidecar_path=factor_sidecar)
    if precomputed_set is not None:
        _require_factor_coverage(precomputed_set, config)
        precomputed_set.require(factor_id)

    try:
        if panel is not None:
            loaded_panel = panel
            loaded_metadata = dict(source_metadata or {"provider": "provided_panel"})
        elif panel_file is not None:
            local_panel = load_validation_panel(panel_file, sidecar_path=panel_sidecar)
            loaded_panel = local_panel.frame
            loaded_metadata = {
                "provider": "local_panel_parquet",
                "panel_file": local_panel.path.name,
                "panel_sha256": local_panel.sha256,
                "price_basis": local_panel.price_basis,
            }
            loaded_metadata.update(source_metadata or {})
            panel_provenance = {
                "panel_file": local_panel.path.name,
                "panel_file_sha256": local_panel.sha256,
                "panel_price_basis": local_panel.price_basis,
            }
        else:
            loaded_panel, loaded_metadata = RQDataPanelLoader(config).load(factor_id)
        result, data_snapshot_hash = validate_panel(
            loaded_panel,
            factor_id,
            config,
            source_metadata=loaded_metadata,
            precomputed=precomputed_set,
            segment=segment,
            base_window_override=base_window_override,
        )
    except MissingDataError as exc:
        needs_human = {
            "status": "needs_human",
            "factor_id": factor_id,
            "reason": str(exc),
            "missing_fields": exc.missing_fields,
            "details": exc.details,
        }
        _write_json(paths.needs_human, needs_human, precision=precision)
        return {**needs_human, "artifact": str(paths.needs_human)}

    params_hash = _sha256(_canonical_json({"factor_id": factor_id, "config": config}))
    result_safe = _json_safe(result, precision=precision)
    result_hash = _sha256(_canonical_json(result_safe))
    manifest = {
        "data_snapshot_hash": data_snapshot_hash,
        "code_commit": _git_commit(),
        "params_hash": params_hash,
        "result_hash": result_hash,
        "segment": segment,
        "factor_source": "precomputed_parquet" if precomputed_set is not None else "pipeline_transform",
    }
    manifest.update(panel_provenance)
    manifest.update(extra_manifest or {})
    if precomputed_set is not None:
        manifest["factor_file"] = precomputed_set.path.name
        manifest["factor_file_sha256"] = precomputed_set.sha256
        manifest["factor_sidecar_data_start"] = precomputed_set.sidecar["data_start"]
        manifest["factor_sidecar_data_end"] = precomputed_set.sidecar["data_end"]
    constraints_path = PROJECT_ROOT / "constraints-rqsdk.txt"
    if constraints_path.is_file():
        manifest["constraints_file"] = constraints_path.name
        manifest["constraints_sha256"] = _sha256(constraints_path.read_bytes())
    _write_json(paths.result, result_safe, precision=precision)
    _write_json(paths.manifest, manifest, precision=precision)
    paths.report.write_text(_report_markdown(result_safe), encoding="utf-8")
    return {
        "status": result_safe["status"],
        "factor_id": result_safe["factor_id"],
        "failed_gates": result_safe["failed_gates"],
        "artifacts": {
            "report": str(paths.report),
            "result": str(paths.result),
            "manifest": str(paths.manifest),
        },
        "manifest": manifest,
    }
