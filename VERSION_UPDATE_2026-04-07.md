# AgentMatrix Research Core 升级记录

**日期**: 2026-04-07  
**范围**: `agentmatrix-research-core` 首次拆分落地与第二阶段结构重组  
**当前版本基线**: `0911a14` (`refactor: establish research core package structure`)

## 1. 本次升级目的

本次升级的目标是把原先混合在 `agentmatrix-web` 仓库中的研究相关能力，独立沉淀到新的 `agentmatrix-research-core` 仓库中，降低前台网站代码、支付登录逻辑、营销页面对研究系统的语义干扰，提升研究协作效率、Agent 解析准确率和后续模块化演进能力。

## 2. 已完成事项

### 2.1 新仓库建立与远程同步

- 新建 GitHub 仓库：`https://github.com/AgentMatrixLab/agentmatrix-research-core`
- 本地仓库已初始化并连接远程 `origin`
- 主分支统一为 `main`
- 已完成首批迁移提交：`60b8843` `chore: bootstrap research core repository`
- 已完成第二阶段结构重组提交：`0911a14` `refactor: establish research core package structure`

### 2.2 首批迁移进入新仓的模块

#### Document Normalizer / Research Copilot

- 文档标准化 API
- 文档标准化服务
- MinerU 运行时与烟雾测试
- 文档标准化接口测试脚本

#### Data Loader

- `fetch_csi300.py`
- `fetch_csi300_simple.py`
- `check_ak.py`
- `check_ak_recent.py`
- `analyze_fund.py`

#### Strategy Engine

- `etf_agent_engine.py`
- `stock_agent_engine.py`
- `mean_revert_engine.py`
- `grid_master_engine.py`
- `index_sniper_engine.py`
- `etf_rotation_agent.py`
- `reproducibility_agent.py`

#### Test Assets

- `test_docs/` 中的首批测试素材
- `sample_report.pdf`

## 3. 当前目录结构

当前仓库已经建立与新架构图相匹配的基础骨架：

```text
agentmatrix-research-core/
  common/
  deerflow/
    research_copilot/
      document_normalizer/
  research_core/
    data_loader/
    dataset_builder/
    strategy_engine/
    risk_rule_engine/
    backtest_adapter/
    attribution_engine/
  registry/
    factor_registry/
    strategy_registry/
    run_registry/
  contracts/
  data_layer/
    serving_repositories/
  runtime/
  data/
```

## 4. 本次关键重构内容

### 4.1 路径与运行目录解耦

已新增统一路径模块：`common/paths.py`

本次改造的重点是把研究内核从旧网站仓的硬编码路径中解耦出来：

- 不再依赖 `product/website/data`
- 不再把输出默认写回旧的 `agentmatrixlab` 路径
- 文档标准化运行目录从旧的 `backend_runtime` 收敛到新仓自己的 `runtime/document_normalizer`
- 新仓的数据输出统一收敛到 `data/`

### 4.2 Document Normalizer 去前台耦合

`document_normalizer` 已从“网站附属页面能力”开始向“研究内核服务能力”转变：

- 去掉了对 `config.js` 的直接依赖回退逻辑
- 首页响应改为服务状态 JSON，而不是依赖旧前台页面文件
- 静态文件直出逻辑已收缩，避免继续把 research-core 当成 web 容器使用

### 4.3 研究模块重新归位

首批文件已经按职责复制进入新结构：

- DeerFlow 侧：`deerflow/research_copilot/document_normalizer/`
- 研究内核侧：`research_core/data_loader/` 与 `research_core/strategy_engine/`
- 治理层：`registry/`、`contracts/`、`data_layer/` 已建立骨架，等待下一阶段实体化

## 5. 当前仍保留的过渡层

为了避免一次性切断研究员当前工作流，仓库里仍保留了旧目录：

- `backend/`
- `scripts/`

这两个目录目前属于**迁移过渡层**，短期内用于兼容旧路径和降低切换成本。

后续原则：

- 新开发优先放入新结构目录
- 旧目录只做过渡，不再作为长期主结构扩展

## 6. 验证情况

本次重构完成后，已执行语法级校验：

