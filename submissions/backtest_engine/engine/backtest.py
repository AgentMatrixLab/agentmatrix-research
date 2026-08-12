"""
轻量回测引擎 — 不依赖Qlib

流程:
  1. 加载本地Parquet数据
  2. 按日期遍历回测区间
  3. 对每个调仓日: 调用 strategy.get_signals(data_up_to_date)
  4. 模拟买卖, 计算净值
  5. 输出净值曲线 + 绩效指标
"""
import os, sys, importlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import *
from engine.metrics import compute_metrics, format_report


class BacktestEngine:
    def __init__(self, data_dir=DATA_DIR, skip_load=False):
        self.data_dir = data_dir
        if not skip_load:
            self._load_data()

    def _load_data(self):
        """加载所有本地数据 (支持按年分片 kline/)"""
        print("  加载数据...")

        from engine.data_manager import load_kline, _kline_dir

        # ── K线: 优先 kline_adj.parquet, 其次按年分片 ──
        merged_path = os.path.join(self.data_dir, "kline_adj.parquet")
        if os.path.exists(merged_path):
            print("  读取预合并K线...", end=' ', flush=True)
            self.kline = pd.read_parquet(merged_path)
            print(f"{len(self.kline)} 行")
        else:
            print("  加载按年分片K线...", end=' ', flush=True)
            self.kline = load_kline()
            if self.kline is None:
                raise FileNotFoundError(
                    f"K线数据不存在: {_kline_dir()}/kline_*.parquet\n"
                    "请确保 DATA_DIR 指向已有数据目录"
                )
            # 无adj_factor时降级
            for col in ['open', 'high', 'low', 'close']:
                if col in self.kline.columns:
                    self.kline[f'{col}_adj'] = self.kline[col]
            print(f"{len(self.kline)} 行 (无复权)")

        # ── 日历: 从K线提取 (兼容无独立calendar文件) ──
        path_cal = os.path.join(self.data_dir, "calendar.parquet")
        if os.path.exists(path_cal):
            self.calendar = pd.read_parquet(path_cal)
            if isinstance(self.calendar['trade_date'].iloc[0], str):
                self.calendar['trade_date'] = pd.to_datetime(self.calendar['trade_date'])
            elif self.calendar['trade_date'].dtype == "uint16":
                self.calendar['trade_date'] = pd.to_datetime(
                    self.calendar['trade_date'], unit="D", origin="unix"
                )
            self.calendar = self.calendar.sort_values('trade_date')
        else:
            # 从K线提取交易日历
            self.calendar = pd.DataFrame({
                'trade_date': sorted(self.kline['trade_date'].unique())
            })
            print(f"  从K线提取日历: {len(self.calendar)} 天")

        # ── 股票状态 (ST/停牌) ──
        self.status = None
        path_status = os.path.join(self.data_dir, "security_status.parquet")
        if os.path.exists(path_status):
            self.status = pd.read_parquet(path_status)
            if self.status['trade_date'].dtype == "uint16":
                self.status['trade_date'] = pd.to_datetime(
                    self.status['trade_date'], unit="D", origin="unix"
                )
        
        # 股票信息 (排除退市股)
        self._valid_symbols = None
        path_info = os.path.join(self.data_dir, "stock_info.parquet")
        if os.path.exists(path_info):
            info = pd.read_parquet(path_info)
            # 排除退市股: is_listed=0 or 名称含"退市"
            listed = info[info['is_listed'] == 1]
            no_delist = listed[~listed['sec_name'].str.contains('退市', na=False)]
            self._valid_symbols = set(no_delist['symbol'].tolist())
            print(f"  有效股票: {len(self._valid_symbols)} 只 (已排除退市股)")
        else:
            print("  stock_info: 无 (跳过退市过滤)")

        print(f"  K线: {len(self.kline)} 行, {self.kline['symbol'].nunique()} 只股票")
        print(f"  交易日: {len(self.calendar)} 天")

        # 财务数据
        self.financial = None
        path_bs = os.path.join(self.data_dir, "balance_sheet.parquet")
        path_is = os.path.join(self.data_dir, "income_stmt.parquet")
        if os.path.exists(path_bs) and os.path.exists(path_is):
            self.financial_path = self.data_dir  # 让策略自己加载
            print(f"  财务数据可用: 策略可自行加载")
        else:
            self.financial = None
            print("  财务: 无 (跳过财务因子)")

    def _get_adj_price(self, df):
        """
        计算后复权价格
        复权因子 adj_factor: 后复权价 = 收盘价 × 复权因子 / 最新复权因子
        处理起来比较简单: price_adj = close × adj_factor (后复权)
        """
        # 合并复权因子
        df = df.merge(self.adj, on=['symbol', 'trade_date'], how='left')
        # 填充缺失的复权因子 (用1)
        df['adj_factor'] = df['adj_factor'].fillna(1.0)
        # 各价格复权
        for col in ['open', 'high', 'low', 'close']:
            df[f'{col}_adj'] = df[col] * df['adj_factor']
        return df

    def _prepare_data(self, end_date, lookback_years=BACKTEST_YEARS):
        """
        准备回测用的完整数据集 (end_date之前的lookback_years年数据)
        返回: 合并后的DataFrame, 所有信号计算需要的列
        """
        start_date = end_date - pd.Timedelta(days=int(lookback_years * 365 + 30))
        start_date = self.calendar[self.calendar['trade_date'] >= start_date]['trade_date'].min()

        # 过滤K线 — 使用 pd.Timestamp 确保 PyArrow 兼容
        ts_start = pd.Timestamp(start_date)
        ts_end = pd.Timestamp(end_date)
        mask = (self.kline['trade_date'] >= ts_start) & (self.kline['trade_date'] <= ts_end)
        df = self.kline.loc[mask]
        # 释放 kline 引用以减少内存 (回测只需要过滤后的数据)
        del mask

        # 合并停牌/ST信息 (过滤掉停牌和ST的股票)
        if self.status is not None:
            status_cols = [c for c in ['symbol','trade_date','is_suspended','is_st','status_code']
                          if c in self.status.columns]
            df = df.merge(
                self.status[status_cols],
                on=['symbol', 'trade_date'], how='left'
            )
            df['is_suspended'] = df['is_suspended'].fillna(0)
            if 'is_st' in df.columns:
                df['is_st'] = df['is_st'].fillna(0)

        # 计算基础因子 (ret_1d 用于基准)
        df = self._calc_basic_factors(df)

        return df.sort_values(['trade_date', 'symbol'])

    def _calc_basic_factors(self, df):
        """计算基础因子 (按股票分组) — 内存优化版"""
        # 只计算必要的 ret_1d, 跳过大量滚动窗口因子减少内存
        df = df.sort_values(['symbol', 'trade_date'])
        df['ret_1d'] = df.groupby('symbol')['close_adj'].pct_change()
        return df

    def _filter_tradable(self, today):
        """
        过滤可交易股票:
        - 非停牌
        - 非ST
        - 非退市
        - 有价格数据
        """
        if len(today) == 0:
            return today

        today = today.copy()
        if 'is_suspended' in today.columns:
            today = today[today['is_suspended'] == 0]
        if 'is_st' in today.columns:
            today = today[today['is_st'] == 0]
        if 'status_code' in today.columns:
            today = today[today['status_code'] == 'NORMAL']
        if self._valid_symbols is not None:
            today = today[today['symbol'].isin(self._valid_symbols)]
        today = today[today['close_adj'] > 0]
        today = today[today['volume'] > 0]
        return today

    def run_strategy(self, signal_fn, name="策略", rebalance_freq=5,
                     start_date=None, end_date=None):
        """
        跑单个策略回测

        参数:
            signal_fn: function(df) -> DataFrame
                输入: 全量历史DataFrame (含价格+因子)
                输出: DataFrame, 包含 ['symbol', 'weight'] 列
                      weight是目标持仓比例 (总和=1)
            name: 策略名称
            rebalance_freq: 调仓频率 (交易日数), 默认5天=周频
            start_date: 自定义回测起始日期 (str/date/datetime), 默认近BACKTEST_YEARS年
            end_date:   自定义回测结束日期 (str/date/datetime), 默认日历最新
        """
        # 确定回测区间
        if end_date is not None:
            end_date = pd.Timestamp(end_date)
        else:
            end_date = self.calendar['trade_date'].max()

        if start_date is not None:
            start_date = pd.Timestamp(start_date)
        else:
            start_idx = max(0, len(self.calendar) - int(BACKTEST_YEARS * 252) - 20)
            start_date = self.calendar.iloc[start_idx]['trade_date']

        print(f"\n  ▶ {name}")
        print(f"    区间: {start_date.date()} → {end_date.date()}")
        print(f"    调仓频率: 每{rebalance_freq}天")

        # 准备完整数据 (覆盖起止区间)
        lookback = max(BACKTEST_YEARS, (end_date - start_date).days / 365 + 1)
        full_data = self._prepare_data(end_date, lookback_years=lookback)
        trade_dates = full_data['trade_date'].unique()
        trade_dates = sorted(trade_dates)

        # 按日期预分组 (避免循环内逐日扫描600万行)
        print("    按日期分组...", end=' ', flush=True)
        date_groups = dict(tuple(full_data.groupby('trade_date')))
        print(f"{len(date_groups)} 组")

        # 只保留回测区间内的数据
        trade_dates = [d for d in trade_dates if d >= start_date]

        # ====== 基准: 沪深300 ======
        csi_path = os.path.join(self.data_dir, "csi300_index.parquet")
        if os.path.exists(csi_path):
            csi = pd.read_parquet(csi_path)
            csi['date'] = pd.to_datetime(csi['date'])
            csi = csi.set_index('date').sort_index()
            # 对齐交易日
            csi = csi.reindex(trade_dates, method='ffill')
            self._benchmark_nav = csi['CSI300'] / csi['CSI300'].iloc[0]
            print(f"    基准: 沪深300 ({csi.index[0].date()} ~ {csi.index[-1].date()})")
        else:
            self._benchmark_nav = pd.Series([1.0] * len(trade_dates))
            print("    基准: 无CSI300数据, 使用占位")

        # 保存调仓频率供后续换手率计算用
        self._rebalance_freq = rebalance_freq

        print(f"    交易日数: {len(trade_dates)}")

        # ====== 回测主循环 ======
        nav = INIT_CAPITAL
        nav_series = []
        position = {}  # {symbol: shares}
        position_cost = {}  # {symbol: avg_entry_price}
        trade_log = []  # [{symbol, entry_date, exit_date, shares, entry_price, exit_price, pnl}]
        position_snapshots = []  # [{date, nav, holdings: [...]}]
        cash_residual = 0.0  # 整数舍入剩余现金
        prev_weights = None
        weights_history = []
        daily_values = []
        rebalance_log = []

        # [#1 T+1执行] 信号在T日生成，T+1日执行
        pending_signals = None       # target_weights from T, execute on T+1
        pending_snapshot = None      # snapshot taken at T

        # [#4 缺价处理] 记录每只股票最后有效价格，价格缺失时沿用
        _last_price = {}

        # 只调仓日调仓
        rebalance_dates = trade_dates[::rebalance_freq]
        rebalance_set = set(rebalance_dates)

        for i, current_date in enumerate(trade_dates):
            # 获取当天数据
            today_data = date_groups.get(current_date)

            # 预构建价格字典 + 更新 _last_price
            price_dict = {}
            if today_data is not None and len(today_data) > 0:
                for _, row in today_data[['symbol', 'close_adj']].iterrows():
                    p = float(row['close_adj'])
                    if p > 0:
                        price_dict[row['symbol']] = p
                        _last_price[row['symbol']] = p

            # ────────────────────────────────────────────
            # Step A: 执行T-1日产生的待执行调仓 (T+1执行)
            # ────────────────────────────────────────────
            if pending_signals is not None:
                target_weights = pending_signals

                # 记录调仓前快照
                if pending_snapshot is not None:
                    position_snapshots.append(pending_snapshot)

                # 当前组合总市值
                total_value = nav
                cash_balance = total_value
                stamps_sell = 0

                # —— 卖出不在目标中的股票 ——
                for sym in list(position.keys()):
                    if sym not in set(target_weights['symbol']):
                        price = price_dict.get(sym)
                        if not price or price <= 0:
                            price = _last_price.get(sym, 0)  # [#4] 缺失时用上一笔有效价
                        if price > 0:
                            shares = position[sym]
                            sell_value = shares * price
                            cash_balance += sell_value
                            stamps_sell += sell_value * ST_TAX_RATE
                            entry_p = position_cost.get(sym, price)
                            pnl = shares * (price - entry_p)
                            trade_log.append({
                                "symbol": sym, "shares": shares,
                                "entry_price": round(entry_p, 4),
                                "exit_price": round(price, 4),
                                "pnl": round(pnl, 2)
                            })
                        del position[sym]
                        if sym in position_cost:
                            del position_cost[sym]

                # —— 按目标权重分配现金 ——
                for _, row in target_weights.iterrows():
                    sym = row['symbol']
                    target_value = total_value * row['weight']
                    if sym in position:
                        price = price_dict.get(sym)
                        if not price or price <= 0:
                            price = _last_price.get(sym, 0)
                        if price > 0:
                            cur_value = position[sym] * price
                            cash_balance += cur_value
                            cash_balance -= target_value
                    else:
                        cash_balance -= target_value

                # —— 交易费用 ——
                turnover = 0
                if prev_weights is not None and len(target_weights) > 0:
                    merged = prev_weights.merge(
                        target_weights, on='symbol', how='outer', suffixes=('_prev', '_cur')
                    ).fillna(0)
                    turnover = (merged['weight_prev'] - merged['weight_cur']).abs().sum() / 2
                    trade_volume = turnover * total_value
                    trade_cost = trade_volume * TRADE_FEE_RATE
                else:
                    trade_cost = total_value * TRADE_FEE_RATE

                # —— 构建新持仓 ——
                new_position = {}
                new_position_cost = {}
                cash_spent = 0.0
                for _, row in target_weights.iterrows():
                    sym = row['symbol']
                    effective_value = total_value * row['weight']
                    if effective_value <= 0:
                        continue
                    buy_price = price_dict.get(sym)
                    if not buy_price or buy_price <= 0:
                        buy_price = _last_price.get(sym, 0)
                    if buy_price > 0:
                        price = buy_price * (1 + SLIPPAGE)
                        raw_shares = effective_value / price
                        if sym.startswith('688'):
                            shares = int(raw_shares) if raw_shares >= 200 else 0
                        elif sym.startswith('8'):
                            shares = int(raw_shares) if raw_shares >= 100 else 0
                        else:
                            shares = int(raw_shares / 100) * 100
                        if shares > 0:
                            new_position[sym] = shares
                            new_position_cost[sym] = price
                            cash_spent += shares * price

                position = new_position
                position_cost = new_position_cost

                cash_residual = total_value - cash_spent - trade_cost - stamps_sell
                if cash_residual < 0:
                    cash_residual = 0.0

                pending_signals = None
                pending_snapshot = None

            # ────────────────────────────────────────────
            # Step B: 调仓日生成信号 (T日, 执行推迟到T+1)
            # ────────────────────────────────────────────
            if current_date in rebalance_set:
                tradable = self._filter_tradable(today_data)

                if len(tradable) > 0:
                    try:
                        signals = signal_fn(tradable)
                    except Exception as e:
                        print(f"    ⚠️ 策略在 {current_date.date()} 出错: {e}")
                        signals = None

                    if signals is not None and len(signals) > 0 and 'weight' in signals.columns:
                        target_weights = signals[['symbol', 'weight']].copy()
                        target_weights['weight'] = target_weights['weight'] / target_weights['weight'].sum()
                        weights_history.append(target_weights.copy())

                        # —— 调仓前持仓快照 (在T日截取) ——
                        snapshot = []
                        nav_for_weights = nav
                        for sym, shr in position.items():
                            p = price_dict.get(sym, 0)
                            if p <= 0:
                                p = _last_price.get(sym, 0)  # [#4]
                            val = shr * p
                            cost = position_cost.get(sym, p)
                            pnl = shr * (p - cost)
                            pnl_pct = (p - cost) / cost * 100 if cost > 0 else 0
                            wgt = val / nav_for_weights * 100 if nav_for_weights > 0 else 0
                            vol = 0; amt = 0
                            if today_data is not None and len(today_data) > 0:
                                row = today_data[today_data['symbol'] == sym]
                                if len(row) > 0:
                                    vol = float(row['volume'].iloc[0]) if 'volume' in row.columns else 0
                                    amt = float(row['total_turnover'].iloc[0]) if 'total_turnover' in row.columns else 0
                            snapshot.append({
                                "symbol": sym, "shares": int(shr),
                                "price": round(p, 2), "value": round(val, 2),
                                "weight": round(wgt, 2), "pnl": round(pnl, 2),
                                "pnl_pct": round(pnl_pct, 2),
                                "volume_wan": round(vol / 10000, 2),
                                "amount_wan": round(amt / 10000, 2)
                            })
                        snapshot.sort(key=lambda x: x['value'], reverse=True)

                        pending_snapshot = {
                            "date": current_date.strftime("%Y-%m-%d"),
                            "nav": round(nav, 2),
                            "holdings": snapshot
                        }

                        pending_signals = target_weights
                        prev_weights = target_weights

            # ────────────────────────────────────────────
            # Step C: 每日净值计算 (逐日盯市)
            # [#3] 无论是否调仓/报错/空信号，都重估现有持仓
            # [#4] 价格缺失时沿用上笔有效价格, 而非0估值
            # ────────────────────────────────────────────
            if len(position) > 0:
                position_value = 0.0
                for sym, shares in position.items():
                    p = price_dict.get(sym, 0)
                    if p <= 0:
                        p = _last_price.get(sym, 0)  # [#4] 沿用最后有效价
                        if p <= 0:
                            p = position_cost.get(sym, 0)  # 兜底: 成本价
                    position_value += shares * p
                total_nav = position_value + cash_residual
                nav = total_nav if total_nav > 0 else nav
            # (空仓时 nav 沿用初始资金/前一日净值, 即纯现金状态)

            daily_values.append(nav)
            nav_series.append((current_date, nav))

            if i % 200 == 0:
                print(f"    进度: {i}/{len(trade_dates)}  ({i/len(trade_dates)*100:.0f}%)")

        # 构建净值序列
        nav_df = pd.DataFrame(nav_series, columns=['date', 'nav'])
        nav_df.set_index('date', inplace=True)
        # 添加基准列
        if hasattr(self, '_benchmark_nav') and self._benchmark_nav is not None:
            nav_df['benchmark'] = self._benchmark_nav.values

        # 计算绩效指标
        metrics = compute_metrics(nav_df['nav'])

        # 计算换手率 (非调仓日不计算)
        if hasattr(self, '_rebalance_freq') and len(weights_history) > 1:
            avg_turnover = self._compute_turnover(weights_history)
            metrics["单次调仓换手率"] = f"{avg_turnover:.2%}"
            # 年化换手率 = 每次调仓换手率 × (年交易日数 / 调仓频率)
            annual_turnover = avg_turnover * (252 / self._rebalance_freq)
            metrics["年化换手率"] = f"{annual_turnover:.0%}"

        # 存储逐笔交易记录和持仓快照
        self._trade_log = trade_log
        self._position_snapshots = position_snapshots

        # 保存调仓报告 CSV
        self._save_rebalance_csv(name, position_snapshots)
        
        # 计算交易统计 (盈亏比、胜率等)
        if trade_log:
            wins = [t for t in trade_log if t['pnl'] > 0]
            losses = [t for t in trade_log if t['pnl'] < 0]
            n_wins = len(wins)
            n_losses = len(losses)
            metrics["交易次数"] = str(len(trade_log))
            metrics["盈利次数"] = str(n_wins)
            metrics["亏损次数"] = str(n_losses)
            if n_losses > 0:
                avg_win = sum(t['pnl'] for t in wins) / n_wins if n_wins > 0 else 0
                avg_loss = abs(sum(t['pnl'] for t in losses) / n_losses) if n_losses > 0 else 0
                if avg_loss > 0:
                    metrics["盈亏比"] = f"{avg_win / avg_loss:.2f}"
                else:
                    metrics["盈亏比"] = "N/A"
            # 按笔胜率
            total_trades = n_wins + n_losses
            metrics["交易胜率"] = f"{n_wins / total_trades:.2%}" if total_trades > 0 else "N/A"
        else:
            metrics["交易次数"] = "0"
        
        return nav_df, metrics

    def _save_rebalance_csv(self, name, position_snapshots):
        """将调仓明细保存为 CSV: date, symbol, weight, price, value"""
        if not position_snapshots:
            return
        rows = []
        for snap in position_snapshots:
            d = snap["date"]
            for h in snap.get("holdings", []):
                rows.append({
                    "date": d,
                    "symbol": h["symbol"],
                    "shares": h["shares"],
                    "weight": h["weight"],
                    "price": h["price"],
                    "value": h["value"],
                })
        if not rows:
            return
        df = pd.DataFrame(rows)

        safe_name = name.replace("/", "_").replace(" ", "_")
        out_path = os.path.join(RESULTS_DIR, f"{safe_name}_rebalance.csv")
        os.makedirs(RESULTS_DIR, exist_ok=True)
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"    调仓报告: {out_path}  ({len(df)} 条)")

    def _compute_turnover(self, weights_history):
        """计算平均换手率"""
        turnovers = []
        for i in range(1, len(weights_history)):
            prev = weights_history[i-1]
            cur = weights_history[i]
            merged = prev.merge(cur, on='symbol', how='outer', suffixes=('_p', '_c')).fillna(0)
            turnover = (merged['weight_p'] - merged['weight_c']).abs().sum() / 2
            turnovers.append(turnover)
        return np.mean(turnovers) if turnovers else 0

    def run_all(self, strategy_map, rebalance_freq=5,
                start_date=None, end_date=None):
        """
        批量跑所有策略

        参数:
            strategy_map: {策略名: signal函数}
            rebalance_freq: 调仓频率
            start_date: 自定义回测起始日期 (str/date/datetime)
            end_date:   自定义回测结束日期 (str/date/datetime)
        返回:
            all_nav: {策略名: nav_series}
            all_metrics: {策略名: metrics_dict}
        """
        all_nav = {}
        all_metrics = {}

        for name, fn in strategy_map.items():
            try:
                nav_df, metrics = self.run_strategy(
                    fn, name, rebalance_freq,
                    start_date=start_date, end_date=end_date)
                all_nav[name] = nav_df
                all_metrics[name] = metrics
            except Exception as e:
                print(f"\n  ❌ {name} 回测失败: {e}")
                all_metrics[name] = {"错误": str(e)}

        # 输出对比报告
        report = format_report(all_metrics)
        print("\n" + report)

        return all_nav, all_metrics, report


