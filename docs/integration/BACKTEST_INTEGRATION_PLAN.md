# 晨曦引擎 Integration Plan

## Goal

Connect 晨曦引擎 to AgentMatrix through the
canonical `BacktestRequest` and `BacktestResult` contracts without changing the
legacy trading algorithm in the first phase.

## Phase 1: compatibility bridge

- Run the desktop engine in a subprocess so its global `config` and `sys.path`
  mutations cannot contaminate the AgentMatrix API process.
- Map its Quant Desk-shaped output into `contracts.backtest.BacktestResult`.
- Keep the desktop source untouched so old and new entry points can be compared.
- Cover validation and result mapping with tests that do not require market data.

## Phase 2: real-data parity

- Point the bridge at the approved Parquet dataset.
- Run `红利策略v6(聚宽对齐)` through both the old command and AgentMatrix.
- Compare NAV, metrics, holdings, trades, and fees.
- Record every intentional difference before changing execution logic.

## Phase 3: internalize the engine

- Move the verified engine implementation into AgentMatrix.
- Replace global configuration with request-scoped configuration.
- Remove the external desktop path and subprocess compatibility bridge only
  after parity tests pass.

## Phase 4: strategy library dashboard

- Make the dashboard entry point a ranked library of strategies rather than a
  selector for one result.
- Open a strategy detail page from a library card; keep NAV, drawdown,
  positions, and trades behind that selection.
- Admit only completed canonical `BacktestResult` artifacts. Do not mix legacy
  mock/cache payloads into the production library.
- Keep the latest result per strategy in the library and report how many
  persisted runs exist for that strategy.
- Populate additional cards only after those strategies have been run through
  the unified engine and their result artifacts have passed validation.

## Current constraints

- The checked desktop engine directory does not currently contain its `data/`
  directory, so a real strategy run needs an explicit approved data path.
- The legacy engine currently fixes some execution settings through global
  configuration. The bridge reports these limitations instead of pretending
  every `BacktestRequest` field was honored.

## Error log

| Date | Attempt | Result | Resolution |
|---|---|---|---|
| 2026-08-06 | Run dividend-v6 through `run-custom` | Reached the legacy `BacktestEngine`, then failed because `data/kline/kline_*.parquet` was absent | Obtain the approved existing Parquet data path and rerun with `--data-dir` |
| 2026-08-06 | Prepare a compatible server-side dataset | Index Parquet restored `order_book_id` as a Pandas index, causing `KeyError` | Reset the named index before selecting CSI300 and rerun the idempotent preparation |
| 2026-08-06 | Load the verified package through the desktop engine | Source calendar used `date`; legacy engine requires `trade_date` | Normalize the calendar column in the server-side preparation script and refresh its manifest |
| 2026-08-06 | Complete the first real dividend-v6 bridge run | Legacy engine tried to write its rebalance CSV into the read-only desktop project | Redirect legacy artifacts to the bridge subprocess temporary directory; keep the desktop project untouched |
| 2026-08-07 | Read-only server audit with SSH key authentication | Server rejected the local key and required password authentication | Use the previously authorized account for the audit; do not persist credentials in the repository or logs |
| 2026-08-07 | Invoke daily runner as `python scripts/run_daily_strategies.py` | Python placed `scripts/`, not the repository root, on `sys.path` and could not import `contracts` | Bootstrap the resolved repository root before project imports so cron and direct invocation behave consistently |
| 2026-08-07 | Bind the minimal Flask app during sandboxed validation | Managed sandbox denied local socket binding | Validate with Flask's test client locally; bind only in the already authorized server isolation environment |
| 2026-08-07 | Reuse the server's RQSDK Conda environment for the dashboard | The ETL environment has pandas/pyarrow but does not include Flask | Create an isolated strategy-system virtual environment; do not modify the existing ETL environment |
| 2026-08-07 | Run the combined dashboard test module on the isolated server release | Test collection imported the monolithic Factor Lab API and hit a pre-existing export mismatch before reaching the minimal app tests | Split production dashboard tests from Factor Lab compatibility tests; validate the minimal app independently on the server |
| 2026-08-07 | Start smoke service through `/home/data/agentmatrix-strategy/current` | The prior `set -e` test failure correctly stopped before creating the release symlink | Create the symlink explicitly after the corrected tests are present, then rerun validation |
| 2026-08-07 | Inspect index maximum date with `pandas.read_parquet(columns=['date'])` | The index dataset stores `date` through Parquet/Pandas index metadata, so Pandas did not expose it as a normal selected column | Read the physical Arrow column directly and calculate its maximum with `pyarrow.compute` |
| 2026-08-07 | Run dividend-v6 in the isolated production virtual environment | The legacy engine imports `requests`, which was absent from the minimal dashboard dependency set | Declare `requests` as an explicit compatibility-engine runtime dependency and rerun the quarantined job |
| 2026-08-07 | Review the first full-period dividend-v6 candidate | It produced a flat NAV and zero trades because historic `dividend_yield` files are basis points, while the legacy strategy divided them as percentages | Normalize legacy basis points by 10,000 and current TTM decimal values unchanged in a new immutable dataset revision; strengthen empty-strategy quality gates |
| 2026-08-07 | Assert current decimal dividend normalization by first row | Normalization sorts by symbol, so the first row was not the target symbol | Assert by stable symbol key rather than row position |
| 2026-08-07 | Run the daily job from the first expedited release package | The focused archive omitted top-level `registry` and the adapter's eager import chain failed before backtesting | Restore `registry` and `data_layer` from the preceding complete release, verify adapter import, and include both in future release manifests |

## Phase 5: production server loop

- Audit the server without modifying existing services or datasets.
- Package AgentMatrix, the compatibility engine, and runtime configuration as a
  self-contained release with explicit paths.
- Complete a manual server-side run before introducing scheduling.
- Add data-ready detection, quality gates, atomic publication, retry, and
  observability.
- Run the API behind a production WSGI service; add reverse proxy, TLS, and
  public access only after the isolated deployment passes acceptance checks.

## Phase 6: incremental core replacement

- Keep `BacktestRequest` and `BacktestResult` stable while replacing internals.
- Replace the legacy metric calculation and portfolio accounting first, using
  deterministic ledger tests and parity reports.
- Replace data access and execution simulation next; migrate strategies one at
  a time rather than forcing a coordinated rewrite.
- Remove the subprocess bridge only after all production strategies pass the
  agreed parity tolerances on pinned datasets.
