# Notion 粘贴稿：DS 回报（D0–D5 + 阻塞）

**为什么是粘贴稿**：按任务书，能用 Notion CLI 就在页面「2026-10执行情况」（ID `3ece9a01-c0bb-8017-87c1-c8c86dd1dc92`）下建子页；不能用就把回报卡原文发给 Sam 粘贴。
DS 侧已核实**没有任何可用通道**：`notion` / `notion-cli` / `notionctl` / `ntn` 均未安装；npm 全局只有 `@tarojs/cli` 与 `mirror-config-china`；无 `NOTION_TOKEN` 等环境变量；DSH 插件目录 193 个条目里没有任何 Notion 插件，也没有配置任何 MCP server（无 `mcpServers` 配置、无 mcp 配置文件）。因此本文件即「回报卡原文」。

**建议做法**：在「2026-10执行情况」下按下列标题建 7 个子页，每个标题下的内容即为该页正文。

| # | 建议子页标题 |
|---|---|
| 1 | `DS回报｜10-03 23:12｜D0–D5 总账与阻塞` |
| 2 | `DS回报｜10-03 21:50｜D0 接手盘点` |
| 3 | `DS回报｜10-03 22:10｜D1 读懂正式流水线` |
| 4 | `DS回报｜10-03 22:25｜D2 预计算因子读取通道` |
| 5 | `DS回报｜10-03 22:35｜D3 批量入口` |
| 6 | `DS回报｜10-03 22:52｜D4 交付文档与打包` |
| 7 | `DS回报｜10-03 23:02｜D5 互查（阻塞）` + `DS回报｜10-03 23:12｜D5 前置加固` |

时间说明：各卡时间来自会话时间戳重建，属近似值；D5 / D5b 的完成时间已按时间戳校正。
所有证据（commit、测试结果、文件 sha256）均可在 `delivery/2026-10-07`（HEAD `d7d6fac0cfb24d06e9c40f654b8222e3a3009df7`，本地=远端）核对。

---

## 子页 1：DS回报｜10-03 23:12｜D0–D5 总账与阻塞

【回报】DS（单位电脑）｜D0–D5 总账与阻塞｜2026-10-03 23:12

状态：D0–D4 完成；D5 工具就绪但**结论阻塞**（缺 Hermes 真实产物与 `candidate_list.csv`）

做了什么：
- 接手 Trae 的交接：从零克隆仓库、切 `delivery/2026-10-07`、核对基线 83 passed/3 failed、读完 Trae 6 个文件。
- 合入 `server/pipeline-cf9c883`（零冲突），给它加了**预计算因子读取通道**与**本地面板读取通道**，让 Hermes 能在服务器上离线跑 ROC/RSI6/alpha002 这类流水线本身算不了的因子。
- 加了 `--segment train/oos`（train 只出训练期指标、完全不碰 OOS）、批量入口 `validate-batch`、因子目录脚本、只收通过项的打包脚本、独立互查工具，并做了全链路彩排。
- 全程**不改门槛、不改切分、不新增因子、不连 115 服务器、不碰密钥**；`configs/validation_gates.yaml` 一行未改。

证据：
- 分支 `delivery/2026-10-07`，HEAD `d7d6fac0cfb24d06e9c40f654b8222e3a3009df7`，本地=远端，工作区干净（19 个 commit 全部已推送）。
- 测试：`python -X utf8 -m pytest tests -q` → **140 passed / 3 failed**；3 个 failed 是**已知**的 `tests/test_backtest_jobs.py` 在 Windows 上清理临时 `jobs.db` 的占用问题（`WinError 32`），与本任务无关。
- 回报文件（均已 commit）：`docs/superpowers/reports/2026-10-03-ds-D0.md` `73eb7802…`、`-D1.md` `4002e3f1…`、`-D2.md` `b7bdf7f9…`、`-D3.md` `dfc86a7a…`、`-D4.md` `a929144b…`、`-D5.md` `7514422e…`、`-D5b.md` `d5c5fb21…`（完整 sha256 见各子页）。

