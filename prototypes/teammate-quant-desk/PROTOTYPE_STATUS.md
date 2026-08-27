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

## Local smoke-test findings (2026-08-12)

The frontend type check, production build, and Python syntax compilation pass.
After starting the FastAPI application, the homepage and the strategy,
position, trade, risk, health, and job-list APIs returned HTTP 200. The service
seeded seven synthetic strategies successfully.

The full upload-to-result flow does not pass yet:

| Finding | Observed impact | Recommended resolution |
| --- | --- | --- |
| `python-multipart` is absent from `server/requirements.txt` | FastAPI refuses to start because the upload route uses `UploadFile` | Add a pinned `python-multipart` dependency and cover application startup in CI |
| The README requests `data/kline_1d.parquet`, while the adapter looks for `data/kline_adj.parquet` | A user following the README still receives a missing-file error | Adopt the AgentMatrix dataset manifest and loader; as a short-term compatibility fix, document one canonical filename and validate it during startup |
| Upload validation returns a generated `fileId` but does not persist the source or map it to that ID | The subsequent submission sends only `fileId`, so the worker receives an empty source string | Persist the validated upload in a private immutable submission store, bind it to the authenticated owner and content hash, and resolve it server-side when creating the job |
| No market dataset is included in the prototype | A submitted smoke job failed with a missing K-line file | Point the service to a versioned AgentMatrix dataset; do not commit market data into Git |
| Seeded strategy records and several frontend overview components use synthetic or local mock data | The dashboard can look complete even though the values are not production results | Replace the seed/mock sources with the strategy registry and canonical result APIs; expose clear data provenance in the UI |
| Uploaded Python is executed with in-process `exec` | Public exposure can lead to arbitrary code execution or resource exhaustion | Do not expose this endpoint publicly; prefer reviewed registered strategies, or execute submissions in an isolated worker/container with authentication, quotas, timeouts, and filesystem/network restrictions |
| Benchmark NAV is derived from strategy NAV plus random noise | Alpha, beta, and excess-return presentation is not valid | Load the selected benchmark from the canonical index dataset and align it by trading date |
| Portfolio results are a weighted merge of stored NAV series | Rebalance choice, portfolio transaction costs, and cash accounting are not implemented | Label this as portfolio analysis initially; implement portfolio backtests through the Chenxi Engine and canonical ledger before calling it a backtest |
| The worker is an in-process thread with a process-local concurrency lock | Restarting or horizontally scaling the API can lose or duplicate work | Submit jobs to the existing AgentMatrix durable job store and execute them with the independent Chenxi worker |

Recommended integration order:

1. Keep the frontend navigation and interaction patterns.
2. Replace mock and seed reads with AgentMatrix strategy registry/result APIs.
3. Route parameterized jobs to the existing authenticated backtest API and
   Chenxi worker.
4. Add canonical holdings, trades, benchmark, and risk fields to the result
   contract where needed by these pages.
5. Only then enable reviewed strategy submissions; arbitrary Python uploads
   remain disabled on the public service.

## Repository hygiene

The received `node_modules`, local `.env`, SQLite files, Python caches, and
build outputs are deliberately excluded from this snapshot.

The intended follow-up is to reuse the strongest frontend interactions while
connecting them to the AgentMatrix registry, job API, canonical datasets, and
Chenxi Engine results.
