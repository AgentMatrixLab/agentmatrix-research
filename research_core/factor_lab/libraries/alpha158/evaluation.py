"""
Alpha158 因子 IC 评估模块

提供因子值 → IC 分析的全套函数，数据源无关。
假设所有输入 DataFrame/Series 的 MultiIndex 均为 (instrument, datetime)。
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def compute_forward_returns(close: pd.Series, period: int = 1) -> pd.Series:
    """
    计算前向收益率。

    Args:
        close: MultiIndex (instrument, datetime) 收盘价
        period: 前向周期

    Returns:
        MultiIndex (instrument, datetime) 同索引的 T+N 收益率
    """
    return close.groupby('instrument').pct_change(period).shift(-period)


def _cross_section_spearman(factor_slice: pd.Series,
                            return_slice: pd.Series) -> float:
    """单日截面的 Spearman rank correlation"""
    both = pd.DataFrame({'f': factor_slice, 'r': return_slice}).dropna()
    if len(both) < 5:
        return np.nan
    ic, _ = spearmanr(both['f'], both['r'])
    return ic


def compute_rank_ic(factor_values: pd.Series,
                    forward_returns: pd.Series) -> pd.Series:
    """
    计算逐日截面 Rank IC。

    Args:
        factor_values: MultiIndex (instrument, datetime) 因子值
        forward_returns: MultiIndex (instrument, datetime) 前向收益率

    Returns:
        pd.Series index=datetime, values=daily Rank IC
    """
    # 转为 (datetime, instrument) wide 格式，便于按日期遍历
    f_wide = factor_values.unstack(level='datetime')
    r_wide = forward_returns.unstack(level='datetime')

    dates = sorted(f_wide.columns)
    ic_list = []
    for d in dates:
        f_slice = f_wide[d]
        r_slice = r_wide[d]
        ic = _cross_section_spearman(f_slice, r_slice)
        ic_list.append(ic)
    return pd.Series(ic_list, index=dates, name='IC')


def compute_ic_summary(ic_series: pd.Series) -> dict:
    """IC 汇总统计"""
    valid = ic_series.dropna()
    n = len(valid)
    if n == 0:
        return {'IC_mean': np.nan, 'IC_std': np.nan, 'ICIR': np.nan,
                'IC_win_rate': np.nan, 'IC_max': np.nan, 'IC_min': np.nan,
                'IC_tstat': np.nan, 'n_days': 0}
    mean_val = valid.mean()
    std_val = valid.std(ddof=1)
    icir = mean_val / std_val if std_val > 0 else np.nan
    win_rate = (valid > 0).sum() / n
    tstat = mean_val / (std_val / np.sqrt(n)) if std_val > 0 else np.nan

    return {
        'IC_mean': round(float(mean_val), 6),
        'IC_std': round(float(std_val), 6),
        'ICIR': round(float(icir), 6),
        'IC_win_rate': round(float(win_rate), 6),
        'IC_max': round(float(valid.max()), 6),
        'IC_min': round(float(valid.min()), 6),
        'IC_tstat': round(float(tstat), 6),
        'n_days': n,
    }


def evaluate_all_factors(factors_df: pd.DataFrame,
                         close: pd.Series,
                         period: int = 1) -> pd.DataFrame:
    """
    批量评估所有因子的 Rank IC。

    Args:
        factors_df: MultiIndex (instrument, datetime), columns = 因子名
        close: MultiIndex (instrument, datetime) 收盘价
        period: 前向周期

    Returns:
        DataFrame index=因子名, columns=IC_mean/IC_std/ICIR/IC_win_rate/IC_max/IC_min/IC_tstat/n_days
    """
    fwd_ret = compute_forward_returns(close, period)
    r_wide = fwd_ret.unstack(level='datetime')

    results = []
    for col in factors_df.columns:
        f_wide = factors_df[col].unstack(level='datetime')
        dates = sorted(f_wide.columns)
        ic_list = []
        for d in dates:
            f_slice = f_wide[d]
            r_slice = r_wide[d]
            ic = _cross_section_spearman(f_slice, r_slice)
            ic_list.append(ic)
        ic_series = pd.Series(ic_list, index=dates)
        summary = compute_ic_summary(ic_series)
        summary['factor'] = col
        results.append(summary)

    df = pd.DataFrame(results).set_index('factor')
    df['abs_icir'] = df['ICIR'].abs()
    df = df.sort_values('abs_icir', ascending=False).drop(columns='abs_icir')
    return df


def compare_ic_with_truth(our_ic: pd.DataFrame,
                          truth_ic: pd.DataFrame,
                          factor_names: list = None) -> pd.DataFrame:
    """将自算 IC 与外部真值 IC 对照"""
    common = factor_names if factor_names else sorted(
        set(our_ic.index) & set(truth_ic.index))
    rows = []
    for f in common:
        ours = our_ic.loc[f, 'IC_mean'] if f in our_ic.index else np.nan
        t = truth_ic.loc[f, 'IC_mean'] if f in truth_ic.index else np.nan
        diff = abs(ours - t) if (pd.notna(ours) and pd.notna(t)) else np.nan
        rows.append({'factor': f, 'our_IC_mean': ours,
                     'truth_IC_mean': t, 'IC_diff': diff})
    df = pd.DataFrame(rows).set_index('factor')
    df['match_1e4'] = df['IC_diff'] < 1e-4
    return df
