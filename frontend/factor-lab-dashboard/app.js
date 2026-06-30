const API_HOST =
  window.location.protocol.startsWith("http") && window.location.port === "8012"
    ? window.location.origin
    : "http://127.0.0.1:8012";
const API_BASE = `${API_HOST}/api/agents/factor-lab`;
const PAGE_SIZE = 10;
const AUTO_REFRESH_INTERVAL_MS = 10000;
const REQUEST_TIMEOUT_MS = 1800;

const state = {
  rawFactors: [],
  filteredFactors: [],
  selectedIds: new Set(),
  category: "全部",
  library: "全部",
  proof: "all",
  truth: "all",
  reuse: "all",
  query: "",
  page: 1,
  sortKey: null,
  sortDirection: "default",
  localConnected: false,
  isLoading: false,
  autoRefreshTimer: null,
  monitorFilter: "all",
  dragSelect: {
    active: false,
    targetChecked: true,
    touched: new Set(),
  },
  view: "library",
  activeFactorId: null,
  detailTab: "analysis",
};

const els = {
  pageTitle: document.querySelector("#pageTitle"),
  localStatus: document.querySelector("#localStatus"),
  cloudStatus: document.querySelector("#cloudStatus"),
  libraryView: document.querySelector("#libraryView"),
  monitorView: document.querySelector("#monitorView"),
  detailView: document.querySelector("#detailView"),
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
  selectionBar: document.querySelector("#selectionBar"),
  errorPanel: document.querySelector("#errorPanel"),
  monitorStats: document.querySelector("#monitorStats"),
  monitorTableBody: document.querySelector("#monitorTableBody"),
  monitorFilters: document.querySelectorAll("[data-monitor-filter]"),
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

function artifactUrl(factor, kind) {
  if (!factor?.latest_job_id) return "";
  const base = `${API_BASE}/artifacts/${encodeURIComponent(factor.latest_job_id)}/${kind}`;
  if (kind === "proof") {
    return `${base}?factor=${encodeURIComponent(factor.raw_factor_name || factor.factor_name)}`;
  }
  return base;
}

function tabButton(label, count, active, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = active ? "tab active" : "tab";
  button.textContent = count === undefined ? label : `${label}${label === "全部" ? "" : ` (${count})`}`;
  button.addEventListener("click", onClick);
  return button;
}

function renderTabs(payload) {
  const categories = payload.categories || {};
  const libraries = payload.libraries || {};
  els.categoryTabs.replaceChildren();
  ["全部", "量价因子", "技术因子", "财务因子", "规模因子", "价值因子", "自定义因子"].forEach((label) => {
    els.categoryTabs.appendChild(
      tabButton(label, categories[label] ?? 0, state.category === label, () => {
        state.category = label;
        state.library = "全部";
        state.page = 1;
        renderTabs({ categories: countCategories(), libraries: countLibraries() });
        applyFilters();
      }),
    );
  });

  const showLibraryTabs = state.category === "量价因子";
  els.libraryRow?.classList.toggle("hidden", !showLibraryTabs);
  els.libraryTabs.replaceChildren();
  if (!showLibraryTabs) {
    return;
  }

  ["全部", "WQ101", "GTJA191", "TA-Lib", "User Custom"].forEach((label) => {
    const count = label === "全部" ? state.rawFactors.length : libraries[label] ?? 0;
    els.libraryTabs.appendChild(
      tabButton(label, count, state.library === label, () => {
        state.library = label;
        state.page = 1;
        renderTabs({ categories: countCategories(), libraries: countLibraries() });
        applyFilters();
      }),
    );
  });
}

function updateConnectionStatus(ok, payload) {
  state.localConnected = ok;
  els.localStatus.className = ok ? "status-pill status-ok" : "status-pill status-bad";
  els.localStatus.textContent = ok ? "本地 Flask：已连接" : "本地 Flask：未连接";
  els.localStatus.title = ok ? "已通过 /health 接口确认" : "未能访问 /health 接口，请确认本地 Flask 服务已启动";
  const cloudLabel = payload?.cloud_registry?.label || "未同步";
  els.cloudStatus.textContent = `云端信息库：${cloudLabel}`;
}

function updateRefreshButton(loading) {
  els.refreshButton.disabled = loading;
  els.refreshButton.classList.toggle("is-loading", loading);
  els.refreshButton.textContent = loading ? "刷新中..." : "刷新";
  els.refreshButton.setAttribute("aria-busy", String(loading));
}

function withCacheBust(url) {
  const parsed = new URL(url);
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

async function loadData() {
  if (state.isLoading) {
    return;
  }
  state.isLoading = true;
  updateRefreshButton(true);
  try {
    const healthy = await checkLocalHealth();
    if (!healthy) throw new Error("Local Flask service is offline");
    const response = await fetchWithTimeout(withCacheBust(`${API_BASE}/factor-library`));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const normalizedPayload = normalizePayload(payload);
    state.rawFactors = normalizedPayload.factors || [];
    updateConnectionStatus(true, payload);
    els.errorPanel.classList.add("hidden");
    renderTabs(normalizedPayload);
    applyFilters();
    syncDetailFromHash();
    if (state.view === "detail") renderDetail();
    if (state.view === "monitor") renderMonitor();
  } catch (error) {
    updateConnectionStatus(false);
    els.errorPanel.classList.remove("hidden");
    state.rawFactors = [];
    state.filteredFactors = [];
    renderTabs({ categories: {}, libraries: {}, factors: [] });
    renderTable();
    if (state.view === "monitor") renderMonitor();
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
    const [truthText, truthClass] = truthBadge(factor.truth_status);
    const openable = canOpenFactor(factor);
    const displayName = compactName(factor.factor_name);
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
      <td><span class="badge ${truthClass}">${truthText}</span></td>
      <td class="number">${formatRatio(factor.coverage_ratio)}</td>
      <td class="number">${formatNumber(factor.rank_ic_mean, 4)}</td>
      <td class="number">${formatNumber(factor.rank_ic_ir, 4)}</td>
      <td class="number">${formatRatio(factor.truth_exact_match_ratio)}</td>
      <td class="number">${formatNumber(factor.long_short_mean, 4)}</td>
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
  const selected = state.rawFactors.filter((factor) => state.selectedIds.has(factor.id));
  const reusable = selected.filter((factor) => factor.reuse_recommendation === "可复用").length;
  const rerun = selected.filter((factor) => factor.reuse_recommendation === "建议重跑").length;
  els.selectedCount.textContent = `已选择 ${selected.length} 个因子`;
  els.selectedReusable.textContent = `可复用 ${reusable} 个`;
  els.selectedRerun.textContent = `建议重跑 ${rerun} 个`;
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

function monitorHint(factor, bucket) {
  if (factor.proof_status === "failed") return "复现失败，建议先重跑";
  if (factor.proof_status === "missing") return "缺少复现产物";
  if (isTruthIssue(factor.truth_status)) return "真值异常，优先排查";
  if (bucket === "missing") return "等待 IC/IR 或研究分析数据";
  if (bucket === "strong") return "优先进入去重和稳定性复核";
  if (bucket === "medium") return "可进入人工 review";
  return "暂不建议进入策略层";
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

  els.monitorStats.innerHTML = [
    ["总因子数", total, "来自当前 specs 与 runtime 产物"],
    ["有 IC/IR", withMetric, "已有可读研究指标"],
    ["可复用", reusable, "按当前适配层建议"],
    ["需关注", review, "复现失败、真值异常或弱指标"],
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
    .sort((a, b) => {
      return (
        monitorSortValue(b.factor) - monitorSortValue(a.factor) ||
        String(a.factor.factor_name).localeCompare(String(b.factor.factor_name), "zh-Hans-CN", { numeric: true })
      );
    });

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
      const [truthText, truthClass] = truthBadge(factor.truth_status);
      const openable = canOpenFactor(factor);
      const name = compactName(factor.factor_name);
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
          <td class="number">${formatRatio(factor.coverage_ratio)}</td>
          <td class="number">${formatNumber(factor.long_short_mean, 4)}</td>
          <td><span class="badge ${proofClass}">${proofText}</span></td>
          <td><span class="badge ${truthClass}">${truthText}</span></td>
          <td>${escapeHtml(monitorHint(factor, bucket))}</td>
        </tr>
      `;
    })
    .join("");

  els.monitorTableBody.querySelectorAll("[data-factor-id]").forEach((button) => {
    button.addEventListener("click", () => openDetail(button.dataset.factorId));
  });
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
  state.view = view === "monitor" ? "monitor" : "library";
  state.activeFactorId = null;
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
  els.pageTitle.textContent = detailMode ? "因子详情" : monitorMode ? "因子监控" : "因子库";
  els.libraryView.classList.toggle("hidden", detailMode || monitorMode);
  els.monitorView.classList.toggle("hidden", !monitorMode);
  els.detailView.classList.toggle("hidden", !detailMode);
  els.selectionBar.classList.toggle("hidden", detailMode || monitorMode);
  els.navItems.forEach((item) => {
    const activeView = detailMode ? "library" : state.view;
    item.classList.toggle("active", item.dataset.view === activeView);
  });
  if (monitorMode) renderMonitor();
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

    ${renderResearchSettings(factor)}

    <nav class="detail-tabs" aria-label="单因子报告切换">
      <button type="button" class="${state.detailTab === "analysis" ? "active" : ""}" data-tab="analysis">复现与研究分析</button>
      <button type="button" disabled>策略回测（待接入）</button>
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
}

function renderResearchSettings(factor) {
  return `
    <section class="research-settings-card" aria-label="研究与回测参数">
      <div class="settings-head">
        <div>
          <strong>研究与回测参数</strong>
          <span>这些参数是复现与研究分析、策略回测的共同前提。当前仅展示口径；接入研究分析数据后，切换区间会同步更新 IC、IR 和图表。</span>
        </div>
        <dl>
          <div><dt>当前研究区间</dt><dd>当前复现样本区间</dd></div>
          <div><dt>指标更新时间</dt><dd>${formatDate(factor.latest_checked_at)}</dd></div>
          <div><dt>数据来源</dt><dd>${escapeHtml(factor.data_source || "-")}</dd></div>
        </dl>
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
        <label>
          <span>调仓周期</span>
          <select disabled>
            <option selected>待策略层接入</option>
            <option>1天</option>
            <option>5天</option>
            <option>20天</option>
          </select>
        </label>
        <label>
          <span>调仓时间</span>
          <select disabled>
            <option selected>待策略层接入</option>
            <option>收盘价</option>
            <option>次日开盘</option>
          </select>
        </label>
        <label>
          <span>过滤涨停及停牌股</span>
          <select disabled>
            <option selected>待真实交易状态数据</option>
            <option>是</option>
            <option>否</option>
          </select>
        </label>
        <label>
          <span>手续费及滑点</span>
          <select disabled>
            <option selected>待策略层接入</option>
            <option>千三佣金 + 千一印花税 + 无滑点</option>
            <option>万三佣金 + 千一印花税 + 万一滑点</option>
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
