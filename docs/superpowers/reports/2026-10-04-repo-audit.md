# 仓库审计：冲突内容 · 现有能力 · 缺失项

【回报】DS（单位电脑）｜仓库审计 + 文档同步｜2026-10-04 21:00

对象：`AgentMatrixLab/agentmatrix-research`，审计时 `main = d3ab4e8`。所有结论都带文件:行号或命令证据；标「推断」的地方是未经运行验证的判断。

## 〇、本轮顺带完成的事

- **PR [#123](https://github.com/AgentMatrixLab/agentmatrix-research/pull/123) 已合并**（`main` 现为 `d3ab4e8`）：把 `delivery/2026-10-07` 上剩余 3 个纯文档提交（PR #121 合并记录、Notion 记录、四面板恢复记录）同步进 main。合并前 `git merge-tree` **双向预演零冲突**；合并后 **delivery 独有提交 = 0**，两个分支完全对齐。
- **把我自己写的服务器地址脱敏**：`2026-10-04-portal-restore.md` 里原本复述了数据服务器公网地址，已改为占位符（具体见下面「安全类」）。

## 一、冲突 / 矛盾 / 风险内容

### A. Git 层面（无阻塞）

| 项 | 状态 |
|---|---|
| 工作区未解决的冲突 | **无**（`git status` 干净） |
| `delivery/2026-10-07` ↔ `main` | **已同步**（delivery 独有提交 0；main 独有 3 个 = PR #121/#122/#123 的合并提交） |
| 未合并远端分支 | **12 个**：其中 **9 个与 main 有冲突**、2 个能干净合（`patch-2`/`patch-4`，但落后 117 个提交、内容已被后续重构覆盖）、1 个封存（`parked/factor-db-api-2026-10-03`，未动） |
| 含独有提交最多者 | `feat/factor-infra-v2`（**41** 个独有提交、与 main 冲突）→ 删不得，需原作者确认废弃后走「打 tag 再删」 |

### B. 内容矛盾（真正要处理的三类）

**B1. 切分口径：现行值已变，但两份文档还写着「未裁定」+ 旧值** ⚠️

- **现行事实**（`configs/validation_gates.yaml`，commit `146c0d7`）：train `2020-01-02~2022-12-31` / OOS `2023-01-01~2026-08-31`。
- `docs/delivery/changelog.md:8` 仍写「**切分口径未裁定**：config 写的是 train `2016-01-01~2023-12-31`…」→ 与现状矛盾。
- `docs/delivery/pipeline_cf9c883_notes.md:110` 同样写「config 是 `2016-01-01~2023-12-31`」→ 已过期。
- `docs/superpowers/reports/2026-10-03-ds-D1.md:28`、`-D2.md:32`、`-D3.md:34` 是**历史回报**，保留原值合理，但应加「已过期，见 E1」标注。
- 影响：读文档的人会以为切分还没定，或按旧切分理解已跑的结果。

**B2. 候选数三个数字并存**

- `91`（现行裁定，134−43，含 10 个风险暴露；有效 Alpha 81）—— `methodology.md:12-13`、`acceptance_checklist.md:9` 已对齐。
- `134`（G2 剔除前的总数）—— 作为推导来源保留，`runbook_hermes.md:205` 已注明「对外不写 134」。
- **`89`**（旧的 G2 口径：134−45）—— 出现在**另一个仓库** `samzhang8/model` 的 `factor_catalog.html` 上，且那页还写着**旧切分** `2016-01-01~2023-12-31`。→ 对客/审阅时极易混。
- 本仓 `changelog.md:11` 仍把「91 vs 134」列为「不一致待查」→ 与已裁定的事实不符。

**B3. 门户第 4 张卡的口径容易被误读**

- `pages/index.html` 第 4 张卡写「**1058 因子检索**」，而本期交付口径是 **91 候选**（有效 Alpha 81）。
- 这两者**不是同一件事**（1058 = Factor DB 目录规模；91 = 本期价量候选），但同页并列没有说明，容易被当成交付数量。
- 建议：卡片上加一行口径注释，或改成「因子库目录（历史目录 1058，本期交付候选另见交付说明）」。

### C. 安全类（按紧急度）

**C1.（已在 2026-10-04 闭环，保留原始记录）公开仓库里 8 个 tracked 文件明写数据服务器公网地址** ⚠️⚠️

> **现状**：PR #125（脱敏 9 个文件）+ PR #126（补 `data_manager.py` 的服务器路径、新增 `tests/test_only_no_baked_in_hosts.py` 守卫）已合并，`main` 当前树 **0 命中**。守卫会阻止地址/token 再被写回。
> **仍待人工完成**：① 在服务器上**轮换曾暴露的 admin token**；② 服务器访问加白名单。历史里旧值仍在（18 个提交含地址、4 个含 token），且 8 个 fork 持有旧对象；经决策**不重写 git 历史**。详见 `2026-10-04-redaction-and-branches.md`。

含 `http://<数据服务器>:8765` 字面量的文件（全部已在 `main`、仓库为 **public**）：

| 文件 | 处数 |
|---|---|
| `.trae/skills/quant-api-v2/SKILL.md` | 5（含「API 公网地址」「服务器 Ubuntu 24.04」） |
| `docs/FACTOR_LAB_QUANT_API_BACKEND.md` | 2 |
| `research_core/data_loader/clickhouse_loader.py` | 2 |
| `research_core/data_loader/quant_api_client.py` | 1 |
| `strategy_panel/engine/config.py` | 1 |
| `strategy_panel/engine/daily_pipeline.py` | 1 |
| `strategy_panel/README.md` | 1 |
| `docs/integration/PROGRESS.md` | 1 |

建议（需 Sam/Patric 拍板，我未擅自改）：全部改为从环境变量读取，并在文档里用占位符；如需彻底清除历史，还要处理 git 历史（成本较高，可先做「当前树脱敏 + 服务器侧换 IP/加白名单」）。

**C2. 另一个仓库的密钥泄露（上一轮已报，仍未处理）**：`samzhang8/model`（public）的 `docs/api_keys.json` 键名即一个 `fa_` 开头的 key id，`docs/api_billing.jsonl` 每行还有 `key` 字段；建议轮换 key 并移出仓库。

**C3. 前端门禁密码硬编码**：`pages/lifecycle-dashboard/app.js:9`、`pages/factor-db-dashboard/app.js:24`、`pages/lifecycle-dashboard/index.html:140` 里 `ACCESS_PASSWORD` 默认值 `factorlab2026`。这是 2026-08-30 上线时就公开过的设计（页面明写「只做前端门禁，真实权限由后端/RLS 控制」），但既已重新公开，建议改后端校验或撤掉门禁。

**C4. 本仓无密钥文件**：`git ls-tree` 未发现 `api_keys*` / `.env` / `credential*`；全仓扫 `sk-`/`ghp_`/`ntn_`/`AKIA` 形态字面量 **0 命中**（这是本仓与 `samzhang8/model` 的关键差别）。

### D. 其他不一致 / 过期内容

- `docs/FACTOR_LAB_CLOUD_DEPLOYMENT.md`：写 `https://miao050805-arch.github.io/...`（该账号已改名为 `theomiao6`，链接现为 **404**，实测）与 `factor-lab-api.onrender.com`（云后端，状态未知）→ 过期文档，建议标注或改指向组织主入口。
- `docs/FACTOR_LAB_ARCHITECTURE_FRAMEWORK.md` 与 `docs/FACTOR_LAB_ARCHITECTURE_V2.md` **并存**，需确认哪份是现行（推断：V2 为现行）。
- 每次本机全量测试固定出现「**3 failed**」（`tests/test_backtest_jobs.py` 清理临时 `jobs.db` 的 Windows 占用），Linux CI 不触发；但容易被人误读成回归，建议加 skip 标注或平台守卫。
- 本地存在 `research_core/**/__pycache__/*.pyc`（未被 tracked，无影响）。

## 二、当前仓库能实现的功能（有代码 + 有测试支撑）

### 1. 因子验证流水线（交付主线）

- **单因子确定性验证**（`cf9c883` + 我加的通道）：全 A 准入过滤（上市满 120 天、未退市、非 ST、非停牌、`volume>0`、价格未触涨跌停）→ 训练/样本外切分 → **8 道门槛**（coverage / rank_ic / oos_seal / style_r2 / residual_ic / cost_adjusted_return / dd_vol_ratio / parameter_perturbation）→ 成本模型（佣金 1.5bp/边 + 印花税 10bp 卖出 + 冲击 8.5bp/边，往返 0.003）→ 产出 `validation_report.md` / `validation_result.json` / `run_manifest.json` + `result_hash`。
- **两条因子来源**：内置 transform（`negative_pct_change`、`rolling_mean`、`rolling_mean_log`）+ **预计算因子长表 Parquet**（含扰动变体 `<id>|window=<w>`）；两条通道对同一因子必须给出**相同 `result_hash`**（有等价测试）。
- **本地面板通道** `--panel-file`：sidecar 校验 SHA-256/列/类型/`(date,code)` 唯一/日期区间/行数，不符即报错。
- **分段** `--segment train|oos`：train 只出训练期指标、**完全不碰 OOS**（用于选簇代表）。
- **批量** `validate-batch`：一条命令跑完候选清单，单因子失败记原因并继续；批量 `batch_manifest.json` 汇总。
- **并行分片**：按因子拆片 → `merge_batch_manifests.py` 合并，硬校验各片 commit/面板/因子文件/配置哈希/切分一致、因子不重叠，不一致拒绝合并；合并只拼接结论不重算判定。
- **交付物件**：`factor_catalog.csv` 生成（未跑的一律 `not_run`）、只收 `validated` 且 `risk_exposure=false` 的打包（空包以退出码 4 拒绝出包）、`cross_check_delivery.py` 独立重算全哈希并逐项对齐。

### 2. 研究与策略栈（既有）

`research_core/` **15 个子包**：`factor_lab`(50 个 .py)、`backtest_adapter`(23)、`strategy_engine`(16)、`data_loader`(12)、`qlib_lab`(10)、`factor_library`(9)、`strategy_operations`(7)、`factor_lab_web`(5)、`strategy_analytics`(5)、`backtest_jobs`(3)、`attribution_engine`(2)、`strategy_dashboard`(2)、`risk_rule_engine`(1)、`dataset_builder`(1) 等。
`backend/` **10 个模块**：`factor_lab_api`、`strategy_dashboard_api`、`backtest_service`、`factor_library_service`、document normalizer、mineru runtime 等。
`scripts/` **34 个脚本**（含我新增的 4 个交付脚本）。

### 3. 门户与展示

- 四卡片门户（已恢复，线上实测 5 个 URL 全 200）：**Factor Lab 看板**（读 Supabase，实时）、**因子生命周期监控**（静态快照，40 因子）、**策略面板**（静态快照，5 策略）、**因子库目录**（静态快照，1058 因子）。
- 另有 `frontend/`（factor-lab-dashboard、quant-desk-react）、`prototypes/`（teammate-quant-desk）。

### 4. 质量与自动化

- **测试**：25 个测试文件、**156 个用例**（153 passed / 3 已知失败）。
- **CI**：4 个 workflow（Factor Validation、PR Hygiene、Deploy GitHub Pages、Deploy Factor Lab Dashboard）。
- **main 保护**（ruleset `protect`）：禁止删除、禁止强推、必须走 PR、**需要 0 个批准、无必需状态检查**。

## 三、缺失 / 不够完善（按优先级）

### P0 —— 直接阻塞 10/7 交付

1. **没有任何真实数据结果**：`candidate_list.csv` 未到、Hermes 未跑彩排/全量 → 「通过哪些因子」为空。这是唯一的实质性交付阻塞。
2. **真实全 A 的单因子耗时与峰值内存未知** → 串行还是并行、要几路，无法排期。

### P1 —— 影响结论的严谨性（建议交付前明确口径）

3. **基准 `000985` 完全没有被门槛使用**：全仓 `000985` 只出现在 `research_core/data_loader/rqdata_panel.py`（契约校验），`deterministic_validation.py` 里 `benchmark|excess|industry` **0 命中**。→ 现在评的是**绝对多空收益**，**没有相对基准的超额收益**，成本门槛也是拿净值对 0 比较。
4. **没有行业中性化**：风格回归只覆盖 size / momentum / volatility / liquidity，代码里没有行业字段或行业哑变量。`samzhang8/model` 的因子面板自己也标注「未扣行业/市值暴露，IC 可能系统性偏高」。
5. **原生 transform 只有 2 类** → ROC / RSI6 / alpha002 等必须走预计算通道（通道已建，但完全依赖 Hermes 的导出规范与扰动变体）。
6. **扰动门槛对「无窗口因子」只能记「无法测量 → 不通过」** → 这类因子在当前门槛下**永远无法通过**（是裁定 A+B 的直接后果，需 Patric/Sam 确认是否接受）。
7. **`turnover_rate` 缺失时自动降级为 `avg_amount_log`**（有 `fallback_reason` 记录）→ 批量结果里容易把 fallback 当原因子读。

### P2 —— 工程与安全

8. **8 个文件公开了数据服务器地址**（见 C1）→ 建议脱敏。
9. **前端门禁密码硬编码**（C3）。
10. **每次全量测试固定 3 failed**（Windows 特有问题）→ 建议加平台 skip，避免淹没真实回归。
11. **9 个与 main 冲突的过期分支 + 2 个已过期可删**→ 需原作者确认废弃，再打 `archive/*` tag 清理。
12. **CI 覆盖不全**：`Factor Validation` 只跑 `research_core/factor_lab/` + `tests/`；新增的 `scripts/`（交付脚本）与 `pages/**`（门户）没有测试覆盖。
13. **`docs/delivery/methodology.md` 与 `acceptance_checklist.md` 仍是草稿**（等真实结果）；`changelog.md` 的两处「未裁定」表述需按现行裁定更新（见 B1/B2）。
14. **Factor DB 平台封存** → 第 4 张卡只有静态快照、**无实时检索后端**；`strategy-dashboard` 的生成脚本因含服务器地址被排除，数据只能手工更新（推断）。

## 四、建议的下一步（按性价比排序）

1. **（10 分钟）文档口径对齐**：把 `changelog.md` 第 8/11 行的「未裁定」改成现行裁定结果；给 3 份历史回报加「已过期」标注；给门户第 4 张卡加口径注释。→ 我可以立刻做，走 PR。
2. **（30 分钟）服务器地址脱敏**：8 个文件改为环境变量/占位符（需你确认，尤其是 `.trae/skills/**` 与 `docs/integration/PROGRESS.md`）。→ 我可以做，但**需要你点头**，因为会改到别人的文档。
3. **（交付主线）催 Hermes 跑彩排 + 全量**，我这边做 D5 互查。
4. **（交付前口径）确认基准与行业中性**：如果客户期望的是「相对 000985 的超额」或「行业中性后 IC」，现行门槛**不满足**，需要先定口径再跑，否则跑完也要重跑。
5. **（清理）** 过期分支打 tag 归档、3 个测试失败加平台 skip、CI 覆盖扩到 scripts/。
