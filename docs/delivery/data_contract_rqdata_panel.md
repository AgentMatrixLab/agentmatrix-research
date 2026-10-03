# RQData 全 A 日线离线面板数据契约

状态：实现草案，待 Hermes A 按服务器实际导出格式核对。此文件定义接口，不证明真实数据已导出或通过验证。

## 1. 文件组成

每个 Parquet 数据文件必须有一个相邻 sidecar JSON：

```text
rqdata_panel.parquet
rqdata_panel.parquet.json
benchmark_000985.parquet
benchmark_000985.parquet.json
```

数据文件为 Hermes A 从 115 服务器 RQData FULL 环境导出的离线文件。Trae 侧只读取本地文件，不联网、不访问服务器、不接触凭证。提交仓库时不包含客户数据、Parquet 结果或密钥。

## 2. 全 A 日线面板

采用长表：每行对应一个交易日和一个证券，`(date, code)` 唯一。

必需列：

| 列 | Parquet 类型 | 说明 |
|---|---|---|
| `date` | date 或 timestamp | 交易日；不得含时区或非零时分秒，不得为空 |
| `code` | string | RQData 证券代码；不得为空 |
| `open`, `high`, `low`, `close` | numeric | 原始未复权日线价格 |
| `volume`, `amount` | numeric | 当日成交量、成交额 |
| `adjustment_factor` | numeric | RQData 复权因子；本契约选择“原始 OHLC + 独立复权因子”，不得把复权价混入原始价格列 |
| `is_suspended` | boolean | 当日是否停牌 |
| `is_st` | boolean | 当日是否 ST |
| `listing_date` | date 或 timestamp，可空 | 上市日期 |
| `delisting_date` | date 或 timestamp，可空 | 退市日期；未退市可空 |
| `limit_up`, `limit_down` | numeric，可空 | 当日涨停价、跌停价 |

价格列单位、`amount` 币种/单位、成交量单位及 `adjustment_factor` 的确切来源定义须与 RQData 导出配置一致，并在正式运行清单中记录。读取器不推断或转换这些口径。

停牌日仍保留面板行，并按源数据如实提供状态和数值。OHLC、成交量、成交额及涨跌停价可空；读取器不插值、不填充、不前向填充。日期、证券代码、状态标记及复权因子不可空。复权因子必须为有限正数。

## 3. 000985 基准收益文件

基准单独存为日频 Parquet，必须包含：

| 列 | Parquet 类型 | 说明 |
|---|---|---|
| `date` | date 或 timestamp | 基准交易日，不得为空 |
| `return` | numeric | 当日简单收益率，以小数表示（例如 1% 记为 `0.01`），不得以百分数整数存储 |

一个日期只能有一行。sidecar 必须写明 `benchmark_code: "000985"`，以及 `return_type` 为 `price_return` 或 `total_return`。在 Hermes 的 `run_manifest.json` 明确口径之前，不得自行假设是全收益或价格指数，也不得把两种口径混用。

## 4. Sidecar JSON

两个数据文件的 sidecar 均必须包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | string | 数据来源；正式运行填写 `RQData FULL`，仅测试夹具可写 `TEST_ONLY_SYNTHETIC` |
| `dataset` | string | 面板为 `daily_panel`；基准为 `benchmark_daily_return` |
| `data_start` | `YYYY-MM-DD` | 文件实际最早日期 |
| `data_end` | `YYYY-MM-DD` | 文件实际最晚日期 |
| `row_count` | integer | Parquet 实际行数 |
| `sha256` | 64 位十六进制字符串 | Parquet 文件原始字节的 SHA-256 |

面板 sidecar 还须包含 `price_basis: "unadjusted_ohlc_with_adjustment_factor"` 及 `adjustment_factor_definition`，说明复权因子的 RQData 字段、方向/含义和可复现的锚点口径。基准 sidecar 还须包含 `benchmark_code` 与 `return_type`。

示例（值仅用于展示结构，不是数据证据）：

```json
{
  "source": "RQData FULL",
  "dataset": "daily_panel",
  "data_start": "2020-01-02",
  "data_end": "2026-09-30",
  "row_count": 1000000,
  "sha256": "<64位实际文件SHA-256>",
  "price_basis": "unadjusted_ohlc_with_adjustment_factor",
  "adjustment_factor_definition": "<按实际RQData导出配置填写>"
}
```

## 5. 读取与失败规则

`research_core/data_loader/rqdata_panel.py` 只从传入的本地路径读取 Parquet 和相邻 sidecar。校验必需列、列类型、空值规则、唯一键、日期范围、行数和 Parquet SHA-256；任何文件缺失或校验失败都抛出明确异常，不联网、不修复、不静默降级。

SHA-256 校验只证明当前 Parquet 字节与 sidecar 中声明的摘要一致，不证明 sidecar 来源真实性。正式真实性仍须由 Hermes 运行报告、冻结的 `run_manifest.json` 和受控数据导出过程核对。
