---
name: alpha158-workflow
description: >
  Alpha158 量化研究完整闭环技能（给 AI 智能体用的操作手册，随仓库分发）。
  从联网 git clone agentmatrix-research 开始，经 Python 环境、SmartData SSH 隧道、
  qlib cn_data、init-workspace、16 批 158 因子计算、qlib truth 5% Spearman 校验、
  IC/多空/分层、单因子图、批次报告与 MASTER_DASHBOARD.html 总报告。
  智能体必须亲自执行每一步，不可只输出命令让用户跑。配合 smartdata-db 处理数据库。
  触发词：Alpha158 全流程、alpha158_lab、batch_01、克隆仓库、因子计算、校验、
  IC 报告、生成报告、生成图片、dashboard、Monday presentation、/alpha158-workflow。
---

# Alpha158 全流程技能（智能体操作手册）

> **这是什么**：随 `agentmatrix-research` 仓库分发的 Grok/Cursor 技能（`.grok/skills/alpha158-workflow/SKILL.md`），供任意机器上的 AI 智能体从零跑完 Alpha158 研究闭环。
>
> **这不是**：应用 build 配置或 Dockerfile。
>
> **给他人使用**：克隆本仓库后，在仓库目录内打开 Grok/Cursor 即可自动发现本技能；也可运行 `scripts/install-skill.ps1`（Windows）或 `scripts/install-skill.sh`（macOS/Linux）安装到 `~/.grok/skills/`。详见 `references/setup-for-other-agents.md`。

## 目标产出（跑完后必须存在）

| 阶段 | 产出 |
|------|------|
| 面板 | `runtime/alpha158_lab/market_panel.parquet` |
| 因子 | `runtime/alpha158_lab/alpha158_factors_smartdata.parquet`（158 列） |
| 校验 | `validation/batch_XX/accuracy_report.md`（Spearman ≥ 0.95） |
| 有效性 | `effectiveness/batch_XX/`、`effectiveness/ic_series.csv` |
| 单因子图 | `charts/{FACTOR}_ic.png`、`*_long_short_nav.png`、`*_quantile_layers.png` |
| 批次报告 | `reports/batch_XX/REPORT.md` + mosaics |
| 总报告 | `reports/master/MASTER_DASHBOARD.html`（**对外分享主文件**） |
| 汇总 | `reports/master/MASTER_SUMMARY.md`、`accuracy_all.csv`、`ic_summary_all.csv` |

## 工作区目录（路径用占位符，禁止写死他人机器路径）

```
<WORKSPACE>/                          ← 任意父目录，如 Desktop/alpha158
└── agentmatrix-research/             ← git 仓库根，**所有命令在此执行**
    ├── .venv/
    ├── .grok/skills/alpha158-workflow/   ← 本技能（随仓库分发）
    ├── data/qlib/cn_data/            ← qlib 本地数据（校验 truth）
    ├── research_core/alpha158_lab/   ← 流水线代码
    └── runtime/alpha158_lab/         ← 全部产物
```

**区分模块（极易搞错）**：
- `research_core/alpha158_lab` → **SmartData 真实行情 + Alpha158 复现**，本技能用这个
- `research_core/qlib_lab` 的 `alpha158-starter` → LightGBM 建模演示，**不是**本技能的因子校验流水线

---

## 阶段 0：智能体原则

1. **必须联网** `git clone`，自己装 venv、开隧道、跑 CLI、生成报告
2. **数据库**：先加载 **`smartdata-db`** 技能，本技能不重复隧道/密码逻辑
3. 长任务（batch_01~16）放后台终端；中断后从失败 batch 续跑，勿从 batch_01 重算已完成的批次
4. 16 批默认顺序跑满；逻辑变更后用 `scripts/rerun_alpha158_batches_01_15.py` 清理重跑
5. 计算完成后若用户要汇报/分享，**必须**跑 `scripts/generate_alpha158_all_reports.py`
6. 向用户汇报前对照文末「完成判定」自查

---

## 阶段 1：联网克隆仓库

```powershell
cd <WORKSPACE>
git clone https://github.com/AgentMatrixLab/agentmatrix-research.git
cd agentmatrix-research
git pull   # 已克隆则更新
```

克隆后确认技能存在：

```powershell
Test-Path .grok/skills/alpha158-workflow/SKILL.md   # 应为 True
```

---

## 阶段 2：Python 环境

```powershell
cd <WORKSPACE>/agentmatrix-research
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements-alpha158.txt
```

