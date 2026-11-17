// 本次修改点：
// 1. 默认落地页切换为因子监控，配合左侧导航新顺序。
// 2. 子库筛选暂时隐藏，保留 state.library 和渲染函数方便后续恢复。
// 3. 分类筛选改为券商研报式大类/子类口径，并作为因子库/监控后续共用过滤基础。
// 4. 新增因子库准入视觉状态、研究口径选择器、策略草稿生成，以及监控页分类/方向筛选。
// 5. 新增独立策略构建页、成品策略模板契约、策略看板删除模式与股票池省略显示。
const urlParams = new URLSearchParams(window.location.search);
const hasWindowConfig = (key) => Object.prototype.hasOwnProperty.call(window, key);
const configuredApiHost = (
  urlParams.get("api") ||
  (hasWindowConfig("FACTOR_LAB_API_HOST")
    ? window.FACTOR_LAB_API_HOST
    : window.localStorage.getItem("FACTOR_LAB_API_HOST")) ||
  ""
).replace(/\/+$/, "");
if (urlParams.get("api")) {
  window.localStorage.setItem("FACTOR_LAB_API_HOST", configuredApiHost);
}
const configuredQuantDeskHost = (
  urlParams.get("quantDesk") ||
  (hasWindowConfig("FACTOR_LAB_QUANT_DESK_HOST")
    ? window.FACTOR_LAB_QUANT_DESK_HOST
    : window.localStorage.getItem("FACTOR_LAB_QUANT_DESK_HOST")) ||
  ""
).replace(/\/+$/, "");
if (urlParams.get("quantDesk")) {
  window.localStorage.setItem("FACTOR_LAB_QUANT_DESK_HOST", configuredQuantDeskHost);
}
const CLOUD_DEMO_MODE =
  !configuredApiHost &&
  (window.location.hostname.endsWith("github.io") || urlParams.has("demo"));
// When no API host is configured, the app is served next to its own API, so same-origin
// is the correct default. The previous fallback was a hardcoded http://127.0.0.1:8012,
// which works in local development and fails for a real deployment: a client opening
// https://<server>/factor-lab/ would have been told to fetch the API from *their own*
// machine's port 8012. The explicit override in config.local.js still wins.
const API_HOST = configuredApiHost
  ? configuredApiHost
  : CLOUD_DEMO_MODE
    ? ""
    : window.location.protocol.startsWith("http")
      ? window.location.origin
      : "http://127.0.0.1:8012";
const API_BASE = CLOUD_DEMO_MODE ? "" : `${API_HOST}/api/agents/factor-lab`;
// The Quant Desk is a separate service rendered in an iframe, so it only exists when a
// host is configured. The previous fallback was a hardcoded http://127.0.0.1:8013, which
// told a *client's* browser to fetch a service on their own machine: the section could
// never work for anyone but the developer, and it advertised an internal port. Empty
// means "this deployment has none", and the section is hidden rather than opening an
// empty view over a refused connection.
const QUANT_DESK_HOST = configuredQuantDeskHost || "";
const QUANT_DESK_ENABLED = QUANT_DESK_HOST.length > 0;
const QUANT_DESK_BASE = QUANT_DESK_ENABLED ? `${QUANT_DESK_HOST}/quant-desk/` : "";
const QUANT_DESK_HEALTH = QUANT_DESK_ENABLED ? `${QUANT_DESK_HOST}/healthz` : "";
const QUANT_DESK_DEFAULT_PATH = "";
const SUPABASE_URL = (
  window.FACTOR_LAB_SUPABASE_URL ||
  urlParams.get("supabaseUrl") ||
  window.localStorage.getItem("FACTOR_LAB_SUPABASE_URL") ||
  ""
).replace(/\/+$/, "");
const SUPABASE_ANON_KEY =
  window.FACTOR_LAB_SUPABASE_ANON_KEY ||
  urlParams.get("supabaseAnonKey") ||
  window.localStorage.getItem("FACTOR_LAB_SUPABASE_ANON_KEY") ||
  "";
const SUPABASE_FACTOR_TABLE =
  urlParams.get("supabaseTable") ||
  (hasWindowConfig("FACTOR_LAB_SUPABASE_FACTOR_TABLE")
    ? window.FACTOR_LAB_SUPABASE_FACTOR_TABLE
    : window.localStorage.getItem("FACTOR_LAB_SUPABASE_FACTOR_TABLE")) ||
  "";
const SUPABASE_TRUTH_SUMMARY_TABLE =
  urlParams.get("truthSummaryTable") ||
  (hasWindowConfig("FACTOR_LAB_SUPABASE_TRUTH_SUMMARY_TABLE")
    ? window.FACTOR_LAB_SUPABASE_TRUTH_SUMMARY_TABLE
    : window.localStorage.getItem("FACTOR_LAB_SUPABASE_TRUTH_SUMMARY_TABLE")) ||
  "factor_truth_values_summary";
const SUPABASE_ANALYSIS_TABLE =
  urlParams.get("analysisTable") ||
  (hasWindowConfig("FACTOR_LAB_SUPABASE_ANALYSIS_TABLE")
    ? window.FACTOR_LAB_SUPABASE_ANALYSIS_TABLE
    : window.localStorage.getItem("FACTOR_LAB_SUPABASE_ANALYSIS_TABLE")) ||
  "factor_analysis_results";
const SUPABASE_ANALYSIS_IC_TABLE =
  urlParams.get("analysisIcTable") ||
  (hasWindowConfig("FACTOR_LAB_SUPABASE_ANALYSIS_IC_TABLE")
    ? window.FACTOR_LAB_SUPABASE_ANALYSIS_IC_TABLE
    : window.localStorage.getItem("FACTOR_LAB_SUPABASE_ANALYSIS_IC_TABLE")) ||
  "factor_analysis_ic_series";
const SUPABASE_ANALYSIS_GROUP_TABLE =
  urlParams.get("analysisGroupTable") ||
  (hasWindowConfig("FACTOR_LAB_SUPABASE_ANALYSIS_GROUP_TABLE")
    ? window.FACTOR_LAB_SUPABASE_ANALYSIS_GROUP_TABLE
    : window.localStorage.getItem("FACTOR_LAB_SUPABASE_ANALYSIS_GROUP_TABLE")) ||
  "factor_analysis_group_series";
const USE_SUPABASE_DASHBOARD = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY && !configuredApiHost);
const ACCESS_PASSWORD =
  window.FACTOR_LAB_ACCESS_PASSWORD ||
  urlParams.get("accessPassword") ||
  window.localStorage.getItem("FACTOR_LAB_ACCESS_PASSWORD") ||
  "factorlab2026";
const ACCESS_SESSION_KEY = "FACTOR_LAB_AUTH_OK";
//: The signed session token returned by the API. Kept in sessionStorage so it dies
//: with the tab, and sent as `Authorization: Bearer` on every data request.
const AUTH_TOKEN_KEY = "FACTOR_LAB_SESSION_TOKEN";
const THEME_STORAGE_KEY = "FACTOR_LAB_THEME";
if (urlParams.get("supabaseUrl")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_URL", SUPABASE_URL);
}
if (urlParams.get("supabaseAnonKey")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_ANON_KEY", SUPABASE_ANON_KEY);
}
if (urlParams.get("supabaseTable")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_FACTOR_TABLE", SUPABASE_FACTOR_TABLE);
}
if (urlParams.get("truthSummaryTable")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_TRUTH_SUMMARY_TABLE", SUPABASE_TRUTH_SUMMARY_TABLE);
}
if (urlParams.get("analysisTable")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_ANALYSIS_TABLE", SUPABASE_ANALYSIS_TABLE);
}
if (urlParams.get("analysisIcTable")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_ANALYSIS_IC_TABLE", SUPABASE_ANALYSIS_IC_TABLE);
}
if (urlParams.get("analysisGroupTable")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_ANALYSIS_GROUP_TABLE", SUPABASE_ANALYSIS_GROUP_TABLE);
}
if (urlParams.get("accessPassword")) {
  window.localStorage.setItem("FACTOR_LAB_ACCESS_PASSWORD", ACCESS_PASSWORD);
}
const PAGE_SIZE = 50;
const AUTO_REFRESH_INTERVAL_MS = 10000;
const REQUEST_TIMEOUT_MS = 8000;
// A fit reads a few hundred MB of score partitions and simulates a portfolio, so it is a
// compute call, not a poll. At the 8s UI timeout the default window already failed and a
// full-history window aborted every time; nginx allows 180s, so match that.
const FIT_TIMEOUT_MS = 150000;
const COVERAGE_WARN_THRESHOLD = 0.6;
const COVERAGE_DANGER_THRESHOLD = 0.3;
const LONG_SHORT_MEAN_HELP = "多空分组收益均值（日频，demo 数据）";
const FACTOR_TABLE_LABELS = [
  "Select",
  "Factor",
  "Library",
  "Market",
  "Major",
  "Subfactor",
  "Direction",
  "Compare",
  "Proof",
  "Truth",
  "Coverage",
  "IC Mean",
  "IR",
  "Long only",
  "Excess",
  "1M",
  "L/S research",
  "Long-short",
  "Checked",
  "Reuse",
];
const MONITOR_TABLE_LABELS = [
  "Status",
  "Factor",
  "Source",
  "Category",
  "IC_IR",
  "IC Mean",
  "Coverage",
  "Recent IC",
  "IC Profile",
  "Direction",
  "Compare",
  "Validation",
  "Market",
];
const ENABLE_AGENT_TASK_DEBUG = true;
const FACTOR_INTAKE_CONTRACT_DOC = "docs/FACTOR_LAB_INTAKE_REPRODUCTION_CONTRACT.md";
// AI 任务调试入口暂时关闭。恢复时打开 ENABLE_AGENT_TASK_DEBUG，并恢复 index.html 中对应入口。
const JQ_FACTOR_CATEGORIES = [
  "价格",
  "成交稳定",
  "流动性",
  "量价拥挤度",
  "成交笔数",
  "反转",
  "动量",
  "质量",
  "成长基本面",
  "SUE",
  "分析",
  "价值",
];
const MARKET_BUCKETS = [
  {
    key: "ashare",
    label: "A股",
    shortLabel: "A股",
    hint: "A股口径：Quant API / RQData / 聚宽等中国股票池",
  },
  {
    key: "us",
    label: "美股",
    shortLabel: "美股",
    hint: "美股口径：yfinance / Yahoo / US universe",
  },
  {
    key: "other",
    label: "其他",
    shortLabel: "其他",
    hint: "暂未识别或混合口径",
  },
];
const MARKET_LABEL_BY_KEY = Object.fromEntries(MARKET_BUCKETS.map((bucket) => [bucket.key, bucket.shortLabel]));
const CJ_TAXONOMY = [
  { category: "价格", subfactor: "残差波动率", direction: -1, keywords: ["residual_vol", "volatility", "波动", "残差波动"] },
  { category: "价格", subfactor: "特异率", direction: -1, keywords: ["idiosyncratic", "specific", "特异"] },
  { category: "价格", subfactor: "残差峰度", direction: -1, keywords: ["kurtosis", "峰度"] },
  { category: "价格", subfactor: "高价振幅", direction: -1, keywords: ["high_low", "amplitude", "振幅"] },
  { category: "成交稳定", subfactor: "换手率变异系数", direction: 1, keywords: ["turnover_cv", "换手率变异", "换手变异"] },
  { category: "成交稳定", subfactor: "成交占比熵", direction: 1, keywords: ["volume_entropy", "amount_entropy", "成交占比熵"] },
  { category: "成交稳定", subfactor: "重大单买入强度", direction: 1, keywords: ["large_buy", "big_order", "单买入"] },
  { category: "成交稳定", subfactor: "涨峰", direction: 1, keywords: ["surge", "涨峰"] },
  { category: "流动性", subfactor: "换手率", direction: -1, keywords: ["turnover", "换手率"] },
  { category: "流动性", subfactor: "非流动性", direction: 1, keywords: ["illiquidity", "非流动"] },
  { category: "流动性", subfactor: "一致买入占比", direction: 1, keywords: ["buy_ratio", "一致买入"] },
  { category: "量价拥挤度", subfactor: "量价相关性", direction: -1, keywords: ["volume_price_corr", "量价相关"] },
  { category: "量价拥挤度", subfactor: "加权偏度", direction: -1, keywords: ["weighted_skew", "skew", "偏度"] },
  { category: "量价拥挤度", subfactor: "时量价比", direction: 1, keywords: ["time_volume_price", "时量价"] },
  { category: "量价拥挤度", subfactor: "高量交易成本", direction: -1, keywords: ["high_volume_cost", "交易成本"] },
  { category: "成交笔数", subfactor: "每笔成交额", direction: 1, keywords: ["avg_amount", "每笔成交"] },
  { category: "成交笔数", subfactor: "高量每笔成交", direction: 1, keywords: ["high_volume_avg_amount", "高量每笔"] },
  { category: "成交笔数", subfactor: "每笔流出额占比", direction: 1, keywords: ["outflow", "流出额"] },
  { category: "反转", subfactor: "短期反转", direction: -1, keywords: ["reversal", "ret_1m", "短期反转"] },
  { category: "反转", subfactor: "收益偏度", direction: -1, keywords: ["return_skew", "收益偏度"] },
  { category: "反转", subfactor: "半衰残差动量", direction: 1, keywords: ["half_life", "residual_momentum", "半衰"] },
  { category: "动量", subfactor: "长期动量", direction: 1, keywords: ["momentum", "ret_3m", "ret_6m", "ret_12m", "长期动量"] },
  { category: "动量", subfactor: "排序动量", direction: 1, keywords: ["rank_momentum", "排序动量"] },
  { category: "质量", subfactor: "ROE", direction: 1, keywords: ["roe"] },
  { category: "质量", subfactor: "总资产周转率", direction: 1, keywords: ["asset_turnover", "总资产周转"] },
  { category: "质量", subfactor: "净利率", direction: 1, keywords: ["net_margin", "净利率"] },
  { category: "质量", subfactor: "现金总资产比率", direction: 1, keywords: ["cash_asset", "现金总资产"] },
  { category: "质量", subfactor: "现金营业收入比率", direction: 1, keywords: ["cash_revenue", "现金营业收入"] },
  { category: "成长基本面", subfactor: "ROE增长", direction: 1, keywords: ["roe_growth", "roe增长"] },
  { category: "成长基本面", subfactor: "营业收入同比", direction: 1, keywords: ["revenue_yoy", "sales_yoy", "营业收入同比"] },
  { category: "成长基本面", subfactor: "归母净利润同比", direction: 1, keywords: ["profit_yoy", "net_profit_yoy", "归母净利润"] },
  { category: "成长基本面", subfactor: "总资产周转率同比", direction: 1, keywords: ["asset_turnover_yoy", "周转率同比"] },
  { category: "SUE", subfactor: "ROE 2年 SUE", direction: 1, keywords: ["roe_sue", "sue_roe"] },
  { category: "SUE", subfactor: "总资产周转率 2年 SUE", direction: 1, keywords: ["asset_turnover_sue"] },
  { category: "SUE", subfactor: "净利率 2年 SUE", direction: 1, keywords: ["net_margin_sue"] },
  { category: "分析", subfactor: "预期增长", direction: 1, keywords: ["eps_forecast", "analyst", "预期增长", "分析师"] },
  { category: "价值", subfactor: "BP", direction: 1, keywords: ["bp", "book_to_price"] },
  { category: "价值", subfactor: "SALES2EV", direction: 1, keywords: ["sales2ev", "sales_ev", "ev_sales"] },
  { category: "价值", subfactor: "DP", direction: 1, keywords: ["dp", "dividend"] },
  { category: "价值", subfactor: "EP", direction: 1, keywords: ["ep", "earnings_to_price"] },
];
const JQ_CATEGORY_BY_FACTOR = {
  roe_ttm: "质量",
  roa_ttm: "质量",
  net_margin: "质量",
  revenue_yoy: "成长基本面",
  profit_yoy: "成长基本面",
  eps_yoy: "分析",
  asset_turnover: "质量",
  log_price: "价值",
  ret_1m: "反转",
  ret_3m: "动量",
  ret_6m: "动量",
  ret_12m: "动量",
  reversal: "反转",
  momentum_12_1: "动量",
  ret_3m_vol_adj: "动量",
  up_ratio_1m: "成交稳定",
  avg_amount_1m: "成交笔数",
  log_amount_1m: "成交笔数",
  turnover_proxy: "流动性",
  volume_ratio: "成交稳定",
  illiquidity: "流动性",
  volatility_1m: "价格",
  volatility_3m: "价格",
  volatility_6m: "价格",
  max_ret_1m: "价格",
  min_ret_1m: "价格",
  high_low_1m: "价格",
  amplitude_1m: "价格",
  ma_signal: "动量",
  vol_convergence: "量价拥挤度",
  rsi_14: "反转",
  bb_position: "价格",
};
const AGENT_TASK_TEXT = {
  title: "数据入口（待接入）",
  subtitle:
    "用于提交研报复现与因子入库任务。任务由平台后端执行，浏览器内不运行计算。",
  boundaryTitle: "执行边界",
  boundary:
    "任务与产物由后端执行并落库；前端仅负责提交与查看进度。上传控件用于提交输入文件。",
  quarantineHint: "任务、状态与指标由后端保存；大文件走对象存储。",
  submit: "接入后运行",
  submitting: "提交中...",
  emptyWarning: "请先拖入或选择文件",
  submittedToast: "任务已创建，已写入数据入口队列",
  recentTitle: "数据入口任务",
  emptyRecent: "暂无任务。拖入文件夹或文件后点击运行。",
};

const state = {
  rawFactors: [],
  filteredFactors: [],
  // factor_id -> the delivery's own verdict for that factor (eight frozen gates).
  deliveryFactors: {},
  deliverySummary: null,
  deliveryList: [],
  librarySource: null,
  // factor_id -> the delivery's full per-factor evidence (eight gates + metrics).
  deliveryEvidence: {},
  // factor_id -> the daily IC series (train / oos), for the performance charts.
  deliverySeries: {},
  // What the precomputed score matrix can fit, and the last successful fit.
  fitMeta: null,
  fitResult: null,
  // True while a fit request is in flight, so the result area can say so.
  strategyBuilderRunning: false,
  // Signed session token issued by the API (never the password itself).
  authToken: null,
  // How current each artifact is (factor values / IC series / delivery snapshot).
  freshness: null,
  // factor_id -> quantile portfolio curves (a factor shown as a portfolio).
  factorPortfolio: {},
  factorHoldings: {},
  selectedIds: new Set(),
  selectedAgentTaskIds: new Set(),
  category: "全部",
  selectedCategories: new Set(JQ_FACTOR_CATEGORIES),
  library: "全部",
  market: "ashare",
  monitorMarket: "ashare",
  proof: "all",
  truth: "all",
  reuse: "all",
  comparison: "all",
  query: "",
  page: 1,
  sortKey: null,
  sortDirection: "default",
  // 策略看板默认按年化收益降序：策略层的问题就是"扣费后赚不赚钱"，所以收益是第一排序键，
  // 夏普与最大回撤同列展示（单看收益会漏掉承担了多少波动）。点表头可切换。
  strategySortKey: "annualReturn",
  strategySortDirection: "desc",
  factorPerformance: { items: {}, meta: null },
  performanceLoaded: false,
  localConnected: false,
  quantApiConfigured: false,
  quantApiReachable: false,
  isLoading: false,
  autoRefreshTimer: null,
  monitorFilter: "all",
  monitorDirectionFilter: "all",
  monitorComparisonFilter: "all",
  monitorQuery: "",
  monitorSelectedCategories: new Set(JQ_FACTOR_CATEGORIES),
  monitorCardFilter: null,
  monitorSortKey: null,
  monitorSortDirection: "default",
  dragSelect: {
    active: false,
    targetChecked: true,
    touched: new Set(),
  },
  view: "monitor",
  activeFactorId: null,
  activeStrategyId: null,
  activeTaskId: null,
  detailTab: "analysis",
  pendingFiles: [],
  intakeTaskType: "research_reproduction",
  intakeInputMode: "folder",
  agentTasks: [],
  agentTasksLoaded: false,
  agentInstruction: "",
  agentTaskSubmitting: false,
  usableOnly: false,
  strategyDrafts: loadSavedStrategies(),
  strategyBuilderFactors: [],
  factorDetailData: {},
  factorDetailLoading: {},
  strategyTemplates: [],
  strategyTemplatesLoaded: false,
  strategyTemplatesLoading: false,
  selectedStrategyTemplateId: null,
  strategyBuilderParams: {},
  strategyBuilderWeights: {},
  strategyBuilderName: "",
  strategyBuilderResult: null,
  strategyDeleteMode: false,
  selectedStrategyDeleteIds: new Set(),
  strategyDetailLoading: {},
  strategies: [],
  strategiesLoaded: false,
  strategiesLoading: false,
  quantDeskStatus: "checking",
  quantDeskMessage: "正在检测策略服务",
  quantDeskCheckedAt: null,
  quantDeskHealthLoading: false,
  quantDeskPath: QUANT_DESK_DEFAULT_PATH,
  researchParams: {
    universe: "沪深300",
    period: "近1年",
    portfolio: "纯多头",
    cost: "无",
    limitFilter: "是",
  },
};

const pendingFileStore = new Map();
let activePreviewUrl = null;

const els = {
  pageTitle: document.querySelector("#pageTitle"),
  localStatus: document.querySelector("#localStatus"),
  cloudStatus: document.querySelector("#cloudStatus"),
  quantStatus: document.querySelector("#quantStatus"),
  libraryView: document.querySelector("#libraryView"),
  monitorView: document.querySelector("#monitorView"),
  strategyView: document.querySelector("#strategyView"),
  strategyBoardView: document.querySelector("#strategyBoardView"),
  quantDeskView: document.querySelector("#strategyView"),
  quantDeskNavGroup: document.querySelector("#quantDeskNavGroup"),
  quantDeskFrame: document.querySelector("#quantDeskFrame"),
  quantDeskTabs: document.querySelectorAll("[data-quant-desk-path]"),
  quantDeskStatusBadge: document.querySelector("#quantDeskStatusBadge"),
  quantDeskHostText: document.querySelector("#quantDeskHostText"),
  quantDeskBridgeStatus: document.querySelector("#quantDeskBridgeStatus"),
  quantDeskOpenLink: document.querySelector("#quantDeskOpenLink"),
  quantDeskReloadButton: document.querySelector("#quantDeskReloadButton"),
  quantDeskRetryButton: document.querySelector("#quantDeskRetryButton"),
  strategyBuilderView: document.querySelector("#strategyBuilderView"),
  taskView: document.querySelector("#taskView"),
  strategyDetailView: document.querySelector("#strategyDetailView"),
  detailView: document.querySelector("#detailView"),
  agentTaskView: document.querySelector("#agentTaskView"),
  settingsView: document.querySelector("#settingsView"),
  navItems: document.querySelectorAll(".nav-item[data-view]"),
  categoryTabs: document.querySelector("#categoryTabs"),
  marketTabs: document.querySelector("#marketTabs"),
  libraryTabs: document.querySelector("#libraryTabs"),
  libraryRow: document.querySelector("#libraryTabs")?.closest(".sub-filter-row"),
  proofFilter: document.querySelector("#proofFilter"),
  truthFilter: document.querySelector("#truthFilter"),
  reuseFilter: document.querySelector("#reuseFilter"),
  comparisonFilter: document.querySelector("#comparisonFilter"),
  usableOnlyToggle: document.querySelector("#usableOnlyToggle"),
  researchUniverse: document.querySelector("#researchUniverse"),
  researchPeriod: document.querySelector("#researchPeriod"),
  researchPortfolio: document.querySelector("#researchPortfolio"),
  researchCost: document.querySelector("#researchCost"),
  researchLimitFilter: document.querySelector("#researchLimitFilter"),
  searchInput: document.querySelector("#searchInput"),
  resetFiltersButton: document.querySelector("#resetFiltersButton"),
  tableBody: document.querySelector("#factorTableBody"),
  pageSummary: document.querySelector("#pageSummary"),
  pagination: document.querySelector("#pagination"),
  selectedCount: document.querySelector("#selectedCount"),
  selectedReusable: document.querySelector("#selectedReusable"),
  selectedRerun: document.querySelector("#selectedRerun"),
  selectionActions: document.querySelector("#selectionActions"),
  selectionBar: document.querySelector("#selectionBar"),
  errorPanel: document.querySelector("#errorPanel"),
  monitorStats: document.querySelector("#monitorStats"),
  monitorTableBody: document.querySelector("#monitorTableBody"),
  monitorFilters: document.querySelectorAll("[data-monitor-filter]"),
  monitorCategoryFilters: document.querySelector("#monitorCategoryFilters"),
  monitorMarketFilters: document.querySelector("#monitorMarketFilters"),
  monitorDirectionFilters: document.querySelector("#monitorDirectionFilters"),
  monitorComparisonFilters: document.querySelector("#monitorComparisonFilters"),
  monitorSearchInput: document.querySelector("#monitorSearchInput"),
  strategyStats: document.querySelector("#strategyStats"),
  strategyTableBody: document.querySelector("#strategyTableBody"),
  taskStats: document.querySelector("#taskStats"),
  taskTableBody: document.querySelector("#taskTableBody"),
  taskStagePanel: document.querySelector("#taskStagePanel"),
  themeToggleButton: document.querySelector("#themeToggleButton"),
  refreshButton: document.querySelector("#refreshButton"),
  logoutButton: document.querySelector("#logoutButton"),
  collapseButton: document.querySelector("#collapseButton"),
  loginView: document.querySelector("#loginView"),
  loginForm: document.querySelector("#loginForm"),
  loginPassword: document.querySelector("#loginPassword"),
  loginError: document.querySelector("#loginError"),
  appShell: document.querySelector(".app-shell"),
};

let collapseTimer = null;
let healthPromise = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeTheme(value) {
  return value === "light" ? "light" : "dark";
}

// ---------------------------------------------------------------------------
// 术语解释
//
// 面向第一次打开这个面板的人。面板上大量术语（IC_IR、残差 IC、量价拥挤度……）对做量化
// 的人是常识，对采购方、投资经理或刚接手的人不是。这里把每个术语用一句人话讲清楚，鼠标
// 悬停即显示。
//
// 用词条表 + 委托式悬停，而不是给每个元素写 title：面板的表格、筛选、卡片都由 JS 渲染，
// 逐个加 title 要改十几处渲染函数，且新增字段容易漏。这里只要文本能对上就有效。
// ---------------------------------------------------------------------------
const GLOSSARY = {
  // —— 顶部四个统计口径 ——
  总因子数: "已经算过 IC 的因子数量（不含只登记、未计算的候选）。点一下可以筛选。",
  有IC_IR: "有完整 IC 与 IC_IR 证据的因子数。其余的是没通过验证门槛的。",
  可复用: "八道门槛全部通过、有完整证据，可以直接用于研究和组合构建的因子。",
  需关注: "存在复现不一致或指标风险的因子，不建议直接使用。当前为 0。",
  当前边界: "这一页的能力范围：只读巡检已生成的因子与指标，不在这里计算新因子、也不替代正式的策略回测。",

  // —— 核心指标 ——
  IC: "信息系数。衡量因子「预测得准不准」——某一天把全市场股票按因子值排名、和之后一段时间的收益排名做相关性，取值 −1 到 +1。A 股日频单因子 0.01–0.07 属正常。",
  IC_IR: "信息比率。IC 的均值 ÷ IC 的标准差，衡量因子「预测得稳不稳」，和夏普比率同一个思路。IC 高但不稳定不如 IC 低但稳定。",
  IC均值: "这段区间内每日 IC 的平均值，代表预测力的大小。",
  近期IC: "最近一段时间的 IC，用于观察因子是否正在衰减。",
  IC柱: "把 IC 值画成柱子，一眼看出近期是正还是负、幅度多大。",
  覆盖率: "当天有多少比例的股票算得出这个因子。太低说明因子依赖的数据缺失严重，结论不可靠。门槛是 95%。",
  方向: "因子的正负号。正向表示因子值越大、后续收益越高；反向则相反。产品内已按方向调整，看到正值就是「越大越好」。",
  RankIC: "用排名（而不是原始数值）计算的 IC。抗极端值，是业界更常用的口径。",

  // —— 验证门槛 ——
  八道冻结门槛: "因子进入交付包必须通过的全部检查，阈值在验证开始前就已冻结、不可事后调整。",
  门槛: "这一行检查的名字。八道门槛分别针对覆盖率、预测力、样本外、风格暴露、独立信息、成本、回撤和参数稳定性。",
  结果: "这个因子在该项检查上是通过还是不通过。全部通过才会进入交付包。",
  实测: "用交付数据实际算出来的数值。旁边一列是判定标准，两者对照即知是否通过。",
  阈值: "判定标准。在验证开始前就已冻结，不会因为结果不好而调整。",
  过闸: "「通过闸门」的简写，即该因子已通过八道门槛的全部检查。",
  交付分层: "在交付包中的分档（A/B/C）。按八道门槛的实测值综合排序，A 档是交付主力。",
  未通过门槛: "这批因子算过、也被八道门槛验证过，但没有全部通过，因此交付包不为它们生成证据文件，面板上也就没有 IC/IR。注意：这与「没算过」是两件事——357 个从未计算的候选根本不在面板里。",
  待数据: "旧标签，指的是「未通过门槛」那批。已改用更准确的说法，避免被读成「数据还没到」。",
  交付验证实测: "交付包内用冻结数据实际算出的验证结果。它不是演示数据，可以逐条复核。",
  交付包: "交给客户的完整验证资产：332 份因子证据、交付清单、方法说明与哈希清单。",
  分周期: "同一因子在 5 日、10 日、20 日三个预测周期上分别计算的结果，用来判断它对周期是否敏感。",
  按年拆分: "把样本外按年度拆开单独看。只看总平均会掩盖某一年的失效，逐年看更严格。",
  样本外封存: "训练段和样本外按固定日期严格切分。因子只能在训练段上研究，样本外用来检验它是否真的有效。区间一旦确定就不能改。",
  残差IC: "剔除风格暴露之后剩下的 IC。用来回答「这个因子是不是只是动量或市值的替身」。留存率越高，说明它越有自己的独立信息。",
  // 面板上渲染的是上标：风格 R²。这里把两种写法都登记，避免只有数字 2 能命中。
  风格R2: "这个因子有多少比例能被市值、动量、波动率、流动性四种常见风格解释。越低越好，说明它不是风格的替身。",
  "风格R²": "这个因子有多少比例能被市值、动量、波动率、流动性四种常见风格解释。越低越好，说明它不是风格的替身。",
  按年拆分: "把样本外按年度拆开单独看。只看总平均会掩盖某一年的失效，逐年看更严格。",
  分周期RankIC: "同一因子在 5 日、10 日、20 日三个预测周期上分别算的 RankIC，用来判断它对周期是否敏感。",
  五分组: "把全市场按因子值从低到高分成五组，分别构建组合，用来观察因子的排序能力。",
  成本后收益: "扣掉双边交易成本之后的年化收益。因子好看不等于策略能赚钱，所以要扣费后再看。",
  回撤波动比: "最大回撤 ÷ 波动率。衡量「为了拿到这些收益，承受的回撤是否过大」。",
  参数扰动: "把因子窗口同时放大和缩小 20% 再重算。要求 IC 符号不变——符号翻转说明原来的结果只是巧合。",

  // —— 分段 ——
  训练段: "用于研究和筛选因子的历史区间（2020-01-02 至 2022-12-30）。",
  样本外: "因子选定之后、没有参与过筛选的区间（2023-01-03 至 2026-08-31）。这才是检验真实有效性的部分。",
  上线跟踪: "交付之后由日更流水线持续计算的区间。它与样本外是两段，数字不能相加。",
  交付验证: "交付包内冻结的验证结果，不随日更变化，用于事后审计。",

  // —— 组合 ——
  单调性: "按因子值分五组之后，各组收益是否依次递增。单调性 1.00 表示完全单调，说明因子的排序能力是稳定的。",
  五分组: "把全市场按因子值从低到高分成五组，分别构建组合，用来观察因子的排序能力。",
  多空: "做多最好的一组、做空最差的一组。用来剥离市场整体涨跌，单看因子的选股能力。",
  等权基准: "所有股票等权买入的收益，作为对照——用来判断因子的超额收益是否真实存在。",
  最大回撤: "从历史最高点到之后最低点的跌幅。单因子多头的回撤通常较大，组合之后会明显降低。",

  // —— 因子分类 ——
  价格: "基于开高低收、均价等价格信息构造的因子。",
  成交稳定: "衡量成交量是否稳定。成交忽大忽小通常意味着筹码不稳定。",
  流动性: "衡量股票买卖的难易程度。流动性差的股票交易成本高、冲击大。",
  量价拥挤度: "衡量资金与价格是否已经过度拥挤。拥挤度过高时，原本有效的因子容易失效。",
  成交笔数: "基于成交笔数（而非成交额）构造的因子，反映交易的分散程度。",
  反转: "短期反转：前期涨得多的股票，短期可能回落。A 股上这类因子通常比较强。",
  动量: "中期趋势延续：前期表现好的股票倾向于继续表现好。",
  质量: "基于财务质量指标（如盈利能力、现金流）构造的因子。",
  成长基本面: "基于营收、利润增长速度等成长性指标构造的因子。",
  SUE: "标准化预期外盈利。实际盈利超出分析师预期的程度，是经典的盈余惊喜指标。",
  分析: "基于分析师预期、评级、覆盖变化等数据构造的因子。",
  价值: "基于估值指标（如市盈率、市净率）构造的因子。",

  // —— 交付状态 ——
  validated: "已通过八道门槛验证，进入交付包。",
  rejected: "计算过，但至少一道门槛没有通过，未进入交付包。",
  not_run: "登记为候选但从未计算。原因是算力预算有限，优先跑最有希望的，不是失败。",
  tier: "交付分档。按八道门槛的实测值综合排序分 A/B/C 三档，A 档为交付主力。",

  // —— 产品边界 ——
  raw: "原始数据端点，会返回逐日截面因子值。当前默认关闭——对外只提供衍生指标，不提供底层数据。",
  聚合: "衍生指标端点，返回统计结果（IC、分组净值等），不含截面原始值。当前对外开放的是这一类。",
};

// 归一化：忽略大小写、空格与常见分隔符，让「IC / IR」「ic_ir」「IC_IR」都能命中
function glossaryKey(text) {
  return String(text || "")
    .replace(/[\s_/／·、,，()（）]/g, "")
    .toLowerCase();
}

const GLOSSARY_BY_KEY = new Map(
  Object.entries(GLOSSARY).map(([term, text]) => [glossaryKey(term), { term, text }]),
);

let glossaryTip = null;

function ensureGlossaryTip() {
  if (glossaryTip) return glossaryTip;
  glossaryTip = document.createElement("div");
  glossaryTip.className = "glossary-tip hidden";
  glossaryTip.setAttribute("role", "tooltip");
  document.body.appendChild(glossaryTip);
  return glossaryTip;
}

function showGlossaryTip(target, entry) {
  const tip = ensureGlossaryTip();
  tip.innerHTML = `<strong>${escapeHtml(entry.term)}</strong><span>${escapeHtml(entry.text)}</span>`;
  tip.classList.remove("hidden");

  const rect = target.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  // 默认放在元素下方；下方空间不够就翻到上方；左右夹在视口内
  let top = rect.bottom + 10;
  if (top + tipRect.height > window.innerHeight - 12) {
    top = Math.max(12, rect.top - tipRect.height - 10);
  }
  let left = rect.left;
  if (left + tipRect.width > window.innerWidth - 12) {
    left = Math.max(12, window.innerWidth - tipRect.width - 12);
  }
  tip.style.top = `${top}px`;
  tip.style.left = `${left}px`;
}

function hideGlossaryTip() {
  if (glossaryTip) glossaryTip.classList.add("hidden");
}

function initGlossary() {
  // 匹配规则：文本完全等于词条才提示（长度上限 22 字）。
  // 不要求「无子元素」——像「交付分层 A」这样的标签带了一个分档徽标，但它整体文字
  // 仍应能命中；靠「完全相等 + 长度上限」避免在容器上误触发，比要求叶子节点更实用。
  const lookup = (node) => {
    if (!node || node.nodeType !== 1) return null;
    const explicit = node.getAttribute("data-term");
    if (explicit) {
      const hit = GLOSSARY_BY_KEY.get(glossaryKey(explicit)) || GLOSSARY[explicit];
      if (hit) return typeof hit === "string" ? { term: explicit, text: hit } : hit;
    }
    const text = (node.textContent || "").trim();
    if (!text || text.length > 22) return null;
    return GLOSSARY_BY_KEY.get(glossaryKey(text)) || null;
  };

  document.addEventListener(
    "mouseover",
    (event) => {
      const entry = lookup(event.target);
      if (entry) {
        event.target.classList.add("glossary-term");
        showGlossaryTip(event.target, entry);
      } else {
        hideGlossaryTip();
      }
    },
    true,
  );
  document.addEventListener(
    "mouseout",
    (event) => {
      event.target.classList?.remove("glossary-term");
      hideGlossaryTip();
    },
    true,
  );
  // 点了就收起，避免提示挡住刚打开的内容
  document.addEventListener("click", hideGlossaryTip, true);
// 持仓明细的「加载」按钮：点击后才请求，并在等待期间启动计时器
document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-load-holdings]");
  if (!btn) return;
  const id = btn.dataset.loadHoldings;
  state.holdingsRequestStartedAt = Date.now();
  state.factorHoldings[id] = { __loading: true, startedAt: Date.now() };
  renderDetail();
  startHoldingsTicker();
  loadFactorHoldings(id).finally(() => {
    stopHoldingsTicker();
    if (state.view === "detail" && state.activeFactorId === id) renderDetail();
  });
});

  window.addEventListener("scroll", hideGlossaryTip, true);
}

function currentTheme() {
  return normalizeTheme(window.localStorage.getItem(THEME_STORAGE_KEY));
}

function updateThemeButton(theme) {
  if (!els.themeToggleButton) return;
  const isDark = theme === "dark";
  const label = els.themeToggleButton.querySelector(".theme-toggle-label");
  els.themeToggleButton.setAttribute("aria-pressed", String(isDark));
  els.themeToggleButton.setAttribute("aria-label", isDark ? "切换到白天模式" : "切换到黑夜模式");
  if (label) label.textContent = isDark ? "黑夜" : "白天";
}

function applyTheme(theme) {
  const normalized = normalizeTheme(theme);
  document.body.dataset.theme = normalized;
  window.localStorage.setItem(THEME_STORAGE_KEY, normalized);
  updateThemeButton(normalized);
  if (typeof state !== "undefined" && isQuantDeskView()) {
    window.requestAnimationFrame(() => setQuantDeskFrameSrc(true));
  }
  if (state?.view === "detail" && state.activeFactorId) {
    window.requestAnimationFrame(() => mountDetailCharts(state.activeFactorId));
  }
}

function toggleTheme() {
  applyTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
}

function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatError(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const number = Number(value);
  if (number === 0) return "0";
  if (Math.abs(number) < 0.001) return number.toExponential(2);
  return number.toFixed(6);
}

function compactName(value, edgeLength = 5, maxLength = 10) {
  const text = String(value ?? "");
  const chars = Array.from(text);
  if (chars.length <= maxLength) {
    return text;
  }
  return `${chars.slice(0, edgeLength).join("")}...${chars.slice(-edgeLength).join("")}`;
}

function formatDate(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").replace("Z", "").slice(0, 16);
}

function formatFileSize(bytes) {
  const size = Number(bytes);
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "app-toast";
  toast.textContent = message;
  document.body.appendChild(toast);
  window.setTimeout(() => toast.classList.add("visible"), 10);
  window.setTimeout(() => {
    toast.classList.remove("visible");
    window.setTimeout(() => toast.remove(), 180);
  }, 2200);
}

function proofBadge(status) {
  const map = {
    passed: ["已通过", "badge-green"],
    failed: ["失败", "badge-red"],
    partial: ["部分", "badge-orange"],
    truth_ready: ["已接入", "badge-blue"],
    pending: ["等待", "badge-gray"],
    missing: ["缺失", "badge-gray"],
  };
  return map[status] || ["状态未知", "badge-gray"];
}

function truthBadge(status) {
  const map = {
    exact_match: ["完全匹配", "badge-green"],
    mismatch: ["不匹配", "badge-red"],
    not_applicable: ["无需对照", "badge-blue"],
    not_compared: ["待对照", "badge-gray"],
    pending: ["待对照", "badge-gray"],
    empty_compare: ["对照异常", "badge-orange"],
    missing: ["缺失", "badge-gray"],
  };
  return map[status] || ["状态未知", "badge-gray"];
}

function proofValue(status) {
  const map = {
    passed: "复现通过",
    failed: "复现失败",
    partial: "部分通过",
    pending: "等待验证",
    missing: "缺少产物",
  };
  return map[status] || "状态未知";
}

function truthValue(status) {
  const map = {
    exact_match: "完全匹配",
    mismatch: "不匹配",
    not_applicable: "无需对照",
    not_compared: "待对照",
    pending: "待对照",
    empty_compare: "对照异常",
    missing: "缺失",
  };
  return map[status] || "状态未知";
}

function isTruthIssue(status) {
  return ["mismatch", "empty_compare", "missing"].includes(status);
}

function truthMetricTone(status) {
  if (status === "exact_match") return "good";
  if (isTruthIssue(status)) return "warn";
  return "";
}

function truthTextClass(status) {
  if (status === "exact_match") return "text-green";
  if (isTruthIssue(status)) return "text-red";
  return "";
}

function factorTaxonomy(factor) {
  const fields = [
    factor?.raw_factor_name,
    factor?.factor_name,
    factor?.subcategory,
    factor?.category,
    factor?.library,
    factor?.raw_library,
    factor?.source_document,
    factor?.data_source,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const name = String(factor?.raw_factor_name || factor?.factor_name || "").toLowerCase();
  const directCategory = JQ_CATEGORY_BY_FACTOR[name];
  const directRule = directCategory
    ? CJ_TAXONOMY.find((rule) => rule.category === directCategory && rule.keywords.some((keyword) => fields.includes(keyword)))
    : null;
  const rule = directRule || CJ_TAXONOMY.find((item) => item.keywords.some((keyword) => fields.includes(keyword)));
  if (rule) {
    return { ...rule, matched: true };
  }

  const subcategory = String(factor?.subcategory || "").toLowerCase();
  const category = String(factor?.category || "").toLowerCase();
  const library = String(factor?.library || factor?.raw_library || "").toLowerCase();
  if (directCategory) return { category: directCategory, subfactor: factor?.subcategory || directCategory, direction: 1, matched: true };
  if (subcategory.includes("成长")) return { category: "成长基本面", subfactor: factor?.subcategory || "成长指标", direction: 1, matched: true };
  if (subcategory.includes("盈利") || subcategory.includes("营运")) return { category: "质量", subfactor: factor?.subcategory || "质量指标", direction: 1, matched: true };
  if (subcategory.includes("成交")) return { category: "成交稳定", subfactor: factor?.subcategory || "成交指标", direction: 1, matched: true };
  if (subcategory.includes("流动") || subcategory.includes("换手")) return { category: "流动性", subfactor: factor?.subcategory || "流动性指标", direction: -1, matched: true };
  if (subcategory.includes("波动") || subcategory.includes("振幅")) return { category: "价格", subfactor: factor?.subcategory || "价格波动指标", direction: -1, matched: true };
  if (subcategory.includes("反转")) return { category: "反转", subfactor: factor?.subcategory || "反转指标", direction: -1, matched: true };
  if (subcategory.includes("动量") || subcategory.includes("收益")) return { category: "动量", subfactor: factor?.subcategory || "动量指标", direction: 1, matched: true };
  if (category.includes("价值") || category.includes("规模")) return { category: "价值", subfactor: factor?.subcategory || "估值指标", direction: 1, matched: true };
  if (category.includes("财务") || library.includes("fundamental")) return { category: "质量", subfactor: factor?.subcategory || "财务质量指标", direction: 1, matched: false };
  if (category.includes("量价") || category.includes("技术")) return { category: "量价拥挤度", subfactor: factor?.subcategory || "量价指标", direction: 1, matched: false };
  return { category: "价格", subfactor: factor?.subcategory || "待细分", direction: monitorDirection(factor).className === "negative" ? -1 : 1, matched: false };
}

function taxonomySearchText(factor) {
  const taxonomy = factorTaxonomy(factor);
  const direction = taxonomy.direction < 0 ? "反向 -1" : "正向 +1";
  const comparison = factorComparisonStatus(factor);
  return [taxonomy.category, taxonomy.subfactor, direction, comparison.label, comparison.key].join(" ");
}

function factorComparisonStatus(factor) {
  const truth = factor?.truth_status || "missing";
  const proof = factor?.proof_status || "missing";
  if (truth === "exact_match") {
    return { key: "matched", label: "已对照", className: "matched", title: "真值校验完全匹配" };
  }
  if (["mismatch", "empty_compare"].includes(truth) || proof === "failed") {
    return { key: "review", label: "需复核", className: "review", title: "真值或复现结果需要人工复核" };
  }
  if (truth === "not_applicable") {
    return { key: "not_applicable", label: "无需对照", className: "not-applicable", title: "当前因子无需真值对照" };
  }
  if (["not_compared", "pending", "missing"].includes(truth) || ["missing", "partial"].includes(proof)) {
    return { key: "pending", label: "待对照", className: "pending", title: "尚未完成因子真值对照" };
  }
  return { key: "pending", label: "待对照", className: "pending", title: `当前状态：${truth || proof}` };
}

function factorComparisonBadgeHtml(factor) {
  const status = factorComparisonStatus(factor);
  return `<span class="comparison-badge ${status.className}" title="${escapeHtml(status.title)}">${escapeHtml(status.label)}</span>`;
}

function taxonomyCellHtml(factor) {
  const taxonomy = factorTaxonomy(factor);
  return `
    <span class="taxonomy-main">${escapeHtml(taxonomy.category)}</span>
    ${taxonomy.matched ? "" : '<span class="taxonomy-pending">待确认</span>'}
  `;
}

function taxonomySubfactorHtml(factor) {
  const taxonomy = factorTaxonomy(factor);
  return `<span class="factor-subcategory">${escapeHtml(taxonomy.subfactor)}</span>`;
}

function taxonomyDirectionHtml(factor) {
  const taxonomy = factorTaxonomy(factor);
  const className = taxonomy.direction < 0 ? "negative" : "positive";
  const symbol = taxonomy.direction < 0 ? "-1" : "+1";
  const label = taxonomy.direction < 0 ? "反向" : "正向";
  return `<span class="direction-pill ${className}" title="按券商分类表方向字段展示">${symbol} ${label}</span>`;
}

function recommendationClass(value) {
  if (value === "可复用") return "reusable";
  if (value === "建议重跑") return "rerun";
  if (value === "未复现") return "missing";
  return "";
}

function reuseStatus(factor) {
  const direct = recommendationClass(factor?.reuse_recommendation);
  if (direct) return direct;

  const proof = factor?.proof_status;
  const truth = factor?.truth_status;
  if (proof === "passed" && truth === "exact_match") return "reusable";
  if (proof === "failed" || proof === "partial" || truth === "mismatch") return "rerun";
  // A delivery verdict is stronger evidence than a missing proof: it means the
  // factor passed all eight frozen gates. Report it as reusable, but keep the
  // distinction visible through recommendationBasis().
  if (isDelivered(factor)) return "reusable";
  if (proof === "missing") return "missing";
  return "unconfirmed";
}

// Which piece of evidence a UI decision stands on, so the label can say so.
function recommendationBasis(factor) {
  const proof = factor?.proof_status;
  const truth = factor?.truth_status;
  if (proof === "passed" && truth === "exact_match") return "proof";
  if (isDelivered(factor)) return "delivery";
  return "none";
}

function canOpenFactor(factor) {
  // Openable when there is something real to show: a cached research job, or the
  // delivery's per-factor evidence.
  if (deliveryVerdict(factor)) return true;
  return Boolean(factor?.latest_job_id) && factor?.proof_status !== "missing";
}

function factorReplicationStatus(factor) {
  // 临时映射：后端正式字段 replication_status 到位前，用现有 proof_status 作为复现状态。
  if (factor?.replication_status) return factor.replication_status;
  if (factor?.proof_status === "passed") return "passed";
  if (factor?.proof_status === "failed") return "failed";
  return "pending";
}

// The delivery's verdict is a different thing from the reproducibility proof:
// `proof_status` answers "does our reimplementation match the source formula",
// while the delivery answers "did this factor pass the eight frozen gates and stay
// free of risk exposure". Both are evidence, and the client's own definition of
// deliverable is the second one, so selection accepts either — and says which.
function deliveryVerdict(factor) {
  const row = state.deliveryFactors?.[factor?.id];
  if (!row) return null;
  if (row.in_delivery_package === true || row.in_delivery_package === "true") return "delivered";
  if (row.status === "validated") return "validated";
  if (row.status === "rejected") return "rejected";
  return null;
}

// True only for the delivery's *positive* verdict. `deliveryVerdict` also returns
// "rejected", which is a real verdict but must never be read as "usable".
function isDelivered(factor) {
  const verdict = deliveryVerdict(factor);
  return verdict === "delivered" || verdict === "validated";
}

function factorAlphaTier(factor) {
  // 临时映射：后端正式字段 alpha_tier 到位前，用 IR 近似分层。IR>0.3 strong，0.1~0.3 weak，<0.1 dead。
  if (factor?.alpha_tier) return factor.alpha_tier;
  const ir = Math.abs(toFiniteNumber(factor?.rank_ic_ir) ?? 0);
  if (ir > 0.3) return "strong";
  if (ir >= 0.1) return "weak";
  return "dead";
}

function factorAdmission(factor) {
  const replication = factorReplicationStatus(factor);
  const alphaTier = factorAlphaTier(factor);
  const delivery = deliveryVerdict(factor);
  const proofPassed = replication === "passed";
  const deliveryPassed = delivery === "delivered" || delivery === "validated";
  const inLibrary = proofPassed || deliveryPassed;
  const agentReadable = inLibrary && alphaTier !== "dead";
  return {
    replication,
    alphaTier,
    delivery,
    admissionBasis: proofPassed ? "proof" : deliveryPassed ? "delivery" : "none",
    inLibrary,
    agentReadable,
    selectable: inLibrary,
    weak: inLibrary && ["dead", "weak"].includes(alphaTier),
  };
}

function isProofFailed(factor) {
  return factor?.proof_status === "failed";
}

function mutedDash(title = "") {
  return `<span class="muted-dash" title="${escapeHtml(title)}">—</span>`;
}

function coverageClass(value) {
  const coverage = toFiniteNumber(value);
  if (coverage === null) return "";
  if (coverage < COVERAGE_DANGER_THRESHOLD) return "coverage-danger";
  if (coverage < COVERAGE_WARN_THRESHOLD) return "coverage-warning";
  return "";
}

function coverageTitle(value) {
  const coverage = toFiniteNumber(value);
  if (coverage === null || coverage >= COVERAGE_WARN_THRESHOLD) return "";
  return "覆盖率偏低，指标可信度受限";
}

function truthBadgeHtml(factor) {
  if (isProofFailed(factor)) {
    return mutedDash("复现失败时不展示真值校验结果");
  }
  const [truthText, truthClass] = truthBadge(factor.truth_status);
  const ratio = formatRatio(factor.truth_exact_match_ratio);
  const title = ratio === "-" ? truthText : `${truthText} · 匹配率 ${ratio}`;
  return `<span class="badge ${truthClass}" title="${escapeHtml(title)}">${truthText}</span>`;
}

function factorMetricHtml(factor, key, formatter, title = "复现失败时不展示该指标") {
  if (isProofFailed(factor)) {
    return mutedDash(title);
  }
  return formatter(factor[key]);
}

function artifactUrl(factor, kind) {
  if (CLOUD_DEMO_MODE) return "";
  if (!factor?.latest_job_id) return "";
  const base = `${API_BASE}/artifacts/${encodeURIComponent(factor.latest_job_id)}/${kind}`;
  if (kind === "proof") {
    return `${base}?factor=${encodeURIComponent(factor.raw_factor_name || factor.factor_name)}`;
  }
  return base;
}

function tabButton(label, count, active, onClick, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = active ? "tab active" : "tab";
  button.textContent = count === undefined ? label : `${label}${label === "全部" ? "" : ` (${count})`}`;
  if (disabled) {
    button.disabled = true;
    button.title = "暂无该类因子";
  } else {
    button.addEventListener("click", onClick);
  }
  return button;
}

function categoryCheckbox(label, checked, onChange, disabled = false, count = undefined) {
  const wrapper = document.createElement("label");
  wrapper.className = disabled ? "category-check disabled" : "category-check";
  if (count !== undefined) {
    wrapper.title = `${label}：${count} 个因子`;
  }
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = checked;
  checkbox.disabled = disabled;
  checkbox.addEventListener("change", onChange);
  const text = document.createElement("span");
  text.textContent = label;
  wrapper.append(checkbox, text);
  return wrapper;
}

function renderTabs(payload) {
  const categories = payload.categories || {};
  const libraries = payload.libraries || {};
  ensureMarketSelections();
  renderMarketTabs();
  if (state.library !== "全部" && (libraries[state.library] ?? 0) === 0) {
    state.library = "全部";
  }
  els.categoryTabs.replaceChildren();
  const allSelected = JQ_FACTOR_CATEGORIES.every((label) => state.selectedCategories.has(label));
  els.categoryTabs.appendChild(categoryCheckbox("全选", allSelected, () => {
    state.selectedCategories = allSelected ? new Set() : new Set(JQ_FACTOR_CATEGORIES);
    state.category = state.selectedCategories.size === JQ_FACTOR_CATEGORIES.length ? "全部" : "自定义";
    state.page = 1;
    renderTabs({ categories: countCategories(), libraries: countLibraries() });
    applyFilters();
  }));
  JQ_FACTOR_CATEGORIES.forEach((label) => {
    const count = categories[label] ?? 0;
    els.categoryTabs.appendChild(
      categoryCheckbox(label, state.selectedCategories.has(label), () => {
        if (state.selectedCategories.has(label)) {
          state.selectedCategories.delete(label);
        } else {
          state.selectedCategories.add(label);
        }
        state.category = state.selectedCategories.size === JQ_FACTOR_CATEGORIES.length ? "全部" : "自定义";
        state.page = 1;
        renderTabs({ categories: countCategories(), libraries: countLibraries() });
        applyFilters();
      }, false, count),
    );
  });

  const showLibraryTabs = false;
  els.libraryRow?.classList.toggle("hidden", !showLibraryTabs);
  els.libraryTabs.replaceChildren();
  if (!showLibraryTabs) {
    return;
  }

  ["全部", "WQ101", "GTJA191", "Quant API", "TA-Lib", "User Custom"].forEach((label) => {
    const count = label === "全部" ? state.rawFactors.length : libraries[label] ?? 0;
    const disabled = label !== "全部" && count === 0;
    els.libraryTabs.appendChild(
      tabButton(label, count, state.library === label, () => {
        state.library = label;
        state.page = 1;
        renderTabs({ categories: countCategories(), libraries: countLibraries() });
        applyFilters();
      }, disabled),
    );
  });
}

function renderMonitorCategoryFilters() {
  if (!els.monitorCategoryFilters) return;
  const allSelected = JQ_FACTOR_CATEGORIES.every((label) => state.monitorSelectedCategories.has(label));
  els.monitorCategoryFilters.replaceChildren();
  els.monitorCategoryFilters.appendChild(categoryCheckbox("全选", allSelected, () => {
    state.monitorSelectedCategories = allSelected ? new Set() : new Set(JQ_FACTOR_CATEGORIES);
    renderMonitor();
  }));
  JQ_FACTOR_CATEGORIES.forEach((label) => {
    els.monitorCategoryFilters.appendChild(
      categoryCheckbox(label, state.monitorSelectedCategories.has(label), () => {
        if (state.monitorSelectedCategories.has(label)) {
          state.monitorSelectedCategories.delete(label);
        } else {
          state.monitorSelectedCategories.add(label);
        }
        renderMonitor();
      }),
    );
  });
}

function renderMonitorDirectionFilters() {
  els.monitorDirectionFilters?.querySelectorAll("[data-monitor-direction]").forEach((button) => {
    button.classList.toggle("active", button.dataset.monitorDirection === state.monitorDirectionFilter);
  });
}

function renderMonitorComparisonFilters() {
  els.monitorComparisonFilters?.querySelectorAll("[data-monitor-comparison]").forEach((button) => {
    button.classList.toggle("active", button.dataset.monitorComparison === state.monitorComparisonFilter);
  });
}

function updateConnectionStatus(ok, payload) {
  state.localConnected = ok;
  els.localStatus.className = ok ? "status-pill status-ok" : "status-pill status-bad";
  if (USE_SUPABASE_DASHBOARD) {
    els.localStatus.textContent = "数据服务：已连接";
    els.localStatus.title = "数据由平台自建服务提供";
  } else if (CLOUD_DEMO_MODE) {
    els.localStatus.textContent = "数据服务：演示模式";
    els.localStatus.title = "当前使用静态演示数据，未连接数据服务";
  } else {
    els.localStatus.textContent = ok ? "数据服务：已连接" : "数据服务：未连接";
    els.localStatus.title = ok ? "已通过 /health 接口确认" : "未能访问服务端 /health 接口，请联系平台管理员";
  }
  // The Supabase mirror is gone from the client path, so a "云端信息库：未同步" pill would
  // describe a component that no longer exists and read to a client as a broken sync.
  // When the mirror is not in use, say where the data actually comes from instead.
  if (els.cloudStatus) {
    if (USE_SUPABASE_DASHBOARD) {
      const cloudLabel = payload?.cloud_registry?.label || "Supabase Public Dashboard";
      els.cloudStatus.textContent = `云端信息库：${cloudLabel}`;
      els.cloudStatus.classList.remove("hidden");
    } else {
      els.cloudStatus.textContent = "数据源：服务器直读";
      els.cloudStatus.title = "因子判定、逐日 IC 与拟合结果均由服务器上的交付文件计算，不再经过任何云同步副本";
      els.cloudStatus.classList.toggle("status-ok", Boolean(ok));
      els.cloudStatus.classList.toggle("status-warn", !ok);
    }
  }
}

function updateQuantApiStatus(payload, failed = false) {
  if (!els.quantStatus) return;
  if (failed) {
    state.quantApiConfigured = false;
    state.quantApiReachable = false;
    els.quantStatus.className = "status-pill status-bad";
    els.quantStatus.textContent = "Quant API：检测失败";
    els.quantStatus.title = "未能通过平台服务端查询 Quant API 配置状态";
    return;
  }
  const configured = Boolean(payload?.token_configured);
  state.quantApiConfigured = configured;
  state.quantApiReachable = true;
  if (CLOUD_DEMO_MODE) {
    els.quantStatus.className = "status-pill status-warn";
    els.quantStatus.textContent = "Quant API：静态演示";
    els.quantStatus.title = "演示模式下不调用真实 Quant API";
    return;
  }
  els.quantStatus.className = configured ? "status-pill status-ok" : "status-pill status-warn";
  els.quantStatus.textContent = configured ? "Quant API：已配置 token" : "Quant API：未配置 token";
  els.quantStatus.title = configured
    ? `官方数据代理已配置：${payload?.base_url || "Quant API"}`
    : "Static preview does not bundle backend credentials.";
}

function updateRefreshButton(loading) {
  els.refreshButton.disabled = loading;
  els.refreshButton.classList.toggle("is-loading", loading);
  els.refreshButton.textContent = loading ? "刷新中..." : "刷新";
  els.refreshButton.setAttribute("aria-busy", String(loading));
}

function applyTableLabels(row, labels) {
  Array.from(row.children).forEach((cell, index) => {
    if (labels[index]) {
      cell.dataset.label = labels[index];
    }
  });
}

function withCacheBust(url) {
  const parsed = new URL(url, window.location.href);
  parsed.searchParams.set("_", String(Date.now()));
  return parsed.toString();
}

async function fetchWithTimeout(url, options = {}) {
  const { timeoutMs = REQUEST_TIMEOUT_MS, ...rest } = options;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    // The client's data routes require the session token issued by the API. Adding it
    // in one place means a new call site cannot forget it.
    const headers = { ...(rest.headers || {}) };
    if (state.authToken) headers.Authorization = `Bearer ${state.authToken}`;
    const response = await fetch(url, {
      cache: "no-store",
      ...rest,
      headers,
      signal: controller.signal,
    });
    if (response.status === 401 && state.authToken) {
      // The session expired or was revoked: drop it and ask again rather than
      // showing a half-loaded page.
      state.authToken = null;
      window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
      showLogin("登录已过期，请重新输入密码");
    }
    return response;
  } finally {
    window.clearTimeout(timeout);
  }
}

function quantDeskStatusLabel() {
  if (state.quantDeskStatus === "ok") return "策略服务：已连接";
  if (state.quantDeskStatus === "bad") return "策略服务：离线";
  return "策略服务：检测中";
}

function quantDeskStatusClass() {
  if (state.quantDeskStatus === "ok") return "status-pill status-ok";
  if (state.quantDeskStatus === "bad") return "status-pill status-bad";
  return "status-pill status-warn";
}

function quantDeskUrl(path = state.quantDeskPath) {
  if (!QUANT_DESK_ENABLED) return "about:blank";
  const normalizedPath = String(path || "").replace(/^\/+/, "");
  const url = new URL(normalizedPath ? `${QUANT_DESK_BASE}${normalizedPath}` : QUANT_DESK_BASE);
  url.searchParams.set("embedded", "factor-lab");
  url.searchParams.set("theme", normalizeTheme(document.body?.dataset?.theme || currentTheme()));
  return url.toString();
}

function renderQuantDeskTabs() {
  els.quantDeskTabs?.forEach((button) => {
    button.classList.toggle("active", (button.dataset.quantDeskPath || "") === state.quantDeskPath);
  });
}

function isQuantDeskView() {
  return state.view === "quant-desk" || state.view === "strategy";
}

function setQuantDeskFrameSrc(force = false) {
  if (!els.quantDeskFrame) return;
  const target = quantDeskUrl();
  const current = els.quantDeskFrame.getAttribute("src") || "";
  const currentUrl = current && current !== "about:blank" ? new URL(current, window.location.href).toString() : "";
  if (force || !currentUrl || currentUrl !== target) {
    els.quantDeskFrame.setAttribute("src", target);
  }
}

function renderQuantDesk() {
  if (!els.quantDeskView) return;
  renderQuantDeskTabs();
  if (els.quantDeskHostText) els.quantDeskHostText.textContent = QUANT_DESK_HOST;
  if (els.quantDeskOpenLink) els.quantDeskOpenLink.href = quantDeskUrl();
  if (els.quantDeskStatusBadge) {
    els.quantDeskStatusBadge.className = quantDeskStatusClass();
    els.quantDeskStatusBadge.textContent = quantDeskStatusLabel();
    els.quantDeskStatusBadge.title = state.quantDeskMessage;
  }
  if (els.quantDeskBridgeStatus) {
    els.quantDeskBridgeStatus.className = `quant-desk-bridge-status ${state.quantDeskStatus}`;
    els.quantDeskBridgeStatus.textContent = state.quantDeskMessage;
  }
  setQuantDeskFrameSrc(false);
  if (!state.quantDeskCheckedAt && !state.quantDeskHealthLoading) {
    checkQuantDeskHealth();
  }
}

async function checkQuantDeskHealth() {
  // Nothing to probe when the deployment has no Quant Desk; probing an empty host would
  // just produce a confusing offline state for a feature that is not offered.
  if (!QUANT_DESK_ENABLED) {
    state.quantDeskStatus = "disabled";
    state.quantDeskMessage = "本部署未配置策略看板";
    return;
  }
  state.quantDeskHealthLoading = true;
  state.quantDeskStatus = "checking";
  state.quantDeskMessage = `正在检测 ${QUANT_DESK_HOST}`;
  renderQuantDesk();
  try {
    const response = await fetchWithTimeout(withCacheBust(QUANT_DESK_HEALTH));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.quantDeskStatus = "ok";
    state.quantDeskMessage = `已打通 ${QUANT_DESK_BASE}`;
  } catch (error) {
    state.quantDeskStatus = "bad";
    state.quantDeskMessage = `请先启动 backend/strategy_dashboard_api.py，或用 ?quantDesk=... 指向已部署主机。${error.message || error}`;
  } finally {
    state.quantDeskHealthLoading = false;
    state.quantDeskCheckedAt = new Date().toISOString();
    renderQuantDesk();
  }
}

function parseJsonObject(value) {
  if (!value) return {};
  if (typeof value === "object" && !Array.isArray(value)) return value;
  if (typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (error) {
    return {};
  }
}

function normalizeSupabaseFactorRow(row) {
  const payload = parseJsonObject(row.payload);
  return {
    ...payload,
    id: payload.id || row.factor_id || row.id,
    factor_name: payload.factor_name || row.factor_name || row.factor_id || row.id,
    raw_factor_name: payload.raw_factor_name || row.raw_factor_name || row.factor_name || row.factor_id,
    library: payload.library || row.library || row.factor_family || "User Custom",
    raw_library: payload.raw_library || row.raw_library || row.factor_family || row.library,
    category: payload.category || row.category || "自定义因子",
    source: payload.source || row.source || "supabase_public_dashboard",
    source_id: payload.source_id || row.source_id || row.factor_id || row.id,
    display_name: payload.display_name || row.display_name || row.factor_name || row.factor_id,
    description: payload.description || row.description || "",
    formula: payload.formula || row.formula || "",
    implementation_status: payload.implementation_status || row.implementation_status || "registered",
    proof_status: payload.proof_status || row.proof_status || null,
    truth_status: payload.truth_status || row.truth_status || null,
    overall_status: payload.overall_status || row.overall_status || row.status || "registered",
    coverage_ratio: payload.coverage_ratio ?? row.coverage_ratio ?? null,
    rank_ic_mean: payload.rank_ic_mean ?? row.rank_ic_mean ?? row.ic_mean ?? null,
    rank_ic_ir: payload.rank_ic_ir ?? row.rank_ic_ir ?? row.ic_ir ?? null,
    long_short_mean: payload.long_short_mean ?? row.long_short_mean ?? null,
    truth_exact_match_ratio: payload.truth_exact_match_ratio ?? row.truth_exact_match_ratio ?? null,
    truth_max_abs_error: payload.truth_max_abs_error ?? row.truth_max_abs_error ?? null,
    latest_job_id: payload.latest_job_id || row.latest_task_id || row.task_id || null,
    latest_checked_at: payload.latest_checked_at || row.latest_checked_at || row.updated_at || row.created_at || null,
    data_source: payload.data_source || row.data_source || "Supabase",
    metadata: {
      ...(payload.metadata || {}),
      supabase_row_id: row.id,
    },
  };
}

function normalizeSupabaseTruthSummaryRow(row) {
  const family = String(row.factor_family || "unknown").trim();
  const factorName = String(row.factor_name || "unknown_factor").trim();
  const sourceVersion = String(row.source_version || "v1").trim();
  const rowCount = toFiniteNumber(row.row_count);
  const symbolCount = toFiniteNumber(row.symbol_count);
  const startDate = row.start_date || null;
  const endDate = row.end_date || null;
  const latestImportedAt = row.latest_imported_at || null;
  const familyKey = family.toLowerCase();
  const library = familyKey === "alpha101" ? "WQ101" : family.toUpperCase();
  return {
    id: `truth:${familyKey}:${factorName}:${sourceVersion}`,
    factor_name: factorName,
    raw_factor_name: factorName,
    library,
    raw_library: `${family} truth`,
    category: "真值库",
    subcategory: "",
    market: "ashare",
    universe: "A股",
    source: "supabase_truth_summary",
    source_id: `${family}:${factorName}:${sourceVersion}`,
    display_name: factorName,
    description: `标准真值已接入：${formatInteger(rowCount)} 条，${formatInteger(symbolCount)} 只标的，${startDate || "-"} 至 ${endDate || "-"}`,
    formula: "",
    implementation_status: "truth_ready",
    proof_status: "truth_ready",
    truth_status: "not_compared",
    overall_status: "truth_ready",
    coverage_ratio: null,
    rank_ic_mean: null,
    rank_ic_ir: null,
    long_short_mean: null,
    truth_exact_match_ratio: null,
    truth_max_abs_error: null,
    latest_job_id: null,
    latest_checked_at: latestImportedAt,
    data_source: "Supabase",
    metadata: {
      truth_summary_source: true,
      factor_family: family,
      source_version: sourceVersion,
      row_count: rowCount,
      symbol_count: symbolCount,
      start_date: startDate,
      end_date: endDate,
      min_truth_value: row.min_truth_value,
      max_truth_value: row.max_truth_value,
      avg_truth_value: row.avg_truth_value,
      latest_imported_at: latestImportedAt,
      supabase_table: SUPABASE_TRUTH_SUMMARY_TABLE,
      market: "ashare",
      universe: "A股",
    },
  };
}

function canonicalFactorKey(factor) {
  const rawLibrary = String(
    factor.library || factor.raw_library || factor.factor_family || ""
  ).trim();
  const family = _normalizeLibrary(rawLibrary);

  const rawName = String(
    factor.raw_factor_name || factor.factor_name || factor.id || ""
  ).trim();
  const name = _normalizeFactorName(rawName, family);

  return `${family}:${name}`;
}

function _normalizeLibrary(raw) {
  var lower = raw.toLowerCase().replace(/[\s_-]+/g, "");
  if (!lower) return "unknown";
  if (lower.includes("alpha101") || lower.includes("wq101") || lower.includes("worldquant")) {
    return "wq101";
  }
  if (lower.includes("gtja191") || lower.includes("alpha191")) {
    return "gtja191";
  }
  if (lower.includes("quantapi")) {
    return "quantapi";
  }
  if (lower.includes("alpha158")) {
    return "alpha158";
  }
  return lower;
}

function _normalizeFactorName(raw, family) {
  // Collapse separators and spaces to underscores for consistent matching.
  var cleaned = raw.toLowerCase()
    .replace(/[\s#:]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");

  if (!cleaned) return "unknown";

  // Pattern A: "worldquant_alpha013" or "WorldQuant Alpha013"
  var wqMatch = cleaned.match(/(?:^|_)worldquant[_-]?alpha0*(\d+)/);
  if (wqMatch) {
    return "alpha" + Number(wqMatch[1]);
  }

  // Pattern B: "alpha013" or "alpha13"
  var alphaMatch = cleaned.match(/(?:^|_)alpha0*(\d+)$/);
  if (alphaMatch) {
    return "alpha" + Number(alphaMatch[1]);
  }

  // Pattern C: "gtja191_alpha_001"
  var libAlphaMatch = cleaned.match(/^[a-z0-9]+_alpha_?0*(\d+)$/);
  if (libAlphaMatch) {
    return "alpha" + Number(libAlphaMatch[1]);
  }

  // Pattern D: strip known library prefix
  var knownPrefixes = /^(?:wq101|alpha101|gtja191|alpha191|quantapi|alpha158)[:_-]/;
  if (knownPrefixes.test(cleaned)) {
    var remainder = cleaned.replace(knownPrefixes, "");
    var remainderMatch = remainder.match(/(?:worldquant[_-]?)?alpha0*(\d+)/);
    if (remainderMatch) {
      return "alpha" + Number(remainderMatch[1]);
    }
    return remainder.replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "unknown";
  }

  return cleaned.replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "unknown";
}

function dedupeSupabaseFactors(factors) {
  const seen = new Set();
  return factors.filter((factor) => {
    const key = canonicalFactorKey(factor);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function formatInteger(value) {
  const number = toFiniteNumber(value);
  return number === null ? "-" : Math.round(number).toLocaleString("zh-CN");
}

async function fetchSupabaseRows(tableName, { order = "", limit = 1000, offset = 0, filters = {} } = {}) {
  const endpoint = new URL(`${SUPABASE_URL}/rest/v1/${encodeURIComponent(tableName)}`);
  endpoint.searchParams.set("select", "*");
  if (order) endpoint.searchParams.set("order", order);
  endpoint.searchParams.set("limit", String(limit));
  if (offset) endpoint.searchParams.set("offset", String(offset));
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      endpoint.searchParams.set(key, String(value));
    }
  });
  const response = await fetchWithTimeout(endpoint.toString(), {
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    let detail = "";
    try {
      detail = await response.text();
    } catch (error) {
      detail = "";
    }
    throw new Error(`Supabase ${tableName} HTTP ${response.status}${detail ? `: ${detail.slice(0, 160)}` : ""}`);
  }
  const rows = await response.json();
  return Array.isArray(rows) ? rows : [];
}

async function fetchSupabaseAllRows(tableName, { order = "", filters = {}, pageSize = 1000, maxRows = 50000 } = {}) {
  const rows = [];
  for (let offset = 0; offset < maxRows; offset += pageSize) {
    const page = await fetchSupabaseRows(tableName, {
      order,
      limit: pageSize,
      offset,
      filters,
    });
    rows.push(...page);
    if (page.length < pageSize) break;
  }
  return rows;
}

async function fetchSupabaseDashboardPayload() {
  const factors = [];
  const errors = [];
  const tables = [];
  if (SUPABASE_FACTOR_TABLE && SUPABASE_FACTOR_TABLE !== SUPABASE_TRUTH_SUMMARY_TABLE) {
    try {
      const rows = await fetchSupabaseRows(SUPABASE_FACTOR_TABLE, {
        order: "latest_checked_at.desc.nullslast",
        limit: 1000,
      });
      factors.push(...rows.map(normalizeSupabaseFactorRow));
      tables.push(SUPABASE_FACTOR_TABLE);
    } catch (error) {
      errors.push(error);
    }
  }
  if (SUPABASE_TRUTH_SUMMARY_TABLE) {
    try {
      const rows = await fetchSupabaseRows(SUPABASE_TRUTH_SUMMARY_TABLE, {
        order: "latest_imported_at.desc.nullslast",
        limit: 1000,
      });
      factors.push(...rows.map(normalizeSupabaseTruthSummaryRow));
      tables.push(SUPABASE_TRUTH_SUMMARY_TABLE);
    } catch (error) {
      errors.push(error);
    }
  }
  if (!factors.length && errors.length) {
    throw new Error(errors.map((error) => error.message).join(" | "));
  }
  return {
    schema_version: "factor_lab_view_v1",
    generated_at: new Date().toISOString(),
    local_flask: { connected: false },
    cloud_registry: { status: "supabase", label: "Supabase Public Dashboard" },
    metadata: {
      factor_source_types: ["supabase_public_dashboard"],
      warning_count: 0,
      factor_source_warning_count: 0,
      artifact_warning_count: 0,
      supabase_table: SUPABASE_FACTOR_TABLE,
      supabase_truth_summary_table: SUPABASE_TRUTH_SUMMARY_TABLE,
      supabase_loaded_tables: tables,
    },
    errors: errors.map((error) => error.message),
    factors: dedupeSupabaseFactors(factors),
  };
}

async function checkLocalHealth() {
  if (CLOUD_DEMO_MODE) {
    updateConnectionStatus(true, {
      cloud_registry: { status: "demo", label: "GitHub Pages Demo" },
      local_flask: false,
    });
    return true;
  }
  if (healthPromise) {
    return healthPromise;
  }
  healthPromise = (async () => {
    try {
      const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/health`));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (payload?.status !== "ok") throw new Error("health status is not ok");
      updateConnectionStatus(true, payload);
      return true;
    } catch (error) {
      updateConnectionStatus(false);
      return false;
    } finally {
      healthPromise = null;
    }
  })();
  return healthPromise;
}

async function checkQuantApiStatus() {
  if (CLOUD_DEMO_MODE) {
    updateQuantApiStatus({
      token_configured: false,
      base_url: "Supabase required",
    });
    return null;
  }
  try {
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/quant-api/status`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    updateQuantApiStatus(payload);
    return payload;
  } catch (error) {
    updateQuantApiStatus(null, true);
    return null;
  }
}

// Load the delivery's verdict per factor, so selection can stand on the eight
// frozen gates instead of on a reproducibility proof the delivery never produced.
async function loadDeliveryFactors() {
  if (!API_BASE) return;
  try {
    const response = await fetchWithTimeout(
      withCacheBust(`${API_BASE}/delivery/factors?limit=1000`)
    );
    if (!response.ok) return;
    const payload = await response.json();
    const map = {};
    for (const item of payload.items || []) {
      if (!item) continue;
      // Index by every id the library may use, so `WQ101:alpha7` finds the
      // delivery's `ALPHA101:alpha7` without matching on the suffix alone.
      for (const alias of item.library_aliases || [item.factor_id]) {
        if (alias) map[alias] = item;
      }
      if (item.factor_id) map[item.factor_id] = item;
    }
    state.deliveryFactors = map;
    state.deliverySummary = payload.summary || null;
    state.deliveryList = payload.items || [];
  } catch (error) {
    // No delivery available: admission falls back to the proof path alone.
    console.warn("交付因子清单不可用:", error);
  }
}

// 因子组合业绩是离线批算产物（scripts/build_factor_performance.py），一次算好、
// 请求时只读。拿不到时全部留空，不在前端伪造任何收益数字。
async function loadFactorPerformance() {
  if (!API_BASE) return;
  try {
    const response = await fetchWithTimeout(
      withCacheBust(`${API_BASE}/delivery/factor-performance`)
    );
    if (!response.ok) return;
    const payload = await response.json();
    const items = {};
    for (const row of payload.items || []) {
      if (row && row.factor_id) items[row.factor_id] = row;
    }
    state.factorPerformance = { items, meta: payload.meta || null };
  } catch (error) {
    console.warn("因子组合业绩不可用:", error);
  }
}

function factorPerformanceFor(item) {
  const ids = [item?.factor_id, ...(item?.library_aliases || [])].filter(Boolean);
  for (const id of ids) {
    const row = state.factorPerformance.items[id];
    if (row) return row;
  }
  return null;
}

function perfWindowLabel(factor) {
  if (!factor?.perf_window_start) return "";
  return `（窗口 ${factor.perf_window_start} ~ ${factor.perf_window_end || "—"}）`;
}

// The delivery is the client's factor set; the demo library is a different set
// (they overlap on ~125 ids). When a delivery is reachable the library is built
// from it, so every row a client sees carries real measured numbers.
function deliveryRowToFactor(item) {
  const id = String(item.factor_id || "");
  const [prefix, rawName] = id.includes(":") ? id.split(":", 2) : [id, id];
  const inPackage =
    item.in_delivery_package === true || item.in_delivery_package === "true";
  const perf = factorPerformanceFor(item);
  return {
    id,
    factor_name: item.name || id,
    display_name: item.name || id,
    raw_factor_name: rawName,
    library: prefix,
    factor_family: prefix.toLowerCase(),
    category: item.category || "",
    formula: item.formula || "",
    direction: item.direction || "",
    // The delivery ships no reproducibility proof, so this is reported as missing
    // rather than being dressed up as "passed". Selection stands on the delivery's
    // own verdict (see factorAdmission).
    proof_status: "missing",
    truth_status: "missing",
    // 交付证据里第一道门槛已经算过覆盖率，之前硬编码成 null，导致整列显示「-」。
    coverage_ratio: toFiniteNumber(item.coverage_ratio),
    rank_ic_mean: toFiniteNumber(item.rank_ic_mean_10d),
    rank_ic_ir: toFiniteNumber(item.rank_ic_ir_10d),
    long_short_mean: null,
    // "rqdata" keeps every delivery row in the A-share bucket.
    data_source: "rqdata",
    source: "交付包",
    delivery_status: item.status || null,
    delivery_in_package: inPackage,
    delivery_tier: item.tier || "",
    delivery_failed_gates: item.failed_gates || [],
    // 服务端算好的综合表现分与排名：IC_IR、残差 IC_IR、扣费后年化 三项百分位的平均。
    // 单看任何一列都会误导——残差 IC_IR 与净年化的相关性约为零。
    composite_score: toFiniteNumber(item.composite_score),
    composite_rank: toFiniteNumber(item.composite_rank),
    net_annualized: toFiniteNumber(item.net_annualized),
    max_drawdown: toFiniteNumber(item.max_drawdown),
    residual_ic_ir: toFiniteNumber(item.residual_ic_ir),
    // 因子组合业绩（预计算）。多头 = 可投资口径；研究多空 = Q5−Q1 毛收益，
    // A 股不能普遍做空，只用于比较因子纯度，不当作可交易收益。
    perf_long_annualized: toFiniteNumber(perf?.long_annualized_return),
    perf_long_excess_annualized: toFiniteNumber(perf?.long_excess_annualized),
    perf_long_sharpe: toFiniteNumber(perf?.long_sharpe),
    perf_long_max_drawdown: toFiniteNumber(perf?.long_max_drawdown),
    perf_last_1m_return: toFiniteNumber(perf?.long_last_1m_return),
    perf_last_3m_return: toFiniteNumber(perf?.long_last_3m_return),
    // 研究多空是 Top20% 篮子减 Bottom20% 篮子的毛收益；A 股不能普遍做空，
    // 只用于因子纯度比较。research_short_* 是底部篮子自己的多头收益，不当作空头 P&L。
    perf_research_spread_annualized: toFiniteNumber(perf?.research_spread_annualized),
    perf_research_short_annualized: toFiniteNumber(perf?.research_short_annualized_return),
    perf_window_start: perf?.window_start || null,
    perf_window_end: perf?.window_end || null,
    latest_checked_at: null,
  };
}

async function loadData() {
  if (state.isLoading) {
    return;
  }
  state.isLoading = true;
  updateRefreshButton(true);
  try {
    if (USE_SUPABASE_DASHBOARD) {
      const payload = await fetchSupabaseDashboardPayload();
      const normalizedPayload = normalizePayload(payload);
      state.rawFactors = normalizedPayload.factors || [];
      updateConnectionStatus(true, payload);
      updateQuantApiStatus({
        token_configured: false,
        base_url: "Supabase public dashboard",
      });
      els.errorPanel.classList.add("hidden");
      renderTabs(normalizedPayload);
      applyFilters();
      await syncDetailFromHash();
      if (state.view === "monitor") renderMonitor();
      if (isQuantDeskView()) renderQuantDesk();
      if (state.view === "strategy-detail") renderStrategyDetail();
      if (state.view === "tasks") renderTasks();
      return;
    }
    if (CLOUD_DEMO_MODE) {
      throw new Error("Supabase is required. Local fallback files have been removed.");
    }
    const healthy = await checkLocalHealth();
    if (!healthy) throw new Error("Local Flask service is offline");
    await checkQuantApiStatus();
    await loadDeliveryFactors();
    await loadFactorPerformance();
    await loadFitFactors();
    await loadFreshness();
    let payload;
    if (state.deliveryList.length) {
      // The delivered factor set is the client's library.
      payload = {
        factors: state.deliveryList.map(deliveryRowToFactor),
        source: "delivery",
      };
      state.librarySource = "delivery";
    document.body.dataset.librarySource = "delivery";
    } else {
      const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/factor-library`));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      payload = await response.json();
      state.librarySource = "api";
    document.body.dataset.librarySource = "api";
    }
    const normalizedPayload = normalizePayload(payload);
    state.rawFactors = normalizedPayload.factors || [];
    updateConnectionStatus(true, payload);
    els.errorPanel.classList.add("hidden");
    renderTabs(normalizedPayload);
    applyFilters();
    await syncDetailFromHash();
    loadStrategies();
    loadStrategyTemplates();
    if (state.view === "monitor") renderMonitor();
    if (isQuantDeskView()) renderQuantDesk();
    if (state.view === "strategy-detail") renderStrategyDetail();
    if (state.view === "tasks") renderTasks();
  } catch (error) {
    updateConnectionStatus(false);
    updateQuantApiStatus(null, true);
    els.errorPanel.classList.remove("hidden");
    state.rawFactors = [];
    state.filteredFactors = [];
    renderTabs({ categories: {}, libraries: {}, factors: [] });
    renderTable();
    if (state.view === "monitor") renderMonitor();
    if (isQuantDeskView()) renderQuantDesk();
    if (state.view === "strategy-detail") renderStrategyDetail();
    if (state.view === "tasks") renderTasks();
  } finally {
    state.isLoading = false;
    updateRefreshButton(false);
  }
}

function startAutoRefresh() {
  if (state.autoRefreshTimer) {
    window.clearInterval(state.autoRefreshTimer);
  }
  state.autoRefreshTimer = window.setInterval(loadData, AUTO_REFRESH_INTERVAL_MS);
}

function normalizePayload(payload) {
  const factors = removeEmptyQuantApiPlaceholders(payload.factors || []);
  const hasAlpha101 = factors.some((factor) => factor.library === "Alpha101");
  if (!hasAlpha101) {
    return {
      ...payload,
      factors,
      categories: countJqCategories(factors),
      libraries: countBy(factors, "library"),
    };
  }

  const normalizedFactors = factors
    .filter((factor) => factor.library !== "WQ101")
    .map((factor) => {
      if (factor.library !== "Alpha101") return factor;
      return {
        ...factor,
        library: "WQ101",
        id: `WQ101:${factor.raw_factor_name || factor.factor_name}`,
      };
    });

  return {
    ...payload,
    factors: normalizedFactors,
    categories: countJqCategories(normalizedFactors),
    libraries: countBy(normalizedFactors, "library"),
  };
}

function removeEmptyQuantApiPlaceholders(factors) {
  return factors.filter((factor) => {
    const library = String(factor.library || factor.raw_library || "").toLowerCase().replace(/\s+/g, "");
    const isQuantApi = library === "quantapi" || library === "quantapi33";
    if (!isQuantApi) return true;
    const hasMetric =
      toFiniteNumber(factor.coverage_ratio) !== null ||
      toFiniteNumber(factor.rank_ic_mean) !== null ||
      toFiniteNumber(factor.rank_ic_ir) !== null ||
      toFiniteNumber(factor.long_short_mean) !== null;
    const hasArtifact = Boolean(factor.latest_job_id || factor.latest_checked_at);
    return hasMetric || hasArtifact;
  });
}

function countBy(items, key, initial = {}) {
  return items.reduce(
    (counts, item) => {
      const value = item[key];
      counts[value] = (counts[value] || 0) + 1;
      return counts;
    },
    { ...initial },
  );
}

function marketBucket(factor) {
  const raw = [
    factor.market,
    factor.universe,
    factor.data_source,
    factor.source,
    factor.source_id,
    factor.raw_library,
    factor.library,
    factor.metadata?.market,
    factor.metadata?.universe,
    factor.metadata?.mining_run,
    factor.metadata?.official_source,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (!raw.trim()) return "other";
  if (
    raw.includes("wq101") ||
    raw.includes("alpha101") ||
    raw.includes("alpha158") ||
    raw.includes("worldquant") ||
    raw.includes("gtja191") ||
    raw.includes("alpha191") ||
    raw.includes("ashare") ||
    raw.includes("a-share") ||
    raw.includes("quant api") ||
    raw.includes("quantapi") ||
    raw.includes("rqdata") ||
    raw.includes("沪深") ||
    raw.includes("中证") ||
    raw.includes("聚宽")
  ) {
    return "ashare";
  }
  if (
    raw.includes("yfinance") ||
    raw.includes("yahoo") ||
    raw.includes("us_") ||
    raw.includes(" us ") ||
    raw.includes("nyse") ||
    raw.includes("nasdaq")
  ) {
    return "us";
  }
  if (raw.includes("static_demo") || raw.includes("demo")) return "ashare";
  return "other";
}

function marketCounts(factors = state.rawFactors) {
  const counts = Object.fromEntries(MARKET_BUCKETS.map((bucket) => [bucket.key, 0]));
  factors.forEach((factor) => {
    counts[marketBucket(factor)] = (counts[marketBucket(factor)] || 0) + 1;
  });
  return counts;
}

function firstAvailableMarket(counts) {
  return MARKET_BUCKETS.find((bucket) => (counts[bucket.key] || 0) > 0)?.key || "other";
}

function ensureMarketSelections(factors = state.rawFactors) {
  const counts = marketCounts(factors);
  if (!counts[state.market]) state.market = firstAvailableMarket(counts);
  if (!counts[state.monitorMarket]) state.monitorMarket = state.market;
}

function marketLabel(factorOrKey) {
  const key = typeof factorOrKey === "string" ? factorOrKey : marketBucket(factorOrKey);
  return MARKET_LABEL_BY_KEY[key] || "其他";
}

function marketDetail(factor) {
  if (factor.metadata?.truth_summary_source) return "";
  return factor.universe || factor.metadata?.universe || factor.data_source || factor.source || "-";
}

function marketChipHtml(factor) {
  const key = marketBucket(factor);
  return `
    <span class="market-chip market-${key}" title="${escapeHtml(marketDetail(factor))}">
      ${escapeHtml(marketLabel(key))}
    </span>
  `;
}

function renderMarketTabs() {
  const counts = marketCounts();
  const renderButton = (bucket, active, onClick) => {
    const count = counts[bucket.key] || 0;
    const button = document.createElement("button");
    button.type = "button";
    button.className = active ? "tab active" : "tab";
    button.textContent = `${bucket.label} (${count})`;
    button.title = bucket.hint;
    button.disabled = count === 0;
    if (!button.disabled) button.addEventListener("click", onClick);
    return button;
  };

  els.marketTabs?.replaceChildren();
  MARKET_BUCKETS.forEach((bucket) => {
    els.marketTabs?.appendChild(
      renderButton(bucket, state.market === bucket.key, () => {
        state.market = bucket.key;
        state.page = 1;
        applyFilters();
        renderMarketTabs();
      }),
    );
  });

  els.monitorMarketFilters?.replaceChildren();
  MARKET_BUCKETS.forEach((bucket) => {
    const button = renderButton(bucket, state.monitorMarket === bucket.key, () => {
      state.monitorMarket = bucket.key;
      renderMonitor();
      renderMarketTabs();
    });
    button.classList.add("market-filter");
    els.monitorMarketFilters?.appendChild(button);
  });
}

function countJqCategories(factors) {
  const counts = { 全部: factors.length };
  JQ_FACTOR_CATEGORIES.forEach((label) => {
    counts[label] = 0;
  });
  factors.forEach((factor) => {
    const category = jqFactorCategory(factor);
    counts[category] = (counts[category] || 0) + 1;
  });
  return counts;
}

function applyFilters() {
  const query = state.query.trim().toLowerCase();
  state.filteredFactors = state.rawFactors
    .filter((factor) => marketBucket(factor) === state.market)
    .filter((factor) => state.selectedCategories.has(jqFactorCategory(factor)))
    .filter((factor) => !state.usableOnly || factorAdmission(factor).agentReadable)
    .filter((factor) => state.library === "全部" || factor.library === state.library)
    .filter((factor) => state.proof === "all" || factor.proof_status === state.proof)
    .filter((factor) => state.truth === "all" || factor.truth_status === state.truth)
    .filter((factor) => state.reuse === "all" || reuseStatus(factor) === state.reuse)
    .filter((factor) => state.comparison === "all" || factorComparisonStatus(factor).key === state.comparison)
    .filter((factor) => {
      if (!query) return true;
      return [
        factor.factor_name,
        factor.raw_factor_name,
        factor.library,
        marketLabel(factor),
        marketDetail(factor),
        factor.subcategory,
        factor.category,
        taxonomySearchText(factor),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });

  if (state.sortKey && state.sortDirection !== "default") {
    state.filteredFactors.sort(compareFactors);
  } else {
    // 默认按综合表现降序：最好的排在最上面。综合分是 IC_IR、残差 IC_IR、扣费后年化
    // 三项百分位的平均（服务端计算）——单看任何一项都会误导，因为残差 IC_IR 与净年化
    // 的相关性约为零。缺任一指标的因子排在最后，不当作 0 参与打分。
    state.filteredFactors.sort(
      (left, right) => (right.composite_score ?? -1) - (left.composite_score ?? -1),
    );
  }
  const totalPages = Math.max(1, Math.ceil(state.filteredFactors.length / PAGE_SIZE));
  if (state.page > totalPages) state.page = totalPages;
  renderTable();
  renderSortHeaders();
  renderSelectionSummary();
}

function jqFactorCategory(factor) {
  return factorTaxonomy(factor).category;
}

// 综合表现前 10 名的徽标。名次来自服务端，是三项指标的百分位平均，不是单看某一列。
function topRankBadge(factor) {
  const rank = toFiniteNumber(factor?.composite_rank);
  if (rank === null || rank > 10) return "";
  return `<span class="rank-badge" title="综合表现第 ${rank} 名（IC_IR、残差 IC_IR、扣费后年化 三项排位平均）">TOP ${rank}</span>`;
}

function compareFactors(left, right) {
  const key = state.sortKey;
  const direction = state.sortDirection === "asc" ? 1 : -1;
  if (key === "factor_name") {
    return compareFactorNames(left.factor_name, right.factor_name) * direction;
  }
  const leftValue = left[key];
  const rightValue = right[key];
  if (typeof leftValue === "number" || typeof rightValue === "number") {
    return compareNullableNumbers(leftValue, rightValue) * direction;
  }
  return String(leftValue ?? "").localeCompare(String(rightValue ?? ""), "zh-CN") * direction;
}

function compareNullableNumbers(leftValue, rightValue) {
  const leftMissing = leftValue === null || leftValue === undefined || Number.isNaN(Number(leftValue));
  const rightMissing = rightValue === null || rightValue === undefined || Number.isNaN(Number(rightValue));
  if (leftMissing && rightMissing) return 0;
  if (leftMissing) return 1;
  if (rightMissing) return -1;
  return Number(leftValue) - Number(rightValue);
}

function cycleSort(key) {
  if (state.sortKey !== key || state.sortDirection === "default") {
    state.sortKey = key;
    state.sortDirection = "desc";
    return;
  }
  if (state.sortDirection === "desc") {
    state.sortDirection = "asc";
    return;
  }
  state.sortKey = null;
  state.sortDirection = "default";
}

function renderSortHeaders() {
  document.querySelectorAll("th.sortable").forEach((header) => {
    const active = state.sortKey === header.dataset.sort && state.sortDirection !== "default";
    header.classList.toggle("sort-desc", active && state.sortDirection === "desc");
    header.classList.toggle("sort-asc", active && state.sortDirection === "asc");
    header.classList.toggle("sort-default", !active);
    header.setAttribute(
      "aria-sort",
      active ? (state.sortDirection === "desc" ? "descending" : "ascending") : "none",
    );
  });
}

function cycleMonitorSort(key) {
  if (state.monitorSortKey !== key || state.monitorSortDirection === "default") {
    state.monitorSortKey = key;
    state.monitorSortDirection = "desc";
    return;
  }
  if (state.monitorSortDirection === "desc") {
    state.monitorSortDirection = "asc";
    return;
  }
  state.monitorSortKey = null;
  state.monitorSortDirection = "default";
}

function renderMonitorSortHeaders() {
  document.querySelectorAll("th.monitor-sortable").forEach((header) => {
    const active = state.monitorSortKey === header.dataset.monitorSort && state.monitorSortDirection !== "default";
    header.classList.toggle("sort-desc", active && state.monitorSortDirection === "desc");
    header.classList.toggle("sort-asc", active && state.monitorSortDirection === "asc");
    header.classList.toggle("sort-default", !active);
    header.setAttribute(
      "aria-sort",
      active ? (state.monitorSortDirection === "desc" ? "descending" : "ascending") : "none",
    );
  });
}

function cycleStrategySort(key) {
  if (state.strategySortKey !== key || state.strategySortDirection === "default") {
    state.strategySortKey = key;
    state.strategySortDirection = "desc";
    return;
  }
  if (state.strategySortDirection === "desc") {
    state.strategySortDirection = "asc";
    return;
  }
  state.strategySortKey = null;
  state.strategySortDirection = "default";
}

function renderStrategySortHeaders() {
  document.querySelectorAll("th.strategy-sortable").forEach((header) => {
    const active = state.strategySortKey === header.dataset.strategySort && state.strategySortDirection !== "default";
    header.classList.toggle("sort-desc", active && state.strategySortDirection === "desc");
    header.classList.toggle("sort-asc", active && state.strategySortDirection === "asc");
    header.classList.toggle("sort-default", !active);
    header.setAttribute(
      "aria-sort",
      active ? (state.strategySortDirection === "desc" ? "descending" : "ascending") : "none",
    );
  });
}

function compareFactorNames(leftName, rightName) {
  const left = factorNameParts(leftName);
  const right = factorNameParts(rightName);
  const prefixCompare = left.prefix.localeCompare(right.prefix, "zh-CN");
  if (prefixCompare !== 0) return prefixCompare;
  if (left.number !== null && right.number !== null) return left.number - right.number;
  if (left.number !== null) return -1;
  if (right.number !== null) return 1;
  return String(leftName ?? "").localeCompare(String(rightName ?? ""), "zh-CN");
}

function factorNameParts(name) {
  const value = String(name ?? "");
  const match = value.match(/^(.*?)(\d+)$/);
  if (!match) return { prefix: value, number: null };
  return { prefix: match[1], number: Number(match[2]) };
}

function beginDragSelection(event, factor, row, checkbox) {
  if (event.button !== 0) {
    return;
  }
  if (!factorAdmission(factor).selectable) {
    return;
  }
  if (event.target.closest(".factor-link")) {
    return;
  }

  event.preventDefault();
  document.body.classList.add("drag-selecting");
  state.dragSelect.active = true;
  state.dragSelect.targetChecked = !state.selectedIds.has(factor.id);
  state.dragSelect.touched = new Set();
  applyDragSelection(factor, row, checkbox);
}

function applyDragSelection(factor, row, checkbox) {
  if (!state.dragSelect.active || state.dragSelect.touched.has(factor.id)) {
    return;
  }

  state.dragSelect.touched.add(factor.id);
  if (state.dragSelect.targetChecked) {
    state.selectedIds.add(factor.id);
  } else {
    state.selectedIds.delete(factor.id);
  }

  checkbox.checked = state.selectedIds.has(factor.id);
  row.classList.toggle("selected", checkbox.checked);
  renderSelectionSummary();
}

function endDragSelection() {
  if (!state.dragSelect.active) {
    return;
  }
  state.dragSelect.active = false;
  state.dragSelect.touched.clear();
  document.body.classList.remove("drag-selecting");
}

function renderTable() {
  els.tableBody.replaceChildren();
  const start = (state.page - 1) * PAGE_SIZE;
  const pageItems = state.filteredFactors.slice(start, start + PAGE_SIZE);

  if (!pageItems.length) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    row.innerHTML = `
      <td colspan="20" class="empty-cell">
        <div class="empty-state">
          <strong>当前筛选条件下没有因子。</strong>
          <span>请调整市场、分类、验证状态或搜索条件。数据来自平台交付库。</span>
        </div>
      </td>
    `;
    els.tableBody.appendChild(row);
    els.pageSummary.textContent = `显示 0-0 / 共 0 个因子`;
    renderPagination();
    return;
  }

  pageItems.forEach((factor) => {
    const [proofText, proofClass] = proofBadge(factor.proof_status);
    const openable = canOpenFactor(factor);
    const admission = factorAdmission(factor);
    const displayName = compactName(factor.factor_name);
    const coverageTone = coverageClass(factor.coverage_ratio);
    const coverageHelp = coverageTitle(factor.coverage_ratio);
    const row = document.createElement("tr");
    row.className = [
      state.selectedIds.has(factor.id) ? "selected" : "",
      openable ? "openable" : "not-openable",
      admission.inLibrary ? "admitted" : "not-admitted",
      admission.weak ? "weak-alpha" : "",
    ]
      .filter(Boolean)
      .join(" ");
    row.innerHTML = `
      <td>
        <input type="checkbox" ${state.selectedIds.has(factor.id) ? "checked" : ""} ${admission.selectable ? "" : "disabled"} aria-label="选择 ${escapeHtml(factor.factor_name)}" />
      </td>
      <td>
        <button class="factor-link" type="button" data-factor-id="${escapeHtml(factor.id)}" ${openable ? "" : "disabled"} title="${escapeHtml(factor.factor_name)} · ${openable ? "查看单因子详情" : "未复现，暂无详情报告"}">
          ${topRankBadge(factor)}${escapeHtml(displayName)}${admission.weak ? '<span class="weak-tag">弱</span>' : ""}
        </button>
      </td>
      <td>${escapeHtml(factor.library)}</td>
      <td>${marketChipHtml(factor)}</td>
      <td>${factor.metadata?.truth_summary_source ? '<span class="taxonomy-main">真值库</span>' : taxonomyCellHtml(factor)}</td>
      <td>${factor.metadata?.truth_summary_source ? mutedDash("真值汇总行不参与分类") : taxonomySubfactorHtml(factor)}</td>
      <td>${factor.metadata?.truth_summary_source ? mutedDash("真值汇总行无方向") : taxonomyDirectionHtml(factor)}</td>
      <td class="legacy-cell">${factorComparisonBadgeHtml(factor)}</td>
      <td class="legacy-cell"><span class="badge ${proofClass}">${proofText}</span></td>
      <td class="legacy-cell">${truthBadgeHtml(factor)}</td>
      <td class="number ${coverageTone}" title="${escapeHtml(coverageHelp)}">${formatRatio(factor.coverage_ratio)}</td>
      <td class="number">${factorMetricHtml(factor, "rank_ic_mean", (value) => formatNumber(value, 4))}</td>
      <td class="number">${factorMetricHtml(factor, "rank_ic_ir", (value) => formatNumber(value, 4))}</td>
      <td class="number" title="${escapeHtml("多头展示组合（TopN 等权）年化收益；可投资口径，含市场 beta" + perfWindowLabel(factor))}">${formatPercent(factor.perf_long_annualized)}</td>
      <td class="number" title="${escapeHtml("多头展示组合相对全市场等权基准的年化超额" + perfWindowLabel(factor))}">${formatPercent(factor.perf_long_excess_annualized)}</td>
      <td class="number" title="${escapeHtml("多头展示组合最近 1 个月收益" + perfWindowLabel(factor))}">${formatPercent(factor.perf_last_1m_return)}</td>
      <td class="number perf-research" title="研究口径多空（Top20% − Bottom20%）毛收益；A 股不能直接做空，仅用于比较因子纯度">${formatPercent(factor.perf_research_spread_annualized)}</td>
      <td class="number legacy-only" title="${escapeHtml(LONG_SHORT_MEAN_HELP)}">${factorMetricHtml(factor, "long_short_mean", (value) => formatNumber(value, 4))}</td>
      <td class="legacy-only">${formatDate(factor.latest_checked_at)}</td>
      <td class="legacy-only"><span class="recommendation ${recommendationClass(factor.reuse_recommendation)}">${escapeHtml(factor.reuse_recommendation)}</span></td>
    `;
    applyTableLabels(row, FACTOR_TABLE_LABELS);
    const checkbox = row.querySelector("input");
    checkbox.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
      beginDragSelection(event, factor, row, checkbox);
    });
    checkbox.addEventListener("click", (event) => event.stopPropagation());
    checkbox.addEventListener("change", (event) => {
      if (!admission.selectable) return;
      if (event.target.checked) {
        state.selectedIds.add(factor.id);
      } else {
        state.selectedIds.delete(factor.id);
      }
      renderTable();
      renderSelectionSummary();
    });
    row.addEventListener("pointerdown", (event) => beginDragSelection(event, factor, row, checkbox));
    row.addEventListener("pointerenter", () => applyDragSelection(factor, row, checkbox));
    row.querySelector(".factor-link").addEventListener("click", () => {
      if (openable) openDetail(factor.id);
    });
    row.addEventListener("dblclick", () => {
      if (openable) openDetail(factor.id);
    });
    els.tableBody.appendChild(row);
  });

  const end = Math.min(start + pageItems.length, state.filteredFactors.length);
  els.pageSummary.textContent = `显示 ${state.filteredFactors.length ? start + 1 : 0}-${end} / 共 ${state.filteredFactors.length} 个因子`;
  renderPagination();
}

function renderPagination() {
  els.pagination.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(state.filteredFactors.length / PAGE_SIZE));
  const pages = paginationItems(state.page, totalPages);
  const pageButtons = [
    { label: "‹", page: Math.max(1, state.page - 1), disabled: state.page === 1 },
    ...pages,
    { label: "›", page: Math.min(totalPages, state.page + 1), disabled: state.page === totalPages },
  ];

  pageButtons.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = item.page === state.page && /^\d+$/.test(item.label) ? "page-button active" : "page-button";
    button.textContent = item.label;
    button.disabled = item.disabled || item.ellipsis;
    button.addEventListener("click", () => {
      if (item.ellipsis || item.disabled) return;
      state.page = item.page;
      renderTable();
    });
    els.pagination.appendChild(button);
  });
}

function paginationItems(currentPage, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => {
      const page = index + 1;
      return { label: String(page), page };
    });
  }

  const pages = new Set([1, totalPages, currentPage, currentPage - 1, currentPage + 1]);
  if (currentPage <= 4) {
    [2, 3, 4, 5].forEach((page) => pages.add(page));
  }
  if (currentPage >= totalPages - 3) {
    [totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1].forEach((page) => pages.add(page));
  }

  const sorted = [...pages].filter((page) => page >= 1 && page <= totalPages).sort((a, b) => a - b);
  const items = [];
  sorted.forEach((page, index) => {
    const previous = sorted[index - 1];
    if (index > 0 && page - previous > 1) {
      items.push({ label: "...", page: previous + 1, ellipsis: true });
    }
    items.push({ label: String(page), page });
  });
  return items;
}

function renderSelectionSummary() {
  if (ENABLE_AGENT_TASK_DEBUG && state.view === "agent_task") {
    renderAgentTaskSelectionSummary();
    return;
  }
  const selected = state.rawFactors.filter((factor) => state.selectedIds.has(factor.id));
  const reusable = selected.filter((factor) => reuseStatus(factor) === "reusable").length;
  const rerun = selected.filter((factor) => reuseStatus(factor) === "rerun").length;
  els.selectedCount.textContent = `已选择 ${selected.length} 个因子`;
  els.selectedReusable.textContent = `可复用 ${reusable} 个`;
  els.selectedRerun.textContent = `建议重跑 ${rerun} 个`;
  if (els.selectionActions) {
    els.selectionActions.innerHTML = `
      <button type="button" class="primary-action compact" id="generateStrategyDraft" ${selected.length ? "" : "disabled"}>生成策略</button>
    `;
    els.selectionActions.querySelector("#generateStrategyDraft")?.addEventListener("click", generateStrategyDraftFromSelection);
  }
}

function renderAgentTaskSelectionSummary() {
  const selected = state.agentTasks.filter((task) => state.selectedAgentTaskIds.has(task.task_id));
  els.selectedCount.textContent = `已选择 ${selected.length} 个任务`;
  els.selectedReusable.textContent = `任务总数 ${state.agentTasks.length} 个`;
  els.selectedRerun.textContent = "删除会移除 request.json、status.json 和 artifacts";
  if (!els.selectionActions) return;
  els.selectionActions.innerHTML = `
    <button type="button" class="secondary-action compact" id="clearAgentTaskSelection" ${selected.length ? "" : "disabled"}>清空选择</button>
    <button type="button" class="danger-action compact" id="deleteSelectedAgentTasks" ${selected.length ? "" : "disabled"}>删除所选</button>
  `;
  els.selectionActions.querySelector("#clearAgentTaskSelection")?.addEventListener("click", () => {
    state.selectedAgentTaskIds.clear();
    renderAgentTask();
  });
  els.selectionActions.querySelector("#deleteSelectedAgentTasks")?.addEventListener("click", deleteSelectedAgentTasks);
}

function selectedUsableFactors() {
  return state.rawFactors.filter((factor) => state.selectedIds.has(factor.id) && factorAdmission(factor).selectable);
}

function generateStrategyDraftFromSelection() {
  const factors = selectedUsableFactors();
  if (!factors.length) {
    showToast("请选择可用因子");
    return;
  }
  state.strategyBuilderFactors = factors;
  state.strategyBuilderWeights = {};
  factors.forEach((factor) => {
    state.strategyBuilderWeights[factor.id] = 1;
  });
  state.strategyBuilderName =
    factors.length === 1 ? `${factors[0].factor_name} 策略研究` : `多因子成品策略 ${state.strategyDrafts.length + 1}`;
  state.strategyBuilderResult = null;
  state.selectedStrategyTemplateId = state.selectedStrategyTemplateId || null;
  state.strategyBuilderParams = {
    top_n: "20",
    rebalance_every: "month_end",
    cost_round_trip: "0.003",
    weight_mode: "equal",
  };
  state.view = "strategy-builder";
  window.location.hash = "strategy-builder";
  loadStrategyTemplates();
  renderView();
  showToast("已进入策略构建页");
}

function monitorBucket(factor) {
  const ic = toFiniteNumber(factor.rank_ic_mean);
  const ir = toFiniteNumber(factor.rank_ic_ir);
  if (ic === null && ir === null) return "missing";
  // A delivered factor already passed the eight frozen gates, so a missing
  // *reproducibility proof* is not a reason to flag it for attention; classify it
  // on its measured IR like any other factor.
  const delivered = isDelivered(factor);
  if (
    !delivered &&
    (factor.proof_status === "failed" ||
      factor.proof_status === "missing" ||
      isTruthIssue(factor.truth_status))
  ) {
    return "weak";
  }
  const absIr = Math.abs(ir ?? 0);
  if (absIr >= 0.3) return "strong";
  if (absIr >= 0.1) return "medium";
  return "weak";
}

function monitorBucketLabel(bucket) {
  return {
    strong: "IR>0.3",
    medium: "IR 0.1-0.3",
    weak: "IR<0.1",
    // 这批因子算过、也被验证过，只是未通过门槛，所以交付包里没有它们的证据文件、
    // IC/IR 为空。原来的标签是「待数据」，读起来像「数据还没到」，会让人以为服务
    // 根本没算过这些因子——而实际恰恰相反，算过才会被拒。
    missing: "未通过门槛",
  }[bucket] || "全部";
}

function monitorHints(factor) {
  const rules = [
    {
      match: (item) => item.proof_status === "failed",
      text: "复现失败，建议重跑",
    },
    {
      match: (item) => item.proof_status === "missing",
      text: "缺少复现产物",
    },
    {
      match: (item) => toFiniteNumber(item.coverage_ratio) !== null && toFiniteNumber(item.coverage_ratio) < COVERAGE_DANGER_THRESHOLD,
      text: "覆盖率过低",
    },
    {
      match: (item) => item.proof_status === "partial",
      text: "真值待对照",
    },
    {
      match: (item) => Math.abs(toFiniteNumber(item.rank_ic_ir) ?? Infinity) < 0.05,
      text: "信号偏弱",
    },
  ];
  return rules.filter((rule) => rule.match(factor)).slice(0, 2).map((rule) => rule.text);
}

function monitorSortValue(factor) {
  const ir = toFiniteNumber(factor.rank_ic_ir);
  if (ir !== null) return Math.abs(ir);
  const ic = toFiniteNumber(factor.rank_ic_mean);
  if (ic !== null) return Math.abs(ic);
  return -1;
}

function monitorDirection(factor) {
  const ic = toFiniteNumber(factor.rank_ic_mean);
  if (ic === null || Math.abs(ic) < 0.0001) {
    return { label: "中性", symbol: "→", className: "neutral" };
  }
  return ic > 0
    ? { label: "正向", symbol: "↑", className: "positive" }
    : { label: "反向", symbol: "↓", className: "negative" };
}

function monitorIcBarHtml(factor, bucket) {
  const ic = toFiniteNumber(factor.rank_ic_mean);
  const width = ic === null ? 0 : Math.min(100, Math.max(4, Math.abs(ic) / 0.08 * 100));
  const tone = ic === null ? "missing" : bucket;
  return `
    <span class="ic-bar-track" title="IC均值 ${escapeHtml(formatNumber(ic, 4))}">
      <span class="ic-bar-fill ${tone}" style="width: ${width.toFixed(1)}%"></span>
    </span>
  `;
}

function monitorRecentIcHtml(factor) {
  const direction = monitorDirection(factor);
  const recent = toFiniteNumber(factor.long_short_mean);
  return `<span class="recent-ic ${direction.className}">${direction.symbol}</span> ${formatNumber(recent, 4)}`;
}

function monitorValidationHtml(factor) {
  const coverage = toFiniteNumber(factor.coverage_ratio);
  const ir = Math.abs(toFiniteNumber(factor.rank_ic_ir) ?? 0);
  // 这个数字是 IC_IR 映射到 30–99 的强度分，越大越好。它曾经与 REJECT 并排显示，
  // 看起来像「被拒绝 84 次」——实际上 84 是它表现好的证据。
  const score = Math.round(Math.min(99, Math.max(30, ir * 100)));
  if (factor.metadata?.truth_summary_source) {
    return `<span class="validation-badge review">TRUTH</span>`;
  }
  // 交付因子优先按交付结论显示。它们出自八道门槛验证，本来就不走旧的复现流水线，
  // 因此 proof_status / truth_status 恒为 missing——把 missing 当「拒绝」会让全部
  // 332 个已交付因子（包括排名第一的）都挂上 REJECT。
  const delivered = isDelivered(factor);
  if (delivered) {
    return `<span class="validation-badge safe" title="已通过八道门槛并进入交付包；${score} 为 IC_IR 强度分（越高越好）">已交付 ${score}</span>`;
  }
  if (factor.delivery_status === "rejected") {
    return `<span class="validation-badge reject" title="计算过，但至少一道门槛未通过，未进入交付包">未通过</span>`;
  }
  if (factor.proof_status === "failed" || isTruthIssue(factor.truth_status)) {
    return `<span class="validation-badge reject" title="复现校验未通过或真值缺失；${score} 为 IC_IR 强度分">待复核 ${score}</span>`;
  }
  if (factor.proof_status === "missing" || factor.proof_status === "partial" || (coverage !== null && coverage < COVERAGE_WARN_THRESHOLD)) {
    return `<span class="validation-badge review" title="${score} 为 IC_IR 强度分">REVIEW ${score}</span>`;
  }
  return `<span class="validation-badge safe">SAFE ${score}</span>`;
}

function monitorMarketHtml(factor) {
  const hints = monitorHints(factor);
  const hint = hints.includes("覆盖率过低") ? `<span class="hint-chip">覆盖率过低</span>` : "";
  return `
    <span class="market-cell">
      ${marketChipHtml(factor)}
      ${hint}
    </span>
  `;
}

function factorSourceDisplay(factor) {
  if (factor.metadata?.truth_summary_source) {
    const rowCount = formatInteger(factor.metadata.row_count);
    const symbolCount = formatInteger(factor.metadata.symbol_count);
    return {
      primary: `${factor.library || "Truth"} 真值库`,
      secondary: `${rowCount} 行 / ${symbolCount} 标的`,
    };
  }
  const officialSource = factor.metadata?.official_source || factor.source_document || factor.data_source || factor.library || "-";
  if (String(officialSource).includes("Quant API factor_monthly")) {
    return {
      primary: "Quant API",
      secondary: `factor_monthly · ${factor.subcategory || factor.category || "-"}`,
    };
  }
  return {
    primary: factor.library || officialSource,
    secondary: factor.subcategory || factor.category || officialSource || "-",
  };
}

function renderMonitorStats() {
  const currentFactors = state.rawFactors.filter((factor) => marketBucket(factor) === state.monitorMarket);
  const total = currentFactors.length;
  const withMetric = currentFactors.filter(
    (factor) => toFiniteNumber(factor.rank_ic_mean) !== null || toFiniteNumber(factor.rank_ic_ir) !== null,
  ).length;
  const reusable = currentFactors.filter((factor) => reuseStatus(factor) === "reusable").length;
  const review = currentFactors.filter((factor) => monitorBucket(factor) === "weak").length;

  const cards = [
    ["all", "总因子数", total, `${marketLabel(state.monitorMarket)} 当前分区`],
    ["metric", "有 IC/IR", withMetric, "同市场内可读研究指标"],
    ["reusable", "可复用", reusable, "同市场口径下的建议"],
    ["review", "需关注", review, "同市场内复现或指标风险"],
  ]
    .map(
      ([key, label, value, note]) => `
        <article class="monitor-stat-card clickable ${state.monitorCardFilter === key ? "active" : ""}" data-monitor-card="${key}">
          <span data-term="${label}">${label}</span>
          <strong>${value}</strong>
          <small>${note}</small>
        </article>
      `,
    )
    .join("");
  els.monitorStats.innerHTML = cards;
  els.monitorStats.querySelectorAll("[data-monitor-card]").forEach((card) => {
    card.addEventListener("click", () => {
      const key = card.dataset.monitorCard;
      state.monitorCardFilter = key === "all" || state.monitorCardFilter === key ? null : key;
      renderMonitor();
    });
  });
}

function renderMonitorFilters() {
  els.monitorFilters.forEach((button) => {
    button.classList.toggle("active", button.dataset.monitorFilter === state.monitorFilter);
  });
}

function renderMonitor() {
  ensureMarketSelections();
  renderMarketTabs();
  renderMonitorStats();
  renderMonitorFilters();
  renderMonitorCategoryFilters();
  renderMonitorDirectionFilters();
  renderMonitorComparisonFilters();
  const query = state.monitorQuery.trim().toLowerCase();
  const factors = state.rawFactors
    .map((factor) => ({ factor, bucket: monitorBucket(factor) }))
    .filter((item) => marketBucket(item.factor) === state.monitorMarket)
    .filter((item) => state.monitorSelectedCategories.has(jqFactorCategory(item.factor)))
    .filter((item) => state.monitorComparisonFilter === "all" || factorComparisonStatus(item.factor).key === state.monitorComparisonFilter)
    .filter((item) => {
      if (state.monitorDirectionFilter === "all") return true;
      const direction = factorTaxonomy(item.factor).direction < 0 ? "negative" : "positive";
      return direction === state.monitorDirectionFilter;
    })
    .filter((item) => state.monitorFilter === "all" || item.bucket === state.monitorFilter)
    .filter((item) => {
      if (!state.monitorCardFilter) return true;
      if (state.monitorCardFilter === "metric") {
        return toFiniteNumber(item.factor.rank_ic_mean) !== null || toFiniteNumber(item.factor.rank_ic_ir) !== null;
      }
      if (state.monitorCardFilter === "reusable") {
        return reuseStatus(item.factor) === "reusable";
      }
      if (state.monitorCardFilter === "review") {
        return item.bucket === "weak";
      }
      return true;
    })
    .filter((item) => {
      if (!query) return true;
      const factor = item.factor;
      return [
        factor.factor_name,
        factor.raw_factor_name,
        factor.library,
        marketLabel(factor),
        marketDetail(factor),
        factor.subcategory,
        factor.category,
        monitorBucketLabel(item.bucket),
        taxonomySearchText(factor),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    })
    .sort((a, b) => {
      if (state.monitorSortKey && state.monitorSortDirection !== "default") {
        return compareMonitorRows(a, b);
      }
      return (
        monitorSortValue(b.factor) - monitorSortValue(a.factor) ||
        String(a.factor.factor_name).localeCompare(String(b.factor.factor_name), "zh-Hans-CN", { numeric: true })
      );
    });
  renderMonitorSortHeaders();

  if (!factors.length) {
    els.monitorTableBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="13" class="empty-cell">
          <div class="empty-state">
            <strong>当前视图没有可显示的行。</strong>
            <span>请切换市场、分类、方向或 IR 分组。数据来自平台交付库。</span>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  if (!factors.length) {
    els.monitorTableBody.innerHTML = `
      <tr>
        <td colspan="14" class="empty-cell">当前筛选下没有可展示的因子。</td>
      </tr>
    `;
    return;
  }

  els.monitorTableBody.innerHTML = factors
    .map(({ factor, bucket }) => {
      const [proofText, proofClass] = proofBadge(factor.proof_status);
      const openable = canOpenFactor(factor);
      const name = compactName(factor.factor_name);
      const coverageTone = coverageClass(factor.coverage_ratio);
      const coverageHelp = coverageTitle(factor.coverage_ratio);
      const sourceDisplay = factorSourceDisplay(factor);
      return `
        <tr>
          <td><span class="monitor-dot ${bucket}"></span>${monitorBucketLabel(bucket)}</td>
          <td>
            <button
              type="button"
              class="factor-link"
              title="${escapeHtml(factor.factor_name)}"
              data-factor-id="${escapeHtml(factor.id)}"
              ${openable ? "" : "disabled"}
            >${escapeHtml(name)}</button>
          </td>
          <td>
            <strong>${escapeHtml(sourceDisplay.primary)}</strong>
            <span class="monitor-source-sub">${escapeHtml(sourceDisplay.secondary)}</span>
          </td>
          <td>${taxonomyCellHtml(factor)}${taxonomySubfactorHtml(factor)}</td>
          <td class="number">${formatNumber(factor.rank_ic_ir, 3)}</td>
          <td class="number">${formatNumber(factor.rank_ic_mean, 4)}</td>
          <td class="number ${coverageTone}" title="${escapeHtml(coverageHelp)}">${formatRatio(factor.coverage_ratio)}</td>
          <td class="number">${monitorRecentIcHtml(factor)}</td>
          <td>${monitorIcBarHtml(factor, bucket)}</td>
          <td>${taxonomyDirectionHtml(factor)}</td>
          <td class="legacy-cell">${factorComparisonBadgeHtml(factor)}</td>
          <td title="${escapeHtml(proofText)} / ${escapeHtml(factor.truth_status || "-")}">${monitorValidationHtml(factor)}</td>
          <td>${monitorMarketHtml(factor)}</td>
          <td class="monitor-strategy-ref-cell">${renderStrategyTraceChips(factor.id)}</td>
        </tr>
      `;
    })
    .join("");

  els.monitorTableBody.querySelectorAll("tr").forEach((row) => applyTableLabels(row, MONITOR_TABLE_LABELS));
  els.monitorTableBody.querySelectorAll("[data-factor-id]").forEach((button) => {
    button.addEventListener("click", () => openDetail(button.dataset.factorId));
  });
  bindStrategyTraceChips(els.monitorTableBody);
}

function compareMonitorRows(left, right) {
  const key = state.monitorSortKey;
  const direction = state.monitorSortDirection === "asc" ? 1 : -1;
  if (key === "bucket") {
    return (monitorSortValue(left.factor) - monitorSortValue(right.factor)) * direction;
  }
  if (key === "taxonomy") {
    return taxonomySearchText(left.factor).localeCompare(taxonomySearchText(right.factor), "zh-CN", { numeric: true }) * direction;
  }
  if (key === "comparison") {
    return factorComparisonStatus(left.factor).label.localeCompare(factorComparisonStatus(right.factor).label, "zh-CN") * direction;
  }
  const leftValue = left.factor[key];
  const rightValue = right.factor[key];
  if (typeof leftValue === "number" || typeof rightValue === "number") {
    return compareNullableNumbers(leftValue, rightValue) * direction;
  }
  return String(leftValue ?? "").localeCompare(String(rightValue ?? ""), "zh-CN", { numeric: true }) * direction;
}

function todayDate() {
  return new Date().toISOString().slice(0, 10);
}

function defaultStrategyTemplates() {
  const dateDefaults = {
    start_date: "2023-01-01",
    end_date: todayDate(),
    cutoff_date: "2025-01-01",
  };
  const baseParams = [
    {
      key: "universe",
      label: "股票池",
      type: "select",
      default: "沪深300",
      options: ["沪深300", "中证500", "中证800", "中证1000", "中证全指"],
    },
    { key: "start_date", label: "开始日期", type: "date", default: dateDefaults.start_date },
    { key: "end_date", label: "结束日期", type: "date", default: dateDefaults.end_date },
    { key: "cutoff_date", label: "临界日", type: "date", default: dateDefaults.cutoff_date },
  ];
  return [
    {
      template_id: "agent_equal_weight_long",
      name: "多因子等权多头",
      description: "封装好的多因子多头策略，只接收因子方向与外围研究参数。",
      source: "agent",
      required_factor_count: { min: 1, max: 30 },
      param_schema: baseParams,
    },
    {
      template_id: "agent_layered_long_short",
      name: "多因子分层多空",
      description: "封装好的分层多空策略，内部合成、分组和调仓规则不在前端暴露。",
      source: "agent",
      required_factor_count: { min: 2, max: 30 },
      param_schema: baseParams,
    },
    {
      template_id: "agent_ic_weighted_score",
      name: "IC加权打分策略",
      description: "由策略模板根据历史 IC 稳定性完成黑盒权重分配，前端只配置研究口径。",
      source: "agent",
      required_factor_count: { min: 1, max: 20 },
      param_schema: baseParams,
    },
  ];
}

function normalizeStrategyTemplate(template) {
  return {
    template_id: template.template_id || template.id || sanitizeId(template.name),
    name: template.name || "未命名成品策略",
    description: template.description || "后端注册的封装策略模板。",
    source: ["agent", "system"].includes(template.source) ? template.source : "agent",
    required_factor_count: template.required_factor_count || { min: 1, max: 99 },
    param_schema: Array.isArray(template.param_schema) && template.param_schema.length
      ? template.param_schema
      : defaultStrategyTemplates()[0].param_schema,
  };
}

async function loadStrategyTemplates() {
  if (state.strategyTemplatesLoaded || state.strategyTemplatesLoading) return;
  state.strategyTemplatesLoading = true;
  try {
    // AGENT-HOOK: Agent 挖掘出的成品策略应注册到此清单接口，前端只按模板声明动态渲染。
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/strategy-templates`));
    if (!response.ok) throw new Error(`strategy-templates ${response.status}`);
    const payload = await response.json();
    const templates = Array.isArray(payload) ? payload : payload.templates || payload.items || [];
    state.strategyTemplates = templates.map(normalizeStrategyTemplate);
  } catch (error) {
    state.strategyTemplates = defaultStrategyTemplates();
  } finally {
    state.strategyTemplatesLoaded = true;
    state.strategyTemplatesLoading = false;
    if (!state.selectedStrategyTemplateId && state.strategyTemplates[0]) {
      state.selectedStrategyTemplateId = state.strategyTemplates[0].template_id;
      seedStrategyBuilderParams(state.strategyTemplates[0]);
    }
    if (state.view === "strategy-builder") renderStrategyBuilder();
  }
}

function activeStrategyTemplate() {
  return state.strategyTemplates.find((template) => template.template_id === state.selectedStrategyTemplateId) || state.strategyTemplates[0] || null;
}

function loadSavedStrategies() {
  try {
    const saved = localStorage.getItem("factor_lab_strategies");
    return saved ? JSON.parse(saved) : [];
  } catch {
    return [];
  }
}

function saveStrategies() {
  try {
    localStorage.setItem("factor_lab_strategies", JSON.stringify(state.strategyDrafts));
  } catch {
    console.error("Failed to save strategies to localStorage");
  }
}

async function loadStrategies() {
  if (state.strategiesLoading) return;
  state.strategiesLoading = true;
  try {
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/strategies`));
    if (!response.ok) throw new Error(`strategies ${response.status}`);
    const payload = await response.json();
    state.strategies = payload.items || [];
  } catch (error) {
    state.strategies = [];
  } finally {
    state.strategiesLoading = false;
    state.strategiesLoaded = true;
    if (state.view === "strategy" || state.view === "strategy-board") renderStrategy();
    if (state.view === "monitor") renderMonitor();
    if (isQuantDeskView()) renderQuantDesk();
  }
}

function seedStrategyBuilderParams(template) {
  (template?.param_schema || []).forEach((field) => {
    if (state.strategyBuilderParams[field.key] === undefined) {
      state.strategyBuilderParams[field.key] = field.default ?? field.options?.[0] ?? "";
    }
  });
  // 拟合引擎参数与"成品策略模板"的外围参数分开：这些是策略层的执行口径，
  // 模板不提供时也要有默认值，否则保存的策略没有可复现的调仓/成本说明。
  const engineDefaults = {
    top_n: "20",
    rebalance_every: "month_end",
    cost_round_trip: "0.003",
    weight_mode: "equal",
  };
  Object.entries(engineDefaults).forEach(([key, value]) => {
    if (state.strategyBuilderParams[key] === undefined) state.strategyBuilderParams[key] = value;
  });
}

function factorDirectionValue(factor) {
  return factorTaxonomy(factor).direction < 0 ? -1 : 1;
}

function requiredFactorLabel(required) {
  if (typeof required === "number") return `${required} 个`;
  if (required?.min !== undefined && required?.max !== undefined) return `${required.min}-${required.max} 个`;
  if (required?.min !== undefined) return `至少 ${required.min} 个`;
  return "-";
}

function renderParamField(field) {
  const value = state.strategyBuilderParams[field.key] ?? field.default ?? field.options?.[0] ?? "";
  if (field.type === "select") {
    return `
      <label class="builder-param">
        <span>${escapeHtml(field.label || field.key)}</span>
        <select data-builder-param="${escapeHtml(field.key)}">
          ${(field.options || []).map((option) => `<option value="${escapeHtml(option)}" ${option === value ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}
        </select>
      </label>
    `;
  }
  return `
    <label class="builder-param">
      <span>${escapeHtml(field.label || field.key)}</span>
      <input data-builder-param="${escapeHtml(field.key)}" type="${field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}" value="${escapeHtml(value)}" />
    </label>
  `;
}

// 保存策略时只需要一条可读的净值曲线，不需要 1600 个日频点：按月取样，
// 不做平滑/插值，最后一点单独补上（否则最后一个月会丢）。
function compactEquityCurve(fit, cutoffDate) {
  const nav = Array.isArray(fit?.nav) ? fit.nav : [];
  const dates = Array.isArray(fit?.dates) ? fit.dates : [];
  if (nav.length < 2 || dates.length !== nav.length) return [];
  const points = [];
  let lastMonth = "";
  for (let index = 0; index < nav.length; index += 1) {
    const month = String(dates[index]).slice(0, 7);
    if (month !== lastMonth || index === nav.length - 1) {
      points.push({
        date: dates[index],
        nav: Number(nav[index]),
        phase: cutoffDate && dates[index] <= cutoffDate ? "backtest" : "live",
      });
      lastMonth = month;
    }
  }
  return points;
}

function fitBacktestResult(fit, params) {
  if (!fit || !fit.ok) return null;
  const metrics = fit.metrics || {};
  const window = fit.window || {};
  return {
    annual_return: metrics.annualized_return ?? null,
    sharpe: metrics.sharpe ?? null,
    max_drawdown: metrics.max_drawdown ?? null,
    total_return: metrics.total_return ?? null,
    volatility: metrics.volatility ?? null,
    window,
    top_n: fit.top_n ?? params.top_n ?? null,
    method: fit.method || null,
    weights: fit.weights || null,
    mean_turnover: fit.mean_turnover ?? null,
    metrics_detail: metrics,
    benchmark_metrics: fit.benchmark_metrics || null,
    equity_curve: compactEquityCurve(fit, params.cutoff_date),
  };
}

function strategyRunPayload(lifecycle = "草稿") {
  const template = activeStrategyTemplate();
  const createdAt = new Date().toISOString();
  const fitBacktest = fitBacktestResult(state.fitResult, state.strategyBuilderParams);
  // AGENT-HOOK: 运行/保存策略的人机共用契约；Agent 后续直接提交同格式 payload，并通过 source 区分来源。
  return {
    strategy_id: `strategy_run_${Date.now()}`,
    name: state.strategyBuilderName || "未命名策略",
    source: "human",
    template_id: template?.template_id || "",
    factors: state.strategyBuilderFactors.map((factor) => ({
      factor_id: factor.id || factor.factor_id || factor.factor_name,
      direction: factorDirectionValue(factor),
    })),
    params: { ...state.strategyBuilderParams },
    lifecycle,
    backtest_result: fitBacktest || state.strategyBuilderResult?.backtest_result || null,
    live_result: state.strategyBuilderResult?.live_result || null,
    created_at: createdAt,
  };
}

// A failed strategy run must stay failed. There used to be a `mockStrategyRunResult()`
// here that invented an annual return, Sharpe, drawdown and win rate from the *number of
// selected factors* and rendered them as if they were backtested numbers. It fired on
// every GitHub Pages visit, because `API_BASE === ""` there makes the POST 404. A panel
// whose whole purpose is trustworthy factor evidence must not show a plausible-looking
// curve it never computed, so the fabrication is gone: the failure is now visible.
//
// `url` is the endpoint that actually failed. This used to be a hardcoded
// `${API_BASE}/strategy-run`, so a timed-out *fit* was reported as a failed strategy-run
// request and sent anyone debugging it to the wrong place.
function strategyRunFailure(payload, error, url) {
  const aborted = error && (error.name === "AbortError" || /abort/i.test(String(error.message || "")));
  return {
    __error: true,
    message: aborted
      ? `请求超时：服务器在 ${Math.round((payload.__timeoutMs || REQUEST_TIMEOUT_MS) / 1000)} 秒内没有返回`
      : String((error && error.message) || error || "请求失败"),
    backend: url || (API_BASE ? `${API_BASE}/strategy-run` : "(未配置后端地址)"),
    cutoff_date: payload.params ? payload.params.cutoff_date : undefined,
  };
}

async function loadFitFactors() {
  if (!API_BASE) return;
  try {
    const response = await fetchWithTimeout(
      withCacheBust(`${API_BASE}/delivery/fit/factors`)
    );
    state.fitMeta = response.ok ? await response.json() : { available: false };
  } catch (error) {
    state.fitMeta = { available: false, error: String(error) };
  }
}

// 自定义权重：归一化到合计 1；没有正权重就拒绝运行，不能悄悄退回等权。
function normalizedCustomWeights(factorIds) {
  const raw = factorIds.map((id) => {
    const value = Number(state.strategyBuilderWeights[id]);
    return Number.isFinite(value) && value > 0 ? value : 0;
  });
  const total = raw.reduce((sum, value) => sum + value, 0);
  if (!(total > 0)) return null;
  const weights = {};
  factorIds.forEach((id, index) => {
    weights[id] = raw[index] / total;
  });
  return weights;
}

// Fit through the real engine: precomputed rank scores -> weighted combination ->
// month-end rebalance -> NAV. Never fabricates a curve.
async function runDeliveryFit(factorIds, params) {
  // Default to the frozen out-of-sample window. Reporting a curve that silently
  // mixes in-sample and out-of-sample days would overstate the result.
  const oosStart = state.fitMeta && state.fitMeta.oos_start;
  const start = params.start_date || oosStart || undefined;
  const weightMode = params.weight_mode === "custom" ? "custom" : "equal";
  const weights = weightMode === "custom" ? normalizedCustomWeights(factorIds) : null;
  if (weightMode === "custom" && !weights) {
    throw new Error("自定义权重至少需要一个大于 0 的权重");
  }
  const rebalanceRaw = params.rebalance_every;
  const rebalanceEvery = rebalanceRaw && rebalanceRaw !== "month_end" ? Number(rebalanceRaw) : undefined;
  const url = `${API_BASE}/delivery/fit`;
  const response = await fetchWithTimeout(url, {
    timeoutMs: FIT_TIMEOUT_MS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      factor_ids: factorIds,
      method: weightMode,
      weights: weights || undefined,
      top_n: Number(params.top_n) || 20,
      start,
      end: params.end_date || undefined,
      cost_round_trip: Number(params.cost_round_trip ?? 0.003),
      rebalance_every: rebalanceEvery,
    }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.reason || `HTTP ${response.status}`);
  }
  payload.__url = url;
  payload.window_defaulted_to_oos = !params.start_date && Boolean(oosStart);
  // Parameters the fit engine does not act on are named rather than silently ignored:
  // a client who set 股票池=沪深300 would otherwise believe the curve was CSI300-only.
  payload.ignored_params = [];
  if (params.universe) {
    payload.ignored_params.push({
      key: "股票池",
      value: params.universe,
      note: "本次拟合在分数矩阵覆盖的全 A 面板上运行，未按股票池过滤",
    });
  }
  if (params.cutoff_date) {
    payload.ignored_params.push({
      key: "临界日",
      value: params.cutoff_date,
      note: "切分点取自冻结配置 configs/validation_gates.yaml，未使用该数值",
    });
  }
  return payload;
}

async function runStrategyBuilder() {
  if (!activeStrategyTemplate()) {
    showToast("请选择成品策略");
    return;
  }
  const payload = strategyRunPayload("回测中");
  const fittable = new Set((state.fitMeta && state.fitMeta.factors) || []);
  const selectedFittable = state.strategyBuilderFactors
    .map((factor) => factor.id)
    .filter((id) => fittable.has(id));

  if (state.fitMeta && state.fitMeta.available && selectedFittable.length) {
    state.strategyBuilderRunning = true;
    state.fitResult = null;
    state.strategyBuilderResult = null;
    renderStrategyBuilder();
    try {
      const result = await runDeliveryFit(selectedFittable, state.strategyBuilderParams || {});
      state.fitResult = {
        ...result,
        requested: state.strategyBuilderFactors.map((f) => f.id),
        used: selectedFittable,
        skipped: state.strategyBuilderFactors
          .map((f) => f.id)
          .filter((id) => !fittable.has(id)),
      };
      state.strategyBuilderResult = null;
      showToast(`拟合完成：使用 ${selectedFittable.length} 个因子`);
    } catch (error) {
      state.fitResult = null;
      const payload = strategyRunPayload("拟合失败");
      payload.__timeoutMs = FIT_TIMEOUT_MS;
      state.strategyBuilderResult = strategyRunFailure(payload, error, `${API_BASE}/delivery/fit`);
      showToast("拟合失败：未生成任何结果");
    } finally {
      state.strategyBuilderRunning = false;
    }
    renderStrategyBuilder();
    return;
  }

  try {
    const response = await fetchWithTimeout(`${API_BASE}/strategy-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    state.strategyBuilderResult = result;
    state.fitResult = null;
    showToast("策略运行完成");
  } catch (error) {
    state.fitResult = null;
    state.strategyBuilderResult = strategyRunFailure(payload, error);
    showToast("策略运行失败：未生成任何结果");
  }
  renderStrategyBuilder();
}

function strategyRowFromRun(payload) {
  const template = activeStrategyTemplate();
  const result = state.strategyBuilderResult || {};
  const factors = state.strategyBuilderFactors;
  const params = payload.params || {};
  const backtest = payload.backtest_result || result.backtest_result || null;
  const live = payload.live_result || result.live_result || null;
  const window = backtest?.window || {};
  return {
    id: payload.strategy_id,
    name: payload.name,
    type: `${factors.length > 1 ? "多因子" : "单因子"} · ${template?.name || "自定义策略"}`,
    factors: factors.map((factor) => factor.factor_name).join(", "),
    factorIds: factors.map((factor) => factor.id),
    universe: params.universe || "全A等权",
    rebalance: `${window.start || params.start_date || "样本外起"} ~ ${window.end || params.end_date || "最新"}`,
    cost: `双边 ${(Number(params.cost_round_trip ?? 0.003) * 100).toFixed(2)}%`,
    annualReturn: live?.annual_return ?? backtest?.annual_return ?? null,
    sharpe: live?.sharpe ?? backtest?.sharpe ?? null,
    maxDrawdown: live?.max_drawdown ?? backtest?.max_drawdown ?? null,
    status: payload.lifecycle,
    lifecycleStatus: payload.lifecycle,
    source: payload.source,
    templateId: payload.template_id,
    strategyRun: payload,
    backtestResult: backtest,
    liveResult: live,
    equity_curve: backtest?.equity_curve || [],
    metrics_backtest: backtest?.metrics_detail || {},
    params,
    deletable: true,
    updatedAt: new Date().toISOString(),
  };
}

async function saveStrategyBuilder() {
  if (!activeStrategyTemplate()) {
    showToast("请选择成品策略");
    return;
  }
  const payload = strategyRunPayload("已保存");
  let persisted = true;
  try {
    // AGENT-HOOK: 保存导入策略看板与 Agent 自动提交共用端点，生命周期状态机保持一致。
    const response = await fetchWithTimeout(`${API_BASE}/strategy-runs/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    // Keep the local draft, but never claim the backend stored it.
    persisted = false;
  }
  state.strategyDrafts.unshift(strategyRowFromRun(payload));
  saveStrategies();
  state.view = "strategy-board";
  if (window.location.hash) {
    history.pushState("", document.title, window.location.pathname + window.location.search);
  }
  renderView();
  showToast(
    persisted
      ? "策略已保存到策略看板"
      : "后端未连接：策略仅存为本地草稿，未持久化"
  );
}

function metricCell(label, backtestValue, liveValue, formatter) {
  return `
    <div class="builder-metric-row">
      <span>${escapeHtml(label)}</span>
      <strong>${formatter(backtestValue)}</strong>
      <strong>${formatter(liveValue)}</strong>
    </div>
  `;
}

function fitPolyline(values, min, max, width, height) {
  if (!values || values.length < 2) return "";
  const span = max - min || 1;
  return values
    .map((value, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function formatPercent(value, digits = 2) {
  const number = toFiniteNumber(value);
  return number === null ? "—" : `${(number * 100).toFixed(digits)}%`;
}

function renderFitResult(result) {
  if (!result || !result.ok) return "";
  const nav = result.nav || [];
  const benchmark = result.benchmark_nav || [];
  if (nav.length < 2) return "";

  const W = 900;
  const H = 240;
  const all = [...nav, ...benchmark];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const metrics = result.metrics || {};
  const benchMetrics = result.benchmark_metrics || {};

  const rows = [
    ["累计", metrics.total_return, benchMetrics.total_return],
    ["年化", metrics.annualized_return, benchMetrics.annualized_return],
    ["最大回撤", metrics.max_drawdown, benchMetrics.max_drawdown],
    ["波动率", metrics.volatility, benchMetrics.volatility],
  ]
    .map(
      ([label, mine, theirs]) =>
        `<tr><td>${escapeHtml(label)}</td><td class="delivery-mono">${formatPercent(mine)}</td>` +
        `<td class="delivery-mono muted">${formatPercent(theirs)}</td></tr>`
    )
    .join("");

  const contributions = (result.contributions || [])
    .slice(0, 8)
    .map(
      (item) =>
        `<tr><td>${escapeHtml(item.factor_id)}</td>` +
        `<td class="delivery-mono">${deliveryNumber(item.weight, 4)}</td>` +
        `<td class="delivery-mono">${deliveryNumber(item.share_of_selected_score, 4)}</td></tr>`
    )
    .join("");

  const skipped = (result.skipped || []).length
    ? `<p class="delivery-note">以下所选因子没有预计算分数，<strong>未参与本次拟合</strong>：${escapeHtml(
        result.skipped.slice(0, 8).join("、")
      )}${result.skipped.length > 8 ? ` 等 ${result.skipped.length} 个` : ""}</p>`
    : "";

  // One factor is allowed by the template, but "多因子等权多头" then degenerates into
  // "that one factor's top-N basket". Saying so prevents reading a single factor's
  // tracking error as a diversified strategy result.
  const single =
    (result.used || []).length === 1
      ? `<p class="delivery-note">
           本次只用 <strong>1 个因子</strong>，「多因子等权多头」因此退化为该因子的 top-${escapeHtml(
             String(result.top_n)
           )} 组合——它反映的是这一个因子的选股能力，<strong>不是</strong>多因子分散后的结果。
           勾选多个因子（例如各簇代表）再看这条曲线，差异通常很大。
         </p>`
      : "";

  const ignored = (result.ignored_params || []).length
    ? `<p class="delivery-note">以下参数<strong>未参与本次拟合</strong>：${escapeHtml(
        result.ignored_params.map((p) => `${p.key}=${p.value}（${p.note}）`).join("；")
      )}</p>`
    : "";

  return `
    <section class="delivery-evidence">
      <header>
        <h3>拟合结果</h3>
        <span class="badge">${escapeHtml(String(result.method))}</span>
        <span class="badge">top ${escapeHtml(String(result.top_n))}</span>
        <span class="badge">${escapeHtml(String(result.rebalances))} 次再平衡</span>
      </header>
      <p class="delivery-note">
        窗口 ${escapeHtml(result.window.start)} → ${escapeHtml(result.window.end)}（${escapeHtml(
          String(result.window.observations)
        )} 个交易日）· 使用 <strong>${result.used ? result.used.length : 0}</strong> 个因子等权 ·
        往返成本 ${escapeHtml(String(result.cost_model.round_trip_total))}
        ${result.window_defaulted_to_oos ? " · <strong>未指定窗口，已默认取冻结样本外区间</strong>" : ""}
      </p>
      ${skipped}
      ${single}
      ${ignored}
      <svg viewBox="0 0 ${W} ${H + 24}" class="delivery-chart" role="img" aria-label="策略净值与基准">
        <polyline points="${fitPolyline(benchmark, min, max, W, H)}" fill="none" stroke="#94a3b8" stroke-width="1.4" stroke-dasharray="5,4" />
        <polyline points="${fitPolyline(nav, min, max, W, H)}" fill="none" stroke="#1d4ed8" stroke-width="2" />
        <text x="0" y="${H + 18}" font-size="10" fill="#6b7280">${escapeHtml(result.window.start)}</text>
        <text x="${W}" y="${H + 18}" font-size="10" fill="#6b7280" text-anchor="end">${escapeHtml(result.window.end)}</text>
        <text x="4" y="12" font-size="10" fill="#1d4ed8">实线＝策略</text>
        <text x="80" y="12" font-size="10" fill="#94a3b8">虚线＝等权基准</text>
      </svg>
      <table class="delivery-table">
        <thead><tr><th>指标</th><th>策略</th><th>基准</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${contributions ? `
        <h4>因子贡献（前 8）</h4>
        <table class="delivery-table">
          <thead><tr><th>因子</th><th>权重</th><th>占入选分数比重</th></tr></thead>
          <tbody>${contributions}</tbody>
        </table>` : ""}
      <p class="delivery-note">
        ${escapeHtml(
          Object.entries(result.disclosure || {})
            .map(([k, v]) => `${k}: ${v}`)
            .join(" · ")
        )}
      </p>
    </section>
  `;
}

function renderStrategyBuilderResult() {
  if (state.strategyBuilderRunning) {
    return `<div class="builder-result-running">
      <strong>拟合中…</strong>
      <span>正在读取分数分区并模拟组合。全历史窗口通常需要 10–30 秒，请不要重复点击运行。</span>
    </div>`;
  }
  if (state.fitResult) return renderFitResult(state.fitResult);
  const result = state.strategyBuilderResult;
  if (!result) {
    return `<div class="builder-empty-result">运行后展示净值曲线与回测段 / 实盘段指标。</div>`;
  }
  if (result.__error) {
    return `
      <section class="builder-result-card builder-result-error">
        <div class="builder-error-title">未生成结果</div>
        <p>策略运行请求失败。<strong>本页不会显示任何模拟或估算的收益数字</strong>——没有真实计算就没有结果。</p>
        <ul>
          <li>请求地址：<code>${escapeHtml(result.backend)}</code></li>
          <li>失败原因：<code>${escapeHtml(result.message)}</code></li>
        </ul>
        <p class="builder-error-hint">本地请通过 Flask 后端访问：<code>http://127.0.0.1:8012/factor-lab-dashboard</code>。</p>
      </section>
    `;
  }
  const backtest = result.backtest_result || {};
  const live = result.live_result || {};
  const backtestEquity = backtest.equity_curve || [];
  const liveEquity = live.equity_curve || [];
  
  let curveHtml = "";
  if (backtestEquity.length > 0 || liveEquity.length > 0) {
    const allEquity = [...backtestEquity, ...liveEquity];
    const minVal = Math.min(...allEquity.filter(v => !isNaN(v)), 0.8);
    const maxVal = Math.max(...allEquity.filter(v => !isNaN(v)), 1.2);
    const range = maxVal - minVal || 0.4;
    const totalLen = backtestEquity.length + liveEquity.length;
    
    const backtestPath = backtestEquity.length > 0 ? generatePathFromEquity(backtestEquity, minVal, maxVal, 0, totalLen) : "";
    const livePath = liveEquity.length > 0 ? generatePathFromEquity(liveEquity, minVal, maxVal, backtestEquity.length, totalLen) : "";
    const cutoffX = backtestEquity.length > 0 ? (backtestEquity.length / totalLen) * 600 : 450;
    
    curveHtml = `
      <svg viewBox="0 0 600 120" class="equity-svg" style="height:120px">
        <defs>
          <linearGradient id="builderBacktestGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#94a3b8;stop-opacity:0.2" />
            <stop offset="100%" style="stop-color:#94a3b8;stop-opacity:0" />
          </linearGradient>
          <linearGradient id="builderLiveGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:0.3" />
            <stop offset="100%" style="stop-color:#3b82f6;stop-opacity:0" />
          </linearGradient>
        </defs>
        ${backtestPath ? `<path d="${backtestPath}" fill="none" stroke="#94a3b8" stroke-width="1.8" stroke-dasharray="5,4" stroke-linejoin="round" stroke-linecap="round" /><path d="${backtestPath} L 600,100 L 0,100 Z" fill="url(#builderBacktestGradient)" />` : ""}
        ${livePath ? `<path d="${livePath}" fill="none" stroke="#3b82f6" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round" /><path d="${livePath} L 600,100 L ${cutoffX},100 Z" fill="url(#builderLiveGradient)" />` : ""}
        <line x1="${cutoffX}" y1="10" x2="${cutoffX}" y2="100" stroke="#94a3b8" stroke-width="0.9" stroke-dasharray="4,4" />
        <text x="${cutoffX + 5}" y="20" fill="#6b7280" font-size="10">临界日</text>
        <text x="10" y="115" fill="#6b7280" font-size="10">回测段</text>
        <text x="550" y="115" fill="#6b7280" font-size="10">实盘段</text>
      </svg>
    `;
  } else {
    curveHtml = `
      <div class="builder-curve" aria-label="净值曲线">
        <div class="curve-line curve-line-backtest"></div>
        <div class="curve-cutoff" title="临界日 ${escapeHtml(result.cutoff_date || state.strategyBuilderParams.cutoff_date || "-")}"></div>
        <div class="curve-line curve-line-live"></div>
        <span class="curve-label left">回测段</span>
        <span class="curve-label right">实盘段</span>
      </div>
    `;
  }
  
  return `
    <section class="builder-result-card">
      ${curveHtml}
      <div class="builder-metrics">
        <div class="builder-metric-head"><span>指标</span><strong>回测段</strong><strong>实盘段</strong></div>
        ${metricCell("年化", backtest.annual_return, live.annual_return, formatRatio)}
        ${metricCell("夏普", backtest.sharpe_ratio || backtest.sharpe, live.sharpe_ratio || live.sharpe, (value) => formatNumber(value, 2))}
        ${metricCell("最大回撤", backtest.max_drawdown, live.max_drawdown, formatRatio)}
        ${metricCell("胜率", backtest.win_rate, live.win_rate, formatRatio)}
      </div>
    </section>
  `;
}

function renderStrategyWeightEditor(selectedFactors) {
  if (state.strategyBuilderParams.weight_mode !== "custom") return "";
  if (!selectedFactors.length) return "";
  const weights = selectedFactors.map((factor) => {
    const value = Number(state.strategyBuilderWeights[factor.id] ?? 1);
    return Number.isFinite(value) && value > 0 ? value : 0;
  });
  const total = weights.reduce((sum, value) => sum + value, 0);
  const denominator = total > 0 ? total : 1;
  return `
    <div class="builder-weight-editor">
      <header><strong>自定义权重</strong><span>运行时按合计归一化${total > 0 ? `（当前合计 ${total.toFixed(2)}）` : "（当前全为 0，无法运行）"}</span></header>
      <div class="builder-weight-grid">
        ${selectedFactors.map((factor, index) => `
          <label class="builder-param">
            <span>${escapeHtml(compactName(factor.factor_name))}（${((weights[index] / denominator) * 100).toFixed(1)}%）</span>
            <input data-builder-weight="${escapeHtml(factor.id)}" type="number" min="0" step="0.1" value="${weights[index]}" />
          </label>
        `).join("")}
      </div>
    </div>
  `;
}

function renderStrategyBuilder() {
  if (!els.strategyBuilderView) return;
  const template = activeStrategyTemplate();
  if (template) seedStrategyBuilderParams(template);
  const selectedFactors = state.strategyBuilderFactors;
  els.strategyBuilderView.innerHTML = `
    <div class="breadcrumb">
      <button type="button" class="breadcrumb-link" data-builder-back="library">因子库</button>
      <span>›</span>
      <strong>策略构建</strong>
    </div>
    <section class="strategy-head builder-head">
      <div>
        <h2>策略构建页</h2>
        <p>选成品策略，把因子塞进去，只调外围研究参数；策略内部逻辑由 Agent / 系统策略库封装。</p>
      </div>
      <span class="panel-badge">成品策略模式</span>
    </section>

    <section class="builder-section">
      <header><strong>已选因子</strong><span>只读，方向由因子 IC/方向字段映射</span></header>
      <div class="table-scroll">
        <table class="builder-factor-table">
          <thead><tr><th>因子名</th><th>方向</th><th>分类</th><th class="number">IC</th><th class="number">IR</th></tr></thead>
          <tbody>
            ${selectedFactors.length ? selectedFactors.map((factor) => {
              const direction = monitorDirection(factor);
              return `
                <tr>
                  <td>${escapeHtml(factor.factor_name)}</td>
                  <td><span class="direction-pill ${direction.className}">${factorDirectionValue(factor) > 0 ? "+1 正向" : "-1 反向"}</span></td>
                  <td>${escapeHtml(jqFactorCategory(factor))}</td>
                  <td class="number">${formatNumber(factor.rank_ic_mean, 4)}</td>
                  <td class="number">${formatNumber(factor.rank_ic_ir, 3)}</td>
                </tr>
              `;
            }).join("") : `<tr><td colspan="5" class="empty-cell">请先从因子库选择可用因子。</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>

    <section class="builder-section">
      <header><strong>成品策略列表</strong><span>来自后端可用策略清单；未接入时展示本地兜底模板</span></header>
      <div class="builder-template-list">
        ${state.strategyTemplates.map((item) => `
          <label class="builder-template-card ${item.template_id === state.selectedStrategyTemplateId ? "active" : ""}">
            <input type="radio" name="strategyTemplate" value="${escapeHtml(item.template_id)}" ${item.template_id === state.selectedStrategyTemplateId ? "checked" : ""} />
            <span>
              <strong>${escapeHtml(item.name)}</strong>
              <small>${escapeHtml(item.description)}</small>
              <em>${item.source === "system" ? "系统策略库" : "Agent 挖掘"} · 需要 ${escapeHtml(requiredFactorLabel(item.required_factor_count))}</em>
            </span>
          </label>
        `).join("")}
      </div>
    </section>

    <section class="builder-section builder-params-section">
      <header><strong>外围参数</strong><span>研究模式，结果不代表复现结论；临界日左回测、右实盘。</span></header>
      <div class="builder-param-grid">
        ${(template?.param_schema || []).map(renderParamField).join("")}
      </div>
    </section>

    <section class="builder-section builder-params-section">
      <header><strong>执行参数</strong><span>拟合引擎口径：持仓数、调仓周期、双边成本与权重方式。这些参数会随策略一起保存，便于复现。</span></header>
      <div class="builder-param-grid">
        <label class="builder-param">
          <span>持仓数</span>
          <input data-builder-param="top_n" type="number" min="1" max="200" step="1" value="${escapeHtml(String(state.strategyBuilderParams.top_n ?? "20"))}" />
        </label>
        <label class="builder-param">
          <span>调仓周期</span>
          <select data-builder-param="rebalance_every">
            ${[
              ["month_end", "月末"],
              ["5", "每 5 个交易日"],
              ["10", "每 10 个交易日"],
              ["20", "每 20 个交易日"],
            ]
              .map(([value, label]) => `<option value="${value}" ${String(state.strategyBuilderParams.rebalance_every) === value ? "selected" : ""}>${label}</option>`)
              .join("")}
          </select>
        </label>
        <label class="builder-param">
          <span>双边成本</span>
          <input data-builder-param="cost_round_trip" type="number" min="0" max="0.02" step="0.0005" value="${escapeHtml(String(state.strategyBuilderParams.cost_round_trip ?? "0.003"))}" />
        </label>
        <label class="builder-param">
          <span>权重方式</span>
          <select data-builder-param="weight_mode">
            ${[
              ["equal", "等权"],
              ["custom", "自定义权重"],
            ]
              .map(([value, label]) => `<option value="${value}" ${String(state.strategyBuilderParams.weight_mode) === value ? "selected" : ""}>${label}</option>`)
              .join("")}
          </select>
        </label>
      </div>
      ${renderStrategyWeightEditor(selectedFactors)}
    </section>

    <section class="builder-section builder-actions-section">
      <label class="builder-name-field">
        <span>策略名称</span>
        <input id="strategyBuilderName" type="text" value="${escapeHtml(state.strategyBuilderName)}" placeholder="给这个策略实例命名" />
      </label>
      <div class="builder-actions">
        <button type="button" class="secondary-action" id="runStrategyBuilder" ${selectedFactors.length ? "" : "disabled"}>运行</button>
        <button type="button" class="primary-action" id="saveStrategyBuilder" ${selectedFactors.length ? "" : "disabled"}>保存并导入策略看板</button>
      </div>
    </section>

    <section class="builder-section">
      <header><strong>结果区</strong><span>净值曲线在临界日切分，核心看回测段与实盘段差距。</span></header>
      ${renderStrategyBuilderResult()}
    </section>
  `;

  els.strategyBuilderView.querySelector("[data-builder-back]")?.addEventListener("click", () => showMainView("library"));
  els.strategyBuilderView.querySelectorAll("input[name='strategyTemplate']").forEach((input) => {
    input.addEventListener("change", () => {
      state.selectedStrategyTemplateId = input.value;
      seedStrategyBuilderParams(activeStrategyTemplate());
      state.strategyBuilderResult = null;
      renderStrategyBuilder();
    });
  });
  els.strategyBuilderView.querySelectorAll("[data-builder-param]").forEach((input) => {
    input.addEventListener("input", () => {
      state.strategyBuilderParams[input.dataset.builderParam] = input.value;
    });
    input.addEventListener("change", () => {
      state.strategyBuilderParams[input.dataset.builderParam] = input.value;
      state.strategyBuilderResult = null;
      // 切换权重方式后要立即显示/隐藏逐因子权重输入框。
      if (input.dataset.builderParam === "weight_mode") renderStrategyBuilder();
    });
  });
  els.strategyBuilderView.querySelectorAll("[data-builder-weight]").forEach((input) => {
    input.addEventListener("input", () => {
      state.strategyBuilderWeights[input.dataset.builderWeight] = Number(input.value);
    });
    input.addEventListener("change", () => {
      state.strategyBuilderWeights[input.dataset.builderWeight] = Number(input.value);
      state.strategyBuilderResult = null;
      renderStrategyBuilder();
    });
  });
  els.strategyBuilderView.querySelector("#strategyBuilderName")?.addEventListener("input", (event) => {
    state.strategyBuilderName = event.target.value;
  });
  els.strategyBuilderView.querySelector("#runStrategyBuilder")?.addEventListener("click", runStrategyBuilder);
  els.strategyBuilderView.querySelector("#saveStrategyBuilder")?.addEventListener("click", saveStrategyBuilder);
}

// ── 因子↔策略双向追溯 helpers ──

function parseFactorTokens(factorsStr) {
  if (!factorsStr) return [];
  if (Array.isArray(factorsStr)) {
    return factorsStr
      .map((f) => (typeof f === "string" ? f.trim() : (f && f.factor_id) || (f && f.id) || ""))
      .filter(Boolean);
  }
  return String(factorsStr)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function factorTokenShortName(token) {
  if (!token) return "";
  const parts = String(token).split(":");
  return parts.length > 1 ? parts[parts.length - 1] : token;
}

function strategiesUsingFactor(factorId) {
  if (!factorId) return [];
  const fid = String(factorId);
  return strategyRows().filter((row) => {
    const tokens = parseFactorTokens(row.factors);
    return tokens.some((t) => String(t) === fid);
  });
}

function renderFactorTraceChips(factorsStr) {
  const tokens = parseFactorTokens(factorsStr);
  if (!tokens.length) return '<span class="trace-chip is-placeholder">-</span>';
  return tokens
    .map((token) => {
      const inLibrary = state.rawFactors.some((f) => f.id === token);
      return `<button type="button" class="trace-chip" data-trace-factor-id="${escapeHtml(token)}" ${inLibrary ? "" : 'title="该因子不在当前因子库中"'}>${escapeHtml(factorTokenShortName(token))}</button>`;
    })
    .join("");
}

function renderStrategyTraceChips(factorId) {
  const refs = strategiesUsingFactor(factorId);
  if (!refs.length) return '<span class="trace-chip is-placeholder">-</span>';
  return refs
    .slice(0, 3)
    .map((row) => `<button type="button" class="trace-chip trace-strategy" data-trace-strategy-id="${escapeHtml(row.id)}" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</button>`)
    .join(refs.length > 3 ? `<span class="trace-chip is-placeholder">+${refs.length - 3}</span>` : "");
}

function bindFactorTraceChips(root) {
  root.querySelectorAll("[data-trace-factor-id]").forEach((chip) => {
    chip.addEventListener("click", (event) => {
      event.stopPropagation();
      const fid = chip.dataset.traceFactorId;
      const factor = state.rawFactors.find((f) => f.id === fid);
      if (factor && canOpenFactor(factor)) {
        openDetail(fid);
      }
    });
  });
}

function bindStrategyTraceChips(root) {
  root.querySelectorAll("[data-trace-strategy-id]").forEach((chip) => {
    chip.addEventListener("click", (event) => {
      event.stopPropagation();
      openStrategyDetail(chip.dataset.traceStrategyId);
    });
  });
}

function strategyRows() {
  const apiRows = state.strategies.map((s) => ({
    id: s.id,
    name: s.name,
    type: s.type,
    factors: s.factors,
    universe: s.universe,
    rebalance: s.rebalance || "月频调仓",
    cost: s.cost || "0.1%",
    annualReturn: s.annualReturn,
    sharpe: s.sharpe,
    maxDrawdown: s.maxDrawdown,
    status: s.status || "研究就绪",
    updatedAt: s.updatedAt || "-",
    rank_ic_mean: s.rank_ic_mean,
    rank_ic_ir: s.rank_ic_ir,
    cutoff_date: s.cutoff_date,
    equity_curve: s.equity_curve,
    nav_history: s.nav_history,
    metrics_backtest: s.metrics_backtest,
    metrics_live: s.metrics_live,
    params: s.params,
    data_source: s.data_source,
    debug: s.debug,
    backtest_result: s.backtest_result,
    live_result: s.live_result,
  }));
  // 本地草稿与后端已保存副本可能是同一条策略（保存成功后两处都有），按 id 去重，
  // 保留本地最新的一份，避免看板出现两行相同策略、收益数字看起来"不一致"。
  const seen = new Set();
  return [...state.strategyDrafts, ...apiRows].filter((row) => {
    const id = row && row.id ? String(row.id) : "";
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function renderStrategyStats(rows) {
  if (!els.strategyStats) return;
  const ready = rows.filter((row) => row.status === "研究就绪").length;
  const withSharpe = rows.filter((row) => Number.isFinite(Number(row.sharpe)));
  const withReturn = rows.filter((row) => Number.isFinite(Number(row.annualReturn)));
  const avgSharpe = withSharpe.length
    ? withSharpe.reduce((sum, row) => sum + Number(row.sharpe), 0) / withSharpe.length
    : 0;
  const avgReturn = withReturn.length
    ? withReturn.reduce((sum, row) => sum + Number(row.annualReturn), 0) / withReturn.length
    : 0;
  els.strategyStats.innerHTML = [
    ["策略条目", rows.length, "含已保存策略与后端研究行"],
    ["已有研究基础", ready, "可从因子研究结果继续推进"],
    ["平均夏普", formatNumber(avgSharpe, 2), `仅统计有数值的 ${withSharpe.length} 条`],
    ["平均年化", formatRatio(avgReturn), `仅统计有数值的 ${withReturn.length} 条`],
  ]
    .map(
      ([label, value, note]) => `
        <article class="monitor-stat-card">
          <span>${label}</span>
          <strong>${value}</strong>
          <small>${note}</small>
        </article>
      `,
    )
    .join("");
}

function renderStrategy() {
  if (!state.strategiesLoaded && !state.strategiesLoading) {
    loadStrategies();
  }
  const rows = strategyRows();
  if (state.strategySortKey && state.strategySortDirection !== "default") {
    rows.sort(compareStrategies);
  }
  renderStrategyStats(rows);
  renderStrategySortHeaders();
  if (!els.strategyTableBody) return;
  els.strategyTableBody.innerHTML = rows
    .map(
      (row) => `
        <tr class="${state.strategyDeleteMode ? "strategy-delete-mode-row" : ""}">
          <td class="strategy-name-cell" title="${escapeHtml(row.name)}">
            ${
              state.strategyDeleteMode
                ? `<label class="strategy-delete-check">
                    <input type="checkbox" data-strategy-delete-id="${escapeHtml(row.id)}" ${row.deletable ? "" : "disabled"} ${state.selectedStrategyDeleteIds.has(row.id) ? "checked" : ""} />
                  </label>`
                : ""
            }
            <button type="button" class="strategy-link" data-strategy-id="${escapeHtml(row.id)}">${escapeHtml(row.name)}</button>
            <span class="monitor-source-sub">${escapeHtml(row.type || "-")}</span>
          </td>
          <td class="strategy-factors-cell">${renderFactorTraceChips(row.factors)}</td>
          <td class="strategy-universe-cell" title="${escapeHtml(row.universe)}">${escapeHtml(row.universe)}</td>
          <td>
            <strong>${escapeHtml(row.rebalance)}</strong>
            <span class="monitor-source-sub">${escapeHtml(row.cost)}</span>
          </td>
          <td class="number">${formatRatio(row.annualReturn)}</td>
          <td class="number">${formatNumber(row.sharpe, 2)}</td>
          <td class="number">${formatRatio(row.maxDrawdown)}</td>
          <td>
            <span class="badge ${["研究就绪", "已验证", "已保存", "监控中"].includes(row.status) ? "badge-green" : row.status === "草稿" ? "badge-blue" : "badge-gray"}">${escapeHtml(row.status)}</span>
            ${row.status === "草稿" ? `<button type="button" class="text-button" data-strategy-save="${escapeHtml(row.id)}">保存策略</button>` : ""}
          </td>
          <td>${formatDate(row.updatedAt)}</td>
        </tr>
      `,
    )
    .join("");
  renderStrategyDeleteActions(rows);

  els.strategyTableBody.querySelectorAll("[data-strategy-id]").forEach((button) => {
    button.addEventListener("click", () => openStrategyDetail(button.dataset.strategyId));
  });
  bindFactorTraceChips(els.strategyTableBody);
  els.strategyTableBody.querySelectorAll("[data-strategy-delete-id]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) {
        state.selectedStrategyDeleteIds.add(input.dataset.strategyDeleteId);
      } else {
        state.selectedStrategyDeleteIds.delete(input.dataset.strategyDeleteId);
      }
      renderStrategyDeleteActions(rows);
    });
  });
  els.strategyTableBody.querySelectorAll("[data-strategy-save]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      saveStrategyDraft(button.dataset.strategySave);
    });
  });
}

function renderStrategyDeleteActions(rows) {
  const tableCard = els.strategyTableBody?.closest(".strategy-table-card");
  if (!tableCard) return;
  let actions = tableCard.querySelector(".strategy-board-actions");
  if (!actions) {
    actions = document.createElement("div");
    actions.className = "strategy-board-actions";
    tableCard.appendChild(actions);
  }
  const deletableCount = rows.filter((row) => row.deletable).length;
  if (!state.strategyDeleteMode) {
    state.selectedStrategyDeleteIds.clear();
    actions.innerHTML = `<button type="button" class="danger-action compact" id="enterStrategyDeleteMode" ${deletableCount ? "" : "disabled"}>删除策略</button>`;
    actions.querySelector("#enterStrategyDeleteMode")?.addEventListener("click", () => {
      state.strategyDeleteMode = true;
      renderQuantDesk();
    });
    return;
  }
  actions.innerHTML = `
    <span>已选 ${state.selectedStrategyDeleteIds.size} 个策略</span>
    <button type="button" class="danger-action compact" id="deleteSelectedStrategies" ${state.selectedStrategyDeleteIds.size ? "" : "disabled"}>删除选中</button>
    <button type="button" class="secondary-action compact" id="cancelStrategyDeleteMode">取消</button>
  `;
  actions.querySelector("#deleteSelectedStrategies")?.addEventListener("click", deleteSelectedStrategies);
  actions.querySelector("#cancelStrategyDeleteMode")?.addEventListener("click", () => {
    state.strategyDeleteMode = false;
    state.selectedStrategyDeleteIds.clear();
    renderStrategy();
  });
}

function deleteSelectedStrategies() {
  if (!state.selectedStrategyDeleteIds.size) return;
  state.strategyDrafts = state.strategyDrafts.filter((row) => !state.selectedStrategyDeleteIds.has(row.id));
  saveStrategies();
  state.selectedStrategyDeleteIds.clear();
  state.strategyDeleteMode = false;
  renderStrategy();
  showToast("已删除所选策略");
}

function saveStrategyDraft(strategyId) {
  const draft = state.strategyDrafts.find((item) => item.id === strategyId);
  if (!draft) return;
  // AGENT-HOOK: 保存策略应由后端统一端点处理，human/agent 共用 source 与同一生命周期状态机。
  draft.status = "已保存";
  draft.lifecycleStatus = "已保存";
  draft.source = draft.source || "human";
  draft.deletable = true;
  draft.updatedAt = new Date().toISOString();
  renderStrategy();
  showToast("策略已保存");
}

function compareStrategies(left, right) {
  const key = state.strategySortKey;
  const direction = state.strategySortDirection === "asc" ? 1 : -1;
  const leftValue = left[key];
  const rightValue = right[key];
  if (typeof leftValue === "number" || typeof rightValue === "number") {
    return compareNullableNumbers(leftValue, rightValue) * direction;
  }
  return String(leftValue ?? "").localeCompare(String(rightValue ?? ""), "zh-CN", { numeric: true }) * direction;
}

function sanitizeId(value) {
  return String(value || "item")
    .replace(/[^A-Za-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function activeStrategy() {
  return strategyRows().find((row) => row.id === state.activeStrategyId);
}

function normalizeRowEquityCurve(row) {
  const params = row.params || {};
  const cutoffDate = params.cutoff_date || row.cutoff_date || "2024-06-01";
  const sourcePoints = Array.isArray(row.equity_curve) && row.equity_curve.length
    ? row.equity_curve
    : Array.isArray(row.nav_history)
      ? row.nav_history
      : [];
  return sourcePoints
    .map((point) => {
      const nav = Number(point.nav);
      if (!point.date || !Number.isFinite(nav)) return null;
      return {
        date: point.date,
        nav,
        phase: point.phase || (point.date <= cutoffDate ? "backtest" : "live"),
      };
    })
    .filter(Boolean);
}

function detailDataFromStrategyRow(row) {
  const factorText = Array.isArray(row.factors) ? row.factors.join(", ") : String(row.factors || "");
  const factors = factorText
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((factor_id) => ({ factor_id, direction: 1 }));
  return {
    strategy_id: row.id,
    name: row.name,
    type: row.type,
    factors,
    params: row.params || {
      universe: row.universe,
      cutoff_date: row.cutoff_date,
      rebalance: row.rebalance,
      cost: row.cost,
    },
    equity_curve: normalizeRowEquityCurve(row),
    metrics_backtest: row.metrics_backtest || {},
    metrics_live: row.metrics_live || {},
    data_source: row.data_source,
    debug: row.debug,
  };
}

async function loadStrategyDetailData(strategyId) {
  if (state.strategyDetailLoading[strategyId]) return;
  state.strategyDetailLoading[strategyId] = true;
  try {
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/strategy/${strategyId}`));
    if (response.ok) {
      const data = await response.json();
      state.strategyDetailData[strategyId] = data;
    }
  } catch (error) {
    console.error("获取策略详情失败:", error);
  } finally {
    state.strategyDetailLoading[strategyId] = false;
    if (state.view === "strategy-detail" && state.activeStrategyId === strategyId) {
      renderStrategyDetail();
    }
  }
}

async function openStrategyDetail(strategyId) {
  const row = strategyRows().find((item) => item.id === strategyId);
  if (!row) return;
  
  if (state.autoRefreshTimer) {
    window.clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
  
  state.view = "strategy-detail";
  state.activeStrategyId = strategyId;
  renderView();
  
  if (!state.strategyDetailData) {
    state.strategyDetailData = {};
  }
  
  try {
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/strategy/${strategyId}`));
    if (response.ok) {
      const data = await response.json();
      console.log("[DEBUG] Strategy detail API response:", data);
      state.strategyDetailData[strategyId] = data;
      renderStrategyDetail();
      return;
    }
  } catch (error) {
    console.error("获取策略详情失败:", error);
  }
  
  const rowDetailData = detailDataFromStrategyRow(row);
  state.strategyDetailData[strategyId] = rowDetailData;
  renderStrategyDetail();
}

function closeStrategyDetail() {
  startAutoRefresh();
  state.view = "strategy-board";
  state.activeStrategyId = null;
  renderView();
}

function normalizeEquityValues(series) {
  if (!Array.isArray(series)) return [];
  return series
    .map((point) => {
      const value = typeof point === "number" ? point : point?.nav ?? point?.equity ?? point?.value;
      return Number(value);
    })
    .filter((value) => Number.isFinite(value) && value > 0);
}

function normalizeEquityDates(series, fallbackDates = []) {
  if (!Array.isArray(series)) return fallbackDates;
  const dates = series.map((point, index) => (
    typeof point === "object" && point !== null ? point.date || fallbackDates[index] || "" : fallbackDates[index] || ""
  ));
  return dates.length ? dates : fallbackDates;
}

function previewEquitySeries() {
  const dates = [
    "2019-01-31", "2019-04-30", "2019-07-31", "2019-10-31",
    "2020-01-31", "2020-04-30", "2020-07-31", "2020-10-31",
    "2021-01-31", "2021-04-30", "2021-07-31", "2021-10-31",
    "2022-01-31", "2022-04-30", "2022-07-31", "2022-10-31",
    "2023-01-31", "2023-04-30", "2023-07-31", "2023-10-31",
    "2024-01-31", "2024-04-30", "2024-07-31", "2024-10-31",
  ];
  const equity = [
    1.00, 1.02, 1.01, 1.04,
    1.05, 1.03, 1.08, 1.12,
    1.15, 1.18, 1.16, 1.22,
    1.20, 1.24, 1.28, 1.27,
    1.31, 1.38, 1.35, 1.42,
    1.48, 1.45, 1.56, 1.62,
  ];
  const split = 15;
  return {
    backtestEquity: equity.slice(0, split),
    liveEquity: equity.slice(split - 1),
    backtestDates: dates.slice(0, split),
    liveDates: dates.slice(split - 1),
  };
}

const EQUITY_CHART = {
  left: 64,
  right: 1540,
  top: 38,
  bottom: 370,
  tickBottom: 398,
  dateY: 424,
  labelX: 802,
  labelY: 464,
};

function equityX(index, totalLength) {
  return EQUITY_CHART.left + (index / Math.max(1, totalLength - 1)) * (EQUITY_CHART.right - EQUITY_CHART.left);
}

function equityY(value, minVal, maxVal, logScale = false) {
  const height = EQUITY_CHART.bottom - EQUITY_CHART.top;
  let normalized;
  if (logScale) {
    const logMin = Math.log10(Math.max(minVal, 0.01));
    const logMax = Math.log10(Math.max(maxVal, 0.01));
    const logRange = logMax - logMin || 1;
    const logVal = Math.log10(Math.max(value, 0.01));
    normalized = (logVal - logMin) / logRange;
  } else {
    const range = maxVal - minVal || 0.4;
    normalized = (value - minVal) / range;
  }
  return EQUITY_CHART.bottom - normalized * height;
}

function equityTickIndexes(dates, maxTicks = 9) {
  if (!Array.isArray(dates) || dates.length === 0) return [];
  const total = dates.length;
  const count = Math.min(maxTicks, total);
  if (count <= 1) return [0];
  return [...new Set(
    Array.from({ length: count }, (_, tick) => Math.round((tick * (total - 1)) / (count - 1)))
  )].sort((a, b) => a - b);
}

function renderEquityCurve(row, logScale = false) {
  const backtest = row.backtestResult || row.backtest_result || {};
  const live = row.liveResult || row.live_result || {};
  let backtestEquity = normalizeEquityValues(backtest.equity_curve || backtest.equity || []);
  let liveEquity = normalizeEquityValues(live.equity_curve || live.equity || []);
  let backtestDates = normalizeEquityDates(backtest.equity_curve, backtest.dates || []);
  let liveDates = normalizeEquityDates(live.equity_curve, live.dates || []);
  let previewOnly = false;
  if (backtestEquity.length === 0 && liveEquity.length === 0) {
    const preview = previewEquitySeries();
    backtestEquity = preview.backtestEquity;
    liveEquity = preview.liveEquity;
    backtestDates = preview.backtestDates;
    liveDates = preview.liveDates;
    previewOnly = true;
  }
  
  if (backtestEquity.length > 0 || liveEquity.length > 0) {
    const allEquity = [...backtestEquity, ...liveEquity];
    const allDates = [...backtestDates, ...liveDates];
    const validEquity = allEquity.filter(v => !isNaN(v) && v > 0);
    const minVal = Math.min(...validEquity, 0.8);
    const maxVal = Math.max(...validEquity, 1.2);
    const range = maxVal - minVal || 0.4;
    const totalLength = backtestEquity.length + liveEquity.length;
    
    const backtestPath = backtestEquity.length > 0 ? generatePathFromEquity(backtestEquity, minVal, maxVal, 0, totalLength, logScale) : "";
    const livePath = liveEquity.length > 0 ? generatePathFromEquity(liveEquity, minVal, maxVal, backtestEquity.length, totalLength, logScale) : "";
    const cutoffIndex = backtestEquity.length > 0 ? Math.min(totalLength - 1, backtestEquity.length) : Math.floor(totalLength * 0.75);
    const cutoffX = equityX(cutoffIndex, totalLength);
    
    let html = "";
    
    html += `<line x1="${EQUITY_CHART.left}" y1="${EQUITY_CHART.top}" x2="${EQUITY_CHART.left}" y2="${EQUITY_CHART.bottom}" stroke="#e2e8f0" stroke-width="1" />`;
    html += `<line x1="${EQUITY_CHART.left}" y1="${EQUITY_CHART.bottom}" x2="${EQUITY_CHART.right}" y2="${EQUITY_CHART.bottom}" stroke="#e2e8f0" stroke-width="1" />`;
    
    let yTicks, yMin, yMax;
    if (logScale) {
      const logMin = Math.log10(Math.max(minVal, 0.01));
      const logMax = Math.log10(Math.max(maxVal, 0.01));
      yMin = Math.pow(10, Math.floor(logMin));
      yMax = Math.pow(10, Math.ceil(logMax));
      yTicks = [];
      let val = yMin;
      while (val <= yMax) {
        yTicks.push(val);
        val *= 2;
        if (val > yMax && yTicks.length < 5) val = yMin * 5;
      }
      yTicks = [...new Set(yTicks)].sort((a, b) => a - b).slice(0, 5);
    } else {
      yTicks = [minVal, minVal + range * 0.25, minVal + range * 0.5, minVal + range * 0.75, maxVal];
    }
    
    yTicks.forEach((val) => {
      const y = equityY(val, minVal, maxVal, logScale);
      html += `<line x1="${EQUITY_CHART.left}" y1="${y}" x2="${EQUITY_CHART.right}" y2="${y}" stroke="#f1f5f9" stroke-width="1" />`;
      html += `<line x1="${EQUITY_CHART.left - 8}" y1="${y}" x2="${EQUITY_CHART.left}" y2="${y}" stroke="#e2e8f0" stroke-width="1" />`;
      html += `<text x="${EQUITY_CHART.left - 14}" y="${y + 4}" fill="#64748b" font-size="12" text-anchor="end">${logScale ? val.toExponential(1) : val.toFixed(2)}</text>`;
    });
    
    const xTickIndexes = equityTickIndexes(allDates);
    html += `<line x1="${EQUITY_CHART.left}" y1="${EQUITY_CHART.tickBottom}" x2="${EQUITY_CHART.right}" y2="${EQUITY_CHART.tickBottom}" stroke="#e2e8f0" stroke-width="1" />`;
    [...new Set(xTickIndexes)].forEach((i) => {
      const x = equityX(i, totalLength);
      const date = allDates[i] || "";
      html += `<line x1="${x}" y1="${EQUITY_CHART.bottom}" x2="${x}" y2="${EQUITY_CHART.tickBottom}" stroke="#e2e8f0" stroke-width="1" />`;
      html += `<text x="${x}" y="${EQUITY_CHART.dateY}" fill="#64748b" font-size="11" text-anchor="middle">${escapeHtml(date || "-")}</text>`;
    });
    html += `<text x="${EQUITY_CHART.labelX}" y="${EQUITY_CHART.labelY}" fill="#64748b" font-size="12" font-weight="600" text-anchor="middle">日期 / Time Series</text>`;
    if (previewOnly) {
      html += `<text x="${EQUITY_CHART.right}" y="${EQUITY_CHART.top + 14}" fill="#b45309" font-size="12" font-weight="600" text-anchor="end">样式预览，非真实回测</text>`;
    }

    if (backtestPath) {
      html += `<path d="${backtestPath}" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,4" stroke-linejoin="miter" stroke-linecap="butt" />`;
    }
    if (livePath) {
      html += `<path d="${livePath}" fill="none" stroke="#2563eb" stroke-width="1.5" stroke-linejoin="miter" stroke-linecap="butt" />`;
    }
    
    html += `<line x1="${cutoffX}" y1="${EQUITY_CHART.top}" x2="${cutoffX}" y2="${EQUITY_CHART.bottom}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4,4" />`;
    html += `<text x="${cutoffX + 8}" y="${EQUITY_CHART.top + 18}" fill="#64748b" font-size="12" font-weight="600">临界日</text>`;
    
    return html;
  } else {
    return `<text x="${EQUITY_CHART.labelX}" y="220" fill="#9ca3af" font-size="18" text-anchor="middle">等待策略回测数据</text>`;
  }
}

function generatePathFromEquity(equity, minVal, maxVal, offset, totalLength, logScale = false) {
  const points = [];
  const n = equity.length;
  const range = maxVal - minVal || 0.4;
  for (let i = 0; i < n; i++) {
    const x = equityX(offset + i, totalLength);
    let normalized;
    if (logScale) {
      const logMin = Math.log10(Math.max(minVal, 0.01));
      const logMax = Math.log10(Math.max(maxVal, 0.01));
      const logRange = logMax - logMin || 1;
      const logVal = Math.log10(Math.max(equity[i], 0.01));
      normalized = (logVal - logMin) / logRange;
    } else {
      normalized = (equity[i] - minVal) / range;
    }
    const y = equityY(equity[i], minVal, maxVal, logScale);
    points.push(`${x},${Math.max(EQUITY_CHART.top, Math.min(EQUITY_CHART.bottom, y))}`);
  }
  return points.length > 0 ? `M ${points.join(" L ")}` : "";
}

function renderRealEquityCurve(detailData, logScale = false) {
  return renderSegmentedEquityCurve(detailData, logScale);
}

function renderWaitingEquityCurve() {
  return `<text x="${EQUITY_CHART.labelX}" y="220" fill="#64748b" font-size="16" font-weight="600" text-anchor="middle">正在加载 Quant API 真实策略数据</text>`;
}

function renderSegmentedEquityCurve(detailData, logScale = false, strategyId = "") {
  const equityCurve = detailData.equity_curve || [];
  const cutoffDate = (detailData.params && detailData.params.cutoff_date) || "2024-06-01";
  const backtestGradientId = strategyId ? `backtestGradient_${strategyId}` : "backtestGradient";
  const liveGradientId = strategyId ? `liveGradient_${strategyId}` : "liveGradient";
  
  if (equityCurve.length === 0) {
    return `<text x="${EQUITY_CHART.labelX}" y="220" fill="#9ca3af" font-size="18" text-anchor="middle">等待策略回测数据</text>`;
  }
  
  const backtestData = equityCurve.filter(d => d.phase === "backtest");
  const liveData = equityCurve.filter(d => d.phase === "live");
  
  const backtestDates = backtestData.map(d => d.date);
  const backtestNav = backtestData.map(d => d.nav);
  const liveDates = liveData.map(d => d.date);
  const liveNav = liveData.map(d => d.nav);
  
  const allNav = [...backtestNav, ...liveNav];
  const validNav = allNav.filter(v => !isNaN(v) && v > 0);
  const minVal = Math.min(...validNav, 0.8);
  const maxVal = Math.max(...validNav, 1.2);
  const range = maxVal - minVal || 0.4;
  const totalLength = equityCurve.length;
  
  console.log(`[renderSegmentedEquityCurve] scale=${logScale ? 'log' : 'linear'}, minVal=${minVal}, maxVal=${maxVal}, range=${range}, totalLength=${totalLength}`);
  
  let html = "";
  
  html += `<line x1="${EQUITY_CHART.left}" y1="${EQUITY_CHART.top}" x2="${EQUITY_CHART.left}" y2="${EQUITY_CHART.bottom}" stroke="#e2e8f0" stroke-width="1" />`;
  html += `<line x1="${EQUITY_CHART.left}" y1="${EQUITY_CHART.bottom}" x2="${EQUITY_CHART.right}" y2="${EQUITY_CHART.bottom}" stroke="#e2e8f0" stroke-width="1" />`;
  
  let yTicks, yMin, yMax;
  if (logScale) {
    const logMin = Math.log10(Math.max(minVal, 0.01));
    const logMax = Math.log10(Math.max(maxVal, 0.01));
    yMin = Math.pow(10, Math.floor(logMin));
    yMax = Math.pow(10, Math.ceil(logMax));
    yTicks = [];
    let val = yMin;
    while (val <= yMax) {
      yTicks.push(val);
      val *= 2;
      if (val > yMax && yTicks.length < 5) val = yMin * 5;
    }
    yTicks = [...new Set(yTicks)].sort((a, b) => a - b).slice(0, 5);
  } else {
    yTicks = [minVal, minVal + range * 0.25, minVal + range * 0.5, minVal + range * 0.75, maxVal];
  }
  
  yTicks.forEach((val) => {
    const y = equityY(val, minVal, maxVal, logScale);
    html += `<line x1="${EQUITY_CHART.left}" y1="${y}" x2="${EQUITY_CHART.right}" y2="${y}" stroke="#f1f5f9" stroke-width="1" />`;
    html += `<line x1="${EQUITY_CHART.left - 8}" y1="${y}" x2="${EQUITY_CHART.left}" y2="${y}" stroke="#e2e8f0" stroke-width="1" />`;
    html += `<text x="${EQUITY_CHART.left - 14}" y="${y + 4}" fill="#64748b" font-size="12" text-anchor="end">${logScale ? val.toExponential(1) : val.toFixed(2)}</text>`;
  });
  
  const allDates = [...backtestDates, ...liveDates];
  const xTickIndexes = equityTickIndexes(allDates);
  html += `<line x1="${EQUITY_CHART.left}" y1="${EQUITY_CHART.tickBottom}" x2="${EQUITY_CHART.right}" y2="${EQUITY_CHART.tickBottom}" stroke="#e2e8f0" stroke-width="1" />`;
  [...new Set(xTickIndexes)].forEach((i) => {
    const x = equityX(i, totalLength);
    const date = allDates[i] || "";
    html += `<line x1="${x}" y1="${EQUITY_CHART.bottom}" x2="${x}" y2="${EQUITY_CHART.tickBottom}" stroke="#e2e8f0" stroke-width="1" />`;
    html += `<text x="${x}" y="${EQUITY_CHART.dateY}" fill="#64748b" font-size="11" text-anchor="middle">${escapeHtml(date || "-")}</text>`;
  });
  html += `<text x="${EQUITY_CHART.labelX}" y="${EQUITY_CHART.labelY}" fill="#64748b" font-size="12" font-weight="600" text-anchor="middle">日期 / Time Series</text>`;
  
  if (backtestNav.length > 0) {
    const backtestPath = generatePathFromEquity(backtestNav, minVal, maxVal, 0, totalLength, logScale);
    html += `<path d="${backtestPath}" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,4" stroke-linejoin="miter" stroke-linecap="butt" />`;
  }
  
  if (liveNav.length > 0) {
    const connectedLiveNav = backtestNav.length > 0 ? [backtestNav[backtestNav.length - 1], ...liveNav] : liveNav;
    const liveOffset = backtestNav.length > 0 ? backtestNav.length - 1 : 0;
    const livePath = generatePathFromEquity(connectedLiveNav, minVal, maxVal, liveOffset, totalLength, logScale);
    html += `<path d="${livePath}" fill="none" stroke="#2563eb" stroke-width="1.5" stroke-linejoin="miter" stroke-linecap="butt" />`;
  }
  
  const cutoffX = equityX(Math.min(totalLength - 1, backtestNav.length), totalLength);
  html += `<line x1="${cutoffX}" y1="${EQUITY_CHART.top}" x2="${cutoffX}" y2="${EQUITY_CHART.bottom}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4,4" />`;
  html += `<text x="${cutoffX + 8}" y="${EQUITY_CHART.top + 18}" fill="#64748b" font-size="12" font-weight="600">临界日 ${escapeHtml(cutoffDate)}</text>`;
  
  equityCurve.forEach((point, i) => {
    if (isNaN(point.nav) || point.nav <= 0) return;
    const y = equityY(point.nav, minVal, maxVal, logScale);
    const x = equityX(i, totalLength);
    const phaseLabel = point.phase === "backtest" ? "回测段" : "实测段";
    html += `<circle cx="${x}" cy="${y}" r="0" fill="${point.phase === "backtest" ? "#9ca3af" : "#2563eb"}" opacity="0" class="equity-point" data-date="${escapeHtml(point.date)}" data-nav="${point.nav.toFixed(4)}" data-phase="${phaseLabel}" />`;
  });
  
  return html;
}

function renderStrategyDetail() {
  const row = activeStrategy();
  if (!row) {
    closeStrategyDetail();
    return;
  }
  
  const rowDetailData = detailDataFromStrategyRow(row);
  const detailData = JSON.parse(JSON.stringify((state.strategyDetailData && state.strategyDetailData[row.id]) || rowDetailData || {}));
  const needsRemoteDetail = row.id.startsWith("strategy_run_") || row.id === "strategy_quant_api_default";
  if (needsRemoteDetail && (!Array.isArray(detailData.equity_curve) || detailData.equity_curve.length === 0)) {
    loadStrategyDetailData(row.id);
  }
  const metricsBacktest = detailData.metrics_backtest || {};
  const metricsLive = detailData.metrics_live || {};
  const params = detailData.params || {};
  const cutoffDate = params.cutoff_date || "2024-06-01";
  const equityCurve = detailData.equity_curve || [];
  const hasRealData = Array.isArray(equityCurve) && equityCurve.length > 0;
  const rowBacktest = row.backtestResult || row.backtest_result || {};
  const rowLive = row.liveResult || row.live_result || {};
  const hasRowEquity = normalizeEquityValues(rowBacktest.equity_curve || rowBacktest.equity || []).length > 0
    || normalizeEquityValues(rowLive.equity_curve || rowLive.equity || []).length > 0;
  const chartSourceLabel = hasRealData
    ? "真实数据"
    : hasRowEquity
      ? "真实数据"
      : "样式预览数据（非真实回测）";
  
  const navValues = equityCurve.map(d => d.nav);
  const navMin = navValues.length ? Math.min(...navValues) : 'N/A';
  const navMax = navValues.length ? Math.max(...navValues) : 'N/A';
  console.log(`[renderStrategyDetail] scale=${state.equityLogScale ? 'log' : 'linear'}, equity_curve.length=${equityCurve.length}, navMin=${navMin}, navMax=${navMax}, hasRealData=${hasRealData}`);
  
  renderView();
  els.strategyDetailView.innerHTML = `
    <div class="breadcrumb">
      <button type="button" class="breadcrumb-link" data-action="back-strategy">策略看板</button>
      <span>›</span>
      <strong>${escapeHtml(row.name)}</strong>
    </div>

    <section class="detail-hero">
      <div>
        <div class="detail-title-row">
          <h2>${escapeHtml(row.name)}</h2>
          <span class="badge ${row.status === "研究就绪" ? "badge-green" : "badge-gray"}">${escapeHtml(row.status)}</span>
        </div>
        <dl class="detail-meta">
          <div><dt>Strategy ID</dt><dd><code>${escapeHtml(row.id)}</code></dd></div>
          <div><dt>类型</dt><dd>${escapeHtml(detailData.type || row.type)}</dd></div>
          <div><dt>使用因子</dt><dd>${renderFactorTraceChips(detailData.factors ? detailData.factors.map(f => f.factor_id).join(', ') : row.factors)}</dd></div>
          <div><dt>股票池</dt><dd>${escapeHtml(params.universe || row.universe)}</dd></div>
          <div><dt>更新时间</dt><dd>${formatDate(row.updatedAt)}</dd></div>
        </dl>
      </div>
      <div class="detail-actions">
        <button type="button" class="secondary-action" data-action="back-strategy">返回策略看板</button>
        <button type="button" class="primary-action compact" disabled>导出策略报告（待接入）</button>
      </div>
    </section>

    <div class="metrics-group">
      <h3 class="metrics-group-title backtest-title">回测段（临界日之前）</h3>
      <section class="metric-grid strategy-metrics">
        <article class="metric-card"><span>年化收益</span><strong>${formatRatio(hasRealData ? metricsBacktest.annual_return : row.annualReturn)}</strong><small>回测段</small></article>
        <article class="metric-card"><span>夏普</span><strong>${formatNumber(hasRealData ? metricsBacktest.sharpe : row.sharpe, 2)}</strong><small>回测段</small></article>
        <article class="metric-card"><span>最大回撤</span><strong>${formatRatio(hasRealData ? metricsBacktest.max_drawdown : row.maxDrawdown)}</strong><small>回测段</small></article>
        <article class="metric-card"><span>换手率</span><strong>${formatRatio(hasRealData ? metricsBacktest.turnover : null)}</strong><small>回测段</small></article>
      </section>
    </div>

    <div class="metrics-group">
      <h3 class="metrics-group-title live-title">实测段（临界日之后）</h3>
      <section class="metric-grid strategy-metrics live-metrics">
        <article class="metric-card live"><span>年化收益</span><strong>${formatRatio(hasRealData ? metricsLive.annual_return : null)}</strong><small>实测段</small></article>
        <article class="metric-card live"><span>夏普</span><strong>${formatNumber(hasRealData ? metricsLive.sharpe : null, 2)}</strong><small>实测段</small></article>
        <article class="metric-card live"><span>最大回撤</span><strong>${formatRatio(hasRealData ? metricsLive.max_drawdown : null)}</strong><small>实测段</small></article>
        <article class="metric-card live"><span>换手率</span><strong>${formatRatio(hasRealData ? metricsLive.turnover : null)}</strong><small>实测段</small></article>
      </section>
    </div>

    <section class="research-settings">
      <div>
        <h3>策略研究与回测参数</h3>
        <p>${hasRealData ? "这些参数是真实回测使用的输入条件。" : "这些参数作为策略回测请求输入。"}</p>
      </div>
      <div class="research-grid">
        <label><span>开始日期</span><input type="date" value="${escapeHtml(params.start_date || "2023-01-01")}" class="research-input" /></label>
        <label><span>结束日期</span><input type="date" value="${escapeHtml(params.end_date || "2024-12-31")}" class="research-input" /></label>
        <label><span>临界日</span><input type="date" value="${escapeHtml(cutoffDate)}" class="research-input cutoff-date" /></label>
        <label><span>股票池</span><select class="research-input"><option>${escapeHtml(params.universe || row.universe)}</option></select></label>
        <label><span>组合构建</span><select class="research-input"><option>${escapeHtml(params.portfolio_construction || row.type + "研究")}</option></select></label>
        <label><span>调仓周期</span><select class="research-input"><option>${escapeHtml(params.rebalance || "月频调仓")}</option></select></label>
        <label><span>手续费及滑点</span><select class="research-input">
          <option value="无" ${(params.cost || row.cost) === "无" ? "selected" : ""}>无</option>
          <option value="3‰佣金+1‰印花税+无滑点" ${(params.cost || row.cost) === "3‰佣金+1‰印花税+无滑点" ? "selected" : ""}>3‰佣金+1‰印花税+无滑点</option>
          <option value="3‰佣金+1‰印花税+1‰滑点" ${(params.cost || row.cost) === "3‰佣金+1‰印花税+1‰滑点" ? "selected" : ""}>3‰佣金+1‰印花税+1‰滑点</option>
        </select></label>
      </div>
    </section>

    <section class="strategy-detail-grid">
      <article class="chart-card large-chart">
        <header>
          <strong>策略收益曲线 / Equity Curve</strong>
          <span>${escapeHtml(chartSourceLabel)}</span>
          <div class="chart-toggle">
            <button type="button" class="toggle-btn ${!state.equityLogScale ? "active" : ""}" data-equity-scale="linear">普通</button>
            <button type="button" class="toggle-btn ${state.equityLogScale ? "active" : ""}" data-equity-scale="log">Log</button>
          </div>
        </header>
        <div class="strategy-equity-chart" data-strategy-id="${escapeHtml(row.id)}">
          <svg viewBox="0 0 1600 520" class="equity-svg">
            <defs>
              <linearGradient id="backtestGradient_${escapeHtml(row.id)}" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:#94a3b8;stop-opacity:0.2" />
                <stop offset="100%" style="stop-color:#9ca3af;stop-opacity:0" />
              </linearGradient>
              <linearGradient id="liveGradient_${escapeHtml(row.id)}" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:0.3" />
                <stop offset="100%" style="stop-color:#3b82f6;stop-opacity:0" />
              </linearGradient>
            </defs>
            ${hasRealData ? renderSegmentedEquityCurve(detailData, state.equityLogScale, row.id) : renderWaitingEquityCurve()}
          </svg>
          <div class="chart-legend">
            <span><span class="legend-dot backtest"></span>回测段 (临界日前)</span>
            <span><span class="legend-dot live"></span>实测段 (临界日后)</span>
          </div>
        </div>
      </article>
      <article class="chart-card">
        <header><strong>风险指标</strong><span>${hasRealData ? "真实回测" : "等待 Volatility / Calmar"}</span></header>
        <div class="risk-metrics-grid">
          <div class="risk-item"><span>年化波动率(回测)</span><strong>${formatRatio(hasRealData ? metricsBacktest.annual_vol : null)}</strong></div>
          <div class="risk-item"><span>年化波动率(实测)</span><strong>${formatRatio(hasRealData ? metricsLive.annual_vol : null)}</strong></div>
          <div class="risk-item"><span>Calmar(回测)</span><strong>${formatNumber(hasRealData ? metricsBacktest.calmar : null, 2)}</strong></div>
          <div class="risk-item"><span>Calmar(实测)</span><strong>${formatNumber(hasRealData ? metricsLive.calmar : null, 2)}</strong></div>
        </div>
      </article>
      <article class="chart-card">
        <header><strong>使用因子</strong><span>${escapeHtml(detailData.factors ? detailData.factors.length : row.factors.split(',').length || 1)} 个</span></header>
        <div class="strategy-factor-chip-list">${renderFactorTraceChips(detailData.factors ? detailData.factors.map(f => f.factor_id).join(', ') : row.factors)}</div>
      </article>
    </section>
  `;

  els.strategyDetailView.querySelectorAll("[data-action='back-strategy']").forEach((button) => {
    button.addEventListener("click", closeStrategyDetail);
  });
  bindFactorTraceChips(els.strategyDetailView);
  
  els.strategyDetailView.querySelectorAll("[data-equity-scale]").forEach((button) => {
    button.addEventListener("click", (e) => {
      const scale = e.target.getAttribute("data-equity-scale");
      state.equityLogScale = scale === "log";
      renderStrategyDetail();
    });
  });
  
  els.strategyDetailView.querySelectorAll(".cutoff-date").forEach((input) => {
    input.addEventListener("change", (e) => {
      const newCutoff = e.target.value;
      if (detailData.params) {
        detailData.params.cutoff_date = newCutoff;
      }
      renderStrategyDetail();
    });
  });
}

function taskRows() {
  const builtInRows = [
    {
      id: "alpha101_reproduction",
      name: "Alpha101 复现任务",
      type: "复现",
      currentGate: "G2",
      progress: 60,
      status: "需关注",
      stages: [
        { gate: "G0", name: "输入与规格检查", status: "passed", note: "specs 与运行参数可读取" },
        { gate: "G1", name: "复现产物检查", status: "passed", note: "proof / evaluation summary 已生成" },
        { gate: "G2", name: "研究评估检查", status: "warning", note: "部分因子需要人工复核" },
        { gate: "G3", name: "策略回测检查", status: "pending", note: "策略层尚未接入" },
        { gate: "G4", name: "人工审核", status: "pending", note: "等待研究员确认" },
      ],
      artifacts: "proof_report.json / evaluation.json",
    },
    {
      id: "gtja191_reproduction",
      name: "GTJA191 因子库复现",
      type: "复现",
      currentGate: "G1",
      progress: 20,
      status: "运行中",
      stages: [
        { gate: "G0", name: "输入与规格检查", status: "passed", note: "因子列表已识别" },
        { gate: "G1", name: "复现产物检查", status: "running", note: "等待产物完整生成" },
        { gate: "G2", name: "研究评估检查", status: "pending", note: "预留子 Gate" },
        { gate: "G3", name: "策略回测检查", status: "pending", note: "预留子 Gate" },
        { gate: "G4", name: "人工审核", status: "pending", note: "预留子 Gate" },
      ],
      artifacts: "local report artifacts",
    },
    // AI Agent 调试占位暂时关闭。
    // {
    //   id: "ai_factor_mining",
    //   name: "AI Agent 因子挖掘候选流程",
    //   type: "挖掘",
    //   currentGate: "G0",
    //   progress: 0,
    //   status: "未实现",
    //   stages: [
    //     { gate: "G0", name: "候选因子登记", status: "pending", note: "未来接入 trial ledger" },
    //     { gate: "G1", name: "安全与泄漏检查", status: "pending", note: "预留子 Gate" },
    //     { gate: "G2", name: "复现与研究评估", status: "pending", note: "预留子 Gate" },
    //     { gate: "G3", name: "策略候选检查", status: "pending", note: "预留子 Gate" },
    //     { gate: "G4", name: "人工审核", status: "pending", note: "预留子 Gate" },
    //   ],
    //   artifacts: "待 Agent 提交",
    // },
  ];
  return ENABLE_AGENT_TASK_DEBUG ? [...agentTaskRows(), ...builtInRows] : builtInRows;
}

function agentTaskStatusMeta(task) {
  const status = String(task.status || "submitted");
  const map = {
    queued: { label: "等待 Agent", progress: 5, stageStatus: "running", appStatus: "运行中" },
    queued_for_trae: { label: "等待 Agent", progress: 10, stageStatus: "running", appStatus: "运行中" },
    submitted: { label: "已提交", progress: 8, stageStatus: "running", appStatus: "运行中" },
    running: { label: "运行中", progress: 45, stageStatus: "running", appStatus: "运行中" },
    waiting_final_approval: { label: "等待最终确认", progress: 92, stageStatus: "running", appStatus: "需关注" },
    failed: { label: "需关注", progress: 35, stageStatus: "warning", appStatus: "需关注" },
    rejected: { label: "已拒绝", progress: 100, stageStatus: "warning", appStatus: "需关注" },
    completed: { label: "已完成", progress: 100, stageStatus: "passed", appStatus: "已完成" },
  };
  return map[status] || { label: status, progress: 10, stageStatus: "running", appStatus: "运行中" };
}

function agentTaskRows() {
  return state.agentTasks.map((task) => {
    const meta = agentTaskStatusMeta(task);
    const summary = agentTaskSummary(task);
    const taskId = task.task_id || task.id || "agent-task";
    const artifacts = task.artifacts_dir || task.status_path || "local agent task artifacts";
    const progress = Number(task.progress ?? meta.progress);
    const stages = Array.isArray(task.gates) && task.gates.length
      ? task.gates.map((gate) => ({
          gate: gate.gate || "-",
          name: gate.name || gate.gate || "Gate",
          status: gate.status || "pending",
          note: gate.note || task.message || meta.label,
        }))
      : [
          {
            gate: "G0",
            name: "任务接收",
            status: "passed",
            note: `已写入任务队列：${taskId}`,
          },
          {
            gate: "G1",
            name: "Agent 执行",
            status: meta.stageStatus,
            note: task.message || meta.label,
          },
          {
            gate: "G2",
            name: "产物校验",
            status: meta.appStatus === "已完成" ? "passed" : "pending",
            note: "等待 request/status/artifacts 校验结果",
          },
          {
            gate: "G3",
            name: "入库审核",
            status: "pending",
            note: "quarantine 通过后进入正式因子库",
          },
        ];
    return {
      id: taskId,
      name: summary === "-" ? taskId : summary,
      type: (task.task_type === "truth_compare" || task.task_type === "factor_values_compare") ? "因子对比" : "研报复现",
      currentGate: task.current_gate || "G0",
      progress: Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : meta.progress,
      status: meta.appStatus,
      sourceStatus: task.status || "submitted",
      stages,
      artifacts,
    };
  });
}

function taskStatusBadge(status) {
  if (status === "运行中") return "badge-blue";
  if (status === "需关注") return "badge-orange";
  if (status === "已完成") return "badge-green";
  if (status === "运行中") return "badge-blue";
  if (status === "需关注") return "badge-orange";
  if (status === "已完成") return "badge-green";
  return "badge-gray";
}

function stageClass(status) {
  if (status === "passed") return "stage-passed";
  if (status === "running") return "stage-running";
  if (status === "warning") return "stage-warning";
  return "stage-pending";
}

function renderTaskStats(rows) {
  if (!els.taskStats) return;
  els.taskStats.innerHTML = [
    ["任务总数", rows.length, "支持大量任务滚动展示"],
    ["运行中", rows.filter((row) => row.status === "运行中").length, "当前正在推进的任务"],
    ["需关注", rows.filter((row) => row.status === "需关注").length, "Gate warning / failed"],
    ["待接入", rows.filter((row) => row.status === "未实现").length, "尚无真实执行数据"],
  ]
    .map(
      ([label, value, note]) => `
        <article class="monitor-stat-card">
          <span>${label}</span>
          <strong>${value}</strong>
          <small>${note}</small>
        </article>
      `,
    )
    .join("");
}

function renderTaskStagePanel(row) {
  if (!els.taskStagePanel || !row) return;
  els.taskStagePanel.innerHTML = `
    <header>
      <strong>${escapeHtml(row.name)}</strong>
      <span>${escapeHtml(row.type)} / CLI</span>
    </header>
    <div class="task-stage-list">
      ${row.stages
        .map(
          (stage) => `
            <article class="task-stage-card ${stageClass(stage.status)}">
              <span class="gate-pill">${escapeHtml(stage.gate)}</span>
              <div>
                <strong>${escapeHtml(stage.name)}</strong>
                <small>${escapeHtml(stage.note)}</small>
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
    <footer>
      <strong>关联产物</strong>
      <span>${escapeHtml(row.artifacts)}</span>
    </footer>
  `;
}

function renderTasks() {
  const rows = taskRows();
  renderTaskStats(rows);
  if (!els.taskTableBody) return;
  const activeRow = rows.find((row) => row.id === state.activeTaskId) || rows[0];
  state.activeTaskId = activeRow?.id || null;
  els.taskTableBody.innerHTML = rows
    .map(
      (row) => {
        const currentStage = row.stages.find((stage) => stage.gate === row.currentGate);
        const statusTitle = currentStage?.note || row.status;
        return `
          <tr class="${row.id === state.activeTaskId ? "selected" : ""}" data-task-id="${escapeHtml(row.id)}">
            <td><strong>${escapeHtml(row.name)}</strong></td>
            <td><span class="badge badge-gray">${escapeHtml(row.type)}</span></td>
            <td>${escapeHtml(row.currentGate)}</td>
            <td class="number">
              <div class="progress-track" aria-label="进度 ${row.progress}%">
                <span class="progress-fill" style="width: ${row.progress}%"></span>
              </div>
              <small>${row.progress}%</small>
            </td>
            <td><span class="badge ${taskStatusBadge(row.status)}" title="${escapeHtml(statusTitle)}">${escapeHtml(row.status)}</span></td>
          </tr>
        `;
      },
    )
    .join("");
  els.taskTableBody.onclick = (event) => {
    const rowEl = event.target.closest("[data-task-id]");
    if (!rowEl) return;
    state.activeTaskId = rowEl.dataset.taskId;
    renderTasks();
  };
  renderTaskStagePanel(activeRow);
}

function agentTaskSummary(task) {
  const instruction = String(task.instruction || "").trim();
  if (instruction) {
    return instruction.length > 34 ? `${instruction.slice(0, 34)}...` : instruction;
  }
  const fileNames = (task.files || []).map((file) => file.name).filter(Boolean);
  return fileNames.length ? fileNames.join(" / ") : "-";
}

function addPendingFiles(fileList) {
  const incoming = Array.from(fileList || []);
  incoming.forEach((file) => {
    const exists = state.pendingFiles.some(
      (item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified,
    );
    if (!exists) {
      state.pendingFiles.push(file);
    }
  });
  renderAgentTask();
}

function removePendingFile(index) {
  const [removed] = state.pendingFiles.splice(index, 1);
  if (removed?.file_id) pendingFileStore.delete(removed.file_id);
  renderAgentTask();
}

function clearPendingFiles() {
  state.pendingFiles = [];
  pendingFileStore.clear();
}

async function loadAgentTasks() {
  if (!ENABLE_AGENT_TASK_DEBUG) {
    state.agentTasks = [];
    state.agentTasksLoaded = true;
    return;
  }
  if (state.agentTasksLoaded) return;
  if (CLOUD_DEMO_MODE) {
    state.agentTasks = [
      {
        task_id: "demo-cloud-factor-review",
        status: "completed",
        instruction: "演示任务：复核样例因子的复现状态。",
        requested_at: "2026-07-06T00:00:00Z",
        message: "静态演示任务，真实执行需要连接云端后端。",
        is_placeholder: true,
        current_gate: "G2",
        progress: 100,
      },
    ];
    state.agentTasksLoaded = true;
    renderAgentTask();
    if (state.view === "tasks") renderTasks();
    return;
  }
  try {
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/agent-tasks`));
    if (!response.ok) return;
    const payload = await response.json();
    state.agentTasks = Array.isArray(payload.items) ? payload.items : [];
  } finally {
    state.agentTasksLoaded = true;
    renderAgentTask();
    if (state.view === "tasks") renderTasks();
  }
}

async function submitTaskRequest(payload) {
  if (!ENABLE_AGENT_TASK_DEBUG) {
    throw new Error("数据入口已关闭");
  }
  if (CLOUD_DEMO_MODE) {
    throw new Error("GitHub Pages demo mode is read-only. Deploy the Flask backend to enable Agent tasks.");
  }
  // TODO(backend agent ready):
  //   switch this isolated function to the real agent task endpoint if needed.
  //   submitAgentTask should not need to change.
  const response = await fetch(`${API_BASE}/agent-tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
  return await response.json();
}

function fileListFromInput(fileList) {
  return Array.from(fileList || [])
    .map((file, index) => {
      const fileId = `${Date.now()}-${index}-${file.name}-${file.size}-${file.lastModified || 0}`;
      pendingFileStore.set(fileId, file);
      return {
        file_id: fileId,
        name: file.name,
        relative_path: file.webkitRelativePath || file.name,
        size: file.size,
        type: file.type || "",
        last_modified: file.lastModified ? new Date(file.lastModified).toISOString() : null,
      };
    })
    .filter((file) => file.name);
}

function inferPackageName(files) {
  const firstPath = files.find((file) => file.relative_path?.includes("/"))?.relative_path || "";
  const root = firstPath.split("/").filter(Boolean)[0];
  if (root) return root;
  return "factor_intake_loose_files";
}

function inferTaskType(files) {
  const names = new Set(files.map((file) => file.name));
  if (names.has("factor_values.csv")) return "truth_compare";
  if (
    names.has("code.py") ||
    names.has("experiment_data.csv") ||
    names.has("paper.pdf") ||
    names.has("research_report.pdf") ||
    names.has("report.pdf")
  ) {
    return "research_reproduction";
  }
  return state.intakeTaskType;
}

function currentInputProfileSummary() {
  if (state.intakeTaskType === "truth_compare" || state.intakeTaskType === "factor_values_compare") {
    return {
      summary: "因子值对照：提交 factor_values.csv，Agent 统一整理成 factor_values_compare 可读结构。",
      tree: ["factor_intake_YYYYMMDD_name/", "  factor_values.csv"],
    };
  }
  return {
    summary: "研报自动复现：提交 code.py、experiment_data.csv、paper.pdf、research_report.pdf，Agent 统一整理成 research_report_reproduction 可读结构。",
    tree: [
      "factor_intake_YYYYMMDD_name/",
      "  code.py",
      "  experiment_data.csv",
      "  paper.pdf",
      "  research_report.pdf",
    ],
  };
}

function currentSkillContract() {
  if (state.intakeTaskType === "truth_compare") {
    return {
      title: "Agent Skill: truth_compare_v1",
      shortDescription: "标准真值对照入口。上传已有因子值，和库内标准真值逐点比较，并做重复因子检查。",
      skillText: `# Agent Skill: truth_compare_v1

## 0. Role
You are the Factor Lab truth-comparison Agent. Your task is to read one uploaded factor value file, compare it point-by-point against the standard truth values already stored in the factor library, check similarity against existing factors, and write machine-readable artifacts.

This entry answers:
- does the uploaded factor value match the library standard truth?
- is it a duplicate or near-duplicate of an existing factor?
- what are the overlap ratio, exact match ratio, max absolute error, and similarity metrics?

Do not promote anything into the official factor library. Write outputs under the task artifacts directory.

## 1. Input
Required:

~~~text
factor_intake_YYYYMMDD_name/
  factor_values.csv
~~~

Recommended metadata:

~~~json
{
  "task_type": "truth_compare",
  "skill_name": "truth_compare_v1",
  "factor_family": "alpha101|wq101|gtja191|exploratory",
  "factor_name": "string"
}
~~~

factor_values.csv must contain:

| column | required | rule |
| --- | --- | --- |
| date | yes | normalize to YYYY-MM-DD |
| symbol | yes | normalize to backend symbol format |
| factor_value | yes | finite numeric value |

## 2. Frozen Criteria
criteria.json is written by G0 and read-only downstream. Every gate must verify status.json.criteria_sha256 before running.

For this entry, standard truth is the primary gate:

~~~json
{
  "standard_truth": {
    "role": "primary_gate",
    "required": true,
    "source": "factor_library_truth",
    "missing_source_status": "not_comparable",
    "blocking": true
  }
}
~~~

If library truth is missing, write status=not_comparable and final decision reject. Do not mark it not_applicable.

## 3. Gates
G0 intake_validation:
- verify request.json and factor_values.csv
- identify factor_family and factor_name
- freeze criteria.json and sha256

G1 criteria_freeze:
- verify criteria hash
- fail with criteria_tampered if changed

G2 value_schema_check:
- validate date, symbol, factor_value
- normalize date/symbol/value

G3 data_quality_check:
- count invalid rows, duplicate keys, missing values
- write data_quality.json

G4 library_truth_lookup:
- locate library standard truth for factor_family + factor_name
- if unavailable, write standard_truth.status=not_comparable

G5 standard_truth_comparison:
- compare uploaded value and library truth point by point
- compute overlap_ratio, exact_match_ratio, max_abs_error
- passed iff overlap_ratio >= min_overlap_ratio and exact_match_ratio >= pass_exact_match_ratio and max_abs_error <= tolerance

G6 library_similarity:
- compare with existing factor library for duplicate / near-duplicate detection

G7 report_generation:
- write comparison_report.md

G8 final_approval:
- write final_decision.json

## 4. Decision Rule
accept iff standard_truth.status=passed and no blocking duplicate issue exists.

Missing library truth means not_comparable and reject. Low overlap means not_compared. Enough overlap but wrong values means failed.

## 5. Required Artifacts
~~~text
artifacts/
  criteria.json
  input_profile.json
  data_quality.json
  normalized_factor_values.parquet
  standard_truth_comparison.json
  library_similarity.json
  comparison_report.md
  final_decision.json
~~~`,
      note: "真值对照入口只处理已有因子值和库内标准真值的逐点对照。",
    };
  }
  if (state.intakeTaskType === "research_reproduction") {
    return {
      title: "Agent Skill: research_reproduction_v1",
      shortDescription: "研报论文复现入口。把研究材料转成可运行、可审核、可入库候选因子；真值只做可选诊断。",
      skillText: `# Agent Skill: research_reproduction_v1

## 0. Role
You are the Factor Lab research-reproduction Agent. Your task is to read one complete research package, reconstruct the factor, run it, evaluate economic usefulness, ask AMR to review it, compare it with the library, and produce artifacts for final approval.

This entry answers:
- can the research material be turned into a runnable factor?
- is the produced factor economically useful?
- does AMR find implementation or assumption risk?
- is it duplicate or near-duplicate with the existing library?

Standard truth is optional diagnostic evidence in this entry. It must not be the main promotion gate.

## 1. Input
Required:

~~~text
factor_intake_YYYYMMDD_name/
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf
~~~

Optional:

~~~text
truth_values.csv
truth_values.parquet
~~~

## 2. Frozen Criteria
criteria.json is written by G0 and read-only downstream. Every gate must verify status.json.criteria_sha256 before running.

For this entry, standard truth is optional:

~~~json
{
  "standard_truth": {
    "role": "optional_diagnostic",
    "required": false,
    "source": "optional_truth_values_or_library_truth",
    "missing_source_status": "not_applicable",
    "blocking": false
  }
}
~~~

Acceptance is based on economic validation, AMR review, and library comparison:

~~~text
accept iff
  economic_validation.status = passed
  and amr_review.status = passed
  and library_comparison.status != duplicate
~~~

## 3. Gates
G0 intake_validation:
- verify request.json
- verify the four fixed files exist
- freeze criteria.json and sha256

G1 criteria_freeze:
- verify criteria hash
- fail with criteria_tampered if changed

G2 document_parse:
- parse paper.pdf and research_report.pdf
- write parsed_paper.md and parsed_research_report.md

G3 factor_spec_extraction:
- extract formula, variables, frequency, universe, preprocessing, return horizon
- prefer research_report.pdf for production formula

G4 code_reconciliation:
- compare code.py with extracted formula
- record conflicts and assumptions

G5 data_binding:
- profile experiment_data.csv
- map variables to file columns or Quant API fields

G6 reproduction_run:
- write factor.py and test_factor.py
- run factor and write factor_values.parquet

G7 optional_truth_diagnostics:
- if no truth exists, write not_applicable
- if truth exists and matches, record stronger evidence
- if truth exists and does not match but economic validation passes, set needs_review because implementation or data mapping may be wrong
- if truth exists and matches but economic validation fails, record as correctly reproduced but economically decayed

G8 economic_validation:
- compute IC, RankIC, IR, long-short return, turnover, coverage, stability, sample-out evidence when available

G9 amr_review:
- review code, assumptions, data mapping, risk, and report consistency
- AMR may suggest patch but must not overwrite factor.py directly

G10 library_comparison:
- detect duplicate or near-duplicate factors

G11 report_generation:
- write reproduction_report.md

G12 final_approval:
- write final_decision.json
- do not promote directly to official library

## 4. Required Artifacts
~~~text
artifacts/
  criteria.json
  parsed_paper.md
  parsed_research_report.md
  extracted_formula.json
  assumptions.json
  data_profile.json
  factor.py
  test_factor.py
  factor_values.parquet
  optional_truth_diagnostics.json
  economic_validation.json
  amr_review.json
  library_comparison.json
  reproduction_report.md
  final_decision.json
~~~`,
      note: "研报复现入口不强制真值；真值只用于诊断和归因。",
    };
  }
  if (state.intakeTaskType === "truth_compare" || state.intakeTaskType === "factor_values_compare") {
    return {
      title: "Agent Skill：factor_values_compare_v1",
      shortDescription: "已配置因子值对照总 Skill。点击查看给智能体执行的完整 SOP、字段要求和后端输出目录。",
      skillText: `# Agent Skill: factor_values_compare_v1

## 0. Role and operating mode
You are the downstream Factor Lab intake Agent. Your task is to read one external factor value file, normalize it, compare it with the existing factor library, and produce machine-readable artifacts for final human approval.

Do not ask the user intermediate questions. If information is missing, make the least risky assumption, record it in artifacts/input_profile.json or artifacts/data_quality.json, and continue until a final_decision.json is produced.

Never write directly into the official factor library. All candidate results must stay under namespace=quarantine.

## 0.1 Frozen criteria
Truth comparison criteria must be resolved from the factor-family registry at G0 and frozen into artifacts/criteria.json. Downstream Agents may read criteria.json but must not modify it. G0 must compute sha256(criteria.json) and store it in status.json.criteria_sha256. Every downstream gate must recompute and compare this hash before running. If the hash differs, fail the gate with error=criteria_tampered.

truth_required and truth_file_present are independent:
| truth_required | truth_file_present | truth_status |
| --- | --- | --- |
| false | false/true | not_applicable |
| true | true | passed or failed |
| true | false | not_compared, blocking |

not_applicable may only be derived from truth_required=false. It must never be derived from a missing truth file.

Passed truth comparison requires all conditions:
overlap_ratio >= min_overlap_ratio
and exact_match_ratio >= pass_exact_match_ratio
and max_abs_error <= tolerance

If truth_required=true and coverage is below min_overlap_ratio, set truth_status=not_compared, never failed or passed. failed means enough overlap was compared but values did not match.

truth_required must come from registry, not from AMR:
- alpha101 / wq101 -> truth_required=true, criteria_source=registry:alpha101_v1
- gtja191 -> truth_required=true, criteria_source=registry:gtja191_v1
- exploratory -> truth_required=false, criteria_source=registry:exploratory_v1
- unknown factor_family -> criteria_status=failed, criteria_error=unknown_factor_family, truth_required=true, no accept

The sha256 mechanism detects accidental tampering such as an Agent overwriting criteria.json or a patch rerun carrying the wrong file. It is not an adversarial security boundary. For adversarial protection, store criteria_sha256 in a database table, append-only log, or read-only API that downstream Agents cannot write.

## 1. Fixed input package
Accept either a folder upload or direct file upload, but normalize both modes into this package model:

factor_intake_YYYYMMDD_name/
  factor_values.csv

Required file list is fixed:
- factor_values.csv

Reject or mark needs_review if factor_values.csv is missing. Extra files are allowed only as optional references; do not require them.

## 2. factor_values.csv hard format
File requirements:
- file name must be exactly factor_values.csv
- format must be CSV
- header row is required
- delimiter is comma
- preferred encoding is UTF-8
- GBK may be accepted only if parser can detect and decode it
- one row represents one symbol on one date

Required columns:
| column | type | required | normalization rule |
| --- | --- | --- | --- |
| date | string/date | yes | normalize to YYYY-MM-DD |
| symbol | string | yes | normalize to backend symbol format, e.g. 000001.SZ or 600000.SH |
| factor_value | number | yes | finite numeric value only |

Optional columns:
| column | type | required | usage |
| --- | --- | --- | --- |
| factor_name | string | no | candidate factor name; fallback to package_name |
| source_weight | number | no | optional confidence/weight; preserve in profile |
| is_valid | bool/int/string | no | false rows excluded from evaluation but counted in data quality |
| group | string | no | optional universe/group label |
| industry | string | no | optional grouping/neutralization label |
| note | string | no | optional row note; preserve but do not evaluate |

Accepted date examples:
- 2024-01-02
- 20240102
- 2024/01/02

Accepted boolean examples for is_valid:
- true/false
- 1/0
- yes/no
- y/n

## 3. Canonical request.json
The backend should persist this request shape. If fields are missing, fill defaults exactly as below.

~~~json
{
  "schema_version": "factor_intake_request_v1",
  "task_type": "factor_values_compare",
  "skill_name": "factor_values_compare_v1",
  "package": {
    "input_mode": "folder_or_files",
    "package_name": "factor_intake_YYYYMMDD_name",
    "required_files": ["factor_values.csv"],
    "files": [
      {
        "name": "factor_values.csv",
        "relative_path": "factor_intake_YYYYMMDD_name/factor_values.csv",
        "size": 0,
        "type": "text/csv",
        "last_modified": "ISO-8601-or-null"
      }
    ]
  },
  "namespace": "quarantine",
  "data_source": "quant_api",
  "requires_quant_api": true,
  "human_policy": {
    "interactive_questions": false,
    "human_only_final_approval": true
  }
}
~~~

## 4. Execution SOP
Run these steps in order and update status.json after each gate.

G0 intake_validation:
- Verify request.json exists.
- Verify task_type equals factor_values_compare.
- Verify skill_name equals factor_values_compare_v1.
- Verify package.required_files contains factor_values.csv.
- Verify factor_values.csv exists and is readable.
- Resolve the factor family from intake metadata, then freeze artifacts/criteria.json from registry. Do not let AMR choose truth_required or tolerance.
- If missing, set status=failed and write final_decision.json with decision=reject.

G1 criteria_freeze:
- Verify artifacts/criteria.json exists.
- Verify criteria_locked_by equals G0.
- Verify mutable_by_downstream_agent equals false.
- Recompute sha256(criteria.json) and compare with status.json.criteria_sha256.
- If mismatched, fail with error=criteria_tampered.
- This check must live in the unified gate entrypoint, not as an optional per-gate helper.
- If AMR thinks criteria are wrong, set needs_review. Do not edit criteria.

G2 value_schema_check:
- Decode CSV.
- Detect header.
- Confirm date, symbol, factor_value columns exist.
- Normalize column names by trimming whitespace and lowercasing.
- Do not silently rename unknown core columns. If date/symbol/factor_value are absent, record error.
- Normalize date to YYYY-MM-DD.
- Normalize symbol to the backend symbol format.
- Convert factor_value to float.

G3 data_quality_check:
- Count total rows, valid rows, invalid rows.
- Detect duplicate keys by date + symbol.
- Detect missing date, missing symbol, missing factor_value.
- Detect non-finite values: NaN, inf, -inf, empty string, null.
- Detect date span: min_date, max_date, number of trading dates.
- Detect symbol coverage: number of unique symbols, average symbols per date.
- Detect extreme values using robust z-score or percentile rules.
- If coverage is too low or values are mostly invalid, continue but set final decision to needs_review.

G4 truth_comparison:
- Read artifacts/criteria.json.
- If truth_required=false, write truth_status=not_applicable.
- If truth_required=true and truth_values.csv or registry truth source is missing, write truth_status=not_compared and block accept.
- If truth_required=true and truth is available, compare point by point.
- Set passed only if overlap_ratio, exact_match_ratio, and tolerance all pass.

G5 library_similarity:
- Load or query existing factor library metadata and values.
- Compare with existing factors when overlapping date/symbol data is available.
- Compute Pearson correlation, Spearman correlation, overlap ratio, and top matches.
- If values are not available for a library factor, record unavailable reason.

G6 metric_evaluation:
- Use quant_api returns if available.
- Calculate IC, RankIC, IC mean, IC std, IR, positive IC ratio.
- If return data is unavailable, write evaluation.status=skipped and explain why.
- Do not block final report only because return data is unavailable.

G7 report_generation:
- Generate comparison_report.md in Chinese.
- Include input summary, quality summary, top similar factors, evaluation metrics, risk notes, and recommendation.

G8 final_approval:
- Generate final_decision.json.
- Do not promote or write the factor to the official library.

## 5. Fixed output directory
All outputs must be written under:

runtime/factor_lab/agent_tasks/<task_id>/
  request.json
  status.json
  artifacts/
    criteria.json
    input_profile.json
    data_quality.json
    normalized_factor_values.parquet
    truth_comparison.json
    library_similarity.json
    evaluation.json
    comparison_report.md
    final_decision.json

## 6. Artifact schemas
artifacts/input_profile.json:
~~~json
{
  "schema_version": "factor_input_profile_v1",
  "task_type": "factor_values_compare",
  "factor_name": "string",
  "file_name": "factor_values.csv",
  "encoding": "utf-8|gbk|unknown",
  "row_count": 0,
  "valid_row_count": 0,
  "date_range": {"start": "YYYY-MM-DD-or-null", "end": "YYYY-MM-DD-or-null"},
  "symbol_count": 0,
  "columns": [],
  "optional_columns_detected": [],
  "assumptions": []
}
~~~

artifacts/data_quality.json:
~~~json
{
  "schema_version": "factor_data_quality_v1",
  "status": "passed|warning|failed",
  "duplicate_key_count": 0,
  "missing_date_count": 0,
  "missing_symbol_count": 0,
  "missing_factor_value_count": 0,
  "non_finite_value_count": 0,
  "invalid_is_valid_count": 0,
  "coverage": {"dates": 0, "symbols": 0, "avg_symbols_per_date": 0.0},
  "warnings": [],
  "errors": []
}
~~~

artifacts/library_similarity.json:
~~~json
{
  "schema_version": "factor_library_similarity_v1",
  "status": "passed|skipped|failed",
  "candidate_factor_name": "string",
  "top_matches": [
    {
      "factor_id": "string",
      "factor_name": "string",
      "pearson_corr": 0.0,
      "spearman_corr": 0.0,
      "overlap_ratio": 0.0,
      "recommendation": "reuse_existing|create_new|needs_review"
    }
  ],
  "notes": []
}
~~~

artifacts/evaluation.json:
~~~json
{
  "schema_version": "factor_evaluation_v1",
  "status": "passed|skipped|failed",
  "metrics": {
    "ic_mean": null,
    "rank_ic_mean": null,
    "ic_std": null,
    "ir": null,
    "positive_ic_ratio": null
  },
  "data_source": "quant_api",
  "notes": []
}
~~~

artifacts/final_decision.json:
~~~json
{
  "schema_version": "factor_final_decision_v1",
  "decision": "accept|reject|needs_review",
  "task_type": "factor_values_compare",
  "candidate_factor_name": "string",
  "library_action": "reuse_existing|create_new|reject|needs_review",
  "truth_status": "passed|failed|not_applicable|not_compared",
  "truth_required": false,
  "truth_blocking": false,
  "matched_existing_factors": [],
  "blocking_errors": [],
  "risk_notes": [],
  "human_approval_required": true
}
~~~

## 7. Decision rules
Use decision=reject when required file or required columns are missing, or factor_value is not usable.
Use decision=needs_review when data is partially usable, similarity is ambiguous, coverage is weak, or evaluation cannot be completed.
Use decision=accept only when schema passes, data quality is acceptable, similarity/evaluation are completed or reasonably skipped, and no blocking risk remains.

## 8. Non-negotiable rules
- Do not ask humans during intermediate steps.
- Never write directly to the official factor library.
- Always write final_decision.json.
- All uncertainty must be recorded in JSON artifacts, not hidden in logs.
- Do not invent missing factor values.
- Do not delete user input files.
- Keep all generated outputs inside the task directory.`,
      note: "因子值对照只有一个主文件，但后端输出必须落成固定任务目录和固定 artifacts。",
    };
  }
  return {
    title: "Agent Skill：research_report_reproduction_v1",
    shortDescription: "已配置研报自动复现总 Skill。点击查看给智能体执行的四文件研究包 SOP、固定字段和产物 schema。",
    skillText: `# Agent Skill: research_report_reproduction_v1

## 0. Role and operating mode
You are the downstream Factor Lab reproduction Agent. Your task is to read one complete research package, reconstruct the factor, bind data, run a reproducible experiment, compare the result with the existing factor library, and produce final artifacts for human approval.

The four required files are one combined research context. Do not treat them as four separate tasks.

Do not ask the user intermediate questions. If information is missing or contradictory, make a conservative assumption, record it in artifacts/assumptions.json, and continue. If the task cannot be completed, still write partial artifacts and final_decision.json.

Never write directly into the official factor library. All candidate results must stay under namespace=quarantine.

## 0.1 Frozen criteria
Truth comparison criteria must be resolved from the factor-family registry at G0 and frozen into artifacts/criteria.json. Downstream Agents may read criteria.json but must not modify it. G0 must compute sha256(criteria.json) and store it in status.json.criteria_sha256. Every downstream gate must recompute and compare this hash before running. If the hash differs, fail the gate with error=criteria_tampered.

criteria.json must come from the factor-family registry, not from AMR or ad hoc intake fields:
~~~json
{
  "schema_version": "factor_intake_criteria_v1",
  "truth_required": true,
  "truth_file_present": true,
  "tolerance": 1e-8,
  "min_overlap_ratio": 0.9,
  "pass_exact_match_ratio": 0.99,
  "criteria_source": "registry:alpha101_v1",
  "criteria_resolved_at": "G0",
  "criteria_locked_by": "G0",
  "mutable_by_downstream_agent": false
}
~~~

truth_required and truth_file_present are independent:
| truth_required | truth_file_present | truth_status |
| --- | --- | --- |
| false | false/true | not_applicable |
| true | true | passed or failed |
| true | false | not_compared, blocking |

not_applicable may only be derived from truth_required=false. It must never be derived from a missing truth file.

Passed truth comparison requires all conditions:
overlap_ratio >= min_overlap_ratio
and exact_match_ratio >= pass_exact_match_ratio
and max_abs_error <= tolerance

If truth_required=true and coverage is below min_overlap_ratio, set truth_status=not_compared, never failed or passed. failed means enough overlap was compared but values did not match.

truth_required must come from registry, not from AMR:
- alpha101 / wq101 -> truth_required=true, criteria_source=registry:alpha101_v1
- gtja191 -> truth_required=true, criteria_source=registry:gtja191_v1
- exploratory -> truth_required=false, criteria_source=registry:exploratory_v1
- unknown factor_family -> criteria_status=failed, criteria_error=unknown_factor_family, truth_required=true, no accept

The sha256 mechanism detects accidental tampering such as an Agent overwriting criteria.json or a patch rerun carrying the wrong file. It is not an adversarial security boundary. For adversarial protection, store criteria_sha256 in a database table, append-only log, or read-only API that downstream Agents cannot write.

## 1. Fixed input package
The user submits exactly one main folder:

factor_intake_YYYYMMDD_name/
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf

Required file list is fixed:
- code.py
- experiment_data.csv
- paper.pdf
- research_report.pdf

File names are part of the contract. Do not guess alternative names. If a required file is missing, write a failed final_decision.json.

Optional extra files may exist under optional/ or references/. They may be read only after the four required files are processed. Optional files must never replace the required files.

## 2. Required file semantics
| file_name | required | purpose | exact handling |
| --- | --- | --- | --- |
| code.py | yes | reference implementation | read first as code evidence; if empty or placeholder, record no_original_code=true |
| experiment_data.csv | yes | local data or sample data | profile columns, dates, symbols, available raw fields, calculated factor values if any |
| paper.pdf | yes | academic/method source | extract theory, variables, formulas, definitions, experiment design |
| research_report.pdf | yes | broker/internal report | extract final factor expression, empirical assumptions, charts, tables, conclusions |

## 3. experiment_data.csv accepted schema
CSV requirements:
- delimiter: comma
- header: required
- preferred encoding: UTF-8
- GBK allowed only if auto-detected
- one row should represent one symbol on one date if panel data is present

Core columns:
| column | type | required | meaning |
| --- | --- | --- | --- |
| date | string/date | recommended | trading date, normalize to YYYY-MM-DD |
| symbol | string | recommended | security identifier, normalize to backend symbol format |
| factor_value | number | optional | precomputed factor value; required only if CSV is submitted as calculated factor data |

Recommended raw panel columns:
| column | type | usage |
| --- | --- | --- |
| open | number | price feature |
| high | number | price feature |
| low | number | price feature |
| close | number | price feature |
| vwap | number | price feature |
| volume | number | volume feature |
| amount | number | turnover amount |
| ret | number | return feature |
| turnover | number | liquidity feature |
| market_cap | number | size neutralization/control |
| industry | string | industry neutralization/group |

Column mapping rules:
- Trim whitespace from headers.
- Preserve original column names in data_profile.json.
- Map common aliases only when unambiguous, e.g. ticker -> symbol, trade_date -> date, sec_code -> symbol.
- If a required variable from the extracted formula is missing, try quant_api before failing.
- Every alias mapping must be recorded in data_profile.json.
- Every missing field filled from quant_api must be recorded in assumptions.json.

## 4. Canonical request.json
The backend should persist this request shape. If fields are missing, fill defaults exactly as below.

~~~json
{
  "schema_version": "factor_intake_request_v1",
  "task_type": "research_report_reproduction",
  "skill_name": "research_report_reproduction_v1",
  "package": {
    "input_mode": "folder",
    "package_name": "factor_intake_YYYYMMDD_name",
    "required_files": [
      "code.py",
      "experiment_data.csv",
      "paper.pdf",
      "research_report.pdf"
    ],
    "files": [
      {"name": "code.py", "relative_path": "factor_intake_YYYYMMDD_name/code.py", "type": "text/x-python"},
      {"name": "experiment_data.csv", "relative_path": "factor_intake_YYYYMMDD_name/experiment_data.csv", "type": "text/csv"},
      {"name": "paper.pdf", "relative_path": "factor_intake_YYYYMMDD_name/paper.pdf", "type": "application/pdf"},
      {"name": "research_report.pdf", "relative_path": "factor_intake_YYYYMMDD_name/research_report.pdf", "type": "application/pdf"}
    ]
  },
  "namespace": "quarantine",
  "data_source": "quant_api",
  "requires_quant_api": true,
  "human_policy": {
    "interactive_questions": false,
    "human_only_final_approval": true
  }
}
~~~

## 5. Execution SOP
Run these gates in order. After each gate, update status.json with gate, status, progress, message, updated_at.

G0 intake_validation:
- Verify request.json exists.
- Verify task_type equals research_report_reproduction.
- Verify skill_name equals research_report_reproduction_v1.
- Verify all four required files exist with exact names.
- Verify files can be opened.
- Resolve the factor family from intake metadata, then freeze artifacts/criteria.json from registry. Do not let AMR choose truth_required, tolerance, min_overlap_ratio, or pass_exact_match_ratio.
- Create artifacts/ if missing.
- If any required file is missing, write final_decision.json with decision=reject and stop.

G1 criteria_freeze:
- Verify artifacts/criteria.json exists.
- Verify criteria_locked_by equals G0.
- Verify mutable_by_downstream_agent equals false.
- Recompute sha256(criteria.json) and compare with status.json.criteria_sha256.
- If mismatched, fail with error=criteria_tampered.
- This check must live in the unified gate entrypoint, not as an optional per-gate helper.
- If AMR thinks criteria are wrong, set needs_review. Do not edit criteria.

G2 document_parse:
- Extract text from paper.pdf into artifacts/parsed_paper.md.
- Extract text from research_report.pdf into artifacts/parsed_research_report.md.
- Preserve page references when possible.
- Extract tables if possible and summarize them under a Tables section.
- If OCR/table parsing fails, continue with available text and record parser limitations in assumptions.json.

G3 factor_spec_extraction:
- From parsed_paper.md and parsed_research_report.md, extract:
  - factor name
  - formula
  - variables and meanings
  - data frequency
  - stock universe
  - sample interval
  - rebalance frequency
  - preprocessing: winsorization, standardization, neutralization
  - ranking direction: higher_is_better, lower_is_better, unknown
  - return horizon and evaluation metric
- Prefer research_report.pdf for final production formula.
- Use paper.pdf for theoretical definition and variable meaning.
- If formula differs between paper and report, record conflict in extracted_formula.json.source_conflicts and assumptions.json.

G4 code_reconciliation:
- Read code.py.
- Identify exposed functions, formula logic, rolling windows, lags, ranking, neutralization, and data dependencies.
- Compare code.py against extracted_formula.json.
- If code.py and documents conflict:
  - prefer explicit final formula in research_report.pdf
  - use code.py to resolve implementation details only when report is ambiguous
  - record every conflict and resolution in assumptions.json
- If code.py is empty/placeholder, generate implementation from extracted formula.

G5 data_binding:
- Read experiment_data.csv.
- Build data_profile.json with row count, column list, date range, symbol coverage, missing values.
- Map formula variables to CSV columns or quant_api fields.
- Pull missing standard market fields from quant_api if requires_quant_api=true.
- Do not invent unavailable variables. If a variable cannot be sourced, mark reproduction_status=partial or failed.

G6 reproduction_run:
- Write artifacts/factor.py.
- Write artifacts/test_factor.py.
- The generated factor.py must expose a callable function named compute_factor(panel).
- compute_factor(panel) must return a table indexed or columned by date and symbol with one factor_value column.
- Run tests on sample data when possible.
- Produce artifacts/factor_values.parquet.
- If execution fails, save error traceback summary in assumptions.json and final_decision.json.
- If AMR later outputs suggested_patch.diff, do not auto-apply it. A human must approve the patch, and the approved patch starts a new attempt with parent_task_id and patch_source=amr.

G7 truth_comparison:
- Read artifacts/criteria.json.
- If truth_required=false, write truth_status=not_applicable.
- If truth_required=true and truth_values.csv or registry truth source is missing, write truth_status=not_compared and block accept.
- If truth_required=true and truth is available, compare reproduced factor values point by point.
- Set passed only if overlap_ratio, exact_match_ratio, and tolerance all pass.
- Coverage below min_overlap_ratio cannot pass.

G8 library_comparison:
- Compare reproduced factor values with existing factor library when overlap exists.
- Compute Pearson correlation, Spearman correlation, overlap ratio, and top matches.
- If library values are unavailable, write library_comparison.status=skipped with reason.

G9 report_generation:
- Write reproduction_report.md in Chinese.
- Include source summary, extracted formula, assumptions, data mapping, reproduction result, evaluation, library comparison, and final recommendation.

G10 final_approval:
- Write final_decision.json.
- Do not promote to official factor library.
- Human must see raw evidence before AMR recommendation: source files, Hermes raw outputs, factor.py, test_factor.py, factor_values.parquet sample, evaluation.json, truth_comparison.json, and library_comparison.json. Show AMR recommendation last or collapsed.

## 6. Fixed output directory
All outputs must be written under:

runtime/factor_lab/agent_tasks/<task_id>/
  request.json
  status.json
  artifacts/
    criteria.json
    parsed_paper.md
    parsed_research_report.md
    normalized_report.md
    extracted_formula.json
    assumptions.json
    data_profile.json
    factor.py
    test_factor.py
    factor_values.parquet
    truth_comparison.json
    evaluation.json
    library_comparison.json
    reproduction_report.md
    final_decision.json

## 7. Artifact schemas
artifacts/extracted_formula.json:
~~~json
{
  "schema_version": "factor_formula_v1",
  "factor_name": "string",
  "formula": "string",
  "formula_source": "research_report|paper|code|inferred",
  "variables": [
    {"name": "string", "meaning": "string", "source": "paper|research_report|code|inferred", "required": true}
  ],
  "frequency": "daily|weekly|monthly|unknown",
  "universe": "string_or_unknown",
  "sample_period": {"start": "YYYY-MM-DD-or-null", "end": "YYYY-MM-DD-or-null"},
  "preprocessing": {
    "winsorize": "string_or_null",
    "standardize": "string_or_null",
    "neutralize": "string_or_null"
  },
  "rebalance_rule": "string_or_unknown",
  "ranking_direction": "higher_is_better|lower_is_better|unknown",
  "return_horizon": "string_or_unknown",
  "source_conflicts": []
}
~~~

artifacts/assumptions.json:
~~~json
{
  "schema_version": "factor_assumptions_v1",
  "no_original_code": false,
  "document_parse_limitations": [],
  "formula_conflicts": [],
  "code_conflicts": [],
  "data_substitutions": [],
  "missing_variables": [],
  "implementation_assumptions": [],
  "blocking_errors": []
}
~~~

artifacts/data_profile.json:
~~~json
{
  "schema_version": "factor_data_profile_v1",
  "file_name": "experiment_data.csv",
  "encoding": "utf-8|gbk|unknown",
  "row_count": 0,
  "columns_original": [],
  "columns_normalized": [],
  "column_mappings": [],
  "date_range": {"start": "YYYY-MM-DD-or-null", "end": "YYYY-MM-DD-or-null"},
  "symbol_count": 0,
  "missing_summary": {},
  "quant_api_fields_used": []
}
~~~

artifacts/evaluation.json:
~~~json
{
  "schema_version": "factor_evaluation_v1",
  "status": "passed|skipped|failed",
  "metrics": {
    "ic_mean": null,
    "rank_ic_mean": null,
    "ic_std": null,
    "ir": null,
    "positive_ic_ratio": null,
    "turnover": null
  },
  "sample_period": {"start": "YYYY-MM-DD-or-null", "end": "YYYY-MM-DD-or-null"},
  "notes": []
}
~~~

artifacts/library_comparison.json:
~~~json
{
  "schema_version": "factor_library_comparison_v1",
  "status": "passed|skipped|failed",
  "top_matches": [
    {
      "factor_id": "string",
      "factor_name": "string",
      "pearson_corr": 0.0,
      "spearman_corr": 0.0,
      "overlap_ratio": 0.0,
      "recommendation": "reuse_existing|create_new|needs_review"
    }
  ],
  "notes": []
}
~~~

artifacts/final_decision.json:
~~~json
{
  "schema_version": "factor_final_decision_v1",
  "decision": "accept|reject|needs_review",
  "task_type": "research_report_reproduction",
  "candidate_factor_name": "string",
  "reproduction_status": "success|partial|failed",
  "library_action": "reuse_existing|create_new|reject|needs_review",
  "truth_status": "passed|failed|not_applicable|not_compared",
  "truth_required": true,
  "truth_blocking": true,
  "matched_existing_factors": [],
  "key_assumptions": [],
  "blocking_errors": [],
  "risk_notes": [],
  "human_approval_required": true
}
~~~

## 8. Decision rules
Use decision=reject when required files are missing, documents cannot be read at all, no formula can be extracted, or the factor cannot be computed.
Use decision=needs_review when formula is partial, assumptions are material, data is incomplete, evaluation is skipped, or library similarity is ambiguous.
Use decision=accept only when the factor was computed, tests passed, evaluation/library comparison completed or reasonably skipped, and no blocking risk remains.

## 9. Non-negotiable rules
- Treat the four files as one research context.
- Do not ask humans during intermediate steps.
- Never write directly to the official factor library.
- Always write final_decision.json.
- All uncertainty must be recorded in JSON artifacts, not hidden in logs.
- Do not invent missing market data or factor values.
- Do not delete user input files.
- Keep all generated outputs inside the task directory.`,
    note: "四个文件合起来是一份研报复现输入包，Agent 只按这一份总 skill 处理。",
  };
}

function renderCurrentSkillContract() {
  const contract = currentSkillContract();
  return `
    <div class="intake-skill-card">
      <div>
        <strong>${escapeHtml(contract.title)}</strong>
        <span>${escapeHtml(contract.shortDescription)}</span>
      </div>
      <button type="button" class="text-button" data-open-skill-contract>查看契约</button>
    </div>
  `;
}

function closeSkillContractModal() {
  document.querySelector(".skill-contract-modal")?.remove();
}

function openSkillContractModal() {
  const contract = currentSkillContract();
  closeSkillContractModal();
  const modal = document.createElement("div");
  modal.className = "skill-contract-modal";
  modal.innerHTML = `
    <div class="file-preview-backdrop" data-skill-contract-close></div>
    <section class="skill-contract-panel" role="dialog" aria-modal="true" aria-label="Agent Skill 契约">
      <header>
        <div>
          <strong>${escapeHtml(contract.title)}</strong>
          <span>${escapeHtml(contract.note)}</span>
        </div>
        <div class="skill-contract-actions">
          <button type="button" class="text-button" data-skill-contract-copy>复制契约</button>
          <button type="button" class="text-button" data-skill-contract-close>关闭</button>
        </div>
      </header>
      <pre>${escapeHtml(contract.skillText)}</pre>
    </section>
  `;
  document.body.appendChild(modal);
  modal.querySelectorAll("[data-skill-contract-close]").forEach((button) => {
    button.addEventListener("click", closeSkillContractModal);
  });
  modal.querySelector("[data-skill-contract-copy]")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(contract.skillText);
      showToast("契约已复制");
    } catch (error) {
      showToast("复制失败，请手动选择文本");
    }
  });
}

function closeFilePreview() {
  document.querySelector(".file-preview-modal")?.remove();
  if (activePreviewUrl) {
    URL.revokeObjectURL(activePreviewUrl);
    activePreviewUrl = null;
  }
}

function renderFilePreview(file, bodyHtml) {
  closeFilePreview();
  const modal = document.createElement("div");
  modal.className = "file-preview-modal";
  modal.innerHTML = `
    <div class="file-preview-backdrop" data-file-preview-close></div>
    <section class="file-preview-panel" role="dialog" aria-modal="true" aria-label="文件预览">
      <header>
        <div>
          <strong>${escapeHtml(file.name)}</strong>
          <span>${escapeHtml(file.type || "unknown")} · ${formatFileSize(file.size)}</span>
        </div>
        <button type="button" class="text-button" data-file-preview-close>关闭</button>
      </header>
      <div class="file-preview-body">${bodyHtml}</div>
    </section>
  `;
  document.body.appendChild(modal);
  modal.querySelectorAll("[data-file-preview-close]").forEach((button) => {
    button.addEventListener("click", closeFilePreview);
  });
}

function previewPendingFile(fileId) {
  const file = pendingFileStore.get(fileId);
  if (!file) {
    showToast("文件已不可用，请重新选择");
    return;
  }
  const type = file.type || "";
  const lowerName = file.name.toLowerCase();
  if (type.startsWith("image/")) {
    activePreviewUrl = URL.createObjectURL(file);
    renderFilePreview(file, `<img class="file-preview-image" src="${activePreviewUrl}" alt="${escapeHtml(file.name)}" />`);
    return;
  }
  if (type === "application/pdf" || lowerName.endsWith(".pdf")) {
    activePreviewUrl = URL.createObjectURL(file);
    renderFilePreview(file, `<iframe class="file-preview-frame" src="${activePreviewUrl}" title="${escapeHtml(file.name)}"></iframe>`);
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const text = String(reader.result || "");
    renderFilePreview(file, `<pre>${escapeHtml(text.slice(0, 200000))}</pre>`);
  };
  reader.onerror = () => showToast("文件读取失败");
  reader.readAsText(file);
}

async function submitAgentTask() {
  if (!ENABLE_AGENT_TASK_DEBUG) return;
  const files = state.pendingFiles;
  if (!files.length) {
    showToast(AGENT_TASK_TEXT.emptyWarning);
    return;
  }
  const taskType = inferTaskType(files);
  const packageName = inferPackageName(files);
  const skillName =
    taskType === "truth_compare" ? "truth_compare_v1" : "research_reproduction_v1";
  const requiredFiles =
    taskType === "truth_compare"
      ? ["factor_values.csv"]
      : ["code.py", "experiment_data.csv", "paper.pdf", "research_report.pdf"];

  const payload = {
    schema_version: "factor_intake_request_v1",
    task_type: taskType,
    skill_name: skillName,
    instruction:
      (taskType === "truth_compare"
        ? "请将外部因子值与当前因子库做对比，中间不要询问用户，最终给出复用和入库建议。"
        : "请按数据入口契约读取 code.py、experiment_data.csv、paper.pdf、research_report.pdf，自动复现研报因子，中间不要询问用户，最终给出入库建议。"),
    package: {
      input_mode: state.intakeInputMode,
      package_name: packageName,
      required_files: requiredFiles,
      files,
    },
    files,
    namespace: "quarantine",
    data_source: "quant_api",
    requires_quant_api: true,
    human_policy: {
      interactive_questions: false,
      human_only_final_approval: true,
    },
    requested_at: new Date().toISOString(),
  };

  state.agentTaskSubmitting = true;
  renderAgentTask();
  try {
    const result = await submitTaskRequest(payload);
    state.agentTasks.unshift({ ...payload, ...result });
    clearPendingFiles();
    showToast(AGENT_TASK_TEXT.submittedToast);
  } catch (error) {
    showToast(`Submit failed: ${error.message}`);
  } finally {
    state.agentTaskSubmitting = false;
    renderAgentTask();
    if (state.view === "tasks") renderTasks();
  }
}

function openAgentTaskProgress(taskId) {
  state.view = "tasks";
  state.activeTaskId = taskId;
  window.location.hash = `task=${encodeURIComponent(taskId)}`;
  renderView();
}

async function deleteAgentTask(taskId) {
  if (!taskId) return;
  if (CLOUD_DEMO_MODE) {
    showToast("GitHub Pages demo mode is read-only");
    return;
  }
  const ok = window.confirm(`删除任务 ${taskId}？这会同时删除本地 request.json、status.json 和 artifacts 目录。`);
  if (!ok) return;

  try {
    const response = await fetch(`${API_BASE}/agent-tasks/${encodeURIComponent(taskId)}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `HTTP ${response.status}`);
    }
    state.agentTasks = state.agentTasks.filter((task) => task.task_id !== taskId);
    if (state.activeTaskId === taskId) {
      state.activeTaskId = state.agentTasks[0]?.task_id || null;
    }
    showToast("任务已删除");
    renderAgentTask();
    if (state.view === "tasks") renderTasks();
  } catch (error) {
    showToast(`Delete failed: ${error.message}`);
  }
}

async function deleteAgentTaskById(taskId) {
  if (CLOUD_DEMO_MODE) {
    throw new Error("GitHub Pages demo mode is read-only");
  }
  const response = await fetch(`${API_BASE}/agent-tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
}

async function deleteSelectedAgentTasks() {
  const taskIds = [...state.selectedAgentTaskIds];
  if (!taskIds.length) return;
  const ok = window.confirm(`删除所选 ${taskIds.length} 个任务？这会同时删除本地 request.json、status.json 和 artifacts 目录。`);
  if (!ok) return;

  try {
    await Promise.all(taskIds.map(deleteAgentTaskById));
    state.agentTasks = state.agentTasks.filter((task) => !state.selectedAgentTaskIds.has(task.task_id));
    if (state.activeTaskId && state.selectedAgentTaskIds.has(state.activeTaskId)) {
      state.activeTaskId = state.agentTasks[0]?.task_id || null;
    }
    state.selectedAgentTaskIds.clear();
    showToast("任务已删除");
    renderAgentTask();
    if (state.view === "tasks") renderTasks();
  } catch (error) {
    showToast(`Delete failed: ${error.message}`);
  }
}

async function openAgentTaskFolder(taskId) {
  if (!taskId) return;
  if (CLOUD_DEMO_MODE) {
    showToast("GitHub Pages demo mode cannot open local folders");
    return;
  }
  try {
    const response = await fetch(`${API_BASE}/agent-tasks/${encodeURIComponent(taskId)}/open-folder`, {
      method: "POST",
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `HTTP ${response.status}`);
    }
    showToast("已打开任务文件夹");
  } catch (error) {
    showToast(`Open folder failed: ${error.message}`);
  }
}

function renderAgentTask() {
  if (!ENABLE_AGENT_TASK_DEBUG) return;
  if (!els.agentTaskView) return;
  const inputProfile = currentInputProfileSummary();
  const pendingFileRows = state.pendingFiles
    .slice(0, 8)
    .map(
      (file) => `
        <li class="agent-file-item">
          <span>
            <strong>${escapeHtml(file.relative_path || file.name)}</strong>
            <small>${escapeHtml(file.type || "unknown")} · ${formatFileSize(file.size)}</small>
          </span>
          <span class="agent-file-actions">
            <button type="button" class="text-button" data-pending-file-preview="${escapeHtml(file.file_id || "")}">查看</button>
            <button type="button" class="text-button danger" data-pending-file-remove="${state.pendingFiles.indexOf(file)}">删除</button>
          </span>
        </li>
      `,
    )
    .join("");
  const pendingFileExtra =
    state.pendingFiles.length > 8
      ? `<li class="agent-file-item"><span><strong>还有 ${state.pendingFiles.length - 8} 个文件</strong><small>运行时会一并写入 request.json 文件清单</small></span></li>`
      : "";
  const taskRows = state.agentTasks
    .map(
      (task) => `
        <tr class="${state.selectedAgentTaskIds.has(task.task_id) ? "selected" : ""}" data-agent-task-row="${escapeHtml(task.task_id)}" title="双击打开任务文件夹">
          <td>
            <input type="checkbox" data-agent-task-select="${escapeHtml(task.task_id)}" ${state.selectedAgentTaskIds.has(task.task_id) ? "checked" : ""} aria-label="选择 ${escapeHtml(task.task_id)}" />
          </td>
          <td><code class="agent-task-id" title="${escapeHtml(task.task_id)}">${escapeHtml(task.task_id)}</code></td>
          <td class="agent-task-summary" title="${escapeHtml(agentTaskSummary(task))}">${escapeHtml(agentTaskSummary(task))}</td>
          <td>
            <span class="badge badge-gray">${escapeHtml(task.status || "submitted")}</span>
            ${task.is_placeholder ? '<span class="badge badge-gray">\u6f14\u793a</span>' : ""}
          </td>
          <td>${formatDate(task.requested_at)}</td>
          <td>
            <div class="agent-task-actions">
              <button type="button" class="text-button" data-agent-task-progress="${escapeHtml(task.task_id)}">\u67e5\u770b\u8fdb\u5ea6</button>
              <button type="button" class="text-button danger" data-agent-task-delete="${escapeHtml(task.task_id)}">删除</button>
            </div>
          </td>
        </tr>
      `,
    )
    .join("");

  els.agentTaskView.innerHTML = `
    <section class="monitor-head">
      <div>
        <h2>${AGENT_TASK_TEXT.title}</h2>
        <p>${AGENT_TASK_TEXT.subtitle}</p>
      </div>
      <div class="monitor-note">
        <strong>${AGENT_TASK_TEXT.boundaryTitle}</strong>
        <span>${AGENT_TASK_TEXT.boundary}</span>
      </div>
    </section>

    <section class="agent-task-card">
      <div class="agent-task-pending-banner">
        <strong>执行边界</strong>
        <span>任务由平台后端执行；浏览器内不上传大文件、不运行 Agent、不写正式因子库。</span>
      </div>

      <div class="agent-intake-mode">
        <button type="button" class="${state.intakeTaskType === "research_reproduction" || state.intakeTaskType === "research_report_reproduction" ? "active" : ""}" data-intake-type="research_reproduction">研报自动复现</button>
        <button type="button" class="${state.intakeTaskType === "truth_compare" || state.intakeTaskType === "factor_values_compare" ? "active" : ""}" data-intake-type="truth_compare">因子值对照</button>
      </div>

      ${renderCurrentSkillContract()}

      <div class="agent-drop-zone" id="agentDropZone">
        <input id="agentFolderInput" type="file" webkitdirectory directory multiple hidden />
        <input id="agentFileInput" type="file" multiple hidden />
        <div>
          <strong>拖入或点击选择文件</strong>
          <span>${escapeHtml(inputProfile.summary)}</span>
        </div>
        <div class="agent-drop-actions">
          <button type="button" class="text-button" id="chooseFolderButton">选择文件夹</button>
          <button type="button" class="text-button" id="chooseFilesButton">选择文件</button>
        </div>
      </div>

      <ul class="agent-file-list">
        ${
          pendingFileRows ||
          `<li class="agent-file-item"><span><strong>等待数据包</strong><small>${escapeHtml(inputProfile.tree.join(" / "))}</small></span></li>`
        }
        ${pendingFileExtra}
      </ul>

      <div class="agent-task-foot">
        <span>${AGENT_TASK_TEXT.quarantineHint}</span>
        <button type="button" class="text-button danger" id="clearPendingFilesButton" ${state.pendingFiles.length ? "" : "disabled"}>清空文件</button>
      </div>

      <div class="agent-task-foot">
        <span>契约：<code>factor_intake_request_v1</code> / <code>factor_intake_manifest_v1</code> / ${escapeHtml(FACTOR_INTAKE_CONTRACT_DOC)}</span>
        <button type="button" class="primary-action compact" id="agentSubmitButton" ${state.agentTaskSubmitting ? "disabled" : ""}>
          ${state.agentTaskSubmitting ? AGENT_TASK_TEXT.submitting : AGENT_TASK_TEXT.submit}
        </button>
      </div>
    </section>

    <section class="table-card">
      <header class="table-card-head">
        <strong>${AGENT_TASK_TEXT.recentTitle}</strong>
        <span>\u672c\u4f1a\u8bdd\u5185\u5b58\u8bb0\u5f55,\u5237\u65b0\u9875\u9762\u540e\u6e05\u7a7a\u3002</span>
      </header>
      <div class="table-scroll">
        <table class="agent-task-table">
          <thead>
            <tr>
              <th><input type="checkbox" id="agentTaskSelectAll" ${state.agentTasks.length && state.agentTasks.every((task) => state.selectedAgentTaskIds.has(task.task_id)) ? "checked" : ""} aria-label="选择全部任务" /></th>
              <th>\u4efb\u52a1 ID</th>
              <th>\u6458\u8981</th>
              <th>\u72b6\u6001</th>
              <th>\u63d0\u4ea4\u65f6\u95f4</th>
              <th>\u64cd\u4f5c</th>
            </tr>
          </thead>
          <tbody>
            ${
              taskRows ||
              `<tr><td class="empty-cell" colspan="6">${AGENT_TASK_TEXT.emptyRecent}</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </section>
  `;

  const submitButton = els.agentTaskView.querySelector("#agentSubmitButton");
  const folderInput = els.agentTaskView.querySelector("#agentFolderInput");
  const fileInput = els.agentTaskView.querySelector("#agentFileInput");
  const dropZone = els.agentTaskView.querySelector("#agentDropZone");

  submitButton?.addEventListener("click", submitAgentTask);
  els.agentTaskView.querySelector("#clearPendingFilesButton")?.addEventListener("click", () => {
    clearPendingFiles();
    renderAgentTask();
  });
  els.agentTaskView.querySelectorAll("[data-pending-file-remove]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.pendingFileRemove);
      if (Number.isInteger(index)) removePendingFile(index);
    });
  });
  els.agentTaskView.querySelectorAll("[data-pending-file-preview]").forEach((button) => {
    button.addEventListener("click", () => previewPendingFile(button.dataset.pendingFilePreview));
  });
  els.agentTaskView.querySelector("[data-open-skill-contract]")?.addEventListener("click", openSkillContractModal);
  els.agentTaskView.querySelectorAll("[data-intake-type]").forEach((button) => {
    button.addEventListener("click", () => {
      state.intakeTaskType = button.dataset.intakeType || "research_reproduction";
      renderAgentTask();
    });
  });
  els.agentTaskView.querySelector("#chooseFolderButton")?.addEventListener("click", () => {
    state.intakeInputMode = "folder";
    folderInput?.click();
  });
  els.agentTaskView.querySelector("#chooseFilesButton")?.addEventListener("click", () => {
    state.intakeInputMode = "files";
    fileInput?.click();
  });
  dropZone?.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    state.intakeInputMode = "files";
    fileInput?.click();
  });
  folderInput?.addEventListener("change", (event) => {
    state.intakeInputMode = "folder";
    pendingFileStore.clear();
    state.pendingFiles = fileListFromInput(event.target.files);
    state.intakeTaskType = inferTaskType(state.pendingFiles);
    renderAgentTask();
  });
  fileInput?.addEventListener("change", (event) => {
    state.intakeInputMode = "files";
    pendingFileStore.clear();
    state.pendingFiles = fileListFromInput(event.target.files);
    state.intakeTaskType = inferTaskType(state.pendingFiles);
    renderAgentTask();
  });
  dropZone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("drag-over");
  });
  dropZone?.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
  dropZone?.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("drag-over");
    state.intakeInputMode = "files";
    pendingFileStore.clear();
    state.pendingFiles = fileListFromInput(event.dataTransfer?.files);
    state.intakeTaskType = inferTaskType(state.pendingFiles);
    renderAgentTask();
  });
  els.agentTaskView.querySelectorAll("[data-agent-task-row]").forEach((row) => {
    row.addEventListener("dblclick", (event) => {
      if (event.target.closest("button") || event.target.closest("input")) return;
      openAgentTaskFolder(row.dataset.agentTaskRow);
    });
  });
  els.agentTaskView.querySelectorAll("[data-agent-task-progress]").forEach((button) => {
    button.addEventListener("click", () => openAgentTaskProgress(button.dataset.agentTaskProgress));
  });
  els.agentTaskView.querySelectorAll("[data-agent-task-delete]").forEach((button) => {
    button.addEventListener("click", () => deleteAgentTask(button.dataset.agentTaskDelete));
  });
  els.agentTaskView.querySelectorAll("[data-agent-task-select]").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const taskId = event.target.dataset.agentTaskSelect;
      if (event.target.checked) {
        state.selectedAgentTaskIds.add(taskId);
      } else {
        state.selectedAgentTaskIds.delete(taskId);
      }
      renderAgentTask();
    });
  });
  els.agentTaskView.querySelector("#agentTaskSelectAll")?.addEventListener("change", (event) => {
    if (event.target.checked) {
      state.agentTasks.forEach((task) => state.selectedAgentTaskIds.add(task.task_id));
    } else {
      state.selectedAgentTaskIds.clear();
    }
    renderAgentTask();
  });
  renderSelectionSummary();
}

function connectionCard(title, statusText, statusClass, rows) {
  return `
    <article class="settings-page-card">
      <div class="settings-page-card-head">
        <strong>${escapeHtml(title)}</strong>
        <span class="settings-page-pill ${statusClass}">${escapeHtml(statusText)}</span>
      </div>
      <dl class="settings-page-list">
        ${rows
          .map(
            ([label, value]) => `
              <div>
                <dt>${escapeHtml(label)}</dt>
                <dd>${value}</dd>
              </div>
            `,
          )
          .join("")}
      </dl>
    </article>
  `;
}

function renderSettings() {
  if (!els.settingsView) return;
  const localStatusText = state.localConnected ? "已连接" : "未连接";
  const supabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
  const quantStatusText = state.quantApiReachable
    ? state.quantApiConfigured
      ? "已配置"
      : "未配置 token"
    : "检测失败";
  const quantStatusClass = state.quantApiConfigured ? "ok" : state.quantApiReachable ? "warn" : "bad";

  els.settingsView.innerHTML = `
    <section class="settings-page-head">
      <div>
        <h2>设置</h2>
        <p>这里集中展示本地服务、官方 Quant API、云端信息库和前端显示偏好。当前页面只读展示配置状态，不保存 token。</p>
      </div>
      <div class="settings-page-note">
        <strong>当前边界</strong>
        <span>前端只消费平台服务端产出的数据；真实计算和数据抓取都留在后端或执行侧。</span>
      </div>
    </section>

    <section class="settings-page-grid" aria-label="连接配置">
      ${connectionCard("数据服务", localStatusText, state.localConnected ? "ok" : "bad", [
        ["接口地址", `<code>${escapeHtml(API_BASE)}</code>`],
        ["健康检查", "<code>/health</code>"],
        ["用途", "读取因子库、交付证据、逐日 IC 与运行状态"],
      ])}
      ${connectionCard("官方 Quant API", quantStatusText, quantStatusClass, [
        ["接入方式", "浏览器 → 平台服务端 → Quant API"],
        ["Credential 位置", "服务端环境变量（浏览器端不携带）"],
        ["安全说明", "前端不接触 token，不直接访问公网数据接口"],
      ])}
      ${connectionCard("数据范围", "按交付约定", "ok", [
        ["对外提供", "衍生指标：IC / IR / 分组净值 / 拟合结果"],
        ["不提供", "底层截面数据与数据库直连"],
        ["计量方式", "每次授权调用写入用量账本，可按天对账"],
      ])}
      ${ENABLE_AGENT_TASK_DEBUG ? connectionCard("AI Agent 接入", "待接入", "warn", [
        ["外部 Agent", "Trae / Claude Code / Codex 等工具预留统一提交入口"],
        ["内部 Agent", "Hermes / Factor Mining Agent / Strategy Agent 预留能力位"],
        ["当前边界", "此页只展示接口位置，不触发自动挖掘、复现或回测"],
      ]) : ""}
    </section>

    <section class="settings-page-panel">
      <header>
        <strong>显示偏好与阈值</strong>
        <span>当前为前端常量，后续可迁移到配置文件。</span>
      </header>
      <div class="settings-page-kv-grid">
        <div><span>因子库每页行数</span><strong>${PAGE_SIZE}</strong></div>
        <div><span>自动刷新间隔</span><strong>${AUTO_REFRESH_INTERVAL_MS / 1000}s</strong></div>
        <div><span>覆盖率警告阈值</span><strong>${Math.round(COVERAGE_WARN_THRESHOLD * 100)}%</strong></div>
        <div><span>覆盖率危险阈值</span><strong>${Math.round(COVERAGE_DANGER_THRESHOLD * 100)}%</strong></div>
      </div>
    </section>

    <section class="settings-page-panel">
      <header>
        <strong>接口契约预留</strong>
        <span>这些是前端当前或后续计划消费的数据结构。</span>
      </header>
      <div class="settings-page-contracts">
        <span><code>factor_lab_view_v1</code>：因子库、因子详情、报告产物</span>
        <span><code>factor_lab_view_v1.1</code>：官方 Quant API 的 official 命名空间</span>
        ${ENABLE_AGENT_TASK_DEBUG ? "<span><code>factor_intake_request_v1</code>：数据入口请求（研报复现包 / 外部因子值包 + 文件元信息；中间流程由后端 Agent 判断）。</span>" : ""}
        ${ENABLE_AGENT_TASK_DEBUG ? "<span><code>factor_intake_manifest_v1</code>：数据入口文件夹 manifest，固定文件名见 docs/FACTOR_LAB_INTAKE_REPRODUCTION_CONTRACT.md。</span>" : ""}
        <span><code>strategy_monitor_view_v1</code>：策略看板与策略详情预留</span>
        <span><code>gate_monitor_view_v1</code>：任务监控与 Gate 可视化预留</span>
      </div>
    </section>
  `;
}

function activeFactor() {
  return state.rawFactors.find((factor) => factor.id === state.activeFactorId);
}

function parseJsonPayload(value) {
  if (!value) return {};
  if (typeof value === "object" && !Array.isArray(value)) return value;
  if (typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (error) {
    return {};
  }
}

function cumulativeFromReturns(items, valueKey = "return") {
  let total = 1;
  return (items || []).map((item) => {
    const value = Number(item?.[valueKey]);
    if (Number.isFinite(value)) {
      total *= 1 + value;
    }
    return Number(total.toFixed(8));
  });
}

function normalizeSupabaseAnalysisPayload(row) {
  const raw =
    [parseJsonPayload(row?.chart_data), parseJsonPayload(row?.analysis_json), parseJsonPayload(row?.payload)]
      .find((item) => Object.keys(item).length) || {};
  const chartData = Object.keys(raw).length ? raw : parseJsonPayload(row);
  const dailySeries = Array.isArray(chartData.daily_series) ? chartData.daily_series : [];
  const groupNav = chartData.group_nav || {};
  const dates =
    (Array.isArray(groupNav.dates) && groupNav.dates.length ? groupNav.dates : null) ||
    (Array.isArray(chartData.stratification?.dates) ? chartData.stratification.dates : []) ||
    dailySeries.map((item) => item.date).filter(Boolean);
  const groupCumulative =
    groupNav.cumulative ||
    chartData.stratification?.equity_by_group ||
    chartData.stratification?.equityByGroup ||
    {};

  let groupReturns = {};
  if (chartData.group_returns && typeof chartData.group_returns === "object") {
    Object.entries(chartData.group_returns).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        groupReturns[key] = value;
      }
    });
  }
  if (!Object.keys(groupReturns).length && dailySeries.length) {
    dailySeries.forEach((item) => {
      Object.entries(item.groups || {}).forEach(([group, value]) => {
        if (!groupReturns[group]) groupReturns[group] = [];
        groupReturns[group].push({ date: item.date, return: Number(value) });
      });
      const longShort = Number(item.long_short);
      if (Number.isFinite(longShort)) {
        if (!groupReturns.long_short) groupReturns.long_short = [];
        groupReturns.long_short.push({ date: item.date, return: longShort });
      }
    });
  }

  const icTimeSeries =
    Array.isArray(chartData.ic_time_series) && chartData.ic_time_series.length
      ? chartData.ic_time_series
      : dailySeries
          .map((item) => ({
            date: item.date,
            ic: Number.isFinite(Number(item.rank_ic)) ? Number(item.rank_ic) : Number(item.ic),
            rank_ic: Number.isFinite(Number(item.rank_ic)) ? Number(item.rank_ic) : Number(item.ic),
            pearson_ic: Number.isFinite(Number(item.pearson_ic)) ? Number(item.pearson_ic) : null,
          }))
          .filter((item) => item.date && Number.isFinite(item.ic));

  const longShortEquity =
    Array.isArray(chartData.stratification?.equity) && chartData.stratification.equity.length
      ? chartData.stratification.equity
      : cumulativeFromReturns(groupReturns.long_short || []);

  return {
    ...chartData,
    source_row_id: row?.id || chartData.id || null,
    ic_time_series: icTimeSeries,
    group_returns: groupReturns,
    stratification: {
      ...(chartData.stratification || {}),
      dates,
      equity: longShortEquity,
      equity_by_group: groupCumulative,
    },
  };
}

function sanitizeNavSeries(values) {
  let lastValid = null;
  return (values || []).map((value) => {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0.05) {
      return lastValid;
    }
    if (lastValid !== null) {
      const ratio = number / lastValid;
      if (ratio < 0.35 || ratio > 3) {
        return lastValid;
      }
    }
    lastValid = number;
    return number;
  });
}

function normalizeSupabaseSplitAnalysisPayload(summaryRow, icRows, groupRows) {
  const orderedIcRows = [...(icRows || [])].sort((a, b) =>
    String(a.trade_date || "").localeCompare(String(b.trade_date || ""))
  );
  const icTimeSeries = orderedIcRows
    .map((row) => {
      const rankIc = Number(row.rank_ic);
      const pearsonIc = Number(row.pearson_ic);
      return {
        date: row.trade_date,
        ic: rankIc,
        rank_ic: rankIc,
        pearson_ic: Number.isFinite(pearsonIc) ? pearsonIc : null,
      };
    })
    .filter((item) => item.date && Number.isFinite(item.ic));

  const orderedGroupRows = [...(groupRows || [])].sort((a, b) => {
    const dateCompare = String(a.trade_date || "").localeCompare(String(b.trade_date || ""));
    if (dateCompare) return dateCompare;
    return String(a.series_key || "").localeCompare(String(b.series_key || ""), undefined, { numeric: true });
  });
  const dates = [];
  const seenDates = new Set();
  const groupReturns = {};
  const equityByGroup = {};

  orderedGroupRows.forEach((row) => {
    const tradeDate = row.trade_date;
    if (tradeDate && !seenDates.has(tradeDate)) {
      dates.push(tradeDate);
      seenDates.add(tradeDate);
    }
    const isLongShort = row.series_type === "long_short" || row.series_key === "LS";
    const groupKey = isLongShort ? "long_short" : String(row.group_no ?? row.series_key ?? "").replace(/^G/i, "");
    if (!groupKey) return;

    const groupReturn = Number(row.group_return);
    if (!groupReturns[groupKey]) groupReturns[groupKey] = [];
    groupReturns[groupKey].push({
      date: tradeDate,
      return: Number.isFinite(groupReturn) ? groupReturn : null,
    });

    if (!isLongShort) {
      const groupNav = Number(row.group_nav);
      if (!equityByGroup[groupKey]) equityByGroup[groupKey] = [];
      equityByGroup[groupKey].push(Number.isFinite(groupNav) ? groupNav : null);
    }
  });

  Object.entries(equityByGroup).forEach(([key, values]) => {
    equityByGroup[key] = sanitizeNavSeries(values);
  });

  return {
    ...summaryRow,
    source_row_id: summaryRow?.id || null,
    dataset: parseJsonPayload(summaryRow?.dataset),
    metrics: parseJsonPayload(summaryRow?.metrics),
    ic_summary: parseJsonPayload(summaryRow?.ic_summary),
    group_returns_summary: parseJsonPayload(summaryRow?.group_returns_summary),
    long_short_summary: parseJsonPayload(summaryRow?.long_short_summary),
    monotonicity: parseJsonPayload(summaryRow?.monotonicity),
    ic_time_series: icTimeSeries,
    group_returns: groupReturns,
    stratification: {
      dates,
      equity: cumulativeFromReturns(groupReturns.long_short || []),
      equity_by_group: equityByGroup,
    },
  };
}

async function loadSupabaseSplitAnalysisPayload(summaryRow) {
  if (!SUPABASE_ANALYSIS_IC_TABLE || !SUPABASE_ANALYSIS_GROUP_TABLE) {
    return normalizeSupabaseAnalysisPayload(summaryRow);
  }
  const factorName = summaryRow?.factor_name;
  const library = summaryRow?.library;
  const configHash = summaryRow?.config_hash;
  if (!factorName || !library || !configHash) {
    return normalizeSupabaseAnalysisPayload(summaryRow);
  }
  const filters = {
    factor_name: `eq.${factorName}`,
    library: `eq.${library}`,
    config_hash: `eq.${configHash}`,
  };
  const [icRows, groupRows] = await Promise.all([
    fetchSupabaseAllRows(SUPABASE_ANALYSIS_IC_TABLE, {
      order: "trade_date.asc",
      filters,
    }),
    fetchSupabaseAllRows(SUPABASE_ANALYSIS_GROUP_TABLE, {
      order: "trade_date.asc,series_key.asc",
      filters,
    }),
  ]);
  return normalizeSupabaseSplitAnalysisPayload(summaryRow, icRows, groupRows);
}

function sortAnalysisRows(rows) {
  return [...rows].sort((a, b) => {
    const left = new Date(a.generated_at || a.created_at || a.imported_at || 0).getTime();
    const right = new Date(b.generated_at || b.created_at || b.imported_at || 0).getTime();
    return right - left;
  });
}

function factorAnalysisNameAliases(factor) {
  const names = new Set();
  [factor?.factor_name, factor?.raw_factor_name, factor?.display_name, factor?.source_id]
    .filter(Boolean)
    .forEach((name) => names.add(String(name).trim()));
  Array.from(names).forEach((name) => {
    const match = name.match(/(?:worldquant[_-]?)?alpha0*(\d+)/i);
    if (!match) return;
    const number = Number(match[1]);
    if (!Number.isFinite(number)) return;
    names.add(`alpha${number}`);
    names.add(`alpha${String(number).padStart(3, "0")}`);
    names.add(`WorldQuant_alpha${String(number).padStart(3, "0")}`);
  });
  return Array.from(names).filter(Boolean);
}

async function loadSupabaseFactorAnalysis(factorId) {
  if (!SUPABASE_ANALYSIS_TABLE) return;
  const factor = state.rawFactors.find((item) => item.id === factorId);
  const attempts = [
    { factor_id: `eq.${factorId}` },
    ...factorAnalysisNameAliases(factor).map((name) => ({ factor_name: `eq.${name}` })),
  ].filter(Boolean);

  for (const filters of attempts) {
    try {
      const rows = await fetchSupabaseRows(SUPABASE_ANALYSIS_TABLE, {
        limit: 10,
        filters,
      });
      if (rows.length) {
        const [latest] = sortAnalysisRows(rows);
        try {
          state.factorDetailData[factorId] = await loadSupabaseSplitAnalysisPayload(latest);
        } catch (seriesError) {
          console.warn("Supabase split factor analysis lookup skipped:", latest, seriesError);
          state.factorDetailData[factorId] = normalizeSupabaseAnalysisPayload(latest);
        }
        return;
      }
    } catch (error) {
      console.warn("Supabase factor analysis lookup skipped:", filters, error);
    }
  }
}

// The delivery's evidence for one factor: the eight frozen gates with their
// measured values, plus the IC/portfolio metrics. Loaded once per factor.
// Three outcomes are kept distinct, because they mean different things:
//   the run object  -> the delivery has evidence for it
//   {__missing}     -> the delivery answered, and this factor is not in it
//   {__error}       -> we could not ask; say so instead of implying "not delivered"
async function loadDeliveryEvidence(factorId) {
  if (!API_BASE || !factorId) return;
  if (Object.prototype.hasOwnProperty.call(state.deliveryEvidence, factorId)) return;
  try {
    const response = await fetchWithTimeout(
      withCacheBust(`${API_BASE}/delivery/factor/${encodeURIComponent(factorId)}`)
    );
    if (response.status === 404) {
      state.deliveryEvidence[factorId] = { __missing: true };
    } else if (!response.ok) {
      state.deliveryEvidence[factorId] = { __error: true, status: response.status };
    } else {
      state.deliveryEvidence[factorId] = await response.json();
    }
  } catch (error) {
    state.deliveryEvidence[factorId] = { __error: true, message: String(error) };
  }
}

// 重新绘制当前因子详情（仅在仍停留在这个因子上时）。用于逐张显示证据卡片。
function repaintDetail(factorId) {
  if (state.view === "detail" && state.activeFactorId === factorId) renderDetail();
}

async function loadFactorDetailData(factorId) {
  if (!factorId || state.factorDetailLoading[factorId]) return;
  if (USE_SUPABASE_DASHBOARD) {
    state.factorDetailLoading[factorId] = true;
    try {
      await loadSupabaseFactorAnalysis(factorId);
    } finally {
      state.factorDetailLoading[factorId] = false;
      if (state.view === "detail" && state.activeFactorId === factorId) {
        renderDetail();
      }
    }
    return;
  }
  if (CLOUD_DEMO_MODE) {
    return;
  }
  state.factorDetailLoading[factorId] = true;
  try {
    // 逐张重绘：证据约 2 秒、逐日 IC 约 2 秒、组合约 10 秒。原来三步串行且全部完成
    // 才渲染，等于让最快的两张卡片陪着最慢的等 10 秒，页面上还一片空白。
    await loadDeliveryEvidence(factorId);
    repaintDetail(factorId);
    await loadDeliverySeries(factorId);
    repaintDetail(factorId);
    await loadFactorPortfolio(factorId);
    repaintDetail(factorId);
    // The research endpoint only knows factors with a cached job. A delivery factor
    // has no job, so asking anyway 404s on every refresh — ask only when there is
    // something to fetch.
    const factor = state.rawFactors.find((item) => item.id === factorId);
    if (factor && factor.latest_job_id) {
      const detailUrl = `${API_BASE}/factor/${encodeURIComponent(factorId)}`;
      const response = await fetchWithTimeout(withCacheBust(detailUrl));
      if (response.ok) {
        const data = await response.json();
        console.log("[DEBUG] Factor detail API response:", data);
        state.factorDetailData[factorId] = data;
      }
    }
  } catch (error) {
    console.error("获取因子详情失败:", error);
  } finally {
    state.factorDetailLoading[factorId] = false;
    if (state.view === "detail" && state.activeFactorId === factorId) {
      renderDetail();
    }
  }
}

async function openDetail(factorId) {
  const factor = state.rawFactors.find((item) => item.id === factorId);
  if (!canOpenFactor(factor)) return;
  state.view = "detail";
  state.activeFactorId = factorId;
  state.detailTab = "analysis";
  window.location.hash = `factor=${encodeURIComponent(factorId)}`;
  renderDetail();
  loadFactorDetailData(factorId);
}

function closeDetail() {
  state.view = "library";
  state.activeFactorId = null;
  state.detailTab = "analysis";
  if (window.location.hash) {
    history.pushState("", document.title, window.location.pathname + window.location.search);
  }
  renderView();
}

function showMainView(view) {
  const enabledViews = ENABLE_AGENT_TASK_DEBUG
    ? ["monitor", "library", "strategy-board", "quant-desk", "strategy-builder", "tasks", "agent_task", "settings"]
    : ["monitor", "library", "strategy-board", "quant-desk", "strategy-builder", "tasks", "settings"];
  state.view = enabledViews.includes(view) ? view : "library";
  state.activeFactorId = null;
  state.activeStrategyId = null;
  state.activeTaskId = null;
  state.detailTab = "analysis";
  if (window.location.hash) {
    history.pushState("", document.title, window.location.pathname + window.location.search);
  }
  renderView();
}

async function syncDetailFromHash() {
  if (window.location.hash === "#quant-desk") {
    state.view = "quant-desk";
    renderView();
    return;
  }
  if (window.location.hash === "#strategy-builder") {
    state.view = "strategy-builder";
    loadStrategyTemplates();
    return;
  }
  if (window.location.hash === "#strategy-board") {
    state.view = "strategy-board";
    renderView();
    return;
  }
  const match = window.location.hash.match(/^#factor=(.+)$/);
  if (!match || state.view === "detail") return;
  const factorId = decodeURIComponent(match[1]);
  const factor = state.rawFactors.find((item) => item.id === factorId);
  if (canOpenFactor(factor)) {
    await openDetail(factorId);
  }
}

function renderView() {
  const detailMode = state.view === "detail";
  const monitorMode = state.view === "monitor";
  const strategyBoardMode = state.view === "strategy-board";
  const strategyMode = state.view === "quant-desk" || state.view === "strategy";
  const strategyBuilderMode = state.view === "strategy-builder";
  const strategyDetailMode = state.view === "strategy-detail";
  const taskMode = state.view === "tasks";
  const agentTaskMode = ENABLE_AGENT_TASK_DEBUG && state.view === "agent_task";
  const settingsMode = state.view === "settings";
  els.pageTitle.textContent = detailMode
    ? "因子详情"
    : monitorMode
      ? "因子监控"
      : strategyBoardMode
        ? "策略看板"
        : strategyMode
          ? "策略看板"
          : strategyBuilderMode
            ? "策略构建"
            : strategyDetailMode
              ? "策略详情"
              : taskMode
                ? "任务监控"
                : agentTaskMode
                  ? "数据入口"
                  : settingsMode
                    ? "设置"
                    : "因子库";
  if (strategyMode) {
    els.pageTitle.textContent = "策略工作台";
  }
  if (strategyMode) {
    els.pageTitle.textContent = "Quant Desk";
  }
  els.libraryView.classList.toggle(
    "hidden",
    detailMode || monitorMode || strategyBoardMode || strategyMode || strategyBuilderMode || strategyDetailMode || taskMode || agentTaskMode || settingsMode,
  );
  els.monitorView.classList.toggle("hidden", !monitorMode);
  els.strategyView.classList.toggle("hidden", !strategyMode);
  els.strategyBoardView?.classList.toggle("hidden", !strategyBoardMode);
  els.strategyBuilderView?.classList.toggle("hidden", !strategyBuilderMode);
  els.taskView.classList.toggle("hidden", !taskMode);
  els.strategyDetailView.classList.toggle("hidden", !strategyDetailMode);
  els.detailView.classList.toggle("hidden", !detailMode);
  els.agentTaskView?.classList.toggle("hidden", !agentTaskMode);
  els.settingsView?.classList.toggle("hidden", !settingsMode);
  els.selectionBar.classList.toggle(
    "hidden",
    detailMode || monitorMode || strategyBoardMode || strategyMode || strategyBuilderMode || strategyDetailMode || taskMode || settingsMode,
  );
  els.navItems.forEach((item) => {
    const activeView = detailMode
      ? "library"
      : strategyDetailMode || strategyBuilderMode
        ? "strategy-board"
        : state.view === "strategy"
          ? "strategy-board"
          : state.view;
    item.classList.toggle("active", item.dataset.view === activeView);
  });
  els.quantDeskNavGroup?.classList.toggle("expanded", strategyMode);
  if (monitorMode) renderMonitor();
  if (strategyBoardMode) renderStrategy();
  if (strategyMode) renderQuantDesk();
  if (strategyBuilderMode) {
    loadStrategyTemplates();
    renderStrategyBuilder();
  }
  if (taskMode) {
    renderTasks();
  }
  if (agentTaskMode) {
    renderAgentTask();
    loadAgentTasks();
  }
  if (settingsMode) renderSettings();
}

const DELIVERY_GATE_CN = {
  coverage: "覆盖率",
  rank_ic: "RankIC",
  oos_seal: "样本外封存",
  style_r2: "风格 R²",
  residual_ic: "残差 IC",
  cost_adjusted_return: "成本后收益",
  dd_vol_ratio: "回撤波动比",
  parameter_perturbation: "参数扰动",
};

function deliveryNumber(value, digits = 4) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    return Math.abs(value) >= 1000 ? value.toLocaleString("en-US") : value.toFixed(digits);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.map((v) => deliveryNumber(v, digits)).join(" → ");
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([k, v]) => `${k}=${deliveryNumber(v, digits)}`)
      .join(" · ");
  }
  return String(value);
}

// A gate's `actual` can carry a whole nested breakdown (the rank_ic gate carries
// four years of IC). Only the headline keys belong in the table row; the yearly
// breakdown has its own table underneath.
const DELIVERY_GATE_ACTUAL_KEYS = {
  coverage: ["mean_daily_coverage", "minimum_daily_coverage"],
  rank_ic: ["days", "horizon", "mean", "ic_ir", "t_stat"],
  oos_seal: ["train_range", "oos_range", "maximum_train_label_date"],
  style_r2: ["days", "mean"],
  residual_ic: ["raw_rank_ic", "residual_rank_ic", "retention", "sign_matches"],
  cost_adjusted_return: [],
  dd_vol_ratio: [],
  parameter_perturbation: ["0.8", "1.2"],
};

function deliveryGateActual(gateName, actual) {
  if (actual === null || actual === undefined) return "—";
  if (typeof actual !== "object") return deliveryNumber(actual);
  const keys = DELIVERY_GATE_ACTUAL_KEYS[gateName] || Object.keys(actual);
  const parts = keys
    .filter((key) => actual[key] !== undefined)
    .map((key) => `${key}=${deliveryNumber(actual[key])}`);
  return parts.length ? parts.join(" · ") : "—";
}

function renderDeliveryEvidence(factor) {
  const run = state.deliveryEvidence ? state.deliveryEvidence[factor.id] : undefined;
  if (run === undefined) return "";

  if (run && run.__error) {
    return `
      <section class="delivery-evidence">
        <header><h3>交付验证实测</h3></header>
        <p class="delivery-empty">读取交付证据失败（${escapeHtml(String(run.status || run.message || "未知错误"))}）。此处不显示任何推测数值。</p>
      </section>`;
  }
  if (!run || run.__missing) {
    return `
      <section class="delivery-evidence">
        <header><h3>交付验证实测</h3></header>
        <p class="delivery-empty">该因子不在本次交付包内（未送验或未评估），因此没有门槛数值。<strong>未评估 ≠ 未通过。</strong></p>
      </section>`;
  }

  const passed = run.status === "validated";
  const manifest = run.manifest || {};
  const gates = Array.isArray(run.gates) ? run.gates : [];
  const gateRows = gates.map((gate) => {
    const ok = gate.passed === true;
    return `<tr>
      <td>${escapeHtml(DELIVERY_GATE_CN[gate.gate] || gate.gate || "-")}</td>
      <td><span class="${ok ? "delivery-ok" : "delivery-bad"}">${ok ? "通过" : "拦截"}</span></td>
      <td class="delivery-mono">${escapeHtml(deliveryGateActual(gate.gate, gate.actual))}</td>
      <td class="delivery-mono muted">${escapeHtml(JSON.stringify(gate.threshold ?? "-"))}</td>
    </tr>`;
  }).join("");

  const rankIc = run.rank_ic || {};
  const horizons = Object.keys(rankIc).sort((a, b) => parseFloat(a) - parseFloat(b));
  const icRows = horizons.map((key) => {
    const block = rankIc[key] || {};
    return `<tr>
      <td>${escapeHtml(key)}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.mean, 5))}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.ic_ir, 4))}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.t_stat, 3))}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.days, 0))}</td>
    </tr>`;
  }).join("");

  const primary = rankIc[horizons.includes("10d") ? "10d" : horizons[0]] || {};
  const yearly = primary.yearly || {};
  const yearRows = Object.keys(yearly).sort().map((year) => {
    const block = yearly[year] || {};
    return `<tr>
      <td>${escapeHtml(year)}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.mean, 5))}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.ic_ir, 4))}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.t_stat, 3))}</td>
      <td class="delivery-mono">${escapeHtml(deliveryNumber(block.days, 0))}</td>
    </tr>`;
  }).join("");

  const style = run.style || {};
  const portfolio = run.portfolio || {};
  const perturbation = run.perturbation || {};
  const training = run.training || {};

  return `
    <section class="delivery-evidence">
      <header>
        <h3>交付验证实测</h3>
        <span class="badge ${passed ? "delivery-badge-ok" : "delivery-badge-bad"}">${passed ? "过闸" : "未过闸"}</span>
        <span class="badge">${escapeHtml(manifest.tier ? `交付分层 ${manifest.tier}` : "无交付分层")}</span>
        ${manifest.cluster_id ? `<span class="badge">簇 ${escapeHtml(manifest.cluster_id)}（${escapeHtml(manifest.cluster_role || "-")}）</span>` : ""}
      </header>

      ${run.reason ? `<p class="delivery-reason">${escapeHtml(run.reason)}</p>` : ""}

      ${gates.length ? `
        <h4>八道冻结门槛</h4>
        <table class="delivery-table">
          <thead><tr><th>门槛</th><th>结果</th><th>实测</th><th>阈值</th></tr></thead>
          <tbody>${gateRows}</tbody>
        </table>` : `<p class="delivery-empty">该因子在交付包中没有逐门槛记录（被拒因子只在清单里留有失败数值，见上）。</p>`}

      ${icRows ? `
        <h4>分周期 RankIC</h4>
        <table class="delivery-table">
          <thead><tr><th>周期</th><th>IC 均值</th><th>IC_IR</th><th>t 值</th><th>天数</th></tr></thead>
          <tbody>${icRows}</tbody>
        </table>` : ""}

      ${yearRows ? `
        <h4>按年拆分（${escapeHtml(horizons.includes("10d") ? "10d" : horizons[0] || "-")}）</h4>
        <table class="delivery-table">
          <thead><tr><th>年</th><th>IC 均值</th><th>IC_IR</th><th>t 值</th><th>天数</th></tr></thead>
          <tbody>${yearRows}</tbody>
        </table>` : ""}

      <h4>风格 · 组合 · 扰动 · 方向</h4>
      <dl class="delivery-kv">
        <div><dt>训练段方向</dt><dd>${escapeHtml(deliveryNumber(training.direction, 2))}</dd></div>
        <div><dt>训练段 IC</dt><dd>${escapeHtml(deliveryNumber(training.primary_rank_ic_mean, 5))}</dd></div>
        <div><dt>风格 R² 均值</dt><dd>${escapeHtml(deliveryNumber(style.r2_mean, 5))}</dd></div>
        <div><dt>残差 IC 留存</dt><dd>${escapeHtml(deliveryNumber(style.retention, 4))}</dd></div>
        <div><dt>成本后年化</dt><dd>${escapeHtml(deliveryNumber(portfolio.net_annualized, 4))}</dd></div>
        <div><dt>最大回撤</dt><dd>${escapeHtml(deliveryNumber(portfolio.max_drawdown, 4))}</dd></div>
        <div><dt>平均换手</dt><dd>${escapeHtml(deliveryNumber(portfolio.mean_turnover, 4))}</dd></div>
        <div><dt>扰动 0.8 / 1.2</dt><dd>${escapeHtml(deliveryNumber((perturbation["0.8"] || {}).rank_ic_mean, 5))} / ${escapeHtml(deliveryNumber((perturbation["1.2"] || {}).rank_ic_mean, 5))}</dd></div>
        <div><dt>FDR 勋章</dt><dd>${escapeHtml(String(manifest.fdr_accepted ?? "-"))}（不参与门槛判定）</dd></div>
        <div><dt>行业中性留存</dt><dd>${escapeHtml(deliveryNumber(manifest.industry_neutral_retention, 4))}（补充层口径，不参与门槛判定）</dd></div>
        <div><dt>p / 校正后 p</dt><dd>${escapeHtml(deliveryNumber(manifest.p_value, 6))} / ${escapeHtml(deliveryNumber(manifest.p_adjusted, 6))}</dd></div>
        <div><dt>result_hash</dt><dd class="delivery-mono">${escapeHtml(String(run.result_hash || manifest.result_hash || "-").slice(0, 24))}${run.result_hash || manifest.result_hash ? "…" : ""}</dd></div>
      </dl>
      <p class="delivery-note">以上数值来自交付包内的逐因子证据文件 <code>${escapeHtml(run.evidence_file || "-")}</code>，未经改写。</p>
    </section>
  `;
}

// Delivery-only factors have no research job, so the research panels are omitted
// rather than drawn empty.
function renderDeliveryOnlyNote(factor) {
  const run = state.deliveryEvidence ? state.deliveryEvidence[factor.id] : null;
  const basis = run && !run.__missing && !run.__error ? "交付包逐因子证据" : "交付清单";
  return `
    <section class="research-settings-card">
      <header><h3>复现研究</h3><span class="badge">未运行</span></header>
      <p class="delivery-empty">
        本因子没有 Factor Lab 复现作业（<code>latest_job_id</code> 为空）。上面展示的是${escapeHtml(basis)}，
        不是复现结果。需要复现研究请在「数据入口」发起一次作业。
      </p>
    </section>
  `;
}

// The daily IC series: what the factor actually did day by day, split at the frozen
// out-of-sample boundary. Same three-state contract as the evidence loader.
async function loadDeliverySeries(factorId) {
  if (!API_BASE || !factorId) return;
  if (Object.prototype.hasOwnProperty.call(state.deliverySeries, factorId)) return;
  try {
    const response = await fetchWithTimeout(
      withCacheBust(`${API_BASE}/delivery/series/${encodeURIComponent(factorId)}`)
    );
    if (response.status === 404) {
      state.deliverySeries[factorId] = { __missing: true };
    } else if (!response.ok) {
      state.deliverySeries[factorId] = { __error: true, status: response.status };
    } else {
      state.deliverySeries[factorId] = await response.json();
    }
  } catch (error) {
    state.deliverySeries[factorId] = { __error: true, message: String(error) };
  }
}

function deliveryPolyline(points, valueKey, min, max, width, height) {
  if (points.length < 2) return "";
  const span = max - min || 1;
  return points
    .map((point, i) => {
      const value = point[valueKey];
      if (value === null || value === undefined) return null;
      const x = (i / (points.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
}

function renderDeliverySeries(factor) {
  const payload = state.deliverySeries ? state.deliverySeries[factor.id] : undefined;
  if (payload === undefined || payload === null) return "";
  if (payload.__error) {
    return `<section class="delivery-evidence"><header><h3>样本外逐日表现</h3></header>
      <p class="delivery-empty">读取逐日序列失败（${escapeHtml(String(payload.status || payload.message || "未知错误"))}）。不画推测曲线。</p></section>`;
  }
  if (!payload.available) return "";

  const points = payload.points || [];
  if (points.length < 2) return "";

  const useSigned = payload.signed_available === true;
  const valueKey = useSigned ? "rank_ic_signed" : "rank_ic";
  const values = points.map((p) => p[valueKey]).filter((v) => v !== null && v !== undefined);
  if (!values.length) return "";

  const W = 980;
  const H = 190;
  // Scale to a robust range, not to the extremes: a handful of tiny early
  // cross-sections produce daily ICs near ±0.85, and scaling to those flattens the
  // rolling line the client is actually reading.
  const magnitudes = values.map((v) => Math.abs(v)).sort((a, b) => a - b);
  const q = magnitudes[Math.min(magnitudes.length - 1, Math.floor(magnitudes.length * 0.98))];
  const bound = Math.max(q || 0, 0.01);
  const min = -bound;
  const max = bound;
  const clamp = (v) => (v > max ? max : v < min ? min : v);
  const clipped = points.map((p) => ({
    ...p,
    [valueKey]: p[valueKey] === null || p[valueKey] === undefined ? null : clamp(p[valueKey]),
  }));

  const daily = deliveryPolyline(clipped, valueKey, min, max, W, H);
  const rolling = (payload.rolling && payload.rolling["60"]) || [];
  const rollingLine = rolling.length >= 2
    ? deliveryPolyline(
        rolling.map((p) => ({ ...p, mean: p.mean === null ? null : clamp(p.mean) })),
        "mean",
        min,
        max,
        W,
        H
      )
    : "";
  const boundaryIndex = points.findIndex((p) => p.phase === "oos");
  const boundaryX = boundaryIndex > 0 ? (boundaryIndex / (points.length - 1)) * W : null;
  const zeroY = H - ((0 - min) / (max - min)) * H;

  const stats = payload.stats || {};
  // The gate table reports the validator's own IC_IR for this factor. It uses the same
  // definition (mean/std) but not always the same set of days — for 1 of the 332 factors
  // it drops 11 days — so the page would otherwise show two IC_IR values for one factor
  // with no explanation. Say so when it happens instead of leaving the client to wonder.
  const evidence = state.deliveryEvidence ? state.deliveryEvidence[factor.id] : null;
  const frozenBlock =
    evidence && evidence.rank_ic
      ? evidence.rank_ic[`${payload.horizon}d`] || null
      : null;
  const mineDays = stats.oos ? stats.oos.days : null;
  const frozenDays = frozenBlock ? Number(frozenBlock.days) : null;
  const dayMismatch =
    Number.isFinite(frozenDays) && mineDays && Math.abs(frozenDays - mineDays) > 0
      ? `<p class="delivery-note">
           此因子的纳入交易日与门槛表不同：本曲线用 <strong>${mineDays}</strong> 天，
           验证器用 <strong>${frozenDays}</strong> 天，因此两处 IC_IR（本表 ${escapeHtml(
             deliveryNumber(stats.oos.ic_ir, 4)
           )} / 门槛表 ${escapeHtml(deliveryNumber(frozenBlock.ic_ir, 4))}）本来就不会完全相同。
           口径一致（均为 IC 均值 ÷ 标准差），差异只来自交易日集合。
         </p>`
      : "";
  // `live` gets its own row rather than being folded into `oos`: the frozen out-of-sample
  // window is what the delivery validated, and days after it are this pipeline's own
  // tracking. Summing them would present tracked days as validated ones.
  const STAT_LABELS = { train: "训练段", oos: "样本外（交付验证）", live: "上线跟踪" };
  const phaseRows = ["train", "oos", "live"]
    .filter((phase) => stats[phase])
    .map((phase) => {
      const s = stats[phase];
      return `<tr>
        <td>${STAT_LABELS[phase] || phase}</td>
        <td class="delivery-mono">${s.days}</td>
        <td class="delivery-mono">${escapeHtml(deliveryNumber(s.ic_mean, 5))}</td>
        <td class="delivery-mono">${escapeHtml(deliveryNumber(s.ic_ir, 4))}</td>
        <td class="delivery-mono">${escapeHtml(deliveryNumber(s.hit_rate, 3))}</td>
        <td class="delivery-mono muted">${escapeHtml(String(s.first_date || ""))} → ${escapeHtml(String(s.last_date || ""))}</td>
      </tr>`;
    })
    .join("");

  return `
    <section class="delivery-evidence">
      <header>
        <h3>样本外逐日表现</h3>
        <span class="badge">${useSigned ? "方向调整后 IC" : "原始 IC（无方向列）"}</span>
        <span class="badge">${escapeHtml(String(payload.horizon))} 日 RankIC</span>
        <span class="badge">as of ${escapeHtml(String(payload.as_of))}</span>
      </header>
      ${useSigned ? "" : `<p class="delivery-empty">该序列文件是在方向调整之前生成的，只含原始 IC。反向使用的因子（direction = −1）在这里会显示为负——不是因子失效。</p>`}
      <svg viewBox="0 0 ${W} ${H + 26}" class="delivery-chart" role="img" aria-label="逐日 RankIC 与 60 日滚动均值">
        <line x1="0" y1="${zeroY.toFixed(1)}" x2="${W}" y2="${zeroY.toFixed(1)}" stroke="#cbd5e1" stroke-width="1" />
        ${boundaryX !== null ? `
          <rect x="${boundaryX.toFixed(1)}" y="0" width="${(W - boundaryX).toFixed(1)}" height="${H}" fill="#3b82f6" opacity="0.05" />
          <line x1="${boundaryX.toFixed(1)}" y1="0" x2="${boundaryX.toFixed(1)}" y2="${H}" stroke="#3b82f6" stroke-width="1" stroke-dasharray="4,3" />
          <text x="${(boundaryX + 4).toFixed(1)}" y="12" font-size="10" fill="#3b82f6">样本外起点</text>` : ""}
        <polyline points="${daily}" fill="none" stroke="#94a3b8" stroke-width="0.7" opacity="0.55" />
        ${rollingLine ? `<polyline points="${rollingLine}" fill="none" stroke="#1d4ed8" stroke-width="1.8" />` : ""}
        <text x="0" y="${H + 18}" font-size="10" fill="#6b7280">${escapeHtml(points[0].date)}</text>
        <text x="${W}" y="${H + 18}" font-size="10" fill="#6b7280" text-anchor="end">${escapeHtml(points[points.length - 1].date)}</text>
        <text x="0" y="11" font-size="10" fill="#6b7280">+${bound.toFixed(3)}</text>
        <text x="0" y="${(H - 2).toFixed(1)}" font-size="10" fill="#6b7280">−${bound.toFixed(3)}</text>
      </svg>
      <p class="delivery-note">灰线＝逐日 RankIC，蓝线＝60 日滚动均值；以零轴对称，便于看衰减。</p>
      <table class="delivery-table">
        <thead><tr><th>区间</th><th>交易日</th><th>IC 均值</th><th>IC_IR</th><th>胜率</th><th>日期范围</th></tr></thead>
        <tbody>${phaseRows}</tbody>
      </table>
      <p class="delivery-note">
        IC_IR 为 IC 均值/标准差（与冻结报告同口径，未年化）；切分点取自 <code>configs/validation_gates.yaml</code>，
        序列由 <code>scripts/daily_factor_metrics.py</code> 生成。
      </p>
      ${dayMismatch}
    </section>
  `;
}

async function loadFreshness() {
  if (!API_BASE) return;
  const banner = document.getElementById("freshnessBanner");
  if (!banner) return;
  try {
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/delivery/freshness`));
    if (!response.ok) {
      banner.classList.add("hidden");
      return;
    }
    state.freshness = await response.json();
  } catch (error) {
    banner.classList.add("hidden");
    return;
  }
  renderFreshness();
}

// Show every date, because one number misleads: the IC series always trails the factor
// values by its horizon, and the delivery package is a frozen snapshot. Showing only the
// frozen date made a healthy daily pipeline look stale.
function renderFreshness() {
  const banner = document.getElementById("freshnessBanner");
  const data = state.freshness;
  if (!banner || !data) return;
  const items = [
    `<span class="freshness-item">日更因子值 as of <strong>${escapeHtml(data.live_values_as_of || data.factor_values_as_of || "未知")}</strong></span>`,
    `<span class="freshness-item">逐日 IC as of <strong>${escapeHtml(data.ic_series_as_of || "未生成")}</strong>`,
    data.ic_horizon_days
      ? `<span class="freshness-note">（比因子值自然滞后 ${escapeHtml(String(data.ic_horizon_days))} 个交易日）</span>`
      : "",
    `</span>`,
  ];
  if (data.delivery_as_of) {
    items.push(
      `<span class="freshness-item muted">交付证据（冻结）as of ${escapeHtml(data.delivery_as_of)}</span>`
    );
  }
  if (data.scores_matrix_as_of && data.scores_matrix_as_of !== data.live_values_as_of) {
    items.push(
      `<span class="freshness-item muted">回测矩阵（冻结）as of ${escapeHtml(data.scores_matrix_as_of)}</span>`
    );
  }
  if (data.stale) {
    items.unshift(`<span class="freshness-item">⚠ ${escapeHtml(data.stale_reason || "数据可能已陈旧")}</span>`);
  }
  banner.innerHTML = items.join("");
  banner.classList.toggle("is-stale", Boolean(data.stale));
  banner.classList.remove("hidden");
}

async function loadFactorPortfolio(factorId) {
  if (!API_BASE || !factorId) return;
  if (Object.prototype.hasOwnProperty.call(state.factorPortfolio, factorId)) return;
  // 组合序列要在服务端按因子重算，实测约 10 秒，是这一页最慢的一步。先把状态标成
  // 「计算中」并立刻重绘，否则这段时间卡片是空的，看起来像卡死。
  state.factorPortfolio[factorId] = { __loading: true, startedAt: Date.now() };
  if (state.view === "detail" && state.activeFactorId === factorId) renderDetail();
  try {
    const response = await fetchWithTimeout(
      withCacheBust(`${API_BASE}/delivery/factor-strategy/${encodeURIComponent(factorId)}`),
      // 该接口在服务端重算分组组合，实测约 10 秒，而默认超时是 8 秒。用默认值会在慢请求
      // 时中止，界面上显示「读取组合序列失败」——看起来像后端故障，其实是我们自己掐断的。
      { timeoutMs: 60000 },
    );
    state.factorPortfolio[factorId] = response.ok
      ? await response.json()
      : { __error: true, status: response.status };
  } catch (error) {
    state.factorPortfolio[factorId] = { __error: true, message: String(error) };
  }
}

function portfolioPolyline(values, min, max, width, height) {
  if (!values || values.length < 2) return "";
  const span = max - min || 1;
  return values
    .map((value, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

// ---------------------------------------------------------------------------
// 持仓明细（按需加载）
//
// 组合净值回答「这个因子赚钱吗」，但答不出「它买了哪些票」——而客户要拿它去和同花顺
// 这类软件逐日核对，只能靠具体标的。所以单独做一张卡，点了才取。
//
// 为什么要按需：构建一次要把全部有分数的交易日重排一遍（实测 2~4 秒，与净值曲线同量级）。
// 每次点开因子都付这个代价，会让大多数根本不看这张表的人一起变慢。
// ---------------------------------------------------------------------------

const HOLDINGS_HELP = "逐次调仓的持仓与买卖变动。可用于与行情软件核对因子信号。";

async function loadFactorHoldings(factorId) {
  if (!API_BASE || !factorId) return;
  // 只在「已经拿到结果」时跳过。不能用「有值且无错误」判断：点击处理器会先把状态设成
  // __loading，那样这里的守卫会直接 return，请求永远发不出去，卡片一直停在「正在构建」。
  const existing = state.factorHoldings[factorId];
  if (existing && !existing.__error && !existing.__loading) return;
  state.factorHoldings[factorId] = { __loading: true, startedAt: Date.now() };
  renderDetail();
  try {
    const response = await fetchWithTimeout(
      withCacheBust(`${API_BASE}/delivery/factor-holdings/${encodeURIComponent(factorId)}`),
      { timeoutMs: 60000 },
    );
    state.factorHoldings[factorId] = response.ok
      ? await response.json()
      : { __error: true, status: response.status };
  } catch (error) {
    state.factorHoldings[factorId] = { __error: true, message: String(error) };
  }
  if (state.view === "detail" && state.activeFactorId === factorId) renderDetail();
}

function renderFactorHoldings(factor) {
  const payload = state.factorHoldings ? state.factorHoldings[factor.id] : undefined;
  if (payload === undefined) {
    // 尚未加载：给出按钮，说明代价，不做无声的等待
    return `<section class="delivery-evidence" data-holdings="idle">
      <header><h3>持仓明细</h3><span class="hint">按需加载</span></header>
      <p class="delivery-empty">逐次调仓的持仓名单与买卖变动。构建需要重新排序全部交易日，约需数秒。</p>
      <button class="ghost-button" type="button" data-load-holdings="${escapeHtml(factor.id)}">加载持仓明细</button>
    </section>`;
  }
  if (payload.__loading) {
    const secs = Math.max(1, Math.round((Date.now() - (payload.startedAt || Date.now())) / 1000));
    return `<section class="delivery-evidence" data-holdings="loading">
      <header><h3>持仓明细</h3><span class="loading-pill">正在构建</span></header>
      <div class="loading-progress" role="status" aria-live="polite">
        <div class="loading-bar"><span></span></div>
        <p class="loading-note" data-elapsed>正在按每个调仓日重排全市场股票，并计算与上次相比的买入与卖出变动……已等待 <strong>${secs}</strong> 秒</p>
      </div>
    </section>`;
  }
  if (payload.__error) {
    return `<section class="delivery-evidence" data-holdings="error">
      <header><h3>持仓明细</h3></header>
      <p class="delivery-empty">读取持仓失败（${escapeHtml(String(payload.status || payload.message || ""))}）。不展示推测的名单。</p>
      <button class="ghost-button" type="button" data-load-holdings="${escapeHtml(factor.id)}">重试</button>
    </section>`;
  }
  if (!payload.available) {
    return `<section class="delivery-evidence" data-holdings="na">
      <header><h3>持仓明细</h3><span class="hint">暂不可用</span></header>
      <p class="delivery-empty">${escapeHtml(payload.reason || "该因子没有逐日截面分数。")}
      <br /><small>持仓明细需要有逐日截面分数才能生成；目前只有簇代表因子具备。</small></p>
    </section>`;
  }

  const snaps = payload.snapshots || [];
  const rows = snaps
    .slice()
    .reverse()
    .map((s) => {
      const held = (s.held || []).slice(0, 12).map((h) => `<code>${escapeHtml(h.code)}</code>`).join(" ");
      const more = (s.held || []).length > 12 ? `<small>…共 ${s.held.length} 只</small>` : "";
      const ent = (s.entries || []).length
        ? (s.entries || []).slice(0, 10).map((c) => `<code class="buy">${escapeHtml(c)}</code>`).join(" ")
        : '<small class="muted">—</small>';
      const ext = (s.exits || []).length
        ? (s.exits || []).slice(0, 10).map((c) => `<code class="sell">${escapeHtml(c)}</code>`).join(" ")
        : '<small class="muted">—</small>';
      return `<tr>
        <td class="nowrap">${escapeHtml(s.date)}</td>
        <td class="number">${s.universe_size}</td>
        <td>${held} ${more}</td>
        <td>${ent}</td>
        <td>${ext}</td>
        <td class="number">${s.turnover === null || s.turnover === undefined ? "—" : Math.round(s.turnover * 100) + "%"}</td>
      </tr>`;
    })
    .join("");

  const d = payload.disclosure || {};
  return `<section class="delivery-evidence" data-holdings="ready">
    <header><h3>持仓明细</h3>
      <span class="hint">每 ${payload.rebalance_every} 个交易日一次 · 持仓 ${payload.top_n} 只 · 共 ${snaps.length} 次</span>
    </header>
    <div class="table-scroll">
      <table class="holdings-table">
        <thead><tr>
          <th>调仓日</th><th class="number">全市场</th><th>持仓</th>
          <th>买入</th><th>卖出</th><th class="number">换手</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <details class="holdings-notes">
      <summary>口径说明（与行情软件核对前请先读）</summary>
      <ul>
        <li><strong>分数是「当日排名」，不是原始指标值。</strong>${escapeHtml(d.what_the_score_is || "")}</li>
        <li><strong>调仓节奏是展示选择。</strong>${escapeHtml(d.rebalance_cadence || "")}</li>
        <li><strong>买卖对比的是本表相邻两次快照。</strong>${escapeHtml(d.entries_exits || "")}</li>
        <li>股票池：${escapeHtml(d.universe || "")}</li>
      </ul>
    </details>
  </section>`;
}

// 让等待过程可见：加载中每秒更新一次已用时间，否则进度条不动会像卡死。
let holdingsTicker = null;
function startHoldingsTicker() {
  stopHoldingsTicker();
  holdingsTicker = window.setInterval(() => {
    const note = document.querySelector("[data-elapsed]");
    if (!note) return stopHoldingsTicker();
    const since = state.holdingsRequestStartedAt || Date.now();
    note.innerHTML = `正在按每个调仓日重排全市场股票，并计算与上次相比的买入与卖出变动……已等待 <strong>${Math.max(1, Math.round((Date.now() - since) / 1000))}</strong> 秒`;
  }, 1000);
}
function stopHoldingsTicker() {
  if (holdingsTicker) {
    window.clearInterval(holdingsTicker);
    holdingsTicker = null;
  }
}

// A factor shown as a portfolio: what holding its ranking would have done, split at the
// frozen boundary so in-sample and out-of-sample are never read as one number.
function renderFactorPortfolio(factor) {
  const payload = state.factorPortfolio ? state.factorPortfolio[factor.id] : undefined;
  // undefined = 还没开始取；__loading = 正在服务端重算。两者都要给出可见状态，
  // 否则这段等待在页面上是一片空白，客户会以为卡死。
  if (payload === undefined) return "";
  if (payload.__loading) {
    return `<section class="delivery-evidence" data-loading="portfolio">
      <header><h3>因子组合表现</h3>
        <span class="loading-pill">正在计算</span>
      </header>
      <div class="loading-progress" role="status" aria-live="polite">
        <div class="loading-bar"><span></span></div>
        <p class="loading-note">服务端正在按这个因子的逐日值构建分组组合并计算单调性，通常需要 10 秒左右。这一步是实时计算，不是读取缓存。</p>
      </div>
    </section>`;
  }
  if (payload === null) return "";
  if (payload.__error) {
    return `<section class="delivery-evidence"><header><h3>因子组合表现</h3></header>
      <p class="delivery-empty">读取组合序列失败（${escapeHtml(String(payload.status || payload.message || ""))}）。不画推测曲线。</p></section>`;
  }
  if (!payload.available) return "";

  const W = 980;
  const H = 210;
  const labels = payload.labels || [];
  const top = labels[labels.length - 1];
  const bottom = labels[0];
  const series = [payload.groups[top], payload.benchmark, payload.groups[bottom], payload.long_short].filter(Boolean);
  const all = series.flat();
  const min = Math.min(...all, 0.9);
  const max = Math.max(...all);

  const dates = payload.dates || [];
  const split = payload.split ? payload.split.oos_start : null;
  const splitIndex = split ? dates.findIndex((d) => d >= split) : -1;
  const splitX = splitIndex > 0 ? (splitIndex / (dates.length - 1)) * W : null;

  const monotonicity = payload.monotonicity;
  const monoBadge =
    monotonicity === null || monotonicity === undefined
      ? ""
      : `<span class="badge ${monotonicity >= 0.8 ? "badge-green" : monotonicity >= 0.5 ? "badge-blue" : "badge-orange"}">单调性 ${monotonicity.toFixed(2)}</span>`;

  const rows = [...labels, "long_short", "benchmark"]
    .filter((key) => payload.metrics[key])
    .map((key) => {
      const m = payload.metrics[key];
      const name =
        key === "long_short" ? `${top}−${bottom} 多空` : key === "benchmark" ? "等权基准" : key;
      return `<tr>
        <td>${escapeHtml(name)}</td>
        <td class="delivery-mono">${formatPercent(m.annualized_return)}</td>
        <td class="delivery-mono">${formatPercent(m.volatility)}</td>
        <td class="delivery-mono">${m.sharpe === null || m.sharpe === undefined ? "—" : m.sharpe.toFixed(2)}</td>
        <td class="delivery-mono">${formatPercent(m.max_drawdown)}</td>
        <td class="delivery-mono">${formatPercent(m.total_return)}</td>
      </tr>`;
    })
    .join("");

  return `
    <section class="delivery-evidence">
      <header>
        <h3>因子组合表现</h3>
        <span class="badge">${escapeHtml(String(payload.observations))} 个交易日</span>
        <span class="badge">${escapeHtml(String(payload.quantiles))} 分组</span>
        ${monoBadge}
        <span class="badge">未计成本</span>
      </header>
      <p class="delivery-note">
        每日把有分数的股票按该因子等分为 ${escapeHtml(String(payload.quantiles))} 组，
        组内等权持有。方向由交付口径给定，<strong>${escapeHtml(top)} 是因子看好的一侧</strong>。
      </p>
      <svg viewBox="0 0 ${W} ${H + 26}" class="delivery-chart" role="img" aria-label="因子分组净值">
        ${splitX !== null ? `
          <rect x="${splitX.toFixed(1)}" y="0" width="${(W - splitX).toFixed(1)}" height="${H}" fill="#3b82f6" opacity="0.05" />
          <line x1="${splitX.toFixed(1)}" y1="0" x2="${splitX.toFixed(1)}" y2="${H}" stroke="#3b82f6" stroke-width="1" stroke-dasharray="4,3" />
          <text x="${(splitX + 4).toFixed(1)}" y="12" font-size="10" fill="#3b82f6">样本外起点</text>` : ""}
        <polyline points="${portfolioPolyline(payload.long_short, min, max, W, H)}" fill="none" stroke="#7c3aed" stroke-width="1.6" stroke-dasharray="6,4" />
        <polyline points="${portfolioPolyline(payload.groups[top], min, max, W, H)}" fill="none" stroke="#1d4ed8" stroke-width="2" />
        <polyline points="${portfolioPolyline(payload.benchmark, min, max, W, H)}" fill="none" stroke="#94a3b8" stroke-width="1.4" />
        <polyline points="${portfolioPolyline(payload.groups[bottom], min, max, W, H)}" fill="none" stroke="#f87171" stroke-width="1.4" />
        <text x="0" y="${H + 18}" font-size="10" fill="#6b7280">${escapeHtml(dates[0] || "")}</text>
        <text x="${W}" y="${H + 18}" font-size="10" fill="#6b7280" text-anchor="end">${escapeHtml(dates[dates.length - 1] || "")}</text>
        <text x="4" y="12" font-size="10" fill="#1d4ed8">${escapeHtml(top)}（因子看好侧）</text>
        <text x="140" y="12" font-size="10" fill="#94a3b8">等权基准</text>
        <text x="240" y="12" font-size="10" fill="#f87171">${escapeHtml(bottom)}</text>
        <text x="300" y="12" font-size="10" fill="#7c3aed">多空</text>
      </svg>
      <table class="delivery-table">
        <thead><tr><th>组合</th><th>年化</th><th>波动率</th><th>夏普</th><th>最大回撤</th><th>累计</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="delivery-note">
        <strong>单调性</strong>是分组序号与各组日均收益的秩相关：接近 1 说明因子把收益从差到好整齐排开；
        接近 0 说明只有某一端有效（常见于"只有最差那组明显差"的因子，多空收益几乎全来自空头）。
        这里未扣交易成本，多空曲线也不是可直接交易的组合。
      </p>
    </section>
  `;
}

function renderDetail() {
  const factor = activeFactor();
  if (!factor) {
    closeDetail();
    return;
  }
  renderView();
  const [proofText, proofClass] = proofBadge(factor.proof_status);
  const [truthText, truthClass] = truthBadge(factor.truth_status);
  const deliveryOnly = !factor.latest_job_id && Boolean(deliveryVerdict(factor));
  els.detailView.innerHTML = `
    <div class="breadcrumb">
      <button type="button" class="breadcrumb-link" data-action="back">因子库</button>
      <span>›</span>
      <span>${escapeHtml(factor.library)}</span>
      <span>›</span>
      <strong>${escapeHtml(factor.factor_name)}</strong>
    </div>

    <section class="detail-hero">
      <div>
        <div class="detail-title-row">
          <h2>${escapeHtml(factor.factor_name)} 单因子详情</h2>
          <span class="badge ${proofClass}">${proofText}</span>
          <span class="badge ${truthClass}">${truthText}</span>
        </div>
        <dl class="detail-meta">
          <div><dt>因子库</dt><dd>${escapeHtml(factor.library)}</dd></div>
          <div><dt>分类</dt><dd>${escapeHtml(jqFactorCategory(factor))}</dd></div>
          <div><dt>子类</dt><dd>${escapeHtml(factor.subcategory || "-")}</dd></div>
          <div><dt>复现验证时间</dt><dd>${formatDate(factor.latest_checked_at)}</dd></div>
          <div><dt>Job ID</dt><dd><code>${escapeHtml(factor.latest_job_id || "-")}</code></dd></div>
        </dl>
      </div>
      <div class="detail-actions">
        <button type="button" class="secondary-action" data-action="back">返回因子库</button>
        <button type="button" class="secondary-action" data-artifact="research_report_markdown" ${factor.latest_job_id ? "" : "disabled"}>查看原始报告</button>
        <button type="button" class="primary-action compact" data-artifact="research_report_json" ${factor.latest_job_id ? "" : "disabled"}>导出当前报告</button>
      </div>
    </section>

    ${renderDeliveryEvidence(factor)}
    ${renderDeliverySeries(factor)}
    ${renderFactorPortfolio(factor)}
    ${renderFactorHoldings(factor)}
    ${renderFactorDefinition(factor)}
    ${deliveryOnly ? renderDeliveryOnlyNote(factor) : renderResearchSettings(factor)}

    ${deliveryOnly ? `
      <p class="delivery-note">
        该因子由交付流水线验证（八道冻结门槛），没有 Factor Lab 复现作业，因此这里不展示复现图表与产物——
        没有数据就不画图。
      </p>
    ` : `
    <nav class="detail-tabs" aria-label="单因子报告切换">
      <button type="button" class="${state.detailTab === "analysis" ? "active" : ""}" data-tab="analysis">复现与研究分析</button>
      <button type="button" class="${state.detailTab === "artifacts" ? "active" : ""}" data-tab="artifacts">验证产物（Artifacts）</button>
    </nav>

    ${state.detailTab === "artifacts" ? renderArtifactsPanel(factor) : renderAnalysisPanel(factor)}
    `}
  `;

  els.detailView.querySelectorAll('[data-action="back"]').forEach((button) => {
    button.addEventListener("click", closeDetail);
  });
  els.detailView.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.detailTab = button.dataset.tab;
      renderDetail();
    });
  });
  els.detailView.querySelectorAll("[data-artifact]").forEach((button) => {
    button.addEventListener("click", () => {
      const url = artifactUrl(factor, button.dataset.artifact);
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    });
  });
  els.detailView.querySelectorAll("[data-copy-formula]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copyFormula || "");
        button.textContent = "已复制";
        window.setTimeout(() => {
          button.textContent = "复制公式";
        }, 1200);
      } catch {
        button.textContent = "复制失败";
      }
    });
  });
  if (state.detailTab === "analysis") {
    window.requestAnimationFrame(() => mountDetailCharts(factor.id));
  }
}

function factorFormula(factor) {
  return factor.formula || factor.expression || factor.definition || factor.raw_formula || "";
}

function factorLookback(factor) {
  return factor.lookback || factor.window || factor.n_days || factor.n_dates || "待接入";
}

function factorSourceRef(factor) {
  const number = factor.factor_name?.match(/\d+$/)?.[0];
  if (factor.library && number) return `${factor.library} #${number}`;
  return factor.library || "待接入";
}

function renderFactorDefinition(factor) {
  const formula = factorFormula(factor);
  const formulaText = formula || "公式待接入";
  return `
    <section class="factor-definition-card" aria-label="因子定义">
      <div class="factor-definition-head">
        <div>
          <strong>因子定义</strong>
          <span>展示当前 specs / view model 可读取的定义信息，不参与前端计算。</span>
        </div>
        <button type="button" class="secondary-action compact" data-copy-formula="${escapeHtml(formulaText)}" ${formula ? "" : "disabled"}>复制公式</button>
      </div>
      <pre class="factor-formula"><code>${escapeHtml(formulaText)}</code></pre>
      <dl class="definition-meta">
        <div><dt>Lookback</dt><dd>${escapeHtml(factorLookback(factor))}</dd></div>
        <div><dt>来源引用</dt><dd>${escapeHtml(factorSourceRef(factor))}</dd></div>
      </dl>
    </section>
  `;
}

function renderResearchSettings(factor) {
  return `
    <section class="research-settings-card" aria-label="复现口径与研究区">
      <div class="settings-head">
        <div>
          <strong>复现口径</strong>
          <span>本因子复现时使用的固定口径，不可调整；调整口径请使用下方研究区。</span>
        </div>
        <dl>
          <div><dt>股票池</dt><dd>当前样本股票池</dd></div>
          <div><dt>频率</dt><dd>日频</dd></div>
          <div><dt>研究区间</dt><dd>当前复现样本区间</dd></div>
          <div><dt>真值对照口径</dt><dd>${truthValue(factor.truth_status)}</dd></div>
          <div><dt>数据来源</dt><dd>${escapeHtml(factor.data_source || "-")}</dd></div>
        </dl>
      </div>

      <div class="research-mode-head">
        <strong>研究区（口径可调）</strong>
        <span>研究模式，结果不代表复现结论</span>
      </div>
      <div class="settings-grid">
        <label>
          <span>研究区间</span>
          <select>
            <option selected>当前复现样本区间</option>
            <option>近3个月（待接入）</option>
            <option>近1年（待接入）</option>
            <option>近3年（待接入）</option>
            <option>自定义区间（待接入）</option>
          </select>
        </label>
        <label>
          <span>股票池</span>
          <select>
            <option selected>当前样本股票池</option>
            <option>沪深300（待接入）</option>
            <option>中证500（待接入）</option>
            <option>中证1000（待接入）</option>
          </select>
        </label>
        <label>
          <span>组合构建</span>
          <select>
            <option selected>单因子分层研究</option>
            <option>纯多组合（待接入）</option>
            <option>多空组合（待接入）</option>
          </select>
        </label>
        <label>
          <span>分组数量</span>
          <select>
            <option selected>10组</option>
            <option>5组（待接入）</option>
          </select>
        </label>
      </div>

      <div class="settings-foot">
        <span>提示：当前控件只说明研究口径，不会重新计算指标；正式切换区间需要后端生成对应 research_analysis.json。</span>
        <button type="button" disabled>应用设置（待接入）</button>
      </div>
    </section>
  `;
}

function renderAnalysisPanel(factor) {
  const detailData = (state.factorDetailData && state.factorDetailData[factor.id]) || {};
  const hasIcSeries = Array.isArray(detailData.ic_time_series) && detailData.ic_time_series.length > 0;
  const hasGroupReturns = detailData.group_returns && Object.values(detailData.group_returns).some((items) => Array.isArray(items) && items.length > 0);
  const stratification = detailData.stratification || {};
  const equityByGroup = stratification.equity_by_group || stratification.equityByGroup || {};
  const hasStratification =
    (Array.isArray(stratification.equity) && stratification.equity.length > 0) ||
    Object.values(equityByGroup).some((items) => Array.isArray(items) && items.length > 0);
  const hasRealData = hasIcSeries || hasGroupReturns || hasStratification;
  const hasTruthComparisonMetrics =
    toFiniteNumber(factor.truth_exact_match_ratio) !== null ||
    toFiniteNumber(factor.truth_max_abs_error) !== null;
  const latestJobHtml = factor.latest_job_id
    ? `<code>${escapeHtml(factor.latest_job_id)}</code>`
    : `<span class="muted-value">未生成</span>`;
  const checkedAtText = formatDate(factor.latest_checked_at);
  const checkedAtHtml = checkedAtText === "-" ? `<span class="muted-value">未记录</span>` : checkedAtText;
  const truthMetricCardHtml = hasTruthComparisonMetrics
    ? metricCard("真值匹配率", formatRatio(factor.truth_exact_match_ratio), "真值匹配")
    : "";
  const truthSummaryTableHtml = hasTruthComparisonMetrics ? `
        <table class="summary-table">
          <thead>
            <tr>
              <th>复现状态（Proof）</th>
              <th>真值状态（Truth）</th>
              <th>真值精确匹配率</th>
              <th>最大绝对误差</th>
              <th>最新 Job ID</th>
              <th>生成时间</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>${proofValue(factor.proof_status)}</td>
              <td>${truthValue(factor.truth_status)}</td>
              <td>${formatNumber(factor.truth_exact_match_ratio, 6)}</td>
              <td>${formatError(factor.truth_max_abs_error)}</td>
              <td>${latestJobHtml}</td>
              <td>${checkedAtHtml}</td>
            </tr>
          </tbody>
        </table>
  ` : `
        <div class="summary-note">
          当前还没有生成逐点真值对照指标，匹配率和最大误差会在真值对照任务完成后展示。
        </div>
        <table class="summary-table summary-table-compact">
          <thead>
            <tr>
              <th>复现状态（Proof）</th>
              <th>真值状态（Truth）</th>
              <th>最新 Job ID</th>
              <th>生成时间</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>${proofValue(factor.proof_status)}</td>
              <td>${truthValue(factor.truth_status)}</td>
              <td>${latestJobHtml}</td>
              <td>${checkedAtHtml}</td>
            </tr>
          </tbody>
        </table>
  `;
  if (!hasRealData && !state.factorDetailLoading[factor.id]) {
    loadFactorDetailData(factor.id);
  }
  
  return `
    <section class="metric-grid">
      ${metricCard("复现状态", proofBadge(factor.proof_status)[0], proofValue(factor.proof_status), factor.proof_status === "passed" ? "good" : "warn")}
      ${metricCard("真值校验", truthBadge(factor.truth_status)[0], truthValue(factor.truth_status), truthMetricTone(factor.truth_status))}
      ${metricCard("覆盖率", formatRatio(factor.coverage_ratio), "有效样本覆盖")}
      ${metricCard("IC均值", formatNumber(factor.rank_ic_mean, 4), "Rank IC Mean")}
      ${metricCard("IR均值", formatNumber(factor.rank_ic_ir, 4), "Rank IC IR")}
      ${truthMetricCardHtml}
    </section>

    <section class="summary-card">
      <header>复现与真值对比摘要</header>
      <div class="summary-body">
        <p>
          本因子已完成复现验证。系统读取本地 proof、evaluation、research report 等产物，
          对复现结果与 Truth 真值进行一致性检查。当前结果显示：
          <strong class="${factor.proof_status === "passed" ? "text-green" : "text-red"}">复现状态为${proofValue(factor.proof_status)}</strong>，
          <strong class="${truthTextClass(factor.truth_status)}">真值状态为${truthValue(factor.truth_status)}</strong>。
        </p>
        ${truthSummaryTableHtml}
      </div>
    </section>

    <section class="research-layout">
      <article class="research-card stratification-card">
        <header>
          <strong>单因子分层研究 / Factor Stratification Analysis</strong>
          <span>区间：当前复现样本区间 · 频率：日频</span>
        </header>
        <div id="stratChart" class="chart-placeholder chart-large ${hasRealData ? "chart-rendered chart-echarts" : ""}">
          ${hasRealData ? renderStratificationChart(detailData) : `
            <div class="placeholder-mark">◇</div>
            <strong>待接入真实数据 API</strong>
            <span>当前仅作为研究级分层回测占位，不代表可交易策略收益。</span>
          `}
        </div>
      </article>
      <div class="side-charts">
        <article class="research-card">
          <header>
            <strong>IC 时序 / IC Time Series</strong>
            <span>区间：当前复现样本区间</span>
          </header>
          <div id="icChart" class="chart-placeholder ${hasRealData ? "chart-rendered chart-echarts" : ""}">
            ${hasRealData ? renderIcTimeSeriesChartV2(detailData) : `<strong>等待时序数据</strong>`}
          </div>
        </article>
        <article class="research-card">
          <header>
            <strong>分组表现 / Group Performance</strong>
            <span>区间：当前复现样本区间</span>
          </header>
          <div id="groupChart" class="chart-placeholder ${hasRealData ? "chart-rendered chart-echarts" : ""}">
            ${hasRealData ? renderGroupPerformanceChartV2(detailData) : `<strong>等待分组收益数据</strong>`}
          </div>
        </article>
      </div>
    </section>

    <section class="info-strip">
      本页面展示的是因子复现产物与内部一致性状态，不代表因子具备投资有效性。正式策略收益需要在策略层结合真实行情、交易成本、滑点、调仓规则和风控约束后验证。
    </section>
  `;
}

function uniqueMonthTicks(dates, maxTicks) {
  const months = [];
  const seen = new Set();
  dates.forEach((date, index) => {
    const label = String(date || "").substring(0, 7);
    if (!label || seen.has(label)) return;
    seen.add(label);
    months.push({ index, label });
  });
  if (months.length <= maxTicks) return months;
  const selected = [];
  const last = months.length - 1;
  for (let i = 0; i < maxTicks; i++) {
    const month = months[Math.round((i / Math.max(maxTicks - 1, 1)) * last)];
    if (!selected.some((item) => item.label === month.label)) {
      selected.push(month);
    }
  }
  return selected.sort((a, b) => a.index - b.index);
}

function evenIndexTicks(labels, maxTicks) {
  const count = labels.length;
  if (!count) return [];
  const tickCount = Math.min(maxTicks, count);
  const ticks = [];
  const seen = new Set();
  for (let i = 0; i < tickCount; i++) {
    const index = Math.round((i / Math.max(tickCount - 1, 1)) * (count - 1));
    const label = String(labels[index] || "").substring(0, 7);
    const key = `${index}:${label}`;
    if (!seen.has(key)) {
      seen.add(key);
      ticks.push({ index, label });
    }
  }
  return ticks;
}

function limitAxisTicks(ticks, maxTicks) {
  if (ticks.length <= maxTicks) return ticks;
  const selected = [];
  const seen = new Set();
  const last = ticks.length - 1;
  for (let i = 0; i < maxTicks; i++) {
    const value = ticks[Math.round((i / Math.max(maxTicks - 1, 1)) * last)];
    const key = String(value);
    if (!seen.has(key)) {
      seen.add(key);
      selected.push(value);
    }
  }
  return selected;
}

function niceAxisRange(values, paddingRatio = 0.18) {
  const finiteValues = values.filter((value) => Number.isFinite(value));
  if (!finiteValues.length) {
    return { min: -0.01, max: 0.01, ticks: [-0.01, 0, 0.01] };
  }
  let min = Math.min(...finiteValues, 0);
  let max = Math.max(...finiteValues, 0);
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.5, 0.001);
    min -= pad;
    max += pad;
  }
  const span = max - min;
  const paddedMin = min - span * paddingRatio;
  const paddedMax = max + span * paddingRatio;
  const rawStep = (paddedMax - paddedMin) / 4;
  const power = Math.pow(10, Math.floor(Math.log10(rawStep || 0.001)));
  const normalized = rawStep / power;
  const niceStep = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * power;
  const axisMin = Math.floor(paddedMin / niceStep) * niceStep;
  const axisMax = Math.ceil(paddedMax / niceStep) * niceStep;
  const ticks = [];
  for (let value = axisMin; value <= axisMax + niceStep * 0.5; value += niceStep) {
    ticks.push(Number(value.toPrecision(12)));
  }
  return { min: axisMin, max: axisMax, ticks };
}

function formatCompactAxisTick(value, range) {
  const absRange = Math.abs(range);
  if (absRange < 0.01) return value.toFixed(4);
  if (absRange < 0.1) return value.toFixed(3);
  return value.toFixed(2);
}

function renderStratificationChart(detailData) {
  const stratification = detailData.stratification || {};
  const equityByGroup = stratification.equity_by_group || stratification.equityByGroup || {};
  const firstGroupEquity = Object.values(equityByGroup).find((values) => Array.isArray(values) && values.length);
  const equity = stratification.equity || firstGroupEquity || [];
  const dates = stratification.dates || [];
  
  if (equity.length === 0) {
    return `<text x="200" y="80" fill="#9ca3af" font-size="12" text-anchor="middle">暂无分层数据</text>`;
  }
  
  const validEquity = equity.map(Number).filter(Number.isFinite);
  const axis = niceAxisRange(validEquity, 0.08);
  const minVal = axis.min;
  const maxVal = axis.max;
  const range = maxVal - minVal || 0.4;
  const totalLength = equity.length;
  const plot = { left: 74, top: 26, right: 884, bottom: 252 };
  const width = plot.right - plot.left;
  const height = plot.bottom - plot.top;
  
  let html = `<svg viewBox="0 0 920 316" class="research-svg">`;
  
  html += `<line x1="${plot.left}" y1="${plot.top}" x2="${plot.left}" y2="${plot.bottom}" stroke="#dbe4f0" stroke-width="1" />`;
  html += `<line x1="${plot.left}" y1="${plot.bottom}" x2="${plot.right}" y2="${plot.bottom}" stroke="#dbe4f0" stroke-width="1" />`;
  
  limitAxisTicks(axis.ticks, 6).forEach((val) => {
    const y = plot.bottom - ((val - minVal) / range) * height;
    html += `<line x1="${plot.left}" y1="${y}" x2="${plot.right}" y2="${y}" stroke="#eef3f8" stroke-width="1" />`;
    html += `<text x="${plot.left - 12}" y="${y + 4}" fill="#5f7189" font-size="12" text-anchor="end">${formatCompactAxisTick(val, range)}</text>`;
  });
  
  const xTicks = evenIndexTicks(dates, 7);
  xTicks.forEach((tick) => {
    const x = plot.left + (tick.index / Math.max(totalLength - 1, 1)) * width;
    html += `<line x1="${x}" y1="${plot.bottom}" x2="${x}" y2="${plot.bottom + 8}" stroke="#dbe4f0" stroke-width="1" />`;
    html += `<text x="${x}" y="${plot.bottom + 32}" fill="#5f7189" font-size="12" text-anchor="middle">${tick.label}</text>`;
  });
  
  const points = [];
  for (let i = 0; i < equity.length; i++) {
    const value = Number(equity[i]);
    if (!Number.isFinite(value)) continue;
    const x = plot.left + (i / Math.max(totalLength - 1, 1)) * width;
    const y = plot.bottom - ((value - minVal) / range) * height;
    points.push(`${x.toFixed(2)},${Math.max(plot.top, Math.min(plot.bottom, y)).toFixed(2)}`);
  }
  
  if (points.length > 0) {
    html += `<path d="M ${points.join(" L ")}" fill="none" stroke="#2454c5" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round" />`;
  }
  
  html += `</svg>`;
  
  return html;
}

function renderIcTimeSeriesChart(detailData) {
  const icSeries = detailData.ic_time_series || [];
  
  if (icSeries.length === 0) {
    return `<text x="100" y="50" fill="#9ca3af" font-size="11" text-anchor="middle">暂无IC时序数据</text>`;
  }
  
  const icValues = icSeries.map(d => d.ic);
  const dates = icSeries.map(d => d.date);
  
  const minVal = Math.min(...icValues, -0.5);
  const maxVal = Math.max(...icValues, 0.5);
  const range = maxVal - minVal || 1;
  const totalLength = icSeries.length;
  
  let html = `<svg viewBox="0 0 240 124" class="research-svg">`;
  
  html += `<line x1="34" y1="14" x2="34" y2="92" stroke="#e2e8f0" stroke-width="1" />`;
  html += `<line x1="34" y1="92" x2="230" y2="92" stroke="#e2e8f0" stroke-width="1" />`;
  html += `<text x="12" y="18" fill="#64748b" font-size="9">IC 值</text>`;
  html += `<text x="34" y="8" fill="#64748b" font-size="9">日均收益</text>`;
  
  html += `<rect x="0" y="0" width="72" height="13" fill="#ffffff" />`;
  html += `<text x="34" y="8" fill="#64748b" font-size="9">IC 值</text>`;
  
  const zeroY = 92 - ((0 - minVal) / range) * 78;
  html += `<line x1="34" y1="${zeroY}" x2="230" y2="${zeroY}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="3,3" />`;
  
  const yTicks = [-0.4, -0.2, 0, 0.2, 0.4];
  yTicks.forEach((val) => {
    const y = 92 - ((val - minVal) / range) * 78;
    html += `<line x1="34" y1="${y}" x2="230" y2="${y}" stroke="#f1f5f9" stroke-width="1" />`;
    html += `<text x="28" y="${y + 3}" fill="#64748b" font-size="9" text-anchor="end">${val.toFixed(1)}</text>`;
  });
  
  const maxBars = 36;
  const displayStep = Math.max(1, Math.ceil(totalLength / maxBars));
  const barWidth = Math.max(3, Math.min(7, 176 / Math.ceil(totalLength / displayStep) - 2));
  for (let i = 0; i < icSeries.length; i += displayStep) {
    const x = 34 + (i / Math.max(totalLength - 1, 1)) * 196;
    const ic = icValues[i];
    const y = 92 - ((ic - minVal) / range) * 78;
    const height = Math.abs(y - zeroY);
    const isPositive = ic >= 0;
    
    html += `<rect x="${x - barWidth/2}" y="${isPositive ? y : zeroY}" width="${barWidth}" height="${Math.max(1, height)}" fill="${isPositive ? '#16a34a' : '#dc2626'}" opacity="0.52" />`;
  }

  const numXTicks = Math.min(5, dates.length);
  const dateStep = Math.max(1, Math.ceil(dates.length / numXTicks));
  for (let i = 0; i < dates.length; i += dateStep) {
    const x = 34 + (i / Math.max(totalLength - 1, 1)) * 196;
    html += `<line x1="${x}" y1="92" x2="${x}" y2="97" stroke="#e2e8f0" stroke-width="1" />`;
    html += `<text x="${x}" y="114" fill="#64748b" font-size="9" text-anchor="middle">${String(dates[i] || "").substring(0, 7)}</text>`;
  }
  
  html += `</svg>`;
  
  return html;
}

function renderGroupPerformanceChart(detailData) {
  const groupReturns = detailData.group_returns || {};
  const groups = Object.keys(groupReturns)
    .filter(k => k !== "long_short")
    .sort((a, b) => Number(a) - Number(b));
  
  if (groups.length === 0) {
    return `<text x="100" y="50" fill="#9ca3af" font-size="11" text-anchor="middle">暂无分组数据</text>`;
  }
  
  const groupAverages = groups
    .map((group) => {
      const values = (groupReturns[group] || []).map(d => Number(d.return)).filter(Number.isFinite);
      if (!values.length) return null;
      return {
        group,
        value: values.reduce((sum, value) => sum + value, 0) / values.length,
      };
    })
    .filter(Boolean);
  let lsAverage = null;
  if (groupReturns["long_short"]) {
    const values = groupReturns["long_short"].map(d => Number(d.return)).filter(Number.isFinite);
    if (values.length) {
      lsAverage = values.reduce((sum, value) => sum + value, 0) / values.length;
    }
  }
  const axis = niceAxisRange([
    ...groupAverages.map(item => item.value),
    ...(Number.isFinite(lsAverage) ? [lsAverage] : []),
  ]);
  const minVal = axis.min;
  const maxVal = axis.max;
  const range = maxVal - minVal || 0.02;
  
  const groupColors = ["#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#3b82f6", "#2563eb", "#1d4ed8", "#1e40af", "#1e3a8a", "#172554"];
  
  let html = `<svg viewBox="0 0 320 150" class="research-svg">`;
  
  html += `<line x1="44" y1="18" x2="44" y2="112" stroke="#e2e8f0" stroke-width="1" />`;
  html += `<line x1="44" y1="112" x2="306" y2="112" stroke="#e2e8f0" stroke-width="1" />`;
  html += `<text x="12" y="18" fill="#64748b" font-size="9">日均收益</text>`;
  html += `<rect x="0" y="0" width="90" height="24" fill="#ffffff" />`;
  html += `<text x="34" y="8" fill="#64748b" font-size="9">日均收益</text>`;
  
  const zeroY = 112 - ((0 - minVal) / range) * 94;
  html += `<line x1="44" y1="${zeroY}" x2="306" y2="${zeroY}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="3,3" />`;
  
  axis.ticks.forEach((val) => {
    const y = 112 - ((val - minVal) / range) * 94;
    html += `<line x1="44" y1="${y}" x2="306" y2="${y}" stroke="#f1f5f9" stroke-width="1" />`;
    html += `<text x="38" y="${y + 3}" fill="#64748b" font-size="8" text-anchor="end">${formatCompactAxisTick(val, range)}</text>`;
  });
  
  const groupWidth = 240 / Math.max(groupAverages.length, 1);
  groupAverages.forEach((item, idx) => {
    const group = item.group;
    const avgReturn = item.value;
    const x = 56 + idx * groupWidth;
    const y = 112 - ((avgReturn - minVal) / range) * 94;
    const height = Math.abs(y - zeroY);
    const isPositive = avgReturn >= 0;
    const label = Number.isFinite(Number(group)) ? `G${Number(group).toFixed(0)}` : `G${group}`;
    
    html += `<rect x="${x - 5}" y="${isPositive ? y : zeroY}" width="10" height="${Math.max(1, height)}" fill="${groupColors[idx % groupColors.length]}" />`;
    html += `<text x="${x}" y="134" fill="#64748b" font-size="8" text-anchor="middle">${label}</text>`;
  });
  
  if (Number.isFinite(lsAverage)) {
    const x = 56 + groupAverages.length * groupWidth + 8;
    const y = 112 - ((lsAverage - minVal) / range) * 94;
    const height = Math.abs(y - zeroY);
    html += `<rect x="${x - 5}" y="${lsAverage >= 0 ? y : zeroY}" width="10" height="${Math.max(1, height)}" fill="#f97316" />`;
    html += `<text x="${x}" y="134" fill="#64748b" font-size="8" text-anchor="middle">LS</text>`;
  }
  
  html += `</svg>`;
  
  return html;
}

function renderIcTimeSeriesChartV2(detailData) {
  const icSeries = detailData.ic_time_series || [];
  if (!icSeries.length) {
    return `<svg viewBox="0 0 452 220" class="research-svg"><text x="226" y="112" fill="#9ca3af" font-size="12" text-anchor="middle">暂无 IC 时序数据</text></svg>`;
  }

  const icValues = icSeries.map((item) => Number(item.ic)).filter(Number.isFinite);
  const dates = icSeries.map((item) => item.date);
  const axis = niceAxisRange(icValues, 0.12);
  const minVal = axis.min;
  const maxVal = axis.max;
  const range = maxVal - minVal || 1;
  const totalLength = icSeries.length;
  const plot = { left: 62, top: 30, right: 426, bottom: 164 };
  const width = plot.right - plot.left;
  const height = plot.bottom - plot.top;
  const zeroY = Math.max(plot.top, Math.min(plot.bottom, plot.bottom - ((0 - minVal) / range) * height));
  const displayStep = Math.max(1, Math.ceil(totalLength / 56));
  const visibleBars = Math.ceil(totalLength / displayStep);
  const barWidth = Math.max(3.5, Math.min(8, width / Math.max(visibleBars, 1) - 2));

  let html = `<svg viewBox="0 0 452 224" class="research-svg">`;
  html += `<line x1="${plot.left}" y1="${plot.top}" x2="${plot.left}" y2="${plot.bottom}" stroke="#dbe4f0" stroke-width="1" />`;
  html += `<line x1="${plot.left}" y1="${plot.bottom}" x2="${plot.right}" y2="${plot.bottom}" stroke="#dbe4f0" stroke-width="1" />`;
  html += `<text x="${plot.left}" y="16" fill="#5f7189" font-size="12" font-weight="700">IC 值</text>`;

  limitAxisTicks(axis.ticks, 6).forEach((val) => {
    const y = plot.bottom - ((val - minVal) / range) * height;
    html += `<line x1="${plot.left}" y1="${y}" x2="${plot.right}" y2="${y}" stroke="#eef3f8" stroke-width="1" />`;
    html += `<text x="${plot.left - 10}" y="${y + 4}" fill="#5f7189" font-size="11" text-anchor="end">${formatCompactAxisTick(val, range)}</text>`;
  });

  html += `<line x1="${plot.left}" y1="${zeroY}" x2="${plot.right}" y2="${zeroY}" stroke="#9aa8ba" stroke-width="1" stroke-dasharray="4,4" />`;

  for (let i = 0; i < icSeries.length; i += displayStep) {
    const ic = Number(icSeries[i]?.ic);
    if (!Number.isFinite(ic)) continue;
    const x = plot.left + (i / Math.max(totalLength - 1, 1)) * width;
    const y = plot.bottom - ((ic - minVal) / range) * height;
    const clampedY = Math.max(plot.top, Math.min(plot.bottom, y));
    const barHeight = Math.max(1.5, Math.abs(clampedY - zeroY));
    const isPositive = ic >= 0;
    html += `<rect x="${(x - barWidth / 2).toFixed(2)}" y="${(isPositive ? clampedY : zeroY).toFixed(2)}" width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="1.4" fill="${isPositive ? "#23a66f" : "#e05252"}" opacity="0.66" />`;
  }

  evenIndexTicks(dates, 4).forEach((tick) => {
    const x = plot.left + (tick.index / Math.max(totalLength - 1, 1)) * width;
    html += `<line x1="${x}" y1="${plot.bottom}" x2="${x}" y2="${plot.bottom + 8}" stroke="#dbe4f0" stroke-width="1" />`;
    html += `<text x="${x}" y="${plot.bottom + 31}" fill="#5f7189" font-size="12" text-anchor="middle">${tick.label}</text>`;
  });

  html += `</svg>`;
  return html;
}

function renderGroupPerformanceChartV2(detailData) {
  const groupReturns = detailData.group_returns || {};
  const groups = Object.keys(groupReturns)
    .filter((key) => key !== "long_short")
    .sort((a, b) => Number(a) - Number(b));

  if (!groups.length) {
    return `<svg viewBox="0 0 452 220" class="research-svg"><text x="226" y="112" fill="#9ca3af" font-size="12" text-anchor="middle">暂无分组收益数据</text></svg>`;
  }

  const groupAverages = groups
    .map((group) => {
      const values = (groupReturns[group] || []).map((item) => Number(item.return)).filter(Number.isFinite);
      if (!values.length) return null;
      return {
        group,
        value: values.reduce((sum, value) => sum + value, 0) / values.length,
      };
    })
    .filter(Boolean);

  let lsAverage = null;
  if (groupReturns.long_short) {
    const values = groupReturns.long_short.map((item) => Number(item.return)).filter(Number.isFinite);
    if (values.length) {
      lsAverage = values.reduce((sum, value) => sum + value, 0) / values.length;
    }
  }

  const barItems = [
    ...groupAverages.map((item) => ({
      ...item,
      label: Number.isFinite(Number(item.group)) ? `G${Number(item.group).toFixed(0)}` : `G${item.group}`,
    })),
    ...(Number.isFinite(lsAverage) ? [{ group: "long_short", label: "LS", value: lsAverage, longShort: true }] : []),
  ];
  const axis = niceAxisRange(barItems.map((item) => item.value), 0.18);
  const minVal = axis.min;
  const maxVal = axis.max;
  const range = maxVal - minVal || 0.02;
  const plot = { left: 62, top: 30, right: 426, bottom: 164 };
  const width = plot.right - plot.left;
  const height = plot.bottom - plot.top;
  const zeroY = Math.max(plot.top, Math.min(plot.bottom, plot.bottom - ((0 - minVal) / range) * height));
  const slotWidth = width / Math.max(barItems.length, 1);
  const barWidth = Math.max(10, Math.min(22, slotWidth * 0.52));
  const palette = ["#d8e9ff", "#bad7ff", "#93c0ff", "#67a1f2", "#3f7ddd", "#245fc5", "#1f4ca3", "#1b3d86", "#18356e", "#112a58"];

  let html = `<svg viewBox="0 0 452 224" class="research-svg">`;
  html += `<line x1="${plot.left}" y1="${plot.top}" x2="${plot.left}" y2="${plot.bottom}" stroke="#dbe4f0" stroke-width="1" />`;
  html += `<line x1="${plot.left}" y1="${plot.bottom}" x2="${plot.right}" y2="${plot.bottom}" stroke="#dbe4f0" stroke-width="1" />`;
  html += `<text x="${plot.left}" y="16" fill="#5f7189" font-size="12" font-weight="700">日均收益</text>`;

  limitAxisTicks(axis.ticks, 6).forEach((val) => {
    const y = plot.bottom - ((val - minVal) / range) * height;
    html += `<line x1="${plot.left}" y1="${y}" x2="${plot.right}" y2="${y}" stroke="#eef3f8" stroke-width="1" />`;
    html += `<text x="${plot.left - 10}" y="${y + 4}" fill="#5f7189" font-size="11" text-anchor="end">${formatCompactAxisTick(val, range)}</text>`;
  });

  html += `<line x1="${plot.left}" y1="${zeroY}" x2="${plot.right}" y2="${zeroY}" stroke="#9aa8ba" stroke-width="1" stroke-dasharray="4,4" />`;

  barItems.forEach((item, index) => {
    const x = plot.left + slotWidth * index + slotWidth / 2;
    const y = plot.bottom - ((item.value - minVal) / range) * height;
    const clampedY = Math.max(plot.top, Math.min(plot.bottom, y));
    const barHeight = Math.max(1.5, Math.abs(clampedY - zeroY));
    const isPositive = item.value >= 0;
    const color = item.longShort ? "#f97316" : palette[index % palette.length];
    html += `<rect x="${(x - barWidth / 2).toFixed(2)}" y="${(isPositive ? clampedY : zeroY).toFixed(2)}" width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="2" fill="${color}" />`;
    html += `<text x="${x.toFixed(2)}" y="${plot.bottom + 31}" fill="#5f7189" font-size="11" text-anchor="middle">${item.label}</text>`;
  });

  html += `</svg>`;
  return html;
}

function chartThemeTokens() {
  const isDark = document.body.dataset.theme === "dark";
  const groupPalette = isDark
    ? ["#60a5fa", "#22d3ee", "#2dd4bf", "#34d399", "#a3e635", "#facc15", "#fb923c", "#f87171", "#e879f9", "#c084fc"]
    : ["#2563eb", "#0891b2", "#0f9f8f", "#16a34a", "#65a30d", "#d97706", "#ea580c", "#dc2626", "#c026d3", "#7c3aed"];
  return {
    text: isDark ? "#e5edf8" : "#1f3147",
    muted: isDark ? "#93a4ba" : "#6b7d93",
    axis: isDark ? "#304258" : "#d6e0ec",
    grid: isDark ? "rgba(84, 103, 126, 0.24)" : "#edf2f8",
    tooltipBg: isDark ? "rgba(12, 18, 28, 0.96)" : "rgba(255, 255, 255, 0.96)",
    tooltipBorder: isDark ? "#2d4058" : "#d7e2ef",
    positive: isDark ? "#34d399" : "#16a34a",
    negative: isDark ? "#fb7185" : "#dc2626",
    longShort: isDark ? "#fbbf24" : "#f97316",
    line: isDark ? "#60a5fa" : "#2563eb",
    groupPalette,
  };
}

function chartDateLabel(value) {
  return String(value || "").slice(0, 10);
}

function chartMonthLabel(value) {
  return String(value || "").slice(0, 7);
}

function setEchart(container, option) {
  if (!container || !window.echarts) return null;
  container.innerHTML = "";
  container.classList.add("echart-active");
  const chart = window.echarts.getInstanceByDom(container) || window.echarts.init(container, null, {
    renderer: "canvas",
    useDirtyRect: true,
  });
  chart.setOption(option, true);
  window.setTimeout(() => chart.resize(), 0);
  return chart;
}

function renderEchartsStratification(container, detailData) {
  const tokens = chartThemeTokens();
  const stratification = detailData.stratification || {};
  const dates = Array.isArray(stratification.dates) ? stratification.dates.map(chartDateLabel) : [];
  const equityByGroup = stratification.equity_by_group || stratification.equityByGroup || {};
  const groupKeys = Object.keys(equityByGroup)
    .filter((key) => Array.isArray(equityByGroup[key]) && equityByGroup[key].length)
    .sort((a, b) => Number(a) - Number(b));
  const series = groupKeys.map((key, index) => ({
    name: `G${key}`,
    type: "line",
    data: equityByGroup[key],
    showSymbol: false,
    connectNulls: false,
    smooth: false,
    lineStyle: {
      width: index === 0 || index === groupKeys.length - 1 ? 2.4 : 1.7,
      color: tokens.groupPalette[index % tokens.groupPalette.length],
      opacity: index === 0 || index === groupKeys.length - 1 ? 1 : 0.86,
    },
    emphasis: { focus: "series" },
  }));
  if (Array.isArray(stratification.equity) && stratification.equity.length) {
    series.push({
      name: "LS",
      type: "line",
      data: stratification.equity,
      showSymbol: false,
      connectNulls: false,
      smooth: false,
      lineStyle: { width: 3, color: tokens.longShort, type: "dashed" },
      emphasis: { focus: "series" },
    });
  }
  if (!dates.length || !series.length) return null;
  return setEchart(container, {
    animationDuration: 520,
    color: tokens.groupPalette,
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.tooltipBg,
      borderColor: tokens.tooltipBorder,
      textStyle: { color: tokens.text, fontSize: 12 },
      valueFormatter: (value) => (Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "-"),
    },
    legend: {
      type: "scroll",
      bottom: 6,
      left: "center",
      itemWidth: 16,
      itemHeight: 8,
      textStyle: { color: tokens.muted, fontSize: 11 },
    },
    grid: { left: 58, right: 22, top: 24, bottom: 56, containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: dates,
      axisLabel: {
        color: tokens.muted,
        formatter: chartMonthLabel,
        hideOverlap: true,
        margin: 14,
      },
      axisLine: { lineStyle: { color: tokens.axis } },
      axisTick: { lineStyle: { color: tokens.axis } },
    },
    yAxis: {
      type: "value",
      name: "累计净值",
      scale: true,
      nameTextStyle: { color: tokens.muted, fontWeight: 700, padding: [0, 28, 0, 0] },
      axisLabel: { color: tokens.muted, formatter: (value) => Number(value).toFixed(2) },
      splitLine: { lineStyle: { color: tokens.grid } },
    },
    series,
  });
}

function renderEchartsIc(container, detailData) {
  const tokens = chartThemeTokens();
  const icSeries = Array.isArray(detailData.ic_time_series) ? detailData.ic_time_series : [];
  const dates = icSeries.map((item) => chartDateLabel(item.date));
  const values = icSeries.map((item) => Number(item.ic));
  if (!dates.length || !values.some(Number.isFinite)) return null;
  return setEchart(container, {
    animationDuration: 420,
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.tooltipBg,
      borderColor: tokens.tooltipBorder,
      textStyle: { color: tokens.text, fontSize: 12 },
      valueFormatter: (value) => (Number.isFinite(Number(value)) ? Number(value).toFixed(4) : "-"),
    },
    grid: { left: 50, right: 14, top: 28, bottom: 42, containLabel: true },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: tokens.muted, formatter: chartMonthLabel, hideOverlap: true, margin: 12 },
      axisLine: { lineStyle: { color: tokens.axis } },
      axisTick: { lineStyle: { color: tokens.axis } },
    },
    yAxis: {
      type: "value",
      name: "IC 值",
      nameTextStyle: { color: tokens.muted, fontWeight: 700 },
      axisLabel: { color: tokens.muted, formatter: (value) => Number(value).toFixed(2) },
      splitLine: { lineStyle: { color: tokens.grid } },
    },
    series: [
      {
        name: "Rank IC",
        type: "bar",
        data: values,
        barMaxWidth: 7,
        itemStyle: {
          borderRadius: [2, 2, 0, 0],
          color: (params) => (Number(params.value) >= 0 ? tokens.positive : tokens.negative),
          opacity: 0.76,
        },
        markLine: {
          silent: true,
          symbol: "none",
          data: [{ yAxis: 0 }],
          lineStyle: { color: tokens.axis, width: 1 },
          label: { show: false },
        },
      },
    ],
  });
}

function renderEchartsGroupPerformance(container, detailData) {
  const tokens = chartThemeTokens();
  const groupReturns = detailData.group_returns || {};
  const groups = Object.keys(groupReturns)
    .filter((key) => key !== "long_short")
    .sort((a, b) => Number(a) - Number(b));
  const items = groups
    .map((group) => {
      const values = (groupReturns[group] || []).map((item) => Number(item.return)).filter(Number.isFinite);
      if (!values.length) return null;
      return {
        label: `G${group}`,
        value: values.reduce((sum, value) => sum + value, 0) / values.length,
      };
    })
    .filter(Boolean);
  const lsValues = (groupReturns.long_short || []).map((item) => Number(item.return)).filter(Number.isFinite);
  if (lsValues.length) {
    items.push({
      label: "LS",
      value: lsValues.reduce((sum, value) => sum + value, 0) / lsValues.length,
      longShort: true,
    });
  }
  if (!items.length) return null;
  return setEchart(container, {
    animationDuration: 420,
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.tooltipBg,
      borderColor: tokens.tooltipBorder,
      textStyle: { color: tokens.text, fontSize: 12 },
      valueFormatter: (value) => (Number.isFinite(Number(value)) ? Number(value).toFixed(5) : "-"),
    },
    grid: { left: 56, right: 16, top: 28, bottom: 42, containLabel: true },
    xAxis: {
      type: "category",
      data: items.map((item) => item.label),
      axisLabel: { color: tokens.muted, fontWeight: 700, margin: 14 },
      axisLine: { lineStyle: { color: tokens.axis } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: "日均收益",
      nameTextStyle: { color: tokens.muted, fontWeight: 700 },
      axisLabel: { color: tokens.muted, formatter: (value) => Number(value).toFixed(4) },
      splitLine: { lineStyle: { color: tokens.grid } },
    },
    series: [
      {
        name: "日均收益",
        type: "bar",
        data: items.map((item) => item.value),
        barMaxWidth: 22,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: (params) =>
            items[params.dataIndex]?.longShort
              ? tokens.longShort
              : tokens.groupPalette[params.dataIndex % tokens.groupPalette.length],
        },
      },
    ],
  });
}

function mountDetailCharts(factorId) {
  if (!window.echarts || state.view !== "detail" || state.detailTab !== "analysis") return;
  const detailData = state.factorDetailData?.[factorId];
  if (!detailData) return;
  renderEchartsStratification(document.querySelector("#stratChart"), detailData);
  renderEchartsIc(document.querySelector("#icChart"), detailData);
  renderEchartsGroupPerformance(document.querySelector("#groupChart"), detailData);
}

function metricCard(label, value, helper, tone = "") {
  return `
    <article class="metric-card ${tone}">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${helper || ""}</small>
    </article>
  `;
}

function renderArtifactsPanel(factor) {
  const hasProofIssue = factor.proof_status && factor.proof_status !== "passed";
  const hasTruthIssue = isTruthIssue(factor.truth_status);
  const resultTone = hasProofIssue || hasTruthIssue ? "badge-red" : "badge-green";
  const resultText = hasProofIssue || hasTruthIssue ? "验证异常" : "验证通过";
  const proofResultText = factor.proof_status === "passed" ? "复现通过" : "复现失败";
  const proofResultTone = factor.proof_status === "passed" ? "badge-green" : "badge-red";
  const artifacts = [
    ["proof.json", "单因子复现证明", "文件已生成", "badge-green", proofResultText, proofResultTone, "proof"],
    ["evaluation.json", "任务汇总评估", "文件已生成", "badge-green", resultText, resultTone, "evaluation_json"],
    ["proof_report.md", "Markdown 研究报告", "文件已生成", "badge-green", "报告已生成", "badge-gray", "research_report_markdown"],
    ["factor values", "因子值数据表", "文件已生成", "badge-green", "数据已生成", "badge-gray", "factor_frame"],
  ];
  return `
    <section class="summary-card">
      <header>验证产物（Artifacts）</header>
      <div class="artifact-note">
        Artifacts 用于内部验证和结果追溯，可能包含路径、数据源、失败原因等内部信息，建议仅员工权限可见。
      </div>
      ${
        hasProofIssue || hasTruthIssue
          ? `<div class="artifact-alert">
              当前因子存在验证异常：复现状态为 <strong>${proofValue(factor.proof_status)}</strong>，
              真值状态为 <strong>${truthValue(factor.truth_status)}</strong>。
              下方“已生成”只代表产物文件存在，不代表验证通过。
            </div>`
          : ""
      }
      <table class="summary-table artifact-table">
        <thead>
          <tr>
            <th>产物名称</th>
            <th>类型</th>
            <th>产物状态</th>
            <th>验证结果</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${artifacts
            .map(
              ([name, description, artifactStatus, artifactBadgeClass, validationStatus, validationBadgeClass, kind]) => `
                <tr>
                  <td>${name}</td>
                  <td>${description}</td>
                  <td><span class="badge ${artifactBadgeClass}">${artifactStatus}</span></td>
                  <td><span class="badge ${validationBadgeClass}">${validationStatus}</span></td>
                  <td><button type="button" class="text-button" data-artifact="${kind}">查看</button></td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </section>
  `;
}

function bindEvents() {
  els.navItems.forEach((button) => {
    button.addEventListener("click", () => showMainView(button.dataset.view));
  });
  // A deployment without a Quant Desk must not offer one. The section is an iframe onto
  // a separate service; when none is configured the entries are hidden rather than
  // opening an empty view over a refused connection.
  if (!QUANT_DESK_ENABLED) {
    els.quantDeskNavGroup?.classList.add("hidden");
    els.quantDeskNavGroup?.setAttribute("hidden", "");
    els.quantDeskTabs?.forEach((button) => button.closest("li, a, button")?.classList.add("hidden"));
  }
  els.quantDeskTabs?.forEach((button) => {
    button.addEventListener("click", () => {
      state.quantDeskPath = button.dataset.quantDeskPath || "";
      showMainView("quant-desk");
      renderQuantDeskTabs();
      setQuantDeskFrameSrc(true);
    });
  });
  els.monitorFilters.forEach((button) => {
    button.addEventListener("click", () => {
      state.monitorFilter = button.dataset.monitorFilter || "all";
      renderMonitor();
    });
  });
  els.monitorDirectionFilters?.querySelectorAll("[data-monitor-direction]").forEach((button) => {
    button.addEventListener("click", () => {
      state.monitorDirectionFilter = button.dataset.monitorDirection || "all";
      renderMonitor();
    });
  });
  els.monitorComparisonFilters?.querySelectorAll("[data-monitor-comparison]").forEach((button) => {
    button.addEventListener("click", () => {
      state.monitorComparisonFilter = button.dataset.monitorComparison || "all";
      renderMonitor();
    });
  });
  els.monitorSearchInput?.addEventListener("input", (event) => {
    state.monitorQuery = event.target.value;
    renderMonitor();
  });
  els.usableOnlyToggle?.addEventListener("change", (event) => {
    state.usableOnly = event.target.checked;
    state.page = 1;
    applyFilters();
  });
  [
    [els.researchUniverse, "universe"],
    [els.researchPeriod, "period"],
    [els.researchPortfolio, "portfolio"],
    [els.researchCost, "cost"],
    [els.researchLimitFilter, "limitFilter"],
  ].forEach(([control, key]) => {
    control?.addEventListener("change", (event) => {
      state.researchParams[key] = event.target.value;
    });
  });
  els.proofFilter.addEventListener("change", (event) => {
    state.proof = event.target.value;
    state.page = 1;
    applyFilters();
  });
  els.truthFilter.addEventListener("change", (event) => {
    state.truth = event.target.value;
    state.page = 1;
    applyFilters();
  });
  els.reuseFilter.addEventListener("change", (event) => {
    state.reuse = event.target.value;
    state.page = 1;
    applyFilters();
  });
  els.comparisonFilter?.addEventListener("change", (event) => {
    state.comparison = event.target.value;
    state.page = 1;
    applyFilters();
  });
  els.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    state.page = 1;
    applyFilters();
  });
  els.resetFiltersButton.addEventListener("click", () => {
    state.category = "全部";
    state.selectedCategories = new Set(JQ_FACTOR_CATEGORIES);
    state.library = "全部";
    state.market = firstAvailableMarket(marketCounts());
    state.monitorMarket = state.market;
    state.proof = "all";
    state.truth = "all";
    state.reuse = "all";
    state.comparison = "all";
    state.usableOnly = false;
    state.query = "";
    state.monitorQuery = "";
    state.monitorComparisonFilter = "all";
    state.page = 1;
    els.proofFilter.value = "all";
    els.truthFilter.value = "all";
    els.reuseFilter.value = "all";
    if (els.comparisonFilter) els.comparisonFilter.value = "all";
    if (els.usableOnlyToggle) els.usableOnlyToggle.checked = false;
    els.searchInput.value = "";
    if (els.monitorSearchInput) els.monitorSearchInput.value = "";
    renderTabs({ factors: state.rawFactors, categories: countCategories(), libraries: countLibraries() });
    applyFilters();
    if (state.view === "monitor") renderMonitor();
  });
  els.themeToggleButton?.addEventListener("click", toggleTheme);
  els.refreshButton.addEventListener("click", loadData);
  els.quantDeskReloadButton?.addEventListener("click", () => {
    state.quantDeskCheckedAt = null;
    setQuantDeskFrameSrc(true);
    checkQuantDeskHealth();
  });
  els.quantDeskRetryButton?.addEventListener("click", () => {
    state.quantDeskCheckedAt = null;
    checkQuantDeskHealth();
  });
  els.collapseButton.addEventListener("click", () => {
    window.clearTimeout(collapseTimer);
    els.appShell.classList.add("is-collapsing");

    const collapsed = !els.appShell.classList.contains("sidebar-collapsed");
    window.requestAnimationFrame(() => {
      els.appShell.classList.toggle("sidebar-collapsed", collapsed);
      els.collapseButton.setAttribute("aria-label", collapsed ? "展开侧边栏" : "收起侧边栏");
      els.collapseButton.setAttribute("aria-expanded", String(!collapsed));
      collapseTimer = window.setTimeout(() => {
        els.appShell.classList.remove("is-collapsing");
      }, 260);
    });
  });
  document.querySelectorAll("th.sortable").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.sort;
      cycleSort(key);
      applyFilters();
    });
  });
  document.querySelectorAll("th.monitor-sortable").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.monitorSort;
      cycleMonitorSort(key);
      renderMonitor();
    });
  });
  document.querySelectorAll("th.strategy-sortable").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.strategySort;
      cycleStrategySort(key);
      renderStrategy();
    });
  });
  window.addEventListener("hashchange", () => {
    if (!window.location.hash && state.view === "detail") closeDetail();
    if (window.location.hash === "#quant-desk") {
      state.view = "quant-desk";
      renderView();
    }
    if (window.location.hash === "#strategy-builder") {
      state.view = "strategy-builder";
      renderView();
    }
    if (window.location.hash === "#strategy-board") {
      state.view = "strategy-board";
      renderView();
    }
  });
  document.addEventListener("pointerup", endDragSelection);
  document.addEventListener("pointercancel", endDragSelection);
}

function countCategories() {
  return countJqCategories(state.rawFactors);
}

function countLibraries() {
  const counts = {};
  state.rawFactors.forEach((factor) => {
    counts[factor.library] = (counts[factor.library] || 0) + 1;
  });
  return counts;
}

let appStarted = false;

function isAuthenticated() {
  return window.sessionStorage.getItem(ACCESS_SESSION_KEY) === "1";
}

// The API issues the session. The typed password is the only secret here; the token it
// returns is what the data routes are checked against.
async function loginThroughApi(password) {
  try {
    const response = await fetch(`${API_HOST || ""}/api/agents/factor-lab/auth/login`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (response.status === 401) return { ok: false, reason: "wrong-password" };
    if (response.status === 503) return { ok: false, reason: "not-configured" };
    if (!response.ok) return { ok: false, reason: `http-${response.status}` };
    const payload = await response.json();
    return { ok: Boolean(payload.token), token: payload.token };
  } catch (error) {
    return { ok: false, reason: "unreachable" };
  }
}

function showApp() {
  document.body.classList.remove("auth-locked");
  els.loginPassword && (els.loginPassword.value = "");
  if (els.loginError) els.loginError.textContent = "";
}

function showLogin(message = "") {
  document.body.classList.add("auth-locked");
  if (els.loginError) els.loginError.textContent = message;
  window.setTimeout(() => els.loginPassword?.focus(), 50);
}

function startApp() {
  if (appStarted) return;
  appStarted = true;
  bindEvents();
  loadData();
  startAutoRefresh();
  bindResearchEvents();
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const password = String(els.loginPassword?.value || "");
  if (!password) {
    showLogin("请输入访问密码");
    return;
  }

  const viaApi = await loginThroughApi(password);
  if (viaApi.ok) {
    state.authToken = viaApi.token;
    window.sessionStorage.setItem(AUTH_TOKEN_KEY, viaApi.token);
    window.sessionStorage.setItem(ACCESS_SESSION_KEY, "1");
    showApp();
    startApp();
    return;
  }
  if (viaApi.reason === "wrong-password") {
    showLogin("密码不正确，请重试");
    return;
  }
  if (viaApi.reason === "not-configured") {
    // Fail closed on the server, but do not pretend here: say the API has no password
    // and let the local gate through only so an operator can still reach the page.
    console.warn("API 未配置客户端密码（FACTOR_LAB_CLIENT_PASSWORD）：数据接口将返回 503");
    if (password === ACCESS_PASSWORD) {
      window.sessionStorage.setItem(ACCESS_SESSION_KEY, "1");
      showApp();
      startApp();
      showToast("服务端未配置访问密码：数据接口会被拒绝，请联系管理员");
      return;
    }
    showLogin("服务端未配置访问密码，且本地口令不正确");
    return;
  }
  if (password === ACCESS_PASSWORD) {
    // No API reachable (pure static preview): keep the local gate, but data routes
    // will simply have nothing to show.
    window.sessionStorage.setItem(ACCESS_SESSION_KEY, "1");
    showApp();
    startApp();
    showToast("未连接到数据服务：仅显示界面，不含客户数据");
    return;
  }
  showLogin("密码不正确，请重试");
}

function logout() {
  window.sessionStorage.removeItem(ACCESS_SESSION_KEY);
  window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
  state.authToken = null;
  showLogin("已退出登录");
}

function initAuth() {
  els.loginForm?.addEventListener("submit", handleLoginSubmit);
  els.logoutButton?.addEventListener("click", logout);
  state.authToken = window.sessionStorage.getItem(AUTH_TOKEN_KEY);
  if (isAuthenticated()) {
    showApp();
    startApp();
  } else {
    showLogin();
  }
}

applyTheme(currentTheme());
initGlossary();
initAuth();

function bindResearchEvents() {
  const runBtn = document.getElementById("runResearchButton");
  const clearBtn = document.getElementById("clearResearchButton");
  
  if (runBtn) {
    runBtn.addEventListener("click", runRealDataResearch);
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", clearResearchResults);
  }
}

async function runRealDataResearch() {
  const factorSet = document.getElementById("researchFactorSet").value;
  const factorsInput = document.getElementById("researchFactors").value;
  const symbolsInput = document.getElementById("researchSymbols").value;
  const startDate = document.getElementById("researchStartDate").value;
  const endDate = document.getElementById("researchEndDate").value;
  
  const factors = factorsInput.split(",").map(f => f.trim()).filter(f => f);
  const symbols = symbolsInput.split(",").map(s => s.trim()).filter(s => s);
  
  if (factors.length === 0) {
    alert("请输入因子名称");
    return;
  }
  if (symbols.length === 0) {
    alert("请输入股票代码");
    return;
  }
  
  document.getElementById("researchLoading").classList.remove("hidden");
  document.getElementById("researchResults").classList.add("hidden");
  
  try {
    const response = await fetch(`${API_BASE}/quant-api/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        factors,
        symbols,
        start_date: startDate,
        end_date: endDate,
        factor_set: factorSet,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const result = await response.json();
    
    if (result.error) {
      alert("研究失败: " + result.error);
      return;
    }
    
    renderResearchResults(result);
  } catch (error) {
    alert("研究请求失败: " + error.message);
  } finally {
    document.getElementById("researchLoading").classList.add("hidden");
  }
}

function renderResearchResults(result) {
  const resultsBody = document.getElementById("researchResultsBody");
  const jobIdBadge = document.getElementById("researchJobId");
  
  jobIdBadge.textContent = result.job_id || "";
  
  const rows = Object.entries(result.results || {}).map(([name, data]) => {
    const icMean = Number.isFinite(data.ic_mean) ? data.ic_mean.toFixed(4) : "-";
    const icIr = Number.isFinite(data.ic_ir) ? data.ic_ir.toFixed(4) : "-";
    const rankIc = Number.isFinite(data.rank_ic_mean) ? data.rank_ic_mean.toFixed(4) : "-";
    const sharpe = Number.isFinite(data.long_short_sharpe) ? data.long_short_sharpe.toFixed(2) : "-";
    const maxDd = Number.isFinite(data.long_short_max_drawdown) ? data.long_short_max_drawdown.toFixed(2) : "-";
    const coverage = Number.isFinite(data.coverage) ? data.coverage.toFixed(1) + "%" : "-";
    const lsMean = Number.isFinite(data.long_short_mean) ? data.long_short_mean.toFixed(4) : "-";
    
    return `
      <tr>
        <td>${escapeHtml(name)}</td>
        <td>${icMean}</td>
        <td>${icIr}</td>
        <td>${rankIc}</td>
        <td>${sharpe}</td>
        <td>${maxDd}</td>
        <td>${coverage}</td>
        <td>${lsMean}</td>
      </tr>
    `;
  });
  
  resultsBody.innerHTML = rows.join("");
  document.getElementById("researchResults").classList.remove("hidden");
}

function clearResearchResults() {
  document.getElementById("researchResults").classList.add("hidden");
  document.getElementById("researchResultsBody").innerHTML = "";
  document.getElementById("researchJobId").textContent = "";
}
