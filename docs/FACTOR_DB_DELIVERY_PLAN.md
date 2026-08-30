# A股因子数据库产品交付方案

> 版本：v1.0 | 日期：2026-08-28 | 负责人：因子工程组
> 基础仓库：AgentMatrixLab/agentmatrix-research（`research_core/factor_lab`）

---

## 1. 产品定位与目标

### 1.1 产品定位

面向公司量化研究团队的一站式 **A股因子数据产品**，提供：

- **因子目录**：标准化因子元数据（定义、公式、来源、频率、覆盖范围）
- **因子数据**：可程序化调用的因子值时序/截面数据
- **查询服务**：Web 检索、详情浏览、公式展示、分布可视化
- **导出能力**：CSV / Excel 数据下载，供研究流程直接消费

### 1.2 核心目标

| 优先级 | 目标 | 衡量标准 |
|---|---|---|
| P0 | 100+ 核心因子标准化入库 | 因子元数据覆盖 134 个（33 Quant API + 101 Alpha101） |
| P0 | 可演示 Web 原型 | 检索/详情/公式/分布/导出 5 项功能可现场演示 |
| P0 | API 接口原型 | 因子列表/详情/数据/导出 4 类端点可调用 |
| P1 | 真实数据联通 | 33 因子月频数据（41.9 万行）经 Quant API v2 可查 |
| P2 | 数据质量控制 | 校验/完整性/异常值三项机制落地 |

### 1.3 用户画像

- **量化研究员**：查因子定义、下载因子值、验证公式口径
- **策略开发**：API 拉取因子数据进回测
- **因子工程师**：比对因子实现、查注意事项、避免口径踩坑

---

## 2. 产品内容设计

### 2.1 因子分类体系（三大类别）

| 大类 | 子类 | 因子示例 | 数量（首批） |
|---|---|---|---|
| **基础因子** | 规模/价格/流动性 | log_price、log_amount_1m、avg_amount_1m、turnover_proxy、volume_ratio、illiquidity | 9 |
| **技术因子** | 动量/反转/波动/技术指标 | ret_1m~12m、momentum_12_1、reversal、volatility_1m/3m/6m、rsi_14、bb_position、ma_signal、Alpha101 全系 | 119 |
| **基本面因子** | 盈利/成长/杠杆/运营 | roe_ttm、roa_ttm、net_margin、revenue_yoy、profit_yoy、eps_yoy、debt_to_asset、asset_turnover | 8 |
| **合计** | | | **134** |

### 2.2 因子元数据规范（每个因子标准化信息）

每条因子记录包含以下字段：

| 字段组 | 字段 | 说明 | 示例 |
|---|---|---|---|
| **基础信息** | `name_cn` | 因子中文名称 | 净资产收益率（TTM） |
| | `name_en` | 英文名称 | Return on Equity (TTM) |
| | `factor_id` | 唯一标识符 | `QAPI33:roe_ttm` |
| | `category` / `subcategory` | 大类 / 子类 | 基本面因子 / 盈利能力 |
| | `data_source` | 数据来源 | Quant API v2 factor_monthly |
| **详细信息** | `definition` | 因子定义 | 衡量股东权益产生净利润的能力… |
| | `calc_logic` | 计算逻辑 | TTM净利润 ÷ 股东权益，月频截面 |
| | `frequency` | 数据频率 | 月频 |
| | `coverage` | 覆盖范围 | 全A 约 5,400 只 |
| | `history_start` | 历史起始 | 2020-01-23 |
| **原理公式** | `formula_latex` | LaTeX 数学公式 | `NP_{ttm} / E` |
| | `formula_expr` | 伪代码公式 | `net_profit_ttm / equity` |
| | `logic_notes` | 逻辑说明 | 分子分母均为 PIT 口径… |
| | `application` | 应用场景 | 质量风格选股、多因子模型质量维度 |
| | `cautions` | 注意事项 | 金融/地产高杠杆行业需行业中性化… |

### 2.3 初始因子库（134 个）

- **Quant API 33 因子**（`QAPI33:*`）：数据现成（月频 41.9 万行，2020-01 至 2026-04），元数据详尽，为首批主推
- **Alpha101 因子**（`ALPHA101:alphaNNN`）：公式与实现齐备（`research_core/factor_lab/libraries/alpha101`），元数据从既有规格批量生成，数据可经 RQData 拉取任务补充

