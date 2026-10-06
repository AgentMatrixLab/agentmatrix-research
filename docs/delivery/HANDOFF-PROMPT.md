# 晨星 300 因子交付 · 完整交接 Prompt

> 用途：把下面 **「交接正文」** 整段复制到 Notion，或作为新对话窗口的第一条消息。它是自包含的——接手方不需要本对话的任何上下文。

---

# 交接正文（从这里开始复制）

## 一、任务是什么

为**晨星基金排名公司**交付 **≥300 个可上线实盘因子**，截止日 **2026-10-07**。除因子本身外还要求：严格检测与验证（体现验证器与打分卡的合理性）、多个实盘可用策略作演示 + 样本外结果、具体实盘信号（文件单 / 条件单 / Supabase 行，供本地 QMT 或掘金量化对照执行偏差）。

**本项目已于 2026-10-06 21:35:51 完成并交付：332 个因子，23 项验收全部通过。** 交付比截止日提前一天多。

## 二、最终结果（已交付，勿重复劳动）

| 项 | 值 |
|---|---|
| **进入交付包（通过全部八道冻结门槛）** | **332**（目标 300，余量 32） |
| 交付清单 | 849 行（全部授权候选）：通过 332、拒绝 160、未评估 357 |
| 排序优先档（tier S/A，**仅排序、不是门槛**） | 260 |
| 冗余聚类 | 50 簇 / 50 个代表（低相关核心集） |
| FDR 勋章 | 479 / 492 通过（q=0.05），`lost_to_correction: 0` |
| 交叉验证 | **`finding_count: 0`**（492 个 result_hash 及全部产物独立重算） |
| 23 项验收 | **全部通过**（`acceptance_exit=0`） |
| 实盘信号 | 文件单 49 笔（UTF-8 BOM，QMT 可直导）、条件单 49 笔、Supabase 行 49 条 |
| 分片进度 | **123 / 213 片**（按「通过数 ≥330」分支提前停止，未跑满） |
| 归因提交 | `71760b4138e350338299a6f48f269099ebbfab5c`（40 位，已写入各分片 manifest） |

**样本外策略结果**（2023-09-28 ~ 2026-08-31，含成本；等权全市场基准 **+42.42%**）：

| 变体 | 累计 | 年化 | 超额 | 最大回撤 |
|---|---|---|---|---|
| **cluster_core（簇代表等权）** | **+84.12%** | 24.38% | **+41.70%** | **35.55%** |
| top_composite（前 50 复合分） | +62.05% | 18.83% | +19.63% | 40.01% |
| all_passers（全部通过者等权） | +54.77% | 16.90% | +12.36% | 40.81% |
| single_best（单因子） | −52.89% | −23.59% | −95.31% | 71.66% |

三个分散化变体全部跑赢基准。`single_best` 是**刻意保留的对照**，用来说明集中度风险，**不是可交付策略**。

**关键提醒**：74 因子彩排时 `cluster_core` 是**跑输**基准的；扩到 332 个因子后转为大幅跑赢。**这个改善来自因子覆盖面扩大，不是任何参数调整**。因子筛选全部由冻结门槛在训练段完成，策略构造方式事先固定，未在样本外调参。

## 三、口径（已确认，不要重新讨论）

| 事项 | 口径 |
|---|---|
| 什么算「可交付」 | **通过全部八道冻结门槛** 且 非风险暴露（`in_delivery_package`）；代码为 `passed and is_alpha` |
| 八道冻结门槛 | coverage、rank_ic、oos_seal、style_r2、residual_ic、cost_adjusted_return、dd_vol_ratio、parameter_perturbation；**只有 `residual_ic` 有实质过滤作用**（约 40–44%） |
| FDR（Q10） | **勋章**：`fdr_accepted` 列标注，**不参与**是否交付 |
| 打分卡 tier（Q4） | **排序**：用于排优先级，**不作门槛**。打分卡仍是草案 |
| 冗余组织（Q1=C） | 按相关性簇交付：代表 + 成员 + 簇内相关性；另附低相关核心集（= 簇代表集合） |
| 基准与中性化（Q2=C） | 基准超额 + 行业中性化残差 IC |
| 候选池（Q11） | 授权扩到 **849** 条（原冻结 91 条），**八道门槛一道未动** |
| 因子方向 | 取自冻结验证器的 `training.direction`（仅训练段测量） |
| 冗余相关性 | 逐日横截面 Spearman 的时间平均 |
| 基准 | 全市场等权日收益指数 |

