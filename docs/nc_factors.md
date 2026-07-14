# NC Factors and Lessons Learned

> Why some factors can never cross-validate between GM and JQ engines, and the
> 16 engineering lessons extracted from 58 version iterations.

## What "NC" Means

**NC (Not Comparable)** factors are known structural differences between GM
and JQ engines that make direct value comparison impossible or meaningless.
They are NOT bugs — they are different implementations of the same concept.

The NC classifier (`nc_classifier.py`) uses a 3-layer architecture:

```
Layer 1 — Factor-level NC: known definition/provenance differences
Layer 2 — Extra NC:       additional per-factor reasons
Layer 3 — Stock-level NC:  per-stock data-source / calendar issues
```

Classification priority (v78):

```
BOTH_NA → MATCH → factor-NC → NC → stock-NC → NC
→ GM_NA → JQ_NA → diff<5% → MATCH → diff≥5% → MISMATCH
```

---

## NC Categories

### Path Dependency

Factors whose values depend on a historical starting point or initialization
method.  GM and JQ use different starting points, so values diverge permanently.

| Factor | Issue |
|--------|-------|
| `RSI`, `rsi_14`, `rsi_6` | EWM initialization: recursive (JQ) vs SMA-first-window (GM) |
| `OBV`, `PVT` | Cumulative start point different |
| `MACD`, `macd_hist`, `macd_signal` | EWM initialization bias (5-10% offset) |
| `KDJ_D`, `KDJ_K` | Starting K/D values: JQ 50 vs GM 0 |

### Barra Neutralized

JQ's Barra factors are cross-sectionally neutralized.  GM provides raw values.
Replicating the neutralization requires a cross-sectional regression engine
that GM does not provide.

| Factor | Issue |
|--------|-------|
| `momentum_20d`, `momentum_60d` | Cross-sectional neutralization |
| `volatility_20d`, `volatility_60d` | Cross-sectional neutralization |
| `roe` | Leverage neutralization |
| `growth_style`, `size`, `beta`, `liquidity`, etc. | Barra composite factors |

### Cumulative vs TTM

GM `income_pt` returns cumulative quarterly values.  JQ returns trailing
twelve months (TTM).  The TTM conversion formula (`TTM = Q + FY - Q_prev`) has
residual differences from JQ's internal TTM.

| Factor | Issue |
|--------|-------|
| `total_asset_turnover` | Revenue numerator: cumulative vs TTM (~4.5x difference) |
| `ar_turn_ratio`, `inventory_turnover` | Same cumulative-vs-TTM issue |
| `operating_revenue`, `total_operating_revenue` | Cumulative vs direct TTM |

### Definition / Scale Fundamentally Different

GM and JQ define these factors using different formulas or data sources.

| Factor | Issue |
|--------|-------|
| `gross_profit_margin` | JQ may include tax surcharges; GM 91% vs JQ 67% for 茅台 |
| `net_debt` | JQ uses interest-bearing debt - cash; GM uses `deriv_pt` raw field |
| `bps` | JQ weighted average shares vs GM total shares |
| `financial_assets` | Account scope differs between data providers |
| `ev` | JQ includes minority interest / preferred shares; 43-75% difference for financials |

### Cash Flow Data Source

Cash flow data differs between GM and JQ providers, and sign conventions may
invert for specific accounts.

| Factor | Issue |
|--------|-------|
| `net_operate_cash_flow_ttm` | Sign differences, data source variance |
| `net_invest_cash_flow_ttm` | Same |
| `net_finance_cash_flow_ttm` | Same |

### v61 Formula / Sign Differences

Specific factors reverted to NC in v61 after formula corrections revealed
fundamental definition gaps.

| Factor | Issue |
|--------|-------|
| `momentum_5d` through `momentum_252d` (6 factors) | Formula/sign convention differs |
| `reversal_5d`, `reversal_20d`, `reversal_60d` | Same |

---

## Stock-Level NC

Some factors have 90%+ matching stocks but a small minority of mismatches.
These are individual data-source or calendar-alignment issues:

| Factor | Stocks | Root Cause |
|--------|--------|------------|
| `net_working_capital` | ~17 / 248 | Individual stock balance-sheet source difference |
| `current_ratio` | ~16 / 248 | Same |
| `quick_ratio` | ~15 / 248 | Same |
| `beta_252d` | ~16 FSX | GM price data quality |
| `momentum_252d` | ~11 | 250 vs 252 trading days |

---

## 16 Key Lessons

1. **Cascading API Failure** — One invalid field name silently kills the
   entire `_pt` call, zeroing all dependent factors.  Test every new field on
   a single stock first.

2. **Look-Ahead Bias** — `_pt` date means "announcement date" (companies use
   latest disclosed financials).  `non-_pt` date means "report period".
   Passing a report-period date to a `_pt` API silently returns wrong data.

3. **balance_pt 20-Field Limit** — Exceeding 20 fields in a single
   `balance_pt` call fails silently.  Split across multiple calls if needed.

4. **Dead Code in Unit Scale** — `FACTOR_REGISTRY` had `unit_scale` defined
   but the compute function never applied it.  Verify data flow end-to-end.

5. **Typo-Silent Import Failure** — `FACTORY_REGISTRY` (extra Y) caused
   `ImportError` to be swallowed, forcing manual computation path and
   destroying accuracy.

6. **Cache Poisoning** — After fixing a formula, always clear `api_cache_*.pkl`
   or the old code's output persists.

7. **Double-Scaling (v75)** — `total_assets_growth_rate` was already a
   percentage; adding `×100` created 299 false MISMATCHES.

8. **Reverse-Scaling (v61)** — `roe_ttm` and `roa` are decimals in both
   engines; adding `×0.01` broke everything.

9. **Auto-NC False Positive** — `ts_rank` contains substring `rank` →
   4 pure time-series factors misclassified as cross-sectional.  Remove
   `ts_rank` before matching.

10. **`int('5d')` Crash** — `factor_key.split('_')[1]` returned `'5d'` →
    `ValueError`.  Use `.rstrip('d')` to extract numeric windows.

11. **`_pt` API Parameter Name Inconsistency** — Market APIs use `trade_date`,
    not `date`.  `symbols` has no default value.

12. **Hardcoded CSV Column Names** — Writing `'value'` when the actual column
    is `'jq_value'` → `KeyError`.  Always verify column names from the source.

13. **Forward-Looking Data (v44)** — Using `non-_pt` balance API for unannounced
    Q3 data introduced look-ahead bias.  Stock-level NC first detected here.

14. **Wrong Account Field** — `acct_pay` (accounts payable) substituted for
    `acct_rcv` (accounts receivable) → opposite semantic.  Double-check field
    meanings, not just names.

15. **JQ statDate Mutual Exclusion** — Cannot pass both `date` and `statDate`
    simultaneously.  `statDate='2024q3'` may return 0 rows (stale data).

16. **BOTH_NA Priority Over NC** — Financial stocks with both engines returning
    NaN → classify as BOTH_NA (counted as MATCH), NOT as NC.  Misclassified
    5 rows in v66.

---

## Adding New NC Patterns

When you discover a new NC pattern during validation, add it to
`nc_classifier.py` in one of three places:

1. **Exact factor match**: Add to `V67_NC_MAP`
2. **Pattern category**: Add to `_PATTERN_NC` if it affects a group of factors
3. **Definition difference**: Add to `_EXTRA_DEFINITION_NC` for single-factor
   naming variants

Always include: factor name, root cause, impact magnitude (if known).
