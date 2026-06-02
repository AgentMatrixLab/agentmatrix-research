from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import pickle

import pandas as pd

from contracts.backtest import BacktestResult, EquityPoint, HoldingSnapshot, PerformanceMetrics, TradeRecord
from research_core.attribution_engine.basic import build_basic_attribution


class RQAlphaPickleParserError(RuntimeError):
    pass


class RQAlphaPickleParser:
    def __init__(self, pickle_path: str | Path):
        self.pickle_path = Path(pickle_path)
        if not self.pickle_path.exists():
            raise FileNotFoundError(f"RQAlpha result pickle not found: {self.pickle_path}")

    def parse(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str = "v1",
        benchmark: str = "000300.XSHG",
    ) -> BacktestResult:
        payload = self._load_payload()
        result = payload.get("sys_analyser", payload)
        summary = self._ensure_mapping(result.get("summary"))
        portfolio_df = self._normalize_frame(
            self._pick_first(result, ["total_portfolios", "portfolio", "stock_account", "stock_portfolios"])
        )
        if portfolio_df.empty:
            raise RQAlphaPickleParserError("RQAlpha result is missing portfolio data")

        benchmark_df = self._normalize_frame(
            self._pick_first(result, ["benchmark_portfolios", "benchmark_portfolio", "benchmark_account"])
        )
        trades_df = self._normalize_frame(self._pick_first(result, ["trades"]))
        positions_df = self._normalize_frame(self._pick_first(result, ["stock_positions", "positions"]))

        initial_cash = self._extract_initial_cash(summary, portfolio_df)
        metrics = self._build_metrics(summary, portfolio_df, trades_df)
        equity_curve = self._build_equity_curve(portfolio_df, benchmark_df, initial_cash)
        holdings = self._build_holdings(positions_df, portfolio_df)
        trades = self._build_trades(trades_df)
        attribution = self._build_attribution(summary, holdings, initial_cash)

        return BacktestResult(
            run_id=run_id,
            status="parsed",
            engine="rqalpha",
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            benchmark=str(summary.get("benchmark") or benchmark),
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            holdings=holdings,
            attribution=attribution,
            artifacts={"source_pickle": str(self.pickle_path)},
            diagnostics={
                "portfolio_rows": len(portfolio_df),
                "benchmark_rows": len(benchmark_df),
                "position_rows": len(positions_df),
                "trade_rows": len(trades_df),
                "summary_keys": sorted(summary.keys()),
            },
        )

    def to_dict(self, result: BacktestResult) -> dict[str, Any]:
        return asdict(result)

    def _load_payload(self) -> dict[str, Any]:
        with self.pickle_path.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            raise RQAlphaPickleParserError("RQAlpha result pickle must contain a dict payload")
        return payload

    def _pick_first(self, payload: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in payload and payload[key] is not None:
                return payload[key]
        return None

    def _ensure_mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        raise RQAlphaPickleParserError("RQAlpha summary payload must be a dict")

    def _normalize_frame(self, value: Any) -> pd.DataFrame:
        if value is None:
            return pd.DataFrame()
        if isinstance(value, pd.DataFrame):
            frame = value.copy()
        elif isinstance(value, pd.Series):
            frame = value.to_frame().T
        elif isinstance(value, list):
            frame = pd.DataFrame(value)
        elif isinstance(value, dict):
            frame = pd.DataFrame(value)
        else:
            raise RQAlphaPickleParserError(f"Unsupported RQAlpha frame payload: {type(value)!r}")

        if isinstance(frame.index, pd.MultiIndex):
            frame = frame.reset_index()
        elif frame.index.name or not isinstance(frame.index, pd.RangeIndex):
            frame = frame.reset_index()

        for candidate in ("date", "datetime", "trading_datetime"):
            if candidate in frame.columns:
                frame[candidate] = pd.to_datetime(frame[candidate], errors="coerce")

        return frame

    def _extract_initial_cash(self, summary: dict[str, Any], portfolio_df: pd.DataFrame) -> float:
        direct_keys = ("units", "stock", "STOCK")
        for key in direct_keys:
            value = summary.get(key)
            if isinstance(value, (int, float)) and float(value) > 0:
                return float(value)

        starting_cash = summary.get("starting_cash")
        if isinstance(starting_cash, str):
            parts = [segment for segment in str(starting_cash).replace(";", ",").split(",") if ":" in segment]
            for part in parts:
                _, raw_value = part.split(":", 1)
                try:
                    parsed = float(raw_value)
                except ValueError:
                    continue
                if parsed > 0:
                    return parsed

        total_value_column = self._pick_first_column(portfolio_df, ["total_value", "portfolio_value", "market_value"])
        if total_value_column and len(portfolio_df):
            return float(portfolio_df.iloc[0][total_value_column])
        return 1.0

    def _pick_first_column(self, frame: pd.DataFrame, candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate in frame.columns:
                return candidate
        return None

    def _get_date_column(self, frame: pd.DataFrame) -> str:
        for candidate in ("date", "datetime", "trading_datetime"):
            if candidate in frame.columns:
                return candidate
        raise RQAlphaPickleParserError("Unable to locate date column in RQAlpha dataframe")

    def _series_from_frame(self, frame: pd.DataFrame, candidates: list[str], fallback_cash: float) -> pd.Series:
        if frame.empty:
            return pd.Series(dtype=float)

        for candidate in candidates:
            if candidate in frame.columns:
                return pd.Series(frame[candidate].astype(float).values, index=frame[self._get_date_column(frame)])

        total_value_column = self._pick_first_column(frame, ["total_value", "portfolio_value"])
        if total_value_column:
            series = frame[total_value_column].astype(float) / max(fallback_cash, 1e-12)
            return pd.Series(series.values, index=frame[self._get_date_column(frame)])

        raise RQAlphaPickleParserError(f"Unable to locate any of {candidates} in RQAlpha dataframe")

    def _build_metrics(
        self,
        summary: dict[str, Any],
        portfolio_df: pd.DataFrame,
        trades_df: pd.DataFrame,
    ) -> PerformanceMetrics:
        total_return = float(summary.get("total_returns", summary.get("total_return", 0.0)) or 0.0)
        annualized_return = float(
            summary.get("annualized_returns", summary.get("annualized_return", 0.0)) or 0.0
        )
        benchmark_return = float(
            summary.get("benchmark_total_returns", summary.get("benchmark_return", 0.0)) or 0.0
        )
        excess_return = float(summary.get("excess_returns", total_return - benchmark_return) or 0.0)
        max_drawdown = abs(float(summary.get("max_drawdown", 0.0) or 0.0))
        sharpe = float(summary.get("sharpe", 0.0) or 0.0)
        volatility = float(summary.get("volatility", 0.0) or 0.0)
        turnover = float(summary.get("turnover", summary.get("avg_daily_turnover", 0.0)) or 0.0)

        if "daily_returns" in portfolio_df.columns and len(portfolio_df):
            daily_returns = portfolio_df["daily_returns"].astype(float)
        else:
            initial_cash = self._extract_initial_cash(summary, portfolio_df)
            nav_series = self._series_from_frame(portfolio_df, ["unit_net_value", "nav"], initial_cash)
            daily_returns = nav_series.pct_change().fillna(0.0)
        win_rate = float((daily_returns.iloc[1:] > 0).mean()) if len(daily_returns) > 1 else 0.0

        if not turnover and not trades_df.empty and "last_price" in trades_df.columns and "last_quantity" in trades_df.columns:
            trade_amount = (trades_df["last_price"].astype(float) * trades_df["last_quantity"].astype(float)).abs().sum()
            assets_col = self._pick_first_column(portfolio_df, ["total_value", "portfolio_value"])
            avg_assets = float(portfolio_df[assets_col].astype(float).mean()) if assets_col else 0.0
            turnover = float(trade_amount / max(avg_assets * 2, 1.0))

        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
            volatility=volatility,
            turnover=turnover,
            win_rate=win_rate,
        )

    def _build_equity_curve(
        self,
        portfolio_df: pd.DataFrame,
        benchmark_df: pd.DataFrame,
        initial_cash: float,
    ) -> list[EquityPoint]:
        strategy_nav = self._series_from_frame(portfolio_df, ["unit_net_value", "nav"], initial_cash).sort_index()
        if benchmark_df.empty:
            benchmark_nav = pd.Series(1.0, index=strategy_nav.index)
        else:
            benchmark_nav = self._series_from_frame(benchmark_df, ["unit_net_value", "static_unit_net_value", "nav"], 1.0)
            benchmark_nav = benchmark_nav.reindex(strategy_nav.index).ffill().fillna(1.0)

        points: list[EquityPoint] = []
        peak = None
        for timestamp, strategy_value in strategy_nav.items():
            peak = strategy_value if peak is None else max(peak, float(strategy_value))
            drawdown = 0.0 if not peak else abs(float(strategy_value) / peak - 1.0)
            benchmark_value = float(benchmark_nav.loc[timestamp]) if timestamp in benchmark_nav.index else 1.0
            points.append(
                EquityPoint(
                    timestamp=pd.Timestamp(timestamp).strftime("%Y-%m-%d"),
                    strategy_nav=float(strategy_value),
                    benchmark_nav=benchmark_value,
                    drawdown=drawdown,
                )
            )
        return points

    def _build_trades(self, trades_df: pd.DataFrame) -> list[TradeRecord]:
        if trades_df.empty:
            return []

        time_column = None
        for candidate in ("trading_datetime", "datetime", "date"):
            if candidate in trades_df.columns:
                time_column = candidate
                break

        symbol_column = self._pick_first_column(trades_df, ["order_book_id", "symbol"])
        qty_column = self._pick_first_column(trades_df, ["last_quantity", "quantity", "filled_quantity"])
        price_column = self._pick_first_column(trades_df, ["last_price", "price", "avg_price"])
        side_column = self._pick_first_column(trades_df, ["side"])
        commission_column = self._pick_first_column(trades_df, ["commission"])
        tax_column = self._pick_first_column(trades_df, ["tax"])

        if not all([time_column, symbol_column, qty_column, price_column, side_column]):
            return []

        records: list[TradeRecord] = []
        for _, row in trades_df.iterrows():
            commission = float(row.get(commission_column, 0.0) or 0.0) if commission_column else 0.0
            tax = float(row.get(tax_column, 0.0) or 0.0) if tax_column else 0.0
            records.append(
                TradeRecord(
                    traded_at=pd.Timestamp(row[time_column]).strftime("%Y-%m-%d %H:%M:%S"),
                    symbol=str(row[symbol_column]),
                    side=str(row[side_column]),
                    quantity=float(row[qty_column] or 0.0),
                    price=float(row[price_column] or 0.0),
                    commission=commission + tax,
                    slippage=0.0,
                    reason=str(row.get("position_effect", "")),
                )
            )
        return records

    def _build_holdings(self, positions_df: pd.DataFrame, portfolio_df: pd.DataFrame) -> list[HoldingSnapshot]:
        if positions_df.empty:
            return []

        date_column = self._get_date_column(positions_df)
        symbol_column = self._pick_first_column(positions_df, ["order_book_id", "symbol"])
        market_value_column = self._pick_first_column(positions_df, ["market_value", "value"])
        if symbol_column is None:
            return []

        total_value_map: dict[pd.Timestamp, float] = {}
        if not portfolio_df.empty:
            portfolio_date_column = self._get_date_column(portfolio_df)
            total_value_column = self._pick_first_column(portfolio_df, ["total_value", "portfolio_value"])
            if total_value_column:
                total_value_map = {
                    pd.Timestamp(row[portfolio_date_column]).normalize(): float(row[total_value_column] or 0.0)
                    for _, row in portfolio_df.iterrows()
                }

        snapshots: list[HoldingSnapshot] = []
        for as_of, frame in positions_df.groupby(date_column):
            normalized_date = pd.Timestamp(as_of).normalize()
            weights: dict[str, float] = {}
            exposures: dict[str, float] = {}
            total_value = total_value_map.get(normalized_date, 0.0)
            if market_value_column:
                total_market_value = float(frame[market_value_column].fillna(0.0).astype(float).sum())
            else:
                total_market_value = 0.0
            denominator = total_value or total_market_value or 1.0

            for _, row in frame.iterrows():
                symbol = str(row[symbol_column])
                market_value = float(row.get(market_value_column, 0.0) or 0.0) if market_value_column else 0.0
                weight = market_value / denominator
                weights[symbol] = weight
                exchange = symbol.split(".")[-1] if "." in symbol else "UNKNOWN"
                exposures[exchange] = exposures.get(exchange, 0.0) + weight

            snapshots.append(
                HoldingSnapshot(
                    as_of=normalized_date.strftime("%Y-%m-%d %H:%M:%S"),
                    weights=weights,
                    exposures=exposures,
                )
            )
        return snapshots

    def _build_attribution(
        self,
        summary: dict[str, Any],
        holdings: list[HoldingSnapshot],
        initial_cash: float,
    ):
        total_return = float(summary.get("total_returns", 0.0) or 0.0)
        benchmark_return = float(summary.get("benchmark_total_returns", 0.0) or 0.0)
        fee_drag = float(summary.get("transaction_cost", 0.0) or 0.0) / max(initial_cash, 1.0)
        final_weights = holdings[-1].weights if holdings else {}
        position_contributions = {
            symbol: weight * total_return
            for symbol, weight in sorted(final_weights.items(), key=lambda item: item[1], reverse=True)[:10]
        }
        sector_contributions: dict[str, float] = {}
        for symbol, contribution in position_contributions.items():
            exchange = symbol.split(".")[-1] if "." in symbol else "UNKNOWN"
            sector_contributions[exchange] = sector_contributions.get(exchange, 0.0) + contribution

        return build_basic_attribution(
            total_return=total_return,
            benchmark_return=benchmark_return,
            fee_drag=fee_drag,
            position_contributions=position_contributions,
            sector_contributions=sector_contributions,
        )