没做或未通过：
- **「哪些因子通过」这一栏是空的，而且应该空着** —— 还没有任何真实 A 股数据跑过。只交通过的、数量不凑，所以不预填。
- D5 的真实不一致项清单无从产出（缺 Hermes 产物）。
- 真实全 A 的批量耗时与内存**未知**：本机 8G 内存/当时空闲 1G/双核，压测结果不可外推，只能由 115 服务器实测。

需要Sam决定：
1. **促 Hermes 按 `runbook_hermes.md` 第 5.3 节跑一次并回传**：`batch/`（含 `batch_manifest.json`、`batch_summary.csv`、`cross_check.json`）、`panel.parquet`+sidecar、`factors.parquet`+sidecar、`candidate_list.csv`、`delivery_package/package_manifest.json`、服务器 `git rev-parse HEAD`。
2. **切分口径**：代码事实是 train `2016-01-01~2023-12-31` / OOS `2024-01-01~2026-08-31`（自 `61dcf19` 建库起未变，全仓无 `2022-12-31`）；任务书冻结的是 train 到 `2022-12-31` / OOS 从 `2023-01-01` 起。哪个为准。（改 config 不影响任何测试。）
3. **复权口径**：`adjust_type: post`（同样自 `61dcf19` 起未变）vs Trae 契约的「未复权 OHLC + 复权因子」。
4. **候选数口径**：任务书 91（+10 风险暴露不计入）vs `methodology.md` 早先草稿 134（114+20）。
5. **`candidate_list.csv` 谁提供**（批量入口与目录脚本都在等它）。
6. **扰动变体接口** `<因子ID>|window=<w>` 是否由 Hermes 的因子导出提供。

下一步：等 Hermes 回传后跑 D5 互查（一条命令）。

---

## 子页 2：DS回报｜10-03 21:50｜D0 接手盘点

【回报】DS（单位电脑）｜D0 接手盘点｜2026-10-03 21:50

状态：完成

做了什么：
- 本机工作目录 `D:\agentmatrix` 是空目录、仓库从没克隆过；先 clone 再 `git fetch --all --prune`。
- 切到 `delivery/2026-10-07`：HEAD `0decc58`，工作区干净，最近 5 个 commit 与交接一致。
- 本机缺 `pyarrow`（9 个测试模块收集失败），装 `pyarrow 25.0.1` 后重跑，与基线一致：83 passed / 3 failed。
- 3 个失败确认是已知的 `jobs.db` 占用问题，未做修改。
- `origin/server/pipeline-cf9c883` 已出现，`cf9c883` 可正常 `git show`；Trae 的 6 个文件全部读完。

证据：
- 分支 `delivery/2026-10-07`；D0 commit `e346179670bf7c330ccf49effceb5205bb3bad99`；基线 HEAD `0decc5899d1fe86bab156cd3c17551b4e53d0980`。
- 测试：`python -X utf8 -m pytest tests -q` → `3 failed, 83 passed, 660 warnings in 80.01s`。
- `cf9c883` 只改 4 个文件；相对 `main` 只领先 1 个 commit；`merge-tree` 预检与交付分支**无冲突**。
- 输出文件 `docs/superpowers/reports/2026-10-03-ds-D0.md`，sha256 `73eb78021a851787cbd1a8520e222c6bac5b562c7f07599194c8006a8a831c35`。

没做或未通过：
- 未细读流水线实现（那是 D1）。
- 仓库里没有 `candidate_list.csv`。
- 发现两处口径不一致，未擅自改任何文件：① 切分（config `2023-12-31/2024-01-01` vs 任务书 `2022-12-31/2023-01-01`）；② 候选数（91 vs 134）。

需要Sam决定：切分口径；候选数口径；`candidate_list.csv` 来源与格式；提交署名是否统一（DS 用 `DS (DeepSeek) <ds@alphaagents.io>`，Trae 用 `AlphaBoss <boss@alphaagents.io>`）。

下一步：D1

开始时间：2026-10-03 21:34　完成时间：2026-10-03 21:50　实际用时：约 16 分钟

---

## 子页 3：DS回报｜10-03 22:10｜D1 读懂正式流水线

【回报】DS（单位电脑）｜D1 读懂正式流水线（cf9c883）｜2026-10-03 22:10

状态：完成（只读任务，未改任何代码）

