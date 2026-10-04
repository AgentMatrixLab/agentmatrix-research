# 2026-10-07 交付执行手册（Runbook）

> 配套：[系统规划](2026-10-07-system-plan.md)、[决策单](2026-10-07-open-questions.md)、[打分卡](2026-10-07-scoring-card.md)、[方法学](methodology.md)
> 所有命令都已在本机验证过（合成数据端到端彩排 + 分片合并验证）。**带 ⛔ 的步骤必须先拿到口径签字或凭据。**

---

## 0. 当前状态（一眼看）

| 环节 | 状态 | 证据 |
|---|---|---|
| 因子目录 | 1058 条 | `pages/factor-db-dashboard/data/factors.json` |
| 引擎可算 | **952 / 1058（90.0%）** | `scripts/build_factor_panel.py` |
| 真实验证运行 | **0 份** | `data/factor_lab/validation_runs/` 不存在 |
| 端到端链路 | ✅ **已彩排通过** | `scripts/dev/rehearse_full_pipeline.py` |
| 分片并行 | ✅ **已验证（含两条拒绝路径）** | `scripts/dev/verify_sharded_batch.py` |
| 打包 + 交叉核对 | ✅ **已验证（含篡改检测）** | `scripts/dev/verify_delivery_packaging.py` |
| 验证器吞吐 | ⚠️ **27 秒/因子**（实测） | `scripts/dev/benchmark_validator_throughput.py` |
| 测试 | ✅ **434 passed / 0 failed** | `python -m pytest tests -q` |

> **除「真实数据」与「口径签字」外，全链路每一段都已端到端验证过。**

---

## D0 · 10/5（周一）—— 口径冻结 + 数据落地

### 0.1 ⛔ 口径冻结会（上午，第一个小时）

必须先拿到签字，否则后面全部要重跑。需要拍板：

- **Q1**：300 的口径（已选 C：按相关性簇组织）；**仍需** 相关性阈值（默认 0.7）+ 核心集数量（建议 60–120）
- **Q2**：基准（000985 / 沪深300 / 中证500 / 中证1000 / 客户指定）+ 行业分类标准（申万 / 中信 / RQData）+ 中性化做法
- **Q10**：FDR 是「必要条件」还是「分层加分维度」。**这是对 300 目标威胁最大的单项**
- **Q4**：打分卡权重与 A 层分数线（55 分）

> 签字后写进 `docs/delivery/2026-10-07-open-questions.md` 的「已确认」表，**当天不再改**。

### 0.2 服务器导出（上午）

```bash
# 在 115 服务器，conda env: rqsdk
conda activate rqsdk

# ① 30 秒 API 体检 —— 先跑这个，别直接拉全量
python -X utf8 scripts/export_rqsdk_panel.py --probe
#    它会用 3 只票 1 天把每个 RQData 调用试一遍，报告哪个字段/权限有问题

# ② 正式导出（扩展面板 + 基准 + 指数成分）
python -X utf8 scripts/export_rqsdk_panel.py \
    --out-dir /data/amr/export --start 2015-01-01 --end 2026-08-31 \
    --batch-size 300

# ③ 自检（不联网，用仓库自己的加载器校验）
python -X utf8 scripts/export_rqsdk_panel.py --out-dir /data/amr/export --self-check
```

**必须确认的产出**：`validation_panel.parquet` 有 **7 个扩展列**（`open/high/low/pre_close/vwap/total_shares/industry`）、`price_basis=post_adjusted`、涨跌停命中率合理性检查通过。

> 若涨跌停命中率被判定不合理，脚本会**拒绝声明成功并退出码 2** —— 那是口径混用的信号，必须查清再往下走。

### 0.3 ⚠️ 单因子耗时实测（上午，定排期的唯一依据）

拿到面板后**立刻**测一次，不要等全量跑完才发现来不及：

```bash
# 本机（或服务器）上，挑 3 个因子跑一次计时
python -X utf8 scripts/dev/benchmark_validator_throughput.py --keep
```

实测基线：**约 27 秒/因子**（3000 个交易日）。据此定分片数：

