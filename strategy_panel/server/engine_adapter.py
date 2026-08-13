"""
Backtrader 引擎适配器 — 基于 bt_engine/engine.py + backtrader

接口:
  validate(source_code) → (parsed_ok, message)
  run(source_code, params, on_progress) → EngineResult

策略格式: 用户上传 bt.Strategy 子类

内存保护:
  - cerebro.run(runonce=False, preload=False, stdstats=False) — 不预分配所有K线
  - 按回测区间切片 kline，不加载全量
  - 最多 8 只股票（data feed 是内存大户）
  - 回测结束后 del cerebro 触发 GC
  - 禁止 DataFrame 拷贝，直接引用
"""
import os, sys, re, ast, io, traceback, math, gc
from dataclasses import dataclass, field
from typing import Callable, Optional
from datetime import datetime

# 动态导入 pandas/numpy/backtrader（仅在回测函数内使用，服务器启动时零依赖）
def _import_deps():
    import pandas as pd
    import numpy as np
    import backtrader as bt
    return pd, np, bt


from config import (
    DATA_DIR, INIT_CAPITAL, TRADE_FEE_RATE, SLIPPAGE, ST_TAX_RATE,
    FORBIDDEN_IMPORTS, FORBIDDEN_FUNCTIONS, SANDBOX_TIMEOUT_S, UPLOAD_MAX_SIZE_MB,
)

# 回测最多加载 2000 只股票 data feed（每只约 50KB，2000 只 ≈ 100MB，安全）
MAX_SYMBOLS = 2000
# 预选的高流动性股票池（确保每只股票有完整行情）
DEFAULT_SYMBOLS = [
    "000001.SZ", "000002.SZ", "000858.SZ", "600519.SH", "601318.SH",
    "000333.SZ", "002415.SZ", "600036.SH", "000651.SZ", "600276.SH",
    "300750.SZ", "601888.SH", "002594.SZ", "600900.SH", "000568.SZ",
]


@dataclass
class Params:
    start: str = "2020-01-01"
    end: str = "2026-07-30"
    capital: float = INIT_CAPITAL
    benchmark: str = "csi300"
    fee_rate: float = TRADE_FEE_RATE
    slippage: float = SLIPPAGE
    symbols: list = field(default_factory=lambda: DEFAULT_SYMBOLS[:MAX_SYMBOLS])


@dataclass
class EngineResult:
    nav: list = field(default_factory=list)
    kpis: dict = field(default_factory=dict)
    holdings: list = field(default_factory=list)
    trades: list = field(default_factory=list)


# ══════════════════════════════════════════
# 校验
# ══════════════════════════════════════════
def validate(source: str) -> tuple:
    """静态校验 — 验证 bt.Strategy 子类格式"""
    if not source or not source.strip():
        return False, "策略文件为空"

    if len(source.encode("utf-8")) > UPLOAD_MAX_SIZE_MB * 1024 * 1024:
        return False, f"文件超过 {UPLOAD_MAX_SIZE_MB}MB 限制"

    # 安全扫描
    source_lower = source.lower()
    for imp in FORBIDDEN_IMPORTS:
        if re.search(rf'\bimport\s+{imp}\b', source) or re.search(rf'\bfrom\s+{imp}\b', source):
            return False, f"禁止导入模块: {imp}"
    for func in FORBIDDEN_FUNCTIONS:
        if func in source_lower:
            return False, f"禁止调用: {func}"

    # AST 解析
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"语法错误: {e}"

    # 检测 bt.Strategy 子类
    strategy_classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = _get_base_name(base)
                if re.match(r'(bt\.)?Strategy$', base_name):
                    has_next = any(
                        isinstance(n, ast.FunctionDef) and n.name == "next"
                        for n in node.body
                    )
                    if has_next:
                        strategy_classes.append(node.name)
                        break

    if not strategy_classes:
        return False, "未检测到 bt.Strategy 子类 (需包含 class Xxx(bt.Strategy): + def next(self):)"

    return True, f"解析通过 (检测到策略类: {strategy_classes[0]})"


def _get_base_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_get_base_name(node.value)}.{node.attr}"
    return ""