做了什么：
- `git show cf9c883` 全量读完，并把该 commit 版本的 `deterministic_validation.py`(979 行)、`cli.py`(478 行)、`validation_gates.yaml`(154 行) 抽出来逐段读。
- 摸清入口：`python -m research_core.factor_lab.cli validate --factor <id> --config configs/validation_gates.yaml`。
- 定位**因子值唯一注入点**：`validate_panel` 第 660-666 行。
- 定位门槛：阈值全在 `validation_gates.yaml` 的 `gates:` 段，判定在 `validate_panel` 第 760-833 行。
- 摸清输出与 hash：每因子一个目录，出 `validation_report.md` / `validation_result.json` / `run_manifest.json` / `needs_human.json`。
- 写清「预计算因子」接入点，并**提前标出扰动窗口这个坑**（第 738-758 行会重算 0.8×/1.2× 窗口，取不到数据就必须如实标注，不许让门槛恒真）。

证据：
- 分支 `delivery/2026-10-07`；commit `2b6bb1353dbe9bdaa873f0019dcf5033ea6062ee`。
- 新增 `docs/delivery/pipeline_cf9c883_notes.md`（120 行），未改任何代码。
- 输出文件 `docs/delivery/pipeline_cf9c883_notes.md`，D1 提交时 sha256 `ed5d8827df2cd1d5d638d193d952bc6eec4434115d9e7fcf8a944a22f27517ca`；D5 追加切分取证后当前 sha256 `79a0e8ac0cd4651ac29dcc1358616159351ba7c2b0d41ca4768621ca8e696ab3`。
- 全量测试：`3 failed, 83 passed, 660 warnings in 73.10s`（本轮只加文档）。

没做或未通过：
- 未实际运行流水线（本机无数据、也不该联网跑），机制结论均为读代码得出。
- 扰动窗口的处理方式需裁定。
- 三处口径冲突未定（切分、复权、候选数）。

需要Sam决定：切分；预计算因子的扰动窗口处理；复权口径；`candidate_list.csv`；候选数 91 vs 134。

下一步：D2

开始时间：2026-10-03 21:56　完成时间：2026-10-03 22:10　实际用时：约 14 分钟

---

## 子页 4：DS回报｜10-03 22:25｜D2 预计算因子读取通道

【回报】DS（单位电脑）｜D2 预计算因子读取通道｜2026-10-03 22:25

状态：完成（功能与测试都做完并推送；两处口径待裁定）

做了什么：
- **合入 server 分支**：`origin/server/pipeline-cf9c883` 并入 `delivery/2026-10-07`，`--no-ff`，**零冲突**。
- **新增预计算因子读取器**：读长表 parquet（`date, code, factor_name, value`）+ sidecar，校验 SHA-256、列（必须正好四列）、类型、重复键、非有限值、日期区间、行数；不符**报错退出**。NaN 允许，±inf 拒绝。
- **走原样判定**：只替换「算因子」那一步，准入过滤、切分、8 条门槛、成本、扰动全部复用原代码；`configs/validation_gates.yaml` 一行未改。
- **`--segment train / oos`**：train 只算训练期指标、不评估门槛、不碰 OOS，输出到独立 `train/` 子目录。
- **额外补了一个入口**（任务书没写但不补就跑不了）：`--panel-file` 本地面板读取器 —— 原来 CLI 离线根本无法喂面板。
- 写了 `docs/delivery/runbook_hermes.md`。

