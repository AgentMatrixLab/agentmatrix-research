r"""
统一数据管理层 — 复用已有 + SIM增量
================================
数据源:
  E:/使用Qlib/data/ (复用已有数据)
    ├── kline/kline_2010~2026.parquet  ← 按年分片日K (open/high/low/close/volume/amount)
    ├── financials/                    ← 财务报表
    ├── index_components/              ← 指数成分股
    ├── industry/                      ← 申万行业
    └── rq_full/                       ← 换手率/指数行情
  SIM API (/sim/*) → 每日增量 (最近60天) — 每天18:30后更新

数据流:
  python update_data.py
      → 检查本地数据 → 从 SIM 拉增量 → 合并到历年 kline 文件
      → 自动合并复权 → kline_adj.parquet
      → 自动生成 Qlib bin

产出文件:
  kline/kline_2010~2026.parquet  ← 按年日K (增量追加到当年文件)
  kline_adj.parquet              ← kline × adj_factor (含 close_adj/open_adj/...)
"""

import os, sys, time, requests, json, glob
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    API_BASE, API_TOKEN, DATA_DIR, QLIB_BIN_DIR, QLIB_FEATURE_MAP,
    ADJUST_MODE, ONLY_CSI_300, ONLY_CSI_500, ONLY_CSI_1000,
)


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _to_date(series):
    """统一日期转换 (处理 uint16 陷阱)"""
    if series.dtype == "uint16":
        return pd.to_datetime(series, unit="D", origin="unix")
    return pd.to_datetime(series)


def _fmt_date(d):
    """安全格式化日期"""
    if hasattr(d, 'strftime'):
        return d.strftime('%Y-%m-%d')
    return str(d)[:10]


def _now_str():
    return datetime.now().strftime('%H:%M:%S')


# ═══════════════════════════════════════════════════════════════
# K线数据加载 (按年分片)
# ═══════════════════════════════════════════════════════════════

def _kline_dir():
    """kline 分片目录"""
    return os.path.join(DATA_DIR, "kline")


def load_kline(columns=None):
    """加载全部 K线 (从按年分片的 parquet 合并) — 自动统一列名
    
    逐年文件可能有不同列名:
      - 股票: order_book_id 或 symbol
      - 日期: date 或 trade_date
      - 成交额: amount 或 total_turnover
    2025文件可能缺少 volume/total_turnover, 2026文件列名已映射
    """
    d = _kline_dir()
    import re
    raw = sorted(glob.glob(os.path.join(d, "kline_*.parquet")))
    # 只保留逐年文件 (kline_20XX.parquet), 排除 kline_1d / kline_adj_old 等非逐年文件
    files = [f for f in raw if re.search(r'kline_20\d{2}\.parquet$', os.path.basename(f))]
    if not files:
        return None

    # 先读取 schema 确认每个文件的实际列名, 避免指定不存在列时报错
    def _safe_read(f, want_columns):
        """安全读取: 只选文件中存在的列"""
        import pyarrow.parquet as pq
        actual = pq.read_metadata(f).schema.names
        if want_columns is None:
            return pd.read_parquet(f)
        avail = [c for c in want_columns if c in actual]
        # 也检查映射后的列名 (如symbol/trade_date直接存在)
        alt = ['symbol', 'trade_date', 'amount']
        avail.extend([c for c in alt if c in actual and c not in avail])
        if not avail:
            return pd.read_parquet(f)  # 全部读
        return pd.read_parquet(f, columns=avail)

    parts = []
    for f in files:
        df = _safe_read(f, columns)
        # 统一列名
        col_map = {}
        if 'order_book_id' in df.columns: col_map['order_book_id'] = 'symbol'
        if 'date' in df.columns:          col_map['date'] = 'trade_date'
        if 'total_turnover' in df.columns: col_map['total_turnover'] = 'amount'
        if col_map:
            df.columns = [col_map.get(c, c) for c in df.columns]
        # 代码格式: XSHE/XSHG → SZ/SH (可能没有该后缀)
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].str.replace('.XSHE', '.SZ', regex=False)
            df['symbol'] = df['symbol'].str.replace('.XSHG', '.SH', regex=False)

        parts.append(df)

    df = pd.concat(parts, ignore_index=True, copy=False)
    del parts
    if 'trade_date' in df.columns:
        df['trade_date'] = _to_date(df['trade_date'])

    return df.sort_values(['symbol', 'trade_date']).reset_index(drop=True)