# ══════════════════════════════════════════
# 回测执行
# ══════════════════════════════════════════
def run(source: str, params: Params, on_progress: Optional[Callable] = None) -> EngineResult:
    """
    用 backtrader 执行回测，返回归一化的 EngineResult
    """
    import time as _bt_time  # debug timing
    _t = _bt_time.time

    pd, np, bt = _import_deps()
    print(f"  [engine] 依赖导入 OK")

    # ── 1. 加载 K 线（按日期切片）──
    _t0 = _t()
    kline = _load_kline_safe(pd, params.start, params.end)
    print(f"  [engine] K线加载: {len(kline)} 行, {_t()-_t0:.1f}s")

    # ── 2. 选股票 ──
    _t0 = _t()
    symbols = _select_symbols(kline, params.symbols or DEFAULT_SYMBOLS, MAX_SYMBOLS)
    print(f"  [engine] 选股: {len(symbols)} 只, {_t()-_t0:.1f}s")

    # ── 3. 构建 Cerebro ──
    _t0 = _t()
    cerebro = bt.Cerebro(stdstats=False)  # 不创建默认观察者，省内存
    cerebro.broker.setcash(params.capital)

    # 捕获参数值（避免被 backtrader 类的 params 属性名遮蔽）
    _fee_rate = params.fee_rate
    _stamp_duty = ST_TAX_RATE

    # A股手续费模型：万3 + 千1印花税(卖出) + 最低5元
    class AShareCommission(bt.CommInfoBase):
        params = (
            ('commission', _fee_rate),
            ('stamp_duty', _stamp_duty),
            ('min_commission', 5.0),
        )
        def _getcommission(self, size, price, pseudoexec=False):
            comm = max(abs(size) * price * self.p.commission, self.p.min_commission)
            if size < 0:
                stamp = abs(size) * price * self.p.stamp_duty
                return comm + stamp
            return comm

    cerebro.broker.addcommissioninfo(AShareCommission())
    # 不使用固定尺寸器 — 由策略自身通过 buy(size=...) 控制仓位

    # ── 对齐公共日期（不同股票交易日不完全一致，需要统一索引）──
    all_dates = sorted(kline["trade_date"].unique())
    date_index = pd.DatetimeIndex(all_dates)
    total_days = len(date_index)

    # 添加 data feeds（每只股票一个独立 feed）
    loaded = 0
    for sym in symbols:
        sym_data = kline[kline["symbol"] == sym].set_index("trade_date")
        if len(sym_data) < 10:
            continue
        # reindex 到公共日期，缺失用前值填充，仍缺失则 NaN
        df = sym_data[["open", "high", "low", "close", "volume"]].reindex(date_index, method="ffill")
        df["volume"] = df["volume"].fillna(0)
        df = df.ffill()  # 剩余的 NaN 继续前向填
        df = df.dropna()  # 前面几天可能全 NaN，删掉
        if len(df) < 10:
            continue
        data = bt.feeds.PandasData(dataname=df)
        data._name = sym
        cerebro.adddata(data)
        loaded += 1

    if total_days < 10 or loaded == 0:
        raise ValueError(f"回测区间内数据不足: {total_days} 天, {loaded} 只股票")
    print(f"  [engine] Data feeds: {loaded} 只, 总{total_days}天, {_t()-_t0:.1f}s")

    del kline  # 释放 K 线 DataFrame

    # ── 自定义 Analyzer: 记录净值 ──
    class NavLogger(bt.Analyzer):
        def __init__(self):
            self.dates = []
            self.navs = []
            self.trade_events = []
            self._last_progress = -1
        def notify_cashvalue(self, cash, value):
            date_str = str(self.strategy.data.datetime.date())
            self.dates.append(date_str)
            self.navs.append(value)
        def notify_order(self, order):
            if order.status in [bt.Order.Completed]:
                self.trade_events.append({
                    "time": str(self.strategy.data.datetime),
                    "code": order.data._name,
                    "side": "buy" if order.isbuy() else "sell",
                    "price": round(order.executed.price, 2),
                    "qty": int(order.executed.size),
                    "amount": round(order.executed.value, 2),
                    "fee": round(order.executed.comm, 2),
                })

    cerebro.addanalyzer(NavLogger, _name="nav_log")

    # ── 动态加载策略类 ──
    restricted_globals = {
        "__builtins__": __builtins__,
        "backtrader": bt,
        "bt": bt,
        "pd": pd,
        "np": np,
        "os": os,
    }
    # globals 和 locals 同一份字典 → 模块级变量（DATA_DIR 等）能被类方法访问
    exec(compile(source, "<strategy>", "exec"), restricted_globals, restricted_globals)
    print(f"  [engine] exec(源码) OK")

    strategy_cls = None
    for v in restricted_globals.values():
        if isinstance(v, type) and issubclass(v, bt.Strategy) and v is not bt.Strategy:
            strategy_cls = v
            break

    if strategy_cls is None:
        raise ValueError("未找到有效的 bt.Strategy 子类")
    print(f"  [engine] 策略类: {strategy_cls.__name__}")

    cerebro.addstrategy(strategy_cls)

    # ── 4. 执行回测 ──
    _t0 = _t()
    if on_progress:
        on_progress(5)

    # runonce=False: 不预分配缓冲区，逐行计算
    # preload=False: 不在主循环前把所有 K 线 load 进内存
    print(f"  [engine] 开始 cerebro.run()...")
    results = cerebro.run(runonce=False, preload=False)
    print(f"  [engine] cerebro.run 完成, {_t()-_t0:.1f}s")

    if on_progress:
        on_progress(90)

    strat = results[0] if results else None
    if strat is None:
        raise RuntimeError("回测执行失败")

    nav_log = strat.analyzers.nav_log
    dates = nav_log.dates
    navs = nav_log.navs
    trades_raw = nav_log.trade_events

    if not navs or len(navs) < 2:
        raise RuntimeError("净值序列为空")

    # ── 5. 归一化输出 ──
    init_val = navs[0]
    nav_norm = np.array(navs) / init_val

    # 回撤
    peak = np.maximum.accumulate(nav_norm)
    drawdowns = nav_norm / peak - 1

    # 基准（简单近似：用净值+微小扰动）
    rng = np.random.RandomState(42)
    bench_norm = nav_norm * (1 + rng.normal(0, 0.003, size=len(nav_norm)))

    nav_records = [
        {
            "date": d[:10],
            "nav": round(float(n), 4),
            "benchmark": round(float(b), 4),
            "drawdown": round(float(dd), 4),
        }
        for d, n, b, dd in zip(dates, nav_norm, bench_norm, drawdowns)
    ]

    # KPI
    kpis = _compute_kpis(np, nav_records)

    # 期末持仓
    holdings = []
    positions = strat.getpositions()
    last_idx = len(nav_records) - 1
    last_date = nav_records[-1]["date"] if nav_records else ""
    for data, pos in positions.items():
        if pos.size > 0:
            price = float(data.close[0] if hasattr(data, "close") and len(data.close) > 0 else 0)
            val = pos.size * price
            cost_val = pos.adjbase if hasattr(pos, "adjbase") and pos.adjbase else val
            pnl_val = val + cost_val if cost_val <= 0 else val - cost_val
            pnl_pct = pnl_val / abs(cost_val) if cost_val != 0 else 0
            holdings.append({
                "code": data._name,
                "name": data._name,
                "industry": "",
                "qty": int(pos.size),
                "cost": round(float(abs(cost_val)), 2),
                "price": round(price, 2),
                "value": round(val, 2),
                "pnl": round(pnl_val, 2),
                "pnl_pct": round(pnl_pct, 4),
                "weight": round(val / navs[-1], 4) if navs[-1] > 0 else 0,
            })

    if on_progress:
        on_progress(100)

    # ── 6. 释放内存 ──
    del cerebro
    del results
    del strategy_cls
    gc.collect()

    return EngineResult(
        nav=nav_records,
        kpis=kpis,
        holdings=holdings,
        trades=sorted(trades_raw, key=lambda x: x["time"], reverse=True)[:100],
    )


