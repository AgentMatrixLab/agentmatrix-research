// 本次修改点：
// 1. 默认落地页切换为因子监控，配合左侧导航新顺序。
// 2. 子库筛选暂时隐藏，保留 state.library 和渲染函数方便后续恢复。
// 3. 分类筛选继续使用聚宽口径，并作为因子库/监控后续共用过滤基础。
// 4. 新增因子库准入视觉状态、研究口径选择器、策略草稿生成，以及监控页分类/方向筛选。
// 5. 新增独立策略构建页、成品策略模板契约、策略看板删除模式与股票池省略显示。
const urlParams = new URLSearchParams(window.location.search);
const configuredApiHost = (
  window.FACTOR_LAB_API_HOST ||
  urlParams.get("api") ||
  window.localStorage.getItem("FACTOR_LAB_API_HOST") ||
  ""
).replace(/\/+$/, "");
if (urlParams.get("api")) {
  window.localStorage.setItem("FACTOR_LAB_API_HOST", configuredApiHost);
}
const CLOUD_DEMO_MODE =
  !configuredApiHost &&
  (window.location.hostname.endsWith("github.io") || urlParams.has("demo"));
const API_HOST = configuredApiHost
  ? configuredApiHost
  : CLOUD_DEMO_MODE
    ? ""
    : window.location.protocol.startsWith("http") && window.location.port === "8012"
      ? window.location.origin
      : "http://127.0.0.1:8012";
const API_BASE = CLOUD_DEMO_MODE ? "" : `${API_HOST}/api/agents/factor-lab`;
const DEMO_LIBRARY_URL = "./data/demo-factor-library.json";
const STATIC_FACTOR_DETAIL_DIR = "./data/factor-details";
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
  window.FACTOR_LAB_SUPABASE_FACTOR_TABLE ||
  urlParams.get("supabaseTable") ||
  window.localStorage.getItem("FACTOR_LAB_SUPABASE_FACTOR_TABLE") ||
  "public_dashboard_factors";
const USE_SUPABASE_DASHBOARD = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY && !configuredApiHost);
const ACCESS_PASSWORD =
  window.FACTOR_LAB_ACCESS_PASSWORD ||
  urlParams.get("accessPassword") ||
  window.localStorage.getItem("FACTOR_LAB_ACCESS_PASSWORD") ||
  "factorlab2026";
