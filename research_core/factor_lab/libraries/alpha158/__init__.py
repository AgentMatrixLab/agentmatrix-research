"""Alpha158 Factor Library - Qlib Alpha158 因子独立实现

本模块提供了 Qlib Alpha158 全部 158 个因子的纯 numpy/pandas 实现，
不依赖 Qlib 表达式引擎，可直接用于任何 OHLCV 数据源。

验证状态：与 Qlib 内置 Alpha158 在 2018-2020 沪深300 数据上逐因子对照，
17 个因子完全一致（max_err=0），100 个高度吻合（>99.99%），
25 个基本吻合（>99%），15 个部分偏差（>82%），1 个无数据。

使用方法:
    from alpha158_library import compute_alpha158

    # raw_data 需要包含列: open, high, low, close, vwap, volume
    # 索引为 MultiIndex (datetime, instrument)
    factors = compute_alpha158(raw_data)
"""
from .factors import compute_alpha158, get_factor_names, get_factor_categories
from .evaluation import (compute_forward_returns, compute_rank_ic,
                         compute_ic_summary, evaluate_all_factors,
                         compare_ic_with_truth)

__all__ = [
    'compute_alpha158', 'get_factor_names', 'get_factor_categories',
    'compute_forward_returns', 'compute_rank_ic', 'compute_ic_summary',
    'evaluate_all_factors', 'compare_ic_with_truth',
]
