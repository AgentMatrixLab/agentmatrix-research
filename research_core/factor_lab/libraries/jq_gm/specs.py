"""
jq_gm FactorResearchSpec declarations.

215 non-Alpha factors in 10 categories, independently implemented
via the GM (掘金) SDK.  Each spec declares *what* the factor is
(formula, required fields, validation targets) but not *how* it is
computed — that lives in factors.py.

=== Mapping from FACTOR_REGISTRY ===

The original FACTOR_REGISTRY in gm_factor_lib.py has this shape:

    'market_cap': {
        'name':     '总市值',
        'category': '基础科目及衍生类因子',
        'desc':     '总市值 = 总股本 × 收盘价',
        'gm_field': 'stk_get_daily_mktvalue_pt',  # GM API endpoint
        'gm_fields': 'tot_mv',                     # Field(s) to fetch
    }

We transform each entry into a FactorResearchSpec, keeping the
gm_field / gm_fields as metadata for the compute layer:

    FactorResearchSpec(
        factor_name     = 'market_cap',
        display_name    = '总市值',
        formula         = derived from gm_fields + desc,
        required_fields = [fields parsed from gm_fields],
        gm_field        = stored in metadata for factors.py,
        ...
    )

=== This file — 30 demo factors ===

For the Week 1 Monday review we ship 30 factors covering:
  - All 5 GM API routing types (mktvalue_pt, valuation_pt, basic_pt,
    income_pt, cashflow_pt, balance_pt, deriv_pt, custom, custom_price)
  - First 5 categories (基础科目, 质量, 动量, 成长, 情绪)

The remaining 185 factors follow the same template and will be
batch-generated after the Monday review confirms the format.

=== FactorResearchSpec dataclass (from contracts/factor_research.py) ===

  factor_name: str             Unique ID (e.g. 'market_cap')
  library: str                 'jq_gm'
  version: str                 Schema version
  display_name: str            Chinese display name
  factor_id: str               Optional external ID
  source_document: str         Provenance
  formula: str                 Formula or field reference
  description: str             Human-readable explanation
  frequency: str               'day'
  sample_scope: str            Stock universe
  required_fields: list[str]   Input data fields
  parameters: dict             Tunable parameters
  preprocessing: list[str]     Preprocessing steps
  neutralization: list[str]    Neutralization applied
  validation_targets: list     Thresholds for proof checks
  tags: list[str]              Category / classification tags
  notes: list[str]             Implementation notes
  metadata: dict               Extra fields (gm_field, gm_fields, routing)
"""

from __future__ import annotations

from contracts.factor_research import FactorResearchSpec, ValidationThreshold

# ── Library metadata ────────────────────────────────────────────
#
# These constants mirror the pattern in alpha101/specs.py, used by
# the factor_lab service layer to tag and version every spec.

JQ_GM_LIBRARY = "jq_gm"
JQ_GM_VERSION = "v2026.06"
JQ_GM_SOURCE = "JoinQuant Factor Board Taxonomy — GM (掘金) SDK Implementation"

# ── Common validation thresholds ────────────────────────────────
#
# All jq_gm factors share the same four proof checks.  The cross_section
# threshold (0.99 Spearman) is the same as alpha101 — we want near-perfect
# alignment with JQ truth data before marking a factor as verified.

JQ_GM_COMMON_THRESHOLDS = [
    ValidationThreshold(
        metric="formula_match_ratio",
        operator=">=",
        value=1.0,
        description="代码实现与规格书公式逐项一致。",
    ),
    ValidationThreshold(
        metric="field_mapping_match_ratio",
        operator=">=",
        value=1.0,
        description="字段、复权、频率和股票池口径一致。",
    ),
    ValidationThreshold(
        metric="sample_point_error_ratio",
        operator="<=",
        value=0.0,
        description="抽样点位误差为零。",
    ),
    ValidationThreshold(
        metric="cross_section_spearman",
        operator=">=",
        value=0.99,
        description="与聚宽(JQ)外部真值做截面对齐。",
    ),
]

# ── Shared defaults ─────────────────────────────────────────────
#
# These apply to every jq_gm factor.  Individual factors can override
# in the _build_spec() helper.

_JQ_GM_DEFAULTS = {
    "library": JQ_GM_LIBRARY,
    "version": JQ_GM_VERSION,
    "source_document": JQ_GM_SOURCE,
    "frequency": "day",
    "sample_scope": (
        "A-share standard pool; remove ST, delisted, and newly-listed "
        "securities when applicable.  GM terminal data, pre-adjustment "
        "prices (前复权) by default."
    ),
    "preprocessing": ["adjust_prices", "align_trading_calendar"],
    "neutralization": [],
    "validation_targets": JQ_GM_COMMON_THRESHOLDS,
    "metadata": {"status": "implemented", "implementation_stage": "code"},
}


def _build_spec(
    factor_name: str,
    display_name: str,
    formula: str,
    required_fields: list[str],
    *,
    category: str = "",
    description: str = "",
    gm_field: str = "",
    gm_fields: str = "",
    parameters: dict | None = None,
    tags: list[str] | None = None,
    notes: list[str] | None = None,
    preprocessing: list[str] | None = None,
    neutralization: list[str] | None = None,
    metadata_overrides: dict | None = None,
) -> FactorResearchSpec:
    """Build a FactorResearchSpec with library-wide defaults.

    Every jq_gm factor shares the same library, version, source, and
    validation targets.  This helper fills those in so individual
    factor declarations only need to specify what makes them unique.

    Args:
        factor_name:    Unique ID (e.g. 'market_cap')
        display_name:   Chinese name (e.g. '总市值')
        formula:        Formula string or field reference
        required_fields: GM API fields needed for computation
        category:       Factor category (stored as first tag)
        description:    Human-readable explanation (defaults to formula)
        gm_field:       GM API endpoint name
        gm_fields:      Comma-separated field names within the endpoint
        parameters:     Additional keyword parameters
        tags:           Extra tags (category is prepended automatically)
        notes:          Implementation notes
        preprocessing:  Override default preprocessing
        neutralization: Override default neutralization
        metadata_overrides: Extra metadata merged on top of defaults
    """
    # Build tags: category goes first, then any extra tags
    all_tags: list[str] = []
    if category:
        all_tags.append(category)
    if tags:
        all_tags.extend(tags)

    # Build metadata: defaults + routing info + overrides
    metadata = dict(_JQ_GM_DEFAULTS["metadata"])
    metadata["gm_field"] = gm_field
    metadata["gm_fields"] = gm_fields
    if metadata_overrides:
        metadata.update(metadata_overrides)

    return FactorResearchSpec(
        factor_name=factor_name,
        library=_JQ_GM_DEFAULTS["library"],
        version=_JQ_GM_DEFAULTS["version"],
        display_name=display_name,
        source_document=_JQ_GM_DEFAULTS["source_document"],
        formula=formula,
        description=description or formula,
        frequency=_JQ_GM_DEFAULTS["frequency"],
        sample_scope=_JQ_GM_DEFAULTS["sample_scope"],
        required_fields=required_fields,
        parameters=parameters or {},
        preprocessing=preprocessing or list(_JQ_GM_DEFAULTS["preprocessing"]),
        neutralization=neutralization or list(_JQ_GM_DEFAULTS["neutralization"]),
        validation_targets=list(_JQ_GM_DEFAULTS["validation_targets"]),
        tags=all_tags,
        notes=notes or [],
        metadata=metadata,
    )

JQ_GM_SPEC_market_cap = _build_spec(
    factor_name="market_cap",
    display_name="总市值",
    formula="tot_mv",
    required_fields=["tot_mv"],
    category="基础科目及衍生类因子",
    description="总市值 = 总股本 × 收盘价",
    gm_field="stk_get_daily_mktvalue_pt",
    gm_fields="tot_mv",
)

JQ_GM_SPEC_circulating_market_cap = _build_spec(
    factor_name="circulating_market_cap",
    display_name="流通市值",
    formula="flow_mv",
    required_fields=["flow_mv"],
    category="基础科目及衍生类因子",
    description="流通市值 = 流通股本 × 收盘价，v49修正: a_mv→flow_mv(mktvalue_pt验证字段名)",
    gm_field="stk_get_daily_mktvalue_pt",
    gm_fields="flow_mv",
)

JQ_GM_SPEC_pe_ttm = _build_spec(
    factor_name="pe_ttm",
    display_name="市盈率TTM",
    formula="pe_ttm",
    required_fields=["pe_ttm"],
    category="基础科目及衍生类因子",
    description="PE(TTM) = 总市值 / 净利润(TTM)，净利润为过去12个月滚动值",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="pe_ttm",
)

JQ_GM_SPEC_pe_ratio = _build_spec(
    factor_name="pe_ratio",
    display_name="市盈率（静态）",
    formula="pe_lyr",
    required_fields=["pe_lyr"],
    category="基础科目及衍生类因子",
    description="PE = 总市值 / 净利润（上年年报）",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="pe_lyr",
)

JQ_GM_SPEC_pb_mrq = _build_spec(
    factor_name="pb_mrq",
    display_name="市净率",
    formula="pb_mrq",
    required_fields=["pb_mrq"],
    category="基础科目及衍生类因子",
    description="PB(MRQ) = 总市值 / 净资产（最新报告期）",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="pb_mrq",
)

JQ_GM_SPEC_ps_ttm = _build_spec(
    factor_name="ps_ttm",
    display_name="市销率TTM",
    formula="ps_ttm",
    required_fields=["ps_ttm"],
    category="基础科目及衍生类因子",
    description="PS(TTM) = 总市值 / 营业收入(TTM)",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="ps_ttm",
)

JQ_GM_SPEC_pcf_ttm = _build_spec(
    factor_name="pcf_ttm",
    display_name="市现率TTM",
    formula="pcf_ttm_oper",
    required_fields=["pcf_ttm_oper"],
    category="基础科目及衍生类因子",
    description="PCF(TTM) = 总市值 / 经营活动现金流净额(TTM)",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="pcf_ttm_oper",
)

JQ_GM_SPEC_turnover_ratio = _build_spec(
    factor_name="turnover_ratio",
    display_name="换手率",
    formula="turnrate",
    required_fields=["turnrate"],
    category="基础科目及衍生类因子",
    description="换手率 = 成交量 / 流通股本 × 100%",
    gm_field="stk_get_daily_basic_pt",
    gm_fields="turnrate",
)

JQ_GM_SPEC_total_operating_revenue_ttm = _build_spec(
    factor_name="total_operating_revenue_ttm",
    display_name="营业总收入TTM",
    formula="inc_oper",
    required_fields=["inc_oper"],
    category="基础科目及衍生类因子",
    description="过去12个月营业总收入之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="inc_oper",
)

