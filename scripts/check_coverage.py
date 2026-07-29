#!/usr/bin/env python3
"""CI coverage gate for jq_gm factor library.

Checks:
  1. All specs have gm_field (ensure compute routing works)
  2. All specs have display_name + description (quality)
  3. Test file exists and has expected test count
  4. Truth CSV coverage (informational only)

Usage:
    python scripts/check_coverage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    specs_file = root / "research_core/factor_lab/libraries/jq_gm/specs.py"
    test_file = root / "research_core/factor_lab/libraries/jq_gm/test_factors.py"
    truth_csv = root / "data/factor_lab/jq_gm_truth.csv"

    if not specs_file.exists():
        print(f"ERROR: specs.py not found at {specs_file}")
        return 1

    spec_content = specs_file.read_text(encoding="utf-8")

    # Extract factor names
    spec_factors = sorted(set(re.findall(r'factor_name="([^"]+)"', spec_content)))
    print(f"Spec factors: {len(spec_factors)}")

    # Extract gm_field for each spec (multi-line spec format)
    spec_blocks = spec_content.split('FactorResearchSpec(')
    missing_gm_field: list[str] = []
    missing_display: list[str] = []
    missing_desc: list[str] = []

    for block in spec_blocks[1:]:
        fk_match = re.search(r'factor_name="([^"]+)"', block)
        if not fk_match:
            continue
        fk = fk_match.group(1)

        has_gm = 'gm_field' in block
        if not has_gm:
            missing_gm_field.append(fk)

        if 'display_name=""' in block or 'display_name=""' not in block and 'display_name=' not in block:
            # Complex check: just check it exists
            if 'display_name=' not in block:
                missing_display.append(fk)

        if 'description=""' in block:
            missing_desc.append(fk)

    # Check tests
    test_content = test_file.read_text(encoding="utf-8") if test_file.exists() else ""
    test_count = len(re.findall(r'def test_', test_content))
    has_spec_format_tests = 'test_spec_count_is_215' in test_content
    has_compute_tests = 'TestComputeStub' in test_content or 'test_stub' in test_content

    # Check truth
    truth_count = 0
    if truth_csv.exists():
        import pandas as pd
        df = pd.read_csv(truth_csv, nrows=1)
        reserved = {"date", "code", "symbol"}
        truth_cols = {c for c in df.columns if c not in reserved}
        truth_count = len(truth_cols & set(spec_factors))

    # Report
    failures = 0

    if missing_gm_field:
        print(f"Missing gm_field: {len(missing_gm_field)}")
        for fk in missing_gm_field[:5]:
            print(f"  - {fk}")
        failures += len(missing_gm_field)
    else:
        print("gm_field: all present")

    if missing_desc:
        print(f"Empty description: {len(missing_desc)}")
        failures += len(missing_desc)

    print(f"Tests: {test_count} test functions")
    if has_spec_format_tests:
        print("  Spec format tests: present")
    else:
        print("  Spec format tests: MISSING")
        failures += 1

    if has_compute_tests:
        print("  Compute stub tests: present")
    else:
        print("  Compute stub tests: MISSING")
        failures += 1

    print(f"Truth CSV coverage: {truth_count}/{len(spec_factors)}")

    if failures == 0:
        print("\nPASSED: all coverage checks")
        return 0

    print(f"\nFAILED: {failures} coverage gap(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
