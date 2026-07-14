# FactorResearchSpec 字段理解笔记

> Week 1 Day 3 产出

## 一、FactorResearchSpec 是什么

一个 Python dataclass（定义在 `contracts/factor_research.py:16`），18 个字段，描述一个因子的**全部元信息**。不包含计算逻辑（计算在 `factors.py` 里），只包含"这个因子是什么、需要什么、怎么验证"。

## 二、18 个字段详解

### 1. factor_name — 唯一标识符
- **类型**: `str`
- **示例**: `"market_cap"`, `"pe_ttm"`
- **规则**: 全小写、下划线分隔、在库内唯一
- **jq_gm 映射**: 直接用 FACTOR_REGISTRY 的 key

### 2. library — 所属因子库
- **类型**: `str`
- **示例**: `"jq_gm"`, `"Alpha101"`
- **作用**: 分类归属，CLI 用这个区分不同库

### 3. version — 版本号
- **类型**: `str`
- **示例**: `"v2026.06"`
- **作用**: 追踪 Spec 格式演进

### 4. display_name — 显示名
- **类型**: `str`（默认 `""`)
- **示例**: `"总市值"`, `"市盈率TTM"`
- **jq_gm 映射**: FACTOR_REGISTRY 的 `'name'` 字段

### 5. factor_id — 外部 ID
- **类型**: `str`（默认 `""`)
- **示例**: `"WQ101_001"`
- **作用**: 关联外部因子编号体系。jq_gm 暂不填。

### 6. source_document — 来源文献
- **类型**: `str`（默认 `""`)
- **示例**: `"JoinQuant Factor Board Taxonomy — GM SDK Implementation"`
- **作用**: 因子的出处，审计/引用用

### 7. formula — 公式表达式 ★
- **类型**: `str`（默认 `""`)
- **示例**: `"tot_mv"`, `"TTM(inc_oper)"`
- **作用**: validation.py 的 `formula_match` 检查此字段非空即通过
- **jq_gm 映射**: 从 `gm_fields` 推导；简单字段就是字段名本身，TTM 因子标注 `TTM(...)`

### 8. description — 说明
- **类型**: `str`（默认 `""`)
- **示例**: `"总市值 = 总股本 × 收盘价"`
- **jq_gm 映射**: FACTOR_REGISTRY 的 `'desc'` 字段

### 9. frequency — 频率
- **类型**: `str`（默认 `"day"`)
- **示例**: `"day"`, `"month"`, `"quarter"`
- **jq_gm**: 全部是 `"day"`（日频因子）

### 10. sample_scope — 股票池范围
- **类型**: `str`（默认 `""`)
- **示例**: `"A-share standard pool; remove ST, delisted..."`
- **作用**: 定义因子适用的股票池，PT/ST 剔除规则

### 11. required_fields — 计算所需字段 ★
- **类型**: `list[str]`（默认 `[]`)
- **示例**: `["tot_mv"]`, `["close", "volume"]`
- **作用**: validation.py 检查这些字段是否在数据面板中存在
- **jq_gm 映射**: 从 `gm_fields` 拆分（逗号分隔 → 列表）

### 12. parameters — 参数
- **类型**: `dict[str, Any]`（默认 `{}`)
- **示例**: `{"window": 20}`
- **作用**: 滚动窗口、滞后期数等可调参数

### 13. preprocessing — 预处理步骤
- **类型**: `list[str]`（默认 `[]`)
- **示例**: `["adjust_prices", "align_trading_calendar"]`
- **作用**: 声明数据需要什么预处理。jq_gm 价格因子需要复权+交易日历。

### 14. neutralization — 中性化处理
- **类型**: `list[str]`（默认 `[]`)
- **示例**: `["industry", "size"]`
- **作用**: 因子是否做了行业/市值中性化。jq_gm 大部分不改。

### 15. validation_targets — 验证阈值 ★
- **类型**: `list[ValidationThreshold]`（默认 `[]`)
- **结构**: `{metric, operator, value, description}`
- **示例**: 
  ```
  {metric: "formula_match_ratio", operator: ">=", value: 1.0}
  {metric: "field_mapping_match_ratio", operator: ">=", value: 1.0}
  {metric: "sample_point_error_ratio", operator: "<=", value: 0.0}
  {metric: "cross_section_spearman", operator: ">=", value: 0.99}
  ```
- **作用**: proof-batch 判断因子是否"验证通过"的标准

### 16. tags — 分类标签
- **类型**: `list[str]`（默认 `[]`)
- **示例**: `["基础科目及衍生类因子", "valuation"]`
- **jq_gm 映射**: category 作为第一个 tag

### 17. notes — 备注
- **类型**: `list[str]`（默认 `[]`)
- **示例**: `["TTM 需自行累加。"]`, `["v49 修正字段名。"]`
- **作用**: 实现注意事项、历史修正记录

### 18. metadata — 扩展信息
- **类型**: `dict[str, Any]`（默认 `{}`)
- **jq_gm 特有字段**:
  - `gm_field`: GM API 端点名 (`"stk_get_daily_mktvalue_pt"`)
  - `gm_fields`: 字段名 (`"tot_mv"`)
  - `status`: `"implemented"`
  - `implementation_stage`: `"code"`

## 三、与 FACTOR_REGISTRY 的映射关系

```
FACTOR_REGISTRY[factor_key]      FactorResearchSpec
─────────────────────────────    ──────────────────
key (如 'market_cap')          → factor_name
'name'                         → display_name
'category'                     → tags[0]
'desc'                         → description
'gm_field'                     → metadata.gm_field
'gm_fields'                    → formula (简单字段) / required_fields (拆分)

需要补的字段:
  library      → 固定 "jq_gm"
  version      → 固定 "v2026.06"
  frequency    → 固定 "day"
  source_document → 固定来源声明
  sample_scope → 固定 A 股票池描述
  validation_targets → 统一 4 项目标
  preprocessing → 价格因子需要复权、财务因子不需要
  tags         → category + 可选额外标签
  notes        → 从 desc 中提取版本修正记录
  metadata     → status + implementation_stage + 原始 gm_field/gm_fields
```

## 四、alpha101 Spec 与 jq_gm Spec 的关键差异

| 维度 | alpha101 | jq_gm |
|------|---------|-------|
| 因子类型 | 数学公式（纯表达式） | 财务/估值字段（调 API 取值） |
| formula | 复杂表达式如 `(rank(Ts_ArgMax(...)) - 0.5)` | 字段名如 `tot_mv` |
| required_fields | `["close"]` 等基础行情字段 | GM API 字段名如 `["tot_mv"]` |
| metadata | 只有 status | status + gm_field + gm_fields |
| 真值数据 | 无（proof 都是 pending） | 有 JQ 真值 CSV |
| compute 依赖 | Qlib 表达式解释器 | 掘金 SDK |
