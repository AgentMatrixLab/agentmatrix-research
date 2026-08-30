"""Factor DB：A股因子数据库产品模块。

提供因子元数据目录、检索服务、因子值查询（经 Quant API v2）、
分布统计与数据导出，以及 Flask API 蓝图。
"""

from research_core.factor_db.metadata import (
    dictionary_rows,
    get_factor,
    get_stats,
    list_factors,
)
from research_core.factor_db.service import (
    export_factor_data,
    factor_distribution,
    factor_values,
)

__all__ = [
    "dictionary_rows",
    "get_factor",
    "get_stats",
    "list_factors",
    "export_factor_data",
    "factor_distribution",
    "factor_values",
]
