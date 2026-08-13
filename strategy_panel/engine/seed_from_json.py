"""将 backtest JSON 和 folio JSON 的最新数据写入 SQLite"""
import os, json, sqlite3
from datetime import datetime

OUTPUT_DIR = r"D:\bigquant\output"
DB_PATH = r"D:\bigquant\bt_panel\server\bt_panel.db"

def load_json(name):
    path = os.path.join(OUTPUT_DIR, name)
    for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise RuntimeError(f"Cannot decode {name}")


db = sqlite3.connect(DB_PATH)
db.execute("PRAGMA journal_mode=WAL")


def _unpack_strategy(data: dict):
    """JSON 格式: {"strategies": [{...}], ...} — 取第一个策略"""
    if "strategies" in data:
        return data["strategies"][0]
    return data


def seed_strategy(sid: str, json_file: str, name: str, tag: str):
    data = load_json(json_file)
    s = _unpack_strategy(data)
    print(f"\n=== {sid} ({name}) ===")
    
    ar = s.get("annual_return", 0.0)   # 百分比，如 26.67
    tr = s.get("total_return", 0.0)
    sr = s.get("sharpe", 0.0)
    md = s.get("max_drawdown", 0.0)
    vol = s.get("annual_vol", 0.15)
    
    print(f"  annualReturn={ar}%, sharpe={sr}, maxDrawdown={md}%")
    
    db.execute("""INSERT OR REPLACE INTO strategies (id, name, tag, status, version, created_at)
                  VALUES (?,?,?,?,?,?)""",
               [sid, name, tag, "active", "v6" if sid == "div_v6" else "v1", datetime.now().isoformat()])
    
    db.execute("""INSERT OR REPLACE INTO kpis (strategy_id, total_return, annual_return, sharpe, max_drawdown, win_rate, volatility, updated_at)
                  VALUES (?,?,?,?,?,?,?,?)""",
               [sid, round(tr / 100, 4), round(ar / 100, 4), round(sr, 4), round(md / 100, 4), 0.5, round(vol / 100 if vol > 1 else vol, 4), datetime.now().isoformat()])
    
    # NAV field: "nav_history" [{date, nav, is_simulation}, ...]
    nav_list = s.get("nav_history", [])
    if isinstance(nav_list, dict):
        nav_list = []
    if not nav_list:
        print(f"  ⚠️ 无NAV数据")
        return
    
    db.execute("DELETE FROM nav_series WHERE strategy_id=?", [sid])
    
    first_nav = nav_list[0].get("nav", 1000000)
    for pt in nav_list:
        d = pt.get("date", "")
        n = pt.get("nav", 0)
        norm = n / first_nav if first_nav > 0 else n
        db.execute("INSERT INTO nav_series (strategy_id, date, nav, benchmark_nav, drawdown) VALUES (?,?,?,?,?)",
                   [sid, str(d)[:10], round(norm, 4), 1.0, 0.0])
    
    print(f"  NAV: {len(nav_list)} 点, {nav_list[0]['date']} -> {nav_list[-1]['date']}")


def seed_folio():
    data = load_json("folio.json")
    s = _unpack_strategy(data)
    print(f"\n=== folio ===")
    
    ar = s.get("annual_return", 0.0)
    tr = s.get("total_return", 0.0)
    sr = s.get("sharpe", 0.0)
    md = s.get("max_drawdown", 0.0)
    vol = s.get("annual_vol", 0.20)
    
    print(f"  annualReturn={ar}%, sharpe={sr}, maxDrawdown={md}%")
    
    db.execute("""INSERT OR REPLACE INTO strategies (id, name, tag, status, version, created_at)
                  VALUES (?,?,?,?,?,?)""",
               ["folio", "综合组合(Top5逆波动率)", "folio", "active", "auto", datetime.now().isoformat()])
    
    db.execute("""INSERT OR REPLACE INTO kpis (strategy_id, total_return, annual_return, sharpe, max_drawdown, win_rate, volatility, updated_at)
                  VALUES (?,?,?,?,?,?,?,?)""",
               ["folio", round(tr / 100, 4), round(ar / 100, 4), round(sr, 4), round(md / 100, 4), 0.55, round(vol / 100 if vol > 1 else vol, 4), datetime.now().isoformat()])
    
    nav_list = s.get("nav_history", [])
    if isinstance(nav_list, dict):
        nav_list = []
    if nav_list:
        db.execute("DELETE FROM nav_series WHERE strategy_id='folio'")
        first_nav = nav_list[0].get("nav", 1.0)
        for pt in nav_list:
            d = pt.get("date", "")
            n = pt.get("nav", 0)
            norm = n / first_nav if first_nav > 0 else n
            db.execute("INSERT INTO nav_series (strategy_id, date, nav, benchmark_nav, drawdown) VALUES (?,?,?,?,?)",
                       ["folio", str(d)[:10], round(norm, 4), 1.0, 0.0])
        print(f"  NAV: {len(nav_list)} 点")


seed_strategy("div_v6", "dividend_yield_v6.json", "红利v6(聚宽对齐)", "dividend")
seed_strategy("micro_cap", "micro_cap_400.json", "微盘股(最小400)", "micro_cap")
seed_strategy("supabase", "supabase_strategy.json", "Supabase信号策略", "signal")
seed_folio()

db.commit()
db.close()
print("\n✅ 数据库已更新")
