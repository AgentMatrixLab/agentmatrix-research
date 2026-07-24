"""从服务器下载所有相关数据到本地"""
import paramiko, os, time

HOST, PORT = "115.159.73.134", 22
USER, PASS = "data", "AgentMatrix2026#"
LOCAL = "E:/custom_engine/data"

# 需要下载的文件列表: (服务器路径, 本地文件名)
FILES = [
    # === K线 (按年) ===
    *[(f"RQdata_files/kline/kline_{y}.parquet", f"kline_{y}.parquet") for y in range(2010, 2025)],
    ("RQdata_files/kline_full/kline_2025.parquet", "kline_2025.parquet"),
    ("RQdata_files/kline_daily/kline_2026.parquet", "kline_2026.parquet"),

    # === 财务 ===
    ("RQdata_files/financials/balance_2010_2024.parquet", "balance_sheet_full.parquet"),
    ("RQdata_files/financials/income_2010_2024.parquet", "income_stmt_full.parquet"),

    # === 市值 ===
    ("RQdata_files/adj_factor_mcap_financials/market_cap_2017_2025.parquet", "market_cap_2017_2025.parquet"),
    ("RQdata_files/shares_daily/shares_2026.parquet", "shares_2026.parquet"),

    # === 指数 ===
    ("RQdata_files/index_kline/index_daily.parquet", "index_daily_raw.parquet"),

    # === 复权因子 ===
    ("RQdata_files/adj_factor_mcap_financials/ex_factor_2017_2025.parquet", "ex_factor_2017_2025.parquet"),

    # === ST状态 ===
    ("RQdata_files/st_status/st_status_2026.parquet", "st_status_2026.parquet"),
]

os.makedirs(LOCAL, exist_ok=True)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, PORT, USER, PASS, timeout=15)
sftp = ssh.open_sftp()

total_mb = 0
ok = 0
fail = 0

for remote_rel, local_name in FILES:
    remote_path = f"/home/data/{remote_rel}"
    local_path = os.path.join(LOCAL, local_name)
    
    # 检查远程文件是否存在
    try:
        stat = sftp.stat(remote_path)
        size_mb = stat.st_size / 1024 / 1024
    except:
        print(f"  SKIP (不存在): {remote_rel}")
        fail += 1
        continue
    
    # 跳过已存在且大小一致的本地文件
    if os.path.exists(local_path) and abs(os.path.getsize(local_path) - stat.st_size) < 100:
        print(f"  SKIP (已存在): {local_name} ({size_mb:.1f}MB)")
        ok += 1
        total_mb += size_mb
        continue
    
    print(f"  下载 {local_name} ({size_mb:.1f}MB)...", end=" ", flush=True)
    t0 = time.time()
    try:
        sftp.get(remote_path, local_path)
        elapsed = time.time() - t0
        print(f"OK {elapsed:.1f}s")
        ok += 1
        total_mb += size_mb
    except Exception as e:
        print(f"FAIL: {e}")
        fail += 1

sftp.close()
ssh.close()

print(f"\n{'='*50}")
print(f"  完成: {ok} 成功, {fail} 跳过/失败")
print(f"  总计: {total_mb:.0f}MB")
