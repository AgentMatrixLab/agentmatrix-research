# 分支盘点与清理记录（2026-10-04）

范围：`origin` 全部分支（清理前 28 个）。方法：`git rev-list --left-right --count origin/main...<b>` 看领先/落后，`git cherry origin/main <b>` 判断独有提交，`git merge-tree` 预演合并冲突，`git diff --quiet origin/main <b>` 判断树是否与 main 完全一致。

**结论摘要**：删除 **13** 个「内容已在 main」的分支；保留 **2** 个在用分支；**1** 个封存分支按规矩不动；**11** 个过期/冲突分支**故意不删**（里面有独有提交，最多 41 个）。清理后远端剩 **15** 个分支。

## 1. 已删除（13 个，内容已在 main，删除不丢任何代码）

判定标准：`ahead == 0`（已完全并入 main）**或** `cherry+ == 0`（领先的提交全部是 patch 等价，即改动早已在 main 里）。

| 分支 | tip SHA | 最后提交 | 领先/落后 | 类型 |
|---|---|---|---|---|
| `dev` | `5bd3a077c4d7` | 2026-04-27 | 0 / 133 | 已并入 main |
| `chore/factor-db-remove-vendor-words` | `f8f4f579839a` | 2026-08-30 | 0 / 13 | 已并入 main |
| `feat/factor-db-directory-1058` | `ba529046926b` | 2026-08-30 | 0 / 16 | 已并入 main |
| `feat/factor-db-login-gate` | `819b6e10ff77` | 2026-08-30 | 0 / 11 | 已并入 main |
| `feat/factor-lifecycle-v2` | `3a541abbd69d` | 2026-08-30 | 0 / 37 | 已并入 main |
| `fix/cleanup-pages-workflow` | `c28b1dfe3bb8` | 2026-08-30 | 0 / 31 | 已并入 main |
| `fix/pages-nav-clean2` | `bb4392b8a68c` | 2026-08-30 | 0 / 33 | 已并入 main |
| `fix/pages-portal-and-auth` | `0cb3997d9790` | 2026-08-30 | 0 / 35 | 已并入 main |
| `feat/deterministic-factor-validation` | `2dca40a04441` | 2026-09-22 | 1 / 1 | 树与 main **完全相同**（内容已由 PR #120 并入） |
| `feat/trust-tier-dashboards` | `f455992a18ee` | 2026-08-30 | 1 / 6 | 唯一提交 patch 等价于 main 中的提交 |
| `feat/strategy-dashboard-v2` | `e9744540ce82` | 2026-08-30 | 1 / 9 | 同上 |
| `feat/strategy-dashboard` | `1ad8af08d0e0` | 2026-08-30 | 1 / 10 | 同上 |
| `docs/pr-review-standard-bilingual-clean` | `42d6bb4d8158` | 2026-06-14 | 1 / 116 | 同上 |

执行方式：删除前对每个分支**重新校验**一次「独有提交 == 0」，不满足就跳过（本次 13 个全部通过校验）。`dev` 首次因网络超时失败，重试后成功。tip SHA 已记录在上表，便于日后追溯。

## 2. 保留 —— 在用（2 个）

| 分支 | 领先/落后 | 说明 |
|---|---|---|
| `delivery/2026-10-07` | 30 / 0 | **本次交付分支**（DS 全部 D0–E2 工作）。等 10/7 验收后由 Sam/Patric 走 PR 并入 main。 |
| `server/pipeline-cf9c883` | 1 / 0 | Hermes 在 115 服务器使用的正式流水线来源；内容已并入 `delivery/2026-10-07`，但尚未进 main，暂留作服务器侧记录。 |

## 3. 保留 —— 封存，按规矩不动（1 个）

| 分支 | 领先/落后 | 说明 |
|---|---|---|
| `parked/factor-db-api-2026-10-03` | 1 / 4（有冲突） | Factor DB 平台，已明确封存。**按硬规则不做任何操作**（不删、不合、不改）。 |

## 4. 保留 —— 过期/冲突，故意不删（11 个）

这些分支**含有 main 里没有的独有提交**，删掉会丢工作，所以一律保留：

| 分支 | 最后提交 | 领先/落后 | 独有提交 | 合并预览 |
|---|---|---|---|---|
| `feat/factor-infra-v2` | 2026-07-27 | 47 / 103 | **41** | 冲突 |
| `feat/data-adapter-and-bootstrap` | 2026-06-28 | 9 / 113 | 9 | 冲突 |
| `feat/portal-4col` | 2026-08-30 | 7 / 8 | 6 | 冲突 |
| `feat/github-pages-portal` | 2026-07-09 | 5 / 110 | 4 | 冲突 |
| `feat/alpha158-lab-clean` | 2026-08-12 | 4 / 102 | 4 | 冲突 |
| `merge-pr-33` | 2026-07-27 | 3 / 102 | 2 | 冲突 |
| `feat/alpha158-lab` | 2026-06-30 | 2 / 102 | 2 | 冲突 |
| `feat/agent-first-pipeline` | 2026-07-25 | 2 / 107 | 2 | 冲突 |
| `patch-2` | 2026-07-26 | 2 / 117 | 2 | 干净 |
| `patch-4` | 2026-07-26 | 2 / 117 | 2 | 干净 |
| `feat/pr-review-gate` | 2026-06-24 | 1 / 113 | 1 | 冲突 |

## 5. 哪些分支能合并到 main？

- **唯一真正可考虑并入 main 的是 `delivery/2026-10-07`**（30 个提交，包含 cf9c883 流水线 + 预计算因子通道 + 批量/并行/目录/打包/互查 + E1 切分冻结 + E2 裁定落地）。但它**必须等 10/7 交付验收后再合**，且按规矩不由 DS 执行合并。
- `server/pipeline-cf9c883` 的内容已全部包含在 `delivery/2026-10-07` 里，等交付分支并入 main 之后即可删除，届时它自然过期。
- **第 4 节那 11 个都不建议现在合并**：9 个有冲突，`patch-2` / `patch-4` 虽然能干净合并，但已落后 main 117 个提交、内容是 7 月的 `qlib_lab` 小修复，几乎肯定已被后续重构覆盖。真要处理，应该由原作者确认「是否废弃」，然后走「先打 `archive/*` tag 再删」的方式清理，而不是直接合进 main。
- **本次没有向 main 合并任何东西**，也没有改动 main。

## 6. 注意事项与遗留

- **未能核对 GitHub 上是否还有未关闭的 PR**：分析时 `github.com:443` 反复超时，只用了本地 remote-tracking refs。若上述某个已删分支背后还挂着未关闭的 PR，该 PR 会被 GitHub 自动关闭；但因为这 13 个分支的改动**全部已在 main**，关闭这类 PR 在内容上是正确的。
- 需要保留「分支历史视图」的话，可以在 GitHub 上直接查看已合并 PR 的记录；本次删除的都是内容已入 main 的分支。
- 后续建议的规矩：PR 合并后即删源分支；废弃分支走 `archive/*` tag 存档再删，不再长期堆在分支列表里。
- 封存分支 `parked/factor-db-api-2026-10-03` 保持原样，未做任何操作。
