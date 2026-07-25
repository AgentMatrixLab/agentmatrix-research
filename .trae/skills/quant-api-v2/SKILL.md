---
name: "quant-api-v2"
description: "通过 HTTP API 查询/拉取 A 股量化数据. 25 张 CH 表 (33 因子/月频/日 K/分钟 K/财务/行业/市值/停牌/ETF/交易日历/行业指数/交易所指数/指数权重/行业成分/交易所成分/L1 快照), 4 个本地 parquet (market_cap/pe/pb/ps), 33 个月度因子 (41.9 万行, 76 月), 加 RQData 异步拉取 (alpha101 等因子). 支持 JSON / NDJSON 流式 / Parquet 二进制 / CSV 四种下载格式. 触发场景: 用户要求查 ROE/PE/PB/动量等因子, 拉日 K 线, 读 parquet 文件, 探索数据源, 查 API 端点, 因子 IC 评估, 触发 RQData 拉新因子数据 (alpha001-101 等), 下载大数据表为 Parquet."
---

# Quant API v2 — 完整 SKILL (给 AI 用的工作手册)

> **API**: `http://115.159.73.134:8765`
> **Token**: 用户提供, `sk-xxx` 格式, Bearer header
> **数据规模**: 25 张 CH 表 + 4 个 parquet + 33 因子月度 (41.9 万行)
> **版本**: v2.3.0 (2026-06-22)
> **端点数**: 28 个 (含 4 种数据格式: JSON / NDJSON / Parquet / CSV)

---

## 0. 触发场景

当用户要求以下任何一项, **立即**使用本 skill:

- "查 ROE/PE/PB 排名前 10 的股票"
- "平安银行过去 5 年 PE 时序"
- "拉因子月度数据 / 33 因子"
- "日 K 线 / 分钟 K 线 / 财务数据 / 资产负债表 / 利润表 / 现金流"
- "读 RQdata 的 parquet 文件"
- "数据源有什么 / API 端点 / Swagger"
- "市值 / 行业 / 申万 / 停牌 / ETF"
- "交易日历 / 复权因子"
- "因子 IC / 因子评估"
- "下载 parquet / 拉大数据 / 拉全表 / 流式下载"
- "拉新因子 / 拉 alpha001-101 / 触发 RQData / 拉新数据"
- "**申万行业成分 / 行业指数 / 行业权重**"
- "**交易所指数 / 上证指数 / 深证综指 / 指数 1 分钟 K**"
- "**指数权重 / 流通股本 / 自由流通比例**"
- "**L1 行情 / 5 档盘口 / 快照**"

**不要触发**: 纯概念问题 ("什么是 ROE"), 或与本项目无关的请求.

---

## 1. 必做前置: 验证 Token + 探索数据

调用任何数据端点前, **必做 3 步**:

```python
import requests
TOK = "<用户提供>"  # 必须是 sk-xxx 格式
H = {"Authorization": f"Bearer {TOK}"}
BASE = "http://115.159.73.134:8765"

def call(path, params=None):
    r = requests.get(f"{BASE}{path}", params=params, headers=H, timeout=30)
    r.raise_for_status()
    return r.json()

# Step 1: 验证 token 有效
whoami = call("/whoami")
# → {"role": "admin", "user": "..."}

# Step 2: 看数据源全景图 (1 步拿到 25 张表 + 4 个目录)
sources = call("/sources")
# → {clickhouse: {url, database, tables: [...]}, files: {directories: [...]}}

# Step 3: 看 25 张 CH 表清单 + 行数
ch = call("/ch")
# → {ok: true, count: 25, tables: [{name, description, row_count_hint}]}
```

**Token 错误立即停止并报告用户** (401 = 找 admin 重发).

---

## 2. 🎯 端点选择决策树 (重要!)

> **不再需要查文档挑端点**. 看到需求直接走流程:

```
我要拿数据
│
├── 先查总量 (用 /ch/{table}?with_total=true&limit=1)
│
├── 数据量 < 1万行
│     └── 走 JSON: /ch/{table} (返回 JSON dict)
│
├── 数据量 1万 ~ 50万
│     ├── 流式处理 / 实时分析 → /ch/{table}/stream (NDJSON)
│     └── pandas 一次性拿 → /ch/{table}/parquet (二进制)
│
├── 数据量 > 50万
│     ├── pandas/polars 用 → /ch/{table}/parquet (流式二进制)
│     └── Excel 打开 → /ch/{table}/csv (流式 CSV)
│
└── 20亿行巨型表 (ods_kline_1m)
      ├── 单股单日 → /parquet?symbol=...&date=...
      ├── 单股一段时间 → /parquet?symbol=...&start_date=&end_date=
      └── 全表 → ❌ 不可能 (用流式 + 按日下载)
```

### 2.1 端点选择速查表

