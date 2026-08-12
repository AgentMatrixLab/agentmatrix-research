"""
Qlib 桥接层 — Parquet → Qlib bin 格式转换 + 策略适配

用法:
  from engine.qlib_bridge import ParquetToQlibConverter, QlibBacktestRunner

  # 数据转换
  converter = ParquetToQlibConverter()
  converter.convert_all()

  # Qlib 回测
  runner = QlibBacktestRunner()
  nav_df, metrics = runner.run_strategy("small_cap", rebalance_freq=21)
"""
import os, sys, json, time, struct
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DATA_DIR, QLIB_BIN_DIR, QLIB_FEATURE_MAP, RESULTS_DIR
from config import BACKTEST_YEARS, INIT_CAPITAL, TRADE_FEE_RATE, SLIPPAGE, ST_TAX_RATE


# ═══════════════════════════════════════════════════════════════
# Part 1: Parquet → Qlib bin 格式转换器
# ═══════════════════════════════════════════════════════════════

class ParquetToQlibConverter:
    """将本地 Parquet 数据转换为 Qlib 二进制格式 (.day 文件)

    Qlib 标准 bin 目录结构:
      qlib_bin/
        calendars/day.txt          ← 交易日列表
        instruments/all.txt        ← 股票代码 + 上市/退市日期
        features/{symbol}/{field}.day  ← 每只股票每个特征的 float64 数组

    重要: kline_adj.parquet 符号格式为 .XSHE/.XSHG (米筐标准),
    但 Qlib 标准格式为 .SZ/.SH。本转换器自动处理格式映射。
    """

    @staticmethod
    def _to_qlib_symbol(sym):
        """将 .XSHE/.XSHG → .SZ/.SH, 其他格式保持原样"""
        sym = sym.replace('.XSHE', '.SZ').replace('.XSHG', '.SH')
        return sym

    @staticmethod
    def _from_qlib_symbol(sym):
        """将 .SZ/.SH → .XSHE/.XSHG, 用于反向查询 kline 数据"""
        # 只替换后缀, 避免误替换代码中的子串
        if sym.endswith('.SZ'):
            return sym[:-3] + '.XSHE'
        if sym.endswith('.SH'):
            return sym[:-3] + '.XSHG'
        return sym

    def __init__(self, data_dir=None, qlib_dir=None):
        self.data_dir = data_dir or DATA_DIR
        self.qlib_dir = Path(qlib_dir or QLIB_BIN_DIR)
        self.manifest_path = self.qlib_dir / "manifest.json"

    # ── 日历 ──

    def build_calendar(self, force=False):
        """生成 calendars/day.txt"""
        cal_dir = self.qlib_dir / "calendars"
        cal_dir.mkdir(parents=True, exist_ok=True)
        cal_file = cal_dir / "day.txt"

        if cal_file.exists() and not force:
            return self._read_calendar()

        cal = pd.read_parquet(os.path.join(self.data_dir, "calendar.parquet"))
        if cal['trade_date'].dtype == "uint16":
            cal['trade_date'] = pd.to_datetime(cal['trade_date'], unit="D", origin="unix")
        cal = cal.sort_values('trade_date')
        dates = cal['trade_date'].dt.strftime("%Y-%m-%d").tolist()

        cal_file.write_text("\n".join(dates), encoding="utf-8")
        print(f"  [qlib] 日历: {len(dates)} 天 ({dates[0]} → {dates[-1]})")
        return dates

    def _read_calendar(self):
        cal_file = self.qlib_dir / "calendars" / "day.txt"
        return cal_file.read_text().strip().split("\n")

    # ── 股票列表 ──

    def build_instruments(self, symbols=None, force=False):
        """生成 instruments/all.txt

        参数:
          symbols: 股票代码列表, 为 None 则用 kline_adj 中全部股票
        """
        inst_dir = self.qlib_dir / "instruments"
        inst_dir.mkdir(parents=True, exist_ok=True)
        inst_file = inst_dir / "all.txt"

        if inst_file.exists() and not force and symbols is None:
            return self._read_instruments()

        dates = self._read_calendar()
        cal_start, cal_end = dates[0], dates[-1]

        if symbols is None:
            kline = pd.read_parquet(
                os.path.join(self.data_dir, "kline_adj.parquet"),
                columns=['symbol']
            )
            raw_symbols = sorted(kline['symbol'].unique())
            # 转换为 Qlib 标准格式 (.XSHE/.XSHG → .SZ/.SH)
            symbols = [self._to_qlib_symbol(s) for s in raw_symbols]

        # 确保所有符号都是 Qlib 格式
        qlib_symbols = [self._to_qlib_symbol(s) for s in symbols]

        lines = [f"{s}\t{cal_start}\t{cal_end}" for s in qlib_symbols]
        inst_file.write_text("\n".join(lines), encoding="utf-8")
        print(f"  [qlib] 股票列表: {len(qlib_symbols)} 只")
        return qlib_symbols

    def _read_instruments(self):
        inst_file = self.qlib_dir / "instruments" / "all.txt"
        symbols = []
        for line in inst_file.read_text().strip().split("\n"):
            if line.strip():
                symbols.append(line.split("\t")[0])
        return symbols

    # ── 特征文件 ──

    def build_features(self, symbols=None, feature_map=None,
                       batch_size=200, force=False):
        """批量生成 features/{symbol}/{field}.day.bin

        为每只股票每个特征生成一个 float64 数组，
        长度与日历对齐, 缺失日期填 NaN。

        参数:
          feature_map: {qlib_name: parquet_column} 映射
                       默认使用 QLIB_FEATURE_MAP
          batch_size: 每批股票数
          force: 是否强制重建

        性能: 200只/批, 约 30 秒/批 (取决于数据量)
        """
        if feature_map is None:
            feature_map = QLIB_FEATURE_MAP

        qlib_features = list(feature_map.keys())   # .day 文件名
        pq_columns = list(feature_map.values())     # Parquet 列名

        dates = self._read_calendar()
        date_idx = {d: i for i, d in enumerate(dates)}
        n_dates = len(dates)

        if symbols is None:
            symbols = self.build_instruments()

        # 读取 K 线数据 (只取需要的列)
        kline = pd.read_parquet(
            os.path.join(self.data_dir, "kline_adj.parquet")
        )
        if kline['trade_date'].dtype == "uint16":
            kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit="D", origin="unix")

        # ═══ 关键修复: 将 kline 符号转换为 Qlib 标准格式 .SZ/.SH ═══
        # kline_adj.parquet 使用 .XSHE/.XSHG (米筐格式),
        # 但 Qlib instruments 和 features 目录使用 .SZ/.SH
        kline['symbol'] = kline['symbol'].apply(self._to_qlib_symbol)

        # 找出实际存在的 Parquet 列
        available = []
        for qf, pq in feature_map.items():
            if pq in kline.columns:
                available.append((qf, pq))
            else:
                print(f"  [qlib] ⚠️ 跳过缺失列: {pq}")

        existing = self._list_existing_features() if not force else set()

        feat_dir = self.qlib_dir / "features"
        feat_dir.mkdir(parents=True, exist_ok=True)

        total = len(symbols)
        converted = 0
        skipped = 0
        t0 = time.time()

        for batch_start in range(0, total, batch_size):
            batch = symbols[batch_start:batch_start + batch_size]
            batch_set = set(batch)

            batch_kline = kline[kline['symbol'].isin(batch_set)]

            for sym in batch:
                sym_dir = feat_dir / sym
                sym_dir.mkdir(parents=True, exist_ok=True)

                sd = batch_kline[batch_kline['symbol'] == sym].sort_values('trade_date')

                for qf, pq in available:
                    # Qlib 标准格式: {field}.day.bin (float32 + 4-byte start_index header)
                    feat_path = sym_dir / f"{qf}.day.bin"

                    if f"{sym}/{qf}.day.bin" in existing and not force:
                        skipped += 1
                        continue

                    arr = np.full(n_dates, np.nan, dtype=np.float32)
                    for _, row in sd.iterrows():
                        d = row['trade_date']
                        if hasattr(d, 'strftime'):
                            d_str = d.strftime('%Y-%m-%d')
                        else:
                            d_str = str(d)[:10]
                        idx = date_idx.get(d_str)
                        if idx is not None:
                            val = row[pq]
                            if not (isinstance(val, float) and np.isnan(val)):
                                arr[idx] = float(val)

                    # Qlib FileFeatureStorage 格式: [start_index: float32][data: float32 array]
                    with open(feat_path, "wb") as fp:
                        fp.write(struct.pack("<f", 0.0))  # start_index=0
                        arr.tofile(fp)
                    converted += 1

            elapsed = time.time() - t0
            done = min(batch_start + batch_size, total)
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(f"\r  [qlib] 特征写入: {done}/{total} 只 "
                  f"({done/total*100:.0f}%)  {rate:.0f}只/秒 ETA:{eta:.0f}秒",
                  end='', flush=True)

        print()
        print(f"  [qlib] 特征: {converted} 个文件新建, {skipped} 个跳过 "
              f"(耗时 {time.time()-t0:.0f}秒)")

        # 写入 factor 特征 (Qlib 需要 factor 来处理交易单位)
        self._write_factor_feature(symbols, dates)

        self._write_manifest(symbols, qlib_features, dates)

    def _write_factor_feature(self, symbols, dates):
        """为每只股票生成 factor.day.bin (全部值=1.0)

        Qlib 的 exchange 需要 factor 来确定交易单位(如A股100股/手)。
        没有 factor → 回退到 adjusted_price 模式 → 交易无法正常执行。
        """
        n_dates = len(dates)
        feat_dir = self.qlib_dir / "features"

        for sym in symbols:
            sym_dir = feat_dir / sym
            sym_dir.mkdir(parents=True, exist_ok=True)

            arr = np.ones(n_dates, dtype=np.float32)
            path = sym_dir / "factor.day.bin"
            with open(path, "wb") as fp:
                fp.write(struct.pack("<f", 0.0))  # start_index=0
                arr.tofile(fp)

        print(f"  [qlib] factor: {len(symbols)} 只 (全部=1.0)")

    def build_benchmark(self, symbols=None):
        """合成一个 SH000300 基准指数 (全市场平均收盘价)

        Qlib 回测要求 benchmark 存在, 这里用所有股票 close 均值模拟沪深300。
        """
        bench_name = "SH000300"
        dates = self._read_calendar()
        date_idx = {d: i for i, d in enumerate(dates)}
        n_dates = len(dates)

        if symbols is None:
            symbols = self._read_instruments()

        kline = pd.read_parquet(
            os.path.join(self.data_dir, "kline_adj.parquet"),
            columns=['symbol', 'trade_date', 'close_adj']
        )
        if kline['trade_date'].dtype == "uint16":
            kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit="D", origin="unix")

        # 符号格式转换: .XSHE/.XSHG → .SZ/.SH
        kline['symbol'] = kline['symbol'].apply(self._to_qlib_symbol)

        # 每个交易日所有股票 close_adj 的均值
        avg_close = kline[kline['symbol'].isin(set(symbols))].groupby('trade_date')['close_adj'].mean()

        arr = np.full(n_dates, np.nan, dtype=np.float64)
        for dt, val in avg_close.items():
            d_str = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)[:10]
            idx = date_idx.get(d_str)
            if idx is not None:
                arr[idx] = float(val)

        # 写入特征文件 (Qlib 标准格式: float32 + 4-byte start_index header)
        bench_dir = self.qlib_dir / "features" / bench_name.lower()
        bench_dir.mkdir(parents=True, exist_ok=True)

        arr_f32 = arr.astype(np.float32)
        # close.day.bin
        with open(bench_dir / "close.day.bin", "wb") as fp:
            fp.write(struct.pack("<f", 0.0))
            arr_f32.tofile(fp)
        # open.day.bin + factor.day.bin (用 close 填充, 防止 Qlib 报缺)
        with open(bench_dir / "open.day.bin", "wb") as fp:
            fp.write(struct.pack("<f", 0.0))
            arr_f32.tofile(fp)
        ones = np.ones(len(arr_f32), dtype=np.float32)
        with open(bench_dir / "factor.day.bin", "wb") as fp:
            fp.write(struct.pack("<f", 0.0))
            ones.tofile(fp)

        # 加入 instruments
        inst_path = self.qlib_dir / "instruments" / "all.txt"
        cal_dates = self._read_calendar()
        with open(inst_path, 'a') as f:
            f.write(f"\n{bench_name}\t{cal_dates[0]}\t{cal_dates[-1]}")

        print(f"  [qlib] 基准: {bench_name} ({len(dates)}天)")

    def _list_existing_features(self):
        """扫描已存在的特征文件"""
        existing = set()
        feat_dir = self.qlib_dir / "features"
        if not feat_dir.exists():
            return existing
        for sym_dir in feat_dir.iterdir():
            if sym_dir.is_dir():
                for f in sym_dir.iterdir():
                    # Qlib 格式: {field}.day.bin
                    if f.name.endswith('.day.bin'):
                        existing.add(f"{sym_dir.name}/{f.name}")
        return existing

    def _write_manifest(self, symbols, features, dates):
        manifest = {
            "converted_at": datetime.now().isoformat(),
            "symbol_count": len(symbols),
            "feature_count": len(features),
            "features": features,
            "date_start": dates[0] if dates else None,
            "date_end": dates[-1] if dates else None,
            "total_dates": len(dates),
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    def read_manifest(self):
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text())
        return None

    # ── 一键全量转换 ──

    def convert_all(self, symbols=None, feature_map=None, force=False):
        """一键全量转换: 日历 + 股票列表 + 特征文件 + 基准"""
        self.build_calendar(force=force)
        symbols = self.build_instruments(symbols, force=force)
        self.build_features(symbols, feature_map, force=force)
        self.build_benchmark(symbols)
        print(f"  [qlib] ✅ 数据转换完成: {self.qlib_dir}")

    def needs_update(self):
        """检查本地 Parquet 是否有新数据 (比 manifest 记录的更新)"""
        manifest = self.read_manifest()
        if manifest is None:
            return True

        cal = pd.read_parquet(os.path.join(self.data_dir, "calendar.parquet"))
        if cal['trade_date'].dtype == "uint16":
            cal['trade_date'] = pd.to_datetime(cal['trade_date'], unit="D", origin="unix")
        latest_cal = cal['trade_date'].max()

        manifest_end = pd.Timestamp(manifest.get('date_end', '2000-01-01'))
        return latest_cal > manifest_end


