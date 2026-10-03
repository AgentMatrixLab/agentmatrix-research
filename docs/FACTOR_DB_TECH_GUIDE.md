# A股因子数据库 — 技术实现文档及维护指南

> 版本：v0.5（客户策略版） · 更新日期：2026-09-01
> 面向维护者。使用说明见 [FACTOR_DB_USER_GUIDE.md](./FACTOR_DB_USER_GUIDE.md)，交付计划见 [FACTOR_DB_DELIVERY_PLAN.md](./FACTOR_DB_DELIVERY_PLAN.md)。

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────┐
│  Web 前端（frontend/factor-db/，静态 SPA）                 │
│  检索 · 详情 · KaTeX 公式渲染 · Canvas 直方图 · 导出入口     │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP (JSON)
┌──────────────────────▼───────────────────────────────────┐
│  API 层  research_core/factor_db/api.py                   │
│  Flask Blueprint（/api/factor-db）+ 静态页路由 + 独立启动    │
├──────────────────────────────────────────────────────────┤
│  服务层  research_core/factor_db/service.py                │
│  因子值查询 · 分布统计 · CSV/Excel 导出 · 数据源状态          │
├──────────────────────────────────────────────────────────┤
│  元数据层 research_core/factor_db/metadata.py              │
│  统一因子目录（1058 个）：检索 / 详情 / 统计 / 数据字典       │
│    ├─ quant_api_33_meta.py   33 因子精编中文元数据（静态）   │
│    ├─ Alpha101 / qlib-factor-zoo / Barra / JQGM 聚合         │
│    └─ zoo_meta.json 等多来源元数据事实源                      │
├──────────────────────────────────────────────────────────┤
│  数据访问  research_core/data_loader/quant_api_client.py   │
│  Quant API v2 HTTP 客户端（token 经环境变量注入）            │
└──────────────────────────────────────────────────────────┘
```

关键设计原则：

- **元数据与数据分离**：元数据（公式、定义、口径说明）本地静态/半静态维护，因子值按需经 API 查询，不落地、不冗余。
- **单一事实源**：Alpha101 的公式与描述直接读自 `factor_lab/libraries/alpha101/specs.py`，因子库更新时产品目录自动同步，无需人工搬运。
- **token 只进后端进程**：前端、API 响应、导出文件中零凭证。

## 2. 文件清单

| 文件 | 职责 |
|---|---|
| `research_core/factor_db/__init__.py` | 模块公开接口 |
| `research_core/factor_db/quant_api_33_meta.py` | Quant API 33 因子精编元数据（`_meta()` 工厂 + `QUANT_API_33_META` 列表） |
| `research_core/factor_db/metadata.py` | 元数据聚合：Alpha101 动态生成（含 `formula_to_latex` 转换器）、检索、统计、数据字典 |
| `research_core/factor_db/service.py` | 因子值查询、分布统计（描述统计+直方图）、CSV/Excel 导出、数据源状态 |
| `research_core/factor_db/api.py` | Flask 蓝图 + 前端静态路由 + `create_app()` + CLI 入口 |
| `frontend/factor-db/index.html` | 单页应用骨架 |
| `frontend/factor-db/styles.css` | 深色主题样式 |
| `frontend/factor-db/app.js` | 前端逻辑（检索/详情/分布图/导出） |
| `tests/test_factor_db.py` | Factor DB 元数据与 API 回归测试 |

## 3. 关键实现说明

### 3.0 公开接口与受控接口分层

- 公开接口：`/stats`、`/factors`、`/factors/{id}`、`/dictionary`、`/distribution?demo=1`
- 受控接口：`/factors/{id}/values`、真实 `/distribution`、`/export?scope=values`、`/quant-api/status?remote=1`
- 客户鉴权：`Authorization: Bearer <key>` 或 `X-FactorDB-API-Key: <key>`
- 客户配置来源：`FACTOR_DB_CUSTOMER_POLICIES_JSON` / `FACTOR_DB_CUSTOMER_POLICIES_PATH`（未配置时回退到 `FACTOR_DB_API_KEYS`）
- CORS 白名单：独立运行优先读取 `FACTOR_DB_CORS_ORIGINS`，未设置时回退到 `FACTOR_LAB_CORS_ORIGINS`
- 受控接口留痕：请求完成后写入 `runtime/factor_db/audit/access.jsonl`（可用环境变量改路径）
- 基础限流：按 `客户/凭证 × 端点` 维度限频，超限返回 `429`

客户策略 JSON 示例：

```json
[
  {
    "customer_id": "client_a",
    "name": "客户A",
    "api_key": "client-a-key",
    "expires_at": "2026-12-31T23:59:59Z",
    "allowed_sources": ["QAPI33", "ALPHA101"],
    "allowed_factors": ["QAPI33:roe_ttm"],
    "allow_export_values": false,
    "rate_limit_count": 60,
    "rate_limit_window_seconds": 60
  }
]
```

### 3.1 因子标识符体系

`factor_id = {来源前缀}:{因子名}`：

- `QAPI33:roe_ttm` — Quant API 33 因子（`factor_monthly` 端点直接可查）
- `ALPHA101:alpha1` — WorldQuant Alpha101（元数据就绪，因子值阶段 1 开放）

`metadata.get_factor()` 支持短名回退（`roe_ttm` → `QAPI33:roe_ttm`，仅短名唯一时命中），便于交互式使用。

### 3.2 Alpha101 公式的 LaTeX 生成

`metadata.formula_to_latex()` 采用**算子记法转换**而非完整语法分析：

- 已知算子/字段名按 `_LATEX_OPERATORS` 映射表替换（`rank` → `\mathrm{rank}`，`close` → `P_{t}` 等）
- 保留伪代码的参数结构（括号、逗号、三元 `? :`），保证公式保真、可与论文逐项对照
- 新增算子只需扩展 `_LATEX_OPERATORS` 映射表，无需改解析逻辑

### 3.3 分布统计（service.factor_distribution）

- 取 `factor_monthly_dates()` 最新截面日期 → 拉取该日全截面（约 5400 只）→ 本地计算
- 统计量：count / mean / std / min / max / P1..P99 / 偏度 / 峰度 / IQR / P1-P99 外比例（离群率）
- 直方图：等宽分箱（默认 30，API 可调 `bins`），前端 Canvas 绘制并叠加 P25/P50/P75 参考线
- `demo=1`：以因子名为种子生成确定性正态代理样本（4000 个），响应中 `demo: true` 明确标注，用于无 token 环境演示

### 3.4 导出实现

- CSV：`pandas.DataFrame.to_csv` + `utf-8-sig`（BOM），Excel 双击直开中文
- Excel：`pd.ExcelWriter(engine="openpyxl")` 写入内存 `BytesIO`；openpyxl 缺失时返回 500 + 安装提示
- 命名：`{factor_id 去冒号}_{scope}.{ext}`，如 `QAPI33_roe_ttm_values.csv`

### 3.5 服务部署形态

```python
# 独立运行（开发/演示）
python -X utf8 -m research_core.factor_db.api --port 8013

