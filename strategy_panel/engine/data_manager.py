"""
数据管理 — 从雷菱API下载数据，增量更新本地Parquet
"""
import os, sys, requests, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import *

import pandas as pd
import numpy as np

H = {"Authorization": f"Bearer {API_TOKEN}"}

def _api_call(path, params=None, stream=False, timeout=120):
    r = requests.get(f"{API_BASE}{path}", params=params, headers=H,
                     stream=stream, timeout=timeout)
    r.raise_for_status()
    return r

def _download_parquet(path, params, save_path):
    """下载Parquet到本地文件"""
    r = _api_call(path, params=params, stream=True, timeout=300)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk if chunk else b'')  # filter keep-alive chunks
    return pd.read_parquet(save_path)

def _to_date(series):
    """统一日期转换 (处理uint16陷阱)"""
    if series.dtype == "uint16":
        return pd.to_datetime(series, unit="D", origin="unix")
    return pd.to_datetime(series)

def get_trade_calendar():
    """
    获取交易日历并缓存
    """
    path = os.path.join(DATA_DIR, "calendar.parquet")
    # 先检查本地
    if os.path.exists(path):
        df = pd.read_parquet(path)
        last_date = df['trade_date'].max()
        print(f"  本地日历已有 {len(df)} 行, 最新: {last_date}")
        # 查API最新日期
        r = _api_call("/ch/ref_calendar", {"order": "desc", "limit": 3})
        new_data = r.json()["data"]
        api_dates = [d['trade_date'] for d in new_data]
        api_latest = max(api_dates)
        if str(api_latest) <= str(last_date):
            return df
        print(f"  日历有更新，拉取增量...")
    else:
        print(f"  日历不存在，全量拉取...")

    r = _api_call("/ch/ref_calendar/parquet", stream=True, timeout=300)
    with open(path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk)
    df = pd.read_parquet(path)
    df['trade_date'] = _to_date(df['trade_date'])
    df.to_parquet(path)
    print(f"  日历已保存: {len(df)} 行")
    return df

def get_stock_info():
    """获取股票基本信息 (全A股)"""
    path = os.path.join(DATA_DIR, "stock_info.parquet")
    if os.path.exists(path):
        df = pd.read_parquet(path)
        print(f"  股票信息已缓存: {len(df)} 只")
        return df
    r = _api_call("/ch/ref_security/parquet", stream=True, timeout=300)
    with open(path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk)
    df = pd.read_parquet(path)
    df.to_parquet(path)
    print(f"  股票信息已保存: {len(df)} 只")
    return df

def _get_local_data_range(table_name):
    """检查本地数据已有的日期范围"""
    path = os.path.join(DATA_DIR, f"{table_name}.parquet")
    if not os.path.exists(path):
        return None, None
    df = pd.read_parquet(path, columns=['trade_date'])
    min_d = df['trade_date'].min()
    max_d = df['trade_date'].max()
    if df['trade_date'].dtype == "uint16":
        min_d = pd.to_datetime(min_d, unit="D", origin="unix")
        max_d = pd.to_datetime(max_d, unit="D", origin="unix")
    return min_d, max_d

def update_kline_1d(calendar=None):
    """
    增量更新日K线
    """
    path = os.path.join(DATA_DIR, "kline_1d.parquet")
    min_local, max_local = _get_local_data_range("kline_1d")

    if min_local is None:
        print("  [kline_1d] 无本地数据，全量拉取5年...")
        start = None  # API默认全量
    else:
        # 从本地最大日期 + 1天开始拉
        start = (pd.Timestamp(max_local) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"  [kline_1d] 增量拉取: {start} → 昨天")

    params = {}
    if start:
        params['start_date'] = start

    r = _api_call("/ch/ods_kline_1d/parquet", params=params, stream=True, timeout=300)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk)

    new_df = pd.read_parquet(tmp_path)
    if len(new_df) == 0:
        os.remove(tmp_path)
        print("  [kline_1d] 无新数据")
        return pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame()

    new_df['trade_date'] = _to_date(new_df['trade_date'])

    if os.path.exists(path):
        old_df = pd.read_parquet(path)
        old_df['trade_date'] = _to_date(old_df['trade_date'])
        # 去重
        combined = pd.concat([old_df, new_df]).drop_duplicates(
            subset=['symbol', 'trade_date'], keep='last').sort_values('trade_date')
    else:
        combined = new_df

    # 保存
    combined.to_parquet(path)
    os.remove(tmp_path)
    print(f"  [kline_1d] 共 {len(combined)} 行, 日期范围: {combined['trade_date'].min()} → {combined['trade_date'].max()}")
    return combined

def update_adj_factor():
    """增量更新复权因子"""
    path = os.path.join(DATA_DIR, "adj_factor.parquet")
    min_local, max_local = _get_local_data_range("adj_factor")
    if min_local is not None:
        start = (pd.Timestamp(max_local) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        start = None
        print("  [adj_factor] 无本地数据，全量拉取...")

    params = {}
    if start:
        params['start_date'] = start
        print(f"  [adj_factor] 增量拉取: {start}")

    r = _api_call("/ch/ods_adj_factor_daily/parquet", params=params, stream=True, timeout=300)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk)

    new_df = pd.read_parquet(tmp_path)
    if len(new_df) == 0:
        os.remove(tmp_path)
        print("  [adj_factor] 无新数据")
        return pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame()

    new_df['trade_date'] = _to_date(new_df['trade_date'])

    if os.path.exists(path):
        old_df = pd.read_parquet(path)
        old_df['trade_date'] = _to_date(old_df['trade_date'])
        combined = pd.concat([old_df, new_df]).drop_duplicates(
            subset=['symbol', 'trade_date'], keep='last').sort_values('trade_date')
    else:
        combined = new_df

    combined.to_parquet(path)
    os.remove(tmp_path)
    print(f"  [adj_factor] 共 {len(combined)} 行")
    return combined

