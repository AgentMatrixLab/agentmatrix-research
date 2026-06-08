# Factor Library Incremental PR Notes

This PR is an incremental follow-up to the closed factor reproduction PR.

## Scope

- Move the new WQ101 Alpha#1-#10 and GTJA191 Alpha#1-#10 capability into the unified `research_core/factor_lab/` mainline.
- Add `research_core/factor_lab/libraries/factor_sets.py` as the official compute entry for `wq101` and `gtja191`.
- Add `research_core/factor_lab/libraries/gtja191/` specs and implementation so GTJA191 can use the same specs, registry, service, truth, proof, report, and CLI chain as Alpha101.
- Keep `research_core/factor_library/` only as a compatibility layer for existing callers.
- Fix the validation return-column mismatch found during review.
- Fix `batch_compute_factors()` to rename the actual returned factor columns dynamically instead of hard-coding Alpha1-Alpha10.

## Review Feedback Addressed

The previous validation path had inconsistent return naming:

- `compute_forward_returns()` produced `forward_return`.
- `compute_monthly_ic()` read `return`.

This PR makes `compute_monthly_ic()` read `forward_return` by default and keeps legacy `return` support through an explicit `return_col="return"` argument.

The regression test is:

```bash
python -m unittest \
  research_core.factor_lab.libraries.test_factor_sets \
  research_core.factor_lab.test_service \
  research_core.factor_library.test_validation
```

The factor-set regression coverage now includes:

- `compute_wq101_alphas()`
- `compute_gtja191_alphas()`
- `compute_factor_set()`
- column-set validation
- non-empty coverage validation
- fixed deterministic anchor values
- WQ101 Alpha#1-#10 equality against the current `factor_lab` Alpha101 mainline implementation
- GTJA191 service artifact export through specs, registry, proof, report, and CLI-compatible service paths

## Validation Boundary

The bundled `example_usage` is a compatibility smoke test for package importability, factor calculation, and batch compute. It uses mock data and must not be treated as proof that Alpha101 or Alpha191 have been fully reproduced on real market data.

Real-data evidence is summarized in:

```text
docs/FACTOR_LIBRARY_REAL_DATA_EVIDENCE.md
```

That evidence package is based on the user's SmartData full-market factor reproduction reports. It is intentionally included as a compact evidence digest, not as raw data, credentials, or large parquet outputs.

Real-data proof should include:

- data source and adjustment mode,
- date range and universe,
- factor output schema,
- IC / rank IC computation,
- point-in-time or no-lookahead checks,
- comparison against an external reference or accepted golden output,
- explicit boundary notes for any secondary validation that remains incomplete.

Current boundary: local full-market reproduction evidence is available for the first 10 WQ101 and GTJA191 factors; external full-market JoinQuant IC remains a secondary follow-up because of platform resource limits. Therefore this PR should be reviewed as factor_lab mainline integration plus validation plumbing with attached local real-data evidence, not as a final claim that every external platform result is fully proven.