def main():
    """
    主入口: 发现策略 → 跑回测 → 保存结果
    """
    from strategies import discover_strategies

    print("=" * 50)
    print("🚀 开始批量回测")
    print(f"   数据目录: {DATA_DIR}")
    print(f"   回测窗口: {BACKTEST_YEARS}年")
    print(f"   初始资金: {INIT_CAPITAL:,.0f}")
    print("=" * 50)

    # 初始化引擎
    engine = BacktestEngine()

    # 发现策略
    strategies = discover_strategies()
    if not strategies:
        print("\n⚠️  没有找到策略文件!")
        print(f"   请在 {STRATEGY_DIR} 下创建策略文件")
        print(f"   参考模板: strategies/template.py")
        return

    print(f"\n发现 {len(strategies)} 个策略:")
    for name in strategies:
        print(f"  - {name}")

    # 跑回测
    all_nav, all_metrics, report = engine.run_all(strategies)

    # 保存结果
    today_str = datetime.now().strftime("%Y-%m-%d")
    result_dir = os.path.join(RESULTS_DIR, today_str)
    os.makedirs(result_dir, exist_ok=True)

    # 保存报告
    report_path = os.path.join(result_dir, "report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 保存净值曲线
    for name, nav_df in all_nav.items():
        safe_name = name.replace("/", "_").replace(" ", "_")
        nav_df.to_csv(os.path.join(result_dir, f"{safe_name}_nav.csv"))
        nav_df.to_parquet(os.path.join(result_dir, f"{safe_name}_nav.parquet"))

    print(f"\n✅ 结果已保存: {result_dir}")
    print(f"   报告: {report_path}")

    return all_nav, all_metrics


if __name__ == "__main__":
    main()
