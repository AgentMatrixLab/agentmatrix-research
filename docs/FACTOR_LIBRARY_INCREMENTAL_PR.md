# Factor Library Incremental PR Notes

This PR is an incremental follow-up to the closed factor reproduction PR.

## Scope

- Add `research_core/factor_library/` as an experimental, standalone factor reproduction module focused on reusable operators, factor computation, batch compute, and validation.
- Keep existing mainline modules untouched:
  - `research_core/factor_lab/`
  - `research_core/qlib_lab/`
  - `docs/QLIB_FACTOR_WORKFLOW.md`
  - `docs/ALPHA158_STARTER.md`
- Fix the validation return-column mismatch found during review.

## Review Feedback Addressed

The previous validation path had inconsistent return naming:

- `compute_forward_returns()` produced `forward_return`.
- `compute_monthly_ic()` read `return`.

This PR makes `compute_monthly_ic()` read `forward_return` by default and keeps legacy `return` support through an explicit `return_col="return"` argument.

The regression test is:

```bash
python -m unittest research_core.factor_library.test_validation
```

## Validation Boundary

The bundled `example_usage` is a smoke test for package importability, factor calculation, and batch compute. It uses mock data and must not be treated as proof that Alpha101 or Alpha191 have been fully reproduced on real market data.

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

Current boundary: SmartData full-market local reproduction evidence is available for the first 10 WQ101 and GTJA191 factors; external full-market JoinQuant IC remains a secondary follow-up because of platform resource limits. Therefore this PR should be reviewed as reusable factor-library scaffolding plus validation plumbing with attached local real-data evidence, not as a final claim that every external platform result is fully proven.