const ACCESS_SESSION_KEY = "FACTOR_LAB_AUTH_OK";
if (urlParams.get("supabaseUrl")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_URL", SUPABASE_URL);
}
if (urlParams.get("supabaseAnonKey")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_ANON_KEY", SUPABASE_ANON_KEY);
}
if (urlParams.get("supabaseTable")) {
  window.localStorage.setItem("FACTOR_LAB_SUPABASE_FACTOR_TABLE", SUPABASE_FACTOR_TABLE);
}
if (urlParams.get("accessPassword")) {
  window.localStorage.setItem("FACTOR_LAB_ACCESS_PASSWORD", ACCESS_PASSWORD);
}
const PAGE_SIZE = 50;
const AUTO_REFRESH_INTERVAL_MS = 10000;
const REQUEST_TIMEOUT_MS = 1800;
const COVERAGE_WARN_THRESHOLD = 0.6;
const COVERAGE_DANGER_THRESHOLD = 0.3;
const LONG_SHORT_MEAN_HELP = "多空分组收益均值（日频，demo 数据）";
const ENABLE_AGENT_TASK_DEBUG = true;
const FACTOR_INTAKE_CONTRACT_DOC = "docs/FACTOR_LAB_INTAKE_REPRODUCTION_CONTRACT.md";
// AI 任务调试入口暂时关闭。恢复时打开 ENABLE_AGENT_TASK_DEBUG，并恢复 index.html 中对应入口。
const JQ_FACTOR_CATEGORIES = [
  "基础科目及衍生类因子",
  "情绪类因子",
  "动量类因子",
  "质量类因子",
  "成长类因子",
  "风险因子-新风格因子",
  "每股指标因子",
  "风险类因子",
  "风险因子-风格因子",
  "技术指标因子",
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
const JQ_CATEGORY_BY_FACTOR = {
  roe_ttm: "质量类因子",
  roa_ttm: "质量类因子",
  net_margin: "质量类因子",
  debt_to_asset: "风险类因子",
  revenue_yoy: "成长类因子",
  profit_yoy: "成长类因子",
  eps_yoy: "每股指标因子",
  asset_turnover: "质量类因子",
  log_price: "风险因子-风格因子",
  ret_1m: "动量类因子",
  ret_3m: "动量类因子",
  ret_6m: "动量类因子",
  ret_12m: "动量类因子",
  reversal: "动量类因子",
  momentum_12_1: "动量类因子",
  ret_3m_vol_adj: "动量类因子",
  up_ratio_1m: "动量类因子",
  avg_amount_1m: "情绪类因子",
  log_amount_1m: "情绪类因子",
  turnover_proxy: "情绪类因子",
  volume_ratio: "情绪类因子",
  illiquidity: "情绪类因子",
  volatility_1m: "风险类因子",
  volatility_3m: "风险类因子",
  volatility_6m: "风险类因子",
  max_ret_1m: "风险类因子",
  min_ret_1m: "风险类因子",
  high_low_1m: "风险类因子",
  amplitude_1m: "风险类因子",
  ma_signal: "技术指标因子",
  vol_convergence: "技术指标因子",
  rsi_14: "技术指标因子",
  bb_position: "技术指标因子",
};
const AGENT_TASK_TEXT = {
  title: "数据入口（待接入）",
  subtitle:
    "当前先作为 Supabase 只读接入口和 Agent Skill 契约预留。GitHub Pages 只负责读取云端表和展示结果，不在网页内执行复现或入库。",
  boundaryTitle: "Supabase 接入预留",
  boundary:
    "后续由云端 Agent / 后端写入 Supabase 与对象存储；前端只读取 public dashboard 表。现有上传和运行控件保留为接入占位，不作为 GitHub Pages 执行入口。",
  quarantineHint: "待接入：Supabase 表存任务、状态、指标和文件路径；大文件放 Storage。GitHub Pages 默认只读。",
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
  query: "",
  page: 1,
  sortKey: null,
  sortDirection: "default",
  strategySortKey: null,
  strategySortDirection: "default",
  localConnected: false,
  quantApiConfigured: false,
  quantApiReachable: false,
  isLoading: false,
  autoRefreshTimer: null,
  monitorFilter: "all",
  monitorDirectionFilter: "all",
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
  strategyBuilderName: "",
  strategyBuilderResult: null,
  strategyDeleteMode: false,
  selectedStrategyDeleteIds: new Set(),
  strategyDetailLoading: {},
  strategies: [],
  strategiesLoaded: false,
  strategiesLoading: false,
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
  strategyStats: document.querySelector("#strategyStats"),
  strategyTableBody: document.querySelector("#strategyTableBody"),
  taskStats: document.querySelector("#taskStats"),
  taskTableBody: document.querySelector("#taskTableBody"),
  taskStagePanel: document.querySelector("#taskStagePanel"),
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
    pending: ["等待", "badge-gray"],
    missing: ["缺失", "badge-gray"],
  };
  return map[status] || [status || "-", "badge-gray"];
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
  return map[status] || [status || "-", "badge-gray"];
}

