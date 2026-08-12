# Teammate Quant Desk prototype

This directory preserves the Quant Desk package received from a teammate on
2026-08-12 for review and incremental integration. It is intentionally isolated
from the production AgentMatrix dashboard and backend.

## Included

- React, TypeScript, Vite, Tailwind CSS, and ECharts frontend
- FastAPI and SQLite API prototype
- Backtrader adapter and an in-process backtest queue
- Strategy overview, backtest center, portfolio, positions, trades, and risk
  pages

## Review status

This package is a prototype and must not be deployed as the production Quant
Desk service in its current form:

- Seeded strategy NAV, holdings, trades, and metrics are synthetic.
- Several overview components still read frontend mock data directly.
- The upload endpoint validates source code but does not persist it; the
  subsequent backtest submission therefore does not recover the uploaded
  source code.
- Benchmark series are approximated rather than loaded from benchmark market
  data.
- Portfolio backtests combine existing NAV series and do not implement actual
  portfolio rebalancing or transaction accounting.
- Uploaded Python is executed in-process. Static string checks are not a
  security sandbox, so this endpoint must not be exposed publicly.
- The adapter is not the canonical Chenxi Engine and does not emit the
  AgentMatrix strategy result contract.

## Repository hygiene

The received `node_modules`, local `.env`, SQLite files, Python caches, and
build outputs are deliberately excluded from this snapshot.

The intended follow-up is to reuse the strongest frontend interactions while
connecting them to the AgentMatrix registry, job API, canonical datasets, and
Chenxi Engine results.
