#!/usr/bin/env python3
"""因子质量验证 — 命令行入口"""

from __future__ import annotations
import sys
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd


def load_factor_function(factor_path: str):
    path = Path(factor_path).resolve()
    if not path.exists(): raise FileNotFoundError(f"因子文件不存在: {path}")
    spec = importlib.util.spec_from_file_location("user_factor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "compute"):
        raise AttributeError("因子文件缺少 compute(panel) -> Series 函数")
    return mod.compute


def run(args=None):
    if args is None: args = sys.argv[1:]
    factor_path = ""
    output_path = ""
    i = 0
    while i < len(args):
        if args[i] == "--factor" and i + 1 < len(args): factor_path = args[i + 1]; i += 2
        elif args[i] in ("-o", "--output") and i + 1 < len(args): output_path = args[i + 1]; i += 2
        elif args[i] == "run": i += 1
        else: i += 1

    if not factor_path:
        print("用法: python -m factor_qualify run --factor <path> [-o report.json]")
        print("因子文件格式: def compute(panel: pd.DataFrame) -> pd.Series")
        print("  panel 包含 date, code, open, high, low, close, volume")
        sys.exit(1)

    print(f"因子: {factor_path}")
    factor_fn = load_factor_function(factor_path)

    from factor_qualify.data import load_full_data, compute_factor
    df = load_full_data()
    print(f"数据: {len(df)}行, {df['code'].nunique()}只股票, {df['date'].min().date()}~{df['date'].max().date()}")

    df = compute_factor(df, factor_fn)
    df = df.sort_values(['code','date']).reset_index(drop=True)
    df['ret'] = df.groupby('code')['close'].pct_change(5).shift(-5)  # 周频收益
    df = df.dropna(subset=['factor_value','ret']).reset_index(drop=True)

    print(f"有效因子值: {len(df)}行")
    from factor_qualify.validate import run_validation
    result = run_validation(df, 'factor_value', 'ret')

    from factor_qualify.report import generate_report, print_summary
    report = generate_report(result, output_path)
    result['report'] = report
    print_summary(result)


if __name__ == "__main__":
    run()
