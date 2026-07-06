const CLOUD_DEMO_MODE =
  window.location.hostname.endsWith("github.io") ||
  new URLSearchParams(window.location.search).has("demo");
const API_HOST = CLOUD_DEMO_MODE
  ? ""
  : window.location.protocol.startsWith("http") && window.location.port === "8012"
    ? window.location.origin
    : "http://127.0.0.1:8012";
const API_BASE = CLOUD_DEMO_MODE ? "" : `${API_HOST}/api/agents/factor-lab`;
const DEMO_LIBRARY_URL = "./data/demo-factor-library.json";
const PAGE_SIZE = 50;
const AUTO_REFRESH_INTERVAL_MS = 10000;
const REQUEST_TIMEOUT_MS = 1800;
const COVERAGE_WARN_THRESHOLD = 0.6;
const COVERAGE_DANGER_THRESHOLD = 0.3;
const LONG_SHORT_MEAN_HELP = "多空分组收益均值（日频，demo 数据）";
const QUANT_API_FACTOR_META = {
  roe_ttm: ["财务因子", "盈利能力"],
  roa_ttm: ["财务因子", "盈利能力"],
  net_margin: ["财务因子", "盈利能力"],
  debt_to_asset: ["财务因子", "偿债能力"],
  revenue_yoy: ["财务因子", "成长能力"],
  profit_yoy: ["财务因子", "成长能力"],
  eps_yoy: ["财务因子", "成长能力"],
  asset_turnover: ["财务因子", "营运能力"],
  log_price: ["价值因子", "价格水平"],
  ret_1m: ["量价因子", "收益"],
  ret_3m: ["量价因子", "收益"],
  ret_6m: ["量价因子", "收益"],
  ret_12m: ["量价因子", "收益"],
  momentum_12_1: ["量价因子", "动量"],
  reversal: ["量价因子", "反转"],
  avg_amount_1m: ["量价因子", "成交额"],
  log_amount_1m: ["量价因子", "成交额"],
  turnover_proxy: ["量价因子", "换手"],
  volume_ratio: ["量价因子", "成交量"],
  up_ratio_1m: ["量价因子", "上涨比例"],
  max_ret_1m: ["技术因子", "极值收益"],
  min_ret_1m: ["技术因子", "极值收益"],
  volatility_1m: ["技术因子", "波动率"],
  volatility_3m: ["技术因子", "波动率"],
  volatility_6m: ["技术因子", "波动率"],
  ma_signal: ["技术因子", "均线"],
  vol_convergence: ["技术因子", "量能收敛"],
  illiquidity: ["技术因子", "流动性"],
  high_low_1m: ["技术因子", "振幅"],
  rsi_14: ["技术因子", "RSI"],
  bb_position: ["技术因子", "布林带"],
  ret_3m_vol_adj: ["技术因子", "风险调整收益"],
  amplitude_1m: ["技术因子", "振幅"],
};

const AGENT_TASK_TEXT = {
  title: "AI 任务(调试入口)",
  subtitle:
    "输入研究要求后,后台 agent 默认使用 Quant API 真实数据判断并执行复现、挖掘或评估。进度在任务监控中查看。",
  boundaryTitle: "当前边界",
  boundary:
    "前端只提交自然语言要求,不上传文件、不选择 skill。数据默认从后端 Quant API 读取;agent 执行、流程判断与入库均在后端完成。",
  instructionLabel: "研究要求",
  instructionPlaceholder: "例如:使用 Quant API 真实数据复现 GTJA191 的 alpha010 并评估;或:挖掘一个低换手量价因子",
  quarantineHint: "默认数据源: Quant API。agent 产出将进入 quarantine(隔离区),通过校验后才进入正式因子库。",
  submit: "提交给 Agent",
  submitting: "提交中...",
  emptyWarning: "请输入研究要求",
  submittedToast: "任务已提交,已生成 Trae 交接文件",
  recentTitle: "最近提交",
  emptyRecent: "暂无提交记录。提交一个任务后会出现在这里。",
};

const state = {
  rawFactors: [],
  filteredFactors: [],
  selectedIds: new Set(),
  selectedAgentTaskIds: new Set(),
  category: "全部",
  library: "全部",
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
  monitorCardFilter: null,
  monitorSortKey: null,
  monitorSortDirection: "default",
  dragSelect: {
    active: false,
    targetChecked: true,
    touched: new Set(),
  },
  view: "library",
  activeFactorId: null,
  activeStrategyId: null,
  activeTaskId: null,
  detailTab: "analysis",
  pendingFiles: [],
  agentTasks: [],
  agentTasksLoaded: false,
  agentInstruction: "",
  agentTaskSubmitting: false,
};