macOS/Linux：

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements-alpha158.txt
```

后续统一：
- Windows: `$PY = ".\.venv\Scripts\python.exe"`
- Unix: `PY=.venv/bin/python`

---

## 阶段 3：环境变量

在仓库根创建 `.env`（可选，与 smartdata-db 一致）：

```ini
SMARTDATA_CH_HOST=127.0.0.1
SMARTDATA_CH_PORT=19000
SMARTDATA_CH_USER=smartdata_ro
SMARTDATA_CH_PASSWORD=<your-password>
SMARTDATA_CH_DATABASE=amazingdata
```

设置 `PYTHONPATH`（每会话）：

```powershell
$env:PYTHONPATH = (Get-Location).Path
```

---

## 阶段 4：SmartData SSH 隧道

加载 **`smartdata-db`** 技能，独立终端保持运行：

```powershell
ssh -N -L 19000:127.0.0.1:9000 intern04@115.159.73.134
```

验证：

```powershell
netstat -ano | findstr :19000    # Windows
# lsof -i :19000                 # macOS/Linux
```

认证失败但密码正确 → 杀 ssh，**新开终端**重连（已知偶发问题）。

---

## 阶段 5：qlib 本地数据（校验 truth 必需）

```powershell
& $PY -m research_core.qlib_lab.cli init-data
```

数据目录默认：`data/qlib/cn_data`（`Alpha158ResearchConfig` 自动解析）。

---

## 阶段 6：预检（任意新机器必跑）

```powershell
& $PY .grok/skills/alpha158-workflow/scripts/verify_setup.py
```

全部 PASS 后再继续。FAIL 项按输出提示修复。

---

## 阶段 7：范围规则（计算 vs 校验，禁止混用）

| 层级 | 股票 | 日期 | 用途 |
|------|------|------|------|
| **计算** | SmartData 全 A 股（~6761），剔除 ST/停牌/退市 | DB 实际交易日 ∩ 请求窗 `2020-01-01`~`2026-12-31` | 因子值 + 全样本 IC |
| **校验（5%）** | 与 qlib `all` **交集**（~678） | 与 qlib 日历 **交集**，上限 `2021-06-11` | 截面 Spearman ≥ 0.95 |
| **2021-06-11 后** | 全计算股票池 | 仅计算 + IC | 无本地 qlib truth |

**禁止**把计算股票池限制为 qlib 交集。交集仅在 `validation/accuracy.py` 内做。

---

## 阶段 8：初始化工作区

```powershell
& $PY -m research_core.alpha158_lab init-workspace
```

---

## 阶段 9：跑 16 批因子流水线

每批内部步骤（`pipeline.py` → `run_alpha158_batch`）：
加载/缓存面板 → 计算因子 → 合并 parquet → 导出 qlib truth → Spearman 校验 → 有效性回测 → IC → 出图 → 批次报告 → manifest。

### 首次或面板逻辑变更

```powershell
& $PY -m research_core.alpha158_lab run-batch --batch-id batch_01 --reload-panel
```

### 后续批次（复用 panel）

```powershell
& $PY -m research_core.alpha158_lab run-batch --batch-id batch_02
# ... batch_03 .. batch_16
```

### 一次跑满 16 批（智能体自己循环执行）

```powershell
1..16 | ForEach-Object {
  $id = "batch_{0:D2}" -f $_
  if ($_ -eq 1) {
    & $PY -m research_core.alpha158_lab run-batch --batch-id $id --reload-panel
  } else {
    & $PY -m research_core.alpha158_lab run-batch --batch-id $id
  }
}
```

预计总时长数小时，**放后台**；检查 `pipeline_manifest_batch_XX.json` 的 `accuracy_status`。

### 逻辑变更后批量重跑 01–15

```powershell
& $PY scripts/rerun_alpha158_batches_01_15.py
& $PY scripts/rerun_alpha158_batches_01_15.py batch_14   # 从 batch_14 续跑
```

### CLI 参数

| 参数 | 默认 | 含义 |
|------|------|------|
| `--start` | `2020-01-01` | 请求起始（裁到 DB） |
| `--end` | `2026-12-31` | 请求结束（裁到 DB） |
| `--validation-end` | `2021-06-11` | qlib truth 截止 |
| `--reload-panel` | 关 | 强制从 DB 重拉面板 |

---

## 阶段 10：解读校验结果

- **PASS**：截面 Spearman 均值 ≥ **0.95**
- **SKIP**：qlib 无有效 truth（如 `VWAP0` 缺 `$vwap`）
- **FAIL**：多为 60 日滚动类（`VSUMN60`、`VSUMD60`、`CORD60` 等）
- 参考整体：约 134 PASS / 23 FAIL / 1 SKIP（~85%）

---

## 阶段 11：生成总报告与分享图

```powershell
& $PY scripts/generate_alpha158_all_reports.py
```

对外分享优先级：
1. `runtime/alpha158_lab/reports/master/MASTER_DASHBOARD.html`
2. `MASTER_SUMMARY.md`
3. `reports/batch_XX/REPORT.md`

产物速查：`references/artifacts.md`

---

## 已知问题

| 问题 | 处理 |
|------|------|
| SSH 隧道认证失败 | 新终端重启隧道（smartdata-db） |
| batch_14+ MemoryError | 保持 `pipeline.py` 中 PyArrow `_merge_factors_parquet`，勿改回 pandas 全量 merge |
| truth 文件名日期 | 用解析后的 `overlap_start`（如 `2020-01-02`） |
| 智能体找不到技能 | 确认 cwd 在仓库内，或运行 `install-skill` 脚本 |
| VWAP0 SKIP | 预期行为 |

---

## 完成判定（向用户汇报前自查）

- [ ] 仓库已克隆，`.grok/skills/alpha158-workflow/SKILL.md` 存在
- [ ] `verify_setup.py` 全部 PASS
- [ ] `batch_01`~`batch_16` manifest 均存在，`alpha158_factors_smartdata.parquet` 含 158 因子列
- [ ] `generate_alpha158_all_reports.py` 已跑，`MASTER_DASHBOARD.html` 存在
- [ ] 向用户说明：计算范围（全市场 ~6761）vs 校验范围（交集 ~678 股 × 至 2021-06-11）
- [ ] 给出主报告路径、整体 PASS 率、典型 FAIL 因子说明

---

## 给他人 / 其他电脑启用本技能

1. **推荐**：`git clone` 本仓库，在 `agentmatrix-research` 目录内用 Grok/Cursor → 自动加载 `<repo>/.grok/skills/`
2. **全局安装**（可选）：运行本技能目录下 `scripts/install-skill.ps1` 或 `install-skill.sh`
3. **验证**：`grok inspect` 应出现 `alpha158-workflow`，source 为 `project` 或 `user`
4. 详细说明见 `references/setup-for-other-agents.md`