证据：
- commit：合并 `ef4fcb1`、代码 `f228f85`、文档 `39f603d`。
- 新增 `research_core/factor_lab/precomputed_factors.py`、`research_core/factor_lab/panel_source.py`、`tests/test_only_precomputed_factors.py`、`tests/test_only_local_panel_source.py`、`docs/delivery/runbook_hermes.md`；修改 `deterministic_validation.py`(+218/-16)、`cli.py`(+57)。未改 configs、未改已有测试。
- 测试：`pytest tests -q` → **114 passed / 3 failed**（D2 前 84）。
- **等价性**：原生 vs 预计算 `result_hash` 相同 = `497be4922c2ddc671b18090492f7c753807d28329561f1954199208232556180`（浮点容差写死 `1e-10`，另加 12 位取整后规范化 JSON 完全相等）。
- **证明没动老逻辑**：合并前版本与改后版本跑同一份数据，规范化结果载荷逐字节相同，`result_hash` 都是 `6f004a65d71425981c12b38c175751f3ce007d367f9c2130927212fbda516068`，面板 hash 都是 `249142742fe5b8d3f82a4ba73d1aae8619a29a47f1cc8507ccff3d2d78889301`。
- CLI 离线实测（合成面板 46,920 行）：`oos` **20.13 秒**、`train` **11.02 秒**；真实全 A **未知**。
- 产物 sha256：`precomputed_factors.py` `142a6bc461b5328385a7d553420ac7cfc375b6eb12617a7fc74d14c3c1730b05`；`panel_source.py` `2f5da9d1355e188dc178f0253a8ba69c24c04d4fa7c53882768ea37cc181a5de`；`runbook_hermes.md` D2 时 `1f3e669e7781cf9e39ee1e44186a6c0448a7aa2f2ce09d85c0811b7a9a3abe7e`（后续 D3/D5 有增补，当前 `eed0136997bed7939b05753cded064f31d30c8e332466c849ccc238c901ba02e`，D3 时 `d8602925e421b07576d678f0308b1f30f710ffdb4d284166dbfb69661d5bd295`）；`test_only_precomputed_factors.py` D2 时 `37867eb8f9608deacda067d1fa9e1d2b9b2df9f75ff0159aa0eaed1b76100c6f`。
- 回报文件 `docs/superpowers/reports/2026-10-03-ds-D2.md`，sha256 `b7bdf7f9c072e1b09ca5b4b38fd4924394493b34abca6a8388e7154da1a1223a`。

没做或未通过：
- 未在真实 A 股数据上跑过，「通过哪些因子」仍是空的。
- 真实全 A 耗时/内存未实测。

需要Sam决定：扰动变体接口（`<因子ID>|window=<w>`，缺了直接报错）；切分；复权口径；`candidate_list.csv`；候选数 91 vs 134。

下一步：D3

开始时间：2026-10-03 22:10　完成时间：2026-10-03 22:25　实际用时：约 15 分钟

---

## 子页 5：DS回报｜10-03 22:35｜D3 批量入口

【回报】DS（单位电脑）｜D3 批量入口｜2026-10-03 22:35

状态：完成

做了什么：
- 新增 `validate-batch`：一条命令吃完 `candidate_list.csv` 全部因子，每个因子输出准入结果、指标、通过/淘汰原因。
- **单个因子失败不中断整批**：失败原因记进汇总与 manifest 后继续跑。
- 批量 `run_manifest.json` 记全：`code_commit`、面板 hash、因子文件 hash、切分、全量参数快照（gates/cost/perturbation/statistics/forward_returns）、每个因子的 `result_hash` 与产物 sha256。
- **省时间的关键实现**：面板与因子 parquet 只读一次，所有因子共用内存对象。
- 候选清单格式写进 runbook 第 5 节；退出码分档 `0` / `3`（有因子报错）/ `2`（输入契约错误）。

证据：
- commit `c68278f`（代码）、`6f8708c`（runbook 批量节）。
- 新增 `research_core/factor_lab/batch_validation.py`、`tests/test_only_batch_validation.py`、`tests/conftest.py`；修改 `cli.py`、`deterministic_validation.py`、`tests/test_only_precomputed_factors.py`、`docs/delivery/runbook_hermes.md`。
- 全量：`pytest tests -q` → **120 passed / 3 failed**（D3 前 114）；批量专项 6 passed。
- **批量 ≡ 单因子**：同一因子，批量入口与单因子 `execute_validation` 产出**相同 `result_hash`**（测试断言）。
- **失败隔离实测**：候选 `[reversal_1m, alpha002(文件里没有), avg_amount_log]` → `counts.error=1`、`errors=["alpha002"]`，另两个照常跑完。
- **CLI 真实进程测试**：退出码 **3**，`counts.error=1`，`batch_manifest.json` 与 `batch_summary.csv` 均落盘。
- 产物 sha256：`batch_validation.py` `66a42ac6d1cdc1361e3daa431974a3f3ddfbf46f37e40513ffb24a9cf88ceaa5`；`test_only_batch_validation.py` `c1d5b0fcde16ec656e40d50ffa1428ef3ef5df038fe78233f1d72be4ccadcf8d`；`conftest.py` `d552c6b2d4a277d36bcbb03ecfe826a1463639aa5cddc74131be8b23998c5329`。
- 回报文件 `docs/superpowers/reports/2026-10-03-ds-D3.md`，sha256 `dfc86a7a5fe13a5f833cd3f168812ba1aefd74b8fb63e9caf28e297177f938e7`。

