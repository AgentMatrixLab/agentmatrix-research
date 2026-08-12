"""
绩效指标计算
"""
import pandas as pd
import numpy as np

def compute_metrics(nav_series, rf=0.02):
    """
    输入: nav_series (pd.Series, index=日期, values=净值)
    输出: dict of 绩效指标
    """
    if len(nav_series) < 2:
        return {}

    daily_ret = nav_series.pct_change().dropna()

    # 交易日天数
    n_days = len(daily_ret)
    n_years = n_days / 252

    total_ret = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    ann_ret = (1 + total_ret) ** (1 / n_years) - 1
    ann_vol = daily_ret.std() * np.sqrt(252)

    # Sharpe
    excess = daily_ret - rf / 252
    sharpe = np.sqrt(252) * excess.mean() / daily_ret.std() if daily_ret.std() > 0 else 0

    # Max Drawdown
    cummax = nav_series.cummax()
    drawdown = nav_series / cummax - 1
    mdd = drawdown.min()

    # Calmar
    calmar = ann_ret / abs(mdd) if mdd < 0 else np.inf

    # Win Rate (日胜率)
    win_rate = (daily_ret > 0).mean()

    # 滚动回撤期
    dd_duration = 0
    current_dd = 0
    max_dd_duration = 0
    for dd in drawdown:
        if dd < 0:
            current_dd += 1
            max_dd_duration = max(max_dd_duration, current_dd)
        else:
            current_dd = 0

    # 年化换手率(如果传了换手数据, 否则不计算)
    # 这里只计算净值相关指标

    result = {
        "总收益率": f"{total_ret:.2%}",
        "年化收益率": f"{ann_ret:.2%}",
        "年化波动率": f"{ann_vol:.2%}",
        "夏普比率": f"{sharpe:.2f}",
        "最大回撤": f"{mdd:.2%}",
        "卡尔玛比率": f"{calmar:.2f}",
        "日胜率": f"{win_rate:.2%}",
        "最长回撤天数": f"{max_dd_duration}天",
        "交易日数": n_days,
    }
    return result

def compute_turnover(weights_series):
    """
    计算平均单边换手率
    weights_series: list of DataFrames, 每个元素是当日持仓权重
    """
    turnovers = []
    prev = None
    for w in weights_series:
        if prev is not None and len(prev) > 0 and len(w) > 0:
            merged = prev.merge(w, on='symbol', how='outer', suffixes=('_prev', '_cur')).fillna(0)
            turnover = (merged['weight_prev'] - merged['weight_cur']).abs().sum() / 2
            turnovers.append(turnover)
        prev = w
    if len(turnovers) == 0:
        return 0
    return np.mean(turnovers)

def format_report(all_results, nav_dict=None):
    """
    格式化多策略对比报告
    all_results: {策略名: {指标名: 值}}
    """
    lines = [
        "=" * 70,
        "📊 多策略回测对比报告",
        "=" * 70,
    ]

    # 提取所有指标名
    metrics = []
    for name, res in all_results.items():
        for k in res.keys():
            if k not in metrics and k != "交易日数":
                metrics.append(k)

    # 表头
    header = f"{'策略':<20}" + "".join(f"{m:>14}" for m in metrics)
    lines.append(header)
    lines.append("-" * 70)

    for name, res in all_results.items():
        row = f"{name:<20}"
        for m in metrics:
            val = res.get(m, "-")
            row += f"{str(val):>14}"
        lines.append(row)

    lines.append("=" * 70)
    return "\n".join(lines)
