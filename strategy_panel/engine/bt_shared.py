"""
Backtrader 共享运行器 — 所有策略统一使用
- AShareCommission: A股万3+千1印花税+最低5元
- PortfolioStrategy: 通用信号跟随策略 (T+0 收盘价成交)
- run_backtrader(): 一站式运行回测
"""
import sys, os, json
import pandas as pd
import numpy as np
import backtrader as bt

COMMISSION = 0.0003      # 万3
STAMP_DUTY = 0.001       # 千1(卖)
MIN_COMMISSION = 5.0     # 最低5元
SLIPPAGE = 0.001         # 0.1%
INITIAL_CASH = 1_000_000
DATA_DIR = r"D:\bigquant\custom_engine\data"


class AShareCommission(bt.CommInfoBase):
    """A股手续费: 万3双边 + 千1印花税(卖) + 最低5元"""
    params = (
        ('commission', COMMISSION),
        ('stamp_duty', STAMP_DUTY),
        ('min_commission', MIN_COMMISSION),
    )

    def _getcommission(self, size, price, pseudoexec=False):
        if size == 0:
            return 0
        comm = max(abs(size) * price * self.p.commission, self.p.min_commission)
        if size < 0:
            comm += abs(size) * price * self.p.stamp_duty
        return comm


class NavRecorder(bt.Analyzer):
    """记录每日净值（同一日多次触发时只保留第一次，忽略后续同日的重复调用）"""
    def __init__(self):
        self.dates = []
        self.navs = []

    def notify_cashvalue(self, cash, value):
        dt = str(self.strategy.data.datetime.date())
        if self.dates and dt == self.dates[-1]:
            return  # 忽略同日重复调用
        self.dates.append(dt)
        self.navs.append(round(value, 2))


