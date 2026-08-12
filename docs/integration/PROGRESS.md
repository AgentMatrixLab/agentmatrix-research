# Backtest Integration Progress

## 2026-08-06

- Added a subprocess-isolated compatibility bridge for the desktop A-share
  engine.
- Added mapping from the legacy Desk payload to AgentMatrix `BacktestResult`.
- Added a `run-custom` CLI entry point.
- Added contract mapping and validation tests.
- Verified seven focused tests, including existing RQAlpha adapter regressions.
- Invoked the real desktop engine entry point with the dividend-v6 strategy.
  Import and dispatch reached `BacktestEngine`; execution then stopped because
  no Parquet data directory exists under the desktop project or indexed local
  paths.

## Current blocker

A real-data parity run requires the team's approved Parquet data directory.
The path must not be guessed or replaced with downloaded data because that
would invalidate comparison with existing results.

## Real-data bridge milestone

- Located the approved source files on `115.159.73.134` and prepared a minimal
  compatibility package from existing Parquet sources without changing source
  data.
- Downloaded 14 files (roughly 400 MB) with SFTP resume support.
- Verified local byte sizes, SHA-256 digests, Parquet row counts, and metadata
  against the server manifest: 14/14 passed.
- Completed `bridge-smoke-001` for dividend-v6 from 2024-01-01 through
  2024-03-31: 58 NAV points, 54 trade records, and 18 final holdings.
- Observed baseline metrics: total return -8.85%, benchmark +4.46%, maximum
  drawdown 22.80%, Sharpe -0.939.

## Findings requiring correctness review

- The legacy transaction payload contained BUY records only for this run.
- The CLI used a 20-trading-day rebalance interval, while the strategy module
  describes January/July rebalancing.
- Final holdings were heavily concentrated in STAR Market symbols. Confirm the
  dividend-yield unit and intended universe before treating performance as a
  validated strategy result.
- These findings are preserved as legacy behavior; the compatibility phase did
  not silently change them.

## Read-only Quant Desk milestone

- Added `/quant-desk/` as a zero-build AgentMatrix strategy dashboard.
- Added read-only `/api/strategy-dashboard/strategies` and strategy-detail
  endpoints backed only by persisted `BacktestResult` JSON files.
- The page displays real KPI, NAV/benchmark, drawdown, final positions, and
  trades. It contains no mock data, SQLite dependency, upload control, or
  browser-side fake job progression.
- The original desktop React prototype remains untouched as a visual/component
  reference; its API server and mock-backed home page are not production
  dependencies.

## Strategy library correction (2026-08-07)

- Reframed `/quant-desk/` as a strategy library rather than a single-result
  selector.
- Added ranked strategy cards and click-through detail navigation, while
  retaining NAV, drawdown, holdings, and trades inside each strategy detail.
- Added persisted run counts and deterministic ranking by Sharpe then
  annualized return.
- Kept the admission boundary strict: only completed canonical backtest
  artifacts appear. The library currently contains one strategy because only
  one qualifying strategy result has been generated; no mock cards were added.

## Production-loop implementation started (2026-08-07)

- Audited the target server without modifying services or datasets. It runs
  Ubuntu, Python 3.12, systemd, Nginx, and Docker, with roughly 127 GB free.
- Confirmed the existing weekday ETL at 18:30 and source files current through
  2026-08-06. Existing ports 80/443/8765 and services must be preserved.
- Added a versioned strategy registry with explicit owner, lifecycle status,
  engine parameters, and quality gates. Dividend-v6 remains `review`, not
  approved for automatic publication.
- Added a daily runner that derives the data version from the dataset manifest,
  runs only approved/published strategies, applies quality gates, writes batch
  status, and atomically replaces the published result only after success.
- Added initial gates for stale results, invalid NAV/metrics, exposure limits,
  one-sided trade histories, and suspicious zero turnover.
- Created an isolated server release and virtual environment without changing
  the existing Quant API, ETL, Nginx, or public ports.
- Started the minimal read-only API through Gunicorn on server loopback port
  8813. Seven isolated tests passed; health returned `strategies: 0` and the
  static dashboard returned HTTP 200.
- Confirmed the current raw/compatibility data gap: daily raw files reached
  2026-08-06, but the compatible engine manifest ends at 2026-04-30.
- Found that quarterly financial refresh currently logs an unsupported RQData
  call while the overall ETL still reports completion. Publication scheduling
  remains disabled until dataset-level readiness is implemented.

## Data readiness and operating status (2026-08-07)