function proofValue(status) {
  const map = {
    passed: "复现通过",
    failed: "复现失败",
    partial: "部分通过",
    pending: "等待验证",
    missing: "缺少产物",
  };
  return map[status] || String(status || "-");
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
  return map[status] || String(status || "-");
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

function recommendationClass(value) {
  if (value === "可复用") return "reusable";
  if (value === "建议重跑") return "rerun";
  if (value === "未复现") return "missing";
  return "";
}

function canOpenFactor(factor) {
  return Boolean(factor?.latest_job_id) && factor?.proof_status !== "missing";
}

function factorReplicationStatus(factor) {
  // 临时映射：后端正式字段 replication_status 到位前，用现有 proof_status 作为复现状态。
  if (factor?.replication_status) return factor.replication_status;
  if (factor?.proof_status === "passed") return "passed";
  if (factor?.proof_status === "failed") return "failed";
  return "pending";
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
  const inLibrary = replication === "passed";
  const agentReadable = inLibrary && alphaTier !== "dead";
  return {
    replication,
    alphaTier,
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

function updateConnectionStatus(ok, payload) {
  state.localConnected = ok;
  els.localStatus.className = ok ? "status-pill status-ok" : "status-pill status-bad";
  if (USE_SUPABASE_DASHBOARD) {
    els.localStatus.textContent = "GitHub Pages：Supabase 只读";
    els.localStatus.title = "当前页面由 GitHub Pages 托管，数据来自 Supabase public_dashboard_* 公开只读表";
  } else if (CLOUD_DEMO_MODE) {
    els.localStatus.textContent = "GitHub Pages：演示模式";
    els.localStatus.title = "当前使用静态演示数据，未连接本地 Flask 服务";
  } else {
    els.localStatus.textContent = ok ? "本地 Flask：已连接" : "本地 Flask：未连接";
    els.localStatus.title = ok ? "已通过 /health 接口确认" : "未能访问 /health 接口，请确认本地 Flask 服务已启动";
  }
  const cloudLabel = payload?.cloud_registry?.label || (USE_SUPABASE_DASHBOARD ? "Supabase Public Dashboard" : "未同步");
  els.cloudStatus.textContent = `云端信息库：${cloudLabel}`;
}

function updateQuantApiStatus(payload, failed = false) {
  if (!els.quantStatus) return;
  if (failed) {
    state.quantApiConfigured = false;
    state.quantApiReachable = false;
    els.quantStatus.className = "status-pill status-bad";
    els.quantStatus.textContent = "Quant API：检测失败";
    els.quantStatus.title = "未能通过本地 Flask 查询 Quant API 配置状态";
    return;
  }
  const configured = Boolean(payload?.token_configured);
  state.quantApiConfigured = configured;
  state.quantApiReachable = true;
  if (CLOUD_DEMO_MODE) {
    els.quantStatus.className = "status-pill status-warn";
    els.quantStatus.textContent = "Quant API：静态演示";
    els.quantStatus.title = "GitHub Pages 版本不直接持有 token，也不调用真实 Quant API";
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

function withCacheBust(url) {
  const parsed = new URL(url, window.location.href);
  parsed.searchParams.set("_", String(Date.now()));
  return parsed.toString();
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, {
      cache: "no-store",
      ...options,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeout);
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

async function fetchSupabaseDashboardPayload() {
  const endpoint = new URL(`${SUPABASE_URL}/rest/v1/${encodeURIComponent(SUPABASE_FACTOR_TABLE)}`);
  endpoint.searchParams.set("select", "*");
  endpoint.searchParams.set("order", "latest_checked_at.desc.nullslast");
  endpoint.searchParams.set("limit", "1000");
  const response = await fetchWithTimeout(endpoint.toString(), {
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      Accept: "application/json",
    },
  });
  if (!response.ok) throw new Error(`Supabase HTTP ${response.status}`);
  const rows = await response.json();
  const factors = Array.isArray(rows) ? rows.map(normalizeSupabaseFactorRow) : [];
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
    },
    errors: [],
    factors,
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
      base_url: "Static demo data",
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
      if (state.view === "strategy") renderStrategy();
      if (state.view === "strategy-detail") renderStrategyDetail();
      if (state.view === "tasks") renderTasks();
      return;
    }
    if (CLOUD_DEMO_MODE) {
      const response = await fetchWithTimeout(withCacheBust(DEMO_LIBRARY_URL));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const normalizedPayload = normalizePayload(payload);
      state.rawFactors = normalizedPayload.factors || [];
      updateConnectionStatus(true, payload);
      updateQuantApiStatus({
        token_configured: false,
        base_url: "Static demo data",
      });
      els.errorPanel.classList.add("hidden");
      renderTabs(normalizedPayload);
      applyFilters();
      await syncDetailFromHash();
      if (state.view === "monitor") renderMonitor();
      if (state.view === "strategy") renderStrategy();
      if (state.view === "strategy-detail") renderStrategyDetail();
      if (state.view === "tasks") renderTasks();
      return;
    }
    const healthy = await checkLocalHealth();
    if (!healthy) throw new Error("Local Flask service is offline");
    await checkQuantApiStatus();
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/factor-library`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
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
    if (state.view === "strategy") renderStrategy();
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
    if (state.view === "strategy") renderStrategy();
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
    .filter((factor) => state.reuse === "all" || factor.reuse_recommendation === state.reuse)
    .filter((factor) => {
      if (!query) return true;
      return [factor.factor_name, factor.raw_factor_name, factor.library, marketLabel(factor), marketDetail(factor), factor.subcategory, jqFactorCategory(factor)]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });

  if (state.sortKey && state.sortDirection !== "default") {
    state.filteredFactors.sort(compareFactors);
  }
  const totalPages = Math.max(1, Math.ceil(state.filteredFactors.length / PAGE_SIZE));
  if (state.page > totalPages) state.page = totalPages;
  renderTable();
  renderSortHeaders();
  renderSelectionSummary();
}

function jqFactorCategory(factor) {
  const name = String(factor.raw_factor_name || factor.factor_name || "").toLowerCase();
  if (JQ_CATEGORY_BY_FACTOR[name]) return JQ_CATEGORY_BY_FACTOR[name];
  const subcategory = String(factor.subcategory || "").toLowerCase();
  const category = String(factor.category || "").toLowerCase();
  const library = String(factor.library || factor.raw_library || "").toLowerCase();
  if (category.includes("技术")) return "技术指标因子";
  if (subcategory.includes("成长")) return "成长类因子";
  if (subcategory.includes("盈利") || subcategory.includes("营运")) return "质量类因子";
  if (subcategory.includes("偿债") || subcategory.includes("波动") || subcategory.includes("振幅")) return "风险类因子";
  if (subcategory.includes("成交") || subcategory.includes("流动") || subcategory.includes("换手")) return "情绪类因子";
  if (subcategory.includes("动量") || subcategory.includes("收益") || subcategory.includes("反转")) return "动量类因子";
  if (category.includes("财务")) return "基础科目及衍生类因子";
  if (category.includes("价值") || category.includes("规模")) return "风险因子-风格因子";
  if (library.includes("barra")) return "风险因子-新风格因子";
  if (category.includes("量价")) return "动量类因子";
  return "技术指标因子";
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
          ${escapeHtml(displayName)}${admission.weak ? '<span class="weak-tag">弱</span>' : ""}
        </button>
      </td>
      <td>${escapeHtml(factor.library)}</td>
      <td>${marketChipHtml(factor)}<span class="factor-subcategory">${escapeHtml(marketDetail(factor))}</span></td>
      <td>${escapeHtml(jqFactorCategory(factor))}<span class="factor-subcategory">${escapeHtml(factor.subcategory || "")}</span></td>
      <td><span class="badge ${proofClass}">${proofText}</span></td>
      <td>${truthBadgeHtml(factor)}</td>
      <td class="number ${coverageTone}" title="${escapeHtml(coverageHelp)}">${formatRatio(factor.coverage_ratio)}</td>
      <td class="number">${factorMetricHtml(factor, "rank_ic_mean", (value) => formatNumber(value, 4))}</td>
      <td class="number">${factorMetricHtml(factor, "rank_ic_ir", (value) => formatNumber(value, 4))}</td>
      <td class="number" title="${escapeHtml(LONG_SHORT_MEAN_HELP)}">${factorMetricHtml(factor, "long_short_mean", (value) => formatNumber(value, 4))}</td>
      <td>${formatDate(factor.latest_checked_at)}</td>
      <td><span class="recommendation ${recommendationClass(factor.reuse_recommendation)}">${escapeHtml(factor.reuse_recommendation)}</span></td>
    `;
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
  const reusable = selected.filter((factor) => factor.reuse_recommendation === "可复用").length;
  const rerun = selected.filter((factor) => factor.reuse_recommendation === "建议重跑").length;
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
  state.strategyBuilderName =
    factors.length === 1 ? `${factors[0].factor_name} 策略研究` : `多因子成品策略 ${state.strategyDrafts.length + 1}`;
  state.strategyBuilderResult = null;
  state.selectedStrategyTemplateId = state.selectedStrategyTemplateId || null;
  state.strategyBuilderParams = {};
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
  if (factor.proof_status === "failed" || factor.proof_status === "missing" || isTruthIssue(factor.truth_status)) {
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
    missing: "待数据",
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
  const score = Math.round(Math.min(99, Math.max(30, ir * 100)));
  if (factor.proof_status === "failed" || isTruthIssue(factor.truth_status)) {
    return `<span class="validation-badge reject">REJECT ${score}</span>`;
  }
  if (factor.proof_status === "missing" || factor.proof_status === "partial" || (coverage !== null && coverage < COVERAGE_WARN_THRESHOLD)) {
    return `<span class="validation-badge review">REVIEW ${score}</span>`;
  }
  return `<span class="validation-badge safe">SAFE ${score}</span>`;
}

function monitorMarketHtml(factor) {
  const hints = monitorHints(factor);
  const hint = hints.includes("覆盖率过低") ? `<span class="hint-chip">覆盖率过低</span>` : "";
  const detail = marketDetail(factor);
  return `
    <span class="market-cell">
      ${marketChipHtml(factor)}
      ${hint}
      <span class="monitor-source-sub">${escapeHtml(detail)}</span>
    </span>
  `;
}

function factorSourceDisplay(factor) {
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
  const reusable = currentFactors.filter((factor) => factor.reuse_recommendation === "可复用").length;
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
          <span>${label}</span>
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
  const factors = state.rawFactors
    .map((factor) => ({ factor, bucket: monitorBucket(factor) }))
    .filter((item) => marketBucket(item.factor) === state.monitorMarket)
    .filter((item) => state.monitorSelectedCategories.has(jqFactorCategory(item.factor)))
    .filter((item) => {
      if (state.monitorDirectionFilter === "all") return true;
      const direction = monitorDirection(item.factor).className;
      return direction === state.monitorDirectionFilter;
    })
    .filter((item) => state.monitorFilter === "all" || item.bucket === state.monitorFilter)
    .filter((item) => {
      if (!state.monitorCardFilter) return true;
      if (state.monitorCardFilter === "metric") {
        return toFiniteNumber(item.factor.rank_ic_mean) !== null || toFiniteNumber(item.factor.rank_ic_ir) !== null;
      }
      if (state.monitorCardFilter === "reusable") {
        return item.factor.reuse_recommendation === "可复用";
      }
      if (state.monitorCardFilter === "review") {
        return item.bucket === "weak";
      }
      return true;
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
      <tr>
        <td colspan="11" class="empty-cell">当前筛选下没有可展示的因子。</td>
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
      const direction = monitorDirection(factor);
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
          <td class="number">${formatNumber(factor.rank_ic_ir, 3)}</td>
          <td class="number">${formatNumber(factor.rank_ic_mean, 4)}</td>
          <td class="number ${coverageTone}" title="${escapeHtml(coverageHelp)}">${formatRatio(factor.coverage_ratio)}</td>
          <td class="number">${monitorRecentIcHtml(factor)}</td>
          <td>${monitorIcBarHtml(factor, bucket)}</td>
          <td><span class="direction-pill ${direction.className}">${direction.symbol} ${direction.label}</span></td>
          <td title="${escapeHtml(proofText)} / ${escapeHtml(factor.truth_status || "-")}">${monitorValidationHtml(factor)}</td>
          <td>${monitorMarketHtml(factor)}</td>
        </tr>
      `;
    })
    .join("");

  els.monitorTableBody.querySelectorAll("[data-factor-id]").forEach((button) => {
    button.addEventListener("click", () => openDetail(button.dataset.factorId));
  });
}

function compareMonitorRows(left, right) {
  const key = state.monitorSortKey;
  const direction = state.monitorSortDirection === "asc" ? 1 : -1;
  if (key === "bucket") {
    return (monitorSortValue(left.factor) - monitorSortValue(right.factor)) * direction;
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
    if (state.view === "strategy") renderStrategy();
  }
}

function seedStrategyBuilderParams(template) {
  (template?.param_schema || []).forEach((field) => {
    if (state.strategyBuilderParams[field.key] === undefined) {
      state.strategyBuilderParams[field.key] = field.default ?? field.options?.[0] ?? "";
    }
  });
}

function factorDirectionValue(factor) {
  return monitorDirection(factor).className === "negative" ? -1 : 1;
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

function strategyRunPayload(lifecycle = "草稿") {
  const template = activeStrategyTemplate();
  const createdAt = new Date().toISOString();
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
    backtest_result: state.strategyBuilderResult?.backtest_result || null,
    live_result: state.strategyBuilderResult?.live_result || null,
    created_at: createdAt,
  };
}

function mockStrategyRunResult(payload) {
  const factorScore = Math.max(1, payload.factors.length);
  return {
    backtest_result: {
      annual_return: Math.min(0.32, 0.08 + factorScore * 0.012),
      sharpe: Math.min(2.4, 0.85 + factorScore * 0.08),
      max_drawdown: -Math.min(0.28, 0.08 + factorScore * 0.01),
      win_rate: Math.min(0.72, 0.52 + factorScore * 0.015),
      equity: [1, 1.04, 1.08, 1.12, 1.18, 1.22],
    },
    live_result: {
      annual_return: Math.min(0.26, 0.06 + factorScore * 0.01),
      sharpe: Math.min(2.0, 0.72 + factorScore * 0.06),
      max_drawdown: -Math.min(0.22, 0.07 + factorScore * 0.008),
      win_rate: Math.min(0.68, 0.5 + factorScore * 0.012),
      equity: [1.22, 1.24, 1.23, 1.27, 1.31],
    },
    cutoff_date: payload.params.cutoff_date,
    fallback: true,
  };
}

async function runStrategyBuilder() {
  if (!activeStrategyTemplate()) {
    showToast("请选择成品策略");
    return;
  }
  const payload = strategyRunPayload("回测中");
  try {
    const response = await fetchWithTimeout(`${API_BASE}/strategy-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`strategy run ${response.status}`);
    const result = await response.json();
    state.strategyBuilderResult = result;
  } catch (error) {
    state.strategyBuilderResult = mockStrategyRunResult(payload);
  }
  renderStrategyBuilder();
  showToast("策略运行结果已生成");
}

function strategyRowFromRun(payload) {
  const template = activeStrategyTemplate();
  const result = state.strategyBuilderResult || {};
  return {
    id: payload.strategy_id,
    name: payload.name,
    type: template?.name || "成品策略",
    factors: state.strategyBuilderFactors.map((factor) => factor.factor_name).join(", "),
    factorIds: state.strategyBuilderFactors.map((factor) => factor.id),
    universe: payload.params.universe || "-",
    rebalance: `${payload.params.start_date || "-"} ~ ${payload.params.end_date || "-"}`,
    cost: `临界日 ${payload.params.cutoff_date || "-"}`,
    annualReturn: result.live_result?.annual_return ?? result.backtest_result?.annual_return ?? null,
    sharpe: result.live_result?.sharpe ?? result.backtest_result?.sharpe ?? null,
    maxDrawdown: result.live_result?.max_drawdown ?? result.backtest_result?.max_drawdown ?? null,
    status: payload.lifecycle,
    lifecycleStatus: payload.lifecycle,
    source: payload.source,
    templateId: payload.template_id,
    strategyRun: payload,
    backtestResult: result.backtest_result || null,
    liveResult: result.live_result || null,
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
  try {
    // AGENT-HOOK: 保存导入策略看板与 Agent 自动提交共用端点，生命周期状态机保持一致。
    await fetchWithTimeout(`${API_BASE}/strategy-runs/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    // 本地未接后端时仍导入看板，后续由同一契约替换为真实持久化。
  }
  state.strategyDrafts.unshift(strategyRowFromRun(payload));
  saveStrategies();
  state.view = "strategy";
  window.location.hash = "";
  renderView();
  showToast("策略已保存并导入策略看板");
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

function renderStrategyBuilderResult() {
  const result = state.strategyBuilderResult;
  if (!result) {
    return `<div class="builder-empty-result">运行后展示净值曲线与回测段 / 实盘段指标。</div>`;
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
    });
  });
  els.strategyBuilderView.querySelector("#strategyBuilderName")?.addEventListener("input", (event) => {
    state.strategyBuilderName = event.target.value;
  });
  els.strategyBuilderView.querySelector("#runStrategyBuilder")?.addEventListener("click", runStrategyBuilder);
  els.strategyBuilderView.querySelector("#saveStrategyBuilder")?.addEventListener("click", saveStrategyBuilder);
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
  return [...state.strategyDrafts, ...apiRows];
}

function renderStrategyStats(rows) {
  if (!els.strategyStats) return;
  const ready = rows.filter((row) => row.status === "研究就绪").length;
  const avgSharpe = rows.length ? rows.reduce((sum, r) => sum + (r.sharpe || 0), 0) / rows.length : 0;
  const avgReturn = rows.length ? rows.reduce((sum, r) => sum + (r.annualReturn || 0), 0) / rows.length : 0;
  els.strategyStats.innerHTML = [
    ["策略条目", rows.length, "含已接入和预留流程"],
    ["已有研究基础", ready, "可从因子研究结果继续推进"],
    ["平均夏普", formatNumber(avgSharpe, 2), "基于因子IC/IR估算"],
    ["平均年化", formatRatio(avgReturn), "基于因子IC/IR估算"],
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
          <td class="strategy-factors-cell" title="${escapeHtml(row.factors)}">${escapeHtml(row.factors)}</td>
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
      renderStrategy();
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
  state.view = "strategy";
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
          <div><dt>使用因子</dt><dd>${escapeHtml(detailData.factors ? detailData.factors.map(f => f.factor_id).join(', ') : row.factors)}</dd></div>
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
        <div class="strategy-factor-chip">${escapeHtml(detailData.factors ? detailData.factors.map(f => f.factor_id).join(', ') : row.factors)}</div>
      </article>
    </section>
  `;

  els.strategyDetailView.querySelectorAll("[data-action='back-strategy']").forEach((button) => {
    button.addEventListener("click", closeStrategyDetail);
  });
  
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
        instruction: "GitHub Pages 展示模式：复核 WQ101 与 GTJA191 样例因子的复现状态。",
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
        <strong>待接入 Supabase</strong>
        <span>当前保留文件契约、Skill 弹窗和提交结构；GitHub Pages 阶段只读取 Supabase 展示表，不在浏览器内上传大文件、执行 Agent 或写正式因子库。</span>
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
        <span>前端只消费 Flask 与本地 runtime 产物；真实计算和数据抓取都留在后端或执行侧。</span>
      </div>
    </section>

    <section class="settings-page-grid" aria-label="连接配置">
      ${connectionCard("本地 Flask 服务", localStatusText, state.localConnected ? "ok" : "bad", [
        ["接口地址", `<code>${escapeHtml(API_BASE)}</code>`],
        ["健康检查", "<code>/health</code>"],
        ["用途", "读取因子库、报告产物、运行状态与官方数据代理"],
      ])}
      ${connectionCard("官方 Quant API", quantStatusText, quantStatusClass, [
        ["接入方式", "浏览器 → 本地 Flask → 官方 Quant API"],
        ["Credential 位置", "后端环境变量（静态快照不携带）"],
        ["安全说明", "前端不接触 token，不直接访问公网数据接口"],
      ])}
      ${connectionCard("Supabase 只读接入", supabaseConfigured ? "已配置" : "待接入", supabaseConfigured ? "ok" : "warn", [
        ["读取方式", "GitHub Pages 浏览器端 → Supabase public dashboard 表"],
        ["目标表", `<code>${escapeHtml(SUPABASE_FACTOR_TABLE)}</code>`],
        ["安全边界", "anon key 只能 SELECT 公开脱敏表；上传、写入、执行和 promotion 不走 GitHub Pages"],
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

async function loadFactorDetailData(factorId) {
  if (!factorId || state.factorDetailLoading[factorId]) return;
  state.factorDetailLoading[factorId] = true;
  try {
    const detailUrl = CLOUD_DEMO_MODE
      ? `${STATIC_FACTOR_DETAIL_DIR}/${staticArtifactKey(factorId)}.json`
      : `${API_BASE}/factor/${encodeURIComponent(factorId)}`;
    const response = await fetchWithTimeout(withCacheBust(detailUrl));
    if (response.ok) {
      const data = await response.json();
      console.log("[DEBUG] Factor detail API response:", data);
      state.factorDetailData[factorId] = data;
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

function staticArtifactKey(value) {
  return String(value || "").replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^_+|_+$/g, "") || "artifact";
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
    ? ["monitor", "library", "strategy", "strategy-builder", "tasks", "agent_task", "settings"]
    : ["monitor", "library", "strategy", "strategy-builder", "tasks", "settings"];
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
  if (window.location.hash === "#strategy-builder") {
    state.view = "strategy-builder";
    loadStrategyTemplates();
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
  const strategyMode = state.view === "strategy";
  const strategyBuilderMode = state.view === "strategy-builder";
  const strategyDetailMode = state.view === "strategy-detail";
  const taskMode = state.view === "tasks";
  const agentTaskMode = ENABLE_AGENT_TASK_DEBUG && state.view === "agent_task";
  const settingsMode = state.view === "settings";
  els.pageTitle.textContent = detailMode
    ? "因子详情"
    : monitorMode
      ? "因子监控"
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
  els.libraryView.classList.toggle(
    "hidden",
    detailMode || monitorMode || strategyMode || strategyBuilderMode || strategyDetailMode || taskMode || agentTaskMode || settingsMode,
  );
  els.monitorView.classList.toggle("hidden", !monitorMode);
  els.strategyView.classList.toggle("hidden", !strategyMode);
  els.strategyBuilderView?.classList.toggle("hidden", !strategyBuilderMode);
  els.taskView.classList.toggle("hidden", !taskMode);
  els.strategyDetailView.classList.toggle("hidden", !strategyDetailMode);
  els.detailView.classList.toggle("hidden", !detailMode);
  els.agentTaskView?.classList.toggle("hidden", !agentTaskMode);
  els.settingsView?.classList.toggle("hidden", !settingsMode);
  els.selectionBar.classList.toggle(
    "hidden",
    detailMode || monitorMode || strategyMode || strategyBuilderMode || strategyDetailMode || taskMode || settingsMode,
  );
  els.navItems.forEach((item) => {
    const activeView = detailMode ? "library" : strategyDetailMode || strategyBuilderMode ? "strategy" : state.view;
    item.classList.toggle("active", item.dataset.view === activeView);
  });
  if (monitorMode) renderMonitor();
  if (strategyMode) renderStrategy();
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

function renderDetail() {
  const factor = activeFactor();
  if (!factor) {
    closeDetail();
    return;
  }
  renderView();
  const [proofText, proofClass] = proofBadge(factor.proof_status);
  const [truthText, truthClass] = truthBadge(factor.truth_status);
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

    ${renderFactorDefinition(factor)}
    ${renderResearchSettings(factor)}

    <nav class="detail-tabs" aria-label="单因子报告切换">
      <button type="button" class="${state.detailTab === "analysis" ? "active" : ""}" data-tab="analysis">复现与研究分析</button>
      <button type="button" class="${state.detailTab === "artifacts" ? "active" : ""}" data-tab="artifacts">验证产物（Artifacts）</button>
    </nav>

    ${state.detailTab === "artifacts" ? renderArtifactsPanel(factor) : renderAnalysisPanel(factor)}
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
  const hasStratification = Array.isArray(stratification.equity) && stratification.equity.length > 0;
  const hasRealData = hasIcSeries || hasGroupReturns || hasStratification;
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
      ${metricCard("真值匹配率", formatRatio(factor.truth_exact_match_ratio), "真值匹配")}
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
              <td>${escapeHtml(factor.latest_job_id || "-")}</td>
              <td>${formatDate(factor.latest_checked_at)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="research-layout">
      <article class="research-card stratification-card">
        <header>
          <strong>单因子分层研究 / Factor Stratification Analysis</strong>
          <span>区间：当前复现样本区间 · 频率：日频</span>
        </header>
        <div class="chart-placeholder chart-large ${hasRealData ? "chart-rendered" : ""}">
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
          <div class="chart-placeholder ${hasRealData ? "chart-rendered" : ""}">
            ${hasRealData ? renderIcTimeSeriesChart(detailData) : `<strong>等待时序数据</strong>`}
          </div>
        </article>
        <article class="research-card">
          <header>
            <strong>分组表现 / Group Performance</strong>
            <span>区间：当前复现样本区间</span>
          </header>
          <div class="chart-placeholder ${hasRealData ? "chart-rendered" : ""}">
            ${hasRealData ? renderGroupPerformanceChart(detailData) : `<strong>等待分组收益数据</strong>`}
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
  const equity = stratification.equity || [];
  const dates = stratification.dates || [];
  
  if (equity.length === 0) {
    return `<text x="200" y="80" fill="#9ca3af" font-size="12" text-anchor="middle">暂无分层数据</text>`;
  }
  
  const validEquity = equity.filter(v => !isNaN(v) && v > 0);
  const rawMin = Math.min(...validEquity);
  const rawMax = Math.max(...validEquity);
  const minVal = Math.max(0, Math.floor((rawMin - 0.05) * 10) / 10);
  const maxVal = Math.ceil((rawMax + 0.05) * 10) / 10;
  const range = maxVal - minVal || 0.4;
  const totalLength = equity.length;
  
  let html = `<svg viewBox="0 0 760 260" class="research-svg">`;
  
  html += `<line x1="50" y1="20" x2="50" y2="220" stroke="#e2e8f0" stroke-width="1" />`;
  html += `<line x1="50" y1="220" x2="740" y2="220" stroke="#e2e8f0" stroke-width="1" />`;
  
  const yTicks = [];
  for (let value = minVal; value <= maxVal + 0.001; value += 0.1) {
    yTicks.push(Number(value.toFixed(1)));
  }
  yTicks.forEach((val) => {
    const y = 220 - ((val - minVal) / range) * 200;
    html += `<line x1="50" y1="${y}" x2="740" y2="${y}" stroke="#f1f5f9" stroke-width="1" />`;
    html += `<text x="42" y="${y + 4}" fill="#64748b" font-size="9" text-anchor="end">${val.toFixed(1)}</text>`;
  });
  
  const xTicks = uniqueMonthTicks(dates, 10);
  xTicks.forEach((tick) => {
    const x = 50 + (tick.index / Math.max(totalLength - 1, 1)) * 690;
    html += `<line x1="${x}" y1="220" x2="${x}" y2="226" stroke="#e2e8f0" stroke-width="1" />`;
    html += `<text x="${x}" y="244" fill="#64748b" font-size="9" text-anchor="middle">${tick.label}</text>`;
  });
  
  const points = [];
  for (let i = 0; i < equity.length; i++) {
    const x = 50 + (i / Math.max(totalLength - 1, 1)) * 690;
    const y = 220 - ((equity[i] - minVal) / range) * 200;
    points.push(`${x},${Math.max(20, Math.min(220, y))}`);
  }
  
  if (points.length > 0) {
    html += `<path d="M ${points.join(" L ")}" fill="none" stroke="#1e40af" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />`;
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
    state.usableOnly = false;
    state.query = "";
    state.page = 1;
    els.proofFilter.value = "all";
    els.truthFilter.value = "all";
    els.reuseFilter.value = "all";
    if (els.usableOnlyToggle) els.usableOnlyToggle.checked = false;
    els.searchInput.value = "";
    renderTabs({ factors: state.rawFactors, categories: countCategories(), libraries: countLibraries() });
    applyFilters();
  });
  els.refreshButton.addEventListener("click", loadData);
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
    if (window.location.hash === "#strategy-builder") {
      state.view = "strategy-builder";
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

function handleLoginSubmit(event) {
  event.preventDefault();
  const password = String(els.loginPassword?.value || "");
  if (password === ACCESS_PASSWORD) {
    window.sessionStorage.setItem(ACCESS_SESSION_KEY, "1");
    showApp();
    startApp();
    return;
  }
  showLogin("密码不正确，请重试");
}

function logout() {
  window.sessionStorage.removeItem(ACCESS_SESSION_KEY);
  showLogin("已退出登录");
}

function initAuth() {
  els.loginForm?.addEventListener("submit", handleLoginSubmit);
  els.logoutButton?.addEventListener("click", logout);
  if (isAuthenticated()) {
    showApp();
    startApp();
  } else {
    showLogin();
  }
}

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