没做或未通过：
- **没有在真实候选清单上跑过**：仓库里仍无 `candidate_list.csv`，所以「哪些因子通过、哪些淘汰」这一栏仍为空。
- 真实全 A 的批量耗时与内存未知（批量会一次性把整块面板读进内存）。

需要Sam决定：`candidate_list.csv` 谁提供、放哪、什么列；扰动变体接口；切分；复权；候选数 91 vs 134。

下一步：D4

开始时间：2026-10-03 22:28　完成时间：2026-10-03 22:35　实际用时：约 7 分钟

---

## 子页 6：DS回报｜10-03 22:52｜D4 交付文档与打包

【回报】DS（单位电脑）｜D4 交付文档与打包｜2026-10-03 22:52

状态：完成

做了什么：
- **因子目录生成脚本** `scripts/build_factor_catalog.py`：从 `candidate_list.csv` + 真实运行结果生成 `factor_catalog.csv`（因子 ID、名称、公式、分类、所需字段、方向、状态、失败门槛、原因、`result_hash`、证据路径）。**没跑过的一律 `not_run`，不猜不填。**
- **打包脚本只收通过的** `scripts/package_delivery.py`：只把 `validated` 的因子产物拷进交付包；淘汰/报错/`needs_human`/未跑的只列状态与原因；**一个都没通过时写 warning 并以退出码 4 结束**，防误发空包。
- **更新 `methodology.md`**：把早先草稿「134 个候选」改成**明确标注口径冲突**；补上两条因子来源通道、等价性要求、`--segment train` 不得看 OOS、扰动变体必须真被测到、批量与打包规则。
- **更新 `acceptance_checklist.md`**：新增门槛 diff 为空、两条通道 `result_hash` 一致、批量与单因子一致、批量失败隔离、扰动变体齐全、打包只收通过项、空包必须非零退出等验收项，并把三项口径列为阻断项。
- **新增 `changelog.md`**：按 commit 记录基线 → Trae → Hermes cf9c883 → DS D0~D4 的实际变更。

证据：
- commit `1a37b34`（代码）、`2560b27`（文档）。
- 新增 `research_core/factor_lab/factor_catalog.py`、`research_core/factor_lab/package_delivery.py`、`scripts/build_factor_catalog.py`、`scripts/package_delivery.py`、`tests/test_only_delivery_packaging.py`、`docs/delivery/changelog.md`；重写 `methodology.md`、`acceptance_checklist.md`。
- 全量：`pytest tests -q` → **129 passed / 3 failed**（D4 前 120；新增 9 个）。
- 打包规则实测（1 通过 + 1 淘汰 + 1 `needs_human` + 1 未跑）：包里只有那 1 个通过因子的产物；淘汰项只出现在 `excluded_factors`；`package_manifest.json` 记了每个拷贝文件的 sha256。
- 空包实测：没有任何因子通过 → warning + **退出码 4**。目录脚本实测：4 个候选 → `{"validated":1,"rejected":1,"needs_human":1,"not_run":1}`。
- 产物 sha256：`factor_catalog.py` `f8350d906802f4f0dce4b1f8f7b46ee89d665b100e8bf22a2293d5506bba7a32`；`package_delivery.py` `8e781e8affeb21cb9982df112d5d9717e0c54e356a1395a936fff540fc1ec7f2`；`build_factor_catalog.py` `0929796afca537634efe54966cac3aaaed5239ea25baa512354ce15267195954`；`scripts/package_delivery.py` `4f092df8da89faf6c0c4c6ed8c4488e69736d845f6fa0bac750ab17ff989435b`；`test_only_delivery_packaging.py` `88b186c6a6dbe0eaf92775e12d7a33dfb110f7298d8ad21f8664783b59b88175`。
- 文档 sha256：`changelog.md` `4b879e579b99c69c6bda4281be325dd252d8290ecc052353c95dff427b4d949b`（D4 时 `fef8c48321bc3072f7e618005f2df0c8ef479afe28e04d5a3731c6a3dadb756c`）；`methodology.md` `a68d3946cff311abcae2f22a68abf5daf7b3a70b14d7acd004993a0a2896ab1c`；`acceptance_checklist.md` `2bc97defd27b044925d352e7c6f030d314331b7215340245c7dc588d9af92473`。
- 回报文件 `docs/superpowers/reports/2026-10-03-ds-D4.md`，sha256 `a929144bae27edd463876119dd8c4c8aeb0a04a628f947cf89472e298eae7e3d`。

