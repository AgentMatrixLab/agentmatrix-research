# Week 1 Day 5 — 周一例会问题清单

> 待确认 · 后续版本回头处理

## 格式层面

### Q1: required_fields 的隐式依赖
**现状**: `market_cap` 的 `required_fields = ["tot_mv"]`，但实际计算时还需要 `close` 做复权推导。Alpha101 的惯例是只写直接输入字段，不写隐式依赖。
**待确认**: jq_gm 是否同样处理？还是必须列出所有依赖？
**标记**: [P2] 不影响管线跑通，但影响"读 Spec 就能独立实现计算"的目标。

### Q2: preprocessing 是否需要按路由细分
**现状**: 所有因子统一用 `["adjust_prices", "align_trading_calendar"]`。但财务因子（income_pt, balance_pt）不涉及价格数据，复权对其无意义。
**待确认**: 是否需要按 `gm_field` 路由类型设置不同的 preprocessing？
**标记**: [P3] 不影响功能，纯元信息准确性。财务因子的 adjust_prices 不会造成错误（只是冗余声明），但不够精确。

### Q3: gm_field / gm_fields 是否该提升为标准字段
**现状**: 放在 `metadata` 里。jq_gm 之外没有其他库有这个信息（Alpha101 是纯公式）。
**待确认**: 导师是否认为这是通用字段应提升到 Spec 顶层？还是保持 metadata 留给库特有信息？
**标记**: [P2] 取决于导师对 Spec 格式的未来规划。

### Q4: formula 字段的表示约定
**现状**: 三种表示方式混用：
- 直接字段取值 → `"tot_mv"`
- TTM 自算 → `"TTM(inc_oper)"`
- 自定义计算 → `"close / Ref(close, 20) - 1"`
**待确认**: 这三种约定是否足够清晰？需要更结构化的格式（如 JSON schema）吗？
**标记**: [P3] 现有约定可读，但缺乏形式化校验能力。

## 真值数据层面

### Q5: 215 个因子中只有 31 个有真值，其余如何处理
**现状**: 31 个因子有 GM vs JQ 交叉验证结果（MISMATCH=0），可提供真值 CSV。其余 184 个只有 GM 端计算结果，没有对照数据。
**待确认**: CI proof-batch 时，无真值的因子 proof 状态应标 `pending_external_truth` 还是 `not_applicable`？
**标记**: 暂标 Pending，已通过 PR 描述向导师确认

## 来源声明

### Q6: source_document 的措辞是否准确
**现状**: `"JoinQuant Factor Board Taxonomy — GM (掘金) SDK Implementation"`
**待确认**: 是否准确传达了"参考聚宽分类体系、独立用掘金 SDK 实现"的含义？
**标记**: [P3] 措辞问题，不影响技术实现。

## 目录结构

### Q7: jq_gm 的 references/ 目录是否需要
**现状**: alpha101 没有 `references/` 子目录，但 jq_gm 有（架构笔记 + Spec 格式笔记）。
**待确认**: PR 提交时是否需要清理这些开发期文档？还是作为贡献者参考文档保留？
**标记**: [P3] 不影响代码，PR 整理时处理。

---

## 优先级说明

| 等级 | 含义 |
|------|------|
| P1 | 阻塞后续开发，需周一当场明确 |
| P2 | 需要导师意见，但不阻塞 |
| P3 | 可以自定，导师有意见再改 |
