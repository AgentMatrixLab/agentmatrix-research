# 晨曦引擎兼容桥

The first integration phase preserves 晨曦引擎 and invokes it in an isolated
subprocess. This is deliberate: the compatibility adapter replaces
the process-wide `config` module, which is unsafe inside the AgentMatrix API
process.

## Run

```bash
python -m research_core.backtest_adapter.cli run-custom \
  --engine-root /path/to/晨曦引擎 \
  --data-dir /path/to/parquet-data \
  --strategy '红利策略v6(聚宽对齐)' \
  --strategy-id dividend-v6 \
  --strategy-version v6 \
  --run-id dividend-v6-smoke-001 \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --rebalance-freq 20
```

`--data-dir` must contain the files expected by 晨曦引擎 and strategy,
including adjusted K-line data, financial statements, dividend-yield data,
stock information, and optionally the CSI300 benchmark.

## Contract behavior

- Legacy NAV is returned as AgentMatrix `EquityPoint` records.
- Equity-curve drawdown remains negative; metric maximum drawdown is stored as
  a positive magnitude.
- Quant Desk codes such as `600519` are normalized to `600519.SH`.
- Legacy holdings weights are expected to already be decimals in `[0, 1]`.
- Legacy aggregate `fee` is temporarily mapped to `TradeRecord.commission`.
- Requested fees, slippage, initial cash, and benchmark are passed through, but
  the legacy engine still fixes some of these through global configuration.
  The returned diagnostics disclose this limitation.

## Removal condition

This bridge is temporary. Remove it only after the engine implementation and
approved dataset have moved into AgentMatrix and real-data parity tests pass.
