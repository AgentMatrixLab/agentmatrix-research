"""
Factor Library Service
=======================
因子库核心服务 - 数据模型 + JSON持久化 + 搜索/评分/IC分析
后续可无缝迁移到 Supabase 作为真值层

数据结构设计（对齐 research-core 中的合约）：
  - Factor: 因子定义（名称、描述、计算逻辑、分类等）
  - FactorSignal: 因子在某时间点生成的信号（个股评分）
  - FactorEval: 因子评估指标（IC、IR、收益等）
"""

import os
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Any
from dataclasses import dataclass, field, asdict
from decimal import Decimal


# ============================================================
# 数据目录
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
FACTORS_FILE = os.path.join(DATA_DIR, 'factors.json')
SIGNALS_FILE = os.path.join(DATA_DIR, 'factor_signals.json')
EVALS_FILE = os.path.join(DATA_DIR, 'factor_evals.json')
RUNS_DIR = os.path.join(DATA_DIR, 'backtest_runs')


# ============================================================
# JSON 持久化工具
# ============================================================
def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RUNS_DIR, exist_ok=True)


def _load_json(path: str, default: list = None) -> list:
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default


def _save_json(path: str, data: list):
    _ensure_data_dir()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _gen_id(seed: str = None) -> str:
    """生成唯一ID"""
    if seed:
        return hashlib.md5(seed.encode()).hexdigest()[:12]
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


# ============================================================
# 因子模型
# ============================================================

FACTOR_CATEGORIES = [
    '价值', '成长', '质量', '动量', '反转',
    '波动率', '流动性', '规模', '技术', '情绪',
    '宏观', '另类', '复合', '自定义'
]

FACTOR_FREQUENCIES = ['daily', 'weekly', 'monthly', 'quarterly']


def create_factor(
    name: str,
    description: str,
    category: str = '自定义',
    formula: str = '',
    parameters: dict = None,
    frequency: str = 'daily',
    universe: str = '全部A股',
    tags: list = None,
    source: str = 'manual',
    references: str = '',
) -> dict:
    """创建新的因子"""
    factor = {
        'id': _gen_id(name),
        'name': name,
        'description': description,
        'category': category if category in FACTOR_CATEGORIES else '自定义',
        'formula': formula,
        'parameters': parameters or {},
        'frequency': frequency,
        'universe': universe,
        'tags': tags or [],
        'source': source,
        'references': references,
        'status': 'active',  # active | deprecated | testing
        'version': 1,
        'created_at': _now_iso(),
        'updated_at': _now_iso(),
        'last_eval_id': None,
    }
    return factor


def list_factors(
    category: str = None,
    status: str = None,
    tag: str = None,
    search: str = None,
    sort_by: str = 'updated_at',
    sort_desc: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list, int]:
    """
    列出因子，支持分类/状态/标签/搜索过滤，返回 (factors, total_count)
    """
    factors = _load_json(FACTORS_FILE)

    if category:
        factors = [f for f in factors if f.get('category') == category]
    if status:
        factors = [f for f in factors if f.get('status') == status]
    if tag:
        factors = [f for f in factors if tag in f.get('tags', [])]
    if search:
        s = search.lower()
        factors = [
            f for f in factors
            if s in f.get('name', '').lower()
            or s in f.get('description', '').lower()
            or s in f.get('tags', [])
        ]

    # 排序
    reverse = sort_desc
    if sort_by == 'name':
        factors.sort(key=lambda f: f.get('name', ''), reverse=reverse)
    elif sort_by == 'created_at':
        factors.sort(key=lambda f: f.get('created_at', ''), reverse=reverse)
    else:
        factors.sort(key=lambda f: f.get('updated_at', ''), reverse=reverse)

    total = len(factors)
    factors = factors[offset:offset + limit]
    return factors, total


def get_factor(factor_id: str) -> dict | None:
    factors = _load_json(FACTORS_FILE)
    for f in factors:
        if f['id'] == factor_id:
            return f
    return None