---

## 3. 现有资源评估

### 3.1 资源盘点

| 资源 | 现状 | 复用度 |
|---|---|---|
| **数据接口** | Quant API v2（`http://115.159.73.134:8765`）：25 张 CH 表 + 33 因子月频 41.9 万行 + RQData 异步拉取；4 种格式（JSON/NDJSON/Parquet/CSV） | ★★★★★ 直接复用 |
| **计算引擎** | `research_core/factor_lab/libraries/`：quant_api_33 / alpha101 / gtja191 / alpha158 / barra 完整实现 + truth 校验 | ★★★★★ 直接复用 |
| **存储系统** | `runtime/`（本地 JSON/parquet）+ ClickHouse（远端）+ Supabase（真值层，规划中） | ★★★☆☆ 本期用本地+远端 CH |
| **Web 框架** | Flask（`backend/factor_lab_api.py` 已有 REST 骨架 + CORS）+ 静态前端模式（factor-lab-dashboard） | ★★★★☆ 复用框架与部署模式 |
| **因子规格** | 134 个因子的公式/描述/分类已在 `specs.py` 中结构化 | ★★★★★ 直接转换 |
| **开发人力** | 因子工程组（本方案执行主体），智能体辅助开发（本仓库已内置 5 个 Skill 流水线） | ★★★★☆ |

### 3.2 差距分析（Gap）

| 缺口 | 解决方案 | 归属阶段 |
|---|---|---|
| 因子元数据无中文名/LaTeX/应用场景 | 新建 `research_core/factor_db/` 元数据模块，33 因子精编 + 101 因子批量生成 | 阶段 0 |
| 无面向"因子数据产品"的 Web 界面 | 新建 `frontend/factor-db/` 轻量原型（检索/详情/公式/分布/导出） | 阶段 0 |
| 无产品化 API（因子目录/导出/分布） | 新建 factor_db Flask 蓝图，4 类端点 | 阶段 0 |
| Alpha101 无现成因子值数据 | 经 `/admin/pull` 触发 RQData 拉取（每因子 5-10 秒） | 阶段 1 |
| Excel 导出依赖 | pandas + openpyxl（已列入 requirements） | 阶段 0 |
| 质量控制机制未产品化 | 沿用 factor_lab truth-compare + 新增分布/缺失率自动检查 | 阶段 2 |

### 3.3 资源分配方案

| 角色 | 投入 | 职责 |
|---|---|---|
| 因子工程（1 人） | 100% | 元数据编制、数据链路、质量控制 |
| 后端开发（1 人，可由上兼任） | 50% | API 端点、导出、缓存 |
| 前端开发（智能体辅助） | 30% | Web 原型、可视化 |
| 数据运维（现有 API admin 兼） | 10% | RQData 拉取任务、CH 表维护 |

---

## 4. 分阶段交付计划

### 阶段 0：产品雏形（2026-08-28 ~ 09-11，2 周）

| 项 | 内容 |
|---|---|
| 交付内容 | ① 本交付方案文档；② `research_core/factor_db/` 元数据+API 模块；③ `frontend/factor-db/` Web 原型；④ 134 因子元数据；⑤ 数据字典+技术文档 |
| 验收标准 | (a) Web 原型可检索/看详情/渲染 LaTeX 公式/看分布图/导出 CSV；(b) `GET /api/factor-db/factors` 返回 134 条；(c) 33 因子可查真实月频数据（需 token）；(d) CSV/Excel 导出可用 |
| 演示脚本 | 打开首页 → 搜索"ROE" → 查看详情（公式/场景/注意） → 查看分布图 → 导出 CSV → curl 调 API |

### 阶段 1：初始因子库成型（2026-09-12 ~ 10-16，5 周）

| 项 | 内容 |
|---|---|
| 交付内容 | ① RQData 拉取 Alpha101 因子值（101 个，月频）；② 因子值本地 parquet 缓存层；③ GTJA191/Alpha158 元数据扩展（至 350+ 因子）；④ API 增加 IC 查询、批量拉取端点 |
| 验收标准 | (a) 134 因子全部有可查数据；(b) 元数据 350+；(c) API 支持 `?fields=` 列裁剪与分页 |

### 阶段 2：质量控制与数据治理（2026-10-17 ~ 11-13，4 周）