```bash
python -m py_compile common\paths.py deerflow\research_copilot\document_normalizer\api.py deerflow\research_copilot\document_normalizer\service.py deerflow\research_copilot\document_normalizer\mineru_runtime.py deerflow\research_copilot\document_normalizer\smoketest.py deerflow\research_copilot\document_normalizer\api_test.py research_core\data_loader\analyze_fund.py research_core\data_loader\check_ak.py research_core\data_loader\check_ak_recent.py research_core\data_loader\fetch_csi300.py research_core\data_loader\fetch_csi300_simple.py research_core\strategy_engine\etf_agent_engine.py research_core\strategy_engine\etf_rotation_agent.py research_core\strategy_engine\grid_master_engine.py research_core\strategy_engine\index_sniper_engine.py research_core\strategy_engine\mean_revert_engine.py research_core\strategy_engine\reproducibility_agent.py research_core\strategy_engine\stock_agent_engine.py
```

校验结果：通过。

## 7. 对当前线上网站的影响

本次升级**不影响当前网站访问**。

原因：

- 本次所有结构化改造都发生在 `agentmatrix-research-core`
- 当前 `agentmatrix-web` 仓库的站点入口、页面、部署逻辑未被改动
- 现有线上网站继续以当前 web 仓为准运行

## 8. 后续建议动作

### 优先级 P1

- 将新开发任务优先切换到 `research_core/` 与 `deerflow/` 新结构
- 两位研究员后续 PR 以新仓为主，不再继续把研究主逻辑堆回 web 仓
- 明确 `backend/`、`scripts/` 为过渡层

### 优先级 P2

- 抽出 `run_registry` 第一版实体结构
- 抽出 `contracts` 中的 run / artifact / dataset 定义
- 将 `etf_agent_engine` 中的输出契约与运行元数据继续解耦

### 优先级 P3

- 逐步清理新仓中的旧路径兼容副本
- 评估哪些历史数据产物应迁到对象存储或数据库，而不是长期留在 Git
- 在稳定后再考虑从 `agentmatrix-web` 中移除重复 research 文件

## 9. 团队协作建议

- `agentmatrix-web` 继续承接线上网站和前台产品迭代
- `agentmatrix-research-core` 继续承接研究编排、数据处理、策略引擎和研究服务能力
- 与研究内核直接相关的新增代码，默认进入新仓
- 对外页面、登录、支付、展示、运营后台默认留在 web 仓

## 10. 给同事的快速同步结论

一句话总结：

> `agentmatrix-research-core` 已经从“新建空仓”升级成“可开始承接研究开发的独立仓库”，并完成了首批研究模块迁移与结构骨架搭建；当前网站不受影响，后续研究开发应优先在新仓推进。

## 11. 第三阶段启动：策略统一接口 / 回测 / 归因骨架

为支持“先落地网站回测与收益归因，再逐步接入更多策略”的目标，本轮已新增第一版标准化骨架：

### 11.1 Contracts

- `contracts/strategy.py`：统一策略接口、策略元信息、目标仓位和策略决策结构
- `contracts/backtest.py`：统一回测请求、绩效指标、净值曲线、交易记录、持仓快照和回测结果结构
- `contracts/attribution.py`：统一收益归因摘要和贡献桶结构

### 11.2 Backtest Adapter

- `research_core/backtest_adapter/base.py`：回测适配器抽象层
- `research_core/backtest_adapter/gm_adapter.py`：第一版 GM / 掘金回测适配器骨架
- 当前重点是先实现“同一策略代码可规划 GM 回测”的执行计划生成，而不是一次性打通所有真实结果解析

### 11.3 Attribution Engine

- `research_core/attribution_engine/basic.py`：第一版基础收益归因构造器
- 当前版本支持总收益、基准收益、超额收益、费用拖累、滑点拖累、现金拖累，以及按持仓/行业维度的贡献桶输出

### 11.4 策略统一接口方向

当前方向明确为：

- DeerFlow 负责任务编排和状态治理
- `research_core` 负责确定性回测、归因、结果产出
- 掘金量化作为执行与回测落地引擎之一
- 后续可在相同 contracts 下继续接入 Qlib，而不与现有架构冲突

### 11.5 当前定位

