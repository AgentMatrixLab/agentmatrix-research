# ============================================================
# Factor Library
# ============================================================

from .operators import (
    rank_cross_section,
    tsrank,
    ts_corr,
    delta,
    delay,
    tsmax,
    tsmin,
    ts_argmax,
    compute_vwap,
    sma_gtja
)

from .wq101_alpha_1_10 import compute_all_alphas as compute_wq101_alphas
from .gtja191_alpha_1_10 import compute_all_alphas as compute_gtja191_alphas
from .batch_compute import compute_factor_set
from .ai_factor_mining import CandidateFactor, generate_candidate_factors, mine_and_validate_factors

__all__ = [
    # Operators
    'rank_cross_section',
    'tsrank',
    'ts_corr',
    'delta',
    'delay',
    'tsmax',
    'tsmin',
    'ts_argmax',
    'compute_vwap',
    'sma_gtja',
    # Factor compute
    'compute_wq101_alphas',
    'compute_gtja191_alphas',
    'compute_factor_set',
    # AI mining prototype
    'CandidateFactor',
    'generate_candidate_factors',
    'mine_and_validate_factors',
]
