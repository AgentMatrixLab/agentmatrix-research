# Unit Scale Rules: GM vs JQ

> 11 unit-scaling categories discovered through 58 versions of cross-engine
> validation.  Misapplied scaling is the most common source of false
> MISMATCHES — GM and JQ return values in different units for the same factor.

## Rule Table

| Category | Example Factors | GM Unit | JQ Unit | Transform |
|----------|----------------|---------|---------|------------|
| Enterprise value | `ev` | 元 (CNY) | 亿元 (100M CNY) | GM `/1e8` |
| Margin ratios | `gross_profit_margin`, `net_profit_margin` | decimal (0–1) | percentage (0–100) | GM `×100` |
| Operating margin | `operating_profit_margin` | decimal (0–1) | percentage (0–100) | GM `×100` |
| Growth rates (TTM) | `*_growth_ttm` | decimal (0–1) | percentage (0–100) | GM `×100` |
| Growth rates (YoY) | `*_yoy` | decimal (0–1) | percentage (0–100) | GM `×100` |
| `total_assets_growth_rate` | — | percentage (*already*) | percentage | **Do NOT scale** |
| Book value per share | `bps` | 元 (CNY) | 元 (CNY) | No scaling |
| ROA / ROE | `roa`, `roe`, `roe_ttm` | decimal | decimal | **Do NOT scale** |
| PE / PB / PS / PCF | `pe_ttm`, `pb_mrq`, `ps_ttm` | multiple | multiple | No scaling |
| Current / Quick ratio | `current_ratio`, `quick_ratio` | multiple | multiple | No scaling |
| Self-computed TTM results | — | decimal | decimal | No scaling |
| Alpha VOLUME | `alpha191_*` volume-based | shares (股) | two units (mix) | **NC** |

---

## Scenarios That Catch You

### 1. Double-Scaling (`total_assets_growth_rate`)

The GM `deriv_pt` API already returns this as a percentage value.  Applying
another `×100` converts 65% → 6500%, causing 299 MISMATCHES (v75).

**Rule**: Always check whether GM returns the value already scaled before
applying unit transforms.

### 2. Wrong-Shift (`roe_ttm`)

GM returns `jroa` (net income / total assets) as a decimal (e.g. 0.12).  JQ
returns the same unit.  Adding `×0.01` (thinking JQ uses percentage) converts
12% → 0.12%, causing all values to miscompare (v61).

**Rule**: ROA and ROE are always decimal in both engines.  Never scale them.

### 3. Dead Code (`unit_scale` in registry, never applied)

The FACTOR_REGISTRY had a `unit_scale` field defined for growth-rate factors
but the compute function never actually read and applied it (v60).  Took 18
versions to discover.

**Rule**: If you define a scaling constant, verify it's actually applied in
the code path before declaring verification complete.

### 4. Volume Factor Ambiguity

JQ's alpha191 volume-based factors use mixed units (some in shares, some in
lots of 100 shares).  GM only provides raw share counts.  No single scaling
rule works for all factors — mark these as NC.

---

## How the Diagnostic Engine Detects Scaling Issues

The `unit_scale` detector in `diagnostics.py` checks for **stable ratio**
between GM and JQ values:

```
avg_ratio = mean(GM_value / JQ_value)
if avg_ratio > 50:   →  unit_scale missing (need /avg_ratio)
if avg_ratio < 0.02: →  unit_scale missing (need ×1/avg_ratio)
```

A stable ratio (low coefficient of variation) means ALL stocks exhibit the same
scaling error, which is the fingerprint of a unit-scale bug.  The detector
suggests the exact multiplier to fix it.

### Example Output

```
MLEV: GM/JQ = 6897x (cv = 0.001)
  → unit_scale issue: need GM / 6897
  → confidence: 90%
  → action: modify_code
```
