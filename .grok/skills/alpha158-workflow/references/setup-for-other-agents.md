# 给他人 / 其他电脑的智能体启用 Alpha158 技能

本技能设计为**随仓库版本控制分发**，任何协作者克隆 `agentmatrix-research` 后即可让 AI 智能体按同一套流程执行。

## 方式 A：仓库内自动发现（推荐）

Grok / Cursor 会从以下路径扫描技能（优先级从高到低）：

| 路径 | 说明 |
|------|------|
| `./.grok/skills/` | 当前工作目录 |
| `<repo_root>/.grok/skills/` | **本仓库已包含** `alpha158-workflow` |
| `~/.grok/skills/` | 用户全局技能 |

**操作步骤（给同事）**：

1. 克隆仓库：
   ```bash
   git clone https://github.com/AgentMatrixLab/agentmatrix-research.git
   cd agentmatrix-research
   ```
2. 用 Grok 或 Cursor **在仓库根目录或子目录**打开项目（cwd 必须在 git 仓库树内）。
3. 对智能体说：「按 alpha158-workflow 技能跑完全流程」或输入 `/alpha158-workflow`。
4. 确认智能体加载了技能：应读取 `.grok/skills/alpha158-workflow/SKILL.md`，并**自己执行**命令而非甩给用户。

验证命令：

```bash
grok inspect | grep -i alpha158
# 或
grok inspect --json
```

JSON 中应出现 `"name": "alpha158-workflow"`，`source` 为 `project`，`path` 指向仓库内 `SKILL.md`。

## 方式 B：安装到用户全局目录（可选）

适用于：工作区父目录不在仓库内、或希望所有项目都能 `/alpha158-workflow`。

### Windows

```powershell
cd <path-to>/agentmatrix-research
powershell -ExecutionPolicy Bypass -File .grok/skills/alpha158-workflow/scripts/install-skill.ps1
```

### macOS / Linux

```bash
cd <path-to>/agentmatrix-research
bash .grok/skills/alpha158-workflow/scripts/install-skill.sh
```

安装目标：`~/.grok/skills/alpha158-workflow/`（Windows 为 `%USERPROFILE%\.grok\skills\alpha158-workflow\`）。

安装后重启 Grok 或等待几秒自动热加载，再运行 `grok inspect`。

## 方式 C：AGENTS.md 提醒（仓库已配置）

仓库根目录 `AGENTS.md` 写明：做 Alpha158 相关任务时必须先遵循 `.grok/skills/alpha158-workflow/SKILL.md`。即使技能扫描偶发未触发，项目规则也会引导智能体读取该文件。

## 智能体还必须具备的技能

| 技能 | 作用 | 位置 |
|------|------|------|
| `smartdata-db` | SSH 隧道 + ClickHouse 连接 | 每台机器需自行安装到 `~/.grok/skills/` 或由团队统一分发 |
| `alpha158-workflow` | 本仓库 Alpha158 全流程 | 随仓库 `.grok/skills/` |

`smartdata-db` 不在本仓库内时，请从团队共享渠道复制到 `~/.grok/skills/smartdata-db/`，或让智能体读取 `research_core/SMARTDATA_CONNECTION_RECIPE.md`（若仓库内有）。

## 提交到 Git（维护者）

确保技能被版本控制跟踪：

```bash
git add .grok/skills/alpha158-workflow/
git add AGENTS.md
git commit -m "Add alpha158-workflow agent skill for cross-machine reproducibility"
git push
```

`.grok/skills/` **不应**出现在 `.gitignore` 中（Grok 文档建议将 project skills 提交到仓库）。

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 斜杠菜单没有 `/alpha158-workflow` | cwd 不在仓库内 | `cd agentmatrix-research` 或运行 install 脚本 |
| 智能体只列命令不执行 | 未按技能原则 | 明确要求「智能体亲自执行 verify_setup 和 run-batch」 |
| 技能是英文旧版 | 用了 `~/.grok` 里过时副本 | 删除 `~/.grok/skills/alpha158-workflow` 后重装，或以 repo 版为准 |
| Cursor 未加载 | 旧版 Cursor 技能路径不同 | Grok 兼容扫描 `~/.cursor/skills/`；可将技能 symlink 过去 |