JQ_GM_SPEC_operating_profit_ttm = _build_spec(
    factor_name="operating_profit_ttm",
    display_name="营业利润TTM",
    formula="oper_prof",
    required_fields=["oper_prof"],
    category="基础科目及衍生类因子",
    description="过去12个月营业利润之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="oper_prof",
)

JQ_GM_SPEC_net_profit_ttm = _build_spec(
    factor_name="net_profit_ttm",
    display_name="净利润TTM",
    formula="net_prof",
    required_fields=["net_prof"],
    category="基础科目及衍生类因子",
    description="过去12个月净利润之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="net_prof",
)

JQ_GM_SPEC_operating_revenue_ttm = _build_spec(
    factor_name="operating_revenue_ttm",
    display_name="营业收入TTM",
    formula="inc_oper",
    required_fields=["inc_oper"],
    category="基础科目及衍生类因子",
    description="过去12个月营业收入之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="inc_oper",
)

JQ_GM_SPEC_net_operate_cash_flow_ttm = _build_spec(
    factor_name="net_operate_cash_flow_ttm",
    display_name="经营活动现金流量净额TTM",
    formula="net_cf_oper",
    required_fields=["net_cf_oper"],
    category="基础科目及衍生类因子",
    description="过去12个月经营活动现金流量净额之和，v13验证: TTM vs JQ偏差10-778%（均值186%），根因: 现金流数据源级差异(部分符号相反)，不可修复",
    gm_field="stk_get_fundamentals_cashflow_pt",
    gm_fields="net_cf_oper",
)

JQ_GM_SPEC_net_invest_cash_flow_ttm = _build_spec(
    factor_name="net_invest_cash_flow_ttm",
    display_name="投资活动现金流量净额TTM",
    formula="Custom(投资活动现金流量净额TTM)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="过去12个月投资活动现金流量净额之和，v49修正: net_cf_inv不存在于cashflow_pt，改用custom+non-_pt API计算",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_finance_cash_flow_ttm = _build_spec(
    factor_name="net_finance_cash_flow_ttm",
    display_name="筹资活动现金流量净额TTM",
    formula="net_cf_fin",
    required_fields=["net_cf_fin"],
    category="基础科目及衍生类因子",
    description="过去12个月筹资活动现金流量净额之和，v49修正: net_cf_fin在cashflow_pt中确认有效(v33验证)，恢复_pt API",
    gm_field="stk_get_fundamentals_cashflow_pt",
    gm_fields="net_cf_fin",
)

JQ_GM_SPEC_total_profit_ttm = _build_spec(
    factor_name="total_profit_ttm",
    display_name="利润总额TTM",
    formula="ttl_prof",
    required_fields=["ttl_prof"],
    category="基础科目及衍生类因子",
    description="过去12个月利润总额之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="ttl_prof",
)

JQ_GM_SPEC_operating_cost_ttm = _build_spec(
    factor_name="operating_cost_ttm",
    display_name="营业成本TTM",
    formula="cost_oper",
    required_fields=["cost_oper"],
    category="基础科目及衍生类因子",
    description="过去12个月营业成本之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="cost_oper",
)

JQ_GM_SPEC_total_operating_cost_ttm = _build_spec(
    factor_name="total_operating_cost_ttm",
    display_name="营业总成本TTM",
    formula="cost_oper",
    required_fields=["cost_oper"],
    category="基础科目及衍生类因子",
    description="过去12个月营业总成本之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="cost_oper",
)

JQ_GM_SPEC_np_parent_company_owners_ttm = _build_spec(
    factor_name="np_parent_company_owners_ttm",
    display_name="归母净利润TTM",
    formula="net_prof_pcom",
    required_fields=["net_prof_pcom"],
    category="基础科目及衍生类因子",
    description="过去12个月归属于母公司股东的净利润之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="net_prof_pcom",
)

JQ_GM_SPEC_sale_expense_ttm = _build_spec(
    factor_name="sale_expense_ttm",
    display_name="销售费用TTM",
    formula="Custom(销售费用TTM)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="过去12个月销售费用之和，v49修正: exp_sell不存在于income_pt，改用custom+non-_pt API",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_administration_expense_ttm = _build_spec(
    factor_name="administration_expense_ttm",
    display_name="管理费用TTM",
    formula="Custom(管理费用TTM)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="过去12个月管理费用之和，v49修正: exp_adm不存在于income_pt，改用custom+non-_pt API",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_financial_expense_ttm = _build_spec(
    factor_name="financial_expense_ttm",
    display_name="财务费用TTM",
    formula="exp_fin",
    required_fields=["exp_fin"],
    category="基础科目及衍生类因子",
    description="过去12个月财务费用之和，v13验证: TTM vs JQ偏差8-37%（均值37.4%），根因: data_type=102合并调整破坏FY=H1+H2加法性，不可修复",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="exp_fin",
)

JQ_GM_SPEC_gross_profit_ttm = _build_spec(
    factor_name="gross_profit_ttm",
    display_name="毛利TTM",
    formula="Custom(毛利TTM)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="过去12个月毛利之和 = 营业收入TTM - 营业成本TTM",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_asset_impairment_loss_ttm = _build_spec(
    factor_name="asset_impairment_loss_ttm",
    display_name="资产减值损失TTM",
    formula="Custom(资产减值损失TTM)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="过去12个月资产减值损失之和，v49修正: ast_impr_loss在_pt API中列存在但值不稳定，改用custom",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_value_change_profit_ttm = _build_spec(
    factor_name="value_change_profit_ttm",
    display_name="价值变动净收益TTM",
    formula="Custom(价值变动净收益TTM)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="过去12个月公允价值变动净收益+投资净收益之和，v49修正: inc_fv_chg字段需验证",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_non_operating_net_profit_ttm = _build_spec(
    factor_name="non_operating_net_profit_ttm",
    display_name="营业外收支净额TTM",
    formula="Custom(营业外收支净额TTM)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="营业外收入TTM - 营业外支出TTM，v49修正: inc_noper/exp_noper字段需验证",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_EBIT = _build_spec(
    factor_name="EBIT",
    display_name="息税前利润",
    formula="Custom(息税前利润)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="EBIT = 营业利润 + 财务费用（反推验证确认：oper_prof + exp_fin），v17修正: 原 ebit_inverse 常返回NaN，改用 income_pt 自算",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_EBITDA = _build_spec(
    factor_name="EBITDA",
    display_name="息税折旧摊销前利润",
    formula="Custom(息税折旧摊销前利润)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="EBITDA = EBIT + 折旧摊销(cur_depr_amort)。v17修正: 原 ebitda_inverse 常返回NaN，改用 EBIT自算 + cur_depr_amort(deriv_pt)。",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_working_capital = _build_spec(
    factor_name="net_working_capital",
    display_name="净运营资本",
    formula="ttl_cur_ast, ttl_cur_liab",
    required_fields=["ttl_cur_ast", "ttl_cur_liab"],
    category="基础科目及衍生类因子",
    description="净运营资本 = 流动资产 - 流动负债",
    gm_field="stk_get_fundamentals_balance_pt",
    gm_fields="ttl_cur_ast, ttl_cur_liab",
)

JQ_GM_SPEC_retained_earnings = _build_spec(
    factor_name="retained_earnings",
    display_name="留存收益",
    formula="sur_rsv, ret_prof",
    required_fields=["sur_rsv", "ret_prof"],
    category="基础科目及衍生类因子",
    description="留存收益 = 盈余公积 + 未分配利润",
    gm_field="stk_get_fundamentals_balance_pt",
    gm_fields="sur_rsv, ret_prof",
)

JQ_GM_SPEC_financial_assets = _build_spec(
    factor_name="financial_assets",
    display_name="金融资产",
    formula="pur_resell_fin,cred_inv,oth_cred_inv,fair_val_fin_ast,amor_cos_fin_ast_ncur,ln_to_ob,lt_eqy_inv",
    required_fields=["pur_resell_fin", "cred_inv", "oth_cred_inv", "fair_val_fin_ast", "amor_cos_fin_ast_ncur", "ln_to_ob", "lt_eqy_inv"],
    category="基础科目及衍生类因子",
    description="金融资产 = 交易性金融资产 + 衍生金融资产 + 其他权益工具投资 + 其他非流动金融资产 + 长期股权投资。",
    gm_field="custom",
    gm_fields="pur_resell_fin,cred_inv,oth_cred_inv,fair_val_fin_ast,amor_cos_fin_ast_ncur,ln_to_ob,lt_eqy_inv",
)

JQ_GM_SPEC_operating_assets = _build_spec(
    factor_name="operating_assets",
    display_name="经营性资产",
    formula="ttl_ast,pur_resell_fin,cred_inv,oth_cred_inv,fair_val_fin_ast,amor_cos_fin_ast_ncur,ln_to_ob,lt_eqy_inv",
    required_fields=["ttl_ast", "pur_resell_fin", "cred_inv", "oth_cred_inv", "fair_val_fin_ast", "amor_cos_fin_ast_ncur", "ln_to_ob", "lt_eqy_inv"],
    category="基础科目及衍生类因子",
    description="经营性资产 = 总资产 - 金融资产，v16修正: 添加 gm_fields 以便 CSV 生成",
    gm_field="custom",
    gm_fields="ttl_ast,pur_resell_fin,cred_inv,oth_cred_inv,fair_val_fin_ast,amor_cos_fin_ast_ncur,ln_to_ob,lt_eqy_inv",
)

JQ_GM_SPEC_financial_liability = _build_spec(
    factor_name="financial_liability",
    display_name="金融负债（有息负债）",
    formula="int_debt",
    required_fields=["int_debt"],
    category="基础科目及衍生类因子",
    description="有息负债 = 带息债务 int_debt（stk_get_finance_deriv_pt），v13验证: int_debt vs JQ偏差79.0%（int_debt覆盖不全），部分可修复",
    gm_field="stk_get_finance_deriv_pt",
    gm_fields="int_debt",
)

JQ_GM_SPEC_operating_liability = _build_spec(
    factor_name="operating_liability",
    display_name="经营性负债",
    formula="ttl_liab",
    required_fields=["ttl_liab"],
    category="基础科目及衍生类因子",
    description="经营性负债 = 总负债 - 有息负债(int_debt)。v17修正: 原用sht_ln+lt_ln产出负值，改用int_debt更准确。",
    gm_field="stk_get_fundamentals_balance_pt",
    gm_fields="ttl_liab",
)