这一步仍属于“平台底座建设”，重点是先定义统一数据结构和 GM 兼容回测入口。

后续下一步应继续：

- 选择一个 BigQuant 策略样本进行首版接入
- 将 GM 回测真实输出映射到 `BacktestResult`
- 将网站展示层接到标准化回测结果和收益归因结果

## 12. 首个 GM 可运行样本策略接入

本轮已将一个掘金可运行的小市值月频调仓策略接入到 `research_core/strategy_engine/samples/`，作为首个标准化接入样本。

### 12.1 已完成内容

- 新增样本策略：`research_core/strategy_engine/samples/gm_small_cap_monthly.py`
- GM 适配器已可识别标准掘金策略中的 `init/algo` 结构
- GM 适配器已可从 `if __name__ == '__main__': run(...)` 中提取默认回测参数
- 示例规划脚本已切到仓库内样本策略，不再依赖外部临时策略文件

### 12.2 当前验证结果

通过 `research_core/backtest_adapter/example_gm_plan.py` 已成功得到以下关键信息：

- 可识别策略入口
- 可识别函数列表
- 可提取默认回测起止时间、初始资金、佣金、滑点、撮合模式等配置
- 可生成第一版标准化 GM 回测执行计划

### 12.3 下一步

下一步将基于这个样本继续推进：

- 将真实 GM 回测结果映射到 `BacktestResult`
- 生成第一版网站可展示的绩效指标与收益归因结果
- 再把 BigQuant 策略迁移到相同的统一接口与结果结构

## 13. 第二个 GM 样本：风格轮动策略

本轮已新增第二个 GM 可运行样本策略：research_core/strategy_engine/samples/gm_style_rotation.py。

### 13.1 已完成内容

- 接入风格轮动样本策略
- 将策略中的明文 token 替换为环境变量 GM_TOKEN
- 将示例规划脚本扩展为支持多样本：gm_small_cap_monthly 与 gm_style_rotation

### 13.2 当前验证

可通过以下命令生成风格轮动策略的 GM 执行计划：

python research_core\backtest_adapter\example_gm_plan.py gm_style_rotation

当前可识别：

- init/algo 标准 GM 入口
- run(...) 默认回测参数
- 样本策略文件路径与策略 ID 映射

### 13.3 关于桌面 PDF

已定位桌面文件：C:\Users\admin\Desktop\风格轮动.pdf。

当前自动检测结果显示该 PDF 为单页报告，且文本层极弱，直接抽取文本基本为空，说明它更接近图片化导出报告。它可以作为后续对照样本，但若要做程序化解析，优先建议获取以下任一原始数据：

- 掘金回测详情导出的指标表
- 净值曲线 CSV
- 交易明细 CSV
- 持仓记录或调仓记录

### 13.4 下一步

下一步优先将风格轮动样本的真实回测结果映射到：

- contracts.backtest.BacktestResult
- contracts.attribution.AttributionReport

并形成网站前端首版可展示字段。

## 14. 掘金导出结果解析器首版

本轮已新增首版掘金导出 ZIP 解析能力，可将净值、持仓、交易三类 CSV 映射为标准化回测结果与基础收益归因。

### 14.1 新增模块

- research_core/backtest_adapter/gm_export_parser.py
- research_core/backtest_adapter/example_parse_gm_export.py

### 14.2 当前能力

- 自动识别 ZIP 中的净值数据、持仓数据、交易数据 CSV
- 生成标准化 PerformanceMetrics
- 生成标准化 EquityCurve、TradeRecord、HoldingSnapshot
- 生成基础 AttributionReport
- 可将解析结果写入 data/gm_exports/33_parsed_backtest.json

### 14.3 已完成的真实数据验证

已使用桌面导出包 C:\Users\admin\Desktop\33.zip 验证，导出包包含：

- 持仓数据_20241231_20251231.csv
- 净值数据_20241231_20251231.csv
- 交易数据_20241231_20251231.csv

这三份数据已足够支撑 BacktestResult V1 与 AttributionReport V1。

### 14.4 后续重点

下一步继续补足：

- 更精确的收益归因方法
- 网站前端展示字段映射
- 多策略导出批量解析