def kline_date_range():
    """返回 kline 数据的日期范围"""
    info = {}
    d = _kline_dir()
    files = sorted(glob.glob(os.path.join(d, "kline_*.parquet")))
    for f in files:
        yr = os.path.basename(f).replace("kline_", "").replace(".parquet", "")
        try:
            t = pd.read_parquet(f, columns=['date'])
            t['date'] = _to_date(t['date'])
            info[yr] = (t['date'].min(), t['date'].max(), len(t))
        except Exception:
            pass
    return info


def load_adj_factor():
    """加载复权因子 (如有)"""
    p = os.path.join(DATA_DIR, "adj_factor.parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    return None


# ═══════════════════════════════════════════════════════════════
# SIM API 客户端 (无需 Token) — 每日增量
# ═══════════════════════════════════════════════════════════════

class SimClient:
    """Sim Trading API 客户端 — 每日增量数据 (最近60天)"""

    EXCHANGE_MAP = {"SZ": "XSHE", "SH": "XSHG", "BJ": "XSHG"}

    def __init__(self):
        self.base = API_BASE

    def _get(self, path, params=None, retry=3, timeout=120):
        for i in range(retry):
            try:
                r = requests.get(f"{self.base}{path}", params=params, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 422:
                    print(f"  ⚠️ SIM 参数错误: {r.text[:200]}")
                    return None
                else:
                    if i < retry - 1:
                        time.sleep(2)
            except Exception as e:
                if i < retry - 1:
                    time.sleep(2)
                else:
                    print(f"  ⚠️ SIM 请求失败: {e}")
        return None

    def summary(self):
        return self._get("/sim/summary", timeout=10)

    @staticmethod
    def to_sim_symbol(s: str) -> str:
        parts = s.rsplit(".", 1)
        if len(parts) == 2 and parts[1] in SimClient.EXCHANGE_MAP:
            return f"{parts[0]}.{SimClient.EXCHANGE_MAP[parts[1]]}"
        return s

    @staticmethod
    def to_local_symbol(s: str) -> str:
        rev = {v: k for k, v in SimClient.EXCHANGE_MAP.items()}
        parts = s.rsplit(".", 1)
        if len(parts) == 2 and parts[1] in rev:
            return f"{parts[0]}.{rev[parts[1]]}"
        return s

    def _get_stock_list(self) -> list:
        kline = load_kline(columns=['symbol'])
        if kline is not None:
            symbols = kline['symbol'].dropna().unique().tolist()
            return sorted(set(self.to_sim_symbol(s) for s in symbols))
        return []

    def fetch_kline(self, symbols=None, days=60, batch_size=200):
        """分批拉取最新K线"""
        if symbols is None:
            symbols = self._get_stock_list()
        print(f"  [{_now_str()}] SIM K线: {len(symbols)} 只 × {days}天, 每批{batch_size}只...", end=" ", flush=True)
        t0 = time.time()

        all_data = []
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            r = self._get("/sim/kline", {"symbols": ",".join(batch), "days": days, "limit": 50000})
            if r and "data" in r:
                all_data.extend(r["data"])
            time.sleep(0.2)

        if not all_data:
            print("无数据")
            return None

        df = pd.DataFrame(all_data)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['symbol'] = df['symbol'].apply(self.to_local_symbol)
        df = df.drop_duplicates(subset=['symbol', 'trade_date'], keep='last')
        df = df.sort_values(['symbol', 'trade_date']).reset_index(drop=True)

        print(f"{len(df):,} 行, {df['symbol'].nunique()} 只 "
              f"({_fmt_date(df['trade_date'].min())} → {_fmt_date(df['trade_date'].max())}), "
              f"{time.time() - t0:.0f}s")
        return df

    def fetch_factors(self, symbols=None, days=60, batch_size=200):
        """分批拉取估值因子"""
        if symbols is None:
            symbols = self._get_stock_list()
        print(f"  [{_now_str()}] SIM 因子: {len(symbols)} 只 × {days}天...", end=" ", flush=True)
        t0 = time.time()

        all_data = []
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            r = self._get("/sim/factors", {"symbols": ",".join(batch), "days": days, "limit": 50000})
            if r and "data" in r:
                all_data.extend(r["data"])
            time.sleep(0.2)

        if not all_data:
            print("无数据")
            return None

        df = pd.DataFrame(all_data)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['symbol'] = df['symbol'].apply(self.to_local_symbol)
        df = df.drop_duplicates(subset=['symbol', 'trade_date'], keep='last')
        df = df.sort_values(['symbol', 'trade_date']).reset_index(drop=True)

        print(f"{len(df):,} 行, {df['symbol'].nunique()} 只, {time.time() - t0:.0f}s")

        path = os.path.join(DATA_DIR, "daily_factors.parquet")
        if os.path.exists(path):
            old = pd.read_parquet(path)
            old['trade_date'] = _to_date(old['trade_date'])
            old = old[old['trade_date'] < df['trade_date'].min()]
            df = pd.concat([old, df], ignore_index=True)
        df.to_parquet(path, index=False)

        latest = df[df['trade_date'] == df['trade_date'].max()]
        latest.to_parquet(os.path.join(DATA_DIR, "daily_factors_latest.parquet"), index=False)
        return df

    def fetch_shares(self, symbols=None, batch_size=200):
        """分批拉取股本市值"""
        if symbols is None:
            symbols = self._get_stock_list()
        print(f"  [{_now_str()}] SIM 股本: {len(symbols)} 只...", end=" ", flush=True)
        t0 = time.time()

        all_data = []
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            r = self._get("/sim/shares", {"symbols": ",".join(batch), "limit": 50000})
            if r and "data" in r:
                all_data.extend(r["data"])
            time.sleep(0.2)

        if not all_data:
            print("无数据")
            return None

        df = pd.DataFrame(all_data)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['symbol'] = df['symbol'].apply(self.to_local_symbol)
        df = df.drop_duplicates(subset=['symbol', 'trade_date'], keep='last')
        df = df.sort_values(['symbol', 'trade_date']).reset_index(drop=True)
        df = df.dropna(subset=['market_cap'])

        print(f"{len(df):,} 行, {df['symbol'].nunique()} 只, {time.time() - t0:.0f}s")

        df_save = df.rename(columns={'symbol': 'order_book_id', 'trade_date': 'date'})
        path = os.path.join(DATA_DIR, "market_cap.parquet")
        if os.path.exists(path):
            old = pd.read_parquet(path)
            old['date'] = _to_date(old['date'])
            old = old[old['date'] < df_save['date'].min()]
            df_save = pd.concat([old, df_save], ignore_index=True)
        df_save.to_parquet(path, index=False)

        latest = df_save[df_save['date'] == df_save['date'].max()]
        latest.to_parquet(os.path.join(DATA_DIR, "market_cap_full.parquet"), index=False)
        return df_save


# ═══════════════════════════════════════════════════════════════
# 统一数据管理器
# ═══════════════════════════════════════════════════════════════

class DataManager:
    """
    统一数据管理 — 复用已有 + SIM增量

    用法:
      dm = DataManager()
      dm.daily_sync()    # 从 SIM 拉增量 → 合并到 kline 分片 → 重建 kline_adj
      dm.report()        # 查看数据状态
    """

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(_kline_dir(), exist_ok=True)
        self.sim = SimClient()

    # ══════════════════════════════════════════════════════════
    # 每日增量同步 (从 SIM)
    # ══════════════════════════════════════════════════════════

    def daily_sync(self, skip_qlib=False):
        """
        每日增量同步: 从 SIM 拉最新数据 → 合并到按年分片 → 重建衍生文件。
        """
        print("=" * 55)
        print("  [SIM] 每日增量同步")
        print("=" * 55)
        t0 = time.time()

        # 0. 检查 SIM 数据新鲜度
        s = self.sim.summary()
        if s:
            for k, v in s.items():
                if isinstance(v, dict) and 'latest_date' in v:
                    print(f"  SIM {k}: {v['latest_date']}")

        # 1. 拉取 K线增量
        df_k = self.sim.fetch_kline(days=60)
        if df_k is not None:
            self._merge_kline(df_k)

        # 2. 重建 kline_adj.parquet
        self._build_kline_adj(force=True)

        # 3. 拉取估值因子 + 股本市值
        self.sim.fetch_factors(days=60)
        self.sim.fetch_shares()

        # 4. 更新 Qlib bin (增量)
        if not skip_qlib:
            self._rebuild_qlib()

        elapsed = time.time() - t0
        print(f"\n  ✅ 每日同步完成 ({elapsed:.0f}s)")
        self.report()

    # ══════════════════════════════════════════════════════════
    # 内部: K线合并到按年分片
    # ══════════════════════════════════════════════════════════

    def _merge_kline(self, df_new: pd.DataFrame):
        """
        将 SIM K线增量合并到按年分片的 kline 文件中。
        SIM 数据以 symbol 为准，按年份写入对应文件。
        """
        d = _kline_dir()
        existing = load_kline()

        if existing is None:
            # 全新：按年写入
            df_new['year'] = df_new['trade_date'].dt.year
            for yr, grp in df_new.groupby('year'):
                fp = os.path.join(d, f"kline_{yr}.parquet")
                grp.drop(columns=['year']).to_parquet(fp)
                print(f"  [merge] 新建 kline_{yr}.parquet: {len(grp):,} 行")
            return

        # 合并
        old_max = existing['trade_date'].max()
        new_min = df_new['trade_date'].min()
        new_max = df_new['trade_date'].max()

        print(f"  [merge] 旧: {len(existing):,} 行 ({_fmt_date(existing['trade_date'].min())} → {_fmt_date(old_max)})")
        print(f"  [merge] 新: {len(df_new):,} 行 ({_fmt_date(new_min)} → {_fmt_date(new_max)})")

        if new_min > old_max:
            # 纯增量：只追加到当前年份文件
            combined = df_new
        else:
            # 有重叠：保留旧 > 覆盖新
            old_keep = existing[existing['trade_date'] < new_min]
            combined = pd.concat([old_keep, df_new], ignore_index=True)
            combined = combined.drop_duplicates(subset=['symbol', 'trade_date'], keep='last')
            combined = combined.sort_values(['symbol', 'trade_date']).reset_index(drop=True)

        # 按年回写
        combined['year'] = combined['trade_date'].dt.year
        for yr, grp in combined.groupby('year'):
            fp = os.path.join(d, f"kline_{yr}.parquet")
            grp.drop(columns=['year']).to_parquet(fp)

        yrs = sorted(combined['year'].unique())
        print(f"  [merge] ✅ 已更新年份: {yrs[0]}~{yrs[-1]}, "
              f"({_fmt_date(combined['trade_date'].min())} → {_fmt_date(combined['trade_date'].max())})")

    # ══════════════════════════════════════════════════════════
    # 内部: 复权合并
    # ══════════════════════════════════════════════════════════

    def _build_kline_adj(self, force=False):
        """
        将 kline(按年分片) × adj_factor → kline_adj.parquet
        包含后复权价格列: open_adj, high_adj, low_adj, close_adj
        """
        path_out = os.path.join(DATA_DIR, "kline_adj.parquet")

        kline = load_kline()
        if kline is None:
            print("  [build_adj] ⚠️ kline 数据不存在, 跳过")
            return

        adj = load_adj_factor()
        adj_available = adj is not None

        if os.path.exists(path_out) and not force:
            # 检查是否需要重建
            kline_files = sorted(glob.glob(os.path.join(_kline_dir(), "kline_*.parquet")))
            max_mtime = max(os.path.getmtime(f) for f in kline_files) if kline_files else 0
            if os.path.getmtime(path_out) >= max_mtime:
                print(f"  [build_adj] kline_adj 已是最新, 跳过")
                return

        t0 = time.time()
        print(f"  [{_now_str()}] 合并复权 kline_adj.parquet ...", end=" ", flush=True)

        if adj_available:
            adj['trade_date'] = _to_date(adj['trade_date'])
            df = kline.merge(adj, on=['symbol', 'trade_date'], how='left')
            df['adj_factor'] = df['adj_factor'].fillna(1.0)
        else:
            df = kline.copy()
            df['adj_factor'] = 1.0

        # 计算后复权价格
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[f'{col}_adj'] = df[col] * df['adj_factor']

        # 保留关键列
        keep_cols = ['symbol', 'trade_date',
                     'open', 'high', 'low', 'close', 'volume', 'amount',
                     'open_adj', 'high_adj', 'low_adj', 'close_adj']
        keep_cols = [c for c in keep_cols if c in df.columns]

        df = df[keep_cols]
        df = df.sort_values(['symbol', 'trade_date']).reset_index(drop=True)
        df.to_parquet(path_out)

        print(f"{len(df):,} 行 "
              f"({_fmt_date(df['trade_date'].min())} → {_fmt_date(df['trade_date'].max())}), "
              f"{time.time() - t0:.1f}s")

    def _rebuild_qlib(self):
        """重建 Qlib bin 数据"""
        try:
            from engine.qlib_bridge import ensure_qlib_data
            ensure_qlib_data()
        except ImportError:
            print("  [qlib] pyqlib 未安装, 跳过")
        except Exception as e:
            print(f"  [qlib] ⚠️ 重建失败: {e}")

    # ══════════════════════════════════════════════════════════
    # 数据状态报告
    # ══════════════════════════════════════════════════════════

    def report(self):
        """输出数据状态摘要"""
        print(f"\n  {'─' * 45}")
        print(f"  📋 数据状态  (DATA_DIR = {DATA_DIR})")
        print(f"  {'─' * 45}")

        # K线按年
        yr_info = kline_date_range()
        if yr_info:
            total_rows = sum(v[2] for v in yr_info.values())
            yrs = sorted(yr_info.keys())
            print(f"  ✅ K线 (分片)     {len(yr_info)}年 {yrs[0]}~{yrs[-1]}, {total_rows:,.0f}行")
        else:
            print(f"  ❌ K线 (分片)    缺失")

        # kline_adj
        pa = os.path.join(DATA_DIR, "kline_adj.parquet")
        if os.path.exists(pa):
            try:
                df = pd.read_parquet(pa, columns=['trade_date'])
                df['trade_date'] = _to_date(df['trade_date'])
                size = os.path.getsize(pa) / 1024 / 1024
                print(f"  ✅ kline_adj      {size:.0f}MB  "
                      f"{_fmt_date(df['trade_date'].min())} → {_fmt_date(df['trade_date'].max())}")
            except Exception:
                print(f"  ⚠️ kline_adj     文件存在但无法读取")
        else:
            print(f"  ⚠️ kline_adj     未生成 (运行 sync 自动生成)")

        # 其他文件
        for fname, label in [
            ("adj_factor.parquet", "复权因子"),
            ("daily_factors.parquet", "估值因子"),
            ("market_cap.parquet", "股本市值"),
        ]:
            p = os.path.join(DATA_DIR, fname)
            if os.path.exists(p):
                size = os.path.getsize(p) / 1024 / 1024
                try:
                    df = pd.read_parquet(p)
                    dc = [c for c in df.columns if 'date' in c.lower()]
                    if dc:
                        df[dc[0]] = _to_date(df[dc[0]])
                        rng = f"{_fmt_date(df[dc[0]].min())} → {_fmt_date(df[dc[0]].max())}"
                        print(f"  ✅ {label:10s}   {size:6.0f}MB  {len(df):,}r  {rng}")
                    else:
                        print(f"  ✅ {label:10s}   {size:6.0f}MB  {len(df):,}r")
                except Exception:
                    print(f"  ⚠️ {label:10s}   {size:6.0f}MB  无法读取")
            else:
                print(f"  ❌ {label:10s}   缺失")

        # SIM 新鲜度
        try:
            s = self.sim.summary()
            if s:
                print(f"  {'─' * 45}")
                print(f"  SIM API 新鲜度:")
                for k, v in s.items():
                    if isinstance(v, dict) and 'latest_date' in v:
                        print(f"     {k}: {v['latest_date']}")
        except Exception:
            pass

        print(f"  {'─' * 45}")

    def needs_update(self):
        """检查 SIM 是否有比本地更新的数据"""
        yr_info = kline_date_range()
        if not yr_info:
            return True

        local_max = max(v[1] for v in yr_info.values())
        try:
            s = self.sim.summary()
            if s and 'kline' in s:
                sim_latest = s['kline'].get('latest_date')
                if sim_latest:
                    return pd.Timestamp(sim_latest) > local_max
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def run_full_update():
    """向后兼容的入口 — 每日同步"""
    dm = DataManager()
    if not glob.glob(os.path.join(_kline_dir(), "kline_*.parquet")):
        print("[首次] 未检测到数据, 请确保 DATA_DIR 指向已有数据目录")
        return
    dm.daily_sync()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="数据管理器 (复用已有数据 + SIM增量)")
    parser.add_argument("action", nargs="?", default="report",
                        choices=["sync", "report"],
                        help="sync=增量同步 / report=状态报告")
    parser.add_argument("--skip-qlib", action="store_true", help="跳过Qlib重建")
    args = parser.parse_args()

    dm = DataManager()

    if args.action == "sync":
        dm.daily_sync(skip_qlib=args.skip_qlib)
    elif args.action == "report":
        dm.report()