没做或未通过：
- **`factor_catalog.csv` 只生成过 fixture 版本，没有真实版本**（服务器还没跑，真实因子状态只能是 `not_run`）；没有造假目录充数。
- `methodology.md` 与 `acceptance_checklist.md` 中依赖真实结果处仍为空/未勾选，只按已实现机制与已确认事实更新。

需要Sam决定：三项口径（切分/复权/候选数）必须裁定；`candidate_list.csv` 谁提供；扰动变体接口是否由 Hermes 提供。

下一步：D5

开始时间：2026-10-03 22:39　完成时间：2026-10-03 22:52　实际用时：约 13 分钟

---

## 子页 7：DS回报｜10-03 23:02｜D5 互查（阻塞）

【回报】DS（单位电脑）｜D5 互查｜2026-10-03 23:02

状态：**部分完成 / 被外部依赖阻塞**（互查工具已做完并验证；Hermes 真实 OOS 结果未回传，实际不一致项清单为空）

做了什么：
- **写了独立互查工具** `scripts/cross_check_delivery.py`：不信任 manifest，**自己重算所有哈希**并逐项对齐。
- 重算：面板/因子文件/候选清单/配置文件 sha256、每个因子 `validation_result.json` 的规范化 `result_hash`、每个产物 sha256、`code_commit` 格式。
- 对齐：manifest 的 counts 与通过/淘汰/报错清单 vs `results` 逐条状态；`candidate_count`/`factor_ids` vs 候选清单；`batch_summary.csv`；`factor_catalog.csv`；`package_manifest.json` 收录集合 vs 真正 `validated` 集合与包内文件一致性。
- 报告 vs 结果对齐：报告首行 `status=`、门槛表行、RankIC 表每行 mean/IC_IR/t-stat/days。
- 退出码：`0` 无不一致；`5` 有（逐条列出 scope/check/expected/actual）；`2` 输入缺失。
- **全链路彩排跑通**：`validate-batch`(3) → `build_factor_catalog`(0) → `package_delivery`(**4**) → `cross_check`(**0 个不一致**)；命令顺序写进 runbook 第 5.3 节。
- 修掉我自己的一个真 bug：result JSON 用 `sort_keys=True` 写，键顺序与报告不同，原来按顺序比 RankIC 行会误报；已改为顺序无关并加比数值。

证据：
- commit `47b3c7c`（工具）、`30149d7`（runbook）。
- 新增 `research_core/factor_lab/cross_check.py`、`scripts/cross_check_delivery.py`、`tests/test_only_cross_check.py`；修改 `docs/delivery/runbook_hermes.md`。
- 全量：`pytest tests -q` → **138 passed / 3 failed**（D4 前 129；新增 9）。
- **故意造错验证互查能抓到**（7 个反向用例全过）：干净夹具 0 条；篡改结果数值 → 抓到 `result_hash` + 产物 sha256 + `report_rank_ic_values`；篡改汇总行 → `summary_status`；改 counts/清单 → `counts` + `factor_list`；换掉面板文件 → `panel_sha256`；目录状态写错 → `catalog_status`；**包里混进淘汰因子 → `package_included`**。
- 产物 sha256：`cross_check.py` `64d9029155515886881a231cdfd38225893277f63325f8cdf11145ad3dec8686`；`cross_check_delivery.py` `ec372ae943914805cd6da9293c4633bcc35003e5d7e780c0daaa293a5bce38b6`；`test_only_cross_check.py` `f64931a549d81a87fc5331800dca8ecb59fbc26141aa33533fb59908a92bb1f3`；`runbook_hermes.md` `eed0136997bed7939b05753cded064f31d30c8e332466c849ccc238c901ba02e`。
- 回报文件 `docs/superpowers/reports/2026-10-03-ds-D5.md`，sha256 `7514422e8f83d85456698731bdd968b6ec5c86b8378aa59e8d90df15cb7fa957`。

