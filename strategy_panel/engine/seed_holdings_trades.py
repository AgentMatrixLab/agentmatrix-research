"""
从回测 JSON 文件读取真实持仓和交易数据，写入 SQLite。
替代之前硬编码假数据的方式。
"""
import os, json, sqlite3
from datetime import datetime

OUTPUT_DIR = r"D:\bigquant\output"
DB_PATH = r"D:\bigquant\bt_panel\server\bt_panel.db"

# 加载股票名称映射
STOCK_NAMES_FILE = os.path.join(OUTPUT_DIR, "stock_names.json")
STOCK_NAMES = {}
if os.path.exists(STOCK_NAMES_FILE):
    with open(STOCK_NAMES_FILE, "r", encoding="utf-8") as f:
        STOCK_NAMES = json.load(f)


def symb(code):
    return code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")


def load_json(name):
    path = os.path.join(OUTPUT_DIR, name)
    for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
        try:
            with open(path, "r", encoding=enc) as f:
                data = json.load(f)
            if "strategies" in data:
                return data["strategies"][0]
            return data
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    print(f"  ⚠️ Cannot decode: {name}")
    return None


def seed_holdings(strategy_id: str, json_file: str):
    """从回测 JSON 读取最新持仓快照"""
    s = load_json(json_file)
    if not s:
        return
    
    snapshots = s.get("position_snapshots", [])
    if not snapshots:
        print(f"  [{strategy_id}] 无持仓快照")
        return
    
    # 取最新快照
    latest = snapshots[-1]
    holdings = latest.get("holdings", [])
    if not holdings:
        print(f"  [{strategy_id}] 空持仓")
        return
    
    total_value = sum(h.get("value", 0) for h in holdings)
    
    for h in holdings:
        code = symb(h["symbol"])
        name = STOCK_NAMES.get(h["symbol"], code)
        qty = h["qty"]
        price = h["price"]
        value = h["value"]
        weight = round(value / total_value, 4) if total_value > 0 else 0
        
        # cost = price (简化：使用当前价格作为成本)
        cost = price
        pnl = 0.0
        pnl_pct = 0.0
        
        db.execute("""
            INSERT INTO holdings (strategy_id, code, name, industry, qty, cost, price, value, pnl, pnl_pct, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [strategy_id, code, name, "", qty, cost, price, value, pnl, pnl_pct, weight])
    
    # 统计
    print(f"  [{strategy_id}] 持仓: {len(holdings)} 条, 日期={latest.get('date','?')}")


def seed_trades(strategy_id: str, json_file: str, max_trades: int = 500):
    """从回测 JSON 读取交易记录"""
    s = load_json(json_file)
    if not s:
        return
    
    trade_log = s.get("trade_log", [])
    if not trade_log:
        print(f"  [{strategy_id}] 无交易记录")
        return
    
    # 倒序取最近 N 条
    recent = trade_log[-max_trades:]
    
    for t in recent:
        code = symb(t["symbol"])
        name = STOCK_NAMES.get(t["symbol"], code)
        side = t.get("side", "buy")
        price = t.get("price", 0)
        qty = t.get("qty", 0)
        amount = t.get("amount", round(price * qty, 2))
        fee = t.get("fee", 0)
        time_str = t.get("date", "") + " 15:00:00"
        
        db.execute("""
            INSERT INTO trades (strategy_id, time, code, name, side, price, qty, amount, fee)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [strategy_id, time_str, code, name, side, price, qty, amount, fee])
    
    print(f"  [{strategy_id}] 交易: {len(recent)} 条 (共 {len(trade_log)} 条)")


def seed():
    db_path = DB_PATH
    global db
    db = sqlite3.connect(db_path)
    
    # 清空旧数据
    db.execute("DELETE FROM holdings")
    db.execute("DELETE FROM trades")
    
    print("=== 持仓 ===")
    seed_holdings("div_v6", "dividend_yield_v6.json")
    seed_holdings("micro_cap", "micro_cap_400.json")
    seed_holdings("supabase", "supabase_strategy.json")
    
    print("\n=== 交易 ===")
    seed_trades("div_v6", "dividend_yield_v6.json")
    seed_trades("micro_cap", "micro_cap_400.json")
    seed_trades("supabase", "supabase_strategy.json")
    
    db.commit()
    db.close()
    print("\nDone!")


if __name__ == "__main__":
    seed()
