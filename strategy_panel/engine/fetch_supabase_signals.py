"""
从 Supabase 拉取交易信号，过滤 ETF，解析 note，输出 JSON 供回测引擎使用。

信号格式：
  - daily_stock_pool:  个股信号（note 中文，如 "[执行指令=开盘价] 持有2300股"）
  - monthly_etf_pool:  ETF/LOF 信号（note 编码乱码但结构相同）
  - 过滤: 排除 stock_name_raw 含 "ETF" 的品种
  - 转换符号: SHSE.XXXXXX → XXXXXX.SH, SZSE.XXXXXX → XXXXXX.SZ
  - 权重: 使用 target_position_raw 字段
  - 仅 note 含 "持有" 或 "全部卖出" 的行才触发

输出: supabase_signals.json
  {
    "trade_dates": ["2026-07-28", "2026-08-03", ...],
    "signals": {
      "2026-07-28": [{"symbol": "301273.SZ", "weight": 0.0368, "action": "HOLD"}, ...],
      ...
    }
  }
"""
import os, sys, json, requests
from collections import defaultdict

SUPABASE_URL = "https://wcexkmmpqmaqwiywntnc.supabase.co/rest/v1"
SUPABASE_KEY = "sb_publishable_MmjB1Z6vUzbhOEmuMI9t4w_YgGPzvMW"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "supabase_signals.json")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def query(path, params=None):
    r = requests.get(f"{SUPABASE_URL}/{path}", headers=HEADERS, params=params)
    r.raise_for_status()
    return r


def is_etf(stock_name_raw: str) -> bool:
    """通过名称判断是否为ETF"""
    if not stock_name_raw:
        return False
    return "ETF" in stock_name_raw


def convert_symbol(supabase_sym: str) -> str:
    """
    SHSE.605589 → 605589.SH
    SZSE.301273 → 301273.SZ
    """
    if supabase_sym.startswith("SHSE."):
        return supabase_sym[5:] + ".SH"
    elif supabase_sym.startswith("SZSE."):
        return supabase_sym[5:] + ".SZ"
    return supabase_sym  # fallback


def parse_note(note: str) -> dict:
    """
    解析 note 字段，返回 {"type": "hold"|"sell"|"skip", "shares": int|None}
    
    有效模式:
      "[执行指令=开盘价] 持有2300股"  → hold, 2300
      "[????=???] ??44200?"           → hold, 44200 (乱码但结构相同)
      "[执行指令=开盘价] 全部卖出"      → sell
      "[????=???] ????"                → sell (乱码)
    """
    if not note:
        return {"type": "skip", "shares": None}
    
    if "全部卖出" in note:
        return {"type": "sell", "shares": None}
    
    # 尝试匹配 "持有XXXX股" 或乱码 "??44200?"
    import re
    # 中文持股市
    m = re.search(r'持有(\d+)股', note)
    if m:
        return {"type": "hold", "shares": int(m.group(1))}
    
    # 乱码格式: "????=???] ??44200?" → 匹配数字
    m = re.search(r'\?\?(\d+)\?', note)
    if m:
        return {"type": "hold", "shares": int(m.group(1))}
    
    # 无法解析
    return {"type": "skip", "shares": None}


def fetch_latest_signals() -> list:
    """获取最新日期的 ACTIVE 信号"""
    # 先查最新日期
    r = query("signals", {
        "select": "trade_date",
        "order": "trade_date.desc",
        "limit": "1",
    })
    if not r.json():
        print("  No signals found")
        return []
    
    latest_date = r.json()[0]["trade_date"]
    print(f"  最新信号日期: {latest_date}")
    
    # 获取该日期的所有 ACTIVE 信号
    r = query("signals", {
        "select": "*",
        "trade_date": f"eq.{latest_date}",
        "status": "eq.ACTIVE",
    })
    return r.json()


def fetch_all_signals() -> list:
    """获取所有信号（用于回测）"""
    all_signals = []
    offset = 0
    limit = 1000
    while True:
        r = query("signals", {
            "select": "*",
            "order": "trade_date.asc",
            "limit": str(limit),
            "offset": str(offset),
        })
        page = r.json()
        if not page:
            break
        all_signals.extend(page)
        offset += limit
        if len(page) < limit:
            break
        print(f"  已拉取 {len(all_signals)} 条...")
    return all_signals


def build_signal_map(raw_signals: list) -> dict:
    """
    将原始信号转换为回测引擎可用的信号映射。
    返回: { "trade_dates": [...], "signals": { "date": [{symbol, weight, action}, ...] } }
    """
    # 过滤 & 分组
    filtered = []
    skipped = 0
    for sig in raw_signals:
        # 1. 过滤 ETF
        name = sig.get("stock_name_raw", "")
        if is_etf(name):
            skipped += 1
            continue
        
        # 2. 解析 note
        note = sig.get("note", "")
        parsed = parse_note(note)
        if parsed["type"] == "skip":
            # note 无法解析 → 跳过（用户要求：note中写明了才触发）
            skipped += 1
            continue
        
        # 3. 转换符号
        sym = convert_symbol(sig["symbol"])
        
        # 4. 权重
        weight = sig.get("target_position_raw")
        if weight is None:
            weight = 0.0
        
        filtered.append({
            "date": sig["trade_date"],
            "symbol": sym,
            "weight": float(weight),
            "action": sig["action"],
            "note_type": parsed["type"],
        })
    
    print(f"  有效信号: {len(filtered)} 条 | 跳过: {skipped} 条 (ETF或无法解析)")
    
    # 按日期分组
    date_groups = defaultdict(list)
    for sig in filtered:
        date_groups[sig["date"]].append({
            "symbol": sig["symbol"],
            "weight": sig["weight"],
            "action": sig["action"],
        })
    
    trade_dates = sorted(date_groups.keys())
    print(f"  信号日: {len(trade_dates)} 天, {trade_dates[0]} → {trade_dates[-1]}" if trade_dates else "  无信号日")
    
    return {
        "trade_dates": trade_dates,
        "signals": {d: date_groups[d] for d in trade_dates},
    }


def fetch_supabase_signals():
    """主入口：拉取全部历史信号并输出JSON"""
    print("=" * 50)
    print("[Supabase] 拉取交易信号...")
    
    raw = fetch_all_signals()
    if not raw:
        print("  ❌ 无信号数据")
        return None
    
    result = build_signal_map(raw)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ 保存: {OUTPUT_FILE}")
    return result


if __name__ == "__main__":
    fetch_supabase_signals()