JQ_GM_SPEC_net_debt = _build_spec(
    factor_name="net_debt",
    display_name="净债务",
    formula="net_debt",
    required_fields=["net_debt"],
    category="基础科目及衍生类因子",
    description="净债务 = 带息债务(int_debt) - 货币资金(mny_cptl)。v17验证: int_debt-mny_cptl与deriv_pt直取net_debt数值相同，偏差未改善(72%)。",
    gm_field="stk_get_finance_deriv_pt",
    gm_fields="net_debt",
)

JQ_GM_SPEC_net_interest_expense = _build_spec(
    factor_name="net_interest_expense",
    display_name="净利息费用",
    formula="Custom(净利息费用)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="净利息费用 = 利息费用 - 利息收入（利润表科目），v49修正: exp_int/inc_int字段需验证",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_goods_sale_and_service_render_cash_ttm = _build_spec(
    factor_name="goods_sale_and_service_render_cash_ttm",
    display_name="销售商品提供劳务收到的现金TTM",
    formula="cash_rcv_sale",
    required_fields=["cash_rcv_sale"],
    category="基础科目及衍生类因子",
    description="过去12个月销售商品提供劳务收到的现金之和，v13验证: TTM vs JQ偏差10-778%（均值186%），根因: 现金流数据源级差异(部分符号相反)，不可修复",
    gm_field="stk_get_fundamentals_cashflow_pt",
    gm_fields="cash_rcv_sale",
)

JQ_GM_SPEC_sales_to_price_ratio = _build_spec(
    factor_name="sales_to_price_ratio",
    display_name="营收市值比",
    formula="Custom(营收市值比)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="营收市值比 = 1 / PS(TTM)",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_cash_flow_to_price_ratio = _build_spec(
    factor_name="cash_flow_to_price_ratio",
    display_name="现金流市值比",
    formula="Custom(现金流市值比)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="现金流市值比 = 1 / PCF(TTM)。注意：JQ get_factor_values()返回的是Barra截面中性化后的残差值，非原始CFP",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_roe_ttm = _build_spec(
    factor_name="roe_ttm",
    display_name="净资产收益率TTM",
    formula="roe_ann",
    required_fields=["roe_ann"],
    category="质量类因子",
    description="ROE(TTM) = roe_ann × 0.01，v13验证: roe_ann/100 vs JQ偏差33.3%（系统偏高），自算ROE(28.3%)方向混乱，不可修复",
    gm_field="stk_get_finance_deriv_pt",
    gm_fields="roe_ann",
)