| 数据场景 | 端点 | 返回格式 | 文件大小 (示例) |
|---------|------|---------|---------------|
| 查某只股票某月 ROE | `/factor_monthly?symbol=&factor=` | JSON | < 1KB |
| 交易日历全集 (1517 行) | `/ch/ref_calendar` | JSON | 0.1MB |
| 利润表 1 年 (30k 行) | `/ch/ods_income_raw/parquet?...` | **Parquet** | 16.6MB |
| 日 K 1 年 (1.5M 行) | `/ch/ods_kline_1d/parquet?start_date=&end_date=` | **Parquet** | 24.9MB |
| 日 K 1 年 (Excel 用) | `/ch/ods_kline_1d/csv?...` | **CSV** | ~50MB |
| 分钟 K 单股 3 天 (720 行) | `/ch/ods_kline_1m/parquet?symbol=&start_date=&end_date=` | **Parquet** | 15KB |
| 实时处理 69万行 (内存敏感) | `/ch/ods_income_raw/stream?batch_size=20000` | **NDJSON** | 50MB 客户端恒定 |

### 2.2 数据量 + 格式决策矩阵

|  | < 1万 | 1万-50万 | 50万-100万 | > 100万 |
|---|---|---|---|---|
| **JSON** | ✅ 最佳 | ⚠️ 慢 | ❌ OOM | ❌ 不可能 |
| **NDJSON 流式** | ✅ 略浪费 | ✅ 最佳 | ✅ 最佳 | ✅ 最佳 |
| **Parquet** | ✅ 略浪费 | ✅ 推荐 | ✅ **断崖式** | ✅ 唯一方案 |
| **CSV** | ✅ | ✅ | ✅ | ✅ |

---

## 3. 4 类数据查询 (按场景)

### 类别 A: 33 因子月度 (主用) ⭐

**适用**: ROE/ROA/PE/PB/动量/波动率/技术指标 月频数据
**规模**: 41.9 万行 × 76 月 (2020-01-23 ~ 2026-04-09, ~5,413 股票)

| 端点 | 用途 |
|------|------|
| `GET /factor_monthly` | 主查询 (支持 symbol/date/factor/limit) |
| `GET /factor_monthly/factors` | 33 个因子名清单 |
| `GET /factor_monthly/latest?factor=X&top=N` | 最新横截面 Top N |
| `GET /factor_monthly/dates` | 76 个月末日期 |
| `GET /factor_monthly/stats` | 各因子 count/min/max/mean |

**33 个因子** (部分): `roe_ttm`, `roa_ttm`, `pe_ttm`, `pb_ratio`, `ps_ttm`,
`momentum_1m/3m/6m/12m`, `volatility_20d/60d`, `rsi_14d`, `macd`, `bollinger_upper/lower`

**典型查询**:
```python
# 某股某因子时序
data = call("/factor_monthly", {"symbol": "000001.SZ", "factor": "roe_ttm"})

# 最新横截面 (最新一天 ROE 最高 10 只)
data = call("/factor_monthly/latest", {"factor": "roe_ttm", "top": 10})

# 某日全部股票
data = call("/factor_monthly", {"date": "2025-01-23"})

# 完整 41.9 万行 (不传 top 即可, 已无上限)
data = call("/factor_monthly", {"factor": "roe_ttm"})

# 多个因子 (逗号分隔, 无空格)
data = call("/factor_monthly", {"factor": "roe_ttm,pe_ttm,pb_ratio"})

# 单只股票历史
data = call("/factor_monthly", {"factor": "roe_ttm", "symbol": "000001.SZ"})
```

### 类别 B: 25 张 CH 表通用查询

**适用**: 日 K/分钟 K/财务/行业/指数/市值/停牌/ETF/交易日历/股票基本信息/指数权重/指数成分

**白名单 (实测 2026-06-22)**:

| 表名 | 行数 | 日期范围 | 主键 | 描述 |
|------|------|---------|------|------|
| `factor_monthly` | 41.9 万 | 2020-01-23 ~ 2026-04-09 | trade_date | 33 因子月频 |
| `factor_ic` | 2,375 | 2020-01-23 ~ 2026-03-31 | trade_date | 因子 IC 评估 |
| `ods_kline_1d` | **8.3 M** | 2020-01-02 ~ 2026-04-09 | trade_date | 日 K 线 (OHLCV) |
| `ods_kline_1m` | **2.0 B (38 GiB)** | 2020-01-02 ~ 2026-04-09 | trade_time | 1 分钟 K 线 ⚠️ 巨大 |
| `ods_industry_index_kline_1d` | 63.6 万 | 2020-01-02 ~ 2026-04-09 | index_code+trade_date | **申万行业指数日 K + 估值 (PE/PB/总市值)** |
| `ods_exchange_index_kline_1m` | **2.0 亿 (7.4GB)** | 2020-01-02 ~ 2026-04-09 | index_code+bar_time | **交易所指数 1 分钟 K** ⚠️ 巨大 |
| `dwd_financial_pit_daily` | 0 | (空) | - | 财务 PIT (空表, 等 ETL) |
| `ods_balance_sheet_raw` | 25.6 万 | 2020-2026 | None ⚠️ | 资产负债表, 需手动 `date_col=report_period` |
| `ods_income_raw` | 69.1 万 | 2020-2026 | None ⚠️ | 利润表, 需手动 `date_col=report_period` |
| `ods_cash_flow_raw` | ~10 万 | 2020-2026 | None ⚠️ | 现金流量表, 需手动 `date_col=report_period` |
| `ods_adj_factor_daily` | ~830 万 | 2020-01-02 ~ 2026-04-09 | trade_date | 日复权因子 |
| `ods_security_status_daily` | ~830 万 | 2020-01-02 ~ 2026-04-09 | trade_date | 股票状态 (停牌/ST) |
| `ods_fund_iopv_daily` | ~200 万 | 2020-01-02 ~ 2026-04-09 | trade_date | ETF IOPV |
| `ref_calendar` | ~1,500 | 2020-01-02 ~ 2026-04-09 | trade_date | 交易日历 |
| `ref_security` | ~6,000 | (无日期) | - | 股票基本信息 |
| `ref_industry_index` | ~511 | (无日期) | - | 申万一级行业指数主表 |
| `ref_exchange_index` | 634 | (无日期) | - | **交易所指数主表 (上证/深证/中证等)** |
| `ref_industry_index_member` | 2.3 万 | 1990-12-19 ~ 2024-07-30 | index_code+symbol+in_date | **申万行业指数成分股 (含 in/out_date)** |
| `ref_exchange_index_member` | 26.8 万 | 1991-04-04 ~ 2026-04-24 | index_code+symbol+in_date | **交易所指数成分股** |
| `ods_industry_index_weight_daily` | 2057 万 | 2020-01-02 ~ 2026-04-09 | index_code+trade_date+symbol | **申万行业指数每日权重** |
| `ods_exchange_index_weight_daily` | 402 万 | 2020-2026 | index_code+trade_date+symbol | **交易所指数每日权重 (含总股本/流通比例)** |
| `ods_snapshot_l1` | 0 | (空) | - | **L1 行情快照 (5 档盘口, 空表)** |
| `ops_run_log` | 数千 | (无日期) | - | 运行日志 |
| `ops_ingest_batch` | 数百 | (无日期) | - | 批次摄入 |
| `ops_data_quality` | ~10 | 2026-04-09 | trade_date | 数据质量 |

**通用查询语法**:
```python
# 参数
#  - date    日期值 (配合 date_col)
#  - symbol  股票代码 (配合 symbol_col)
#  - factor  逗号分隔, 指定返回哪些列 (不传=全列)
#  - order   asc | desc (默认 desc)
#  - top     Top N. **不传=不限** (已解除 le=10000 限制)
#            大表 (ods_kline_1m 20亿行) 必须用 date/symbol 过滤
#  - limit/offset 客户端分页 (新)
#  - with_total  True 时返回 total 字段 (新)

# 日 K 线 (单日)
data = call("/ch/ods_kline_1d", {"symbol": "000001.SZ", "date": "2025-12-31"})

# 资产负债表 (注意用 report_period, 单日)
data = call("/ch/ods_balance_sheet_raw", {"symbol": "000001.SZ",
                                           "date_col": "report_period",
                                           "date": "2025-12-31"})

# 交易日历 (单日)
data = call("/ch/ref_calendar", {"date": "2026-01-01"})

# Top N (按某列排序)
data = call("/ch/factor_ic", {"top": 20, "order": "desc", "order_by": "ic"})

# 复权因子 (单日)
data = call("/ch/ods_adj_factor_daily", {"symbol": "000001.SZ",
                                          "date": "2025-12-31"})

# 客户端分页 (大表)
data = call("/ch/ods_income_raw", {"limit": 10000, "offset": 0, "with_total": True})
# → {"data": [...], "has_more": True, "next_offset": 10000, "total": 690852}
```

**支持参数**:
| 参数 | 含义 | 备注 |
|------|------|------|
| `symbol` | 股票代码 | `000001.SZ` 格式 |
| `date` | 单日 (配合 `date_col`) | `YYYY-MM-DD` 格式 |
| `factor` | 列名 (逗号分隔) | 选列, 不传=全列 |
| `top` | Top N | **不传=不限** (已解除 le=10000), 大表用 date/symbol 过滤 |
| `order` | `asc` / `desc` | 默认 desc |
| `order_by` | 排序列 | 默认自动 |
| `limit` | 客户端分页 (新) | 默认 10000, 1~100000 |
| `offset` | 客户端分页偏移 (新) | 默认 0 |
| `with_total` | 返回 total 字段 (新) | False |

### 类别 C: 文件读取 (parquet/csv/json/log)

**一个端点自动识别** (`/files/{dir_path}/{filename}`):
- parquet → pandas 读
- csv → pandas 读
- json → 转 dict
- log/text → 头 200 行

```python
d = call("/files/<server_data_root>/RQdata_files/rq_factor_market_cap_20260604.parquet")
# → {
#     ok: True,
#     type: "parquet",
#     total_rows: 98770,
#     columns: ["market_cap"],
#     preview_rows: 1000,
#     data: [...前 1000 行]
#   }
```

