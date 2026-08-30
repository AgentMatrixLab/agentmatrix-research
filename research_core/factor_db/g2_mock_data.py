"""QAPI33 mock 面板数据生成器（九道闸门骨架验证用）。

设计目标：**不只是"能跑"，还要"能判别"**——mock 数据里预埋三类因子，
验证九道闸门各自的判别力（好因子该过、坏因子该挂、知道死在哪道闸）：

1. **planted_good**   月频 Rank IC≈0.06、36 个月方向一致 → 目标全过九道
2. **planted_decay**  IC 全样本均值好看但逐年衰减、OOS 留存 <70% → 目标死在闸门8
3. **planted_regime** 只在"牛市段"有 alpha、熊市段归零 → 目标死在闸门11
4. **planted_turnover** 信号噪声大、换手爆表 → 目标死在闸门9
5. **planted_crowded** 与 planted_good 相关性 0.95 → 目标死在闸门12

面板字段覆盖九道闸门全部输入：
- 基础：date / code / factor_value / next_return（月频）
- 闸门4：coverage_ratio / missing_rate（每因子预埋缺失率）
- 闸门5：limit_up / limit_down / suspended / is_st / days_since_ipo / avg_amount_20d
- 闸门10：log_mcap / industry（Barra 代理由 mcap+ret 派生）
- 闸门9：next_return 派生 breakeven 检验

可复现：seed=42，30 股 × 96 个月（8 年，IS/OOS 6:2 预注册切分）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 42
N_STOCKS = 30
N_MONTHS = 96  # 8 年：72 IS + 24 OOS
PREREG_SPLIT = "2022-01-01"  # 预注册切分点（novel 类入队时锁定）


def make_panel(seed: int = SEED) -> pd.DataFrame:
    """生成月频 mock 面板（date/code/next_return + 闸门5/10 输入字段）。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-31", periods=N_MONTHS, freq="ME")
    codes = [f"MOCK{i:02d}" for i in range(N_STOCKS)]

    # 股票截面属性（固定，PIT 简化）
    log_mcap = rng.normal(22.0, 0.8, N_STOCKS)          # 流通市值对数
    industry = np.array([f"IND{i % 5}" for i in range(N_STOCKS)])  # 5 行业
    beta = rng.normal(1.0, 0.2, N_STOCKS)
    days_since_ipo = rng.integers(200, 3000, N_STOCKS)
    avg_amount_20d = rng.normal(5e7, 2e7, N_STOCKS).clip(1e7)  # 均成交额

    # 市场状态：月度市场收益（前 48 月上行、中 24 月震荡、后 24 月下行）
    mkt = np.concatenate([
        rng.normal(0.02, 0.03, 48),
        rng.normal(0.0, 0.03, 24),
        rng.normal(-0.01, 0.04, 24),
    ])

    # 共同风格因子：动量（牛市段走强）
    style_mom = np.concatenate([np.linspace(-0.5, 1.0, 48), rng.normal(0.2, 0.5, 24), rng.normal(-0.6, 0.5, 24)])

    rows = []
    for t, d in enumerate(dates):
        stock_ret = (
            mkt[t] * beta
            + 0.01 * style_mom[t] * rng.normal(0, 1, N_STOCKS) * 0  # 风格项见下
            + rng.normal(0, 0.08, N_STOCKS)
        )
        # 显式构造一个风格因子载荷（供闸门10 残差检验）
        mom_load = rng.normal(0, 1, N_STOCKS)
        stock_ret = stock_ret + 0.008 * style_mom[t] * mom_load

        # 闸门5 字段：随机少量涨跌停/停牌/ST/低流动性
        limit_up = rng.random(N_STOCKS) < 0.02
        limit_down = rng.random(N_STOCKS) < 0.02
        suspended = rng.random(N_STOCKS) < 0.01
        is_st = rng.random(N_STOCKS) < 0.05
        low_liq = avg_amount_20d < 2.0e7

        for i, c in enumerate(codes):
            rows.append(
                {
                    "date": d,
                    "code": c,
                    "next_return": stock_ret[i],
                    "log_mcap": log_mcap[i] + rng.normal(0, 0.02),
                    "industry": industry[i],
                    "mom_load": mom_load[i] + rng.normal(0, 0.1),
                    "limit_up": bool(limit_up[i]),
                    "limit_down": bool(limit_down[i]),
                    "suspended": bool(suspended[i]),
                    "is_st": bool(is_st[i]),
                    "days_since_ipo": int(days_since_ipo[i] + t * 21),
                    "avg_amount_20d": float(avg_amount_20d[i] * rng.normal(1, 0.2)),
                }
            )
    return pd.DataFrame(rows)


