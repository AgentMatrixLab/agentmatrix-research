# Strategy dashboard production rollout

## Target daily flow

```text
RQData ETL -> dataset-level readiness manifest -> compatible dataset version
-> approved strategy batch -> quality gates -> atomic publish
-> loopback dashboard API -> Nginx/TLS -> Quant Desk
```

## Server baseline (2026-08-07)

- Host: Ubuntu Linux, Python 3.12, systemd, Nginx, and Docker.
- Capacity: about 127 GB free at audit time.
- Existing services: Nginx on 80/443 and Quant API on 8765. These were not
  changed.
- Existing schedule: weekday ETL at 18:30 under the `data` account.
- Source daily market files were current through 2026-08-06 at audit time.
- Isolated release: `${STRATEGY_ROOT}/releases/20260807_1100`.
- Shared state: `${STRATEGY_ROOT}/shared`.
- Smoke API: Gunicorn on server loopback `127.0.0.1:8813`; seven isolated
  tests passed, `/healthz` returned healthy, and `/quant-desk/` returned 200.
- Public proxy and system service installation have not been performed.

## Data blockers discovered

The existing ETL is not yet a sufficient production-ready signal for the
legacy engine:

- The daily K-line output is unadjusted and does not contain every field
  required by the legacy engine's combined K-line artifact.
- ST is updated, but suspension state is not present in the daily status file.
- Ex-factor events do not by themselves satisfy dividend-v6's required daily
  dividend-yield input.
- Financial quarterly refresh logs an unsupported RQData API call and still
  allows the overall job to log completion.
- The compatibility dataset manifest ends at 2026-04-30, while raw daily ETL
  files were current through 2026-08-06.
- Therefore neither the ETL completion log nor file modification time alone is
  an acceptable data-ready trigger.

Required resolution: produce a dataset-level manifest that records status,
row count, maximum trade date, schema, and validation outcome for every
required input. The strategy batch may start only when all mandatory datasets
pass for one immutable data version.

## Release boundary

Dividend-v6 remains in `review`. Its one-sided trade records and zero turnover
warning prevent automatic publication. The empty production library is
intentional until a strategy passes both correctness review and automated
quality gates.

## Team approvals needed

1. Data owner: repair the quarterly financial pull and define the source for
   suspension status, limit prices, adjusted prices, and dividend data.
2. Strategy owner: resolve dividend-v6 trade direction, turnover, rebalance
   schedule, and intended stock universe.
3. Infrastructure owner: install/enable the systemd unit and add an Nginx
   location plus TLS/public access policy after smoke acceptance.
4. Product owner: approve the first strategy set and publication/ranking rules.
5. Security owner: move credentials out of source files and rotate credentials
   that have been shared or embedded in scripts.

## Next implementation steps

1. Add the dataset readiness manifest generator and validation contract.
2. Build an incremental compatibility dataset from the approved daily sources.
3. Run dividend-v6 on the server but keep it quarantined if quality gates fail.
4. Add a user-level supervised batch schedule after ETL readiness, then request
   administrator installation for systemd/Nginx.
5. Expose update status and data-as-of metadata in Quant Desk.

## Expedited compatibility release scope (2026-08-07)

The first release intentionally keeps the legacy engine behind the canonical
AgentMatrix adapter. It includes the strategy library, detail views, explicit
review/published state, immutable data version, weekday calculation template,
atomic result files, batch status, and deployment verification. Strategy
performance validation and the new accounting core are post-launch work.

### Installation order

1. Create `${BACKTEST_ENGINE_ROOT}` with versioned `releases`,
   `current`, and writable `shared` directories owned by `data:datateam`.
2. Package the approved desktop-engine baseline without datasets, credentials,
   caches, or prior results; install its pinned environment and switch the
   `current` symlink only after a server-side smoke run.
3. Deploy the AgentMatrix release and set the internal preview environment to
   the quarantine directory with publication status `review`.
4. Install `strategy-dashboard.service`, verify loopback port 8813, and run
   `scripts/verify_strategy_dashboard_deployment.py --require-strategy
   --expected-publication-status review`.
5. Add `deploy/strategy-dashboard/nginx-location.conf` to the existing TLS
   virtual host, run `nginx -t`, reload Nginx, and repeat verification through
   the approved public URL.
6. Confirm ETL completion time and engine path, then install and enable
   `strategy-daily.timer`. Trigger the oneshot once manually before relying on
   the calendar schedule.

### Rollback

- Disable the timer first; it is not required for serving the previous result.
- Point the AgentMatrix `current` symlink back to the preceding tested release
  and restart only `strategy-dashboard.service`.
- If public routing fails, remove the two added Nginx locations and reload;
  existing Quant API routes and datasets are not modified by this deployment.
- Never delete the previous published JSON or immutable dataset revision during
  a release or rollback.
