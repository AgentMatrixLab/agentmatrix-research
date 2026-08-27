"""
Supabase 信号策略 — 从 Supabase signals 表读取交易指令

信号格式:
  - supabase_signals.json 由 fetch_supabase_signals.py 生成
  - {"trade_dates": [...], "signals": {"date": [{symbol, weight, action}, ...]}}
  - action: BUY/HOLD/SELL
  - weight: 目标仓位权重 (0~1)

get_signals(tradable_df) 接口:
  - 输入: DataFrame with ['symbol', 'trade_date']
  - 输出: DataFrame with ['symbol', 'weight'] (weight 是 target_position)
"""
import os, json
import pandas as pd

SIGNAL_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "output", "supabase_signals.json")

_SIGNAL_MAP = None  # {date_str: {symbol: weight}}


def _load_signals():
    """加载信号文件，返回 {date_str: {symbol: weight}}"""
    global _SIGNAL_MAP
    if _SIGNAL_MAP is not None:
        return _SIGNAL_MAP
    
    if not os.path.exists(SIGNAL_FILE):
        print(f"  [supabase_signals] 信号文件不存在: {SIGNAL_FILE}")
        _SIGNAL_MAP = {}
        return _SIGNAL_MAP
    
    with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    _SIGNAL_MAP = {}
    for date_str, sigs in data.get("signals", {}).items():
        # 只取 HOLD 和 BUY 信号（SELL 表示退出）
        weights = {}
        for s in sigs:
            if s["action"] in ("HOLD", "BUY"):
                weights[s["symbol"]] = s["weight"]
        if weights:
            _SIGNAL_MAP[date_str] = weights
    
    print(f"  [supabase_signals] 已加载 {len(_SIGNAL_MAP)} 个信号日")
    return _SIGNAL_MAP


def get_signals(tradable_df: pd.DataFrame) -> pd.DataFrame:
    """
    从 Supabase 信号获取调仓指令。
    tradable_df 包含单日的 symbol 列表，返回该日应持仓的 symbol+weight。
    """
    signal_map = _load_signals()
    if not signal_map:
        return None
    
    # 获取 tradable_df 的日期
    if 'trade_date' in tradable_df.columns:
        date_val = tradable_df['trade_date'].iloc[0]
        date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)[:10]
    else:
        return None
    
    if date_str not in signal_map:
        return None
    
    weights = signal_map[date_str]
    if not weights:
        return None
    
    # 交集：只保留 tradable_df 中存在的 symbol
    tradable_symbols = set(tradable_df['symbol'].tolist())
    matched = {sym: w for sym, w in weights.items() if sym in tradable_symbols}
    
    if not matched:
        return None
    
    result = pd.DataFrame([
        {"symbol": sym, "weight": w}
        for sym, w in matched.items()
    ])
    return result