**硬约束（必须继续遵守）**：`configs/validation_gates.yaml` 与 `research_core/factor_lab/deterministic_validation.py` **冻结，不得修改门槛**；新增层必须是**叠加式**的，且**不得被冻结验证器 import**（有结构性测试保证）。

## 四、东西在哪里

**服务器**（Ubuntu，16 核 / 62 GB，共享机；SSH 115，凭据在本地 `secrets/server-access.txt`，已 gitignore）：

```
/home/data/agentmatrix_run/                 # 运行根
├── agentmatrix/                            # 代码仓库（部署副本）
├── delivery/                               # ★ 交付产物
│   ├── delivery_manifest.csv               # 25 列冻结顺序的主交付表
│   ├── delivery_manifest.summary.json
│   ├── supplementary_report.json/.md       # FDR 勋章 + 行业中性留存
│   ├── strategy_demos/                     # strategies / backtest_results / clusters.json
│   ├── live_signals/                       # file_orders.csv / conditional_orders.json / supabase_rows.json / signal_summary.json
│   ├── package/                            # ★ 可审计包：factors/<id>/ 逐因子证据（带 sha256）+ factor_catalog.csv + package_manifest.json（含每个被排除因子的具体失败数值）
│   ├── cross_check.json                    # 独立重算结果
│   ├── merged_oos/                         # 合并后的批次判决
│   └── README.md                           # 由产物生成的交付说明
├── shards/shardNNN/                        # 各分片（oos/batch_manifest.json 表示完成）
├── delivery/values/parts/                  # 留存守护写入的因子值 part（每片一个）
├── runtime_mirror/data/factor_lab/validation_runs/   # ★ 证据镜像（评分与 FDR 读它）
├── logs/
│   ├── auto_deliver.done                   # ★ 一行裁决：chain_exit=0 acceptance_exit=0 in_delivery_package=332
│   ├── auto_deliver_acceptance.log         # 23 项验收逐条
│   ├── auto_deliver_chain.log              # 链全量输出
│   ├── auto_deliver.log / pool_watchdog.log
│   └── shardNNN.log                        # 每片的 build/train/oos 耗时与峰值内存
├── panel/validation_panel.parquet          # 9,444,457 行面板
├── candidate_list.csv                      # 849 个授权候选
└── delivery_dryrun/                        # ⚠ 并发 agent 留下的 38 GB（非本项目产物）
```

Python 解释器：`/home/data/conda-envs/rqsdk/bin/python`（3.11.15）。代码仓库本地工作区：`D:\agentmatrix`。

**本地仓库关键文件**：

```
scripts/dev/run_downstream.sh          # ★ 交付主链（11 步）
scripts/dev/auto_deliver.sh            # ★ 达标自动交付（阈值 330 + 三道前置检查 + 自动验收）
scripts/dev/stop_and_deliver.sh        # 人工交接（先停 watchdog 再停 pool，然后跑链）
scripts/dev/pool_watchdog.sh           # pool 死了自动拉起（按进程组检测，非模式匹配）
scripts/dev/run_pool.sh / run_one_shard.sh   # 分片驱动（含 oos flock 串行化）
scripts/verify_delivery.py             # ★ 23 项交付验收（只读）
scripts/reconcile_signals.py           # ★ 执行偏差对账（读文件单 + 成交回单）
scripts/build_delivery_readme.py       # 由产物生成交付说明（避免数字过期）
scripts/dev/ssh_run.py                 # SSH 执行（--put 上传、--file 跑脚本）
scripts/dev/recon/audit_deployed.py    # ★ 审计「服务器是否真的在跑 HEAD 的代码」
scripts/dev/recon/status.sh            # 一行看全：分片/通过/守护/资源/交付状态
docs/delivery/2026-10-07-execution-findings.md   # ★ 执行记录：6 类缺陷 + 每项实测数字 + 复现方式
```

## 五、怎么快速核实（不要凭信任）

