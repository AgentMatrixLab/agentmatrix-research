# Strategy dashboard deployment

The dashboard API and the daily calculation job are separate processes. The
API reads only atomically published JSON artifacts and binds to loopback port
8813. Nginx should proxy the approved public path to that port.

Server layout:

```text
${STRATEGY_ROOT}/
  current -> releases/<release-id>
  releases/<release-id>/
  shared/
    dashboard.env
    published/
    operations/
    datasets/current -> versions/<data-version>
    venv/
```

Do not point `current` at a new release until its unit tests, `/healthz`, and
strategy-list endpoint pass. Do not expose the Flask development server.

The systemd unit requires an administrator to install it. Until that approval
is available, run the same Gunicorn command under a user-level systemd unit or
a supervised isolated smoke process.

`strategy-daily.timer` is scheduled for 19:30 China time on weekdays, after
the existing 18:30 data refresh. Its oneshot service runs approved strategies
and review strategies. Review and quality-failed artifacts stay in
`shared/quarantine`; only gate-passing approved strategies can replace files in
`shared/published`. The team must confirm the server's backtest-engine path and
the upstream ETL completion time before an administrator enables the timer.

For an internal engineering demonstration, the API may read the quarantine
directory only when both variables are set together:

```text
STRATEGY_BACKTEST_RESULT_DIR=${STRATEGY_ROOT}/shared/quarantine
STRATEGY_RESULT_PUBLICATION_STATUS=review
```

The UI then labels every result as research validation and unpublished. Switch
both values back to the published directory/status for a release-facing
deployment.

The interactive worker must use the same lock as the daily batch:

```text
--lock-file ${STRATEGY_ROOT}/shared/operations/daily.lock
```

It releases the lock between queue polls, so the weekday batch can take
priority when idle and interactive jobs cannot overlap a daily calculation.
