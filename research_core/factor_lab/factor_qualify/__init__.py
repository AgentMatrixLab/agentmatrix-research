"""
factor_qualify — 因子实盘就绪度自动化验证

用法:
  python -m factor_qualify run --factor <path> [--oos-split YYYY-MM-DD] [-o report.json]
"""

from factor_qualify.cli import run
from factor_qualify.validate import run_validation
from factor_qualify.data import load_full_data, compute_factor