# 挂载到已有 factor_lab_api Flask 应用
from research_core.factor_db.api import register_factor_db
register_factor_db(app)
```

依赖：flask、flask-cors、pandas、openpyxl（Excel 导出）、requests（quant_api_client）。前端除 KaTeX CDN 外零依赖。

## 4. 维护指南

### 4.0 关键环境变量

| 变量名 | 说明 |
|---|---|
| `FACTOR_DB_API_KEYS` | 受控接口客户凭证列表，多个值用逗号分隔 |
| `FACTOR_DB_CUSTOMER_POLICIES_JSON` | 客户策略 JSON，支持客户名、到期时间、访问范围、导出权限、客户级限流 |
| `FACTOR_DB_CUSTOMER_POLICIES_PATH` | 客户策略 JSON 文件路径 |
| `FACTOR_DB_CORS_ORIGINS` | Factor DB 独立应用允许的浏览器来源白名单 |
| `FACTOR_DB_PUBLIC_ORIGIN` | 对外公开域名，可自动加入 CORS 白名单 |
| `FACTOR_DB_RATE_LIMIT_COUNT` | 单个 API Key 在窗口期内的最大调用次数，默认 120 |
| `FACTOR_DB_RATE_LIMIT_WINDOW_SECONDS` | 限流窗口秒数，默认 60 |
| `FACTOR_DB_AUDIT_LOG_PATH` | 审计日志落盘路径，默认 `runtime/factor_db/audit/access.jsonl` |
| `FACTOR_LAB_QUANT_API_TOKEN` / `QUANT_API_TOKEN` | 后端访问 Quant API 的服务端凭证 |

### 4.1 新增一个 Quant API 因子（元数据 + 数据即齐）

1. 在 `quant_api_33_meta.py` 追加一个 `_meta(...)` 条目（字段齐全：公式 LaTeX、定义、计算逻辑、应用、注意事项）
2. 重启服务即可；`/stats`、检索、详情、导出自动包含新因子
3. 若因子属于新大类/子类，无需改代码——分类标签由元数据驱动

### 4.2 新增一个因子来源（如 GTJA191、Barra）

1. 仿照 `metadata._build_alpha101_meta()` 写一个 `_build_<source>_meta()`，从对应 factor_lab 规格模块动态加载
2. 在 `_all_factors()` 中拼接；确认 `factor_id` 前缀不冲突
3. 若该来源的因子值可经已有 API 查询，扩展 `service._quant_name()` 的前缀分发逻辑；否则保持 425（数据未就绪）语义

### 4.3 因子值数据源切换（阶段 1：RQData 本地 parquet）

当前 `factor_values()` 直连 Quant API。阶段 1 接入 RQData 拉取的本地 parquet 时：

1. 在 `service.py` 增加本地 parquet 读取路径（`common.paths` 取 runtime 数据目录）
2. `factor_values()` 按来源前缀路由：`QAPI33` → API，`ALPHA101` → 本地 parquet
3. 修改点集中在 service 层单函数内，API 与前端零改动

### 4.4 冒烟测试

仓库根目录执行：

```bash
python -m pytest -q tests/test_factor_db.py
```

覆盖：目录统计、检索过滤、详情（QAPI33/ALPHA158/短名）、来源计数、
token/425 语义、演示分布、字典接口。

### 4.5 质量控制机制（与交付方案 6 节对应）

| 机制 | 实现位置 |
|---|---|
| 因子值准确性 | 服务层透传 Quant API 原始值，不做静默修改；分布统计独立复算均值/分位数供交叉校验 |
| 完整性检查 | 元数据加载时校验当前目录聚合结果可正常检索、统计与导出（回归测试覆盖） |
| 异常值提示 | 分布统计输出 P1/P99 离群率、偏度、峰度，前端直方图叠加分位线 |
| 口径透明 | 每个因子强制携带 `cautions`（注意事项）字段，提示口径陷阱 |

### 4.6 安全要点

- token 仅经环境变量 `FACTOR_LAB_QUANT_API_TOKEN` / `QUANT_API_TOKEN` 进入后端进程
- 真实数据接口默认可通过客户策略或 `FACTOR_DB_API_KEYS` 转为客户受控接口；目录检索类接口保持公开只读
- 受控接口默认记录客户编号、客户名称、来源 IP、路径、状态码，便于交付后的审计与追溯
- 所有导出文件名由服务端生成（基于 factor_id 白名单字符），拒绝用户输入拼接
- CORS 仅开放 `/api/*`；独立应用通过 `FACTOR_DB_CORS_ORIGINS` 收紧来源白名单

## 5. 已知限制与阶段 1 待办

| 项 | 现状 | 计划 |
|---|---|---|
| Alpha101 因子值 | 元数据/公式就绪，值未生成 | RQData 异步拉取任务 → 本地 parquet → service 路由 |
| 真实分布 | 需 token，逐因子现算 | 增加（因子×日期）分布结果缓存（parquet 落地） |
| 因子历史截面 | 单因子单截面查询 | 批量截面导出（NDJSON/Parquet 流式） |
| 鉴权 | 已支持客户策略 / API Key 保护受控接口 | 后续可接入内网网关、数据库化客户配置与额度管理 |
| 前端 | 原生 JS 单页 | 按反馈迭代（React/Vue 化仅在复杂度需要时） |

## 6. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-28 | v0.1 | 阶段 0 产品雏形：134 因子元数据目录、API 8 端点、Web 原型、CSV/Excel 导出、演示分布 |
| 2026-09-01 | v0.2 | 目录扩展至 1058 因子，宿主服务挂载 Factor DB，回归测试改为 `tests/test_factor_db.py` |
| 2026-09-01 | v0.3 | 增加客户 API Key、CORS 白名单与公开/受控接口分层 |
| 2026-09-01 | v0.4 | 为受控接口增加基础限流与审计日志 |
| 2026-09-01 | v0.5 | 增加客户策略：到期控制、因子范围授权、导出权限与客户级限流 |
