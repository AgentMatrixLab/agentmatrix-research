# 交付分支变更记录（delivery/2026-10-07）

只记录本分支的实际变更。**本文件不包含任何因子有效性结论**；通过/淘汰结论必须来自 115 服务器上带 hash 的正式运行。

## 未完成/未裁定（先看这里）

- **没有真实数据结果**：截至本记录，仓库里没有任何真实 A 股数据的验证产物，`factor_catalog.csv` 里所有因子状态都会是 `not_run`。
- **切分口径未裁定**：`configs/validation_gates.yaml` 写的是 train `2016-01-01~2023-12-31` / OOS `2024-01-01~2026-08-31`；任务书冻结的是 train 到 `2022-12-31` / OOS 从 `2023-01-01` 起。**两者差一整年，未裁定前不得对外声称任何样本外结论。**
  取证（2026-10-03）：该 config 由 `61dcf19` 建库，`git log -S'train_end'` / `-S'adjust_type'` 都只命中它，**自那以后从未改过**；全仓搜 `2022-12-31` **零命中**；也没有任何测试把生产切分写死 —— 所以改它不会破坏测试，纯粹是口径决定。详见 `pipeline_cf9c883_notes.md` 第 7 节。
- **复权口径未裁定**：config 用 `adjust_type: post`（后复权价），Trae 的数据契约写「未复权 OHLC + 复权因子」。
- **候选数口径不一致**：任务书说价量候选 91 个（另有 10 个风险暴露不计入）；`methodology.md` 早先写的是 134 个（技术指标 114 + Alpha101 20）。**以实际 `candidate_list.csv` 为准**，差异必须先查清。

## 时间线

### 基线

| commit | 内容 |
|---|---|
| `61dcf19` | `main` 基线：deterministic single-factor validation (#120) |

### Trae（A1，2026-10-03）

| commit | 内容 |
|---|---|
| `478b967` | 新增 RQData 全 A 日线面板与 000985 基准的 Parquet/sidecar 数据契约、只读本地加载器、14 个 test_only 单测 |
| `0decc58` | A1 交接状态记录 |

### Hermes（服务器侧流水线，2026-09-25 提交 / 2026-10-03 推到 origin）

| commit | 内容 |
|---|---|
| `cf9c883` | 在 `feat/deterministic-factor-validation` 上新增 `negative_pct_change` 变换（一月反转），并让该变换在**未过滤的整块面板**上计算后按 `(date, code)` 映回；新增 `constraints-rqsdk.txt` 摘要记录 |

分支 `server/pipeline-cf9c883` 目前就是 `main` + 这 1 个 commit。

### DS（2026-10-03，本分支）

| commit | 内容 |
|---|---|
| `e346179` | **D0** 接手盘点回报 |
| `2b6bb13` | **D1** cf9c883 流水线只读阅读笔记（`docs/delivery/pipeline_cf9c883_notes.md`） |
| `00ec0d8` | **D1** 回报 |
| `ef4fcb1` | **D2** 合入 `origin/server/pipeline-cf9c883`（`--no-ff`，零冲突） |
| `f228f85` | **D2** 新增预计算因子读取通道与本地面板读取通道（见下） |
| `39f603d` | **D2** Hermes 离线运行手册 `docs/delivery/runbook_hermes.md` |
| `0657d02` | **D2** 回报 |
| `c68278f` | **D3** 批量入口 `validate-batch` + 批量 run_manifest |
| `6f8708c` | **D3** runbook 增补批量章节与 `candidate_list.csv` 格式 |
| `f44814d8` | **D3** 回报 |

## D2 具体改了什么

新增：

- `research_core/factor_lab/precomputed_factors.py`：读长表因子 Parquet（`date, code, factor_name, value`）+ sidecar。校验 SHA-256、列（必须正好四列）、类型、`(date, code, factor_name)` 重复键、非有限值、日期区间、行数；NaN 允许，缺项报错退出。
- `research_core/factor_lab/panel_source.py`：读本地面板 Parquet + sidecar（列名按流水线需要，不做改名与复权换算）。
- `tests/test_only_precomputed_factors.py`、`tests/test_only_local_panel_source.py`。

修改：

- `deterministic_validation.py`：新增 `precomputed=` / `segment=` / `panel_file=` / `extra_manifest=` 参数；新增 `_training_segment_result`；新增 `_require_factor_coverage`。**门槛阈值、判定逻辑、切分、成本一律未改。**
- `cli.py`：`validate` 增加 `--factor-file` / `--factor-sidecar` / `--panel-file` / `--panel-sidecar` / `--segment`。

关键性质：

- **`result_hash` 只由数值结果决定**：同一份数据，原生 transform 与预计算通道必须得到同一个 `result_hash`。来源（因子文件名/hash）只记在 `run_manifest.json`。
- **扰动不可跳过**：预计算通道必须提供 `<因子ID>|window=<w>` 的扰动变体，缺了直接报错，不让 `parameter_perturbation` 变恒真。
- **`--segment train` 完全不碰 OOS 窗口**：不评估门槛、不算样本外指标，输出到 `<factor_id>/train/` 独立目录。

## D3 具体改了什么

新增：

- `research_core/factor_lab/batch_validation.py`：读 `candidate_list.csv`，逐个因子跑完整流程，单因子失败记原因并继续；输出 `batch_manifest.json`（commit、面板/因子文件 hash、切分、全量参数快照、每个因子的 `result_hash` 与产物 sha256）与 `batch_summary.csv`。
- `cli.py` 的 `validate-batch` 子命令；退出码 `0`（无 error）/ `3`（有因子报错）/ `2`（输入契约错误）。
- `tests/conftest.py`（合成面板/配置共享夹具）、`tests/test_only_batch_validation.py`。

已证明的性质：

- 面板与因子文件**只读一次**，批量共用内存对象。
- 批量入口与单因子入口对同一因子给出**相同 `result_hash`**。

## D4 具体改了什么

新增：

- `research_core/factor_lab/factor_catalog.py` + `scripts/build_factor_catalog.py`：从 `candidate_list.csv` 与真实运行结果生成 `factor_catalog.csv`（因子 ID、名称、公式、分类、所需字段、方向、状态、失败门槛、原因、`result_hash`、证据路径）。**没有跑过的因子一律 `not_run`，不猜、不填。**
- `research_core/factor_lab/package_delivery.py` + `scripts/package_delivery.py`：只把 `status == "validated"` 的因子打进交付包；淘汰/报错/`needs_human`/未跑的因子只列状态与原因，不打包产物。一个都没通过时写 warning 并以退出码 `4` 结束，避免误发空包。

## 未做的事

- 没有连接 115 服务器、没有接触 RQData 账号或任何密钥。
- 没有修改 `configs/validation_gates.yaml` 的门槛或切分。
- 没有新增因子定义（`reversal_1m` 的定义来自 Hermes 的 `cf9c883`）。
- 没有生成、也没有伪造任何真实数据验证结果。