```bash
# 1) 交付裁决（一行看全）
cat /home/data/agentmatrix_run/logs/auto_deliver.done
# → 2026-10-06T21:35:51+08:00 chain_exit=0 acceptance_exit=0 in_delivery_package=332

# 2) 23 项验收逐条
cat /home/data/agentmatrix_run/logs/auto_deliver_acceptance.log

# 3) 交付清单摘要
cat /home/data/agentmatrix_run/delivery/delivery_manifest.summary.json

# 4) 独立重跑验收（只读）
cd /home/data/agentmatrix_run/agentmatrix && export PYTHONPATH=$PWD
/home/data/conda-envs/rqsdk/bin/python -X utf8 scripts/verify_delivery.py \
    --delivery-dir /home/data/agentmatrix_run/delivery

# 5) 作业与资源全貌
bash /home/data/agentmatrix_run/agentmatrix/scripts/dev/recon/status.sh

# 6) 执行偏差对账（客户拿到成交回单后）
python -X utf8 scripts/reconcile_signals.py \
    --orders <delivery>/live_signals/file_orders.csv \
    --fills  <成交回单.csv> --out-dir <delivery>/live_signals
# 退出码 0=无偏差 5=存在偏差 2=回单不可读
```

## 六、后续需要注意的地方（重点）

### 6.1 四条禁令（本项目已因此付出代价）

1. **严禁 `rm -rf ~/agentmatrix_run/shards`** —— 曾毁掉半小时已完成结果
2. **严禁并行度 > 2** —— oos 相位单进程约 28 GB；两个同时到峰值 = 56 GB + 其他 ~8 GB > 62 GB，`shard004/005` 就是被 signal 9 杀死的。**这是实测结论，不是保守设定**
3. **严禁 `pkill -f run_pool.sh`** —— 已两次杀掉调用者自己的 shell。要停就**按进程组**（`stop_and_deliver.sh` 已封装）
4. **上传 `.sh` 后必须 `sed -i 's/\r$//'`**，然后 `bash -n` 校验

### 6.2 「已提交但未部署」是最危险的一类缺陷

`delivery_manifest.py` 的口径修正**在 git 里是对的、服务器上是旧的**，后果：交付会报 **260**（**低于 300 目标**）而不是 332。**这一处是本次交付成败的分界**，是靠把完整链真跑一遍才发现的（此前的彩排只跑低内存步骤，4b 一直用旧模块，每次都得出一份「看起来正常」的清单）。

**接手后的纪律**：部署必须是**可核对**的，不是可回忆的。用 `scripts/dev/recon/audit_deployed.py`（它做 **LF 归一化后**的内容比对——直接比字节会因 CRLF/LF 得出「43 个文件未部署」的假象）。

### 6.3 无人值守路径上已修掉的四个缺陷（别改回去）

1. **留存滞后窗口**：`parts` 比 `oos` 少 1 时，链的第 2 步会放弃「合并 parts」改为**重建全部通过因子**（数小时）。`auto_deliver` 进链前会等两个计数一致
2. **done-marker 只记 `chain_exit`**：链退出码 0 **不等于**产物自洽（交叉验证是咨询性的，不致命）。现在同一行记录 `acceptance_exit=`
3. **链启动不等内存释放**：pool 停后要等可用内存 ≥30 GB（pool 在跑时约 29 GB、停后约 55 GB）
4. **watchdog 连续两版完全无效且看起来正常**：检测器把自己数进去了（`pgrep -f` 匹配到自己的命令行；`awk -v pat=` 把 marker 放进自己的参数）。现在 marker 走**环境变量**，并按 pid/脚本名/awk 三重排除

### 6.4 并发写入者（真实存在）

工作区可能有另一个 agent（commit 作者 **AgentMatrix Agent**）在写：

- 它曾**提议 `rm -rf $RUN/shards`** —— 脚本是 `scripts/dev/recon/63_fix_restart.sh`，**绝不要运行**
- 它在 2026-10-06 跑了约 5 小时的 `rebuild_passing_factors` dry-run，**输出留在 `$RUN/delivery_dryrun/`，38 GB，无破坏性但占磁盘**（磁盘当前 60 GB 可用；确认无用可自行 `rm -rf`，我未代删）
- 它的未跟踪文件 `scripts/dev/recon/70_dryrun.sh` 仍在仓库里
- **纪律**：每次部署前 `git status`；用**显式路径** `git add`，不要 `git add -A`（否则会把对方未完成的工作卷进你的提交）

### 6.5 吞吐与内存的物理限制（别再试图优化）

