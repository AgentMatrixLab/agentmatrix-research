# Factor Lab 策略看板与 Gate 监控契约草案

状态：前端占位契约。当前没有真实策略层和 Gate 引擎，本文件只定义后续后端应提供的数据形状。

## 边界

- 前端只展示，不触发策略回测、不启动 agent、不执行 gate。
- 当前页面使用 mock 数据渲染，所有收益、夏普、回撤等策略指标均应由后端策略层产出后再展示。
- Gate 监控只展示任务阶段，不替代 proof / truth / evaluation / 回测逻辑。

## strategy_monitor_view_v1

```json
{
  "schema_version": "factor_lab_strategy_monitor_v1",
  "generated_at": "2026-07-02T10:00:00+08:00",
  "data_status": "placeholder | live | stale | error",
  "strategies": [
    {
      "strategy_id": "strategy_single_factor_alpha1",
      "strategy_name": "alpha1 单因子分层策略",
      "strategy_type": "single_factor | multi_factor | portfolio | agent_pipeline",
      "status": "not_connected | research_ready | backtest_ready | review_needed | blocked | failed",
      "source": "Factor Lab",
      "factors": ["WQ101:alpha1"],
      "universe": "中证500",
      "rebalance": "monthly",
      "cost_model": "commission=0.03%, tax=0.05%, slippage=0.1%",
      "metrics": {
        "annual_return": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "turnover": 0.0
      },
      "artifacts": [],
      "updated_at": "2026-07-02T10:00:00+08:00",
      "note": "用于解释当前状态"
    }
  ]
}
```

## gate_monitor_view_v1

```json
{
  "schema_version": "factor_lab_gate_monitor_v1",
  "generated_at": "2026-07-02T10:00:00+08:00",
  "data_status": "placeholder | live | stale | error",
  "tasks": [
    {
      "task_id": "task-alpha101-c015efeba388",
      "task_name": "Alpha101 复现任务",
      "task_type": "factor_reproduction | factor_mining | strategy_backtest | agent_mining",
      "status": "pending | running | passed | warning | failed | blocked | not_implemented",
      "owner": "Agent / CLI / Researcher",
      "current_gate": "G2",
      "updated_at": "2026-07-02T10:00:00+08:00",
      "gates": [
        {
          "gate_id": "G0",
          "name": "输入与规格检查",
          "status": "pending | running | passed | warning | failed | blocked | not_implemented",
          "message": "当前 gate 的说明",
          "metrics": {},
          "artifacts": []
        }
      ],
      "artifacts": []
    }
  ]
}
```

## 推荐 Gate 语义

- G0：输入与规格检查，确认因子定义、参数、数据源声明可读。
- G1：复现产物检查，确认 proof / evaluation / factor_frame 等产物存在且结构正确。
- G2：研究评估检查，承接 IC/IR、OOS、bootstrap、similarity、trial ledger 等研究层校验。
- G3：策略回测检查，承接真实策略层的回测、交易成本、调仓、风险指标。
- G4：人工审核，研究员确认后进入云端信息库或后续策略流程。

当前前端只把这些 Gate 做成可视化节点；真实状态由后端将来写入。
