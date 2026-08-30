# A股因子数据库 — 数据字典及使用说明

> 版本：v0.1（阶段 0 产品雏形） · 更新日期：2026-08-28
> 配套交付方案：[FACTOR_DB_DELIVERY_PLAN.md](./FACTOR_DB_DELIVERY_PLAN.md) · 技术文档：[FACTOR_DB_TECH_GUIDE.md](./FACTOR_DB_TECH_GUIDE.md)

## 1. 产品概览

A股因子数据库（Factor DB）是面向量化研究流程的因子元数据与因子值数据服务，当前版本包含 **134 个因子**：

| 来源 | 数量 | 数据频率 | 因子值数据状态 |
|---|---|---|---|
| Quant API 33 因子（QAPI33） | 33 | 月频 | 实时可查（经 Quant API v2，41.9 万行 × 76 月） |
| WorldQuant Alpha101（ALPHA101） | 101 | 日频（计算） | 元数据+公式就绪；因子值待 RQData 拉取任务生成（阶段 1） |

因子分类分布：技术因子 120 · 基本面因子 8 · 基础因子 6。

## 2. 快速开始

### 2.1 启动服务

```bash
# 仓库根目录执行
python -X utf8 -m research_core.factor_db.api --port 8013
```

启动后：

- Web 界面：<http://127.0.0.1:8013/factor-db/>
- API 根路径：<http://127.0.0.1:8013/api/factor-db/factors>
- 健康检查：<http://127.0.0.1:8013/health>

### 2.2 配置数据 Token（查询真实因子值）

```bash
# Windows PowerShell
$env:FACTOR_LAB_QUANT_API_TOKEN = "<your-token>"   # 或 QUANT_API_TOKEN
```

未配置 token 时：因子目录 / 详情 / 公式 / 演示分布 / 元数据导出均可用；
真实因子值查询与真实分布统计返回 401。前端可勾选「演示模式」查看分布形态。

## 3. Web 界面使用

| 功能 | 入口 | 说明 |
|---|---|---|
| 因子检索 | 左侧搜索框 | 匹配中文名 / 英文名 / factor_id / 定义 / 公式，200ms 防抖 |
| 分类过滤 | 左侧大类/来源标签 | 基础 / 技术 / 基本面 × Quant API / Alpha101 |
| 因子详情 | 点击因子条目 | 元数据、定义、计算逻辑、LaTeX 公式（KaTeX 渲染）、伪代码表达式 |
| 因子分布 | 详情页「因子分布」 | 直方图 + P25/P50/P75 分位线 + 12 项统计指标 |
| 数据导出 | 详情页按钮 / 页脚 | 因子值 CSV/Excel、元数据 CSV、全量数据字典 CSV/Excel |

## 4. API 使用说明

所有端点前缀 `/api/factor-db`。factor_id 形如 `QAPI33:roe_ttm`、`ALPHA101:alpha1`（URL 中冒号可直接使用，或 `%3A` 编码）。

### 4.1 端点一览

| 端点 | 方法 | 参数 | 说明 |
|---|---|---|---|
| `/stats` | GET | — | 目录统计（总数/分类/来源分布） |
| `/factors` | GET | `category` `subcategory` `source` `search` `limit` `offset` | 因子列表检索 |
| `/factors/{factor_id}` | GET | — | 因子完整详情（含 LaTeX 公式） |
| `/factors/{factor_id}/values` | GET | `symbol` `date` `limit` | 因子值（真实数据，需 token） |
| `/factors/{factor_id}/distribution` | GET | `demo` `bins` | 分布统计+直方图（`demo=1` 免 token） |
| `/factors/{factor_id}/export` | GET | `format=csv\|xlsx` `scope=values\|meta` `symbol` `date` | 数据导出 |
| `/dictionary` | GET | `format=json\|csv\|xlsx` | 全量数据字典 |
| `/quant-api/status` | GET | `remote` | 数据源状态（`remote=1` 附带远端健康检查） |

### 4.2 调用示例

```bash
# 搜索动量类因子
curl "http://127.0.0.1:8013/api/factor-db/factors?search=momentum"

# 因子详情（含 LaTeX 公式）
curl "http://127.0.0.1:8013/api/factor-db/factors/QAPI33:roe_ttm"

# 查询平安银行 ROE 时序（需 token）
curl "http://127.0.0.1:8013/api/factor-db/factors/QAPI33:roe_ttm/values?symbol=000001.SZ"

# 演示分布（无需 token）
curl "http://127.0.0.1:8013/api/factor-db/factors/QAPI33:roe_ttm/distribution?demo=1"

# 导出因子值 Excel
curl -OJ "http://127.0.0.1:8013/api/factor-db/factors/QAPI33:roe_ttm/export?scope=values&format=xlsx"

# 下载数据字典
curl -OJ "http://127.0.0.1:8013/api/factor-db/dictionary?format=csv"
```

Python 调用：