- **整体速率 5.4–5.6 片/小时**。6.4 片/小时是**连续便宜分片**时的 cadence（间隔 559 s = 恰好一个 oos 相位，槽位零空闲），而 **8% 的分片 build 超过 1000 s**（昂贵的是嵌套 rolling correlation 这类公式），把均值拉了下来
- **瓶颈是内存不是 CPU**：16 核里 14 核空闲，两个 worker 的重相位已占 56/62 GB。加并行度只会 OOM
- 已量过的优化：流式读取修掉「逐行 Python 循环」后 **11.9×**；`--jobs 4` 并行构建**逐字节相同**但受 Amdahl 限制（成本分散 1.39×，单候选独占仅 1.10×）
- **链成本实测**：合并 60 parts / 10.5 亿行 = 266 s / 670 MB；附加层 137 因子 jobs=6 = 340 s / 2.73 GB；演示 `ranked_block` 约 **59 MB/因子**（332 因子 ≈ 19.6 GB）；**完整 11 步链在 332 因子上耗时 46 分钟**

### 6.6 操作环境的坑

- **PowerShell**：没有 heredoc；`<` 会被当重定向；`/dev/null` 会被解析成 `D:\dev\null`；内联 `awk` 的引号会被打乱。**一律把命令写成脚本文件，用 `ssh_run.py --file` 执行**
- **不要 kill 正在运行的 `ssh_run.py` 本地任务** —— SIGHUP 会连带杀掉远端脚本
- **Windows 没有 fork**，所以并行相关测试会 skip；**必须在服务器上验证**（`bash -n` 也要在服务器上跑）

## 七、未完成 / 待决策的事项

1. **357 个候选未评估**：跑停在 **123/213 片**（按「通过数 ≥330」分支提前停止，而非跑满 143 片）。若要全量覆盖，重启 pool 即可——`run_pool.sh` 会**跳过已完成分片**：
   ```bash
   cd /home/data/agentmatrix_run/agentmatrix
   AGENTMATRIX_COMMIT=71760b4138e350338299a6f48f269099ebbfab5c \
     setsid nohup bash scripts/dev/run_pool.sh 213 2 > /home/data/agentmatrix_run/logs/pool_run5.log 2>&1 &
   ```
   **但注意**：一旦续跑，`delivery/` 里那份交付就是**过期的快照**了——必须重跑链（`run_downstream.sh`）才会更新。
2. **Supabase 行是 `pushed: false`**：仓库里的信号库**没有 Supabase 客户端**，`FACTOR_LAB_SUPABASE_URL` / `_WRITE_KEY` 是**刻意不读**的。上传是独立的一步，交付没有声称已推送。
3. **执行偏差对账需要客户提供成交回单**：`reconcile_signals.py` 已就绪，但没有真实回单可测（仅在注入的合成回单上验证过：全部成交→退出码 0「无偏差」；漏单+部分成交+滑点+多单→退出码 5 且四类各自正确报出）。
4. **打分卡仍是草案**：tier 只用于排序。若客户要把它变成门槛，需重新讨论——**不要擅自改**。
5. **样本外结果的诚实边界**：策略是**多头集中组合**，最大回撤 35–40%；回测窗口 2023-09-28 ~ 2026-08-31，含成本。**未做任何收益承诺**，交付文档里也禁止出现承诺性表述（`build_delivery_readme.py` 会拒绝这类措辞）。

## 八、我没有做的事（如实声明）

- **没有对外推送能力**：不能发邮件/短信/微信/飞书，**也不能上传 Notion**（`web_fetch` 只能 GET，不能 POST）。本文件是交给用户自行搬运的
- **没有修改任何冻结门槛**
- **没有运行、修改或删除并发 agent 的文件**
- **没有代用户删除** `delivery_dryrun/` 那 38 GB
- **没有把 213 片跑满**（停在 123 片，这是指令允许的第二分支）

## 九、接手后的第一条指令建议

```
先核实，再决定：
1. cat /home/data/agentmatrix_run/logs/auto_deliver.done
2. /home/data/conda-envs/rqsdk/bin/python -X utf8 scripts/verify_delivery.py \
     --delivery-dir /home/data/agentmatrix_run/delivery
3. bash scripts/dev/recon/status.sh
4. git status && git log --oneline -5   # 留意并发 agent 的改动
然后告诉我：是否需要续跑到 213 片、是否要清理 delivery_dryrun 的 38 GB、
是否需要把交付物整理成给客户的最终包。
```

# 交接正文（复制到此结束）