# ═══════════════════════════════════════════════════════════════
# Part 2: Qlib 回测执行器
# ═══════════════════════════════════════════════════════════════

class QlibBacktestRunner:
    """使用 Qlib 引擎运行回测, 输出与 BacktestEngine 统一格式

    用法:
      runner = QlibBacktestRunner()
      nav_df, metrics = runner.run_strategy("small_cap", rebalance_freq=21)
    """

    def __init__(self, qlib_dir=None):
        self.qlib_dir = str(qlib_dir or QLIB_BIN_DIR)
        self._initialized = False

    def _ensure_init(self):
        """初始化 Qlib (只执行一次)。

        ``LocalProvider`` 会依据 ``kernels`` 使用 joblib 读取每只股票的
        特征。Windows 的 spawn 模式下，多进程既没有性能优势，也容易因为
        入口模块被重复导入而失败；固定为单核/线程后仍然走 Qlib 的完整
        ``backtest`` 流程，只是不再创建子进程。
        """
        if self._initialized:
            return
        import qlib
        qlib.init(
            provider_uri=self.qlib_dir,
            region="cn",
            kernels=1,
            joblib_backend="threading",
        )
        self._initialized = True

    def _safe_end_time(self, end_time):
        """避免 Qlib 在日历边界处的 off-by-one bug — end_time 往前退一天"""
        from qlib.data import D
        try:
            cal = D.calendar()
            end_ts = pd.Timestamp(end_time)
            if len(cal) > 0 and end_ts >= cal[-1]:
                return cal[-2].strftime('%Y-%m-%d') if len(cal) >= 2 else str(cal[-1])[:10]
        except Exception:
            pass
        return end_time

    def _shift_signal_to_execution_date(self, signal, delay_days):
        """将 T 日生成的信号映射到后续交易日执行。

        Qlib 的信号策略会在信号索引所示的交易步下单。自定义引擎的
        约定则是 T 日选股、T+1 日按收盘价成交，因此这里必须按 Qlib
        日历而不是自然日平移，避免周末和节假日造成错位。
        """
        if delay_days == 0:
            return signal
        if delay_days < 0:
            raise ValueError("execution_delay 必须大于或等于 0")

        from qlib.data import D

        calendar = pd.DatetimeIndex(pd.to_datetime(D.calendar())).normalize()
        original_dates = pd.DatetimeIndex(
            pd.to_datetime(signal.index.get_level_values("datetime"))
        ).normalize()
        unique_dates = original_dates.unique()
        positions = calendar.get_indexer(unique_dates)
        missing = unique_dates[positions < 0]
        if len(missing):
            # 历史信号可以早于当前 Qlib 数据起点。这些记录本来就无法
            # 参与本次回测，显式丢弃；只有日历内部的缺口才是数据错误。
            internal_missing = missing[
                (missing >= calendar[0]) & (missing <= calendar[-1])
            ]
            if len(internal_missing):
                raise ValueError(
                    "信号日期不在 Qlib 交易日历中: "
                    + ", ".join(str(d.date()) for d in internal_missing[:5])
                )
            print("  [qlib] 丢弃日历范围外信号: "
                  + ", ".join(str(d.date()) for d in missing))

        available = positions >= 0
        unique_dates = unique_dates[available]
        positions = positions[available]

        valid = positions + delay_days < len(calendar)
        if not valid.all():
            dropped = unique_dates[~valid]
            print("  [qlib] 丢弃无法在日历内延后执行的信号: "
                  + ", ".join(str(d.date()) for d in dropped))

        date_map = {
            original: calendar[pos + delay_days]
            for original, pos in zip(unique_dates[valid], positions[valid])
        }
        keep_mask = original_dates.isin(date_map)
        shifted_dates = original_dates[keep_mask].map(date_map)
        instruments = signal.index.get_level_values("instrument")[keep_mask]
        shifted = signal[keep_mask].copy()
        shifted.index = pd.MultiIndex.from_arrays(
            [shifted_dates, instruments], names=signal.index.names
        )
        print(f"  [qlib] 信号执行延后: T+{delay_days} 交易日 "
              f"({len(unique_dates)} 个信号日)")
        return shifted

    def run_with_signal(self, signal, start_time, end_time,
                        symbols=None, topk=50, n_drop=5,
                        account=INIT_CAPITAL, execution_delay=1):
        """用 Qlib TopkDropoutStrategy 跑回测

        参数:
          signal: pd.Series, MultiIndex=(datetime, instrument), values=score
          start_time, end_time: 回测区间
          symbols: 股票池
          topk: 持仓数量
          n_drop: 缓冲区
          account: 初始资金
          execution_delay: 信号到成交间隔的交易日数；默认 1，即 T+1

        返回:
          (nav_df, metrics_dict) — 与 BacktestEngine 统一格式
        """
        self._ensure_init()

        from qlib.contrib.strategy.signal_strategy import TopkDropoutStrategy
        from qlib.backtest import backtest, executor as ex

        # 不修改调用方持有的信号对象；确保 instrument 是 .SZ/.SH 格式。
        signal = signal.copy()
        _conv = ParquetToQlibConverter()
        signal_index = signal.index
        signal_instruments = signal_index.get_level_values('instrument').map(_conv._to_qlib_symbol)
        new_index = pd.MultiIndex.from_arrays(
            [signal_index.get_level_values('datetime'), signal_instruments],
            names=signal_index.names
        )
        signal.index = new_index
        signal = self._shift_signal_to_execution_date(signal, execution_delay)

        # 确保 symbols 也是 .SZ/.SH 格式
        if symbols:
            symbols = [_conv._to_qlib_symbol(s) for s in symbols]

        strategy = TopkDropoutStrategy(
            signal=signal,
            topk=topk,
            n_drop=n_drop,
            only_tradable=False,
        )

        # Qlib 的 exchange_kwargs 对齐我们 config.py 的费率
        exchange_kwargs = {
            "freq": "day",
            "deal_price": "$close",
            "open_cost": TRADE_FEE_RATE,              # 买入手续费 万3
            "close_cost": TRADE_FEE_RATE + ST_TAX_RATE,  # 卖出: 手续费+印花税
            "min_cost": 5.0,                          # 最低手续费 5元
            "impact_cost": SLIPPAGE,                  # 滑点 (market impact) 0.1%
        }
        if symbols:
            exchange_kwargs["codes"] = symbols

        portfolio_metrics, indicator = backtest(
            start_time=start_time,
            # Qlib has an off-by-one bug at calendar boundary — use second-to-last date
            end_time=self._safe_end_time(end_time),
            strategy=strategy,
            executor={
                "class": "SimulatorExecutor",
                "module_path": "qlib.backtest.executor",
                "kwargs": {
                    "time_per_step": "day",
                    "generate_portfolio_metrics": True,
                },
            },
            account=account,
            exchange_kwargs=exchange_kwargs,
        )

        # 转换 Qlib 结果为统一格式
        nav_df, metrics = self._convert_results(
            portfolio_metrics, indicator, start_time, end_time
        )
        return nav_df, metrics

    def _convert_results(self, portfolio_metrics, indicator, start, end):
        """将 Qlib 的回测输出转为与 BacktestEngine 一致的格式

        Qlib 输出:
          pf = {'1day': (DataFrame, indicator_dict)}
          DataFrame columns: account, return, total_turnover, turnover,
                             total_cost, cost, value, cash, bench
        """
        nav_records = []

        # 提取第一个频率的 DataFrame
        metrics_df = None
        if isinstance(portfolio_metrics, dict):
            for freq_key, tup in portfolio_metrics.items():
                if isinstance(tup, tuple) and len(tup) >= 1:
                    metrics_df = tup[0]
                    break
        elif isinstance(portfolio_metrics, tuple):
            metrics_df = portfolio_metrics[0]

        if metrics_df is not None and isinstance(metrics_df, pd.DataFrame) and len(metrics_df) > 0:
            # account 列 = 每日总资产 (最完整), value = 持仓市值 (首日为 0)
            if 'account' in metrics_df.columns:
                nav_col = metrics_df['account']
            elif 'value' in metrics_df.columns:
                nav_col = metrics_df['value']
            else:
                nav_col = None

            if nav_col is not None:
                nav_col = nav_col.copy()
                # 首日可能是 0 (建仓前) — 用 INIT_CAPITAL 替换
                if nav_col.iloc[0] == 0 or pd.isna(nav_col.iloc[0]):
                    nav_col.iloc[0] = INIT_CAPITAL

                nav_records = [(idx, float(val))
                              for idx, val in nav_col.items()
                              if not np.isnan(val)]

        if not nav_records:
            nav_records = [
                (pd.Timestamp(start), INIT_CAPITAL),
                (pd.Timestamp(end), INIT_CAPITAL),
            ]

        nav_df = pd.DataFrame(nav_records, columns=['date', 'nav'])
        if not nav_df.empty:
            nav_df.set_index('date', inplace=True)
            nav_df.sort_index(inplace=True)

        # 指标
        metrics = {}
        if isinstance(indicator, dict):
            for freq_key, ind_obj in indicator.items():
                if isinstance(ind_obj, dict):
                    # Qlib 的指标以英文 key 存在
                    for qk, v in ind_obj.items():
                        if isinstance(v, (int, float, np.floating)):
                            mk = self._translate_metric_key(qk)
                            if 'return' in qk.lower() or 'drawdown' in qk.lower():
                                metrics[mk] = f"{v:.2%}"
                            elif 'ratio' in qk.lower() or 'sharpe' in qk.lower():
                                metrics[mk] = f"{v:.2f}"
                            elif 'turnover' in qk.lower() or 'cost' in qk.lower():
                                metrics[mk] = f"{v:.4f}"
                            else:
                                metrics[mk] = f"{v:.4f}"

        # 从 NAV 自己算指标 (兜底)
        if len(nav_df) > 2 and nav_df['nav'].iloc[-1] != nav_df['nav'].iloc[0]:
            try:
                from engine.metrics import compute_metrics
                custom_m = compute_metrics(nav_df['nav'])
                for k, v in custom_m.items():
                    if k not in metrics:
                        metrics[k] = v
            except (ZeroDivisionError, ValueError):
                pass

        if len(nav_df) > 1 and '总收益率' not in metrics:
            total_ret = nav_df['nav'].iloc[-1] / nav_df['nav'].iloc[0] - 1
            metrics['总收益率'] = f'{total_ret:.2%}'
        metrics['交易日数'] = len(nav_df)

        return nav_df, metrics

    def _translate_metric_key(self, key):
        """Qlib 指标 key → 中文名"""
        mapping = {
            "annualized_return": "年化收益率",
            "information_ratio": "信息比率",
            "max_drawdown": "最大回撤",
            "annualized_volatility": "年化波动率",
            "sharpe_ratio": "夏普比率",
            "total_return": "总收益率",
            "total_turnover": "总换手率",
            "total_cost": "总费用",
        }
        return mapping.get(key, key)

    def _save_rebalance_csv(self, name, rows):
        """将调仓信号保存为 CSV: date, symbol, shares, weight, price"""
        if not rows:
            return
        df = pd.DataFrame(rows)
        df = df.rename(columns={"datetime": "date", "instrument": "symbol", "score": "weight"})
        df["date"] = df["date"].apply(lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)[:10])
        # 列顺序
        cols = ["date", "symbol", "shares", "weight", "price"]
        df = df[[c for c in cols if c in df.columns]]

        safe_name = name.replace("/", "_").replace(" ", "_")
        out_path = os.path.join(RESULTS_DIR, f"{safe_name}_qlib_rebalance.csv")
        os.makedirs(RESULTS_DIR, exist_ok=True)
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"    调仓报告: {out_path}  ({len(df)} 条)")

    def run_strategy(self, strategy_name, rebalance_freq=21,
                     start_time=None, end_time=None, symbols=None,
                     topk=50):
        """按策略名运行 Qlib 回测 (对外统一接口)

        先在自定义引擎中跑一遍信号收集, 再交给 Qlib 执行。
        """
        from strategies import discover_strategies
        from engine.backtest import BacktestEngine

        strategies = discover_strategies()
        if strategy_name not in strategies:
            raise ValueError(f"策略 '{strategy_name}' 不存在, "
                           f"可选: {list(strategies.keys())}")

        signal_fn = strategies[strategy_name]

        # 用自定义引擎准备数据和日历
        engine = BacktestEngine()
        end_date = engine.calendar['trade_date'].max()
        if end_time is None:
            end_time = end_date.strftime('%Y-%m-%d')

        full_data = engine._prepare_data(end_date)
        trade_dates = sorted(full_data['trade_date'].unique())
        date_groups = dict(tuple(full_data.groupby('trade_date')))

        if start_time is None:
            # 近5年
            start_idx = max(0, len(trade_dates) - int(BACKTEST_YEARS * 252) - 20)
            start_time = trade_dates[start_idx].strftime('%Y-%m-%d')

        # 调仓日
        rebalance_dates = trade_dates[::rebalance_freq]
        rebalance_set = set(rebalance_dates)

        # 构建 Qlib 信号: 在每个调仓日调用策略, 收集 scores
        rows = []
        for d in trade_dates:
            if d < pd.Timestamp(start_time):
                continue
            if d not in rebalance_set:
                continue

            today = date_groups.get(d)
            if today is None or len(today) == 0:
                continue

            tradable = engine._filter_tradable(today)
            if len(tradable) == 0:
                continue

            try:
                signals = signal_fn(tradable)
            except Exception as e:
                continue

            if signals is None or len(signals) == 0:
                continue

            if 'weight' not in signals.columns:
                continue

            # Qlib 要求 datetime 是 pd.Timestamp, 不能是 str
            dt = pd.Timestamp(d)
            price_dict = dict(zip(tradable['symbol'], tradable['close_adj']))
            total_weight = signals['weight'].sum()
            for _, row in signals.iterrows():
                sym = row['symbol']
                w = float(row['weight']) / total_weight if total_weight > 0 else 0
                p = price_dict.get(sym, 0)
                # 按 100 股整手估算股数
                raw_shares = int(w * INIT_CAPITAL / p) if p > 0 else 0
                shares = raw_shares // 100 * 100
                rows.append({
                    'datetime': dt,
                    'instrument': sym,
                    'score': w,
                    'price': round(p, 2),
                    'shares': shares,
                })

        if not rows:
            raise RuntimeError(f"策略 '{strategy_name}' 没有产生任何信号")

        signal_series = pd.DataFrame(rows).set_index(
            ['datetime', 'instrument']
        )['score']

        # 保存调仓报告 CSV (在过滤前, 保存完整选股)
        self._save_rebalance_csv(strategy_name, rows)

        # 过滤: 只保留 Qlib 数据中存在的股票
        _conv = ParquetToQlibConverter()
        qlib_symbols = set(_conv._read_instruments())
        if 'SH000300' in qlib_symbols:
            qlib_symbols.discard('SH000300')

        # 将信号中的 .XSHE/.XSHG 转换为 .SZ/.SH (对齐 Qlib 格式)
        signal_index = signal_series.index
        signal_instruments = signal_index.get_level_values('instrument')
        signal_instruments = signal_instruments.map(_conv._to_qlib_symbol)
        new_index = pd.MultiIndex.from_arrays(
            [signal_index.get_level_values('datetime'), signal_instruments],
            names=signal_index.names
        )
        signal_series.index = new_index

        before = len(signal_series)
        mask = signal_series.index.get_level_values('instrument').isin(qlib_symbols)
        signal_series = signal_series[mask]
        after = len(signal_series)

        if before != after:
            print(f"  [qlib] 信号: {before} → {after} 条 (过滤了 {before-after} 条不在 Qlib 数据中的股票)")
        print(f"  [qlib] 信号: {after} 条 "
              f"({signal_series.index.get_level_values('datetime').nunique()} 个调仓日)")

        return self.run_with_signal(
            signal_series,
            start_time=start_time,
            end_time=end_time,
            symbols=symbols,
            topk=topk,
        )


