# 离线运行手册（给 Hermes A 在 115 服务器上用）

状态：D2 交付。本文描述怎么在**不联网、不碰 RQData 账号**的前提下，用导出的文件跑正式验证流水线。
适用范围：`delivery/2026-10-07` 分支，代码 commit 见 `run_manifest.json` 的 `code_commit`。

## 0. 硬约束（先看这条）

1. **不改门槛**：`configs/validation_gates.yaml` 的 `gates:`、`portfolio.cost`、`statistics`、`split` 一律不动。
2. **不用 OOS 结果挑因子**：`--segment train` 只看训练期；选簇代表只能用 train 的输出。
3. **不静默降级**：任何输入契约不符都会**报错退出**，不会跳过、不会填默认值、不会让某条门槛变恒真。
4. **口径不明就停**：`split` 与 `price_basis` 两处口径目前仍有待确认项（见第 8 节），跑之前请确认或回到 Sam。

## 1. Python 环境

```
Python 3.13（本机实测版本）
numpy>=2.0  pandas>=2.2  scipy>=1.14  PyYAML>=6.0  pyarrow>=15
```

仓库里 `requirements-factor-lab.txt` 已列了 numpy/pandas/scipy/PyYAML；**pyarrow 是本流程新增的必需项**（读写 parquet）。

依赖确认：

```bash
python -c "import numpy, pandas, pyarrow, yaml; print('ok')"
```

跑测试：

```bash
python -X utf8 -m pytest tests -q
```

本机基线（合成数据）：**103 passed / 3 failed**；3 个 failed 是已知的 `tests/test_backtest_jobs.py` 在 Windows 上清理临时 `jobs.db` 的文件占用问题，与因子逻辑无关。

## 2. 输入文件一：本地面板 Parquet

文件名随意，但必须有一个相邻的 sidecar JSON（`<文件名>.json`）。

**必需列（列名必须完全一致，本流程不做改名）**：

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | date/timestamp，不可空、无时区、无时分秒 | 交易日 |
| `code` | string，不可空 | RQData 证券代码 |
| `close` | numeric | **与 config 的 `data.adjust_type: post` 一致的价格口径** |
| `volume` | numeric | 成交量 |
| `total_turnover` | numeric | 成交额 |
| `limit_up` / `limit_down` | numeric，可空 | 当日涨停价 / 跌停价（可空的行走资格过滤会被剔除） |
| `circulation_a` | numeric | 流通股本（风格因子 size 用） |
| `listed_date` | date，不可空 | 上市日期（上市满 120 天才进样本） |
| `de_listed_date` | date，可空 | 退市日期，未退市留空 |
| `is_st` | boolean，不可空 | 是否 ST |
| `is_suspended` | boolean，不可空 | 是否停牌 |

**sidecar 必需字段**：

```json
{
  "source": "RQData FULL",
  "dataset": "validation_panel",
  "data_start": "2015-01-01",
  "data_end": "2026-08-31",
  "row_count": 13000000,
  "sha256": "<Parquet 原始字节的 SHA-256>",
  "price_basis": "post_adjusted"
}
```

`source` / `dataset` / `data_start` / `data_end` / `row_count` / `sha256` / `price_basis` 缺一不可。
读取器会校验：SHA-256、列齐全、`date`/`code` 非空、布尔列类型、数值列有限、`(date, code)` 无重复键、sidecar 声明的日期区间与行数是否与实际一致。**任何一条不符直接报错退出。**

> 注意：这份面板契约的列名和 `docs/delivery/data_contract_rqdata_panel.md`（Trae 的原始导出契约）**不一样**。那份是「原始 OHLC + 复权因子」，这份是**流水线直接吃的形态**。从 RQData 字段到这里需要一层明确映射（例如 `total_turnover`、`circulation_a`、`limit_up`/`limit_down`、复权后的 `close`）。映射口径请写进 `run_manifest.json` 之外的自查记录，别混用两种价格口径。

## 3. 输入文件二：预计算因子值 Parquet

长表，**列必须正好是这四列**：

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | date/timestamp，不可空 | 交易日 |
| `code` | string，不可空 | 证券代码 |
| `factor_name` | string，不可空 | 因子名，见下面的命名规则 |
| `value` | numeric | 因子值；**允许 NaN**（预热期/停牌），**不允许 ±inf** |

`(date, code, factor_name)` 必须唯一。

**`factor_name` 命名规则（关键）**：

- 基础值：就是因子 ID，例如 `reversal_1m`
- 参数扰动值：`<因子ID>|window=<窗口>`，例如 `reversal_1m|window=18`

流水线的 `parameter_perturbation` 门槛会按 `multipliers: [0.8, 1.2]` 去算扰动窗口，并向文件索取对应的 `factor_name`。
以 `reversal_1m`（base window 22）为例，文件里必须同时有：