| 实测秒/因子 | 913 因子 × 8 核 | 913 因子 × 16 核 | 建议 |
|---:|---:|---:|---|
| 27（下限） | 0.9 h | 0.4 h | 8 核足够 |
| 60 | 1.9 h | 1.0 h | 8 核足够 |
| 124（拟合上限） | 3.9 h | 2.0 h | 16 核，并考虑收窄候选池 |

**若实测 > 90 秒/因子且核数 ≤ 8** → 启动备用方案：候选池收到 400–500（按来源分族取头部），先保 300。

### 0.4 因子值计算（下午，本机）

引擎已能算 90% 的目录，**因子值在本机算，不需要服务器导出**：

```bash
# 在仓库根目录，用扩展面板跑引擎（具体入口见 FACTOR_LAB_ALPHA101_WORKFLOW.md）
# 产出必须是长表 Parquet：date, code, factor_name, value
#   带窗口的因子同时给 <id> 与 <id>|window=<0.8x> 与 <id>|window=<1.2x>
```

### 0.5 分片并行跑训练段（晚）

```bash
# ① 把 candidate_list.csv 切成 N 片（N = 核数）
#    每片自己的 --output-dir，但 --panel-file / --factor-file / --config 必须完全相同
python -X utf8 -m research_core.factor_lab.cli validate-batch \
    --candidates shard0/candidate_list.csv \
    --config configs/validation_gates.yaml \
    --panel-file data/factor_lab/panel.parquet \
    --factor-file data/factor_lab/factors.parquet \
    --segment train \
    --output-dir data/factor_lab/batches/shard0
# ② ... 各片并行（nohup / xargs -P / 作业系统）
# ③ 合并
python -X utf8 scripts/merge_batch_manifests.py \
    --shards data/factor_lab/batches/shard*/batch_manifest.json \
    --output-dir data/factor_lab/batches/merged
```

> **合并会拒绝不一致的分片**（面板哈希/配置哈希/切分不同、因子重复），退出码 2。这是刻意的，不要绕过。
> **选簇代表只能用 `--segment train` 的输出**，禁止看 OOS。

---

## D1 · 10/6（周二）—— 全量 OOS + 打分 + 策略

### 1.1 分片并行跑全量 OOS

同上，把 `--segment train` 换成 `--segment oos`。**预计小时级，早上开跑。**

### 1.2 追加稳健性层

```bash
python -X utf8 scripts/run_robustness_supplement.py \
    --runs-dir data/factor_lab/validation_runs \
    --panel-file data/factor_lab/panel.parquet \
    --factor-file data/factor_lab/factors.parquet \
    --out data/factor_lab/supplementary_report.json \
    --q 0.05
```

产出 `supplementary_report.json` + `.md`：逐因子双侧 p 值、BH-FDR 结果、行业中性留存、**以及「校正的代价」**（多少因子被多重检验拦下）。

> **健康检查**：若报告里 `n_tested = 0`，说明 rank_ic 键格式又对不上了（曾出过这个 bug），**立刻停**。

### 1.3 策略演示集（四个变体 + 样本外结果）

```bash
python -X utf8 scripts/build_strategy_demos.py \
    --panel-file data/factor_lab/panel.parquet \
    --factor-file data/factor_lab/factors.parquet \
    --runs-dir data/factor_lab/validation_runs \
    --out-dir data/factor_lab/strategy_demos
```

四个变体：`top_composite` / `cluster_core` / `single_best` / `all_passers`。
输出 `data_status = real_run`。**若输出写的是 `synthetic_rehearsal`，说明拿错面板了。**

### 1.4 交叉核对与打包

```bash
# ① 打包：只收 status == "validated" 的因子
python -X utf8 scripts/package_delivery.py \
    --batch-manifest data/factor_lab/batches/merged/batch_manifest.json \
    --candidates data/factor_lab/candidate_list.csv \
    --output-dir data/factor_lab/package

# ② 交叉核对：独立重算全哈希，不信 manifest
python -X utf8 scripts/cross_check_delivery.py \
    --batch-manifest data/factor_lab/batches/merged/batch_manifest.json \
    --panel-file data/factor_lab/panel.parquet \
    --factor-file data/factor_lab/factors.parquet \
    --candidates data/factor_lab/candidate_list.csv \
    --config configs/validation_gates.yaml \
    --package-manifest data/factor_lab/package/package_manifest.json \
    --output data/factor_lab/cross_check.json
```