- Added an atomic dataset-readiness manifest with schema, row-count, maximum
  date, freshness, and mandatory/optional checks. Synthetic readiness tests
  cover aligned, stale, and incomplete-schema cases.
- Ran the gate against `/home/data/RQdata_files`; its data version is
  2026-08-06. Daily K-line, ST, shares, daily factors, ex-factor, income, and
  balance inputs passed their configured checks.
- Confirmed the shared index file ends at 2026-07-14 and blocks publication.
- Built a strategy-owned CSI300 reference file without modifying the shared
  source. It now ends at 2026-08-06 and contains 9,503 total index rows, 1,598
  for CSI300.
- Added explicit mandatory gates for adjusted K-line/limit fields, suspension
  status, and dividend-yield data after confirming the legacy engine silently
  degrades or returns empty signals when they are absent.
- The current complete failure set is `index_kline`,
  `engine_adjusted_kline`, `engine_suspension_status`, and `dividend_yield`.
- Added `/api/strategy-dashboard/status` and a Quant Desk status banner. The
  server endpoint now reports the 2026-08-06 version and all blocking inputs.
- Fourteen local integration tests and two server API tests passed for the
  status release; the reference-data addition increased the focused local
  suite to fifteen tests.

## Immutable strategy dataset and full candidate run (2026-08-07)

- Probed RQData 3.5.2 with bounded samples and confirmed official support for
  raw/pre-adjusted prices, limit prices, suspension state, ST state, and
  `dividend_yield_ttm`.
- Confirmed the legacy compatibility prices use the same `pre` adjustment
  anchor as current RQData, allowing an incremental extension without a splice
  discontinuity.
- Built, hashed, and validated an immutable 2026-08-06 custom-engine dataset;
  then retained two superseded revisions while correcting dividend semantics.
- Found historic `dividend_yield` files use basis points, not percentage
  points. The production r3 build normalizes each legacy file by 10,000 and
  leaves current TTM decimal values unchanged. Its median yield is 0.85% and
  99th percentile is 7.67%.
- `datasets/current` now points to `2026-08-06-r3`. Structural, row-count,
  SHA-256, date, and dividend-freshness validation passed.
- Completed a full 2020-01-02 through 2026-08-06 dividend-v6 candidate run on
  the server using r3. It produced 1,598 NAV points, 100 exposed trade records
  (75 BUY / 25 SELL), and 20 final positions.
- Candidate metrics: total return 53.55%, annualized return 7.00%, benchmark
  12.02%, reported excess 41.53%, maximum drawdown 26.70%, Sharpe 0.44, and
  volatility 19.89%.
- The result remains quarantined and the published directory remains empty.
  Reported turnover is still zero despite trades, and the configured 20-day
  rebalance schedule conflicts with the strategy's January/July description.
- Strengthened publication gates to reject empty/flat strategies, missing
  holdings, missing two-sided trades, minimum-trade failures, and zero turnover
  with a non-empty trade history.
- Quant Desk now reports the r3 strategy dataset as ready through 2026-08-06,
  while the candidate strategy remains quarantined.

## Review-result dashboard mode (2026-08-07)

- Performance validation is intentionally deferred while the source dataset is
  being corrected. Dividend-v6 remains an engineering integration sample.
- Added an explicit result publication status to the dashboard contract. A
  deployment can now point at a quarantine directory without presenting those
  artifacts as approved or published.
- Strategy cards label quarantine results as `研究验证 · 未发布`; the detail
  profile also displays publication state and immutable data version.
- The default remains `published`, so production deployments cannot expose
  review artifacts unless `STRATEGY_RESULT_PUBLICATION_STATUS=review` is set
  deliberately.

## Compatibility release deployed (2026-08-07)

- Deployed AgentMatrix release `20260807_1530`; server-side focused tests passed
  10/10 and `current` now resolves to that release.
- Created `/home/data/agentmatrix-backtest-engine` and promoted the verified
  legacy baseline as `releases/20260807_legacy_v1`; its `current` symlink is the
  only engine path used by the daily runner.
- Switched the internal preview to the quarantine directory with explicit
  `review` status. Deployment verification reports one strategy and data
  version 2026-08-06.
- Re-ran dividend-v6 through the formal engine path. The 7m44s job produced a
  new atomic artifact and batch status; it remains quality-failed because trade
  history is non-empty while reported turnover is zero.
- Installed a `data`-account cron at 19:30 on weekdays with `flock` overlap
  prevention, following the existing 18:30 ETL. Added an `@reboot` public
  dashboard launcher as an interim supervisor.
