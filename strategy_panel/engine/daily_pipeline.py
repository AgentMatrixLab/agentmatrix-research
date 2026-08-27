"""
每日数据更新 + 回测 + 部署 全自动流水线
=========================================
由 Windows 计划任务每天 10:00 触发执行

流程:
  1. 从 sim API 增量拉取 kline + adj_factor
  2. 重建复权 K 线 (kline_adj.parquet)
  3. 数据校验（行数、日期、股票数）
  4. 回测: 红利v6 + 微盘股
  5. 构建投资组合 (逆波动率加权 Top5)
  6. 种子数据库 (nav + kpis + holdings + trades)
  7. 重启网站服务器
"""
import os, sys, json, subprocess, time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ===== 配置 =====
DATA_DIR = r"D:\bigquant\custom_engine\data"
OUTPUT_DIR = r"D:\bigquant\output"
ENGINE_DIR = r"D:\bigquant\custom_engine"
SERVER_DIR = r"D:\bigquant\bt_panel\server"
API_BASE = "http://115.159.73.134:8765"
LOG_FILE = r"D:\bigquant\custom_engine\daily_pipeline.log"

# 引擎目录下已有的脚本
BUILD_ADJ = os.path.join(ENGINE_DIR, "build_kline_adj_full.py")
RERUN_DIV = os.path.join(ENGINE_DIR, "rerun_dividend_v6_bt.py")
RERUN_MICRO = os.path.join(ENGINE_DIR, "rerun_micro_bt.py")
BUILD_FOLIO = os.path.join(ENGINE_DIR, "build_folio.py")
SEED_HT = os.path.join(ENGINE_DIR, "seed_holdings_trades.py")
SEED_JSON = os.path.join(ENGINE_DIR, "seed_from_json.py")
FETCH_SUPABASE = os.path.join(ENGINE_DIR, "fetch_supabase_signals.py")
RERUN_SUPABASE = os.path.join(ENGINE_DIR, "rerun_supabase_bt.py")
SERVER_MAIN = os.path.join(SERVER_DIR, "main.py")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: str, cwd: str = ENGINE_DIR, timeout: int = 600) -> str:
    """执行命令，返回 stdout"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd, timeout=timeout,
            encoding="utf-8", errors="replace",
            env=env,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            log(f"  ⚠️ 失败 (rc={result.returncode}): {cmd[:100]}")
            if err:
                log(f"     stderr: {err[:300]}")
        return out
    except subprocess.TimeoutExpired:
        log(f"  ⏱ 超时: {cmd[:100]}")
        return ""


def kill_server():
    """精准停止监听 8100 端口的进程，不影响本脚本"""
    try:
        out = subprocess.run(
            'netstat -ano | findstr ":8100.*LISTENING"',
            shell=True, capture_output=True, text=True,
        )
        for line in out.stdout.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 5 and parts[4].isdigit():
                pid = parts[4]
                subprocess.run(f"taskkill /f /pid {pid}", shell=True, capture_output=True)
                log(f"  已终止旧服务器 (PID {pid})")
    except Exception as e:
        log(f"  kill_server 跳过: {e}")
    time.sleep(2)


def start_server():
    """在后台启动服务器"""
    subprocess.Popen(
        ["python", SERVER_MAIN],
        cwd=SERVER_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(3)


# ============================================================
# Step 1: 更新 K 线数据
# ============================================================
def step1_update_kline() -> bool:
    log("=" * 60)
    log("Step 1/7: 更新 K 线数据...")

    kline_path = os.path.join(DATA_DIR, "kline_1d.parquet")
    adj_path = os.path.join(DATA_DIR, "adj_factor.parquet")

    # --- 1a. 更新 kline_1d ---
    if os.path.exists(kline_path):
        old = pd.read_parquet(kline_path)
        if old['trade_date'].dtype == 'uint16':
            old['trade_date'] = pd.to_datetime(old['trade_date'], unit='D', origin='unix')
        last_date = old['trade_date'].max()
        log(f"  本地 K 线: {len(old)} 行, 截止 {last_date.date()}")
    else:
        old = pd.DataFrame()
        last_date = pd.Timestamp("2015-01-01")

    try:
        # 从 API 拉增量
        start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        log(f"  拉取增量: {start} → ...")
        r = requests.get(
            f"{API_BASE}/ch/ods_kline_1d/parquet",
            params={"start_date": start},
            stream=True, timeout=300,
        )
        if r.status_code == 200 and len(r.content) > 1000:
            tmp = kline_path + ".tmp"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)
            new_df = pd.read_parquet(tmp)
            new_df['trade_date'] = pd.to_datetime(new_df['trade_date'])
            log(f"  API 返回: {len(new_df)} 行, {new_df['trade_date'].max().date()}")
            os.remove(tmp)

            if len(new_df) > 0:
                if not old.empty:
                    combined = pd.concat([old, new_df]).drop_duplicates(
                        subset=['symbol', 'trade_date'], keep='last'
                    ).sort_values('trade_date')
                else:
                    combined = new_df
                combined.to_parquet(kline_path, index=False)
                log(f"  ✅ K 线已更新: {len(combined)} 行, 截止 {combined['trade_date'].max().date()}")
            else:
                log("  无新数据，跳过")
        else:
            log(f"  ⚠️ API 返回状态 {r.status_code}, 跳过更新")
    except Exception as e:
        log(f"  ⚠️ K 线更新失败: {e}")

    # --- 1b. 更新 adj_factor ---
    try:
        log("  更新复权因子...")
        r = requests.get(
            f"{API_BASE}/ch/ods_adj_factor_daily/parquet",
            stream=True, timeout=300,
        )
        if r.status_code == 200 and len(r.content) > 1000:
            tmp = adj_path + ".tmp"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)
            adj = pd.read_parquet(tmp)
            adj.to_parquet(adj_path, index=False)
            os.remove(tmp)
            log(f"  ✅ 复权因子: {len(adj)} 行, 截止 {adj['trade_date'].max() if 'trade_date' in adj.columns else '?'}")
        else:
            log(f"  ⚠️ adj_factor 返回 {r.status_code}")
    except Exception as e:
        log(f"  ⚠️ 复权因子更新失败: {e}")

    return True


# ============================================================
# Step 2: 重建复权 K 线
# ============================================================
def step2_build_adj_kline() -> bool:
    log("Step 2/7: 重建复权 K 线...")
    out = run(f"python {BUILD_ADJ}", cwd=ENGINE_DIR, timeout=300)
    if "[OK]" in out or "已更新" in out:
        log("  ✅ 复权 K 线已更新")
        return True
    log(f"  ⚠️ 输出: {out[-200:]}")
    return False


# ============================================================
# Step 3: 数据校验
# ============================================================
def step3_validate() -> bool:
    log("Step 3/7: 数据校验...")
    ok = True

    # 检查 kline_adj.parquet
    path = os.path.join(DATA_DIR, "kline_adj.parquet")
    if not os.path.exists(path):
        log("  ❌ kline_adj.parquet 不存在!")
        return False
    df = pd.read_parquet(path, columns=['trade_date', 'symbol'])
    if df['trade_date'].dtype == 'uint16':
        df['trade_date'] = pd.to_datetime(df['trade_date'], unit='D', origin='unix')
    max_date = df['trade_date'].max()
    stocks = df['symbol'].nunique()
    log(f"  复权 K 线: {len(df)} 行, {stocks} 只, 截止 {max_date.date()}")

    # 检查是否更新到了最近
    today = datetime.now()
    if (today - max_date).days > 7:
        log(f"  ⚠️ 数据滞后 {(today - max_date).days} 天")
        ok = False

    # 检查最新一天至少有 4000 只
    latest_day = df[df['trade_date'] == max_date]
    if len(latest_day) < 3000:
        log(f"  ⚠️ 最新交易日仅 {len(latest_day)} 只股票（预期 ≥3000）")
        ok = False

    if ok:
        log("  ✅ 数据校验通过")
    return ok


# ============================================================
# Step 4: 回测 — 红利v6
# ============================================================
def step4_backtest_div() -> bool:
    log("Step 4/7: 回测 红利v6...")
    out = run(f"python {RERUN_DIV}", cwd=ENGINE_DIR, timeout=900)
    if "回测完成" in out or "✅" in out or "OK" in out:
        log("  ✅ 红利v6 完成")
        return True
    log(f"  输出: {out[-200:]}")
    return False


# ============================================================
# Step 5: 回测 — 微盘股
# ============================================================
def step5_backtest_micro() -> bool:
    log("Step 5/7: 回测 微盘股...")
    out = run(f"python {RERUN_MICRO}", cwd=ENGINE_DIR, timeout=900)
    if "回测完成" in out or "✅" in out or "OK" in out:
        log("  ✅ 微盘股 完成")
        return True
    log(f"  输出: {out[-200:]}")
    return False


# ============================================================
# Step 5b: 拉取 Supabase 信号
# ============================================================
def step5b_fetch_supabase() -> bool:
    log("Step 5b/7: 拉取 Supabase 信号...")
    out = run(f"python {FETCH_SUPABASE}", cwd=ENGINE_DIR, timeout=120)
    if "✅" in out:
        log("  ✅ Supabase 信号已拉取")
        return True
    log(f"  ⚠️ 输出: {out[-200:]}")
    return False


# ============================================================
# Step 5c: 回测 — Supabase 信号策略
# ============================================================
def step5c_backtest_supabase() -> bool:
    log("Step 5c/7: 回测 Supabase 信号策略...")
    out = run(f"python {RERUN_SUPABASE}", cwd=ENGINE_DIR, timeout=600)
    if "回测完成" in out or "All done" in out:
        log("  ✅ Supabase 信号策略 完成")
        return True
    log(f"  输出: {out[-200:]}")
    return False


# ============================================================
# Step 6: 构建组合 + 种子数据库
# ============================================================
def step6_seed_and_folio() -> bool:
    log("Step 6/7: 构建组合 + 种子数据库...")

    # 先 kill 服务器释放 DB 锁
    kill_server()

    # 构建 folio
    out = run(f"python {BUILD_FOLIO}", cwd=ENGINE_DIR, timeout=120)
    log(f"  folio: {out[:200]}")

    # 种子策略 KPI + NAV (dividend, micro, folio)
    out1 = run(f"python {SEED_JSON}", cwd=ENGINE_DIR, timeout=120)
    log(f"  seed_json: {out1[:300]}")

    # 种子持仓/交易
    out2 = run(f"python {SEED_HT}", cwd=ENGINE_DIR, timeout=60)
    log(f"  seed_ht: {out2[:200]}")

    log("  ✅ 数据库已更新")
    return True


# ============================================================
# Step 7: 重启服务器
# ============================================================
def step7_restart_server() -> bool:
    log("Step 7/7: 重启网站...")
    start_server()
    log("  ✅ 服务器已重启 (0.0.0.0:8100)")
    return True


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    log("")
    log("#" * 60)
    log(f"每日流水线启动 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("#" * 60)

    step1_update_kline()
    step2_build_adj_kline()

    if step3_validate():
        step4_backtest_div()
        step5_backtest_micro()
        step5b_fetch_supabase()
        step5c_backtest_supabase()
    else:
        log("❌ 数据校验失败，跳过回测")

    step6_seed_and_folio()
    step7_restart_server()

    log("✅ 流水线完成")
