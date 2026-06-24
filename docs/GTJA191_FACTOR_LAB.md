# GTJA191 Factor Lab

This repository exposes the full GTJA191 / Alpha191 price-volume factor set through `research_core.factor_lab`.

## Scope

- `research_core.factor_lab.libraries.gtja191` registers `alpha1` through `alpha191`.
- `compute_gtja191_alphas(panel, factor_names=...)` supports any valid subset or the full catalog.
- `list-factor-set --factor-set gtja191` returns 191 factor specs.
- Specs use the paper-derived GTJA191 formula manifest as the formula source and record the `py-alpha-lib` adapter as the execution engine.

## Runtime Boundary

The implementation vendors the reviewed `examples/gtja191/al/alpha191.py` execution adapter from `tic-top/py-alpha-lib` and uses `py-alpha-lib` for the execution context helpers. The adapter keeps the existing factor_lab shape: input panel columns are normalized to the Alpha191 context and output is returned as a `date, code, alpha*` frame.

The demo path validates registration and computation on deterministic OHLCV data. Full-market reproduction with ClickHouse data remains an environment-specific run because database credentials and raw exports are not committed to the repository.

## Quick Checks

```bash
python -m research_core.factor_lab.cli list-factor-set --factor-set gtja191
python -m research_core.factor_lab.cli run-factor-set-demo --factor-set gtja191 --factors alpha1,alpha10,alpha11,alpha100,alpha149,alpha191 --n-dates 320 --n-codes 8
python -m unittest research_core.factor_lab.libraries.test_factor_sets
```