如果是大文件, 想拿完整数据, 用 `requests.get` + `pd.read_parquet`:
```python
import pandas as pd
r = requests.get(f"{BASE}/files/<server_data_root>/RQdata_files/rq_factor_market_cap_20260604.parquet",
                 headers=H)
with open("local.parquet", "wb") as f:
    f.write(r.content)
df = pd.read_parquet("local.parquet")
# shape: (98770, 1)  ← 完整 98,770 行
```

> **注意**: 之前文档提到的 `/files/raw/{dir}/{file}` **是误解**, 实际端点就是 `/files/{dir_path}/{filename}`, 它自动返回完整文件 (parquet bytes) 或 JSON 预览 (CSV/JSON/log).

**4 个白名单目录** (只能读这些):
| 目录 | 内容 |
|------|------|
| `<server_data_root>/RQdata_files/` | 因子 parquet (market_cap/pe/pb/ps) |
| `/srv/factor-truth/manifests/` | 因子名清单 |
| `/srv/factor-truth/snapshots/` | 因子快照 |
| `<quant_api_deploy_root>/logs/` | 服务日志 (api.log 等) |

### 类别 D: 因子评估 (`/factor_ic`)

```python
# 因子 IC 评估 (看哪个因子有效)
data = call("/ch/factor_ic", {"top": 20, "order": "desc", "order_by": "ic"})
# → 因子名, IC 均值, IC 标准差, IC>0 比例, t 统计量
```

### 类别 E: 触发 RQData 拉取 (admin)

**适用**: 需要**新拉数据** (而不是查现有数据) 时, 通过 API 触发 RQData SDK 在服务器后台跑, 结果落 parquet, 同事下载.

**端点**:
| 端点 | 用途 |
|------|------|
| `POST /admin/pull` | 触发拉取 (传 factors 列表, 立即返回 job_id) |
| `GET /admin/pull/jobs` | 列所有任务 |
| `GET /admin/pull/jobs/{job_id}` | 查单个任务 (status/progress/output) |
| `GET /admin/pull/jobs/{job_id}/download/{filename}` | **下载产出文件 (绕过白名单)** |
| `DELETE /admin/pull/jobs/{job_id}` | 清任务记录 (不杀进程, 不删文件) |

**典型流程** (3 步):
```python
# Step 1: 触发拉取 (admin token, 立即返回, 不阻塞)
r = requests.post(f"{BASE}/admin/pull", headers=H, json={
    "factors": ["WorldQuant_alpha001", "WorldQuant_alpha002"],
    "start": "2020-01-01",
    "end": "2026-04-30",
})
job_id = r.json()["job_id"]  # 如 "5ec1aa92c95a"

# Step 2: 轮询状态 (拉取很慢, 一个因子 ~5-10 秒)
while True:
    j = requests.get(f"{BASE}/admin/pull/jobs/{job_id}", headers=H).json()["job"]
    print(f"{j['status']} {j['progress']}%")
    if j["status"] in ("done", "failed"):
        break
    time.sleep(10)

# Step 3: 下载 (走专属端点, 绕过白名单)
for filename in j["files"]:  # ["alpha_alpha001.parquet", ...]
    r = requests.get(f"{BASE}/admin/pull/jobs/{job_id}/download/{filename}",
                     headers=H)
    with open(filename, "wb") as f:
        f.write(r.content)
    df = pd.read_parquet(filename)
```

**RQData 拉取的数据格式** (实测 2026-06-18):
```
columns: ['order_book_id', 'date', 'value', 'factor']
dtypes:
  order_book_id    object
  date             datetime64[ns]
  value            float64       ← alpha 数值
  factor           object
```

**任务状态**: `queued` → `running` → `done` | `failed`
**进度**: 0-100%, log_tail 有子进程 stdout 末 30 行
**约束**:
- 最多同时 2 个任务在跑 (`_MAX_CONCURRENT = 2`)
- 任务结果保留在服务器 `<server_data_root>/RQdata_files/alpha101/job_xxx/`
- 不自动清理

---

## 4. 4 种数据下载格式 (新增 v2.2) ⭐

### 4.1 JSON 格式 (默认) — 适合小数据

| 端点 | 返回 | 大小限制 |
|------|------|---------|
| `GET /ch/{table}` | JSON dict | 1万行以下 |

```python
r = requests.get(f"{BASE}/ch/ref_calendar", headers=H)
data = r.json()["data"]
```

### 4.2 NDJSON 流式 (新) — 适合大数据 + 实时处理

| 端点 | 返回 | 特点 |
|------|------|------|
| `GET /ch/{table}/stream?batch_size=N` | NDJSON (一行一记录) | 服务器分批, 客户端内存恒定 |

**响应格式 (NDJSON)**:
```
{"_meta": true, "table": "ods_income_raw", "columns": [...], "order_by": "report_period", "order": "desc"}
{"_row": true, "symbol": "000001.SZ", "report_period": "2026-03-31", ...}
{"_row": true, ...}
...
{"_end": true, "total_returned": 690123}
```