# ═══════════════════════════════════════════════════════════════
# Part 3: 工具函数
# ═══════════════════════════════════════════════════════════════

def ensure_qlib_data(symbols=None, force=False):
    """确保 Qlib bin 数据存在且是最新的 (数据更新后调用)"""
    converter = ParquetToQlibConverter()

    if not force and not converter.needs_update():
        print("[qlib] 数据已是最新, 跳过")
        return str(converter.qlib_dir)

    print("[qlib] 检测到数据更新, 重新生成 bin 文件...")
    converter.convert_all(symbols=symbols, force=force)
    return str(converter.qlib_dir)


def get_qlib_calendar():
    """获取 Qlib 交易日列表"""
    converter = ParquetToQlibConverter()
    return converter.build_calendar()


def init_qlib(qlib_dir=None):
    """初始化 Qlib 环境 (便捷函数)"""
    import qlib
    uri = qlib_dir or str(QLIB_BIN_DIR)
    qlib.init(provider_uri=uri, region="cn")
    return qlib


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Qlib 桥接工具")
    parser.add_argument("action", nargs="?", default="convert",
                        choices=["convert", "check", "run"])
    parser.add_argument("--strategy", type=str, help="策略名")
    parser.add_argument("--force", action="store_true", help="强制重建")
    parser.add_argument("--symbols", type=int, default=0,
                        help="限制股票数量 (0=全部)")
    args = parser.parse_args()

    if args.action == "convert":
        converter = ParquetToQlibConverter()
        symbols = None
        if args.symbols > 0:
            kline = pd.read_parquet(os.path.join(DATA_DIR, "kline_adj.parquet"), columns=['symbol'])
            all_syms = sorted(kline['symbol'].unique())
            step = max(1, len(all_syms) // args.symbols)
            symbols = all_syms[::step][:args.symbols]
            print(f"限制股票: {len(symbols)} 只")
        converter.convert_all(symbols=symbols, force=args.force)

    elif args.action == "check":
        converter = ParquetToQlibConverter()
        manifest = converter.read_manifest()
        if manifest:
            print("✅ Qlib 数据已存在:")
            for k, v in manifest.items():
                print(f"   {k}: {v}")
        else:
            print("❌ Qlib 数据不存在, 请运行: python engine/qlib_bridge.py convert")
        print(f"   需要更新: {converter.needs_update()}")

    elif args.action == "run":
        if not args.strategy:
            print("请指定 --strategy")
            sys.exit(1)
        runner = QlibBacktestRunner()
        nav_df, metrics = runner.run_strategy(args.strategy)
        print(f"\n策略: {args.strategy}")
        for k, v in metrics.items():
            print(f"  {k}: {v}")
        if len(nav_df) > 0:
            print(f"\n净值: {nav_df['nav'].iloc[0]:.2f} → {nav_df['nav'].iloc[-1]:.2f}")