```
reversal_1m
reversal_1m|window=18      # round(22 * 0.8)
reversal_1m|window=26      # round(22 * 1.2)
```

**少任何一个，运行会直接报错退出**（报错信息会写明缺哪个名字）。这是故意的：扰动门槛必须真被测到，不允许因为拿不到数据就当作通过。

**sidecar 必需字段**：

```json
{
  "source": "RQData FULL",
  "dataset": "factor_values",
  "data_start": "2016-01-01",
  "data_end": "2026-08-31",
  "row_count": 39000000,
  "sha256": "<Parquet 原始字节的 SHA-256>",
  "factors": {
    "reversal_1m": {"window": 22},
    "rsi_6": {"window": 6}
  },
  "value_definition": "说明因子单位、符号方向、复权口径和锚点"
}
```

- `factors` 的键是基础因子 ID；每个都必须至少在文件里有行。
- `factors` 里声明的 `window` 是扰动的基准窗口。
- 文件里出现未声明的 `factor_name` 会报错（防止张冠李戴）。
- 文件区间必须**覆盖 `split.train_start` 到 `split.oos_end`**，否则报错。
- 每个因子都要覆盖面板里存在的所有 `(date, code)`：缺的行会变成 NaN，只会让 `coverage` 门槛变差，不会被填补。

## 4. 命令

单因子样本外（正式判定）：

```bash
python -X utf8 -m research_core.factor_lab.cli validate \
  --factor reversal_1m \
  --config configs/validation_gates.yaml \
  --panel-file /data/panel.parquet \
  --factor-file /data/factors.parquet \
  --segment oos
```

单因子训练段（**只用于选簇代表，不含任何样本外指标**）：

```bash
python -X utf8 -m research_core.factor_lab.cli validate \
  --factor reversal_1m \
  --config configs/validation_gates.yaml \
  --panel-file /data/panel.parquet \
  --factor-file /data/factors.parquet \
  --segment train
```

原生对照（不读因子文件，用内置 transform 自己算 `reversal_1m`，用于核对两条通道一致）：

```bash
python -X utf8 -m research_core.factor_lab.cli validate \
  --factor reversal_1m \
  --config configs/validation_gates.yaml \
  --panel-file /data/panel.parquet \
  --segment oos
```

**退出码**：`0` = 跑完（`validated` 或 `rejected` 都是 0，**必须读 JSON 里的 `status`**）；`2` = 输入契约错误或 `needs_human`，stdout 里有 `reason`。

## 5. 批量跑全部候选（validate-batch）

一条命令跑完 `candidate_list.csv` 里的全部因子。**单个因子失败会记录原因并继续跑，不会中断整批。**

```bash
python -X utf8 -m research_core.factor_lab.cli validate-batch \
  --candidates candidate_list.csv \
  --config configs/validation_gates.yaml \
  --panel-file /data/panel.parquet \
  --factor-file /data/factors.parquet \
  --segment oos \
  --output-dir /data/batch_run_20261004
```

可选参数：`--factors a,b,c` 只跑子集；`--segment train` 跑训练段。

**退出码**：`0` = 全部因子都跑完且**没有** `error`；`3` = 跑完了但有因子报错（结果仍在产物里）；`2` = 输入契约错误（整批没跑）。

### 5.1 candidate_list.csv 格式

必需列：`factor_id`。其余列随便加，会原样带进 `batch_manifest.json` 的 `metadata`（建议按 D4 因子目录用 `name,formula,category,required_fields,direction,status`）。

```csv
factor_id,name,formula,category,required_fields,direction,status
reversal_1m,一月反转,"-(close_t / close_{t-22} - 1)",price_momentum,"close,date,code,is_suspended",negative_reversal,research
```

规则：
- `factor_id` 不能为空、不能重复，否则整批拒绝启动。
- 每个 `factor_id` 必须在因子文件里有对应行；**没有的那个因子会被记成 `error` 并继续跑别的**。
- 编码用 UTF-8（读的时候也兼容带 BOM 的 UTF-8）。

### 5.2 批量产物

- `batch_summary.csv`：每因子一行 —— `factor_id, status, failed_gates, reason, 指标, result_hash, params_hash, 产物路径`。
- `batch_manifest.json`：
  - `code_commit`、`created_at_utc`、`segment`
  - `candidates_file` + sha256、`candidate_count`、`factor_ids`
  - `panel_file` + sha256 + `panel_price_basis`、`data_snapshot_hash`
  - `factor_file` + sha256 + 因子文件区间
  - `configuration_file` + sha256，以及 `parameters`（`split` / `gates` / `portfolio.cost` / `perturbation` / `statistics` / `forward_returns` 全量快照）
  - `counts`、`validated` / `rejected` / `errors` / `needs_human` 清单
  - `results`：每个因子的状态、`failed_gates`、淘汰原因、指标、`result_hash`、产物路径与产物文件的 sha256
  - `outputs.batch_summary_sha256`