```python
import requests

base = "http://127.0.0.1:8013/api/factor-db"
# 检索
rows = requests.get(f"{base}/factors", params={"category": "基本面因子", "search": "roe"}).json()
# 详情
detail = requests.get(f"{base}/factors/QAPI33:roe_ttm").json()
print(detail["formula_latex"])   # ROE_{ttm,t} = \frac{NP_{ttm,t}}{E_{t}}
```

### 4.3 错误码约定

| 状态码 | 含义 |
|---|---|
| 401 | Quant API token 未配置 |
| 404 | 因子不存在 / 截面无有效数据 |
| 425 | 因子元数据就绪但因子值数据未生成（Alpha101 阶段 1 前） |
| 502 | 远端 Quant API 不可达或返回异常 |

## 5. 因子元数据字段（数据字典 schema）

| 字段 | 类型 | 说明 |
|---|---|---|
| `factor_id` | string | 唯一标识符，`{来源前缀}:{因子名}` |
| `name_cn` / `name_en` | string | 中文名 / 英文名 |
| `category` | string | 大类：基础因子 / 技术因子 / 基本面因子 |
| `subcategory` | string | 子类（如 盈利能力 / 动量 / 波动率 / 横截面排序） |
| `data_source` | string | 数据来源 |
| `frequency` | string | 数据频率（月频 / 日频） |
| `coverage` | string | 覆盖范围（股票池口径） |
| `history_start` | string | 历史数据起始时间 |
| `definition` | string | 因子定义 |
| `calc_logic` | string | 计算逻辑（窗口、复权、PIT 口径说明） |
| `formula_expr` | string | 伪代码表达式 |
| `formula_latex` | string | LaTeX 数学公式 |
| `logic_notes` | string | 逻辑说明 |
| `application` | string | 应用场景 |
| `cautions` | string | 注意事项（口径陷阱、行业偏差等） |

完整字典可随时导出：

```bash
curl -OJ "http://127.0.0.1:8013/api/factor-db/dictionary?format=csv"    # CSV（带 BOM，Excel 直开）
curl -OJ "http://127.0.0.1:8013/api/factor-db/dictionary?format=xlsx"   # Excel
```

## 6. 因子清单

### 6.1 Quant API 33 因子（月频，因子值实时可查）

| factor_id | 中文名 | 子类 | 频率 | 一句话定义 |
|---|---|---|---|---|
| QAPI33:asset_turnover | 总资产周转率（TTM） | 运营效率 | 月频 | TTM 营业收入与总资产之比，衡量资产的运营效率 |
| QAPI33:debt_to_asset | 资产负债率 | 杠杆水平 | 月频 | 总负债与总资产之比，衡量财务杠杆水平与偿债压力 |
| QAPI33:eps_yoy | 每股收益同比增长率 | 成长性 | 月频 | 最新报告期每股收益相对上年同期的增长率 |
| QAPI33:net_margin | 销售净利率（TTM） | 盈利能力 | 月频 | TTM 归母净利润与 TTM 营业收入之比，衡量每单位收入的利润留存 |
| QAPI33:profit_yoy | 净利润同比增长率 | 成长性 | 月频 | 最新报告期归母净利润相对上年同期的增长率 |
| QAPI33:revenue_yoy | 营业收入同比增长率 | 成长性 | 月频 | 最新报告期营业收入相对上年同期营业收入的增长率 |
| QAPI33:roa_ttm | 总资产收益率（TTM） | 盈利能力 | 月频 | 滚动十二个月归母净利润与总资产之比，衡量全部资产的使用效率 |
| QAPI33:roe_ttm | 净资产收益率（TTM） | 盈利能力 | 月频 | 滚动十二个月归母净利润与归属股东权益之比，衡量股东资本的盈利效率 |
| QAPI33:avg_amount_1m | 月均成交额 | 流动性 | 月频 | 过去 21 个交易日（约 1 个月）日成交额的均值，衡量交易活跃度与流动性规模 |
| QAPI33:illiquidity | Amihud 非流动性 | 流动性 | 月频 | Amihud (2002) 非流动性指标：单位成交额引起的价格变动，衡量价格冲击成本 |
| QAPI33:log_amount_1m | 对数成交额 | 流动性 | 月频 | 月均成交额的自然对数，将长尾分布的成交额转换为近似正态的横截面分布 |
| QAPI33:log_price | 对数价格 | 价格 | 月频 | 股票后复权收盘价的自然对数，刻画价格水平的量级 |
| QAPI33:turnover_proxy | 换手率代理 | 流动性 | 月频 | 当日成交量相对过去一年平均成交量的比值，代理异常换手热度 |
| QAPI33:volume_ratio | 量比（5日/21日） | 流动性 | 月频 | 近 5 日平均成交量与近 21 日平均成交量之比，衡量短期量能变化方向 |
| QAPI33:amplitude_1m | 1月日均振幅 | 波动率 | 月频 | 过去 21 日日内振幅（高低价差/收盘价）的均值，刻画日内多空分歧强度 |
| QAPI33:bb_position | 布林带位置 | 技术指标 | 月频 | 收盘价在 20 日均值±2倍标准差布林带通道中的相对位置，值域通常 [0,1] |
| QAPI33:high_low_1m | 1月振幅 | 波动率 | 月频 | 过去 21 日最高价与最低价之比减一，价格通道宽度 |
| QAPI33:ma_signal | 均线偏离信号 | 技术指标 | 月频 | 收盘价相对 20 日均线的偏离率，衡量短期价格与中期趋势的乖离程度 |
| QAPI33:max_ret_1m | 1月最大单日收益（彩票偏好） | 波动率 | 月频 | 过去 21 个交易日内单日收益率的最大值 |
| QAPI33:min_ret_1m | 1月最小单日收益 | 波动率 | 月频 | 过去 21 个交易日内单日收益率的最小值 |
| QAPI33:momentum_12_1 | 12-1 动量（剔除近月） | 动量 | 月频 | 经典学术动量定义：t-21 日至 t-252 日的收益率，即 12 个月动量剔除最近 1 个月 |
| QAPI33:ret_12m | 12月收益率 | 动量 | 月频 | 过去 252 个交易日（约一年）的区间收益率 |
| QAPI33:ret_1m | 1月收益率（短动量） | 动量 | 月频 | 过去 21 个交易日的区间收益率 |
| QAPI33:ret_3m | 3月收益率 | 动量 | 月频 | 过去 63 个交易日（约一季度）的区间收益率 |
| QAPI33:ret_3m_vol_adj | 波动率调整动量 | 动量 | 月频 | 3 月收益率除以 3 月波动率，即收益的夏普式标准化（信息比率形态的动量） |
| QAPI33:ret_6m | 6月收益率 | 动量 | 月频 | 过去 126 个交易日（约半年）的区间收益率 |
| QAPI33:reversal | 1月反转 | 反转 | 月频 | 1 月收益率的相反数，A 股最强的异象之一：短期超跌的股票未来倾向于反弹 |
| QAPI33:rsi_14 | 14日相对强弱指标（RSI） | 技术指标 | 月频 | Wilder 相对强弱指标：上涨动量与下跌动量之比的归一化表达，值域 [0,100] |
| QAPI33:up_ratio_1m | 1月上涨天数占比 | 波动率 | 月频 | 过去 21 个交易日中上涨天数的占比，值域 [0,1] |
| QAPI33:vol_convergence | 波动率收敛比 | 波动率 | 月频 | 短期波动率与中期波动率之比，捕捉波动率状态的变化方向 |
| QAPI33:volatility_1m | 1月波动率 | 波动率 | 月频 | 过去 21 个交易日日收益率的标准差，衡量短期价格波动水平 |
| QAPI33:volatility_3m | 3月波动率 | 波动率 | 月频 | 过去 63 个交易日日收益率的标准差，中期波动水平 |
| QAPI33:volatility_6m | 6月波动率 | 波动率 | 月频 | 过去 126 个交易日日收益率的标准差，长期波动水平 |