**退出码含义**（不要忽略）：

| 脚本 | 码 | 含义 |
|---|---|---|
| `package_delivery.py` | 0 | 出包成功 |
| | **4** | **一个因子都没通过 → 拒绝出空包**。这是正确行为，不是故障 |
| `cross_check_delivery.py` | 0 | 无不一致 |
| | **5** | **发现不一致** —— 停下来查，不要签收 |
| | 2 | 输入有问题，无法核对 |

**这条路径已端到端验证**（`scripts/dev/verify_delivery_packaging.py`）：

| 检查 | 结果 |
|---|---|
| 分片 → 合并 → 打包 | ✅ included=2 / excluded=10 |
| 打包内容**恰好等于** validated 集合 | ✅ |
| **每一条被排除的因子都带原因** | ✅ |
| `factor_catalog.csv` 行数 = 批次因子数 | ✅ |
| 干净包上跑交叉核对 | ✅ 退出码 0 |
| **篡改包内证据后再核对** | ✅ **退出码 5，并指名具体因子与检查项** |

---

## D2 · 10/7（周三）—— 信号 + 对账 + 交付

### 2.1 生成实盘信号

```bash
# 用 strategy_demos 的目标权重产出：
#   · 文件单 CSV（UTF-8 BOM，Excel/QMT 可直接读）
#   · 条件单 JSON（显式 trigger_price，可无人值守）
#   · Supabase 行（(strategy_id, trade_date, code) 唯一，重复推送幂等）
```

两条口径写死在代码里：**取整永远向下**（不足一手丢弃，不向上取整）；**滑点正值一律表示更差**。

### 2.2 执行对账

拿本地 QMT / 掘金量化的成交回报跑 `reconcile_execution`，产出：

- 未成交 / 计划外成交 / 数量不符 / 价格滑点 / 成交比例
- 结论：**无偏差** 或 **存在偏差**

**「无偏差」的判定标准需要客户先定义**（成交价差容差？数量容差？时点？）—— 见决策单 Q6。

### 2.3 交付

```bash
python -X utf8 scripts/build_factor_panel.py     # 刷新因子作战面板
```

面板的交付漏斗会显示真实数字：目录 → 引擎可算 → 已送验 → 过闸 → 已评分 → 进策略 → 实盘在线。

---

## 3. 健康检查清单（每步之后扫一眼）

| 检查 | 不通过说明什么 |
|---|---|
| `validation_panel.parquet` 有 7 个扩展列 | 导出脚本没按扩展契约跑，ALPHA158/360 大部分算不了 |
| 涨跌停合理性检查通过 | `close` 与 `limit_up` 口径可能混用，**不要拿这个面板做验证** |
| `supplementary_report.json` 的 `n_tested > 0` | rank_ic 键格式对不上（历史 bug），FDR 层在静默空转 |
| 合并退出码 0 且因子总数 = 各片之和 | 分片输入不一致或因子重复 |
| `strategy_demos/strategies.json` 的 `data_status = real_run` | 拿错面板了 |
| `package_delivery.py` 退出码非 4 | 退出码 4 = 一个因子都没通过，**不要误发空包** |
| `python -m pytest tests -q` 全绿 | 434 passed 是当前基线 |

---

## 4. 已知风险与备用方案

| 风险 | 触发条件 | 备用方案 |
|---|---|---|
| **数据迟到** | 10/5 中午前没拿到面板 | 用 `samzhang8/model` 已下载的 300 条作备选；或与客户协商延期 |
| **吞吐不够** | 实测 > 90 秒/因子且核数 ≤ 8 | 候选池收到 400–500 优先集，先保 300 |
| **300 达不成** | 过闸数 < 300 | ① 纳入月频族扩大分母；② 从 10443 条 RQData 目录增补；③ 与客户协商「过闸 + 高潜力候选」口径 |
| **FDR 过严** | Q10 选「必要条件」 | 三个选项都已实现（`supplementary.py` 的 `q` 参数），改一个开关 |
| **口径变更** | 冻结会后又改基准/行业 | 10/6 跑完要重跑。**签字后不要改。** |

---

## 5. 一句话总结

**除「真实数据」和「口径签字」外，交付所需的全部工程能力都已就绪且验证过。** 拿到这两样东西后，按本手册顺序执行即可。