def update_security_status():
    """增量更新停牌/ST状态"""
    path = os.path.join(DATA_DIR, "security_status.parquet")
    min_local, max_local = _get_local_data_range("security_status")
    if min_local is not None:
        start = (pd.Timestamp(max_local) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        start = None
        print("  [security_status] 无本地数据，全量拉取...")

    params = {}
    if start:
        params['start_date'] = start
        print(f"  [security_status] 增量拉取: {start}")

    r = _api_call("/ch/ods_security_status_daily/parquet", params=params, stream=True, timeout=300)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk)

    new_df = pd.read_parquet(tmp_path)
    if len(new_df) == 0:
        os.remove(tmp_path)
        print("  [security_status] 无新数据")
        return pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame()

    new_df['trade_date'] = _to_date(new_df['trade_date'])

    if os.path.exists(path):
        old_df = pd.read_parquet(path)
        old_df['trade_date'] = _to_date(old_df['trade_date'])
        combined = pd.concat([old_df, new_df]).drop_duplicates(
            subset=['symbol', 'trade_date'], keep='last').sort_values('trade_date')
    else:
        combined = new_df

    combined.to_parquet(path)
    os.remove(tmp_path)
    print(f"  [security_status] 共 {len(combined)} 行")
    return combined

def update_financial_data():
    """下载财务数据 (资产负债表 + 利润表 = 全量覆盖)"""
    tables = {
        "balance_sheet": {
            "path": os.path.join(DATA_DIR, "balance_sheet.parquet"),
            "api": "/ch/ods_balance_sheet_raw/parquet",
            "factor": "symbol,report_period,ann_date,total_assets,total_liab,tot_share_equity_excl_min_int",
            "date_col": "report_period",
        },
        "income_stmt": {
            "path": os.path.join(DATA_DIR, "income_stmt.parquet"),
            "api": "/ch/ods_income_raw/parquet",
            "factor": "symbol,report_period,ann_date,net_pro_excl_min_int_inc,tot_opera_rev",
            "date_col": "report_period",
        },
    }

    for name, cfg in tables.items():
        path = cfg["path"]
        if os.path.exists(path):
            print(f"  [{name}] 已缓存, 跳过 (财报全量覆盖, 无需增量)")
            continue
        print(f"  [{name}] 首次下载全量...")

        r = _api_call(cfg["api"], params={"factor": cfg["factor"],
                                           "date_col": cfg["date_col"]},
                      stream=True, timeout=300)
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024*1024):
                f.write(chunk)
        df = pd.read_parquet(path)
        df['report_period'] = _to_date(df['report_period'])
        if 'ann_date' in df.columns:
            df['ann_date'] = _to_date(df['ann_date'])

        # 资产负债表 key 重命名 (英文命名)
        if name == "balance_sheet":
            df = df.rename(columns={
                'tot_share_equity_excl_min_int': 'total_equity',
                'total_liab': 'total_liabilities',
            })

        # 利润表 key 重命名
        if name == "income_stmt":
            df = df.rename(columns={
                'net_pro_excl_min_int_inc': 'net_profit',
                'tot_opera_rev': 'revenue',
            })

        df.to_parquet(path)
        print(f"  [{name}] 已保存: {len(df)} 行")

def update_market_cap():
    """从API下载市值数据 (下载全量, 覆盖更新)"""
    path = os.path.join(DATA_DIR, "market_cap.parquet")
    if os.path.exists(path):
        print("  [market_cap] 已缓存")
        return pd.read_parquet(path)

    print("  [market_cap] 从API下载...")
    # 用 /factors/market_cap 端点下载
    r = _api_call("/factors/market_cap", stream=True, timeout=300)
    tmp_path = path + ".tmp"
    # /factors 端点返回的是JSON格式, 需特殊处理
    import json
    data = r.json()
    records = data.get("data", [])
    if not records:
        # 尝试直接下载 parquet 文件
        r2 = _api_call("/files/home/data/RQdata_files/rq_factor_market_cap_latest.parquet",
                       stream=True, timeout=300)
        with open(tmp_path, "wb") as f:
            for chunk in r2.iter_content(1024*1024):
                f.write(chunk)
        df = pd.read_parquet(tmp_path)
    else:
        df = pd.DataFrame(records)

    if 'date' in df.columns:
        df['date'] = _to_date(df['date'])

    df.to_parquet(path)
    os.makedirs(tmp_path, exist_ok=True)
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    print(f"  [market_cap] 已保存: {len(df)} 行")
    return df

def run_full_update():
    """
    完整数据更新流程
    """
    print("=" * 50)
    print("[DATA] 开始数据更新...")
    os.makedirs(DATA_DIR, exist_ok=True)

    calendar = get_trade_calendar()
    stock_info = get_stock_info()
    df_k = update_kline_1d(calendar)
    df_adj = update_adj_factor()
    df_status = update_security_status()
    update_financial_data()
    update_market_cap()

    print("[OK] 数据更新完成")
    return calendar, stock_info, df_k, df_adj, df_status

if __name__ == "__main__":
    run_full_update()