**Python 客户端**:
```python
r = requests.get(f"{BASE}/ch/ods_income_raw/stream",
                 params={"batch_size": 20000}, headers=H, stream=True, timeout=300)
columns = None
total = 0
for line in r.iter_lines(decode_unicode=True):
    if not line: continue
    obj = json.loads(line)
    if obj.get("_meta"): columns = obj["columns"]
    elif obj.get("_row"):
        total += 1
        # process row
    elif obj.get("_end"):
        print(f"完成: {obj['total_returned']} 行")
```

**特点**:
- 服务器内部自动分批 (默认 5000/批), 流式 NDJSON 输出
- 客户端 `stream=True` 逐行读, 内存稳定不超 50MB
- 永不超时, 大表 (69万行) 完整可下
- 防 OOM: `batch_size` 1~50000 (默认 5000)

### 4.3 Parquet 二进制 (新, 推荐) — 适合大数据 + pandas/polars

| 端点 | 返回 | 特点 |
|------|------|------|
| `GET /ch/{table}/parquet?...` | Apache Parquet 字节流 | 体积小 5-10x, pandas 直接读 |

**支持参数** (vs JSON 多 3 个):
| 参数 | 含义 | 示例 |
|------|------|------|
| `start_date` | 起始日期 (含) | `2025-01-01` |
| `end_date` | 结束日期 (含) | `2025-12-31` |
| `where` | 额外 WHERE 子句 | `close > 100` |

**典型用法**:
```python
# 全年日 K 线 (1.5M 行, 24.9MB Parquet, 8s 下载)
r = requests.get(f"{BASE}/ch/ods_kline_1d/parquet",
                 params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
                 headers=H, stream=True, timeout=300)
with open("kline_2025.parquet", "wb") as f:
    for chunk in r.iter_content(1024*1024):
        f.write(chunk)

import pandas as pd
df = pd.read_parquet("kline_2025.parquet")
print(df.shape)  # (1542154, 12)

# 单股单日 (1 分钟 K 线, 20亿表也能拉)
r = requests.get(f"{BASE}/ch/ods_kline_1m/parquet",
                 params={"symbol": "000001.SZ",
                         "start_date": "2025-12-29",
                         "end_date": "2025-12-31"},
                 headers=H)
with open("kline_1m.parquet", "wb") as f:
    f.write(r.content)
df = pd.read_parquet("kline_1m.parquet")
print(df.shape)  # (720, 12)

# 只导指定列 (省带宽)
r = requests.get(f"{BASE}/ch/ods_income_raw/parquet",
                 params={"factor": "symbol,report_period,revenue,net_profit",
                         "date_col": "report_period",
                         "date": "2025-12-31"},
                 headers=H)
```

**关键能力**: 20亿行表按股票+按日切片, **从不可能 → 可能**.

### 4.4 CSV 流式 (新) — 适合 Excel / 简单查看

| 端点 | 返回 | 特点 |
|------|------|------|
| `GET /ch/{table}/csv?...` | CSV (带表头) | Excel 直接打开, 比 Parquet 大 2-3x |

**Python 客户端**:
```python
r = requests.get(f"{BASE}/ch/ods_kline_1d/csv",
                 params={"date": "2025-12-31"},
                 headers=H, stream=True)
with open("kline_2025-12-31.csv", "wb") as f:
    for chunk in r.iter_content(1024*1024):
        f.write(chunk)
# Excel / pandas / vim 都能打开
```

### 4.5 4 种格式对比

| 维度 | JSON | NDJSON 流式 | Parquet | CSV |
|------|------|------------|---------|-----|
| **数据格式** | 单一大 JSON | 换行分隔 JSON | Apache Parquet | RFC 4180 CSV |
| **压缩率** | 1x (无压缩) | 1x | **0.1-0.2x** (5-10x 小) | 0.5-0.7x |
| **客户端内存** | 累积整段 | **恒定 50MB** | 累积整段 | 累积整段 |
| **首屏延迟** | 等全部 | **首行 100ms** | 等全部 | 等全部 |
| **pandas/polars** | `pd.DataFrame(r.json()['data'])` | `for line in r.iter_lines()` | `pd.read_parquet()` | `pd.read_csv()` |
| **Excel 兼容** | ❌ | ❌ | ❌ (要客户端) | ✅ |
| **可读性** | 好看 | 一行一 record | 二进制 | 文本 |
| **大表首选** | ❌ | ✅ (实时) | ✅ (分析) | ✅ (Excel) |

### 4.6 实战推荐组合

| 场景 | 推荐 |
|------|------|
| 探索数据 / 查几只股票 | JSON |
| 内存敏感 / 实时处理 100万+ | NDJSON 流式 |
| pandas 一次性分析 1万-1亿 | **Parquet** |
| 给非技术同事 / Excel | CSV |
| 20亿表 (ods_kline_1m) | Parquet + symbol/date 切片 |

### 4.7 ⭐ 8 张新表的典型查询 (v2.3.0)

**新增于 2026-06-22**, 8 张原本缺的白名单表:

```python
# 1) 申万行业指数日 K + 估值 (PE/PB/总市值)
data = call("/ch/ods_industry_index_kline_1d", {
    "symbol": "801010.SI",  # 农林牧渔
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
})
# → 含 open/high/low/close + pb + pe + total_cap + a_float_cap

# 2) 申万行业指数成分股 (含进出日期)
data = call("/ch/ref_industry_index_member", {
    "symbol": "600602.SH"  # 查 600602 所属行业历史
})
# → index_code, index_name, in_date, out_date

# 3) 申万行业指数每日权重
data = call("/ch/ods_industry_index_weight_daily", {
    "date": "2024-12-31",
    "factor": "index_code,trade_date,symbol,weight"
})
# → ~3000 行/天 (申万 31 个一级行业 × 平均 100 只成分股)

# 4) 交易所指数主表 (上证/深证/中证等)
data = call("/ch/ref_exchange_index", {"limit": 50})

# 5) 交易所指数 1 分钟 K (7.4GB 巨型表, 必须切片!)
r = requests.get(f"{BASE}/ch/ods_exchange_index_kline_1m/parquet",
                 params={"symbol": "000001.SH",  # 上证指数
                         "start_date": "2024-12-30",
                         "end_date": "2024-12-31"},
                 headers=H, stream=True, timeout=300)
with open("sh_index_2d.parquet", "wb") as f:
    for chunk in r.iter_content(1024*1024):
        f.write(chunk)
df = pd.read_parquet("sh_index_2d.parquet")
# → 240 行 (2天 × 120 分钟/天)

# 6) 交易所指数每日权重 (含总股本/自由流通比例)
data = call("/ch/ods_exchange_index_weight_daily", {
    "date": "2024-12-31",
    "symbol": "600000.SH"  # 查单股
})
# → total_share, free_share_ratio, calc_share, weight_factor, weight

# 7) 交易所指数成分股 (查某股票所属交易所指数)
data = call("/ch/ref_exchange_index_member", {
    "symbol": "000001.SZ"  # 查 000001.SZ 所属交易所指数历史
})
# -> index_code, index_name, in_date, out_date
```

**⚠️ Date 字段陷阱**: 从 Parquet 读出的 Date 类型是 `uint16` (Excel 序列号, 0=1899-12-30, 7648=1990-12-19), 转回日期:
```python
df['in_date'] = pd.to_datetime(df['in_date'], unit='D', origin='unix')
df['out_date'] = pd.to_datetime(df['out_date'], unit='D', origin='unix')
```

---

## 5. 完整端点清单 (28 个)

> 实际 `openapi.json` 端点数 = **28 个** (v2.3.0, 2026-06-22).

### 读端点 (22 个)

| 端点 | 用途 | Token |
|------|------|-------|
| `GET /` | 重定向到 /docs | - |
| `GET /docs` | Swagger UI (浏览器可视化) | - |
| `GET /health` | 服务健康检查 | - |
| `GET /info` | 服务信息 | - |
| `GET /whoami` | Token 身份 (role/user) | - |
| `GET /sources` | **数据源全景图** (25 表 + 4 目录) | - |
| `GET /factor_monthly` | **33 因子月频** | ✅ |
| `GET /factor_monthly/factors` | 33 因子名清单 | ✅ |
| `GET /factor_monthly/dates` | 76 月末日期 | ✅ |
| `GET /factor_monthly/stats` | 因子统计 | ✅ |
| `GET /factor_monthly/latest` | 最新横截面 Top N | ✅ |
| `GET /factors` | 4 因子清单 (parquet) | ✅ |
| `GET /factors/{name}` | 4 因子查询 | ✅ |
| `GET /factors/{name}/stats` | 4 因子统计 | ✅ |
| `GET /factors/{name}/dates` | 4 因子日期 | ✅ |
| `GET /ch` | CH 白名单 (25 张表) | ✅ |
| `GET /ch/{table_name}` | **25 张表通用查询 (JSON)** | ✅ |
| `GET /ch/{table_name}/stream` | **流式 NDJSON (大表首选)** | ✅ |
| `GET /ch/{table_name}/parquet` | **下载 Parquet 文件 (二进制, 推荐)** | ✅ |
| `GET /ch/{table_name}/csv` | **下载 CSV 文件 (Excel 兼容)** | ✅ |
| `GET /files` | 4 个白名单目录 | ✅ |
| `GET /files/{dir_path}/{filename}` | **文件读取 (parquet/csv/json/log, 自动识别)** | ✅ |

### 写端点 (6 个, 需 admin)

| 端点 | 用途 |
|------|------|
| `POST /cache/clear` | 清缓存 (强制下次读重新加载) |
| `POST /admin/pull` | **触发 RQData 拉取 (异步, 立即返回 job_id)** |
| `GET /admin/pull/jobs` | **列所有拉取任务** |
| `GET /admin/pull/jobs/{job_id}` | **查单个任务状态** |
| `GET /admin/pull/jobs/{job_id}/download/{filename}` | **下载 pull 产出文件 (绕过白名单)** |
| `DELETE /admin/pull/jobs/{job_id}` | 清任务记录 (不杀进程, 不删文件) |