没做或未通过：
- **D5 实质结论做不了**：Hermes 还没在 115 服务器跑 OOS，无法核对真实 hash、因子数与通过/淘汰清单。
- 没有真实面板/因子文件，凡依赖真实文件的检查项只用合成夹具验证过逻辑。
- 推送受网络影响（当晚 GitHub 反复断，重试若干次才成功）。

需要Sam决定：促 Hermes 跑一次并回传（runbook 5.3 节末尾有清单）；三项口径；`candidate_list.csv`；扰动变体接口。

下一步：等 Hermes 回传后重跑 D5。

开始时间：2026-10-03 22:53　完成时间：2026-10-03 23:02　实际用时：约 9 分钟（按会话时间戳重建）

---

## 子页 8：DS回报｜10-03 23:12｜D5 前置加固

【回报】DS（单位电脑）｜D5 前置加固｜2026-10-03 23:12

状态：完成（D5 阻塞期间的加固轮，不是 D5 本身的结论）

做了什么（为什么做这轮：`git fetch` 确认远端仍只有三个分支、没有结果、没有 `candidate_list.csv`；本机 8G 内存/空闲 1G/双核，压测结论不可外推，所以转做不依赖外部的事）：
- **切分口径取证**：`validation_gates.yaml` 只有 `61dcf19`（建文件）与 `cf9c883`（只加 `reversal_1m`）两个 commit；`git log -S'train_end'`、`-S'adjust_type'` 都只命中 `61dcf19` → 切分与 `adjust_type: post` 自建库起从未变过；全仓搜 `2022-12-31` **零命中**；没有任何测试写死生产切分 → **改它不破坏测试**，纯口径决定。写进 `pipeline_cf9c883_notes.md` 第 7 节与 `changelog.md`。
- **预计算通道抗脏数据加固**：新增 ① 脏面板等价性（停牌日、涨跌停锁定、1 只全年 ST、1 只次新上市、1 只中途退市；先断言过滤真的生效，再断言两条通道结果逐字节相同）；② 缺行不被填补（删掉 3 只股票的因子行后，覆盖率跌破 0.95、第一条失败门槛就是 `coverage`、被删股票零出现）。

证据：
- commit `fab428d`（测试）、`3a2e013`（取证文档）、`d7d6fac`（回报）；HEAD `d7d6fac0cfb24d06e9c40f654b8222e3a3009df7`，本地=远端。
- 改动：`tests/test_only_precomputed_factors.py`、`docs/delivery/pipeline_cf9c883_notes.md`、`docs/delivery/changelog.md`。
- 全量：`pytest tests -q` → **140 passed / 3 failed**（本轮前 138）；预计算专项 **22 passed in 133.37s**。
- 未动 `configs/validation_gates.yaml`：切分与门槛一个字节没改，取证只写进文档。
- 回报文件 `docs/superpowers/reports/2026-10-03-ds-D5b.md`，sha256 `d5c5fb21a93725575334c176a3ec647474eb53d1df91a9f0b1875180e024ba61`。

没做或未通过：
- D5 实质结论仍未产出（无真实产物）。
- 真实全 A 耗时与内存仍是未知，只能由 115 服务器实测。

需要Sam决定：切分（代码事实 `2023-12-31/2024-01-01` 起于 `61dcf19`，任务书 `2022-12-31/2023-01-01` 仓库零记录，请指定以哪边为准）；复权；候选数；`candidate_list.csv`；扰动变体接口；促 Hermes 开跑并回传。

下一步：等 Hermes 回传后跑 D5 互查。

开始时间：2026-10-03 23:03　完成时间：2026-10-03 23:12　实际用时：约 9 分钟（按会话时间戳重建）
