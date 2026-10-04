"""Simulate a weight-based strategy into a NAV curve, with costs.

This is the piece between "we have target weights" and "here is the sample-out
result the client reads". `strategy_analytics.performance.analyze_window` already
computes the metrics from a `[{date, nav, benchmark}]` curve; what was missing was
producing that curve from real prices and trading it honestly.

Semantics that matter, stated because each is a place a backtest can lie:

* **Weights are targets at rebalance dates, not holdings.** Between rebalances the
  position is held as *shares*, so weights drift with prices. Rebalancing back to
  the target is what generates turnover, and turnover is what generates cost. A
  backtest that re-imposes the target weight every day pays no drift and
  silently earns a free rebalancing bonus.
* **Costs are charged as a portfolio fraction.** At each rebalance the traded
  fraction is the one-sided turnover -- ``max(total buys, total sells)`` -- which
  is the fraction of the portfolio that actually changed hands. Buying a full
  book from cash trades 1.0, and a full swap of one name for another also trades
  1.0 (not 2.0); the simpler ``sum(|dw|)/2`` gets the cash case wrong by half.
  That fraction is multiplied by the round-trip cost, matching
  `configs/validation_gates.yaml`'s ``portfolio.cost.round_trip_total``.
* **A held name with no price is an error, not a zero and not a stale carry.**
  Valuing an unquoted holding at zero vaporises the position; carrying the last
  close hides a delisting behind a flat line. Either way the curve lies, so the
  default is to stop and say which name and date. Pass
  ``missing_price_policy="last_close"`` to deliberately carry the last close
  (correct for a suspension that the panel simply failed to flag) -- but then the
  choice is the caller's, not a silent default.

The frozen single-factor validator measures turnover differently -- as bucket
*name* overlap on equal-weighted quantiles rather than weight deltas -- because
its portfolio is equal-weighted by construction. The difference is documented
here so that a strategy number and a factor number are never compared as if they
were the same statistic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "BacktestError",
    "backtest_weights",
    "curve_from_nav",
    "summarise_curve",
]

#: Matches configs/validation_gates.yaml -> portfolio.cost.round_trip_total.
DEFAULT_ROUND_TRIP_COST = 0.003


class BacktestError(ValueError):
    """Raised when a backtest cannot be run under the stated rules."""


@dataclass(frozen=True)
class _Snapshot:
    date: pd.Timestamp
    weights: dict[str, float]


def _prepare(weights: pd.DataFrame, prices: pd.DataFrame) -> tuple[list[_Snapshot], pd.DataFrame]:
    for frame, name in ((weights, "weights"), (prices, "prices")):
        missing = {"date", "code"} - set(frame.columns)
        if missing:
            raise BacktestError(f"{name} is missing columns: {', '.join(sorted(missing))}")
    if "weight" not in weights.columns:
        raise BacktestError("weights must carry a 'weight' column")
    if "close" not in prices.columns:
        raise BacktestError("prices must carry a 'close' column")
    if weights.empty:
        raise BacktestError("weights are empty")
    if prices.empty:
        raise BacktestError("prices are empty")

    work = weights.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.normalize()
    work["code"] = work["code"].astype(str)
    work["weight"] = pd.to_numeric(work["weight"], errors="coerce")
    work = work.dropna(subset=["weight"])
    if work.empty:
        raise BacktestError("weights contain no finite values")

    snapshots = [
        _Snapshot(date=date, weights=dict(zip(group["code"], group["weight"])))
        for date, group in work.groupby("date", sort=True)
    ]

    wide = prices.copy()
    wide["date"] = pd.to_datetime(wide["date"]).dt.normalize()
    wide["code"] = wide["code"].astype(str)
    wide["close"] = pd.to_numeric(wide["close"], errors="coerce")
    wide = wide.dropna(subset=["close"])
    wide = wide.pivot_table(index="date", columns="code", values="close", aggfunc="last")
    wide = wide.sort_index()
    if wide.empty:
        raise BacktestError("prices collapse to an empty matrix")
    return snapshots, wide


def backtest_weights(
    weights: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    initial_nav: float = 1.0,
    round_trip_cost: float = DEFAULT_ROUND_TRIP_COST,
    benchmark: pd.Series | None = None,
    benchmark_level: float | None = None,
    missing_price_policy: str = "error",
) -> dict[str, Any]:
    """Trade `weights` against `prices` and return the NAV curve and diagnostics.

    ``weights`` is a long frame of ``(date, code, weight)`` targets; ``prices`` is
    a long frame of ``(date, code, close)``. Returns a curve suitable for
    ``strategy_analytics.performance.analyze_window``.

    ``missing_price_policy`` governs a held name that has no price on a date:
    ``"error"`` (default) stops with the name and date, ``"last_close"`` carries
    the previous close forward.
    """
    if initial_nav <= 0:
        raise BacktestError(f"initial_nav must be positive, got {initial_nav!r}")
    if round_trip_cost < 0:
        raise BacktestError(f"round_trip_cost must not be negative, got {round_trip_cost!r}")
    if missing_price_policy not in ("error", "last_close"):
        raise BacktestError(
            f"missing_price_policy must be 'error' or 'last_close', got {missing_price_policy!r}"
        )

    snapshots, wide = _prepare(weights, prices)
    calendar = wide.index
    first_date = snapshots[0].date
    if first_date not in calendar:
        later = calendar[calendar >= first_date]
        if later.empty:
            raise BacktestError("no price dates on or after the first rebalance date")
        first_date = later[0]

    # Rebalance dates snapped onto the price calendar.
    schedule: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for snapshot in snapshots:
        snapped = calendar[calendar >= snapshot.date]
        if snapped.empty:
            continue
        schedule.append((snapped[0], snapshot.weights))
    if not schedule:
        raise BacktestError("no rebalance date falls on or after a price date")

    trade_dates = [date for date, _ in schedule]
    series = calendar[calendar >= trade_dates[0]]

    shares: dict[str, float] = {}
    nav = float(initial_nav)
    curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    rebalances: list[dict[str, Any]] = []
    schedule_index = 0

    for step, date in enumerate(series):
        row = wide.loc[date]
        prices_today = {code: float(value) for code, value in row.items() if np.isfinite(value)}

        # Value the book at today's prices before trading.
        if shares:
            unquoted = sorted(code for code in shares if code not in prices_today)
            if unquoted:
                if missing_price_policy == "error":
                    raise BacktestError(
                        f"{len(unquoted)} held name(s) have no price on {date.date()}: "
                        f"{', '.join(unquoted[:5])}"
                        + (" ..." if len(unquoted) > 5 else "")
                        + ". Valuing them at zero would vaporise the position and "
                        "carrying the last close would hide a delisting; decide which "
                        "is right and pass missing_price_policy explicitly."
                    )
                # Carry the last known close for the unquoted names only.
                last_known = wide.loc[:date, unquoted].ffill().iloc[-1]
                for code in unquoted:
                    value = last_known.get(code, np.nan)
                    if pd.notna(value):
                        prices_today[code] = float(value)

            nav = sum(quantity * prices_today.get(code, 0.0) for code, quantity in shares.items())
            if nav <= 0:
                raise BacktestError(
                    f"portfolio value fell to {nav!r} on {date.date()}; the curve cannot continue"
                )

        if schedule_index < len(schedule) and date == schedule[schedule_index][0]:
            targets = schedule[schedule_index][1]
            schedule_index += 1

            total = sum(targets.values())
            if total > 1.0 + 1e-9:
                raise BacktestError(
                    f"target weights sum to {total:.6f} (> 1) on {date.date()}; "
                    "the strategy would be levered"
                )

            # Current weights before trading, and the one-sided traded fraction.
            current: dict[str, float] = {}
            for code, quantity in shares.items():
                price = prices_today.get(code, 0.0)
                current[code] = (quantity * price / nav) if nav > 0 else 0.0

            universe = sorted(set(current) | set(targets))
            buys = 0.0
            sells = 0.0
            for code in universe:
                delta_weight = targets.get(code, 0.0) - current.get(code, 0.0)
                if delta_weight > 0:
                    buys += delta_weight
                else:
                    sells -= delta_weight

            # One-sided turnover: buying a full book from cash trades 1.0, and so
            # does a full swap. sum(|dw|)/2 would report the cash case as 0.5.
            traded = min(max(buys, sells), 1.0)
            cost = traded * round_trip_cost

            for code in universe:
                delta_weight = targets.get(code, 0.0) - current.get(code, 0.0)
                if abs(delta_weight) < 1e-12:
                    continue
                price = prices_today.get(code)
                if price is None or price <= 0:
                    continue
                trades.append(
                    {
                        "date": date,
                        "code": code,
                        "delta_weight": delta_weight,
                        "price": price,
                    }
                )

            # Trade at today's close and pay the cost out of NAV.
            nav *= 1.0 - cost
            shares = {}
            for code, weight in targets.items():
                price = prices_today.get(code)
                if price is None or price <= 0 or weight == 0:
                    continue
                shares[code] = nav * weight / price

            rebalances.append(
                {
                    "date": date,
                    "traded_fraction": traded,
                    "cost": cost,
                    "n_positions": len(shares),
                }
            )

        bench_value: float | None = None
        if benchmark is not None and len(benchmark):
            aligned = benchmark.reindex([date]).ffill()
            value = aligned.iloc[0] if len(aligned) else np.nan
            if pd.notna(value):
                if benchmark_level is None:
                    benchmark_level = float(value)
                bench_value = float(value) / benchmark_level
        elif benchmark_level is not None:
            bench_value = None

        curve.append({"date": date.date().isoformat(), "nav": nav, "benchmark": bench_value})

    if len(curve) < 2:
        raise BacktestError("the price calendar produced fewer than two observations")

    total_turnover = float(sum(item["traded_fraction"] for item in rebalances))
    return {
        "curve": curve,
        "trades": trades,
        "rebalances": rebalances,
        "metrics": {
            "observations": len(curve),
            "rebalances": len(rebalances),
            "total_traded_fraction": total_turnover,
            "mean_traded_fraction": total_turnover / len(rebalances) if rebalances else 0.0,
            "total_cost_fraction": float(sum(item["cost"] for item in rebalances)),
            "round_trip_cost": round_trip_cost,
            "final_nav": nav,
        },
        "turnover_basis": "one-sided turnover, max(buys, sells)",
    }


def curve_from_nav(
    nav: Mapping[str, float] | pd.Series,
    *,
    benchmark: Mapping[str, float] | pd.Series | None = None,
) -> list[dict[str, Any]]:
    """Build an ``analyze_window`` curve from date->level mappings."""
    levels = pd.Series(dict(nav), dtype=float).sort_index()
    if levels.empty:
        raise BacktestError("nav series is empty")
    bench = None
    if benchmark is not None:
        bench = pd.Series(dict(benchmark), dtype=float).sort_index().reindex(levels.index).ffill()
        base = bench.dropna()
        if len(base):
            bench = bench / float(base.iloc[0])

    rows: list[dict[str, Any]] = []
    for date, value in levels.items():
        entry: dict[str, Any] = {"date": str(date)[:10], "nav": float(value)}
        if bench is not None:
            aligned = bench.get(date, np.nan)
            entry["benchmark"] = None if pd.isna(aligned) else float(aligned)
        rows.append(entry)
    return rows


def summarise_curve(curve: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Metrics via the existing analytics module, with the curve's date range."""
    from research_core.strategy_analytics.performance import analyze_window

    rows = list(curve)
    if len(rows) < 2:
        raise BacktestError("need at least two curve points to summarise")
    metrics = analyze_window(rows)
    metrics["start"] = rows[0]["date"]
    metrics["end"] = rows[-1]["date"]
    return metrics
