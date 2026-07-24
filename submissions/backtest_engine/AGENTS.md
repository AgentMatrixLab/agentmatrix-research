# Custom Engine — A股量化回测系统

## 项目概述

本地 A 股多因子回测平台。自建引擎 + Qlib 双引擎支持，数据来自雷菱 API，15+ 个策略，全 Parquet 存储。

## 架构

```
雷菱 API (115.159.73.134:8765)
    │
    ▼
engine/data_manager.py          ← 数据管道：API → Parquet
    │
    ▼
data/*.parquet                  ← 数据中心（K线/财务/市值/股息率）
    │
    ├─→ engine/backtest.py      ← 自定义回测引擎（原版，一直正常使用）
    │       ├─ 日频遍历 + 调仓日信号
    │       ├─ 交易模拟（手续费/印花税/滑点/科创板200股/北交所）
    │       └─ 净值计算 + 绩效指标
    │
    └─→ engine/qlib_bridge.py   ← Qlib 桥接层（新增）
            ├─ ParquetToQlibConverter：Parquet → Qlib bin
            └─ QlibBacktestRunner：策略适配 → Qlib backtest()
    │
    ▼
results/                        ← 自动输出：净值 CSV + 调仓 CSV
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `config.py` | 全局配置（API、费率、路径自动检测） |
| `run_all.py` | 主入口，`--engine custom|qlib|both`，`--strategy xxx`，`--freq N` |
| `update_data.py` | 数据更新入口 |
| `engine/backtest.py` | 自定义回测引擎（`BacktestEngine`） |
| `engine/qlib_bridge.py` | Qlib 桥接（`ParquetToQlibConverter` + `QlibBacktestRunner`） |
| `engine/data_manager.py` | 数据下载管理 |
| `engine/metrics.py` | 绩效指标计算 |
| `qlib_backtest.py` | Qlib CLI（convert/check/list/run） |
| `compare_engines.py` | 双引擎一致性验证 |
| `generate_report.py` | HTML 报告生成 |
| `server.py` | 本地报告服务器（:8080） |
| `strategies/` | 策略库，自动发现 |

## 策略接口

每个策略只需实现一个函数：

```python
def get_signals(data: pd.DataFrame) -> pd.DataFrame:
    # data: 当天可交易股票的横截面数据
    # 返回: DataFrame with columns ['symbol', 'weight']
```

引擎自动处理调仓、费用、净值计算。策略可自行加载额外数据（市值、财务、股息率等）通过模块级缓存。

## 回测自动输出

每次跑回测，`results/` 下自动生成：

| 文件 | 内容 |
|------|------|
| `{策略}_nav.csv` | 每日净值 |
| `{策略}_rebalance.csv` | 调仓明细：`date, symbol, shares, weight, price, value` |

## 常用命令

```bash
python run_all.py                              # 全量回测（自定义引擎）
python run_all.py --engine qlib                # Qlib 引擎
python run_all.py --engine both --strategy xxx  # 双引擎对比
python qlib_backtest.py list                   # 列出策略
python qlib_backtest.py run --strategy xxx     # Qlib 单策略
python qlib_backtest.py convert                # 重建 Qlib bin 数据
python compare_engines.py                      # 双引擎验证
python update_data.py                          # 更新数据
python generate_report.py                      # 生成 HTML 报告
```

## 策略列表

- **小市值(月)**：市值 < 100 亿，等权月频
- **Barra四因子**：BP + EY + Lev + NLS，日频 Top 20%
- **红利策略 v1~v6**：股息率选股，逐步对齐聚宽口径
- **微盘股**：市值最小 400 只
- 更多在 `strategies/` 下

## Qlib 对齐（新增功能）

### 目的
让同一策略既能用自定义引擎跑，也能用 Qlib 引擎跑，不改策略代码。

### 数据转换
`ParquetToQlibConverter` 把 Parquet 转成 Qlib 标准 bin 格式。注意：
- 文件名：`{field}.day.bin`，不是 `.day`
- 格式：`float32` + 4 字节 start_index header
- 必须生成 `factor.day.bin`（全 1.0），否则 Qlib 无法处理 A 股百股交易
- 必须合成 `SH000300` 基准，否则 Qlib backtest 报错

### Qlib 版本
本地安装的是 `pyqlib 0.1.dev1`（从 `E:\qlib_repo` 可编辑安装）。API 与文档有差异：
- `NestedExecutor` 需要 `inner_executor` + `inner_strategy` 参数
- 用 `SimulatorExecutor` 替代，API 更简单
- `backtest()` 输出是 `{'1day': (DataFrame, indicator_dict)}`

### 费用对齐
`exchange_kwargs` 配置：
- `open_cost=0.0003`（万3 买入）
- `close_cost=0.0013`（万3 + 千1 印花税）
- `min_cost=5.0`
- `impact_cost=0.001`（滑点 0.1%）
- 科创板 200 股 / 北交所 1 股递增：**Qlib 不支持**，对红利策略影响可忽略

### 已知限制
- Qlib 回测有日历边界 off-by-one bug → `_safe_end_time()` 规避
- Qlib `D.features()` 对自定义 bin 数据可能返回空，但 `backtest()` 本身可以正常读取
- 信号 datetime 层级必须是 `pd.Timestamp`，不能是 `str`

## 数据格式备忘

### Parquet 数据（`data/`）
| 文件 | 大小 | 内容 |
|------|------|------|
| `kline_adj.parquet` | 8.3M 行 | 后复权日K线（close_adj 等） |
| `kline_1d.parquet` | 8.4M 行 | 原始日K线 |
| `calendar.parquet` | 1517 天 | 交易日历 2020-01-02 → 2026-04-09 |
| `market_cap_full.parquet` | 9.4M 行 | 市值数据 |
| `balance_sheet.parquet` | - | 资产负债表 |
| `income_stmt.parquet` | - | 利润表 |
| `dividend_yield_v2.parquet` | 110K 行 | 股息率数据 |
| `stock_info.parquet` | 7962 只 | 股票基本信息 |

### Qlib bin 数据（`data/qlib_bin/`）
由 `qlib_backtest.py convert` 生成，6981 只股票 × 7 字段（close/open/high/low/volume/amount/factor）。
