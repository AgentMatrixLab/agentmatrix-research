# 合并记录：delivery/2026-10-07 → main（PR #121）

【回报】DS（单位电脑）｜主线合并｜2026-10-04 13:45

状态：完成 —— `delivery/2026-10-07` 已全部并入 `main`。

## 结果

| 项 | 值 |
|---|---|
| PR | [#121](https://github.com/AgentMatrixLab/agentmatrix-research/pull/121)（已 merged） |
| 合并方式 | merge commit（非 squash、非 rebase，保留 31 个提交的分支历史） |
| 合并提交 | `e79748eee9ffa13d5512ff2e945a7377e58b7dee` |
| 合并前 main | `61dcf19745aa170b470b92bb1b76e0a369ea3a50` |
| 规模 | 31 个提交，43 个文件，+7002 / -22 |
| 合并时间 | 2026-10-04T05:42:01Z |
| 合并后状态 | `delivery/2026-10-07` 独有提交 = **0**（全部已入 main）；main 独有 1 个提交 = 该合并提交本身 |

## 过程（含两次被 CI 拦住）

1. **直推被拒**：`main` 有仓库规则「Changes must be made through a pull request」（`GH013`），直推被 GitHub 拒绝。改为走 PR。
2. **PR 建好后 CI 不过**：两个必需检查 `hygiene` 与 `validate`。`validate`（Factor Validation）跑通过；`hygiene`（PR Hygiene）失败，原因两条：
   - **PR 正文缺 6 个固定标题**：CI 要求 `# Summary` / `# AI Assistance Record` / `# Prompt / Instruction Record` / `# Validation Evidence` / `# Risk Checklist` / `# Reviewer Focus`。已按模板重写正文。
   - **仓库里有机器本地路径**：`constraints-rqsdk.txt` 第 1 行写着 `/home/data/conda-envs/rqsdk`（该文件来自 Hermes 的 `cf9c883`），命中 CI 的「禁止机器本地路径」规则。已改为「115 server RQData conda environment (env name: rqsdk)」，**包版本列表一行未动**。
   - 顺带说明：改动该文件会**改变它的 sha256**，因此后续 `run_manifest.json` 里的 `constraints_sha256` 会与旧值不同（旧 manifest `b8d740f6` 已按接龙10 裁定作废）。
3. **时序坑**：CI 由 push 触发，而修正路径的那次 push 发生在改 PR 正文**之前**，所以那一轮 hygiene 仍读到旧正文并失败。用「关闭 + 重开 PR」触发新运行（没有往分支里塞空提交），第二轮两项检查全绿、`mergeable_state=clean` 后才执行合并。

## 合并前的验证

- 在**合并后的 main 工作树**上跑全量：`python -X utf8 -m pytest tests -q` → **153 passed / 3 failed**；3 个 failed 是已知的 Windows `tests/test_backtest_jobs.py` 清理临时 `jobs.db` 的文件占用问题（Linux CI 不触发，CI 上的 `validate` 也跑绿了）。
- 本地复现了 hygiene 的两道硬门：变更文件机器路径扫描 43 个文件 **0 违规**、变更 Python 文件 **0 编译失败**。
- 合并后核对：`origin/main` 已包含 `research_core/factor_lab/{precomputed_factors,batch_validation,merge_batches}.py`、`scripts/merge_batch_manifests.py`、`docs/delivery/runbook_hermes.md`；`configs/validation_gates.yaml` 里切分已是冻结值（train `2020-01-02~2022-12-31` / OOS `2023-01-01~2026-08-31`）。

## 回滚方式

- 整体回滚：`git revert -m 1 e79748e`（或把 main 重置到 `61dcf19`）。
- 交付分支 `delivery/2026-10-07` 仍保留，未被删除。

## 合并后的影响与后续

1. **`server/pipeline-cf9c883` 现在冗余了**：`git merge-base --is-ancestor cf9c883 origin/main` 成立，其内容已通过本次合并进入 main，可以安全删除（该分支原属 Hermes，删除前建议知会）。**本次未删。**
2. **本次没有合并任何其他分支**：另外 11 个过期/冲突分支仍保留（它们含 main 里没有的独有提交），`parked/factor-db-api-2026-10-03` 封存未碰。
3. **本文件这个提交未进 main**（它是在合并之后写到 `delivery/2026-10-07` 的文档）：代码层面 main 与 delivery 一致于合并提交 `e79748e`；此文档会随后续 PR（例如 Hermes 彩排结果出来后）一起进 main。
4. 下一步不变：等 Hermes 在 115 服务器跑彩排（G2.5 两路一致 + 3 因子）+ 全量，DS 做 D5 互查。
