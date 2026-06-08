# Factor Library Real-Data Evidence Digest

This document addresses the review concern that `example_usage` is based on mock data. The mock example remains a smoke test only. The real-data evidence for the 10-factor reproduction comes from private SmartData full-market factor reproduction reports retained outside this repository:

```text
WQ101_前10因子复现与有效性检验报告.docx
GTJA191_前10因子复现与有效性检验报告.docx
```

Large raw parquet files, SmartData credentials, and local database access details are not committed to this PR. This file records the evidence boundary and the concrete report artifacts used for validation.

## Acceptance Scope

| Item | Value |
|---|---|
| Data source | SmartData ClickHouse daily A-share OHLCV |
| Database note | GTJA191 report: `SmartData (ClickHouse amazingdata)`; WQ101 report: `SmartData（ClickHouse 数据库，通过 SSH Tunnel 访问）` |
| Date range | 2020-01-01 to 2025-12-31 |
| Universe | Full A-share universe after filtering ST, delisted names, and stocks listed for fewer than 120 trading days |
| Stock count | Approximately 4,993 stocks |
| Raw rows | WQ101 report: 6,416,449 rows; GTJA191 report: about 6.4M+ rows |
| Validation method | Monthly Spearman rank IC, 10-quantile long-short grouping, long-short NAV, visual report |
| Secondary validation | JoinQuant full-market IC not included; still pending because of platform resource limits |

## Source Artifacts

```text
WQ101_前10因子复现与有效性检验报告.docx
GTJA191_前10因子复现与有效性检验报告.docx
```

## Report Evidence Summary

WQ101 report:

- Uses SmartData A-share full-market daily data as the source.
- Covers 2020-01-01 to 2025-12-31, about 1,285 trading days.
- Uses about 4,993 filtered A-share stocks and 6,416,449 rows.
- Computes Alpha#1 to Alpha#10.
- Evaluates monthly Spearman rank IC, 10-quantile long-short returns, long-short NAV, and charts.
- Explicitly aligns month-end factor values with next-month returns to avoid lookahead bias.

GTJA191 report:

- Uses SmartData `(ClickHouse amazingdata)` as the source.
- Covers 2020-01-01 to 2025-12-31.
- Uses about 4,993 A-share stocks and about 6.4M+ daily records.
- Computes GJ#1 to GJ#10 from GTJA191 Table 6.
- Is marked as version `v2.0 (修复前视偏差后)`.
- Explicitly states that older abnormal GJ#3/GJ#9 high-IC conclusions were caused by lookahead bias and should be discarded.

## Output Schema / Artifact Checks

The reports reference the generated local artifacts without committing the large files to this PR.

| Dataset | Referenced factor output | Report coverage |
|---|---|---|
| WQ101 | `results/wq101/factor_values/wq_alpha_1_10_2020-01-01_2025-12-31.parquet` | Alpha#1-Alpha#10 |
| GTJA191 | `results/gtja191/factor_values/gtja_alpha_1_10_2020-01-01_2025-12-31.parquet` | GJ#1-GJ#10 |

Both runs produced:

- `factor_test_summary.csv`
- `ic_series.csv`
- `long_short_nav.csv`

## Current Result Summary

WQ101:

- Strongest factors are Alpha#3 and Alpha#6.
- Alpha#4 and Alpha#2 are medium-strength candidates.
- Alpha#8 has weaker IC but a comparatively attractive return/drawdown profile.
- Alpha#1 and Alpha#7 should not be used directly.

GTJA191:

- GJ#5 is the strongest factor in the SmartData report.
- GJ#7 and GJ#8 are also reported as effective in this SmartData report.
- GJ#3 and GJ#9 old high-IC results were explicitly identified as lookahead-biased and discarded after the v2.0 correction.

## No-Lookahead Boundary

The SmartData reports use month-end factor values to predict next-month returns. The GTJA191 report explicitly documents the earlier lookahead-risk audit and the corrected factor-to-return alignment. Smoke tests must not be used as evidence for final IC or return conclusions.

## Review Boundary

This PR now contains five separate validation layers:

1. `python -m research_core.factor_lab.cli run-factor-set-demo --factor-set wq101`: factor_lab mainline smoke path for WQ101 Alpha#1-#10.
2. `python -m research_core.factor_lab.cli run-factor-set-demo --factor-set gtja191`: factor_lab mainline smoke path for GTJA191 Alpha#1-#10.
3. `research_core.factor_lab.libraries.test_factor_sets`: regression tests for WQ101, GTJA191, dynamic column sets, non-empty coverage, fixed anchors, and WQ101-vs-Alpha101 mainline equality.
4. `research_core.factor_library.test_validation`: compatibility regression tests for the `forward_return` / `return` validation-column mismatch and dynamic batch column prefixes.
5. This evidence digest: real SmartData full-market reproduction summary from the user's WQ101 and GTJA191 Word reports.

The PR should not claim that external full-market JoinQuant IC is complete. That remains a secondary validation item.
