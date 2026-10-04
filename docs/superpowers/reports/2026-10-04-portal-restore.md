# 四卡片门户恢复记录（PR #122）

【回报】DS（单位电脑）｜四卡片门户恢复｜2026-10-04 20:30

状态：完成并已在线上验证。

## 起因：门户是被哪一下顶掉的

`pages/index.html` 的完整历史（`git log --full-history`）+ Pages 部署记录交叉核对：

| 日期 | commit / PR | 结果 |
|---|---|---|
| 2026-08-30 | `0cb3997`(#105) → `c264acc` → `575a6c9`(#109) → `91ceff4`(#113) | 门户重建，5→6 卡片 |
| 2026-08-30 | `e7f0fc5` **#117** | 「信任分级收编两面板（6→4）」→ 4 卡片 |
| 2026-08-30 | `17ce4bd` **#118** | 「四卡片一行并列布局」← **最后在线版**（当天 15:34 / 15:37 两次 Pages 部署就是它） |
| **2026-09-07** | **`307258e`**（AlphaBoss：Merge branch main into PR: resolve monitor-table conflicts） | **退回「Factor Lab」跳转页** |
| 2026-09-07 | `67e73c1` merge **#119** | 覆盖被固化 |
| 2026-10-04 | **PR #122** | 恢复（本记录） |

同类事故这仓库之前也发生过一次：`9e67f21`「fix: restore main tree accidentally rolled back by PR #101 merge (base_tree mistake)」。

## 恢复内容（来源 = `17ce4bd`，即最后在线版）

| 文件/目录 | 说明 |
|---|---|
| `pages/index.html` | 四卡片门户（与未合并分支 `feat/portal-4col` 上的版本逐字节相同） |
| `pages/lifecycle-dashboard/` | 45 个文件，含 40 个因子的静态快照 |
| `pages/strategy-dashboard/` | 静态页面 + 数据（7 个文件） |
| `pages/factor-db-dashboard/` | 4 个文件 |

**故意没有碰**：

- `pages/factor-lab-dashboard/**` —— main 上的版本比 `17ce4bd` 新 5 周（PR #119 的 quant-desk 改版，旧版 CSS 有 5000+ 行差异），用旧版覆盖会回滚真实工作。
- `pages/assets/**` —— 两版逐字节一致。
- **`pages/strategy-dashboard/backtest.py` 与 `generate_data.py` 不恢复**：这两个离线脚本里硬编码了数据服务器的公网地址（`http://<数据服务器>:8765`，具体值不在此复述）。仓库是**公开**的、还要上 Pages，**绝不能把服务器地址发出去**。页面本身只读静态 `data/strategies.json`，删掉这两个脚本不影响展示。

## 验证证据

- **本地复现 PR Hygiene 两道硬门**（对 55 个变更文件）：机器路径扫描 **0 违规**；变更 Python 文件 **0 编译失败**（本次改动不含任何 `.py`）。
- **内部地址/凭据扫描**：恢复内容中**无任何内网 IP、无服务器地址**（数据服务器地址已排除）。
- **PR #122**：`hygiene` 检查 **success**；55 文件、+6652/−78；合并提交 `f44c00258b7753f0694ac52d2c37436774cfb45d`。
- **Pages 部署**：合并后自动部署，deployment id `6840956432`，状态 **success**，`environment_url = https://agentmatrixlab.github.io/agentmatrix-research/`。
- **四个入口实测**（HTTP HEAD）：

| 路径 | 状态 | 大小 |
|---|---|---|
| `/`（门户） | **200** | 3650 B |
| `/factor-lab-dashboard/` | **200** | 20595 B |
| `/lifecycle-dashboard/` | **200** | 4394 B |
| `/strategy-dashboard/` | **200** | 5189 B |
| `/factor-db-dashboard/` | **200** | 3357 B |

- 门户线上文案（抓取）：标题「AgentMatrix Research · 研究面板门户」，副标题「7×24 自动化因子挖掘机 · 内部研究基座」，四张卡 = Factor Lab 看板 / 因子生命周期监控 / 策略面板 / 因子库目录。

## 需要决定的两件事（**已恢复但风险未消**）

1. ⚠️ **前端门禁密码是硬编码的**：`pages/lifecycle-dashboard/app.js` 与 `pages/factor-db-dashboard/app.js` 的 `ACCESS_PASSWORD` 默认值为 `factorlab2026`，`index.html` 里也内联了。这是 2026-08-30 上线时就已公开的设计（页面明写「GitHub Pages 仅做前端门禁和只读展示；真实权限仍由后端/RLS 控制」）。既然重新公开了，建议改成后端校验或直接撤掉前端门禁 —— 需要 Sam/Patric 定。
2. ⚠️ **`factor-db-dashboard`（因子库目录，1058 因子）** 关联的 Factor DB 平台**已封存**（`parked/factor-db-api-2026-10-03`）。这次只从 `17ce4bd` 取静态文件，**没有合并、没有触碰那个封存分支**；但它重新公开是否合适，请一并确认（要下线只需删一个目录 + 改一张卡）。

## 回滚方式

- 单次回滚：`git revert -m 1 f44c002`。
- 只下线第四张卡：删 `pages/factor-db-dashboard/` 并移除 `pages/index.html` 里对应的 `<a class="card">` 块。
- 临时分支 `fix/restore-portal-4col` 已删除（本地 + 远端），内容已并入 main。