def make_factor_values(panel: pd.DataFrame, seed: int = SEED) -> dict[str, pd.DataFrame]:
    """生成 5 个预埋因子 + 33 个真实 QAPI33 因子的 mock 值。

    返回 {factor_name: DataFrame(date, code, factor_value)}。
    预埋因子的 alpha 注入方式各不相同，用于检验各闸门判别力。
    """
    rng = np.random.default_rng(seed)
    dates = sorted(panel["date"].unique())
    n_t = len(dates)
    codes = sorted(panel["code"].unique())
    n_s = len(codes)

    # 信号基底：每期一个独立的横截面信号（好因子 = 真实 next_return 的领先量）
    base_signal = rng.normal(0, 1, (n_t, n_s))

    # next_return 面板（对齐用）
    ret = panel.pivot(index="date", columns="code", values="next_return").loc[dates, codes]

    is_mask = np.array([d < pd.Timestamp(PREREG_SPLIT) for d in dates])
    bull_mask = np.arange(n_t) < 48  # 前 48 月"牛市段"

    factors: dict[str, pd.DataFrame] = {}

    def _mk(name: str, values: np.ndarray) -> None:
        factors[name] = pd.DataFrame(
            {"date": np.repeat(dates, n_s), "code": np.tile(codes, n_t), "factor_value": values.ravel()},
        )

    # 1) planted_good：IS+OOS 全程稳定 alpha（真实收益 + 噪声）
    good = ret.values * 0.5 + rng.normal(0, 0.05, (n_t, n_s))
    _mk("planted_good", good)

    # 2) planted_decay：IS 前段强、后段消失（OOS 留存 < 70%）
    decay = np.where(is_mask[:, None], ret.values * 0.6 + rng.normal(0, 0.05, (n_t, n_s)), rng.normal(0, 0.1, (n_t, n_s)))
    _mk("planted_decay", decay)

    # 3) planted_regime：alpha 覆盖全程，但 2019/2021 两个 IS 年份归零
    #    （OOS 2022-2023 均有 alpha → 过闸门8；逐年一致性差 → 死闸门11）
    regime_years = pd.DatetimeIndex(dates).year
    dead_years = {2019, 2021}
    alive = np.array([y not in dead_years for y in regime_years])
    regime = np.where(alive[:, None], ret.values * 0.6 + rng.normal(0, 0.05, (n_t, n_s)), rng.normal(0, 0.1, (n_t, n_s)))
    _mk("planted_regime", regime)

    # 4) planted_turnover：真实信号 + 大噪声（换手爆表）
    noisy = ret.values * 0.6 + rng.normal(0, 0.8, (n_t, n_s))
    _mk("planted_turnover", noisy)

    # 5) planted_crowded：good 的马甲（相关性 >0.9）
    _mk("planted_crowded", good + rng.normal(0, 0.03, (n_t, n_s)))

    # 6) 33 个 QAPI33 真名因子的 mock 值（独立噪声信号，检验闸门不会放水）
    from research_core.factor_db.metadata import _all_factors

    for row in _all_factors():
        if row["factor_id"].startswith("QAPI33:"):
            short = row["factor_id"].split(":", 1)[1]
            _mk(short, rng.normal(0, 1, (n_t, n_s)))
    return factors


def build_long_panel(seed: int = SEED) -> pd.DataFrame:
    """长表（date, code, <factor_name>...，闸门5/10 字段）——九道闸门的统一输入。"""
    panel = make_panel(seed)
    factors = make_factor_values(panel, seed)
    wide = panel.copy()
    for name, df in factors.items():
        wide[name] = wide.merge(df, on=["date", "code"], how="left")["factor_value"]
    return wide, list(factors.keys())


if __name__ == "__main__":
    wide, names = build_long_panel()
    print(f"panel: {wide.shape}, factors: {len(names)}")
    print(wide.head(3).to_string())
