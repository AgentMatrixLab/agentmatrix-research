# Core modules that are always safe to import
from research_core.factor_lab.operators import __all__ as _operators_all  # noqa: F401
from research_core.factor_lab.formula_compiler import compile_formula  # noqa: F401

# Service-layer imports — may fail if optional dependencies are missing
try:
    from research_core.factor_lab.runtime import FactorLabWorkspaceConfig  # noqa: F401
    from research_core.factor_lab.service import (  # noqa: F401
        check_amazingdata,
        get_alpha101_factor_detail,
        get_factor_lab_job,
        get_factor_lab_overview,
        list_alpha101_factors,
        list_factor_lab_jobs,
        run_alpha101_research_job,
        run_factor_set_real_data_job,
        run_factor_set_research_job,
        run_stratified_analysis_job,
    )
    from research_core.factor_lab.stratified import (  # noqa: F401
        batch_stratified_analysis,
        compute_stratified_analysis,
    )
    _service_available = True
except ImportError:
    _service_available = False


__all__ = [
    "compile_formula",
    "FactorLabWorkspaceConfig",
    "batch_stratified_analysis",
    "check_amazingdata",
    "compute_stratified_analysis",
    "get_alpha101_factor_detail",
    "get_factor_lab_job",
    "get_factor_lab_overview",
    "list_alpha101_factors",
    "list_factor_lab_jobs",
    "run_alpha101_research_job",
    "run_factor_set_real_data_job",
    "run_factor_set_research_job",
    "run_stratified_analysis_job",
]
