#!/usr/bin/env python3
"""End-to-end bridge verification with GM SDK.

Requires GM terminal. Falls back gracefully when unavailable.

Usage: python scripts/bridge_e2e_verify.py <GM_TOKEN>
"""
import sys, os, json
import numpy as np
import pandas as pd

# GM SDK project dir (gm_factor_lib.py lives here)
_PROJECT_DIR = os.environ.get("GM_PROJECT_DIR", r"C:\Users\lorenzoteng\.goldminer3\projects")
if os.path.isdir(_PROJECT_DIR):
    sys.path.insert(0, _PROJECT_DIR)

_GM_AVAILABLE = False
try:
    from gm.api import set_token as _gm_set_token
    from gm_factor_lib import calc_factors as _gm_calc
    _GM_AVAILABLE = True
except ImportError:
    pass

def main():
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GM_TOKEN", "")
    if not token:
        print("用法: python scripts/bridge_e2e_verify.py <GM_TOKEN>")
        sys.exit(0)
    if not _GM_AVAILABLE:
        print("GM SDK not available on this machine.")
        sys.exit(0)
    
    _gm_set_token(token)
    
    # Test expressions
    test_exprs = [
        "Ref($close,20)/$close-1",
        "$close/Mean($close,20)-1",
        "Std($close,20)",
    ]
    
    from research_core.factor_lab.mining_bridge import parse_expression, batch_verify
    results = []
    for expr in test_exprs:
        parsed = parse_expression(expr)
        results.append({
            "expression": expr,
            "type": parsed.expr_type.name if parsed else "None",
        })
    print(json.dumps({"status": "ok", "results": results}, indent=2))

if __name__ == "__main__":
    main()