### 6.2 WorldQuant Alpha101（日频，共 101 个）

- 标识符：`ALPHA101:alpha1` … `ALPHA101:alpha101`
- 大类：技术因子；子类按主要算子自动归类：横截面排序 / 时序排序 / 价量相关性 / 价量协方差 / 衰减加权量价 / 行业中性量价 / 复合量价
- 公式与描述直接来自本仓库 factor_lab Alpha101 规格（单一事实源，随仓库自动更新）
- 因子值数据需经 RQData 拉取任务生成（交付方案阶段 1），当前查询返回 425 状态码
- 完整 101 因子明细见 API：`/api/factor-db/factors?source=ALPHA101&limit=200`

### 6.3 基础因子（6 个）

| factor_id | 中文名 | 说明 |
|---|---|---|
| QAPI33:log_price | 对数价格 | 价格量级 |
| QAPI33:avg_amount_1m | 月均成交额 | 流动性规模 |
| QAPI33:log_amount_1m | 对数成交额 | 流动性规模（正态化） |
| QAPI33:volume_ratio | 量比（5日/21日） | 量能变化 |
| QAPI33:turnover_proxy | 换手率代理 | 换手热度 |
| QAPI33:bb_position | 布林带位置 | 通道位置 |

> 注：基础因子与技术因子按用途划分——同一因子在「基础量价描述」语境下列入基础因子，在「信号构建」语境下列入技术因子。本库以子类字段区分用途，大类归属见 `/stats`。

## 7. 常见问题

**Q: 导出的 CSV 用 Excel 打开中文乱码？**
A: 不会。CSV 导出统一使用 `utf-8-sig`（带 BOM）编码，Excel 可直接打开。

**Q: Alpha101 因子值什么时候可查？**
A: 阶段 1（见交付方案）通过 RQData 异步拉取任务生成后开放，届时 `/values` 与 `/distribution` 自动切换为真实数据，无需改代码。

**Q: token 放在哪里安全？**
A: 通过环境变量 `FACTOR_LAB_QUANT_API_TOKEN` 注入后端进程，API 响应、导出文件、前端页面中均不出现凭证。

**Q: 如何把 Factor DB 挂到已有的 factor_lab_api 服务？**
A: `from research_core.factor_db.api import factor_db_bp; app.register_blueprint(factor_db_bp)`（详见技术文档第 3 节）。