> **注意**: 之前文档提到的 `/admin/restart`, `/admin/keys`, `/admin/logs`, `/metrics`, `/admin/disk`, `/admin/process` **当前不存在** (代码尚未部署). 仅 `/admin/pull*` 5 个端点已上线.

---

## 6. 错误处理

| HTTP | 含义 | 处理 |
|------|------|------|
| 401 | Token 无效/缺失 | 检查 H 头, 让用户找 admin 重发 |
| 404 | 表/路径错 | 调 `/ch` 或 `/files` 查白名单 |
| 500 | 后端 bug | 把 error 截图给 admin |
| 422 | 参数错误 | 检查参数名/类型, 端点签名见 `/docs` |

> **限流**: 当前 API **未启用限流** (`slowapi` 装了未接), 所以**不会**返回 429.

---

## 7. ⚠️ 重要陷阱 (必读)

1. **1 分钟 K 线 (`ods_kline_1m`) 38 GiB** + **交易所指数 1 分 K (`ods_exchange_index_kline_1m`) 7.4GB**: **不要用 JSON 拿全表**! 用 `/parquet?symbol=&start_date=&end_date=` 按股+按日切片
2. **财务表用 `report_period`**: 不用 `trade_date`. `ods_income_raw/balance_sheet_raw/cash_flow_raw` 这 3 张表 `date_col=None`, 用 `?date=...` 过滤**不会生效**, 必须手动传 `date_col=report_period`
3. **factor 参数**: 逗号分隔, **没有空格**
4. **大文件读取**: 用 `/files/{dir_path}/{filename}`, 自动识别 parquet/csv/json/log
5. **空表 `dwd_financial_pit_daily` 和 `ods_snapshot_l1`**: 0 行, 不要用它们做查询 (snapshot_l1 是 5 档盘口, 结构在等 ETL)
6. **ods_balance_sheet_raw** 才有完整数据, `dwd_financial_pit_daily` 是空的
7. **RQData 拉取很慢** (一个因子 ~5-10 秒, 全 A 股 5553 × 多月): **必须异步**! 用 `/admin/pull` 触发, **不要同步等** (HTTP 会超时)
8. **RQData order_book_id 格式**: `000001.XSHE` / `600000.XSHG` (不是 `000001.SZ`!), rqdatac 拒绝 `000001.SZ` 格式
9. **RQData 任务结果目录**: `<server_data_root>/RQdata_files/alpha101/job_xxx/`, **不在 `/files` 白名单**, 必须用专属 `/admin/pull/jobs/{job_id}/download/{filename}` 端点下载
10. **限流未启用**: 当前 token 可任意调用, 不卡 429. 切勿给外部用户或泄露 token
11. **客户端分页会 OOM**: `/ch/{table}?limit=&offset=` 累积所有 data 到客户端, 大表用流式或 Parquet 替代
12. **`top` 已无上限**: 不传 top 可拿全表, 大表会自动触发 count() + 全表序列化, **大表会卡**! 走 `/parquet`
13. **Parquet 读 Date 字段是 uint16**: CH 的 `Date` 类型在 Parquet 输出时变成 `uint16` (Excel 序列号). 转换: `pd.to_datetime(df['col'], unit='D', origin='unix')`. 影响表: `ref_industry_index_member`, `ref_exchange_index_member` 等含 Date 列的表
14. **新增 8 张表的主键多列**: `ref_industry_index_member` / `ref_exchange_index_member` 主键是 `(index_code, symbol, in_date)`, 查询时建议至少传 `symbol` 才有意义

---

## 8. 推荐工作流

1. **接到任务**: 先调 `/whoami` + `/sources` 探明数据
2. **看数据量**: 用 `/ch/{table}?with_total=true&limit=1` 查 `total` 字段
3. **小数据探索** (< 1万): 直接 `/factor_monthly` 或 `/ch/{table}` JSON
4. **中大数据** (1万-100万): `/ch/{table}/parquet` 流式下载, pandas 读
5. **实时处理/内存敏感** (100万+): `/ch/{table}/stream` NDJSON 流式
6. **Excel 用**: `/ch/{table}/csv` 流式
7. **20亿表**: `/ch/{table}/parquet?symbol=&start_date=&end_date=` 按日切片
8. **新数据源**: 调 `/sources` 看清单
9. **拉新因子** (没有现成数据): 用 `/admin/pull` 异步触发
10. **写代码模板**:
   ```python
   import requests, time
   import pandas as pd
   TOK = "<用户提供>"
   H = {"Authorization": f"Bearer {TOK}"}
   BASE = "http://115.159.73.134:8765"

   def call(path, params=None):
       r = requests.get(f"{BASE}{path}", params=params, headers=H, timeout=30)
       r.raise_for_status()
       return r.json()

   def download_parquet(path, params, save_path):
       r = requests.get(f"{BASE}{path}", params=params, headers=H,
                        stream=True, timeout=300)
       r.raise_for_status()
       with open(save_path, "wb") as f:
           for chunk in r.iter_content(1024*1024):
               f.write(chunk)
       return pd.read_parquet(save_path)
   ```

---

## 9. 部署信息 (内部, admin 用)