- Existing Nginx already proxies all HTTP/HTTPS traffic to loopback port 3000,
  which was unused and returned 502. Bound the read-only dashboard there
  without modifying `/etc/nginx`; external HTTP and HTTPS `/quant-desk/` and
  strategy API checks returned 200.
- Administrator follow-up remains: replace the broad port-3000 proxy with the
  path-scoped Nginx locations and replace cron/daemon supervision with the
  reviewed systemd units.

## Product naming and dashboard visual refresh (2026-08-07)

- Standardized the product name `晨曦引擎` for the integrated desktop
  backtest engine. New canonical results use `chenxi_engine`; the frontend maps
  historic `custom_legacy_bridge` artifacts to the same display name.
- Refreshed Quant Desk using the established desktop prototype's visual
  language while retaining the zero-build, real-API-only production boundary.
- Factor Lab remains a separate internal-development application. Its Flask
  backend is not part of the deployed minimal dashboard service, and its
  frontend password is only a convenience gate rather than production
  authentication; it must not be described as production-released yet.

## Chenxi accounting and signal readiness (2026-08-11)

- Added a canonical compatibility-accounting summary based on the complete
  Chenxi transaction ledger and actual portfolio equity series. Turnover now
  follows the repository-wide two-sided convention: absolute traded notional
  divided by twice average equity.
- Kept display pagination separate from accounting: Quant Desk may expose only
  the latest trades, while turnover and transaction counts use every engine
  transaction returned by the run.
- Added deterministic tests for accounting math and contract mapping.
- Confirmed the zero-signal cause for the example momentum and reversal
  strategies: they require `ret_60d`, `volatility_20d`, and `ret_5d`, while the
  legacy engine only derives `ret_1d`.
- Extended the immutable Chenxi compatibility dataset builder to derive those
  three rolling features from adjusted close prices. Source datasets remain
  untouched; features appear only in the next versioned compatibility output.
- No strategy was rerun and no server dataset or active release was changed in
  this step.
- Remaining accounting risk: the legacy execution loop rebuilds target
  holdings and emits repeated BUY rows instead of recording only position
  deltas. The compatibility turnover is internally consistent with those rows,
  but execution realism still requires replacing that loop with the new
  cash/position/order ledger before results can be performance-certified.

## Quant Desk visual convergence (2026-08-12)

- Rebuilt the dashboard presentation around the teammate prototype's strongest
  product ideas while keeping the AgentMatrix API and result contract intact.
- Added a compact global strategy strip, search/publication filters, real NAV
  sparklines, multi-strategy portfolio view, and risk center.
- Portfolio NAV and inverse-volatility allocations are calculated in the
  browser from persisted strategy detail results over their common dates.
- Risk observations use real volatility, drawdown, final-position
  concentration, and quality status. Missing fields are not filled with demo
  values.
- Did not import the prototype's SQLite database, static JSON API, Windows
  paths, Qlib experiments, or local daily pipeline.
- Dashboard/API regressions pass. The active local service serves the new
  assets successfully; screenshot-level QA remains a manual follow-up because
  no graphical browser was available in this session.

## Controlled backtest job loop, phase 1 (2026-08-12)

- Added a persistent SQLite job queue with atomic single-worker claiming and
  explicit `queued`, `running`, `validating`, `completed`, and `failed` states.
- Added a standalone worker that reuses the existing Chenxi adapter, quality
  gates, immutable dataset manifest, and canonical `BacktestResult` JSON.
- Added capability, submission, job-list, and job-detail API endpoints.
- Interactive submission is disabled by default and requires both an explicit
  server enable flag and a matching request token. Requests can select only
  non-disabled registry strategies and bounded parameters; source code, module
  paths, engine paths, and data paths are never accepted from the browser.
- Added a Quant Desk backtest workbench with strategy/date/capital/fee inputs,
  queue progress, failure details, polling, and completed-result navigation.
- The access token stays in page memory and is neither persisted nor returned
  by the API. Public deployment must remain read-only until authentication and
  role controls are approved.

## Quant Desk functional expansion (2026-08-12)

- Added strategy comparison for two to five persisted results, including NAV
  overlays, KPI tables, and daily-return correlation matrices.
- Added a portfolio builder with equal-weight, inverse-volatility, and manual
  allocation modes. Portfolio drafts can be named and saved in browser-local
  storage for the current user.
- Kept synthetic NAV portfolios explicitly separate from executed portfolios.
  The builder does not claim shared-cash fills, holdings, fees, or turnover;
  those require the replacement Chenxi execution ledger.
- Existing strategy library, detail, positions, trades, risk, job workbench,
  data quality, and publication-state views remain connected to the canonical
  AgentMatrix API.
