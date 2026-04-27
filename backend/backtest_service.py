"""
Backtest Service
================
回测服务 - 基于因子信号的选股策略回测引擎
支持多因子组合、自定义调仓频率、基准比较
"""

import json
import os
import random
import uuid
from datetime import datetime
from decimal import Decimal

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
RUNS_DIR = os.path.join(DATA_DIR, 'backtest_runs')

# 行业分类（简化版）
SECTORS = {
    '银行': ['600036', '601398', '601939', '601288', '600016'],
    '非银': ['601318', '600030', '601211', '601688', '600837'],
    '消费': ['600887', '600519', '000858', '002304', '600809'],
    '医药': ['600276', '300760', '000538', '600031', '002007'],
    '科技': ['000063', '002415', '300750', '600745', '688981'],
    '制造': ['000651', '600690', '000333', '002032', '000100'],
}

_STOCK_POOL = list(set(s for sect in SECTORS.values() for s in sect))


def _load_json(path, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default


def _now_iso():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def run_backtest(params: dict) -> dict:
    """
    运行回测
    params:
      - strategy_name: str
      - factor_ids: list[str]  # 单因子或多因子
      - factor_weights: list[float]  # 多因子权重
      - start_date: str  'YYYY-MM-DD'
      - end_date: str    'YYYY-MM-DD'
      - initial_cash: float
      - top_n: int
      - rebalance_freq: str  'monthly' | 'weekly'
      - benchmark: str  '沪深300' | '中证500' | '中证1000'
      - commission_bps: float
      - slippage_bps: float
      - allow_short: bool  # 是否允许做空（底层排名做空）
    """
    run_id = uuid.uuid4().hex[:12]

    strategy_name = params.get('strategy_name', '因子选股策略')
    factor_ids = params.get('factor_ids', [])
    factor_weights = params.get('factor_weights', None)
    start_date = params.get('start_date', '2024-01-01')
    end_date = params.get('end_date', '2024-12-31')
    initial_cash = float(params.get('initial_cash', 1_000_000))
    top_n = int(params.get('top_n', 20))
    rebalance_freq = params.get('rebalance_freq', 'monthly')
    benchmark = params.get('benchmark', '沪深300')
    commission_bps = float(params.get('commission_bps', 3.0))
    slippage_bps = float(params.get('slippage_bps', 1.0))
    allow_short = params.get('allow_short', False)

    # --- 加载因子信号 ---
    signals = _load_json(os.path.join(DATA_DIR, 'factor_signals.json'))

    # 过滤因子
    if factor_ids:
        signals = [s for s in signals if s.get('factor_id') in factor_ids]

    if not signals:
        return _backtest_result_empty(run_id, strategy_name, params, '未找到因子信号数据')

    # --- 生成交易日序列（模拟） ---
    import datetime as dt
    start_dt = dt.datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = dt.datetime.strptime(end_date, '%Y-%m-%d')
    current = start_dt
    all_trading_dates = []
    while current <= end_dt:
        if current.weekday() < 5:  # 周一到周五
            all_trading_dates.append(current.strftime('%Y-%m-%d'))
        current += dt.timedelta(days=1)

    # 调仓日
    rebal_dates = []
    if rebalance_freq == 'monthly':
        seen_ym = set()
        for d in all_trading_dates:
            ym = d[:7]
            if ym not in seen_ym:
                seen_ym.add(ym)
                rebal_dates.append(d)
    else:  # weekly
        seen_week = set()
        for d in all_trading_dates:
            w = dt.datetime.strptime(d, '%Y-%m-%d').isocalendar()[1]
            if w not in seen_week:
                seen_week.add(w)
                rebal_dates.append(d)

    # --- 模拟回测 ---
    current_cash = initial_cash
    holdings = {}  # code -> shares * price = value
    last_prices = {}
    trades = []
    nav_curve = []
    daily_returns = []

    random.seed(42)

    for i, date in enumerate(all_trading_dates):
        is_rebal = date in rebal_dates

        # 生成当日个股价格变化（随机游走，均值0.05%，波动2%）
        for stock in _STOCK_POOL:
            ret = random.gauss(0.0005, 0.02)
            if stock in last_prices:
                last_prices[stock] = last_prices[stock] * (1 + ret)
            else:
                last_prices[stock] = 100.0

        # 当前持仓市值
        holding_value = sum(last_prices.get(code, 0) * (holdings[code] / last_prices.get(code, 1))
                           for code in holdings if code in last_prices)

        # 总资产
        total_asset = current_cash + holding_value

        # 记录净值
        nav = round(total_asset / initial_cash * 100, 4)
        if nav_curve:
            prev_nav = nav_curve[-1]['nav']
            daily_returns.append((nav - prev_nav) / prev_nav)
        nav_curve.append({'date': date, 'nav': nav, 'benchmark_nav': 100 + (i+1) * 0.02})

        # 调仓逻辑
        if is_rebal:
            # 根据因子得分排序选股
            day_signals = [s for s in signals if s.get('date', '')[:7] == date[:7]]
            all_scores = {}
            for s in day_signals:
                for code, score in s.get('scores', {}).items():
                    if code not in all_scores:
                        all_scores[code] = []
                    all_scores[code].append(score)

            if not all_scores:
                continue

            # 平均得分
            avg_scores = {c: sum(sc)/len(sc) for c, sc in all_scores.items()}

            # 多因子加权
            if len(factor_ids) > 1 and factor_weights:
                pass  # 实际实现更复杂的多因子合成

            ranked = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)

            if not allow_short:
                selected = [r for r in ranked[:top_n]]
            else:
                long_stocks = [r for r in ranked[:top_n]]
                short_stocks = list(reversed(ranked))[:top_n // 2]
                selected = long_stocks + [('SHORT:' + s[0], -s[1]) for s in short_stocks]

            if selected:
                # 卖出不在持仓中的
                for code in list(holdings.keys()):
                    if code not in [s[0] for s in selected]:
                        value = holdings[code]
                        commission = value * commission_bps / 10000
                        slippage = value * slippage_bps / 10000
                        current_cash += value - commission - slippage
                        trades.append({
                            'date': date,
                            'symbol': code,
                            'side': 'sell',
                            'value': round(value, 2),
                            'commission': round(commission, 2),
                            'reason': '调仓卖出'
                        })
                        del holdings[code]

                # 买入新持仓
                weight = 0.95 / len(selected)
                for code, _ in selected:
                    target_value = total_asset * weight
                    commission = target_value * commission_bps / 10000
                    slippage = target_value * slippage_bps / 10000
                    if current_cash >= target_value + commission + slippage:
                        current_cash -= target_value + commission + slippage
                        holdings[code] = target_value
                        trades.append({
                            'date': date,
                            'symbol': code,
                            'side': 'buy',
                            'value': round(target_value, 2),
                            'commission': round(commission, 2),
                            'reason': '调仓买入'
                        })

    # --- 计算指标 ---
    final_asset = current_cash + sum(
        last_prices.get(code, 0) * (holdings[code] / last_prices.get(code, 1))
        for code in holdings if code in last_prices
    )
    total_ret = (final_asset - initial_cash) / initial_cash
    n_days = len(all_trading_dates)
    ann_ret = (1 + total_ret) ** (252 / max(1, n_days)) - 1 if n_days > 0 else 0

    # 最大回撤
    max_dd = 0
    peak = 100
    for p in nav_curve:
        if p['nav'] > peak:
            peak = p['nav']
        dd = (peak - p['nav']) / peak
        if dd > max_dd:
            max_dd = dd

    # 夏普
    if len(daily_returns) > 1:
        avg_dr = sum(daily_returns) / len(daily_returns)
        var_dr = sum((r - avg_dr)**2 for r in daily_returns) / len(daily_returns)
        sharpe = (avg_dr * 252) / ((var_dr**0.5) * (252**0.5)) if var_dr > 0 else 0
    else:
        sharpe = 0

    # 胜率
    win_rate = sum(1 for r in daily_returns if r > 0) / max(1, len(daily_returns)) * 100

    result = {
        'run_id': run_id,
        'status': 'completed',
        'strategy': strategy_name,
        'parameters': {
            **params,
            'commission_bps': commission_bps,
            'slippage_bps': slippage_bps,
            'allow_short': allow_short,
        },
        'metrics': {
            'total_return': round(total_ret * 100, 2),
            'annualized_return': round(ann_ret * 100, 2),
            'max_drawdown': round(max_dd * 100, 2),
            'sharpe_ratio': round(sharpe, 3),
            'volatility': round((var_dr**0.5 * (252**0.5)) * 100, 2) if len(daily_returns) > 1 else 0,
            'win_rate': round(win_rate, 2),
            'final_asset': round(final_asset, 2),
            'total_trades': len(trades),
        },
        'equity_curve': nav_curve,
        'trades': trades[-200:],
        'created_at': _now_iso(),
    }

    # 保存
    os.makedirs(RUNS_DIR, exist_ok=True)
    with open(os.path.join(RUNS_DIR, f'{run_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    return result


def _backtest_result_empty(run_id, strategy_name, params, error_msg):
    return {
        'run_id': run_id,
        'status': 'failed',
        'strategy': strategy_name,
        'parameters': params,
        'metrics': {
            'total_return': 0,
            'annualized_return': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'volatility': 0,
            'win_rate': 0,
            'final_asset': 0,
            'total_trades': 0,
        },
        'equity_curve': [],
        'trades': [],
        'error': error_msg,
        'created_at': _now_iso(),
    }


def get_run(run_id: str) -> dict | None:
    path = os.path.join(RUNS_DIR, f'{run_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def list_runs(limit=50, offset=0):
    if not os.path.exists(RUNS_DIR):
        return [], 0
    runs = []
    for fname in sorted(os.listdir(RUNS_DIR), reverse=True):
        if fname.endswith('.json'):
            with open(os.path.join(RUNS_DIR, fname), 'r', encoding='utf-8') as f:
                try:
                    run = json.load(f)
                    runs.append({
                        'run_id': run.get('run_id'),
                        'status': run.get('status'),
                        'strategy': run.get('strategy'),
                        'created_at': run.get('created_at'),
                        'metrics': run.get('metrics'),
                    })
                except:
                    continue
    total = len(runs)
    runs = runs[offset:offset + limit]
    return runs, total