def save_factor(factor: dict) -> dict:
    """创建或更新因子"""
    factors = _load_json(FACTORS_FILE)
    existing_idx = None
    for i, f in enumerate(factors):
        if f['id'] == factor['id']:
            existing_idx = i
            break

    if existing_idx is not None:
        factor['updated_at'] = _now_iso()
        factor['version'] = factors[existing_idx].get('version', 1) + 1
        factors[existing_idx] = factor
    else:
        factors.append(factor)

    _save_json(FACTORS_FILE, factors)
    return factor


def delete_factor(factor_id: str) -> bool:
    factors = _load_json(FACTORS_FILE)
    new_factors = [f for f in factors if f['id'] != factor_id]
    if len(new_factors) == len(factors):
        return False
    _save_json(FACTORS_FILE, new_factors)
    return True


# ============================================================
# 因子信号模型
# ============================================================

def create_signal(
    factor_id: str,
    date: str,
    scores: dict[str, float],
    coverage: int = None,
    metadata: dict = None,
) -> dict:
    """
    创建因子信号记录
    scores: { stock_code: score_value, ... }
    """
    signal = {
        'id': _gen_id(f'{factor_id}_{date}'),
        'factor_id': factor_id,
        'date': date,
        'scores': scores,
        'coverage': coverage or len(scores),
        'metadata': metadata or {},
        'created_at': _now_iso(),
    }
    return signal


def save_signal(signal: dict):
    signals = _load_json(SIGNALS_FILE)
    signals.append(signal)
    _save_json(SIGNALS_FILE, signals)


def list_signals(
    factor_id: str = None,
    date_from: str = None,
    date_to: str = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list, int]:
    signals = _load_json(SIGNALS_FILE)
    if factor_id:
        signals = [s for s in signals if s.get('factor_id') == factor_id]
    if date_from:
        signals = [s for s in signals if s.get('date', '') >= date_from]
    if date_to:
        signals = [s for s in signals if s.get('date', '') <= date_to]
    signals.sort(key=lambda s: s.get('date', ''), reverse=True)
    total = len(signals)
    signals = signals[offset:offset + limit]
    return signals, total


# ============================================================
# 因子评估模型
# ============================================================

def create_eval(
    factor_id: str,
    period: str = '1m',
    ic: float = None,
    rank_ic: float = None,
    ir: float = None,
    total_return: float = None,
    sharpe: float = None,
    max_drawdown: float = None,
    turnover: float = None,
    metrics: dict = None,
) -> dict:
    """创建因子评估记录"""
    eval_record = {
        'id': _gen_id(f'{factor_id}_{period}_{_now_iso()}'),
        'factor_id': factor_id,
        'period': period,
        'ic': ic,
        'rank_ic': rank_ic,
        'ir': ir,
        'total_return': total_return,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'turnover': turnover,
        'metrics': metrics or {},
        'created_at': _now_iso(),
    }
    return eval_record


def save_eval(eval_record: dict) -> dict:
    evals = _load_json(EVALS_FILE)
    evals.append(eval_record)
    _save_json(EVALS_FILE, evals)

    # 更新因子的 last_eval_id
    factors = _load_json(FACTORS_FILE)
    for f in factors:
        if f['id'] == eval_record['factor_id']:
            f['last_eval_id'] = eval_record['id']
            f['updated_at'] = _now_iso()
            break
    _save_json(FACTORS_FILE, factors)

    return eval_record


def list_evals(
    factor_id: str = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int]:
    evals = _load_json(EVALS_FILE)
    if factor_id:
        evals = [e for e in evals if e.get('factor_id') == factor_id]
    evals.sort(key=lambda e: e.get('created_at', ''), reverse=True)
    total = len(evals)
    evals = evals[offset:offset + limit]
    return evals, total


# ============================================================
# 统计分析
# ============================================================