| 项 | 内容 |
|---|---|
| 交付内容 | ① 数据准确性校验（truth-compare 机制接入：overlap_ratio/exact_match_ratio）；② 完整性检查（缺失率/覆盖率监控）；③ 异常值处理（MAD winsorize，可配置）；④ 数据质量周报 |
| 验收标准 | (a) 每因子质量评分（accuracy/completeness/outlier 三维）；(b) 缺失率>5% 自动告警；(c) 质量报告自动生成 |

### 阶段 3：生产化与迭代（2026-11-14 起，持续）

| 项 | 内容 |
|---|---|
| 交付内容 | ① 因子值日频扩展；② 用户体系与权限（对接 Supabase）；③ 因子相关性矩阵、行业中性化预处理；④ SDK（Python client） |
| 验收标准 | 按迭代需求单验收 |

---

## 5. 技术路线

### 5.1 总体架构

```
┌─────────────────────────────────────────────────────┐
│  Web 前端  frontend/factor-db/（静态 HTML+JS）        │
│  检索 · 详情 · KaTeX 公式 · 分布图 · 导出下载          │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (JSON)
┌──────────────────────▼──────────────────────────────┐
│  API 服务  research_core/factor_db/api.py (Flask)    │
│  /api/factor-db/factors          因子目录            │
│  /api/factor-db/factors/{id}     因子详情            │
│  /api/factor-db/factors/{id}/distribution 分布统计   │
│  /api/factor-db/factors/{id}/export  CSV/Excel 导出  │
│  /api/factor-db/dictionary       数据字典下载        │
└───────┬─────────────────────────────┬───────────────┘
        │                             │
┌───────▼──────────┐   ┌──────────────▼───────────────┐
│ 因子元数据层      │   │ 因子值数据层（QuantApiClient）│
│ metadata JSON    │   │ → Quant API v2 factor_monthly│
│ (134 因子，版本化)│   │ → 本地 parquet 缓存（阶段1）  │
└──────────────────┘   │ → RQData 异步拉取（阶段1）    │
                       └──────────────────────────────┘
```

### 5.2 数据获取

- **33 因子月频**：`GET {QUANT_API}/factor_monthly?factor=X&symbol=Y`（JSON，小数据）/ `?factor=X`（全量 41.9 万行）
- **Alpha101 因子值**：`POST /admin/pull`（异步 job，5-10 秒/因子）→ `GET /admin/pull/jobs/{id}/download/{file}`
- **日 K 等基础行情**：`GET /ch/ods_kline_1d/parquet?start_date=&end_date=`（Parquet 流式）

### 5.3 数据清洗

沿用 factor_lab 既有口径（`research_core/factor_lab/operators.py`）：

1. **缺失值**：停牌/涨跌停导致的 NaN 保留（不前向填充，避免引入前视偏差）
2. **异常值**：阶段 2 引入 MAD winsorize（默认 3 倍 MAD，可配置），导出时提供 raw/winsorized 双口径
3. **对齐**：`trade_date` + `symbol` 双键对齐；复权采用后复权（qfq 因子表 `ods_adj_factor_daily`）

### 5.4 因子计算

- 复用 `compute_quant_api_33_factors()` / `compute_alpha101_factors()`，本地可重算（与远端数据交叉验证）
- 新因子经 factor_lab intake 流程（G0~G13 门禁）后入目录

### 5.5 存储

| 层 | 载体 | 说明 |
|---|---|---|
| 元数据 | `research_core/factor_db/metadata/*.json`（版本化于 git） | 单一事实源 |
| 因子值缓存 | `runtime/factor_db/cache/*.parquet` | 阶段 1 落地，TTL 策略 |
| 远端真值 | ClickHouse `factor_monthly` / `factor_ic` | 已存在 |

---

## 6. 质量控制方案

### 6.1 数据准确性校验

| 机制 | 说明 | 现状 |
|---|---|---|
| Truth-compare | 与外部真值比对：`overlap_ratio ≥ 0.9`、`exact_match_ratio ≥ 0.99`、`tolerance 1e-8` | ✅ factor_lab 已有（`validation_gate.py`），阶段 2 接入 |
| 重算比对 | 本地 `compute_*` 重算 vs 远端值，逐样本误差 | 阶段 2 |
| 逻辑校验 | 值域检查（如 up_ratio_1m ∈ [0,1]、debt_to_asset ≤ 1 常规应满足） | ✅ 阶段 0 内置于分布端点 |