const els = {
  pageTitle: document.querySelector("#pageTitle"),
  localStatus: document.querySelector("#localStatus"),
  cloudStatus: document.querySelector("#cloudStatus"),
  quantStatus: document.querySelector("#quantStatus"),
  libraryView: document.querySelector("#libraryView"),
  monitorView: document.querySelector("#monitorView"),
  strategyView: document.querySelector("#strategyView"),
  taskView: document.querySelector("#taskView"),
  strategyDetailView: document.querySelector("#strategyDetailView"),
  detailView: document.querySelector("#detailView"),
  agentTaskView: document.querySelector("#agentTaskView"),
  settingsView: document.querySelector("#settingsView"),
  navItems: document.querySelectorAll(".nav-item[data-view]"),
  categoryTabs: document.querySelector("#categoryTabs"),
  libraryTabs: document.querySelector("#libraryTabs"),
  libraryRow: document.querySelector("#libraryTabs")?.closest(".sub-filter-row"),
  proofFilter: document.querySelector("#proofFilter"),
  truthFilter: document.querySelector("#truthFilter"),
  reuseFilter: document.querySelector("#reuseFilter"),
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
  strategyStats: document.querySelector("#strategyStats"),
  strategyTableBody: document.querySelector("#strategyTableBody"),
  taskStats: document.querySelector("#taskStats"),
  taskTableBody: document.querySelector("#taskTableBody"),
  taskStagePanel: document.querySelector("#taskStagePanel"),
  refreshButton: document.querySelector("#refreshButton"),
  collapseButton: document.querySelector("#collapseButton"),
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

function renderTabs(payload) {
  const categories = payload.categories || {};
  const libraries = payload.libraries || {};
  if (state.category !== "全部" && (categories[state.category] ?? 0) === 0) {
    state.category = "全部";
    state.library = "全部";
  }
  if (state.library !== "全部" && (libraries[state.library] ?? 0) === 0) {
    state.library = "全部";
  }
  els.categoryTabs.replaceChildren();
  ["全部", "量价因子", "技术因子", "财务因子", "规模因子", "价值因子", "自定义因子"].forEach((label) => {
    const count = categories[label] ?? 0;
    const disabled = label !== "全部" && count === 0;
    els.categoryTabs.appendChild(
      tabButton(label, count, state.category === label, () => {
        state.category = label;
        state.library = "全部";
        state.page = 1;
        renderTabs({ categories: countCategories(), libraries: countLibraries() });
        applyFilters();
      }, disabled),
    );
  });

  const showLibraryTabs = state.category === "量价因子";
  els.libraryRow?.classList.toggle("hidden", !showLibraryTabs);
  els.libraryTabs.replaceChildren();
  if (!showLibraryTabs) {
    return;
  }

  ["全部", "WQ101", "GTJA191", "QuantAPI", "TA-Lib", "User Custom"].forEach((label) => {
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

function updateConnectionStatus(ok, payload) {
  state.localConnected = ok;
  els.localStatus.className = ok ? "status-pill status-ok" : "status-pill status-bad";
  if (CLOUD_DEMO_MODE) {
    els.localStatus.textContent = "GitHub Pages：演示模式";
    els.localStatus.title = "当前使用静态演示数据，未连接本地 Flask 服务";
  } else {
    els.localStatus.textContent = ok ? "本地 Flask：已连接" : "本地 Flask：未连接";
    els.localStatus.title = ok ? "已通过 /health 接口确认" : "未能访问 /health 接口，请确认本地 Flask 服务已启动";
  }
  const cloudLabel = payload?.cloud_registry?.label || "未同步";
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
    : "尚未配置 FACTOR_LAB_QUANT_API_TOKEN 或 QUANT_API_TOKEN，前端不会直接持有 token";
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

async function loadOfficialQuantFactors(quantStatus) {
  if (CLOUD_DEMO_MODE) {
    return [];
  }
  if (!quantStatus?.token_configured) {
    return [];
  }
  try {
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/quant-api/factor-monthly/factors`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const factors = Array.isArray(payload?.factors) ? payload.factors : [];
    return factors.map(officialQuantFactorRow);
  } catch (error) {
    return [];
  }
}

function officialQuantFactorRow(factorName) {
  const [category, subcategory] = QUANT_API_FACTOR_META[factorName] || ["量价因子", "官方因子"];
  return {
    id: `QuantAPI:${factorName}`,
    factor_name: factorName,
    raw_factor_name: factorName,
    library: "QuantAPI",
    raw_library: "QuantAPI",
    category,
    category_inferred: false,
    subcategory,
    required_fields: [],
    metadata: {
      official_source: "Quant API factor_monthly",
      not_reproduced_locally: true,
    },
    formula: "",
    description: "官方 Quant API 月频因子，当前仅作为数据源展示，尚未进入本地复现流程。",
    source: "quant_api",
    source_id: "factor_monthly/factors",
    implementation_status: "official_data_only",
    proof_status: "missing",
    truth_status: "not_applicable",
    overall_status: "missing",
    coverage_ratio: null,
    rank_ic_mean: null,
    rank_ic_ir: null,
    long_short_mean: null,
    truth_exact_match_ratio: null,
    truth_max_abs_error: null,
    latest_job_id: null,
    latest_checked_at: null,
    data_source: "Quant API",
    dataset: {},
    reuse_recommendation: "未复现",
  };
}

async function loadData() {
  if (state.isLoading) {
    return;
  }
  state.isLoading = true;
  updateRefreshButton(true);
  try {
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
      syncDetailFromHash();
      if (state.view === "detail") renderDetail();
      if (state.view === "monitor") renderMonitor();
      if (state.view === "strategy") renderStrategy();
      if (state.view === "strategy-detail") renderStrategyDetail();
      if (state.view === "tasks") renderTasks();
      return;
    }
    const healthy = await checkLocalHealth();
    if (!healthy) throw new Error("Local Flask service is offline");
    const quantStatus = await checkQuantApiStatus();
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/factor-library`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const officialFactors = await loadOfficialQuantFactors(quantStatus);
    const normalizedPayload = normalizePayload(withOfficialQuantFactors(payload, officialFactors));
    state.rawFactors = normalizedPayload.factors || [];
    updateConnectionStatus(true, payload);
    els.errorPanel.classList.add("hidden");
    renderTabs(normalizedPayload);
    applyFilters();
    syncDetailFromHash();
    if (state.view === "detail") renderDetail();
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

function withOfficialQuantFactors(payload, officialFactors) {
  if (!officialFactors.length) {
    return payload;
  }
  const existingIds = new Set((payload.factors || []).map((factor) => factor.id));
  const mergedFactors = [
    ...(payload.factors || []),
    ...officialFactors.filter((factor) => !existingIds.has(factor.id)),
  ];
  return {
    ...payload,
    factors: mergedFactors,
    categories: countBy(mergedFactors, "category", { 全部: mergedFactors.length }),
    libraries: countBy(mergedFactors, "library"),
  };
}

function normalizePayload(payload) {
  const factors = payload.factors || [];
  const hasAlpha101 = factors.some((factor) => factor.library === "Alpha101");
  if (!hasAlpha101) {
    return payload;
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
    categories: countBy(normalizedFactors, "category", { 全部: normalizedFactors.length }),
    libraries: countBy(normalizedFactors, "library"),
  };
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

function applyFilters() {
  const query = state.query.trim().toLowerCase();
  state.filteredFactors = state.rawFactors
    .filter((factor) => state.category === "全部" || factor.category === state.category)
    .filter((factor) => state.library === "全部" || factor.library === state.library)
    .filter((factor) => state.proof === "all" || factor.proof_status === state.proof)
    .filter((factor) => state.truth === "all" || factor.truth_status === state.truth)
    .filter((factor) => state.reuse === "all" || factor.reuse_recommendation === state.reuse)
    .filter((factor) => {
      if (!query) return true;
      return [factor.factor_name, factor.raw_factor_name, factor.library, factor.subcategory]
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
    const displayName = compactName(factor.factor_name);
    const coverageTone = coverageClass(factor.coverage_ratio);
    const coverageHelp = coverageTitle(factor.coverage_ratio);
    const row = document.createElement("tr");
    row.className = [
      state.selectedIds.has(factor.id) ? "selected" : "",
      openable ? "openable" : "not-openable",
    ]
      .filter(Boolean)
      .join(" ");
    row.innerHTML = `
      <td>
        <input type="checkbox" ${state.selectedIds.has(factor.id) ? "checked" : ""} aria-label="选择 ${escapeHtml(factor.factor_name)}" />
      </td>
      <td>
        <button class="factor-link" type="button" data-factor-id="${escapeHtml(factor.id)}" ${openable ? "" : "disabled"} title="${escapeHtml(factor.factor_name)} · ${openable ? "查看单因子详情" : "未复现，暂无详情报告"}">
          ${escapeHtml(displayName)}
        </button>
      </td>
      <td>${escapeHtml(factor.library)}</td>
      <td>${escapeHtml(factor.subcategory || "-")}</td>
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
  if (state.view === "agent_task") {
    renderAgentTaskSelectionSummary();
    return;
  }
  const selected = state.rawFactors.filter((factor) => state.selectedIds.has(factor.id));
  const reusable = selected.filter((factor) => factor.reuse_recommendation === "可复用").length;
  const rerun = selected.filter((factor) => factor.reuse_recommendation === "建议重跑").length;
  els.selectedCount.textContent = `已选择 ${selected.length} 个因子`;
  els.selectedReusable.textContent = `可复用 ${reusable} 个`;
  els.selectedRerun.textContent = `建议重跑 ${rerun} 个`;
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

function monitorBucket(factor) {
  const ic = toFiniteNumber(factor.rank_ic_mean);
  const ir = toFiniteNumber(factor.rank_ic_ir);
  if (ic === null && ir === null) return "missing";
  if (factor.proof_status === "failed" || factor.proof_status === "missing" || isTruthIssue(factor.truth_status)) {
    return "weak";
  }
  const absIc = Math.abs(ic ?? 0);
  const absIr = Math.abs(ir ?? 0);
  if (absIr >= 0.3 || absIc >= 0.05) return "strong";
  if (absIr >= 0.1 || absIc >= 0.02) return "medium";
  return "weak";
}

function monitorBucketLabel(bucket) {
  return {
    strong: "强有效",
    medium: "中等",
    weak: "弱或失效",
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

function renderMonitorStats() {
  const total = state.rawFactors.length;
  const withMetric = state.rawFactors.filter(
    (factor) => toFiniteNumber(factor.rank_ic_mean) !== null || toFiniteNumber(factor.rank_ic_ir) !== null,
  ).length;
  const reusable = state.rawFactors.filter((factor) => factor.reuse_recommendation === "可复用").length;
  const review = state.rawFactors.filter((factor) => monitorBucket(factor) === "weak").length;

  const cards = [
    ["all", "总因子数", total, "来自当前 specs 与 runtime 产物"],
    ["metric", "有 IC/IR", withMetric, "已有可读研究指标"],
    ["reusable", "可复用", reusable, "按当前适配层建议"],
    ["review", "需关注", review, "复现失败、真值异常或弱指标"],
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
  renderMonitorStats();
  renderMonitorFilters();
  const factors = state.rawFactors
    .map((factor) => ({ factor, bucket: monitorBucket(factor) }))
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
        <td colspan="10" class="empty-cell">当前筛选下没有可展示的因子。</td>
      </tr>
    `;
    return;
  }

  els.monitorTableBody.innerHTML = factors
    .map(({ factor, bucket }) => {
      const [proofText, proofClass] = proofBadge(factor.proof_status);
      const openable = canOpenFactor(factor);
      const name = compactName(factor.factor_name);
      const hints = monitorHints(factor);
      const coverageTone = coverageClass(factor.coverage_ratio);
      const coverageHelp = coverageTitle(factor.coverage_ratio);
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
            <strong>${escapeHtml(factor.library || "-")}</strong>
            <span class="monitor-source-sub">${escapeHtml(factor.subcategory || factor.category || "-")}</span>
          </td>
          <td class="number">${formatNumber(factor.rank_ic_ir, 3)}</td>
          <td class="number">${formatNumber(factor.rank_ic_mean, 4)}</td>
          <td class="number ${coverageTone}" title="${escapeHtml(coverageHelp)}">${formatRatio(factor.coverage_ratio)}</td>
          <td class="number">${formatNumber(factor.long_short_mean, 4)}</td>
          <td><span class="badge ${proofClass}">${proofText}</span></td>
          <td>${truthBadgeHtml(factor)}</td>
          <td>${hints.length ? hints.map((hint) => `<span class="hint-chip">${escapeHtml(hint)}</span>`).join("") : mutedDash()}</td>
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

function strategyRows() {
  const reusable = state.rawFactors.filter((factor) => factor.reuse_recommendation === "可复用");
  const first = reusable[0] || state.rawFactors[0];
  return [
    {
      id: first ? `strategy_single_factor_${sanitizeId(first.id || first.factor_name)}` : "strategy_single_factor",
      name: first ? `${first.factor_name} 单因子分层策略` : "单因子分层策略",
      type: "单因子",
      factors: first ? `${first.library}:${first.factor_name}` : "待选择",
      universe: "当前样本股票池",
      rebalance: "待策略层接入",
      cost: "待策略层接入",
      annualReturn: null,
      sharpe: null,
      maxDrawdown: null,
      status: first ? "研究就绪" : "待接入",
      updatedAt: first?.latest_checked_at || "-",
    },
    {
      id: "strategy_multi_factor_candidate",
      name: "多因子合成候选",
      type: "多因子",
      factors: "待选择",
      universe: "待接入",
      rebalance: "待接入",
      cost: "待接入",
      annualReturn: null,
      sharpe: null,
      maxDrawdown: null,
      status: "待接入",
      updatedAt: "-",
    },
    {
      id: "strategy_agent_pipeline",
      name: "AI Agent 自动生成策略",
      type: "Agent",
      factors: "待 Agent 提交",
      universe: "待接入",
      rebalance: "待接入",
      cost: "待接入",
      annualReturn: null,
      sharpe: null,
      maxDrawdown: null,
      status: "待接入",
      updatedAt: "-",
    },
  ];
}

function renderStrategyStats(rows) {
  if (!els.strategyStats) return;
  const ready = rows.filter((row) => row.status === "研究就绪").length;
  els.strategyStats.innerHTML = [
    ["策略条目", rows.length, "含已接入和预留流程"],
    ["已有研究基础", ready, "可从因子研究结果继续推进"],
    ["正式回测", 0, "等待策略层与真实交易参数接入"],
    ["数据状态", "占位", "当前不触发计算"],
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
        <tr>
          <td>
            <button type="button" class="strategy-link" data-strategy-id="${escapeHtml(row.id)}">${escapeHtml(row.name)}</button>
          </td>
          <td>${escapeHtml(row.type)}</td>
          <td>${escapeHtml(row.factors)}</td>
          <td>${escapeHtml(row.universe)}</td>
          <td>
            <strong>${escapeHtml(row.rebalance)}</strong>
            <span class="monitor-source-sub">${escapeHtml(row.cost)}</span>
          </td>
          <td class="number">${formatRatio(row.annualReturn)}</td>
          <td class="number">${formatNumber(row.sharpe, 2)}</td>
          <td class="number">${formatRatio(row.maxDrawdown)}</td>
          <td><span class="badge ${row.status === "研究就绪" ? "badge-green" : "badge-gray"}">${escapeHtml(row.status)}</span></td>
          <td>${formatDate(row.updatedAt)}</td>
        </tr>
      `,
    )
    .join("");

  els.strategyTableBody.querySelectorAll("[data-strategy-id]").forEach((button) => {
    button.addEventListener("click", () => openStrategyDetail(button.dataset.strategyId));
  });
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

function openStrategyDetail(strategyId) {
  const row = strategyRows().find((item) => item.id === strategyId);
  if (!row) return;
  state.view = "strategy-detail";
  state.activeStrategyId = strategyId;
  renderStrategyDetail();
}

function closeStrategyDetail() {
  state.view = "strategy";
  state.activeStrategyId = null;
  renderView();
}

function renderStrategyDetail() {
  const row = activeStrategy();
  if (!row) {
    closeStrategyDetail();
    return;
  }
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
          <div><dt>类型</dt><dd>${escapeHtml(row.type)}</dd></div>
          <div><dt>使用因子</dt><dd>${escapeHtml(row.factors)}</dd></div>
          <div><dt>股票池</dt><dd>${escapeHtml(row.universe)}</dd></div>
          <div><dt>更新时间</dt><dd>${formatDate(row.updatedAt)}</dd></div>
        </dl>
      </div>
      <div class="detail-actions">
        <button type="button" class="secondary-action" data-action="back-strategy">返回策略看板</button>
        <button type="button" class="primary-action compact" disabled>导出策略报告（待接入）</button>
      </div>
    </section>

    <section class="metric-grid strategy-metrics">
      <article class="metric-card"><span>年化收益</span><strong>${formatRatio(row.annualReturn)}</strong><small>待策略层产出</small></article>
      <article class="metric-card"><span>夏普</span><strong>${formatNumber(row.sharpe, 2)}</strong><small>待策略层产出</small></article>
      <article class="metric-card"><span>最大回撤</span><strong>${formatRatio(row.maxDrawdown)}</strong><small>待策略层产出</small></article>
      <article class="metric-card"><span>换手率</span><strong>-</strong><small>待交易成本模型接入</small></article>
    </section>

    <section class="research-settings">
      <div>
        <h3>策略研究与回测参数</h3>
        <p>这些参数作为未来策略回测请求输入。当前只展示预留口径，不会在前端触发计算。</p>
      </div>
      <div class="research-grid">
        <label><span>研究区间</span><select><option>当前复现样本区间</option></select></label>
        <label><span>股票池</span><select><option>${escapeHtml(row.universe)}</option></select></label>
        <label><span>组合构建</span><select><option>${escapeHtml(row.type)}研究</option></select></label>
        <label><span>调仓周期</span><select disabled><option>待策略层接入</option></select></label>
        <label><span>手续费及滑点</span><select disabled><option>待策略层接入</option></select></label>
      </div>
    </section>

    <section class="strategy-detail-grid">
      <article class="chart-card large-chart">
        <header><strong>策略收益曲线 / Equity Curve</strong><span>待接入</span></header>
        <div class="chart-placeholder">等待策略回测数据</div>
      </article>
      <article class="chart-card">
        <header><strong>风险指标</strong><span>待接入</span></header>
        <div class="chart-placeholder">等待 Sharpe / Max DD / Volatility</div>
      </article>
      <article class="chart-card">
        <header><strong>使用因子</strong><span>1 个</span></header>
        <div class="strategy-factor-chip">${escapeHtml(row.factors)}</div>
      </article>
    </section>
  `;

  els.strategyDetailView.querySelectorAll("[data-action='back-strategy']").forEach((button) => {
    button.addEventListener("click", closeStrategyDetail);
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
        { gate: "G1", name: "复现产物检查", status: "passed", note: "proof / evaluation / factor_frame 已生成" },
        { gate: "G2", name: "研究评估检查", status: "warning", note: "部分因子需要人工复核" },
        { gate: "G3", name: "策略回测检查", status: "pending", note: "策略层尚未接入" },
        { gate: "G4", name: "人工审核", status: "pending", note: "等待研究员确认" },
      ],
      artifacts: "proof_report.json / evaluation.json / factor_frame.csv",
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
      artifacts: "runtime/factor_lab/reports",
    },
    {
      id: "ai_factor_mining",
      name: "AI Agent 因子挖掘候选流程",
      type: "挖掘",
      currentGate: "G0",
      progress: 0,
      status: "未实现",
      stages: [
        { gate: "G0", name: "候选因子登记", status: "pending", note: "未来接入 trial ledger" },
        { gate: "G1", name: "安全与泄漏检查", status: "pending", note: "预留子 Gate" },
        { gate: "G2", name: "复现与研究评估", status: "pending", note: "预留子 Gate" },
        { gate: "G3", name: "策略候选检查", status: "pending", note: "预留子 Gate" },
        { gate: "G4", name: "人工审核", status: "pending", note: "预留子 Gate" },
      ],
      artifacts: "待 Agent 提交",
    },
  ];
  return [...agentTaskRows(), ...builtInRows];
}

function agentTaskStatusMeta(task) {
  const status = String(task.status || "submitted");
  const map = {
    queued_for_trae: { label: "等待 Agent", progress: 10, stageStatus: "running", appStatus: "运行中" },
    submitted: { label: "已提交", progress: 8, stageStatus: "running", appStatus: "运行中" },
    running: { label: "运行中", progress: 45, stageStatus: "running", appStatus: "运行中" },
    failed: { label: "需关注", progress: 35, stageStatus: "warning", appStatus: "需关注" },
    completed: { label: "已完成", progress: 100, stageStatus: "passed", appStatus: "已完成" },
  };
  return map[status] || { label: status, progress: 10, stageStatus: "running", appStatus: "运行中" };
}

function agentTaskRows() {
  return state.agentTasks.map((task) => {
    const meta = agentTaskStatusMeta(task);
    const summary = agentTaskSummary(task);
    const taskId = task.task_id || task.id || "agent-task";
    const artifacts = task.artifacts_dir || task.status_path || "runtime/factor_lab/agent_tasks";
    const progress = Number(task.progress ?? meta.progress);
    return {
      id: taskId,
      name: summary === "-" ? taskId : summary,
      type: "Agent",
      currentGate: task.current_gate || "G0",
      progress: Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : meta.progress,
      status: meta.appStatus,
      sourceStatus: task.status || "submitted",
      stages: [
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
      ],
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
  state.pendingFiles.splice(index, 1);
  renderAgentTask();
}

async function loadAgentTasks() {
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

async function submitAgentTask() {
  const instruction = state.agentInstruction.trim();
  if (!instruction) {
    showToast(AGENT_TASK_TEXT.emptyWarning);
    return;
  }

  const payload = {
    schema_version: "agent_task_request_v1",
    instruction,
    files: [],
    namespace: "quarantine",
    data_source: "quant_api",
    requires_quant_api: true,
    requested_at: new Date().toISOString(),
  };

  state.agentTaskSubmitting = true;
  renderAgentTask();
  try {
    const result = await submitTaskRequest(payload);
    state.agentTasks.unshift({ ...payload, ...result });
    state.pendingFiles = [];
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
  if (!els.agentTaskView) return;
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
      <label class="agent-task-field">
        <span>${AGENT_TASK_TEXT.instructionLabel}</span>
        <textarea id="agentInstructionInput" rows="5" placeholder="${AGENT_TASK_TEXT.instructionPlaceholder}">${escapeHtml(state.agentInstruction)}</textarea>
      </label>

      <div class="agent-task-foot">
        <span>${AGENT_TASK_TEXT.quarantineHint}</span>
      </div>

      <div class="agent-task-foot">
        <span>\u4f4e\u624b\u52a8\u6a21\u5f0f: \u4e0d\u62d6\u6587\u4ef6\u3001\u4e0d\u9009\u62e9\u6d41\u7a0b,\u7531\u540e\u7aef agent \u57fa\u4e8e Quant API \u81ea\u52a8\u5224\u65ad\u3002</span>
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

  const instructionInput = els.agentTaskView.querySelector("#agentInstructionInput");
  const submitButton = els.agentTaskView.querySelector("#agentSubmitButton");

  instructionInput?.addEventListener("input", (event) => {
    state.agentInstruction = event.target.value;
  });
  submitButton?.addEventListener("click", submitAgentTask);
  els.agentTaskView.querySelectorAll("[data-agent-task-row]").forEach((row) => {
    row.addEventListener("dblclick", (event) => {
      if (event.target.closest("button") || event.target.closest("input")) return;
      openAgentTaskFolder(row.dataset.agentTaskRow);
    });
  });
  els.agentTaskView.querySelectorAll("[data-agent-task-progress]").forEach((button) => {
    button.addEventListener("click", () => openAgentTaskProgress(button.dataset.agentTaskProgress));
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
        <p>这里集中展示本地服务、官方 Quant API、AI Agent 接入和前端显示偏好。当前页面只读展示配置状态，不保存 token，也不启动任何 agent。</p>
      </div>
      <div class="settings-page-note">
        <strong>当前边界</strong>
        <span>前端只消费 Flask 与本地 runtime 产物；真实计算、数据抓取和 Agent 编排都留在后端或执行侧。</span>
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
        ["Token 位置", "<code>FACTOR_LAB_QUANT_API_TOKEN</code> 或 <code>QUANT_API_TOKEN</code>"],
        ["安全说明", "前端不接触 token，不直接访问公网数据接口"],
      ])}
      ${connectionCard("云端信息库", "未同步", "warn", [
        ["当前状态", "预留同步入口，后续用于团队共享已审核因子与报告"],
        ["同步对象", "因子元信息、审核状态、报告摘要、可追溯 artifact"],
        ["当前策略", "本地优先，云端只读展示待接入"],
      ])}
      ${connectionCard("AI Agent 接入", "待接入", "warn", [
        ["外部 Agent", "Trae / Claude Code / Codex 等工具预留统一提交入口"],
        ["内部 Agent", "Hermes / Factor Mining Agent / Strategy Agent 预留能力位"],
        ["当前边界", "此页只展示接口位置，不触发自动挖掘、复现或回测"],
      ])}
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
        <span><code>agent_task_request_v1</code>：AI 任务发起请求（要求文本 + 文件元信息，不含 skill；流程由后端 agent 判断）。当前为占位，后端接入后生效。</span>
        <span><code>strategy_monitor_view_v1</code>：策略看板与策略详情预留</span>
        <span><code>gate_monitor_view_v1</code>：任务监控与 Gate 可视化预留</span>
      </div>
    </section>
  `;
}

function activeFactor() {
  return state.rawFactors.find((factor) => factor.id === state.activeFactorId);
}

function openDetail(factorId) {
  const factor = state.rawFactors.find((item) => item.id === factorId);
  if (!canOpenFactor(factor)) return;
  state.view = "detail";
  state.activeFactorId = factorId;
  state.detailTab = "analysis";
  window.location.hash = `factor=${encodeURIComponent(factorId)}`;
  renderDetail();
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
  state.view = ["monitor", "strategy", "tasks", "agent_task", "settings"].includes(view) ? view : "library";
  state.activeFactorId = null;
  state.activeStrategyId = null;
  state.activeTaskId = null;
  state.detailTab = "analysis";
  if (window.location.hash) {
    history.pushState("", document.title, window.location.pathname + window.location.search);
  }
  renderView();
}

function syncDetailFromHash() {
  const match = window.location.hash.match(/^#factor=(.+)$/);
  if (!match || state.view === "detail") return;
  const factorId = decodeURIComponent(match[1]);
  const factor = state.rawFactors.find((item) => item.id === factorId);
  if (canOpenFactor(factor)) {
    state.view = "detail";
    state.activeFactorId = factorId;
  }
}

function renderView() {
  const detailMode = state.view === "detail";
  const monitorMode = state.view === "monitor";
  const strategyMode = state.view === "strategy";
  const strategyDetailMode = state.view === "strategy-detail";
  const taskMode = state.view === "tasks";
  const agentTaskMode = state.view === "agent_task";
  const settingsMode = state.view === "settings";
  els.pageTitle.textContent = detailMode
    ? "因子详情"
    : monitorMode
      ? "因子监控"
      : strategyMode
        ? "策略看板"
        : strategyDetailMode
          ? "策略详情"
          : taskMode
            ? "任务监控"
            : agentTaskMode
              ? "AI 任务(调试)"
              : settingsMode
                ? "设置"
                : "因子库";
  els.libraryView.classList.toggle(
    "hidden",
    detailMode || monitorMode || strategyMode || strategyDetailMode || taskMode || agentTaskMode || settingsMode,
  );
  els.monitorView.classList.toggle("hidden", !monitorMode);
  els.strategyView.classList.toggle("hidden", !strategyMode);
  els.taskView.classList.toggle("hidden", !taskMode);
  els.strategyDetailView.classList.toggle("hidden", !strategyDetailMode);
  els.detailView.classList.toggle("hidden", !detailMode);
  els.agentTaskView?.classList.toggle("hidden", !agentTaskMode);
  els.settingsView?.classList.toggle("hidden", !settingsMode);
  els.selectionBar.classList.toggle(
    "hidden",
    detailMode || monitorMode || strategyMode || strategyDetailMode || taskMode || settingsMode,
  );
  els.navItems.forEach((item) => {
    const activeView = detailMode ? "library" : strategyDetailMode ? "strategy" : state.view;
    item.classList.toggle("active", item.dataset.view === activeView);
  });
  if (monitorMode) renderMonitor();
  if (strategyMode) renderStrategy();
  if (taskMode) {
    renderTasks();
    loadAgentTasks();
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
          <div><dt>分类</dt><dd>${escapeHtml(factor.category || "-")}</dd></div>
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
        <div class="chart-placeholder chart-large">
          <div class="placeholder-mark">◇</div>
          <strong>待接入真实数据 API</strong>
          <span>当前仅作为研究级分层回测占位，不代表可交易策略收益。</span>
        </div>
      </article>
      <div class="side-charts">
        <article class="research-card">
          <header>
            <strong>IC 时序 / IC Time Series</strong>
            <span>区间：当前复现样本区间</span>
          </header>
          <div class="chart-placeholder">
            <strong>等待时序数据</strong>
          </div>
        </article>
        <article class="research-card">
          <header>
            <strong>分组表现 / Group Performance</strong>
            <span>区间：当前复现样本区间</span>
          </header>
          <div class="chart-placeholder">
            <strong>等待分组收益数据</strong>
          </div>
        </article>
      </div>
    </section>

    <section class="info-strip">
      本页面展示的是因子复现产物与内部一致性状态，不代表因子具备投资有效性。正式策略收益需要在策略层结合真实行情、交易成本、滑点、调仓规则和风控约束后验证。
    </section>
  `;
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
    ["factor_frame.csv", "因子值数据表", "文件已生成", "badge-green", "数据已生成", "badge-gray", "factor_frame"],
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
    state.library = "全部";
    state.proof = "all";
    state.truth = "all";
    state.reuse = "all";
    state.query = "";
    state.page = 1;
    els.proofFilter.value = "all";
    els.truthFilter.value = "all";
    els.reuseFilter.value = "all";
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
  });
  document.addEventListener("pointerup", endDragSelection);
  document.addEventListener("pointercancel", endDragSelection);
}

function countCategories() {
  const counts = { 全部: state.rawFactors.length };
  state.rawFactors.forEach((factor) => {
    counts[factor.category] = (counts[factor.category] || 0) + 1;
  });
  return counts;
}

function countLibraries() {
  const counts = {};
  state.rawFactors.forEach((factor) => {
    counts[factor.library] = (counts[factor.library] || 0) + 1;
  });
  return counts;
}

bindEvents();
loadData();
startAutoRefresh();