def get_factor_stats() -> dict:
    """获取因子库统计信息"""
    factors = _load_json(FACTORS_FILE)
    evals = _load_json(EVALS_FILE)
    signals = _load_json(SIGNALS_FILE)

    # 分类统计
    by_category = {}
    for f in factors:
        cat = f.get('category', '未分类')
        by_category[cat] = by_category.get(cat, 0) + 1

    # 状态统计
    by_status = {}
    for f in factors:
        st = f.get('status', 'unknown')
        by_status[st] = by_status.get(st, 0) + 1

    # 最佳因子（按最新IC排序）
    latest_ic = {}
    for e in evals:
        fid = e.get('factor_id')
        ic = e.get('ic')
        if fid and ic is not None:
            if fid not in latest_ic or e.get('created_at', '') > latest_ic[fid].get('created_at', ''):
                latest_ic[fid] = {'ic': ic, 'factor_name': '', 'created_at': e.get('created_at', '')}

    # 补上因子名
    factor_name_map = {f['id']: f['name'] for f in factors}
    for fid in latest_ic:
        latest_ic[fid]['factor_name'] = factor_name_map.get(fid, '未知')

    return {
        'total_factors': len(factors),
        'total_signals': len(signals),
        'total_evals': len(evals),
        'active_factors': by_status.get('active', 0),
        'by_category': by_category,
        'by_status': by_status,
        'factors_with_ic': len(latest_ic),
        'top_ic_factors': sorted(
            [v for v in latest_ic.values() if v['ic'] is not None],
            key=lambda x: abs(x['ic']),
            reverse=True
        )[:10],
    }


# ============================================================
# 伪回测引擎（用于演示/开发验证）
# ============================================================