### 6.2 完整性检查

- 覆盖率：每期截面股票数 / 全A 数，阈值 ≥ 90%
- 缺失率：每因子月度缺失率，> 5% 告警
- 时序连续性：月频应逐月有值，断档检测

### 6.3 异常值处理

- 分布统计端点输出：count / mean / std / min / p25 / p50 / p75 / max / 偏度 / 峰度 / NaN 率
- 超出 p1/p99 的样本在可视化中单独标记
- 导出支持 `?winsorize=mad3` 参数（阶段 2）

### 6.4 质量评分（阶段 2）

`quality_score = 0.4×accuracy + 0.3×completeness + 0.3×stability`，入库元数据展示。

---

## 7. 风险评估

| # | 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|---|
| R1 | Quant API token 权限变更/失效 | 中 | 高（数据断供） | 元数据与计算引擎本地自治；token 由后端环境变量注入，不进前端 |
| R2 | RQData 拉取慢（101 因子 × 76 月） | 高 | 中（阶段 1 延期） | 异步 job + 并发 2 + 分批入库，先 33 因子保底 |
| R3 | Alpha101 元数据质量参差（批量生成） | 中 | 中 | 生成后人工抽检 10%；详情页标注"自动生成"标识 |
| R4 | Excel 导出依赖（openpyxl）缺失 | 低 | 低 | 运行时探测，缺失时降级 CSV 并提示 |
| R5 | 因子口径分歧（复权/ST/停牌处理） | 中 | 中 | 元数据 `cautions` 字段显式记录口径；truth-compare 把关 |
| R6 | 单人开发瓶颈 | 中 | 中 | 智能体流水线（Skill）承担重复劳动；阶段 0 产物全部脚本化可再生 |

---

## 8. 后续迭代计划（阶段 3+ 路线图）

| 迭代 | 主题 | 关键特性 |
|---|---|---|
| v0.2 | 数据扩充 | GTJA191（191 因子）、Alpha158、Barra 风格因子元数据；日频因子值 |
| v0.3 | 研究增强 | 因子 IC/IR 时序、相关性矩阵、因子正交化、行业中性化预处理 |
| v0.4 | 服务化 | 用户体系（Supabase RLS）、API 限流、Python SDK、Webhook 数据更新通知 |
| v0.5 | 智能化 | 自然语言因子检索（接入 document_normalizer）、因子自动发现流水线（mining_bridge） |

---

## 9. 交付物清单（本期阶段 0）

| # | 交付物 | 路径 | 状态 |
|---|---|---|---|
| 1 | 交付方案文档（本文件，含计划/资源/风险） | `docs/FACTOR_DB_DELIVERY_PLAN.md` | ✅ |
| 2 | 产品雏形——Web 系统 | `frontend/factor-db/`（index.html / app.js / styles.css） | ✅ |
| 3 | 产品雏形——API 接口 | `research_core/factor_db/api.py` | ✅ |
| 4 | 初始因子库（134 因子元数据） | `research_core/factor_db/metadata/` | ✅ |
| 5 | 数据字典及使用说明 | `docs/FACTOR_DB_DICTIONARY.md` | ✅ |
| 6 | 技术实现文档及维护指南 | `docs/FACTOR_DB_TECHNICAL.md` | ✅ |

---

## 10. 验收演示脚本（阶段 0）

```powershell
# 1. 启动服务（仓库根目录）
$env:FACTOR_LAB_QUANT_API_TOKEN="sk-..."   # 可选，配置后可查真实数据
python -X utf8 -m research_core.factor_db.api --port 8013

# 2. 浏览器打开
#    http://127.0.0.1:8013/factor-db/
#    → 搜索 "ROE" / 筛选 "基本面因子" → 详情页查看 LaTeX 公式
#    → 分布图 → 导出 CSV

# 3. API 调用
curl http://127.0.0.1:8013/api/factor-db/factors?category=基本面因子
curl http://127.0.0.1:8013/api/factor-db/factors/QAPI33:roe_ttm
curl "http://127.0.0.1:8013/api/factor-db/factors/QAPI33:roe_ttm/distribution"
curl -o roe.csv "http://127.0.0.1:8013/api/factor-db/factors/QAPI33:roe_ttm/export?format=csv"
```
