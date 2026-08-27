# Alpha158 Artifact Map

Root: `runtime/alpha158_lab/` (from repo root `agentmatrix-research/`)

## Core Data

| File | Description |
|------|-------------|
| `market_panel.parquet` | SmartData OHLCV panel (date, code, flags). ~8M rows, ~6761 codes |
| `alpha158_factors_smartdata.parquet` | Merged 158 factor columns (PyArrow outer join on date+code) |
| `factors/batch_XX.parquet` | Per-batch factor slice (debug / partial rerun) |

## Per-Batch (`XX` = 01 … 16)

| Path | Description |
|------|-------------|
| `truth/batch_XX/qlib_truth_{start}_{end}.parquet` | qlib Alpha158 exported truth |
| `validation/batch_XX/accuracy_report.json` | Machine-readable Spearman results |
| `validation/batch_XX/accuracy_report.md` | Human-readable accuracy summary |
| `effectiveness/batch_XX/` | Long-short spread, quantile returns CSVs |
| `reports/batch_XX/REPORT.md` | Batch narrative report with headline status |
| `reports/batch_XX/mosaics/` | Factor mosaic PNG grids |
| `pipeline_manifest_batch_XX.json` | Full run config + artifact paths + `accuracy_status` |

## Aggregated IC

| File | Description |
|------|-------------|
| `effectiveness/ic_series.csv` | Long-format daily IC per factor (merged across batches) |

## Charts

`charts/{FACTOR}_ic.png`, `{FACTOR}_long_short_nav.png`, `{FACTOR}_quantile_layers.png`

## Master Reports (presentation)

| File | Use |
|------|-----|
| `reports/master/MASTER_DASHBOARD.html` | **Primary** — scope diagram, batch table, fail list, talking points |
| `reports/master/MASTER_SUMMARY.md` | Printable one-pager |
| `reports/master/accuracy_all.csv` | All factors Spearman + status |
| `reports/master/ic_summary_all.csv` | IC mean/std/IR per factor |

## Regenerate Commands

```powershell
python scripts/generate_alpha158_all_reports.py
```

Individual generators:
- `scripts/generate_alpha158_dashboard.py` → MASTER_DASHBOARD.html
- `scripts/generate_alpha158_master_summary.py` → MASTER_SUMMARY.md + CSVs

## Manifest Fields (quick inspect)

```powershell
Get-Content runtime/alpha158_lab/pipeline_manifest_batch_01.json | ConvertFrom-Json | Select config, accuracy_status
```

Key `config` fields: `compute_range`, `validation_range`, `compute_codes`, `post_validation_note`.