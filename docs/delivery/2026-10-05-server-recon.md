# 115 服务器数据盘点（2026-10-05 实测）

> 全部结论来自**只读**探测。未做任何写入、未下载任何数据、未修改任何配置。

## 1. 机器

| 项 | 实测 |
|---|---|
| 主机 | `VM-4-9-ubuntu`，Linux 6.8.0-51 |
| CPU | **16 核**（比我之前假设的 8 核好一倍） |
| 内存 | 62 GB（在用 4 GB，可用 57 GB） |
| 负载 | 0.29 / 0.21 / 0.19 —— **空闲** |
| 磁盘 | `/` 443G，**已用 286G，可用 140G（68%）** |
| 已运行 | 171 天 |

> 16 核意味着全量验证时间从我原先估的 2–5 小时可以压到 **1–2.5 小时**。

## 2. ClickHouse（24.8.14，非 systemd 启动，已跑 24884 分钟 CPU）

| 库 | 大小 | 行数 | 说明 |
|---|---:|---:|---|
| `amazingdata` | 46.83 GiB | 2,262,642,592 | 另一个实习生建，RQData + 其他数据源混合 |
| **`rqdata`** | **28.49 GiB** | **3,246,865,026** | **Hermes 建，最新最全，53 张表，结构专业** |
| `rqdata_server_validation` | 488 KiB | 15,650 | |

**`rqdata` 是主库**，表命名规范（`stock_*` / `index_*` / `etf_*` / `ref_*` / `ops_*`），带 `source`/`run_id`/`loaded_at` 审计列。

### 关键表

| 表 | 行数 | 日期范围 | 备注 |
|---|---:|---|---|
| `stock_price_1d_raw` | 11,035,817 | 2016-01-04 ~ 2026-09-30 | **只有 `adjust_type='none'`**，5,473 只 |
| `stock_adjust_factor` | 26,286 | — | 除权除息因子（可用于自行复权） |
| `stock_factor_daily_long` | **2,341,730,100** | 2020-01-02 ~ 2026-09-30 | **RQData 自带因子值 300 个**，5,449 只 |
| `stock_factor_catalog` | **10,443** | — | 因子目录（**无公式**，见下） |
| `stock_industry_snapshot` | 83,398 | 2020-06-30 ~ 2026-09-29 | 中信 `citics_2019`，**仅 13 个半年快照** + 4 个近期日快照 |
| `index_weight_daily` | 11,640,449 | 2020-01-02 ~ 2026-09-30 | 000300 / 000905 / 000852 / 000906 齐全 |
| `stock_financial_pit_long` | 32,905,890 | — | 财务 PIT |
| `stock_security_state_daily` | 7,805,767 | — | 停牌/ST 状态 |
| `stock_turnover_rate` | 7,805,095 | — | 换手率 |
| `ref_calendar_cn` | 8,736 | — | 交易日历 |

## 3. 已存在的导出（`/home/data/delivery_export/`，10/3）

| 文件 | 大小 | 内容 |
|---|---:|---|
| `rqdata_panel.parquet` | 270 MB | **11,059,219 行**，2016-01-04~2026-09-30 |
| `benchmark_000985.parquet` | 49 KB | 000985 全 A 收益，2,610 行 |
| `factor_values_long_2020_2026.parquet` | **5.4 GB** | **91 个因子的值，7.1 亿行** |
| `reversal_1m_2020_2026.parquet` | 71 MB | reversal_1m（自算，7.69M 行） |

### 面板列（`rqdata_panel.parquet`）

```
date, code, open, high, low, close, volume, amount, adjustment_factor,
is_suspended, is_st, listing_date, delisting_date, limit_up, limit_down
```

**这几乎正好是我引擎需要的列。** 缺的可派生：`pre_close`(shift)、`vwap`(amount/volume)、
`total_turnover`(改名 amount)、`industry`(从中信快照取)。

→ **结论：不需要动 5GB/天的下载配额，也不需要重新下载任何数据。**

### ⚠️ 但 91 因子的值是 RQData 的，不是我们引擎算的

侧车原文：
> `"formula": "RQData stock_factor_daily_long 预计算值 (toFloat64)"`
> `"content": "91 候选因子值长表"`

即：**这 91 个因子的值直接从 RQData 的预计算因子表取用**，而非我们的表达式引擎从面板计算。
`reversal_1m` 被单独列出并注明 `-(close_t/close_{t-22}-1)`，说明它是唯一一个自己算的。

**这是一个必须先澄清的口径问题**（见「待定事项 1」）。

## 4. 回答用户提出的几个问题

### Q：RQData 的一万多个因子提供计算公式吗？

**不提供。** `stock_factor_catalog` 有 `calculation_logic` 列，但
**10,443 条全部为空**（`sum(calculation_logic != '')` = 0）。只有因子名 + 类型。

构成：

| 类型 | 条数 |
|---|---:|
| balance_sheet | 4,836 |
| income_statement | 2,821 |
| cash_flow_statement | 2,201 |
| financial_indicator | 127 |
| **alpha101** | **101** |
| operational_indicator | 96 |
| moving_average_indicator | 82 |
| obos_indicator | 43 |
| 其他 | ~136 |

**绝大多数是财报科目名，不是"因子"。** 真正可用的（有值的）只有 300 个。

### Q：那 300 个是什么？

**通达信风格技术指标 + 少量财务指标 + 20 个 alpha101**：

| 类型 | 有值个数 |
|---|---:|
| operational_indicator | 47 |
| financial_indicator | 46 |
| obos_indicator | 42 |
| moving_average_indicator | 40 |
| energy_indicator | 32 |
| **alpha101** | **20** |
| eod_indicator | 20 |
| 其他 | ~53 |

因子名样例：`ACCER, ADTM, ADX, ADXR, AMP1/3/5/10/20/60, AMV5/20/60, AR, AROON_UP/DOWN, ASI, ASIT, ATR, BBI, ...`

→ 与我们目录的 **TDXGS 族**高度重合。**可以用它们做交叉对照**，验证我们引擎算得对不对。

### Q：下载配额限制？

**未实测**（实测会消耗配额）。已知线索：`daily_etl.py` 是每日增量脚本；
RQData 官方文档口径通常按**日下载量**限制。**需要单独确认**，我倾向先不动配额。

## 5. 🔴 发现的安全问题

| 问题 | 位置 |
|---|---|
| **rqdatac 账号密码明文硬编码** | `/home/data/daily_etl.py:33`（一长串 token） |
| **ClickHouse 密码明文硬编码** | `/home/data/quant_api_v2/ch_client.py:19` → `smartdata_ro` |
| ClickHouse 以 root 手动启动、无 systemd 单元 | 重启后不会自动恢复 |
| SSH root 密码认证（你给我的那个） | 建议改用密钥 |

**建议**：这批凭据轮换一次，并改成环境变量/密钥文件。我可以出一份整改清单。

## 6. 待你确认的事项

1. **🔴 交付的因子是我们的，还是 RQData 的？**
   - 现有导出 = RQData 的 91 个因子值
   - 你授权的 849 条 = **我们自己目录的因子**，需要我们的引擎从面板计算
   - 两者是**不同的集合**，交付物完全不同
2. **行业中性化怎么办？** 中信快照只有半年频、2020-06-30 起 → 2020 上半年无行业数据
3. **磁盘**：现有 140G 可用。全量备份 RQData 需要多少空间要先估算