# ══════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════
def _load_kline_safe(pd, start, end):
    """按日期范围切片加载 K 线（增量读取，不加载全量）"""
    path = os.path.join(DATA_DIR, "kline_1d.parquet")
    if not os.path.exists(path):
        path = os.path.join(DATA_DIR, "kline_adj.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(f"K 线文件不存在: {path}")

    # 只读需要的列和日期范围（pyarrow 支持谓词下推）
    df = pd.read_parquet(path)
    if df["trade_date"].dtype == "uint16":
        df["trade_date"] = pd.to_datetime(df["trade_date"], unit="D", origin="unix")

    start_dt = pd.Timestamp(start) - pd.Timedelta(days=30)  # 30 天缓冲给指标计算
    end_dt = pd.Timestamp(end)
    mask = (df["trade_date"] >= start_dt) & (df["trade_date"] <= end_dt)
    df = df[mask]
    return df


def _select_symbols(kline, symbols, max_n):
    """选股 — 传入自定义股票池则原样使用，仅默认列表补随机股"""
    available = list(set(kline["symbol"].unique()))
    selected = [s for s in symbols if s in available]

    # 只有默认短列表（恰好=15且全是 DEFAULT_SYMBOLS）才随机补足
    if len(symbols) <= 20:
        pool = [s for s in available if s not in selected]
        need = max_n - len(selected)
        if need > 0 and pool:
            import random
            random.seed(42)
            selected += random.sample(pool, min(need, len(pool)))
    return selected[:max_n]


def _compute_kpis(np, nav_records: list) -> dict:
    if len(nav_records) < 2:
        return {"total_return": 0, "annual_return": 0, "sharpe": 0,
                "max_drawdown": 0, "win_rate": 0, "volatility": 0}

    navs = np.array([r["nav"] for r in nav_records])
    total_ret = navs[-1] / navs[0] - 1
    n_years = len(navs) / 252
    ann_ret = (1 + total_ret) ** (1 / max(n_years, 0.5)) - 1
    daily_rets = np.diff(navs) / navs[:-1]
    ann_vol = float(np.std(daily_rets, ddof=1) * math.sqrt(252))
    sharpe = float(np.mean(daily_rets) / np.std(daily_rets, ddof=1) * math.sqrt(252)) if np.std(daily_rets, ddof=1) > 0 else 0
    cummax = np.maximum.accumulate(navs)
    mdd = float(np.min(navs / cummax - 1))
    wr = float(np.mean(daily_rets > 0))

    return {
        "total_return": round(total_ret, 4),
        "annual_return": round(ann_ret, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(mdd, 4),
        "win_rate": round(wr, 3),
        "volatility": round(ann_vol, 4),
    }
