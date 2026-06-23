## Summary

Add the jq_gm factor library to AgentMatrix Research — the first non-formula, external-data-source-driven factor library. Includes diagnostic engine, NC classifier, CI gates, mining bridge, feedback loop, and end-to-end experiment.

## What's Included

### jq_gm Factor Library (W1-2)
- **215 FactorResearchSpec** across 10 categories
- **Compute engine** wrapping GM SDK with stub fallback for CI
- **18 unit tests** covering spec validity and compute routing
- **4 CLI subcommands**: list-jq-gm, export-jq-gm, run-jq-gm-demo, run-jq-gm-proof-batch

### Diagnostic Engine (W3-4)
- **diagnostics.py** — 12 root-cause detectors (median-based TTM, unit scale, stock-NC, structural diff)
- **nc_classifier.py** — 3-layer NC classifier with 127+ known patterns (V67 + financial TTM validation + pattern matching)
- **service.py** integration — NC + diagnosis run automatically in proof-batch

### CI Gates (W6)
- **check_regression.py** — detects factor value changes >5% between builds
- **check_coverage.py** — verifies all specs have gm_field, display_name, tests
- **factor-validation.yml** — both gates wired into CI workflow

### Documentation (W7)
- **FACTOR_LAB_CONTRIBUTOR_GUIDE.md** — 5-step onboarding
- **gm_field_mapping.md** — 21 field-name corrections + API field limits
- **unit_scale_rules.md** — 11 scaling categories + 4 common pitfalls
- **nc_factors.md** — NC categories, stock-level NC, 16 lessons learned

### Mining Bridge (W8-9)
- **mining_bridge.py** — Qlib expression parser (13 patterns, including compound) → 3-layer mappability:
  - PASS/PENDING_GM: time-series momentum, volume, volatility → custom_price route
  - PENDING_JQ: Rank, IndNeutralize, Group, Cut → needs JQ engine
  - NC: unparseable expressions
- **_compute_directly()** — computes factors from panel data directly (bypasses FACTOR_REGISTRY/GM SDK)
- Data-source agnostic: only checks column names (close/volume/high/low)

### Feedback Loop + End-to-End Experiment (W10-11)
- **auto_factor_miner.py** — `_build_prompt()`, `auto_mine()`, `propose_candidates()` all accept `feedback` param
- **cli.py** — `--feedback` arg (file path or inline text)
- **feedback_to_prompt()** — structured VerificationResults → compact LLM prompt
- **feedback_to_miner()** — JSON feedback with batch summary + successful patterns + avoid patterns + suggestions
- **mining_loop_experiment.py** — 2-round simulation on demo panel (100d × 30 stocks)
- **FACTOR_MINING_CLOSED_LOOP.md** — full experiment writeup

#### Experiment Results
| Round | Candidates | PASS | FAIL | PENDING_JQ | NC | PASS Rate |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| R1 (no feedback) | 10 | 7 | 1 | 1 | 1 | 70% |
| R2 (with feedback) | 8 | 8 | 0 | 0 | 0 | **100%** |

Feedback eliminated ALL cross-sectional ops and unparseable patterns. 4 factors selected for jq_gm entry.

## Verification Status

| Layer | Method | Result |
|-------|--------|--------|
| Spec completeness | Coverage check | 215/215 have gm_field ✅ |
| Unit tests | 18 pytests | All passing ✅ |
| Pipeline | proof-batch on Mac | End-to-end operational ✅ |
| NC classification | VM: 57 factors × 248 stocks | 129 factors diagnosed ✅ |
| Regression gate | Stub mode CI | Detects compute failures ✅ |
| Feedback loop | 2-round simulation | 70% → 100% PASS rate ✅ |

## Files Changed

```
research_core/factor_lab/
├── diagnostics.py                               (+436 new)
├── nc_classifier.py                             (+387 new)
├── mining_bridge.py                             (+390 new, expanded patterns + feedback)
├── service.py                                   (+120 modified)
├── scripts/
│   ├── mining_loop_experiment.py                 (+160 new)
│   └── w10_experiment_results.json
└── libraries/jq_gm/
    ├── specs.py                                  (217 specs)
    ├── factors.py                                (compute + stub)
    ├── test_factors.py                           (18 tests)
    └── references/

research_core/qlib_lab/
├── auto_factor_miner.py                          (+30 modified, feedback param)
└── cli.py                                        (+6 modified, --feedback arg)

scripts/
├── check_regression.py                          (+156 new)
└── check_coverage.py                            (+116 new)

docs/
├── FACTOR_LAB_CONTRIBUTOR_GUIDE.md              (+147 new)
├── gm_field_mapping.md                          (+105 new)
├── unit_scale_rules.md                          (+83 new)
├── nc_factors.md                                (+186 new)
├── mining_bridge_design.md                      (+160 new)
└── FACTOR_MINING_CLOSED_LOOP.md                 (+160 new)

.github/workflows/
└── factor-validation.yml                         (+12 modified)
```

## Questions for Reviewer

**Q1 (P2) — required_fields 隐式依赖**: `market_cap` 的 `required_fields = ["tot_mv"]`，但实际计算时还需要 `close` 做复权推导。alpha101 惯例只写直接输入字段，不写隐式依赖。jq_gm 按同样惯例处理，还是必须列出所有依赖？

**Q2 (P3) — preprocessing 按路由细分**: 所有因子统一用 `["adjust_prices", "align_trading_calendar"]`，但财务因子不涉及价格数据，复权无意义。需要按路由类型设置不同 preprocessing 吗？

**Q3 (P2) — gm_field 提升为标准字段**: 目前放在 `metadata` 里。如果未来有 Wind/Tushare 等其他数据源库，它们也会有类似字段。是否应提升到 Spec 顶层？

**Q4 (P3) — formula 表示约定**: formula 字段三种写法混用——直接字段名、TTM 缩写、完整表达式。需要统一格式吗？

**Q5 (P1) — CI 无真值因子状态**: 188 个因子暂无外部真值。计划标 `pending_external_truth`。JQ SDK 已就绪，数据可拉，仅等 NC 分类器。可行还是用其他标签？

**Q6 (P3) — source_document 措辞**: `"JoinQuant Factor Board Taxonomy — GM SDK Implementation"` 是否准确传达"参考聚宽分类体系、独立用掘金 SDK 实现"？

**Q7 (P3) — references 目录**: alpha101 没有 references/，jq_gm 有。保留还是清理？

**Q8 (P2) — custom_price 单日 NaN**: 需多日历史窗口。管线是否需要支持多日计算模式？

