# GM SDK — JQ Field Mapping Reference

> 21 field-name corrections discovered across 58 versions (v20→v78) of the
> CrossvalidationTYD GM-vs-JQ factor validation project.  Use this as a
> reference when writing new factor Specs or debugging `_pt` API failures.

## Why This Matters

GM SDK uses non-standard field names in its financial data APIs.  The most
dangerous failure mode is **cascading API failure**: one invalid field name in
a `_pt` API call causes the entire call to fail silently, zeroing out ALL
factors that depend on that API call.  No error, no warning — just NaN.

The 21 corrections below are split into two categories:

- **A.1 (9 errors)**: Wrong field name used — API accepted it but returned
  semantically wrong data or a different field.
- **A.2 (12 errors)**: Invalid field name — field doesn't exist, causing
  the entire API call to fail.

---

## A.1 Field-Name Mapping Errors (9)

These fields exist in the GM API under different names.  Using the wrong name
returns incorrect data or a different field entirely.

| Wrong Field | Correct GM Field | API | Semantic | Found |
|-------------|-----------------|-----|----------|-------|
| `gp_mg` | `sale_gpm` | `deriv_pt` | Gross profit margin | v52 |
| `np_mg` | `sale_npm` | `deriv_pt` | Net profit margin | v52 |
| `tot_ast_turn` | `ttl_ast_turnover_rate` | `deriv_pt` | Total asset turnover | v52 |
| `debt_ast_rat` | `ast_liab_rate` | `deriv_pt` | Debt-to-assets ratio | v52 |
| `cur_rat` | `curr_rate` | `deriv_pt` | Current ratio | v52 |
| `qd_rat` | `quick_rate` | `deriv_pt` | Quick ratio | v52 |
| `net_cf_fnc` | `net_cf_fin` | `cashflow_pt` | Net financing cash flow | v52 |
| `ttl_sh_eqy` | `ttl_eqy` | `balance_pt` | Total shareholders' equity | v48 |
| `roa` | `jroa` | `deriv_pt` | Return on assets | v57 |

**How to avoid**: Always verify a field against the GM Data Dictionary before
using it.  Run a single-symbol API call to confirm the field returns expected
values before integrating it into the factor engine.

---

## A.2 Invalid Fields (12)

These fields do NOT exist in the specified GM API.  Including any of them in
a bulk `_pt` call causes the entire call to fail.

| Invalid Field | API Attempted | Workaround | Found |
|---------------|--------------|------------|-------|
| `flow_mv` | `mktvalue_pt` | Use `tot_mv` instead | v58 |
| `ttl_shr` | `basic_pt`, `mktvalue_pt` | Compute from `tot_mv / close` | v48 |
| `float_shr` | `basic_pt`, `mktvalue_pt` | Compute from `tot_mv / close` | v48 |
| `cur_liab` | `balance_pt` | Use `ttl_cur_liab` | v52 |
| `tax_surch` | `income_pt` | Does not exist | v52 |
| `biz_tax_surch` | `income_pt` | Does not exist | v52 |
| `ttl_inc_oper` | `income_pt` | Use `inc_oper` | v52 |
| `inv_turn_ratio` | `deriv_pt` | Custom computation | v52 |
| `ar_turn_ratio` | `deriv_pt` | Custom computation | v52 |
| `np_parent_company_owners_yoy` | `deriv_pt` | Custom computation | v52 |
| `ev_ebitda` | `valuation_pt` | Custom computation | v46 |
| `depr`/`amort` | `deriv_pt` | Use `cur_depr_amort` | v52 |

**The cascading failure pattern** (v58 case study):
1. `flow_mv` is passed to `stk_get_daily_mktvalue_pt()`
2. GM API rejects the entire request because `flow_mv` is an invalid field
3. ALL fields requested in that call (`tot_mv`, `pe_ttm`, `pb_mrq`, `ps_ttm`)
   return NaN
4. Multiple factor categories (market cap, valuation) fail simultaneously

**Mitigation**: Test every new field on a single symbol before adding it to
production-factor computation.  If an entire factor category suddenly goes NaN,
check for invalid fields in the corresponding `_pt` API call first.

---

## API Field Limits

| API | Max Fields | Silent Failure |
|-----|-----------|----------------|
| `balance_pt` | 20 | Yes — exceeds limit → entire call fails silently |
| `income_pt` | No known limit | — |
| `cashflow_pt` | No known limit | — |
| `deriv_pt` | No known limit | — |
| `mktvalue_pt` | No known limit | But `flow_mv` is invalid (see above) |
| `valuation_pt` | No known limit | — |

---

## Testing New Fields

```python
# 1. Test on a single stock first
from gm.api import stk_get_fundamentals_balance_pt
result = stk_get_fundamentals_balance_pt(
    symbols="SHSE.600519",
    fields="ttl_cur_liab,ttl_eqy",
    date="2026-03-17"
)
# 2. Verify the result is non-NaN with expected magnitude
assert result is not None
assert not result.empty
```
