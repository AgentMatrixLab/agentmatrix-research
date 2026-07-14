# Mining Bridge Design

> Bridge between AI-generated Qlib expressions and the jq_gm factor
> validation pipeline.  W8 deliverable — design document, module, and
> 3 manual case studies.

## Problem

`auto-mine` generates candidate factor expressions in Qlib syntax:

```
Ref($close, 20) / $close - 1        # 20-day momentum
$volume / Mean($volume, 10)          # 10-day volume ratio
Rank(Ref($close, 20) / $close - 1)  # cross-sectional momentum (unmappable)
```

These expressions must be:
1. **Parsed** — identify semantic type (momentum, volatility, etc.)
2. **Mapped** — find corresponding GM implementation route
3. **Verified** — compute and validate without external truth data
4. **Fed back** — structured rejection reasons returned to the AI miner

## Architecture

```
auto-mine (AI generates expressions)
        │
        ▼
┌─── mining_bridge.py ───────────────────────────┐
│                                                │
│  parse_expression(expr) → ParsedExpression     │
│         │                                      │
│         ▼                                      │
│  is_mappable(expr) → (bool, reason?)           │
│         │                                      │
│    ┌────┴────┐                                 │
│    ▼         ▼                                 │
│  mappable  unmappable → NC (with reason)       │
│    │                                            │
│    ▼                                            │
│  expression_to_spec() → FactorResearchSpec     │
│         │                                      │
│         ▼                                      │
│  batch_verify(specs) → VerificationResult[]    │
│         │                                      │
│    ┌────┼────┐                                 │
│    ▼    ▼    ▼                                 │
│  PASS  FAIL  NC  ← auto-classified             │
│    │                                            │
│    ▼                                            │
│  feedback_to_miner() → structured feedback     │
│                                                │
└────────────────────────────────────────────────┘
        │
        ▼
auto-mine (receives feedback, avoids known traps)
```

## Expression Types and Mapping

| Expression Type | Example | GM Route | Base Factor | Mappable? |
|----------------|---------|----------|-------------|-----------|
| Momentum | `Ref($close, 20) / $close - 1` | custom_price | REVS20 | ✅ |
| Volume Ratio | `$volume / Mean($volume, 10)` | custom_price | VOL10 | ✅ |
| Volatility | `Std($close, 20)` | custom_price | Std20 | ⚠️ (年化需验证) |
| Moving Average | `Mean($close, 5)` | custom_price | MA5 | ✅ |
| Price Ratio | `$high / $low` | custom_price | VWAP | ✅ |
| Correlation | `Corr($close, $volume, 20)` | custom | beta_252d | ⚠️ (需窗口对齐) |
| Delta | `$close - Ref($close, 20)` | custom_price | REVS20 | ✅ |
| **Rank** | `Rank(Ref($close, 20) / $close - 1)` | — | — | ❌ |
| **IndNeutralize** | `IndNeutralize(momentum, SW1)` | — | — | ❌ |
| **Group** | `Group(momentum, 'industry')` | — | — | ❌ |
| **Cut** | `Cut(momentum, 0.33)` | — | — | ❌ |

## Unmappable Patterns

These patterns appear in ~83% of Alpha factors (159/191 for Alpha191):

| Pattern | Why Unmappable |
|---------|---------------|
| `Rank(...)` | Cross-sectional rank — requires full-market cross-section, GM per-stock computation cannot replicate |
| `IndNeutralize(...)` | Industry neutralization — needs sector data + cross-sectional regression |
| `Group(...)` | Group aggregation — needs membership + cross-sectional aggregation |
| `Cut(...)` | Universe cutting — multi-stock comparison, single-stock mode can't do |
| `$vwap /` | VWAP ratios — GM custom_price mode uses close-only, no trade-level data |

## Self-Verification (No External Truth)

When no JQ or external truth data exists, verification checks:

1. **Coverage**: ≥80% of stocks have non-NaN computed values
2. **Finite Ratio**: ≥95% of values are finite (no ±∞)
3. **Benchmark Correlation**: If claimed type is "momentum", correlation with
   REVS250 should be in [0.6, 0.9]; if lower, the formula may be wrong

## Case Studies

### Case 1: Simple Momentum (mappable → PASS)

```
Input:  "Ref($close, 20) / $close - 1"
Parse:  ExprType.MOMENTUM, window=20
Map:    custom_price → REVS20
Bench:  Corr(REVS20) = 1.0
Result: PASS, auto-verification complete
```

### Case 2: Cross-Sectional Momentum (unmappable → NC)

```
Input:  "Rank(Ref($close, 20) / $close - 1)"
Parse:  ExprType.CROSS_SECTIONAL
Map:    None — Rank() is unmappable
Result: NC → feedback: "Rank operation requires cross-sectional data"
```

### Case 3: Volume Momentum (mappable → verify benchmark)

```
Input:  "$volume / Mean($volume, 10)"
Parse:  ExprType.VOLUME_RATIO, window=10
Map:    custom_price → VOL10
Bench:  Corr(VOL10) = 1.0
Result: PASS, auto-verification complete
```

## Feedback Format

Structured feedback returned to the AI miner:

```json
{
  "batch_summary": {
    "total": 10,
    "passed": 3,
    "failed": 1,
    "nc": 5,
    "unknown": 1
  },
  "successful_patterns": ["MOMENTUM", "VOLUME_RATIO", "MOMENTUM"],
  "avoid_patterns": [
    "Rank(Ref($close, 20) / $close - 1): Cross-sectional rank...",
    "IndNeutralize(Ref($close, 20) / $close - 1, SW1): ..."
  ],
  "suggestion": "Focus on time-series momentum, volume, and volatility..."
}
```

## Integration Point

`mining_bridge.py` → `service.py` — a new CLI subcommand:

```bash
python -m research_core.factor_lab.cli verify-candidates \
  --expressions candidate_expressions.json \
  --output results.json
```

This feeds candidate expressions through the bridge and outputs verification
results + structured feedback.