def run_pseudo_backtest(
    factor_id: str = None,
    strategy_name: str = '因子选股',
    factor_ids: list = None,
    start_date: str = '2024-01-01',
    end_date: str = '2024-12-31',
    initial_cash: float = 1_000_000,
    top_n: int = 20,
    rebalance_freq: str = 'monthly',
    benchmark: str = '沪深300',
) -> dict:
    """
    伪回测引擎 - 基于已有信号模拟因子选股策略
    后续将被 research-core 中的真实回测引擎替代
    """
    run_id = _gen_id()
    signals = _load_json(SIGNALS_FILE)

    # 过滤条件
    if factor_id:
        signals = [s for s in signals if s.get('factor_id') == factor_id]
    if factor_ids:
        signals = [s for s in signals if s.get('factor_id') in factor_ids]

    # 按日期分组
    dates = sorted(set(s.get('date', '') for s in signals
                       if start_date <= s.get('date', '') <= end_date))
    if not dates:
        return _empty_backtest_result(run_id, start_date, end_date, benchmark, 'not_enough_data')

    # 模拟持仓
    nav_curve = []
    current_cash = initial_cash
    current_holdings = {}
    trades = []
    prev_nav = initial_cash

    for i, date in enumerate(dates):
        day_signals = [s for s in signals if s.get('date') == date]

        # 整合因子信号
        all_scores = {}
        for s in day_signals:
            for code, score in s.get('scores', {}).items():
                if code not in all_scores:
                    all_scores[code] = []
                all_scores[code].append(score)

        # 平均评分
        avg_scores = {code: sum(sc) / len(sc) for code, sc in all_scores.items()}

        if not avg_scores:
            nav = prev_nav
            nav_curve.append({'date': date, 'nav': round(nav, 2), 'benchmark_nav': round(prev_nav, 2)})
            continue

        # 取 top_n
        ranked = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

        # 简单调仓模拟
        turnover = 0
        new_holdings = {}
        if ranked:
            weight_per_stock = 0.95 / len(ranked)
            for code, score in ranked:
                weight = weight_per_stock * (1 + 0.2 * (score - ranked[-1][1]) / max(0.001, ranked[0][1] - ranked[-1][1]))
                amount = current_cash * weight
                new_holdings[code] = amount
                if code not in current_holdings:
                    trades.append({
                        'date': date,
                        'symbol': code,
                        'side': 'buy',
                        'amount': round(amount, 2),
                        'reason': f'score={score:.4f}'
                    })
                    turnover += amount

            for code in current_holdings:
                if code not in new_holdings:
                    trades.append({
                        'date': date,
                        'symbol': code,
                        'side': 'sell',
                        'amount': round(current_holdings[code], 2),
                        'reason': 'dropped'
                    })
                    turnover += current_holdings[code]

        # 简单伪收益（模拟 ~0.1% daily return + noise）
        import random
        daily_return = random.gauss(0.001, 0.015)
        nav = current_cash * (1 + daily_return) * (1 - turnover / current_cash * 0.0003)
        current_holdings = new_holdings
        prev_nav = nav

        nav_curve.append({'date': date, 'nav': round(nav, 2), 'benchmark_nav': round(current_cash, 2)})

    # 计算指标
    final_nav = nav_curve[-1]['nav'] if nav_curve else initial_cash
    total_return = (final_nav - initial_cash) / initial_cash
    days = len(dates)
    ann_return = (1 + total_return) ** (252 / days) - 1 if days > 0 else 0

    # 最大回撤
    max_dd = 0
    peak = nav_curve[0]['nav'] if nav_curve else initial_cash
    for p in nav_curve:
        if p['nav'] > peak:
            peak = p['nav']
        dd = (peak - p['nav']) / peak
        if dd > max_dd:
            max_dd = dd

    # 夏普（简化）
    returns = [0]
    for i in range(1, len(nav_curve)):
        r = (nav_curve[i]['nav'] - nav_curve[i-1]['nav']) / nav_curve[i-1]['nav']
        returns.append(r)
    avg_r = sum(returns) / len(returns) if returns else 0
    variance = sum((r - avg_r) ** 2 for r in returns) / len(returns) if returns else 0
    sharpe = (avg_r * 252) / ((variance ** 0.5) * (252 ** 0.5)) if variance > 0 else 0

    result = {
        'run_id': run_id,
        'status': 'completed',
        'strategy': strategy_name,
        'parameters': {
            'factor_id': factor_id,
            'factor_ids': factor_ids,
            'start_date': start_date,
            'end_date': end_date,
            'initial_cash': initial_cash,
            'top_n': top_n,
            'rebalance_freq': rebalance_freq,
            'benchmark': benchmark,
        },
        'metrics': {
            'total_return': round(total_return * 100, 2),
            'annualized_return': round(ann_return * 100, 2),
            'max_drawdown': round(max_dd * 100, 2),
            'sharpe_ratio': round(sharpe, 3),
            'volatility': round(variance ** 0.5 * (252 ** 0.5) * 100, 2),
            'win_rate': round(sum(1 for r in returns[1:] if r > 0) / max(1, len(returns) - 1) * 100, 2),
        },
        'equity_curve': nav_curve,
        'trades': trades[:100],
        'created_at': _now_iso(),
    }

    # 持久化
    run_path = os.path.join(RUNS_DIR, f'{run_id}.json')
    with open(run_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    return result


def _empty_backtest_result(run_id, start_date, end_date, benchmark, reason):
    return {
        'run_id': run_id,
        'status': 'failed',
        'strategy': 'N/A',
        'parameters': {
            'start_date': start_date,
            'end_date': end_date,
            'benchmark': benchmark,
        },
        'metrics': {
            'total_return': 0,
            'annualized_return': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'volatility': 0,
            'win_rate': 0,
        },
        'equity_curve': [],
        'trades': [],
        'error': f'回测失败: {reason}',
        'created_at': _now_iso(),
    }


def get_backtest_result(run_id: str) -> dict | None:
    run_path = os.path.join(RUNS_DIR, f'{run_id}.json')
    if not os.path.exists(run_path):
        return None
    with open(run_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def list_backtest_runs(limit: int = 50, offset: int = 0) -> tuple[list, int]:
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