class PortfolioStrategy(bt.Strategy):
    """
    通用信号跟随策略
    - signal_map: {date_str: {symbol: weight}}
    - 信号日调仓到目标权重; 非信号日持仓不动
    - T+0: coc=True 时当日收盘价成交
    """
    params = (
        ('signal_map', {}),
        ('signal_start', None),
    )

    def __init__(self):
        self.trade_log = []           # [{date, symbol, side, price, qty, amount, fee}]
        self.position_snapshots = []  # [{date, holdings: [{symbol, weight, qty, price, value}]}]

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            # 记录成交
            sym = order.data._name if order.data else '?'
            dt = str(self.data.datetime.date())
            price = order.executed.price
            qty = abs(order.executed.size)
            amount = round(price * qty, 2)
            side = 'buy' if order.isbuy() else 'sell'
            # 费用: 万3佣金 + 千1印花税(卖), 最低5元
            fee = max(round(amount * COMMISSION, 2), MIN_COMMISSION)
            if side == 'sell':
                fee += round(amount * STAMP_DUTY, 2)
            self.trade_log.append({
                'date': dt,
                'symbol': sym,
                'side': side,
                'price': round(price, 2),
                'qty': qty,
                'amount': amount,
                'fee': round(fee, 2),
            })
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            sym = order.data._name if order.data else '?'
            dt = self.data.datetime.date(0)
            if dt >= pd.Timestamp(self.p.signal_start).date():
                print(f"    ⚠️ [{dt}] {sym} {order.getstatusname()}")

    def _safe_data(self, sym):
        """安全获取 data feed，如果股票不在 data feeds 中返回 None"""
        try:
            return self.getdatabyname(sym)
        except KeyError:
            return None

    def next(self):
        dt = self.data.datetime.date(0)
        dt_str = str(dt)

        # 信号开始前不动
        if self.p.signal_start and dt < pd.Timestamp(self.p.signal_start).date():
            return

        weights = self.p.signal_map.get(dt_str)
        if weights is None:
            return

        total_value = self.broker.getvalue()

        # 收集当前持仓
        current_positions = {}
        for d in self.datas:
            pos = self.getposition(d).size
            if pos != 0:
                current_positions[d._name] = pos

        # 先卖: 清仓不在新信号中的
        for sym in list(current_positions.keys()):
            if sym not in weights:
                d = self._safe_data(sym)
                if d is not None:
                    self.order_target_size(data=d, target=0)

        # 后买: 按价格排序, 控制现金
        buy_list = [(sym, w, self._safe_data(sym)) for sym, w in weights.items()]
        buy_list = [(s, w, d) for s, w, d in buy_list if d is not None and d.close[0] > 0]
        buy_list.sort(key=lambda x: x[2].close[0])

        for sym, weight, data in buy_list:
            price = data.close[0]
            raw = total_value * weight / (price * (1 + SLIPPAGE))
            target = self._lot_size(sym, raw)
            current = current_positions.get(sym, 0)
            if abs(current - target) <= 0:
                continue
            est_cost = target * price * (1 + SLIPPAGE) * (1 + COMMISSION)
            actual_cash = self.broker.getcash()
            if est_cost > actual_cash * 0.98 and target > 0:
                continue
            self.order_target_size(data=data, target=target)

        # ── 记录调仓后的持仓快照 ──
        self._snapshot_positions(dt_str, weights)

    def _snapshot_positions(self, dt_str, target_weights):
        """记录当前持仓快照"""
        total_value = self.broker.getvalue()
        if total_value <= 0:
            return
        holdings = []
        for d in self.datas:
            pos = self.getposition(d).size
            if pos != 0 and d.close[0] > 0:
                price = d.close[0]
                value = round(pos * price, 2)
                weight = round(value / total_value, 4)
                holdings.append({
                    'symbol': d._name,
                    'qty': pos,
                    'price': round(price, 2),
                    'value': value,
                    'weight': weight,
                })
        self.position_snapshots.append({
            'date': dt_str,
            'holdings': holdings,
        })

    def _lot_size(self, symbol, raw_shares):
        """
        按交易所交易规则调整买卖数量：
          沪深主板 (000-003, 600-605): 100股起, 100股整数倍, 最大100万股
          创业板   (300-301):        100股起, 100股整数倍, 限价30万/市价15万股（取限价）
          科创板   (688):            200股起, 1股递增,     限价10万/市价5万股（取限价）
          北交所   (4/8开头):        100股起, 1股递增,     最大100万股
        """
        raw = int(raw_shares)
        if raw <= 0:
            return 0

        # ── 科创板 (688) ──
        if symbol.startswith('688'):
            if raw < 200:
                return 0
            return min(raw, 100_000)   # 限价上限10万股（coc 近似限价）

        # ── 北交所 (4/8开头) ──
        if symbol.startswith('4') or symbol.startswith('8'):
            if raw < 100:
                return 0
            return min(raw, 1_000_000)  # 每股递增

        # ── 创业板 (300/301) ──
        if symbol.startswith('300') or symbol.startswith('301'):
            if raw < 100:
                return 0
            lots = (raw // 100) * 100
            return min(lots, 300_000)   # 限价上限30万股

        # ── 沪深主板 (其他: 000-003, 600-605 等) ──
        if raw < 100:
            return 0
        lots = (raw // 100) * 100
        return min(lots, 1_000_000)


def run_backtrader(signal_map, sorted_dates, kline_adj_path=DATA_DIR, 
                   signal_start=None, preloaded_kline=None,
                   initial_cash=INITIAL_CASH, verbose=True):
    """
    一站式 backtrader 回测
    
    参数:
        signal_map: {date_str: {symbol: weight}}  每日持仓目标
        sorted_dates: 信号日期列表
        kline_adj_path: kline_adj.parquet 所在目录 (若未提供 preloaded_kline)
        signal_start: 第一个信号日 (之前持现金)
        preloaded_kline: 可选, 预加载的 kline DataFrame (避免重复读文件)
        initial_cash: 初始资金
        verbose: 是否打印进度
    
    返回:
        (dates, navs)  日期列表和净值列表
    """
    if signal_start is None and sorted_dates:
        signal_start = sorted_dates[0]
    
    # 1. 收集所有涉及股票
    all_symbols = set()
    for w in signal_map.values():
        all_symbols.update(w.keys())
    
    if verbose:
        print(f"  信号股票: {len(all_symbols)}只")
    
    # 2. 加载/过滤 K 线
    if preloaded_kline is not None:
        kline = preloaded_kline  # 不加 .copy()，调用方不再使用此变量
    else:
        kline_path = os.path.join(kline_adj_path, "kline_adj.parquet")
        kline = pd.read_parquet(kline_path)
        if kline['trade_date'].dtype.name == 'uint16':
            kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit='D', origin='unix')
    
    # 用复权价（添加引用列，不复制数据）
    kline['close'] = kline['close_adj']
    kline['open']  = kline['open_adj']
    kline['high']  = kline['high_adj']
    kline['low']   = kline['low_adj']
    
    # 日期范围: 信号期 + 前60天预热（过滤掉 99% 的行后才 copy）
    start = pd.Timestamp(signal_start) - pd.Timedelta(days=60)
    end = kline['trade_date'].max()
    mask = (kline['trade_date'] >= start) & (kline['trade_date'] <= end)
    kline = kline[mask].copy()  # 此时只剩 ~20 万行，copy 开销可以忽略
    
    # 只要涉及的股票
    available = all_symbols & set(kline['symbol'].unique())
    kline = kline[kline['symbol'].isin(available)]
    
    # 过滤掉数据起始日期太晚的股票 (会导致 Backtrader 对齐到最晚日期)
    # 只保留数据起始日期 <= 首个信号日的股票（不要求覆盖预热期）
    sym_first_dates = kline.groupby('symbol')['trade_date'].min()
    early_syms = set(sym_first_dates[sym_first_dates <= pd.Timestamp(signal_start)].index)
    kline = kline[kline['symbol'].isin(early_syms)]
    
    if verbose:
        print(f"  K线: {len(kline)}行, {kline['symbol'].nunique()}只, "
              f"{kline['trade_date'].min().date()}→{kline['trade_date'].max().date()}")
    
    # 3. 构造 cerebro
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.set_checksubmit(False)
    cerebro.broker.addcommissioninfo(AShareCommission())
    cerebro.broker.set_coc(True)   # T+0: 当日收盘价成交
    
    sym_count = 0
    for sym, group in kline.groupby('symbol'):
        df = group.sort_values('trade_date').copy()
        df = df.set_index('trade_date')
        if len(df) < 5:
            continue
        data = bt.feeds.PandasData(dataname=df[['open', 'high', 'low', 'close', 'volume']])
        data._name = sym
        cerebro.adddata(data)
        sym_count += 1
    
    if verbose:
        print(f"  加载 {sym_count} 只到 Backtrader")
    
    cerebro.addstrategy(PortfolioStrategy, signal_map=signal_map, signal_start=signal_start)
    cerebro.addanalyzer(NavRecorder, _name='nav')
    
    if verbose:
        print(f"  回测中...")
    
    results = cerebro.run()
    
    # 4. 提取结果
    strat = results[0]
    nav_rec = strat.analyzers.nav
    return nav_rec.dates, nav_rec.navs, strat.trade_log, strat.position_snapshots


def compute_metrics(dates, navs, initial_cash=INITIAL_CASH):
    """从净值序列计算指标"""
    nav_arr = np.array(navs) / initial_cash
    if len(nav_arr) < 2:
        return {}
    
    daily_ret = nav_arr[1:] / nav_arr[:-1] - 1
    n_days = len(daily_ret)
    
    ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
    sharpe = float(np.mean(daily_ret) / np.std(daily_ret, ddof=1) * np.sqrt(252)) if ann_vol > 0 else 0
    peak = np.maximum.accumulate(nav_arr)
    dd = (nav_arr - peak) / peak * 100
    mdd = float(np.min(dd))
    total_years = n_days / 252
    ann_ret = float(nav_arr[-1] ** (1 / total_years) - 1) * 100 if total_years > 0 else 0
    tot_ret = float((nav_arr[-1] - 1) * 100)
    
    return {
        'annual_return': round(ann_ret, 2),
        'total_return': round(tot_ret, 2),
        'sharpe': round(sharpe, 2),
        'max_drawdown': round(abs(mdd), 2),
        'annual_vol': round(ann_vol * 100, 2),
        'total_value_10k': round(10000 * nav_arr[-1], 2),
    }
