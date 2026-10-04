# 脱敏收尾 + 分支清理记录

【回报】DS（单位电脑）｜脱敏收尾 / 分支清理 / 历史问题结论｜2026-10-04 21:35

## 一、脱敏（已完成，含一次带病合并的坦白）

| PR | 内容 | CI 结果 |
|---|---|---|
| [#125](https://github.com/AgentMatrixLab/agentmatrix-research/pull/125) | 清掉 8 个文件里的服务器地址 + `strategy_panel/engine/config.py` 的 admin token → 改读环境变量、未配置即报错 | `validate` ✅ / **`hygiene` ❌（仍被我合并）** |
| [#126](https://github.com/AgentMatrixLab/agentmatrix-research/pull/126) | 补 `data_manager.py` 的服务器路径、新增守卫测试、修脚本守卫 | **`hygiene` ✅**，`clean` 后才合并 |

**失败根因**：#125 改动了 `strategy_panel/engine/data_manager.py`，使该文件整体进入 CI 路径扫描，暴露出第 298 行**早已存在**的服务器文件路径（服务器数据根目录下的绝对路径，命中「禁止机器本地路径」）。**我的合并脚本当时有 bug：等不到 `clean` 也会继续合并**，因此带病合并。已修：脚本现在非 `clean` 直接拒绝合并（`REFUSING TO MERGE`）。

**加固**：新增 `tests/test_only_no_baked_in_hosts.py` —— 全仓 `git ls-files` 扫描，命中①硬编码 `http://<IP>` 形式默认值（放行 `127.0.0.1`/`localhost`/`example.com` 等）②`sk-admin-…` token ③绝对用户目录路径（`<用户主目录>/…` 形式）即失败。
**反证（守卫必须能失败）**：临时 `git add` 一个含硬编码测试 IP（形如 `HOST = "http://x.x.x.x"`）的文件 → 守卫如期失败并指出该文件与行号；删除探针后 `2 passed`。

**改动清单**：`research_core/data_loader/quant_api_client.py`、`research_core/data_loader/clickhouse_loader.py`、`strategy_panel/engine/{config,daily_pipeline,data_manager}.py`、`.trae/skills/quant-api-v2/SKILL.md`、`docs/FACTOR_LAB_QUANT_API_BACKEND.md`、`docs/integration/PROGRESS.md`、`strategy_panel/README.md`（+ 我自己报告里引用的一处服务器路径）。当前树 `115.159.*` / `sk-admin-` **0 命中**。
**全量测试**：`pytest tests -q` → **153 passed / 3 failed**（3 个为已知 Windows `jobs.db` 占用，与本次改动无关）。

## 二、历史与备份：**旧值仍可检索到**，故决策「换锁不擦字」

证据（本轮实测）：

- `git log -S'<旧地址>' --all` → **18 个提交**；`git log -S'sk-admin-' --all` → **4 个提交**。任何克隆都能复现。
- **8 个 fork** 持有旧对象：`Theomiao6`、`LorenzoTeng`、`Promise19131`、`JustinF8`、`zlu05211-creator`、`kkkkk-79`、`celine385567-cyber`、`youqiliu05`。→ **重写组织仓库历史也删不掉 fork 里的副本**。
- GitHub 上旧提交页面、PR 引用仍在；搜索引擎/archive 可能存有快照。

**决策（Sam/本机确认）**：**只做「轮换 token + 服务器加白名单」，不重写 git 历史**。

**仍待执行（服务器侧，DS 不连服务器）**：
1. **轮换曾暴露的 admin token**（不轮换 = 没修好）；确认旧 token 失效。
2. 服务器访问加 **IP 白名单**（或改端口/限制来源）。
3. （可选）评估 `samzhang8/model` 公开仓库里的 `docs/api_keys.json` + `api_billing.jsonl`（另一个仓库的问题，仍未处理）。

## 三、分支清理

**本轮删除**：`server/pipeline-cf9c883`
- 删除前核验：**独有提交 = 0**（内容已全部在 main）；tip = `cf9c8836c2aca390a9a6e6a17550ce4af981d7b4`（2026-09-25，`feat(factor-lab): validate one-month reversal deterministically`）。因提交已可从 main 到达，无需另打归档 tag。
- 远端分支：**15 → 14**。

**保留**：

| 分支 | 原因 |
|---|---|
| `main` | 主线 |
| `delivery/2026-10-07` | 交付分支，**留到 10/7 验收后**再删（当前独有提交 0） |
| `parked/factor-db-api-2026-10-03` | Factor DB 平台，**封存未动**（硬规则） |
| 其余 11 个 | 均含 main 里没有的提交，**需原作者确认后才能清理**；建议「先打 `archive/<分支名>` tag 再删」，零丢失 |

11 个待确认分支（独有提交数 / 最后提交）：`feat/factor-infra-v2`(47, 07-27)、`feat/data-adapter-and-bootstrap`(9, 06-28)、`feat/portal-4col`(7, 08-30)、`feat/github-pages-portal`(5, 07-09)、`feat/alpha158-lab-clean`(4, 08-12)、`merge-pr-33`(3, 07-27)、`feat/alpha158-lab`(2, 06-30)、`feat/agent-first-pipeline`(2, 07-25)、`patch-2`(2, 07-26)、`patch-4`(2, 07-26)、`feat/pr-review-gate`(1, 06-24)。其中 **`feat/factor-infra-v2`（47 个）值得先评估内容是否该合并**，不宜直接删。

## 四、CI 复核：一个真漏洞 + 一处我的误报

1. **真漏洞（已修）**：**只改 `tests/**` 的 PR 不会跑测试** —— `Factor Validation` 的 `pull_request.paths` 不含 `tests/**`（PR #126 只改了 `tests/` 与 `strategy_panel/`，结果只有 `hygiene` 跑了）。→ 已在 PR #128 把 `tests/**` 加进触发路径，并新增 `tests/test_only_ci_triggers.py` 守护该性质（改回去就会测试失败）。
2. **误报（我撤回）**：我此前称「`pr-hygiene.yml` 会扫到它自己，任何改动该 workflow 的 PR 都会失败」——**这是错的**。该 workflow 第 156-158 行**早已把自己排除在路径扫描之外**（`excluded = {".github/workflows/pr-hygiene.yml"}`，由 2026-07-09 的 PR #42 / `859c259` 引入）。误报原因：我本地复刻 CI 规则时**没有复刻这条排除**，于是把它的两条「用户主目录路径」正则定义行当成了违规。按 CI 自身逻辑模拟（变更文件只含该 workflow）→ 扫描目标为空、0 违规。

结论：**只需修第 1 项**。第 2 项无需改动，我不去动它（也避免「为了通过而改规则」）。
