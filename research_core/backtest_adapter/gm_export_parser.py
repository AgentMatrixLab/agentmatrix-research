from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd

from contracts.backtest import BacktestResult, EquityPoint, HoldingSnapshot, PerformanceMetrics, TradeRecord
from research_core.attribution_engine.basic import build_basic_attribution


class GMExportParserError(RuntimeError):
    pass


class GMExportParser:
    def __init__(self, zip_path: str | Path):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f'GM export zip not found: {self.zip_path}')

    def parse(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str = 'v1',
        benchmark: str = 'SHSE.000300',
    ) -> BacktestResult:
        nav_df, holdings_df, trades_df, filenames = self._load_frames()
        initial_cash = float(nav_df.iloc[0]['total_asset_value'])
        metrics = self._build_metrics(nav_df, trades_df)
        holdings = self._build_holdings(holdings_df)
        trades = self._build_trades(trades_df)
        attribution = self._build_attribution(nav_df, holdings_df, trades_df, initial_cash)
        equity_curve = self._build_equity_curve(nav_df)
        return BacktestResult(
            run_id=run_id,
            status='parsed',
            engine='gm',
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            benchmark=benchmark,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            holdings=holdings,
            attribution=attribution,
            artifacts={
                'source_zip': str(self.zip_path),
                'nav_file': filenames['nav'],
                'holdings_file': filenames['holdings'],
                'trades_file': filenames['trades'],
            },
            diagnostics={
                'nav_rows': len(nav_df),
                'holdings_rows': len(holdings_df),
                'trade_rows': len(trades_df),
                'source_files': filenames,
            },
        )

    def to_dict(self, result: BacktestResult) -> dict[str, Any]:
        return asdict(result)

    def _load_frames(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
        with ZipFile(self.zip_path, 'r') as archive:
            names = archive.namelist()
            nav_name = self._match_name(names, ['净值数据', 'nav'])
            holdings_name = self._match_name(names, ['持仓数据', 'holding', 'position'])
            trades_name = self._match_name(names, ['交易数据', 'trade'])
            nav_df = self._read_csv(archive, nav_name)
            holdings_df = self._read_csv(archive, holdings_name)
            trades_df = self._read_csv(archive, trades_name)
        nav_df['date'] = pd.to_datetime(nav_df['date'])
        holdings_df['date'] = pd.to_datetime(holdings_df['date'])
        trades_df['trade_time'] = pd.to_datetime(trades_df['trade_time'])
        if 'order_fill_time' in trades_df.columns:
            trades_df['order_fill_time'] = pd.to_datetime(trades_df['order_fill_time'], errors='coerce')
        return nav_df, holdings_df, trades_df, {
            'nav': nav_name,
            'holdings': holdings_name,
            'trades': trades_name,
        }

    def _match_name(self, names: list[str], keywords: list[str]) -> str:
        for name in names:
            normalized = name.lower()
            if all(keyword.lower() in normalized for keyword in keywords[:1]) or any(keyword.lower() in normalized for keyword in keywords):
                return name
        raise GMExportParserError(f'Unable to find file matching {keywords} in {names}')

    def _read_csv(self, archive: ZipFile, name: str) -> pd.DataFrame:
        with archive.open(name) as handle:
            return pd.read_csv(handle, encoding='utf-8-sig')

    def _build_metrics(self, nav_df: pd.DataFrame, trades_df: pd.DataFrame) -> PerformanceMetrics:
        daily_returns = nav_df['strategy_yield_daily'].astype(float)
        benchmark_daily = nav_df['benchmark_yield_daily'].astype(float)
        total_return = float(nav_df.iloc[-1]['strategy_yield'])
        benchmark_return = float(nav_df.iloc[-1]['benchmark_yield'])
        excess_return = total_return - benchmark_return
        max_drawdown = abs(float(nav_df['strategy_drawdown'].min()))
        daily_std = float(daily_returns.std(ddof=0))
        annualized_return = self._annualize_return(total_return, len(nav_df))
        volatility = daily_std * (252 ** 0.5) if daily_std else 0.0
        sharpe = float(daily_returns.mean() / daily_std * (252 ** 0.5)) if daily_std else 0.0
        trade_activity = trades_df[trades_df['symbol'].notna() & trades_df['volume'].fillna(0).ne(0)].copy()
        avg_assets = float(nav_df['total_asset_value'].mean()) if len(nav_df) else 0.0
        turnover = float(trade_activity['amount'].abs().sum() / max(avg_assets * 2, 1.0))
        win_rate = float((daily_returns.iloc[1:] > 0).mean()) if len(daily_returns) > 1 else 0.0
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

    def _annualize_return(self, total_return: float, periods: int) -> float:
        trading_periods = max(periods - 1, 1)
        base = 1.0 + total_return
        if base <= 0:
            return -1.0
        return base ** (252 / trading_periods) - 1.0

    def _build_equity_curve(self, nav_df: pd.DataFrame) -> list[EquityPoint]:
        points: list[EquityPoint] = []
        for _, row in nav_df.iterrows():
            benchmark_nav = 1.0 + float(row['benchmark_yield'])
            points.append(
                EquityPoint(
                    timestamp=row['date'].strftime('%Y-%m-%d'),
                    strategy_nav=float(row['nav']),
                    benchmark_nav=benchmark_nav,
                    drawdown=abs(float(row['strategy_drawdown'])),
                )
            )
        return points

    def _build_trades(self, trades_df: pd.DataFrame) -> list[TradeRecord]:
        rows = trades_df[trades_df['symbol'].notna() & trades_df['volume'].fillna(0).ne(0)].copy()
        records: list[TradeRecord] = []
        for _, row in rows.iterrows():
            order_price = float(row.get('order_price', 0.0) or 0.0)
            vwap = float(row.get('vwap', 0.0) or 0.0)
            quantity = float(row.get('volume', 0.0) or 0.0)
            slippage = abs(vwap - order_price) * quantity if order_price and quantity else 0.0
            traded_at = row['order_fill_time'] if pd.notna(row.get('order_fill_time')) else row['trade_time']
            records.append(
                TradeRecord(
                    traded_at=pd.Timestamp(traded_at).strftime('%Y-%m-%d %H:%M:%S'),
                    symbol=str(row['symbol']),
                    side=str(row.get('btype') or row.get('side') or ''),
                    quantity=quantity,
                    price=vwap or order_price,
                    commission=float(row.get('fee', 0.0) or 0.0),
                    slippage=float(slippage),
                    reason=str(row.get('btype') or ''),
                )
            )
        return records

    def _build_holdings(self, holdings_df: pd.DataFrame) -> list[HoldingSnapshot]:
        snapshots: list[HoldingSnapshot] = []
        for as_of, frame in holdings_df.groupby('date'):
            total_market_value = float(frame['market_value'].sum())
            weights = {}
            exchange_exposures: dict[str, float] = {}
            for _, row in frame.iterrows():
                symbol = str(row['symbol'])
                market_value = float(row['market_value'])
                weight = market_value / total_market_value if total_market_value else 0.0
                weights[symbol] = weight
                exchange = symbol.split('.')[0] if '.' in symbol else 'UNKNOWN'
                exchange_exposures[exchange] = exchange_exposures.get(exchange, 0.0) + weight
            snapshots.append(
                HoldingSnapshot(
                    as_of=pd.Timestamp(as_of).strftime('%Y-%m-%d %H:%M:%S'),
                    weights=weights,
                    exposures=exchange_exposures,
                )
            )
        return snapshots

    def _build_attribution(
        self,
        nav_df: pd.DataFrame,
        holdings_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        initial_cash: float,
    ):
        total_return = float(nav_df.iloc[-1]['strategy_yield'])
        benchmark_return = float(nav_df.iloc[-1]['benchmark_yield'])
        fee_drag = float(trades_df['fee'].fillna(0.0).sum()) / max(initial_cash, 1.0)
        avg_cash_ratio = float((nav_df['cash_balance'] / nav_df['total_asset_value'].replace(0, pd.NA)).fillna(0.0).mean())
        cash_drag = avg_cash_ratio * max(benchmark_return, 0.0)
        final_holdings = holdings_df.sort_values('date').groupby('symbol').tail(1)
        final_market_values = {
            str(row['symbol']): float(row['market_value'])
            for _, row in final_holdings.iterrows()
        }
        trade_rows = trades_df[trades_df['symbol'].notna()].copy()
        net_amount_by_symbol = trade_rows.groupby('symbol')['net_amount'].sum().to_dict()
        position_contributions: dict[str, float] = {}
        sector_contributions: dict[str, float] = {}
        symbols = set(final_market_values) | set(net_amount_by_symbol)
        for symbol in symbols:
            pnl_currency = final_market_values.get(symbol, 0.0) + float(net_amount_by_symbol.get(symbol, 0.0))
            contribution = pnl_currency / max(initial_cash, 1.0)
            if abs(contribution) < 1e-12:
                continue
            position_contributions[str(symbol)] = contribution
            exchange = str(symbol).split('.')[0] if '.' in str(symbol) else 'UNKNOWN'
            sector_contributions[exchange] = sector_contributions.get(exchange, 0.0) + contribution
        return build_basic_attribution(
            total_return=total_return,
            benchmark_return=benchmark_return,
            fee_drag=fee_drag,
            cash_drag=cash_drag,
            position_contributions=position_contributions,
            sector_contributions=sector_contributions,
        )