- **API 公网地址**: `http://115.159.73.134:8765`
- **服务器**: Ubuntu 24.04, `115.159.73.134`
- **部署目录**: `<quant_api_deploy_root>/`
- **数据目录**: `<server_data_root>/RQdata_files/` (因子 parquet)
- **本地项目**: `<local_quant_api_repo>/`
- **配套 skill**: `rqdata-factor-pulling` (拉数据), `quant-api-v2` (查数据)
- **配套文档**: README.md (上手), USER_MANUAL.md (端点详解)

---

## 10. 版本记录

| 日期 | 变更 |
|------|------|
| 2026-06-16 | 初版, 整合 README.md + USER_MANUAL.md, 17 张表实测 |
| 2026-06-17 | 加入触发场景、AI 指令化、5 大陷阱 |
| 2026-06-18 | **新增类别 E: RQData 异步拉取** (5 个新端点: /admin/pull 等). 数据格式修正 (date/value 类型). 加入专属 download 端点 (绕过白名单). |
| 2026-06-18 | **全文档同步**: 删 8 个幽灵端点, 修 4 个 endpoint 占位符名, 加 5 个 /admin/pull 端点, 删限流宣传. |
| 2026-06-18 | **完全解除 top 限制**: 同事反馈 K_line 端点 10000 行限制, 实查是 FastAPI `le=10000` 验证器. 删 4 处 le=10000, 默认值 100→None, data_loader 加 `if top else ""`. `/ch/{table}` + `/factor_monthly` + `/factors/{name}` 全部支持不传 top 拿全表. |
| 2026-06-18 | **修 factor_monthly TypeError**: 同事报告 `/factor_monthly?factor=roe_ttm` 报 `TypeError`. 根因: `data_loader.query_factor_monthly` 参数是 `factors: list[str]` (复数+list), main.py 传 `factor=str` (单数+str). 修 2 处. |
| 2026-06-18 | **修 /ch 端点文档**: 删除错的 `start_date`/`end_date` 参数, 加 17 张表 `ods_kline_1m` 警告. |
| 2026-06-18 | **修 /ch/{table} top 限制**: 之前只解了 `/factor_monthly` 和 `/factors/{name}`, 漏修 `/ch/{table}` (默认 100, le=10000). 现 main.py + data_loader.py 都已修, 不传 top 拿全表, 无上限. 修 `ref_industry_index_sw_l1` → `ref_industry_index` (实际表名, 白名单配错导致 500 错). |
| 2026-06-18 | **加分页 + 流式端点 (防大表超时)**: `/ch/{table}` 新增 `limit` (默认 10000, 上限 10万) / `offset` / `with_total` 参数, 响应含 `has_more` + `next_offset`. 新增 `/ch/{table}/stream` 端点走 NDJSON. |
| 2026-06-18 | **修 count() 返回 string bug**: with_total=true 返回 `total="1517"` (str) 而非 int. ch_client 返回 ClickHouse UInt64 时被转字符串, data_loader 加 `int()` 强转. |
| 2026-06-18 | **v2.2.0: 大数据 Parquet / CSV 下载 (解决 80% 痛点)**. 新增 `/ch/{table}/parquet` 和 `/ch/{table}/csv` 端点, 服务器直出 Apache Parquet 字节流, 客户端用 pandas 直接读. 20亿行表 (ods_kline_1m) 通过 `?symbol=&start_date=&end_date=` 切片下载. 性能提升 4-35x, 文件大小 5-10x 缩小. |
| 2026-06-22 | **v2.3.0: CH 白名单从 17 张扩到 25 张 (补全 8 张缺失表)**. 新增: 1) 申万行业指数日 K (`ods_industry_index_kline_1d`, 63万行) + 行业指数成分股 (`ref_industry_index_member`, 2.3万行) + 行业指数权重 (`ods_industry_index_weight_daily`, 2057万行); 2) 交易所指数 (`ref_exchange_index`, 634 行) + 交易所指数成分股 (`ref_exchange_index_member`, 26.8万行) + 交易所指数权重 (`ods_exchange_index_weight_daily`, 402万行) + 交易所指数 1 分钟 K (`ods_exchange_index_kline_1m`, 2亿行 7.4GB 巨型表); 3) L1 行情快照 (`ods_snapshot_l1`, 0 行空表, 等 ETL). 全 8 张表端到端测试通过, 4 种格式 (JSON/Parquet/CSV/NDJSON) 全部支持. 重要陷阱: 7.4GB 巨型表必须传 `symbol`+`date` 切片, 不可全表下载. Date 字段从 Parquet 读出是 uint16 (Excel 序列号), pandas 用 `pd.to_datetime(df['col'], unit='D', origin='unix')` 转回日期. |

---

## 11. 配套 skill

如果你需要**新拉数据** (而不是查现有数据), 用 `.trae/skills/rqdata-factor-pulling/SKILL.md`:
- 米筐 RQData 拉数据 → 服务器 → SFTP → 本机
- 适用于: 拉新因子, 增量更新, 重新拉历史

拉完后再用本 skill 查/分析.