- 每个因子的 `validation_report.md` / `validation_result.json` / `run_manifest.json` 仍写到 `config.output.root/<factor_id>/`（`train` 段在 `.../<factor_id>/train/`）。

## 6. 输出文件

输出根目录来自 `config.output.root`（默认 `data/factor_lab/validation_runs`）：

```
data/factor_lab/validation_runs/<factor_id>/validation_report.md      # 人读：门槛表 + RankIC 表
data/factor_lab/validation_runs/<factor_id>/validation_result.json    # 机器读：全部指标与门槛判定
data/factor_lab/validation_runs/<factor_id>/run_manifest.json         # 运行清单
data/factor_lab/validation_runs/<factor_id>/needs_human.json          # 只在缺数据时产生
data/factor_lab/validation_runs/<factor_id>/train/...                 # --segment train 的输出，与 oos 分开
```

`run_manifest.json` 记录：

| 字段 | 含义 |
|---|---|
| `data_snapshot_hash` | 传入面板的框架哈希（对未过滤的原始面板算） |
| `code_commit` | 运行目录的 `git rev-parse HEAD` |
| `params_hash` | `sha256(factor_id + 完整 config)` |
| `result_hash` | `sha256(validation_result.json 的规范化内容)` |
| `segment` | `oos` / `train` |
| `factor_source` | `precomputed_parquet`（读了因子文件）/ `pipeline_transform`（自算） |
| `factor_file` / `factor_file_sha256` | 因子文件名与其字节 SHA-256 |
| `panel_file` / `panel_file_sha256` / `panel_price_basis` | 面板文件与其字节 SHA-256、声明的价格口径 |
| `constraints_file` / `constraints_sha256` | `constraints-rqsdk.txt` 的摘要（仓库里存在时） |

**重要性质**：`result_hash` 只由数值结果决定，与因子来自哪条通道无关。同一份面板、同一个因子，`--factor-file` 与原生自算两条路必须得到**完全相同的 `result_hash`**。请用这一条做自查。

## 7. 预计耗时（实测）

本机（Windows，非服务器）用合成面板实测：

| 场景 | 面板规模 | 耗时 |
|---|---|---|
| `--segment oos` | 46,920 行（30 只 × 1564 交易日） | **20.13 秒** |
| `--segment train` | 同上 | **11.02 秒** |

**真实全 A 的耗时与内存占用：未知**，必须由你在服务器上实测后回报。全 A 日线全区间（含 2015 起预热）行数量级远大于上面的合成面板，导出文件与内存占用请提前评估。

**批量耗时 ≈ 因子数 × 单因子耗时**（每个因子都要完整跑一遍准入+OOS+扰动）。批量入口已经做了一件事来省时间：**面板和因子文件只读一次**，所有因子共用同一份内存对象，不会每个因子重读大文件。

## 8. 常见失败与含义

| 现象 | 含义 |
|---|---|
| `PanelSourceError: ... SHA-256 does not match sidecar` | parquet 被改过/传坏了，或 sidecar 是旧的 |
| `PrecomputedFactorError: ... parameter_perturbation ...` | 因子文件缺 `<id>\|window=<w>`，扰动门槛测不了（**这是设计如此**） |
| `PrecomputedFactorError: ... does not cover the frozen train..oos range` | 因子文件区间不够，补齐再跑 |
| `needs_human.json`，`reason` 里提 `Missing fields` | 面板缺列，按第 2 节补 |
| `needs_human.json`，`reason` 提 `No rows remain after all-A eligibility filters` | 过滤后没有样本，多半是列口径或日期区间不对 |
| `status: rejected` | 正常结果，说明没过门槛；看 `failed_gates` 与报告 |

## 9. 跑之前必须先确认的两件事

1. **切分**：`configs/validation_gates.yaml` 当前写的是 train `2016-01-01~2023-12-31` / OOS `2024-01-01~2026-08-31`；任务书冻结的是 train 到 `2022-12-31` / OOS 从 `2023-01-01` 起。**两者不一致，尚未裁定**。这条直接决定 `oos_seal` 与全部样本外指标，不要自行改。
2. **价格口径**：config 是 `adjust_type: post`（后复权价），Trae 的原始契约是「未复权 OHLC + 复权因子」。面板 sidecar 的 `price_basis` 必须与 config 实际口径一致，不一致就停下来问。

## 10. 交付边界

本手册只说明怎么跑。**跑出来的结果不代表因子有效**；有效与否只看流水线门槛判定，且真实数据证据只能来自 115 服务器上的正式运行。