JQ_GM_SPEC_roa_ttm = _build_spec(
    factor_name="roa_ttm",
    display_name="总资产收益率TTM",
    formula="Custom(总资产收益率TTM)",
    required_fields=["close"],
    category="质量类因子",
    description="ROA(TTM) = 净利润(TTM) / 总资产 × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_gross_income_ratio = _build_spec(
    factor_name="gross_income_ratio",
    display_name="毛利率",
    formula="Custom(毛利率)",
    required_fields=["close"],
    category="质量类因子",
    description="毛利率 = (营业收入 - 营业成本) / 营业收入 × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_profit_margin = _build_spec(
    factor_name="net_profit_margin",
    display_name="净利率",
    formula="Custom(净利率)",
    required_fields=["close"],
    category="质量类因子",
    description="净利率 = 净利润 / 营业收入 × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_profit_margin = _build_spec(
    factor_name="operating_profit_margin",
    display_name="营业利润率",
    formula="Custom(营业利润率)",
    required_fields=["close"],
    category="质量类因子",
    description="营业利润率 = 营业利润 / 营业收入 × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_total_asset_turnover = _build_spec(
    factor_name="total_asset_turnover",
    display_name="总资产周转率",
    formula="Custom(总资产周转率)",
    required_fields=["close"],
    category="质量类因子",
    description="总资产周转率 = 营业收入 / 平均总资产",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_accounts_receivable_turnover = _build_spec(
    factor_name="accounts_receivable_turnover",
    display_name="应收账款周转率",
    formula="Custom(应收账款周转率)",
    required_fields=["close"],
    category="质量类因子",
    description="应收账款周转率 = 营业收入 / 平均应收账款",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_inventory_turnover = _build_spec(
    factor_name="inventory_turnover",
    display_name="存货周转率",
    formula="Custom(存货周转率)",
    required_fields=["close"],
    category="质量类因子",
    description="存货周转率 = 营业成本 / 平均存货",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_cycle = _build_spec(
    factor_name="operating_cycle",
    display_name="营业周期",
    formula="Custom(营业周期)",
    required_fields=["close"],
    category="质量类因子",
    description="营业周期 = 存货周转天数 + 应收账款周转天数",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_cash_ratio = _build_spec(
    factor_name="cash_ratio",
    display_name="现金比率",
    formula="Custom(现金比率)",
    required_fields=["close"],
    category="质量类因子",
    description="现金比率 = 货币资金 / 流动负债",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_current_ratio = _build_spec(
    factor_name="current_ratio",
    display_name="流动比率",
    formula="Custom(流动比率)",
    required_fields=["close"],
    category="质量类因子",
    description="流动比率 = 流动资产 / 流动负债",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_quick_ratio = _build_spec(
    factor_name="quick_ratio",
    display_name="速动比率",
    formula="Custom(速动比率)",
    required_fields=["close"],
    category="质量类因子",
    description="速动比率 = (流动资产 - 存货) / 流动负债",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_debt_to_assets_ratio = _build_spec(
    factor_name="debt_to_assets_ratio",
    display_name="资产负债率",
    formula="Custom(资产负债率)",
    required_fields=["close"],
    category="质量类因子",
    description="资产负债率 = 总负债 / 总资产 × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_tangible_assets_to_debt_ratio = _build_spec(
    factor_name="tangible_assets_to_debt_ratio",
    display_name="有形净值债务率",
    formula="Custom(有形净值债务率)",
    required_fields=["close"],
    category="质量类因子",
    description="有形净值债务率 = 总负债 / (净资产 - 无形资产)",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_net_income = _build_spec(
    factor_name="operating_net_income",
    display_name="经营活动净收益",
    formula="Custom(经营活动净收益)",
    required_fields=["close"],
    category="质量类因子",
    description="经营活动净收益 = 经营活动净收益占比 × 利润总额",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_eps_ttm = _build_spec(
    factor_name="eps_ttm",
    display_name="每股收益TTM",
    formula="Custom(每股收益TTM)",
    required_fields=["close"],
    category="每股指标因子",
    description="EPS(TTM) = 归母净利润(TTM) / 总股本（v13验证: JQ用加权平均股本，GM用总股本ttl_shr，偏差28.4%，不可修复）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_bps = _build_spec(
    factor_name="bps",
    display_name="每股净资产",
    formula="Custom(每股净资产)",
    required_fields=["close"],
    category="每股指标因子",
    description="BPS = 归属母公司股东权益 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_revenue_per_share = _build_spec(
    factor_name="operating_revenue_per_share",
    display_name="每股营业总收入",
    formula="Custom(每股营业总收入)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股营业总收入 = 营业总收入 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_profit_per_share = _build_spec(
    factor_name="operating_profit_per_share",
    display_name="每股营业利润",
    formula="Custom(每股营业利润)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股营业利润 = 营业利润 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_cash_flow_per_share = _build_spec(
    factor_name="cash_flow_per_share",
    display_name="每股经营活动现金流量",
    formula="Custom(每股经营活动现金流量)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股现金流 = 经营活动现金流量净额 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_capital_reserve_per_share = _build_spec(
    factor_name="capital_reserve_per_share",
    display_name="每股资本公积",
    formula="Custom(每股资本公积)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股资本公积 = 资本公积 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_surplus_reserve_per_share = _build_spec(
    factor_name="surplus_reserve_per_share",
    display_name="每股盈余公积",
    formula="Custom(每股盈余公积)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股盈余公积 = 盈余公积 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_retained_earnings_per_share = _build_spec(
    factor_name="retained_earnings_per_share",
    display_name="每股未分配利润",
    formula="Custom(每股未分配利润)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股未分配利润 = 未分配利润 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_revenue_growth_ttm = _build_spec(
    factor_name="operating_revenue_growth_ttm",
    display_name="每股营收同比增长",
    formula="Custom(每股营收同比增长)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股营收同比增长 = (本期每股营收 - 上期每股营收) / |上期每股营收| × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_profit_growth_per_share = _build_spec(
    factor_name="net_profit_growth_per_share",
    display_name="每股净利润同比增长",
    formula="Custom(每股净利润同比增长)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股净利润同比增长 = (本期EPS - 上期EPS) / |上期EPS| × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_beta = _build_spec(
    factor_name="beta",
    display_name="Beta（贝塔）",
    formula="Custom(Beta（贝塔）)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="个股收益率对市场收益率的敏感系数，用过去252日日收益率回归斜率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_size = _build_spec(
    factor_name="size",
    display_name="市值因子",
    formula="Custom(市值因子)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="ln(总市值)，市值越大因子值越大",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_non_linear_size = _build_spec(
    factor_name="non_linear_size",
    display_name="非线性市值",
    formula="Custom(非线性市值)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="cubic(ln(市值))^3，市值非线性特征",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_book_to_price_ratio = _build_spec(
    factor_name="book_to_price_ratio",
    display_name="账面市值比",
    formula="Custom(账面市值比)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="BP = 净资产 / 总市值。注意：JQ get_factor_values()返回的是Barra截面中性化后的残差值，非原始BP",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_earnings_yield = _build_spec(
    factor_name="earnings_yield",
    display_name="盈利收益率",
    formula="Custom(盈利收益率)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="EP = 净利润(TTM) / 总市值。注意：JQ get_factor_values()返回的是Barra截面中性化后的残差值，非原始EP",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_leverage = _build_spec(
    factor_name="leverage",
    display_name="杠杆因子",
    formula="Custom(杠杆因子)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="MLEV = 总市值 / (总市值 + 总负债 - 现金)。注意：JQ get_factor_values()返回的是Barra截面中性化后的残差值，非原始杠杆",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_liquidity = _build_spec(
    factor_name="liquidity",
    display_name="流动性因子",
    formula="Custom(流动性因子)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="过去252日换手率的标准差 × sqrt(252)（年化）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_style = _build_spec(
    factor_name="momentum_style",
    display_name="动量因子（风格）",
    formula="Custom(动量因子（风格）)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="过去252日（不含最近20日）的累计收益率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_residual_volatility = _build_spec(
    factor_name="residual_volatility",
    display_name="残差波动率",
    formula="Custom(残差波动率)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="个股收益率对市场收益率回归的残差标准差 × sqrt(252)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_growth_style = _build_spec(
    factor_name="growth_style",
    display_name="成长因子（风格）",
    formula="Custom(成长因子（风格）)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="JQ Barra成长风格因子，v49修正: inc_oper_yoy字段改为custom（Barra复合因子无法从单一GM字段精确还原）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_turnover_ratio_5d = _build_spec(
    factor_name="turnover_ratio_5d",
    display_name="5日平均换手率",
    formula="Custom(5日平均换手率)",
    required_fields=["close"],
    category="情绪类因子",
    description="过去5个交易日换手率的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_turnover_ratio_20d = _build_spec(
    factor_name="turnover_ratio_20d",
    display_name="20日平均换手率",
    formula="Custom(20日平均换手率)",
    required_fields=["close"],
    category="情绪类因子",
    description="过去20个交易日换手率的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_turnover_ratio_60d = _build_spec(
    factor_name="turnover_ratio_60d",
    display_name="60日平均换手率",
    formula="Custom(60日平均换手率)",
    required_fields=["close"],
    category="情绪类因子",
    description="过去60个交易日换手率的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_turnover_ratio_120d = _build_spec(
    factor_name="turnover_ratio_120d",
    display_name="120日平均换手率",
    formula="Custom(120日平均换手率)",
    required_fields=["close"],
    category="情绪类因子",
    description="过去120个交易日换手率的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_turnover_ratio_5d_to_120d = _build_spec(
    factor_name="turnover_ratio_5d_to_120d",
    display_name="5日与120日平均换手率之比",
    formula="Custom(5日与120日平均换手率之比)",
    required_fields=["close"],
    category="情绪类因子",
    description="5日平均换手率 / 120日平均换手率，反映短期交易活跃度变化",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_turnover_ratio_20d_to_120d = _build_spec(
    factor_name="turnover_ratio_20d_to_120d",
    display_name="20日与120日平均换手率之比",
    formula="Custom(20日与120日平均换手率之比)",
    required_fields=["close"],
    category="情绪类因子",
    description="20日平均换手率 / 120日平均换手率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_volume_ratio = _build_spec(
    factor_name="volume_ratio",
    display_name="量比",
    formula="Custom(量比)",
    required_fields=["close"],
    category="情绪类因子",
    description="今日成交量 / 过去5日平均成交量",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_price_volume_trend = _build_spec(
    factor_name="price_volume_trend",
    display_name="价量趋势",
    formula="Custom(价量趋势)",
    required_fields=["close"],
    category="情绪类因子",
    description="PVT = sum(成交量 × (收盘价 - 前收盘价) / 前收盘价)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_money_flow_ratio_20d = _build_spec(
    factor_name="money_flow_ratio_20d",
    display_name="20日资金流量比",
    formula="Custom(20日资金流量比)",
    required_fields=["close"],
    category="情绪类因子",
    description="过去20日主力资金净流入占成交额比例",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_volatility_20d = _build_spec(
    factor_name="volatility_20d",
    display_name="20日波动率",
    formula="Custom(20日波动率)",
    required_fields=["close"],
    category="情绪类因子",
    description="过去20个交易日收益率的标准差 × sqrt(252)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_operating_revenue_growth_rate = _build_spec(
    factor_name="operating_revenue_growth_rate",
    display_name="营业收入同比增长率",
    formula="inc_oper",
    required_fields=["inc_oper"],
    category="成长类因子",
    description="v53: gm_field=custom(非_pt API不参与prefetch), ttm_growth_v2自动路由到_compute_ttm_growth; api_name指定non-_pt API名",
    gm_field="custom",
    gm_fields="inc_oper",
)

JQ_GM_SPEC_net_profit_growth_rate = _build_spec(
    factor_name="net_profit_growth_rate",
    display_name="净利润同比增长率",
    formula="net_prof_pcom",
    required_fields=["net_prof_pcom"],
    category="成长类因子",
    description="v53: gm_field=custom(非_pt API不参与prefetch), ttm_growth_v2自动路由到_compute_ttm_growth; api_name指定non-_pt API名",
    gm_field="custom",
    gm_fields="net_prof_pcom",
)

JQ_GM_SPEC_operating_profit_growth_rate = _build_spec(
    factor_name="operating_profit_growth_rate",
    display_name="营业利润同比增长率",
    formula="oper_prof",
    required_fields=["oper_prof"],
    category="成长类因子",
    description="v53: gm_field=custom(非_pt API不参与prefetch), ttm_growth_v2自动路由到_compute_ttm_growth; api_name指定non-_pt API名",
    gm_field="custom",
    gm_fields="oper_prof",
)

JQ_GM_SPEC_total_profit_growth_rate = _build_spec(
    factor_name="total_profit_growth_rate",
    display_name="利润总额同比增长率",
    formula="ttl_prof",
    required_fields=["ttl_prof"],
    category="成长类因子",
    description="v53: gm_field=custom(非_pt API不参与prefetch), ttm_growth_v2自动路由到_compute_ttm_growth; api_name指定non-_pt API名",
    gm_field="custom",
    gm_fields="ttl_prof",
)

JQ_GM_SPEC_eps_growth_rate = _build_spec(
    factor_name="eps_growth_rate",
    display_name="EPS同比增长率",
    formula="Custom(EPS同比增长率)",
    required_fields=["close"],
    category="成长类因子",
    description="EPS同比增长率 = (本期EPS - 上期EPS) / |上期EPS| × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_revenue_growth_3y = _build_spec(
    factor_name="operating_revenue_growth_3y",
    display_name="营收3年复合增长率",
    formula="Custom(营收3年复合增长率)",
    required_fields=["close"],
    category="成长类因子",
    description="近3年营业收入复合增长率 CAGR",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_profit_growth_3y = _build_spec(
    factor_name="net_profit_growth_3y",
    display_name="净利润3年复合增长率",
    formula="Custom(净利润3年复合增长率)",
    required_fields=["close"],
    category="成长类因子",
    description="近3年净利润复合增长率 CAGR",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_gross_profit_growth_rate = _build_spec(
    factor_name="gross_profit_growth_rate",
    display_name="毛利同比增长率",
    formula="Custom(毛利同比增长率)",
    required_fields=["close"],
    category="成长类因子",
    description="毛利同比增长率",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_operate_cash_flow_growth_rate = _build_spec(
    factor_name="net_operate_cash_flow_growth_rate",
    display_name="经营活动现金流同比增长率",
    formula="net_cf_oper",
    required_fields=["net_cf_oper"],
    category="成长类因子",
    description="v53: gm_field=custom(非_pt API不参与prefetch), ttm_growth_v2自动路由到_compute_ttm_growth; api_name指定non-_pt API名",
    gm_field="custom",
    gm_fields="net_cf_oper",
)

JQ_GM_SPEC_total_assets_growth_rate = _build_spec(
    factor_name="total_assets_growth_rate",
    display_name="总资产同比增长率",
    formula="ttl_asset_yoy",
    required_fields=["ttl_asset_yoy"],
    category="成长类因子",
    description="v18: 保留deriv_pt _yoy×0.01。存量变量YoY≈TTM，_yoy准确率4/5✓",
    gm_field="stk_get_finance_deriv_pt",
    gm_fields="ttl_asset_yoy",
)

JQ_GM_SPEC_net_assets_growth_rate = _build_spec(
    factor_name="net_assets_growth_rate",
    display_name="净资产同比增长率",
    formula="Custom(净资产同比增长率)",
    required_fields=["close"],
    category="成长类因子",
    description="v18: 保留deriv_pt _yoy×0.01。存量变量YoY≈TTM，_yoy准确率1/5✓(五粮液偏差25%)，v49修正: net_asset_yoy改为custom",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_operating_revenue_qoq = _build_spec(
    factor_name="operating_revenue_qoq",
    display_name="营业收入环比增长率",
    formula="Custom(营业收入环比增长率)",
    required_fields=["close"],
    category="成长类因子",
    description="营业收入环比增长率 = (本期营收 - 上季度营收) / |上季度营收| × 100%",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_volatility_20d_risk = _build_spec(
    factor_name="volatility_20d_risk",
    display_name="20日波动率（风险）",
    formula="Custom(20日波动率（风险）)",
    required_fields=["close"],
    category="风险类因子",
    description="过去20个交易日日收益率的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_volatility_60d = _build_spec(
    factor_name="volatility_60d",
    display_name="60日波动率",
    formula="Custom(60日波动率)",
    required_fields=["close"],
    category="风险类因子",
    description="过去60个交易日日收益率的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_volatility_120d = _build_spec(
    factor_name="volatility_120d",
    display_name="120日波动率",
    formula="Custom(120日波动率)",
    required_fields=["close"],
    category="风险类因子",
    description="过去120个交易日日收益率的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_skewness_20d = _build_spec(
    factor_name="skewness_20d",
    display_name="20日收益率偏度",
    formula="Custom(20日收益率偏度)",
    required_fields=["close"],
    category="风险类因子",
    description="过去20个交易日日收益率的三阶矩（偏度）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_skewness_60d = _build_spec(
    factor_name="skewness_60d",
    display_name="60日收益率偏度",
    formula="Custom(60日收益率偏度)",
    required_fields=["close"],
    category="风险类因子",
    description="过去60个交易日日收益率的三阶矩（偏度）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_kurtosis_20d = _build_spec(
    factor_name="kurtosis_20d",
    display_name="20日收益率峰度",
    formula="Custom(20日收益率峰度)",
    required_fields=["close"],
    category="风险类因子",
    description="过去20个交易日日收益率的四阶矩（超额峰度）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_downside_volatility_20d = _build_spec(
    factor_name="downside_volatility_20d",
    display_name="20日下行波动率",
    formula="Custom(20日下行波动率)",
    required_fields=["close"],
    category="风险类因子",
    description="过去20日负收益的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_max_drawdown_20d = _build_spec(
    factor_name="max_drawdown_20d",
    display_name="20日最大回撤",
    formula="Custom(20日最大回撤)",
    required_fields=["close"],
    category="风险类因子",
    description="过去20个交易日内的最大回撤",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_beta_252d = _build_spec(
    factor_name="beta_252d",
    display_name="252日Beta",
    formula="Custom(252日Beta)",
    required_fields=["close"],
    category="风险类因子",
    description="过去252日收益率对市场收益率的回归斜率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_idiosyncratic_volatility_252d = _build_spec(
    factor_name="idiosyncratic_volatility_252d",
    display_name="252日特质波动率",
    formula="Custom(252日特质波动率)",
    required_fields=["close"],
    category="风险类因子",
    description="过去252日收益率的特质波动率（回归残差标准差）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_ma_5 = _build_spec(
    factor_name="ma_5",
    display_name="5日均线",
    formula="Custom(5日均线)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去5个交易日收盘价的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_ma_10 = _build_spec(
    factor_name="ma_10",
    display_name="10日均线",
    formula="Custom(10日均线)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去10个交易日收盘价的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_ma_20 = _build_spec(
    factor_name="ma_20",
    display_name="20日均线",
    formula="Custom(20日均线)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去20个交易日收盘价的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_ma_60 = _build_spec(
    factor_name="ma_60",
    display_name="60日均线",
    formula="Custom(60日均线)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去60个交易日收盘价的算术平均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_vwap = _build_spec(
    factor_name="vwap",
    display_name="成交量加权平均价",
    formula="Custom(成交量加权平均价)",
    required_fields=["close"],
    category="技术指标因子",
    description="VWAP = sum(成交额) / sum(成交量)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_macd = _build_spec(
    factor_name="macd",
    display_name="MACD",
    formula="Custom(MACD)",
    required_fields=["close"],
    category="技术指标因子",
    description="MACD = DIF - DEA, DIF=EMA12-EMA26, DEA=EMA(DIF,9)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_macd_signal = _build_spec(
    factor_name="macd_signal",
    display_name="MACD信号线(DEA)",
    formula="Custom(MACD信号线(DEA))",
    required_fields=["close"],
    category="技术指标因子",
    description="DEA = DIF的9日指数移动平均",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_macd_hist = _build_spec(
    factor_name="macd_hist",
    display_name="MACD柱状图",
    formula="Custom(MACD柱状图)",
    required_fields=["close"],
    category="技术指标因子",
    description="MACD柱 = (DIF - DEA) × 2",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_rsi_6 = _build_spec(
    factor_name="rsi_6",
    display_name="6日RSI",
    formula="Custom(6日RSI)",
    required_fields=["close"],
    category="技术指标因子",
    description="RSI(6) = 100 - 100/(1 + avg_gain_6d / avg_loss_6d)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_rsi_14 = _build_spec(
    factor_name="rsi_14",
    display_name="14日RSI",
    formula="Custom(14日RSI)",
    required_fields=["close"],
    category="技术指标因子",
    description="RSI(14) = 100 - 100/(1 + avg_gain_14d / avg_loss_14d)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_boll_upper = _build_spec(
    factor_name="boll_upper",
    display_name="布林上轨",
    formula="Custom(布林上轨)",
    required_fields=["close"],
    category="技术指标因子",
    description="BOLL上轨 = MA20 + 2 × 20日标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_boll_lower = _build_spec(
    factor_name="boll_lower",
    display_name="布林下轨",
    formula="Custom(布林下轨)",
    required_fields=["close"],
    category="技术指标因子",
    description="BOLL下轨 = MA20 - 2 × 20日标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_boll_width = _build_spec(
    factor_name="boll_width",
    display_name="布林带宽度",
    formula="Custom(布林带宽度)",
    required_fields=["close"],
    category="技术指标因子",
    description="BOLL宽度 = (上轨 - 下轨) / 中轨",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_atr_20 = _build_spec(
    factor_name="atr_20",
    display_name="20日ATR",
    formula="Custom(20日ATR)",
    required_fields=["close"],
    category="技术指标因子",
    description="ATR(20) = 过去20日真实波幅(Range)的移动平均",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_obv = _build_spec(
    factor_name="obv",
    display_name="OBV能量潮",
    formula="Custom(OBV能量潮)",
    required_fields=["close"],
    category="技术指标因子",
    description="OBV = 累计量，收盘价上涨加成交量，下跌减成交量",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_5d = _build_spec(
    factor_name="momentum_5d",
    display_name="5日动量",
    formula="Custom(5日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去5个交易日的累计收益率 = close[-1]/close[-6] - 1",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_10d = _build_spec(
    factor_name="momentum_10d",
    display_name="10日动量",
    formula="Custom(10日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去10个交易日的累计收益率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_20d = _build_spec(
    factor_name="momentum_20d",
    display_name="20日动量",
    formula="Custom(20日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去20个交易日的累计收益率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_60d = _build_spec(
    factor_name="momentum_60d",
    display_name="60日动量",
    formula="Custom(60日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去60个交易日的累计收益率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_120d = _build_spec(
    factor_name="momentum_120d",
    display_name="120日动量",
    formula="Custom(120日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去120个交易日的累计收益率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_252d = _build_spec(
    factor_name="momentum_252d",
    display_name="252日动量",
    formula="Custom(252日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去252个交易日的累计收益率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_reversal_5d = _build_spec(
    factor_name="reversal_5d",
    display_name="5日反转",
    formula="Custom(5日反转)",
    required_fields=["close"],
    category="动量类因子",
    description="过去5个交易日的收益率取反（短期反转因子）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_reversal_20d = _build_spec(
    factor_name="reversal_20d",
    display_name="20日反转",
    formula="Custom(20日反转)",
    required_fields=["close"],
    category="动量类因子",
    description="过去20个交易日的收益率取反（中期反转因子）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_reversal_60d = _build_spec(
    factor_name="reversal_60d",
    display_name="60日反转",
    formula="Custom(60日反转)",
    required_fields=["close"],
    category="动量类因子",
    description="过去60个交易日的收益率取反（长期反转因子）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_volume_momentum_20d = _build_spec(
    factor_name="volume_momentum_20d",
    display_name="20日成交量动量",
    formula="Custom(20日成交量动量)",
    required_fields=["close"],
    category="动量类因子",
    description="近20日均量 / 近60日均量",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_price_momentum_ratio = _build_spec(
    factor_name="price_momentum_ratio",
    display_name="价格动量比",
    formula="Custom(价格动量比)",
    required_fields=["close"],
    category="动量类因子",
    description="20日动量 / 120日动量",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_adj_momentum = _build_spec(
    factor_name="adj_momentum",
    display_name="调整动量",
    formula="Custom(调整动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去252日（不含最近20日）的累计收益率，剔除短期反转",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_beta_neutralized = _build_spec(
    factor_name="beta_neutralized",
    display_name="市值中性化Beta",
    formula="Custom(市值中性化Beta)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="Beta经市值中性化处理后的残差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_size_neutralized = _build_spec(
    factor_name="size_neutralized",
    display_name="行业中性化市值",
    formula="Custom(行业中性化市值)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="市值经行业中性化处理后的残差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_volatility_neutralized = _build_spec(
    factor_name="volatility_neutralized",
    display_name="市值中性化波动率",
    formula="Custom(市值中性化波动率)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="波动率经市值中性化处理后的残差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_liquidity_neutralized = _build_spec(
    factor_name="liquidity_neutralized",
    display_name="市值中性化流动性",
    formula="Custom(市值中性化流动性)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="流动性经市值中性化处理后的残差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_growth_neutralized = _build_spec(
    factor_name="growth_neutralized",
    display_name="市值中性化成长",
    formula="Custom(市值中性化成长)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="成长因子经市值中性化处理后的残差",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_momentum_neutralized = _build_spec(
    factor_name="momentum_neutralized",
    display_name="市值中性化动量",
    formula="Custom(市值中性化动量)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="动量经市值中性化处理后的残差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_leverage_neutralized = _build_spec(
    factor_name="leverage_neutralized",
    display_name="市值中性化杠杆",
    formula="Custom(市值中性化杠杆)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="杠杆经市值中性化处理后的残差",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_book_to_price_neutralized = _build_spec(
    factor_name="book_to_price_neutralized",
    display_name="市值中性化账面市值比",
    formula="Custom(市值中性化账面市值比)",
    required_fields=["close"],
    category="风险因子-新风格因子",
    description="BP经市值中性化处理后的残差",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_total_operating_revenue = _build_spec(
    factor_name="total_operating_revenue",
    display_name="营业总收入（最新报告期）",
    formula="inc_oper",
    required_fields=["inc_oper"],
    category="基础科目及衍生类因子",
    description="最近报告期营业总收入，直接读取利润表，v49修正: ttl_inc_oper→inc_oper",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="inc_oper",
)

JQ_GM_SPEC_operating_revenue = _build_spec(
    factor_name="operating_revenue",
    display_name="营业收入（最新报告期）",
    formula="inc_oper",
    required_fields=["inc_oper"],
    category="基础科目及衍生类因子",
    description="最近报告期营业收入，直接读取利润表",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="inc_oper",
)

JQ_GM_SPEC_net_profit = _build_spec(
    factor_name="net_profit",
    display_name="净利润（最新报告期）",
    formula="net_prof",
    required_fields=["net_prof"],
    category="基础科目及衍生类因子",
    description="最近报告期净利润，直接读取利润表",
    gm_field="stk_get_fundamentals_income_pt",
    gm_fields="net_prof",
)

JQ_GM_SPEC_total_assets = _build_spec(
    factor_name="total_assets",
    display_name="总资产（最新报告期）",
    formula="ttl_ast",
    required_fields=["ttl_ast"],
    category="基础科目及衍生类因子",
    description="最近报告期总资产，直接读取资产负债表",
    gm_field="stk_get_fundamentals_balance_pt",
    gm_fields="ttl_ast",
)

JQ_GM_SPEC_total_owner_equities = _build_spec(
    factor_name="total_owner_equities",
    display_name="股东权益合计（最新报告期）",
    formula="ttl_eqy",
    required_fields=["ttl_eqy"],
    category="基础科目及衍生类因子",
    description="最近报告期股东权益合计，直接读取资产负债表",
    gm_field="stk_get_fundamentals_balance_pt",
    gm_fields="ttl_eqy",
)

JQ_GM_SPEC_total_liability = _build_spec(
    factor_name="total_liability",
    display_name="负债合计（最新报告期）",
    formula="ttl_liab",
    required_fields=["ttl_liab"],
    category="基础科目及衍生类因子",
    description="最近报告期负债合计，直接读取资产负债表",
    gm_field="stk_get_fundamentals_balance_pt",
    gm_fields="ttl_liab",
)

JQ_GM_SPEC_net_operate_cash_flow = _build_spec(
    factor_name="net_operate_cash_flow",
    display_name="经营活动现金流量净额（最新报告期）",
    formula="net_cf_oper",
    required_fields=["net_cf_oper"],
    category="基础科目及衍生类因子",
    description="最近报告期经营活动现金流量净额，直接读取现金流量表",
    gm_field="stk_get_fundamentals_cashflow_pt",
    gm_fields="net_cf_oper",
)

JQ_GM_SPEC_MLEV = _build_spec(
    factor_name="MLEV",
    display_name="市场杠杆（MLEV）",
    formula="Custom(市场杠杆（MLEV）)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="MLEV = (总市值 + 优先股 + 长期债务) / 总市值",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_DTOA = _build_spec(
    factor_name="DTOA",
    display_name="资产负债率（DTOA）",
    formula="Custom(资产负债率（DTOA）)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="DTOA = 总负债 / 总资产（与 debt_to_assets_ratio 等价，提供 JQ 命名兼容）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_BLEV = _build_spec(
    factor_name="BLEV",
    display_name="账面杠杆（BLEV）",
    formula="Custom(账面杠杆（BLEV）)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="BLEV = (账面权益 + 长期债务) / 账面权益",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_pe_ratio_lyr = _build_spec(
    factor_name="pe_ratio_lyr",
    display_name="市盈率LYR（静态年报）",
    formula="pe_lyr",
    required_fields=["pe_lyr"],
    category="基础科目及衍生类因子",
    description="PE(LYR) = 总市值 / 上年年报净利润，与 pe_ratio 等价",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="pe_lyr",
)

JQ_GM_SPEC_pb_ratio = _build_spec(
    factor_name="pb_ratio",
    display_name="市净率（JQ命名）",
    formula="pb_mrq",
    required_fields=["pb_mrq"],
    category="基础科目及衍生类因子",
    description="PB = 总市值 / 净资产（与 pb_mrq 等价，提供 JQ 命名兼容）",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="pb_mrq",
)

JQ_GM_SPEC_ps_ratio = _build_spec(
    factor_name="ps_ratio",
    display_name="市销率TTM（JQ命名）",
    formula="ps_ttm",
    required_fields=["ps_ttm"],
    category="基础科目及衍生类因子",
    description="PS(TTM) = 总市值 / 营业收入(TTM)（与 ps_ttm 等价，提供 JQ 命名兼容）",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="ps_ttm",
)

JQ_GM_SPEC_pcf_ratio = _build_spec(
    factor_name="pcf_ratio",
    display_name="市现率TTM（JQ命名）",
    formula="pcf_ttm_oper",
    required_fields=["pcf_ttm_oper"],
    category="基础科目及衍生类因子",
    description="PCF(TTM) = 总市值 / 经营活动现金流净额(TTM)（与 pcf_ttm 等价）",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="pcf_ttm_oper",
)

JQ_GM_SPEC_ev = _build_spec(
    factor_name="ev",
    display_name="企业价值EV",
    formula="Custom(企业价值EV)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="EV = 总市值 + 总债务 - 现金及现金等价物",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_ev2_to_ebitda = _build_spec(
    factor_name="ev2_to_ebitda",
    display_name="EV/EBITDA",
    formula="Custom(EV/EBITDA)",
    required_fields=["close"],
    category="基础科目及衍生类因子",
    description="EV/EBITDA = 企业价值 / EBITDA（v49修正: valuation_pt无ev_ebitda字段，改用custom自算）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_dividend_ratio = _build_spec(
    factor_name="dividend_ratio",
    display_name="股息率",
    formula="dy_ttm",
    required_fields=["dy_ttm"],
    category="基础科目及衍生类因子",
    description="股息率 = 每股股息 / 收盘价（GM字段dy_ttm=TTM股息率%）",
    gm_field="stk_get_daily_valuation_pt",
    gm_fields="dy_ttm",
)

JQ_GM_SPEC_roe = _build_spec(
    factor_name="roe",
    display_name="净资产收益率ROE（最新报告期）",
    formula="roe_weight_avg",
    required_fields=["roe_weight_avg"],
    category="质量类因子",
    description="ROE = 净利润 / 净资产 × 100，最新报告期数据。v49修正: deriv_pt无bare roe字段，改用prime_pt的roe_weight_avg",
    gm_field="stk_get_finance_prime_pt",
    gm_fields="roe_weight_avg",
)

JQ_GM_SPEC_roa = _build_spec(
    factor_name="roa",
    display_name="总资产净利率ROA（最新报告期）",
    formula="jroa",
    required_fields=["jroa"],
    category="质量类因子",
    description="ROA = 净利润 / 总资产 × 100，最新报告期数据；v16修正：GM roa=总资产报酬率(含利息)，jroa=总资产净利率(仅净利润)，JQ roa 对应 jroa",
    gm_field="stk_get_finance_deriv_pt",
    gm_fields="jroa",
)

JQ_GM_SPEC_gross_profit_margin = _build_spec(
    factor_name="gross_profit_margin",
    display_name="销售毛利率",
    formula="Custom(销售毛利率)",
    required_fields=["close"],
    category="质量类因子",
    description="毛利率 = (营业收入 - 营业成本) / 营业收入 × 100",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_OperatingCycle = _build_spec(
    factor_name="OperatingCycle",
    display_name="营业周期（天）",
    formula="Custom(营业周期（天）)",
    required_fields=["close"],
    category="质量类因子",
    description="营业周期 = 存货周转天数 + 应收账款周转天数",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_inv_turn_ratio = _build_spec(
    factor_name="inv_turn_ratio",
    display_name="存货周转率（JQ命名）",
    formula="Custom(存货周转率（JQ命名）)",
    required_fields=["close"],
    category="质量类因子",
    description="存货周转率 = 营业成本 / 平均存货（与 inventory_turnover 等价）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_ar_turn_ratio = _build_spec(
    factor_name="ar_turn_ratio",
    display_name="应收账款周转率（JQ命名）",
    formula="Custom(应收账款周转率（JQ命名）)",
    required_fields=["close"],
    category="质量类因子",
    description="应收账款周转率 = 营业收入 / 平均应收账款（与 accounts_receivable_turnover 等价）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_assets_turn_ratio = _build_spec(
    factor_name="assets_turn_ratio",
    display_name="总资产周转率（JQ命名）",
    formula="Custom(总资产周转率（JQ命名）)",
    required_fields=["close"],
    category="质量类因子",
    description="总资产周转率 = 营业收入 / 平均总资产（与 total_asset_turnover 等价）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_ocf_to_operating_profit = _build_spec(
    factor_name="ocf_to_operating_profit",
    display_name="经营现金流/经营利润",
    formula="Custom(经营现金流/经营利润)",
    required_fields=["close"],
    category="质量类因子",
    description="经营活动现金流净额 / 营业利润，反映利润质量",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_inc_return = _build_spec(
    factor_name="inc_return",
    display_name="净资产收益率（加权平均）",
    formula="roe_weight_avg",
    required_fields=["roe_weight_avg"],
    category="质量类因子",
    description="加权平均净资产收益率，反映股东权益回报水平",
    gm_field="stk_get_finance_prime_pt",
    gm_fields="roe_weight_avg",
)

JQ_GM_SPEC_eps = _build_spec(
    factor_name="eps",
    display_name="每股收益EPS（JQ命名）",
    formula="eps_basic",
    required_fields=["eps_basic"],
    category="每股指标因子",
    description="EPS = 归母净利润 / 总股本（与 eps_ttm 近似，使用最新报告期数据）",
    gm_field="stk_get_finance_prime_pt",
    gm_fields="eps_basic",
)

JQ_GM_SPEC_basic_eps = _build_spec(
    factor_name="basic_eps",
    display_name="基本每股收益",
    formula="eps_basic",
    required_fields=["eps_basic"],
    category="每股指标因子",
    description="基本每股收益，直接读取财务报表（利润表）",
    gm_field="stk_get_finance_prime_pt",
    gm_fields="eps_basic",
)

JQ_GM_SPEC_diluted_eps = _build_spec(
    factor_name="diluted_eps",
    display_name="稀释每股收益",
    formula="eps_dil",
    required_fields=["eps_dil"],
    category="每股指标因子",
    description="稀释每股收益，考虑可转债/期权等稀释效应",
    gm_field="stk_get_finance_prime_pt",
    gm_fields="eps_dil",
)

JQ_GM_SPEC_ocfps = _build_spec(
    factor_name="ocfps",
    display_name="每股经营现金流",
    formula="Custom(每股经营现金流)",
    required_fields=["close"],
    category="每股指标因子",
    description="OCFPS = 经营活动现金流量净额 / 总股本",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_revenue_ps = _build_spec(
    factor_name="revenue_ps",
    display_name="每股营业收入（JQ命名）",
    formula="Custom(每股营业收入（JQ命名）)",
    required_fields=["close"],
    category="每股指标因子",
    description="每股营业收入 = 营业总收入 / 总股本（与 operating_revenue_per_share 近似）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_np_parent_company_owners_growth_rate = _build_spec(
    factor_name="np_parent_company_owners_growth_rate",
    display_name="归母净利润同比增长率",
    formula="net_prof_pcom",
    required_fields=["net_prof_pcom"],
    category="成长类因子",
    description="v53: gm_field=custom(非_pt API不参与prefetch), ttm_growth_v2自动路由到_compute_ttm_growth; api_name指定non-_pt API名",
    gm_field="custom",
    gm_fields="net_prof_pcom",
)

JQ_GM_SPEC_total_asset_growth_rate = _build_spec(
    factor_name="total_asset_growth_rate",
    display_name="总资产增长率（JQ命名）",
    formula="Custom(总资产增长率（JQ命名）)",
    required_fields=["close"],
    category="成长类因子",
    description="总资产同比增长率（与 total_assets_growth_rate 等价）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_asset_growth_rate = _build_spec(
    factor_name="net_asset_growth_rate",
    display_name="净资产增长率（JQ命名）",
    formula="Custom(净资产增长率（JQ命名）)",
    required_fields=["close"],
    category="成长类因子",
    description="净资产同比增长率（与 net_assets_growth_rate 等价）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_net_operate_cashflow_growth_rate = _build_spec(
    factor_name="net_operate_cashflow_growth_rate",
    display_name="经营现金流增长率（JQ命名）",
    formula="Custom(经营现金流增长率（JQ命名）)",
    required_fields=["close"],
    category="成长类因子",
    description="经营活动现金流净额同比增长率（与 net_operate_cash_flow_growth_rate 等价）",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_financing_cash_growth_rate = _build_spec(
    factor_name="financing_cash_growth_rate",
    display_name="筹资现金流增长率",
    formula="Custom(筹资现金流增长率)",
    required_fields=["close"],
    category="成长类因子",
    description="筹资活动现金流净额同比增长率",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_sales_growth = _build_spec(
    factor_name="sales_growth",
    display_name="5年营收增长率（回归斜率法）",
    formula="Custom(5年营收增长率（回归斜率法）)",
    required_fields=["close"],
    category="成长类因子",
    description="近5年每股营收的线性回归斜率 / 均值，反映长期增长趋势",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_PEG = _build_spec(
    factor_name="PEG",
    display_name="PEG（市盈率相对增长比率）",
    formula="Custom(PEG（市盈率相对增长比率）)",
    required_fields=["close"],
    category="成长类因子",
    description="PEG = PE(TTM) / 净利润同比增长率，综合估值与成长",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_VOL5 = _build_spec(
    factor_name="VOL5",
    display_name="5日平均换手率（JQ命名）",
    formula="Custom(5日平均换手率（JQ命名）)",
    required_fields=["close"],
    category="情绪类因子",
    description="近5日换手率均值，与 turnover_ratio_5d 等价，保留 JQ 命名",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_VOL10 = _build_spec(
    factor_name="VOL10",
    display_name="10日平均换手率",
    formula="Custom(10日平均换手率)",
    required_fields=["close"],
    category="情绪类因子",
    description="近10日换手率均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_VEMA5 = _build_spec(
    factor_name="VEMA5",
    display_name="5日成交量EMA",
    formula="Custom(5日成交量EMA)",
    required_fields=["close"],
    category="情绪类因子",
    description="成交量的5日指数移动平均",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_VEMA10 = _build_spec(
    factor_name="VEMA10",
    display_name="10日成交量EMA",
    formula="Custom(10日成交量EMA)",
    required_fields=["close"],
    category="情绪类因子",
    description="成交量的10日指数移动平均",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_VEMA20 = _build_spec(
    factor_name="VEMA20",
    display_name="20日成交量EMA",
    formula="Custom(20日成交量EMA)",
    required_fields=["close"],
    category="情绪类因子",
    description="成交量的20日指数移动平均",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_DAVOL5 = _build_spec(
    factor_name="DAVOL5",
    display_name="5日成交额均量比",
    formula="Custom(5日成交额均量比)",
    required_fields=["close"],
    category="情绪类因子",
    description="近5日成交额 / 近5日前5日成交额，反映短期成交量变化",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_DAVOL10 = _build_spec(
    factor_name="DAVOL10",
    display_name="10日成交额均量比",
    formula="Custom(10日成交额均量比)",
    required_fields=["close"],
    category="情绪类因子",
    description="近10日成交额 / 前10日成交额",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_REVS5 = _build_spec(
    factor_name="REVS5",
    display_name="5日动量（JQ命名）",
    formula="Custom(5日动量（JQ命名）)",
    required_fields=["close"],
    category="动量类因子",
    description="过去5日收益率之和（与 momentum_5d 等价）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_REVS10 = _build_spec(
    factor_name="REVS10",
    display_name="10日动量",
    formula="Custom(10日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去10日收益率之和",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_REVS20 = _build_spec(
    factor_name="REVS20",
    display_name="20日动量",
    formula="Custom(20日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去20日收益率之和",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_REVS60 = _build_spec(
    factor_name="REVS60",
    display_name="60日动量",
    formula="Custom(60日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去60日收益率之和",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_REVS120 = _build_spec(
    factor_name="REVS120",
    display_name="120日动量",
    formula="Custom(120日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去120日收益率之和",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_REVS250 = _build_spec(
    factor_name="REVS250",
    display_name="250日动量",
    formula="Custom(250日动量)",
    required_fields=["close"],
    category="动量类因子",
    description="过去250日收益率之和",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_KDJ_K = _build_spec(
    factor_name="KDJ_K",
    display_name="KDJ K值",
    formula="Custom(KDJ K值)",
    required_fields=["close"],
    category="动量类因子",
    description="K = RSV的3日均值；RSV = (close - lowest_low_9d) / (highest_high_9d - lowest_low_9d) × 100",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_KDJ_D = _build_spec(
    factor_name="KDJ_D",
    display_name="KDJ D值",
    formula="Custom(KDJ D值)",
    required_fields=["close"],
    category="动量类因子",
    description="D = K值的3日均值",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_MA5 = _build_spec(
    factor_name="MA5",
    display_name="5日均线（JQ命名）",
    formula="Custom(5日均线（JQ命名）)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去5日收盘价算术平均（与 ma_5 等价）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_MA10 = _build_spec(
    factor_name="MA10",
    display_name="10日均线（JQ命名）",
    formula="Custom(10日均线（JQ命名）)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去10日收盘价算术平均（与 ma_10 等价）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_MA20 = _build_spec(
    factor_name="MA20",
    display_name="20日均线（JQ命名）",
    formula="Custom(20日均线（JQ命名）)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去20日收盘价算术平均（与 ma_20 等价）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_MA60 = _build_spec(
    factor_name="MA60",
    display_name="60日均线（JQ命名）",
    formula="Custom(60日均线（JQ命名）)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去60日收盘价算术平均（与 ma_60 等价）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_EMA5 = _build_spec(
    factor_name="EMA5",
    display_name="5日指数移动均线",
    formula="Custom(5日指数移动均线)",
    required_fields=["close"],
    category="技术指标因子",
    description="收盘价的5日EMA",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_EMA10 = _build_spec(
    factor_name="EMA10",
    display_name="10日指数移动均线",
    formula="Custom(10日指数移动均线)",
    required_fields=["close"],
    category="技术指标因子",
    description="收盘价的10日EMA",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_EMA20 = _build_spec(
    factor_name="EMA20",
    display_name="20日指数移动均线",
    formula="Custom(20日指数移动均线)",
    required_fields=["close"],
    category="技术指标因子",
    description="收盘价的20日EMA",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_Std5 = _build_spec(
    factor_name="Std5",
    display_name="5日收益率标准差",
    formula="Custom(5日收益率标准差)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去5日日收益率的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_Std10 = _build_spec(
    factor_name="Std10",
    display_name="10日收益率标准差",
    formula="Custom(10日收益率标准差)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去10日日收益率的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_Std20 = _build_spec(
    factor_name="Std20",
    display_name="20日收益率标准差",
    formula="Custom(20日收益率标准差)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去20日日收益率的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_Std60 = _build_spec(
    factor_name="Std60",
    display_name="60日收益率标准差",
    formula="Custom(60日收益率标准差)",
    required_fields=["close"],
    category="技术指标因子",
    description="过去60日日收益率的标准差",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_BIAS5 = _build_spec(
    factor_name="BIAS5",
    display_name="5日乖离率",
    formula="Custom(5日乖离率)",
    required_fields=["close"],
    category="技术指标因子",
    description="BIAS5 = (close - MA5) / MA5 × 100",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_BIAS10 = _build_spec(
    factor_name="BIAS10",
    display_name="10日乖离率",
    formula="Custom(10日乖离率)",
    required_fields=["close"],
    category="技术指标因子",
    description="BIAS10 = (close - MA10) / MA10 × 100",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_BIAS20 = _build_spec(
    factor_name="BIAS20",
    display_name="20日乖离率",
    formula="Custom(20日乖离率)",
    required_fields=["close"],
    category="技术指标因子",
    description="BIAS20 = (close - MA20) / MA20 × 100",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_RSI = _build_spec(
    factor_name="RSI",
    display_name="相对强弱指标（14日）",
    formula="Custom(相对强弱指标（14日）)",
    required_fields=["close"],
    category="技术指标因子",
    description="RSI(14) = 100 - 100/(1 + 近14日涨幅均值/跌幅均值)（与 rsi_14 等价）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_ATR14 = _build_spec(
    factor_name="ATR14",
    display_name="14日真实波幅均值",
    formula="Custom(14日真实波幅均值)",
    required_fields=["close"],
    category="技术指标因子",
    description="ATR(14) = TR.rolling(14).mean()，TR = max(H-L, |H-C_prev|, |L-C_prev|)",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_MACD = _build_spec(
    factor_name="MACD",
    display_name="MACD（JQ命名）",
    formula="Custom(MACD（JQ命名）)",
    required_fields=["close"],
    category="技术指标因子",
    description="MACD = DIF - DEA，DIF = EMA12 - EMA26，DEA = EMA(DIF, 9)（与 macd 等价）",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_alpha = _build_spec(
    factor_name="alpha",
    display_name="Alpha（超额收益截距）",
    formula="Custom(Alpha（超额收益截距）)",
    required_fields=["close"],
    category="风险类因子",
    description="个股收益率对市场收益率回归的截距项，反映特异收益",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_sharpe_ratio = _build_spec(
    factor_name="sharpe_ratio",
    display_name="夏普比率",
    formula="Custom(夏普比率)",
    required_fields=["close"],
    category="风险类因子",
    description="夏普比率 = (年化收益 - 无风险利率) / 年化波动率",
    gm_field="custom_price",
    gm_fields="?",
)

JQ_GM_SPEC_growth = _build_spec(
    factor_name="growth",
    display_name="成长因子（Barra）",
    formula="Custom(成长因子（Barra）)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="近期盈利增速综合得分，与 growth_style 等价，提供 JQ 命名兼容。v49修正: inc_oper_yoy在deriv_pt中无效(v33确认)，改为custom",
    gm_field="custom",
    gm_fields="?",
)

JQ_GM_SPEC_momentum = _build_spec(
    factor_name="momentum",
    display_name="动量因子（Barra）",
    formula="Custom(动量因子（Barra）)",
    required_fields=["close"],
    category="风险因子-风格因子",
    description="过去12月（扣除最近1月）超额收益，与 adj_momentum 等价",
    gm_field="custom_price",
    gm_fields="?",
)

def jq_gm_specs() -> list[FactorResearchSpec]:
    """Return all 215 implemented jq_gm FactorResearchSpec declarations."""
    return [
        JQ_GM_SPEC_market_cap,
        JQ_GM_SPEC_circulating_market_cap,
        JQ_GM_SPEC_pe_ttm,
        JQ_GM_SPEC_pe_ratio,
        JQ_GM_SPEC_pb_mrq,
        JQ_GM_SPEC_ps_ttm,
        JQ_GM_SPEC_pcf_ttm,
        JQ_GM_SPEC_turnover_ratio,
        JQ_GM_SPEC_total_operating_revenue_ttm,
        JQ_GM_SPEC_operating_profit_ttm,
        JQ_GM_SPEC_net_profit_ttm,
        JQ_GM_SPEC_operating_revenue_ttm,
        JQ_GM_SPEC_net_operate_cash_flow_ttm,
        JQ_GM_SPEC_net_invest_cash_flow_ttm,
        JQ_GM_SPEC_net_finance_cash_flow_ttm,
        JQ_GM_SPEC_total_profit_ttm,
        JQ_GM_SPEC_operating_cost_ttm,
        JQ_GM_SPEC_total_operating_cost_ttm,
        JQ_GM_SPEC_np_parent_company_owners_ttm,
        JQ_GM_SPEC_sale_expense_ttm,
        JQ_GM_SPEC_administration_expense_ttm,
        JQ_GM_SPEC_financial_expense_ttm,
        JQ_GM_SPEC_gross_profit_ttm,
        JQ_GM_SPEC_asset_impairment_loss_ttm,
        JQ_GM_SPEC_value_change_profit_ttm,
        JQ_GM_SPEC_non_operating_net_profit_ttm,
        JQ_GM_SPEC_EBIT,
        JQ_GM_SPEC_EBITDA,
        JQ_GM_SPEC_net_working_capital,
        JQ_GM_SPEC_retained_earnings,
        JQ_GM_SPEC_financial_assets,
        JQ_GM_SPEC_operating_assets,
        JQ_GM_SPEC_financial_liability,
        JQ_GM_SPEC_operating_liability,
        JQ_GM_SPEC_net_debt,
        JQ_GM_SPEC_net_interest_expense,
        JQ_GM_SPEC_goods_sale_and_service_render_cash_ttm,
        JQ_GM_SPEC_sales_to_price_ratio,
        JQ_GM_SPEC_cash_flow_to_price_ratio,
        JQ_GM_SPEC_roe_ttm,
        JQ_GM_SPEC_roa_ttm,
        JQ_GM_SPEC_gross_income_ratio,
        JQ_GM_SPEC_net_profit_margin,
        JQ_GM_SPEC_operating_profit_margin,
        JQ_GM_SPEC_total_asset_turnover,
        JQ_GM_SPEC_accounts_receivable_turnover,
        JQ_GM_SPEC_inventory_turnover,
        JQ_GM_SPEC_operating_cycle,
        JQ_GM_SPEC_cash_ratio,
        JQ_GM_SPEC_current_ratio,
        JQ_GM_SPEC_quick_ratio,
        JQ_GM_SPEC_debt_to_assets_ratio,
        JQ_GM_SPEC_tangible_assets_to_debt_ratio,
        JQ_GM_SPEC_operating_net_income,
        JQ_GM_SPEC_eps_ttm,
        JQ_GM_SPEC_bps,
        JQ_GM_SPEC_operating_revenue_per_share,
        JQ_GM_SPEC_operating_profit_per_share,
        JQ_GM_SPEC_cash_flow_per_share,
        JQ_GM_SPEC_capital_reserve_per_share,
        JQ_GM_SPEC_surplus_reserve_per_share,
        JQ_GM_SPEC_retained_earnings_per_share,
        JQ_GM_SPEC_operating_revenue_growth_ttm,
        JQ_GM_SPEC_net_profit_growth_per_share,
        JQ_GM_SPEC_beta,
        JQ_GM_SPEC_size,
        JQ_GM_SPEC_non_linear_size,
        JQ_GM_SPEC_book_to_price_ratio,
        JQ_GM_SPEC_earnings_yield,
        JQ_GM_SPEC_leverage,
        JQ_GM_SPEC_liquidity,
        JQ_GM_SPEC_momentum_style,
        JQ_GM_SPEC_residual_volatility,
        JQ_GM_SPEC_growth_style,
        JQ_GM_SPEC_turnover_ratio_5d,
        JQ_GM_SPEC_turnover_ratio_20d,
        JQ_GM_SPEC_turnover_ratio_60d,
        JQ_GM_SPEC_turnover_ratio_120d,
        JQ_GM_SPEC_turnover_ratio_5d_to_120d,
        JQ_GM_SPEC_turnover_ratio_20d_to_120d,
        JQ_GM_SPEC_volume_ratio,
        JQ_GM_SPEC_price_volume_trend,
        JQ_GM_SPEC_money_flow_ratio_20d,
        JQ_GM_SPEC_volatility_20d,
        JQ_GM_SPEC_operating_revenue_growth_rate,
        JQ_GM_SPEC_net_profit_growth_rate,
        JQ_GM_SPEC_operating_profit_growth_rate,
        JQ_GM_SPEC_total_profit_growth_rate,
        JQ_GM_SPEC_eps_growth_rate,
        JQ_GM_SPEC_operating_revenue_growth_3y,
        JQ_GM_SPEC_net_profit_growth_3y,
        JQ_GM_SPEC_gross_profit_growth_rate,
        JQ_GM_SPEC_net_operate_cash_flow_growth_rate,
        JQ_GM_SPEC_total_assets_growth_rate,
        JQ_GM_SPEC_net_assets_growth_rate,
        JQ_GM_SPEC_operating_revenue_qoq,
        JQ_GM_SPEC_volatility_20d_risk,
        JQ_GM_SPEC_volatility_60d,
        JQ_GM_SPEC_volatility_120d,
        JQ_GM_SPEC_skewness_20d,
        JQ_GM_SPEC_skewness_60d,
        JQ_GM_SPEC_kurtosis_20d,
        JQ_GM_SPEC_downside_volatility_20d,
        JQ_GM_SPEC_max_drawdown_20d,
        JQ_GM_SPEC_beta_252d,
        JQ_GM_SPEC_idiosyncratic_volatility_252d,
        JQ_GM_SPEC_ma_5,
        JQ_GM_SPEC_ma_10,
        JQ_GM_SPEC_ma_20,
        JQ_GM_SPEC_ma_60,
        JQ_GM_SPEC_vwap,
        JQ_GM_SPEC_macd,
        JQ_GM_SPEC_macd_signal,
        JQ_GM_SPEC_macd_hist,
        JQ_GM_SPEC_rsi_6,
        JQ_GM_SPEC_rsi_14,
        JQ_GM_SPEC_boll_upper,
        JQ_GM_SPEC_boll_lower,
        JQ_GM_SPEC_boll_width,
        JQ_GM_SPEC_atr_20,
        JQ_GM_SPEC_obv,
        JQ_GM_SPEC_momentum_5d,
        JQ_GM_SPEC_momentum_10d,
        JQ_GM_SPEC_momentum_20d,
        JQ_GM_SPEC_momentum_60d,
        JQ_GM_SPEC_momentum_120d,
        JQ_GM_SPEC_momentum_252d,
        JQ_GM_SPEC_reversal_5d,
        JQ_GM_SPEC_reversal_20d,
        JQ_GM_SPEC_reversal_60d,
        JQ_GM_SPEC_volume_momentum_20d,
        JQ_GM_SPEC_price_momentum_ratio,
        JQ_GM_SPEC_adj_momentum,
        JQ_GM_SPEC_beta_neutralized,
        JQ_GM_SPEC_size_neutralized,
        JQ_GM_SPEC_volatility_neutralized,
        JQ_GM_SPEC_liquidity_neutralized,
        JQ_GM_SPEC_growth_neutralized,
        JQ_GM_SPEC_momentum_neutralized,
        JQ_GM_SPEC_leverage_neutralized,
        JQ_GM_SPEC_book_to_price_neutralized,
        JQ_GM_SPEC_total_operating_revenue,
        JQ_GM_SPEC_operating_revenue,
        JQ_GM_SPEC_net_profit,
        JQ_GM_SPEC_total_assets,
        JQ_GM_SPEC_total_owner_equities,
        JQ_GM_SPEC_total_liability,
        JQ_GM_SPEC_net_operate_cash_flow,
        JQ_GM_SPEC_MLEV,
        JQ_GM_SPEC_DTOA,
        JQ_GM_SPEC_BLEV,
        JQ_GM_SPEC_pe_ratio_lyr,
        JQ_GM_SPEC_pb_ratio,
        JQ_GM_SPEC_ps_ratio,
        JQ_GM_SPEC_pcf_ratio,
        JQ_GM_SPEC_ev,
        JQ_GM_SPEC_ev2_to_ebitda,
        JQ_GM_SPEC_dividend_ratio,
        JQ_GM_SPEC_roe,
        JQ_GM_SPEC_roa,
        JQ_GM_SPEC_gross_profit_margin,
        JQ_GM_SPEC_OperatingCycle,
        JQ_GM_SPEC_inv_turn_ratio,
        JQ_GM_SPEC_ar_turn_ratio,
        JQ_GM_SPEC_assets_turn_ratio,
        JQ_GM_SPEC_ocf_to_operating_profit,
        JQ_GM_SPEC_inc_return,
        JQ_GM_SPEC_eps,
        JQ_GM_SPEC_basic_eps,
        JQ_GM_SPEC_diluted_eps,
        JQ_GM_SPEC_ocfps,
        JQ_GM_SPEC_revenue_ps,
        JQ_GM_SPEC_np_parent_company_owners_growth_rate,
        JQ_GM_SPEC_total_asset_growth_rate,
        JQ_GM_SPEC_net_asset_growth_rate,
        JQ_GM_SPEC_net_operate_cashflow_growth_rate,
        JQ_GM_SPEC_financing_cash_growth_rate,
        JQ_GM_SPEC_sales_growth,
        JQ_GM_SPEC_PEG,
        JQ_GM_SPEC_VOL5,
        JQ_GM_SPEC_VOL10,
        JQ_GM_SPEC_VEMA5,
        JQ_GM_SPEC_VEMA10,
        JQ_GM_SPEC_VEMA20,
        JQ_GM_SPEC_DAVOL5,
        JQ_GM_SPEC_DAVOL10,
        JQ_GM_SPEC_REVS5,
        JQ_GM_SPEC_REVS10,
        JQ_GM_SPEC_REVS20,
        JQ_GM_SPEC_REVS60,
        JQ_GM_SPEC_REVS120,
        JQ_GM_SPEC_REVS250,
        JQ_GM_SPEC_KDJ_K,
        JQ_GM_SPEC_KDJ_D,
        JQ_GM_SPEC_MA5,
        JQ_GM_SPEC_MA10,
        JQ_GM_SPEC_MA20,
        JQ_GM_SPEC_MA60,
        JQ_GM_SPEC_EMA5,
        JQ_GM_SPEC_EMA10,
        JQ_GM_SPEC_EMA20,
        JQ_GM_SPEC_Std5,
        JQ_GM_SPEC_Std10,
        JQ_GM_SPEC_Std20,
        JQ_GM_SPEC_Std60,
        JQ_GM_SPEC_BIAS5,
        JQ_GM_SPEC_BIAS10,
        JQ_GM_SPEC_BIAS20,
        JQ_GM_SPEC_RSI,
        JQ_GM_SPEC_ATR14,
        JQ_GM_SPEC_MACD,
        JQ_GM_SPEC_alpha,
        JQ_GM_SPEC_sharpe_ratio,
        JQ_GM_SPEC_growth,
        JQ_GM_SPEC_momentum,
    ] + _dynamic_specs


# ── Convenience set for CLI / service lookups ────────────────────

# Runtime registry for dynamically-added specs (e.g. from AI mining bridge)
_dynamic_specs: list[FactorResearchSpec] = []


def register_spec(spec: FactorResearchSpec) -> None:
    """Register a new factor spec at runtime (e.g. from AI mining bridge)."""
    existing = {s.factor_name for s in jq_gm_specs()}
    if spec.factor_name not in existing:
        _dynamic_specs.append(spec)


JQ_GM_IMPLEMENTED_FACTORS = [
    spec.factor_name for spec in jq_gm_specs()
]
