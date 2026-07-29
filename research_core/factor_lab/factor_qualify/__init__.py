"""
factor_qualify — 因子实盘就绪度自动化验证

用法:
  python -m factor_qualify run --factor <path> [--oos-split YYYY-MM-DD] [-o report.json]
"""

from research_core.factor_lab.factor_qualify.cli import run
from research_core.factor_lab.factor_qualify.validate import run_validation
from research_core.factor_lab.factor_qualify.data import load_full_data, compute_factor
