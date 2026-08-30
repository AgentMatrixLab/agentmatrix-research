/* A股因子库目录（静态快照版）— 前端逻辑
 * 数据源：./data/factors.json（由 research_core.factor_db.snapshot 生成，与 API 同口径）
 * 因子值实时查询 / 真实分布需本地 API：python -m research_core.factor_db.api
 */
"use strict";

const state = {
  snapshot: null,
  factors: [],
  filtered: [],
  stats: {},
  byId: new Map(),
  selected: null,
  category: "",
  source: "",
  search: "",
};

const $ = (id) => document.getElementById(id);

/* ---------------- 登录门禁（与生命周期面板同一模式） ---------------- */
const ACCESS_PASSWORD = window.FACTORDB_ACCESS_PASSWORD || "factorlab2026";
const AUTH_KEY = "FACTORDB_AUTH_OK";

function isAuthed() { return sessionStorage.getItem(AUTH_KEY) === "1"; }
function showApp() {
  document.body.classList.remove("auth-locked");
  $("loginError").textContent = "";
  if (!state.snapshot) loadData();
}
function showLogin(msg) {
  document.body.classList.add("auth-locked");
  if (msg) $("loginError").textContent = msg;
  setTimeout(() => $("loginPassword")?.focus(), 50);
}
function bindAuth() {
  $("loginForm").addEventListener("submit", (e) => {
    e.preventDefault();
    if (($("loginPassword").value || "") === ACCESS_PASSWORD) {
      sessionStorage.setItem(AUTH_KEY, "1");
      showApp();
    } else {
      showLogin("密码不正确，请重试");
    }
  });
  $("logoutBtn").addEventListener("click", (e) => {
    e.preventDefault();
    sessionStorage.removeItem(AUTH_KEY);
    showLogin("已退出登录");
  });
}

/* ---------------- 初始化 ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  bindAuth();
  if (isAuthed()) showApp(); else showLogin();
});

async function loadData() {
  try {
    const res = await fetch("./data/factors.json");
    state.snapshot = await res.json();
  } catch (e) {
    $("topStats").textContent = "快照加载失败";
    return;
  }
  state.factors = state.snapshot.factors || [];
  state.stats = state.snapshot.stats || {};
  state.factors.forEach((f) => state.byId.set(f.factor_id, f));
  state.filtered = [...state.factors];

  $("modeStatus").textContent = `静态快照 · 生成于 ${formatTime(state.snapshot.generated_at)} · 因子值实时查询需本地 API`;
  const byCat = state.stats.by_category || {};
  $("topStats").innerHTML = `共 <b>${state.stats.total_factors}</b> 个因子 · ` +
    Object.entries(byCat).map(([k, v]) => `${k} <b>${v}</b>`).join(" · ");
  renderChips();
  renderList();
  bindEvents();
  if (state.filtered.length) {
    const roe = state.byId.get("QAPI33:roe_ttm");
    selectFactor((roe || state.filtered[0]).factor_id);
  }
}

function bindEvents() {
  let timer = null;
  $("searchInput").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.search = e.target.value.trim();
      applyFilter();
    }, 150);
  });

  $("dictCsvLink").addEventListener("click", (e) => {
    e.preventDefault();
    downloadCsv("factor_db_dictionary.csv", state.snapshot.dictionary || []);
  });
  $("dictJsonLink").addEventListener("click", (e) => {
    e.preventDefault();
    downloadJson("factor_db_dictionary.json", state.snapshot.dictionary || []);
  });
}

/* ---------------- 过滤与列表 ---------------- */
function applyFilter() {
  const { category, source, search } = state;
  const needle = search.toLowerCase();
  state.filtered = state.factors.filter((f) => {
    if (category && f.category !== category) return false;
    if (source && !f.factor_id.startsWith(source + ":")) return false;
    if (needle) {
      const hay = [f.name_cn, f.name_en, f.factor_id, f.definition || "", f.formula_expr || ""]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
  renderList();
}

const SOURCE_LABELS = {
  QAPI33: "Quant API 33",
  ALPHA101: "Alpha101",
  GTJA191: "GTJA191",
  TDXGS: "通达信指标",
  JQ110: "JQ110 技术因子",
  ALPHA158: "Alpha158",
  ALPHA360: "Alpha360",
  BARRA: "Barra CNE5",
  JQGM: "换手率家族",
};

function renderChips() {
  const catChips = $("categoryChips");
  const byCat = state.stats.by_category || {};
  catChips.innerHTML = "";
  catChips.appendChild(chipEl("全部", null, !state.category, () => { state.category = ""; refresh(); }));
  Object.entries(byCat).forEach(([name, count]) => {
    catChips.appendChild(chipEl(name, count, state.category === name, () => {
      state.category = state.category === name ? "" : name;
      refresh();
    }));
  });

  const srcChips = $("sourceChips");
  srcChips.innerHTML = "";
  const bySrc = state.stats.by_source || {};
  srcChips.appendChild(chipEl("全部", null, !state.source, () => { state.source = ""; refresh(); }));
  Object.entries(bySrc).forEach(([key, count]) => {
    const label = SOURCE_LABELS[key] || key;
    srcChips.appendChild(chipEl(label, count, state.source === key, () => {
      state.source = state.source === key ? "" : key;
      refresh();
    }));
  });
}

function chipEl(name, count, active, onClick) {
  const el = document.createElement("button");
  el.className = "chip" + (active ? " active" : "");
  el.textContent = name;
  if (count !== null) {
    el.innerHTML = `${escapeHtml(name)} <span class="cnt">${count}</span>`;
  }
  el.addEventListener("click", onClick);
  return el;
}

function refresh() {
  renderChips();
  applyFilter();
}

function renderList() {
  const list = $("factorList");
  $("resultMeta").textContent = `${state.filtered.length} / ${state.factors.length} 个因子`;
  list.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const f of state.filtered) {
    const item = document.createElement("div");
    item.className = "factor-item" + (state.selected === f.factor_id ? " active" : "");
    item.dataset.id = f.factor_id;
    item.innerHTML = `
      <div class="f-name">${escapeHtml(f.name_cn)}</div>
      <div class="f-id">${escapeHtml(f.factor_id)}</div>
      <div class="f-tags">
        <span class="tag cat-${f.category}">${f.category}</span>
        <span class="tag">${f.subcategory}</span>
        <span class="tag">${f.frequency.split("；")[0]}</span>
      </div>`;
    item.addEventListener("click", () => selectFactor(f.factor_id));
    frag.appendChild(item);
  }
  list.appendChild(frag);
}

/* ---------------- 详情 ---------------- */
function selectFactor(factorId) {
  state.selected = factorId;
  document.querySelectorAll(".factor-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === factorId);
  });
  const activeEl = document.querySelector(`.factor-item[data-id="${CSS.escape(factorId)}"]`);
  if (activeEl) activeEl.scrollIntoView({ block: "nearest" });

  const f = state.byId.get(factorId);
  if (f) renderDetail(f);
}

function metaCell(k, v) {
  return `<div class="meta-cell"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(v || "—")}</div></div>`;
}

function renderDetail(f) {
  $("detailEmpty").hidden = true;
  const panel = $("detailContent");
  panel.hidden = false;

  const live = f.factor_id.startsWith("QAPI33:");
  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-title">
        <h1>${escapeHtml(f.name_cn)}</h1>
        <div class="en">${escapeHtml(f.name_en)} · <code>${escapeHtml(f.factor_id)}</code></div>
      </div>
      <div class="detail-actions">
        <button class="btn" data-act="meta-csv">导出元数据 CSV</button>
        ${live ? '<button class="btn primary" data-act="values-csv" title="需本地 API + Quant API token">导出因子值 CSV</button>' : ""}
      </div>
    </div>

    <div class="meta-grid">
      ${metaCell("大类", f.category)}
      ${metaCell("子类", f.subcategory)}
      ${metaCell("数据来源", f.data_source)}
      ${metaCell("数据频率", f.frequency)}
      ${metaCell("覆盖范围", f.coverage)}
      ${metaCell("历史起始", f.history_start)}
    </div>

    <div class="section">
      <div class="section-title">因子定义</div>
      <div class="section-body">${escapeHtml(f.definition)}</div>
    </div>

    <div class="section">
      <div class="section-title">计算逻辑</div>
      <div class="section-body">${escapeHtml(f.calc_logic)}</div>
    </div>

    <div class="section">
      <div class="section-title">因子公式</div>
      <div class="formula-block">
        <div class="formula-label">数学公式（LaTeX）</div>
        <div id="latexFormula"></div>
        <div class="formula-label" style="margin-top:14px">伪代码表达式</div>
        <div class="expr">${escapeHtml(f.formula_expr || "")}</div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">逻辑说明</div>
      <div class="section-body notice purple">${escapeHtml(f.logic_notes || "—")}</div>
    </div>

    <div class="section">
      <div class="section-title">应用场景</div>
      <div class="section-body notice green">${escapeHtml(f.application || "—")}</div>
    </div>

    <div class="section">
      <div class="section-title">注意事项</div>
      <div class="section-body notice">${escapeHtml(f.cautions || "—")}</div>
    </div>

    <div class="section">
      <div class="section-title">因子分布</div>
      <div class="dist-controls">
        <span class="dist-note demo">演示模式：正态代理样本（非真实因子值）· 真实数据需本地 API + Quant API token</span>
        <span class="dist-note" id="distNote"></span>
      </div>
      <div class="chart-card">
        <canvas id="distCanvas" height="260"></canvas>
        <div class="stats-grid" id="statsGrid"></div>
      </div>
    </div>
  `;

  renderLatex(f.formula_latex || "");
  const metaBtn = panel.querySelector('[data-act="meta-csv"]');
  metaBtn.addEventListener("click", () => downloadCsv(`factor_${f.factor_id.replace(":", "_")}_meta.csv`, [f]));
  const valuesBtn = panel.querySelector('[data-act="values-csv"]');
  if (valuesBtn) {
    valuesBtn.addEventListener("click", () => {
      alert("因子值导出需要本地数据服务：\n\n1. 启动 API：python -m research_core.factor_db.api\n2. 配置 token：环境变量 FACTOR_LAB_QUANT_API_TOKEN\n3. 访问 /factor-db/ 使用完整数据面板");
    });
  }
  drawDemoDistribution(f.factor_id);
}

function renderLatex(raw) {
  const el = $("latexFormula");
  if (!el) return;
  if (window.katex && raw) {
    try {
      katex.render(raw, el, { displayMode: true, throwOnError: false });
      return;
    } catch { /* fallthrough */ }
  }
  el.textContent = raw || "—";
  el.style.color = "var(--text-dim)";
}

/* ---------------- 演示分布（客户端正态代理，与 API demo 模式同口径并明确标注） ---------------- */
function hashSeed(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function demoDistribution(factorId, bins = 36, n = 4000) {
  const rng = mulberry32(hashSeed(factorId));
  const u = () => {
    let s = 0;
    for (let i = 0; i < 12; i++) s += rng();
    return s - 6; // 近似标准正态（均值 0，方差 1）
  };
  const values = [];
  for (let i = 0; i < n; i++) values.push(u());

  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const width = (hi - lo) / bins;
  const counts = new Array(bins).fill(0);
  values.forEach((v) => counts[Math.min(Math.floor((v - lo) / width), bins - 1)]++);
  const histogram = counts.map((c, i) => ({ bin_left: lo + i * width, bin_right: lo + (i + 1) * width, count: c }));

  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1);
  const std = Math.sqrt(variance);
  const sorted = [...values].sort((a, b) => a - b);
  const pct = (q) => {
    const idx = (sorted.length - 1) * q / 100;
    const low = Math.floor(idx), high = Math.ceil(idx);
    return sorted[low] * (1 - idx + low) + sorted[high] * (idx - low);
  };
  const skew = std > 0 ? values.reduce((a, b) => a + ((b - mean) / std) ** 3, 0) / n : 0;
  const kurt = std > 0 ? values.reduce((a, b) => a + ((b - mean) / std) ** 4, 0) / n - 3 : 0;
  const p25 = pct(25), p75 = pct(75);
  const stats = {
    count: n, mean, std, min: sorted[0], max: sorted[n - 1],
    p25, p50: pct(50), p75,
    skewness: skew, kurtosis: kurt,
    iqr: p75 - p25,
    outlier_ratio_p1_p99: values.filter((v) => v < pct(1) || v > pct(99)).length / n,
  };
  return { stats, histogram };
}

function drawDemoDistribution(factorId) {
  const note = $("distNote");
  const canvas = $("distCanvas");
  if (!canvas) return;
  note.textContent = "计算中…";
  const { stats, histogram } = demoDistribution(factorId);
  note.textContent = `演示样本 ${stats.count} · 均值 ${fmtNum(stats.mean)} · 标准差 ${fmtNum(stats.std)}`;
  drawHistogram(canvas, histogram, stats);
  renderStatsGrid(stats);
}

function drawHistogram(canvas, bins, stats) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 800;
  const height = 260;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const pad = { l: 52, r: 16, t: 16, b: 30 };
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  ctx.clearRect(0, 0, width, height);

  const lo = bins[0].bin_left;
  const hi = bins[bins.length - 1].bin_right;
  const maxCount = Math.max(...bins.map((b) => b.count));
  const x = (v) => pad.l + ((v - lo) / (hi - lo || 1)) * plotW;
  const y = (c) => pad.t + plotH - (c / maxCount) * plotH;

  ctx.strokeStyle = "#2a3644";
  ctx.fillStyle = "#8a9bb0";
  ctx.font = "10px sans-serif";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const yy = pad.t + (plotH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.l, yy);
    ctx.lineTo(pad.l + plotW, yy);
    ctx.stroke();
    ctx.fillText(String(Math.round(maxCount * (1 - i / 4))), 8, yy + 3);
  }

  const barW = plotW / bins.length;
  bins.forEach((b, i) => {
    const bx = pad.l + i * barW;
    const bh = plotH - (y(b.count) - pad.t);
    const grad = ctx.createLinearGradient(0, pad.t + plotH - bh, 0, pad.t + plotH);
    grad.addColorStop(0, "rgba(77,163,255,0.85)");
    grad.addColorStop(1, "rgba(77,163,255,0.25)");
    ctx.fillStyle = grad;
    ctx.fillRect(bx + 0.6, y(b.count), barW - 1.2, bh);
  });

  const qline = (v, color, label) => {
    if (!Number.isFinite(v)) return;
    ctx.strokeStyle = color;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x(v), pad.t);
    ctx.lineTo(x(v), pad.t + plotH);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.fillText(label, x(v) + 3, pad.t + 10);
  };
  qline(stats.p25, "rgba(52,211,153,0.7)", "P25");
  qline(stats.p50, "rgba(251,191,36,0.9)", "P50");
  qline(stats.p75, "rgba(52,211,153,0.7)", "P75");

  ctx.fillStyle = "#8a9bb0";
  for (let i = 0; i <= 6; i++) {
    const v = lo + ((hi - lo) / 6) * i;
    ctx.fillText(fmtNum(v), x(v) - 14, height - 10);
  }
}

function renderStatsGrid(stats) {
  const cells = [
    ["样本数", stats.count],
    ["均值", stats.mean],
    ["标准差", stats.std],
    ["最小值", stats.min],
    ["P25", stats.p25],
    ["中位数", stats.p50],
    ["P75", stats.p75],
    ["最大值", stats.max],
    ["偏度", stats.skewness],
    ["峰度", stats.kurtosis],
    ["IQR", stats.iqr],
    ["P1/P99外比例", stats.outlier_ratio_p1_p99],
  ];
  $("statsGrid").innerHTML = cells
    .map(([k, v]) => `<div class="stat-cell"><div class="k">${k}</div><div class="v">${fmtNum(v)}</div></div>`)
    .join("");
}

/* ---------------- 导出与工具 ---------------- */
function downloadCsv(filename, rows) {
  if (!rows || !rows.length) return;
  const keys = Object.keys(rows[0]);
  const esc = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = "\ufeff" + keys.join(",") + "\n" + rows.map((r) => keys.map((k) => esc(r[k])).join(",")).join("\n");
  triggerDownload(new Blob([csv], { type: "text/csv;charset=utf-8" }), filename);
}

function downloadJson(filename, data) {
  const json = JSON.stringify(data, null, 2);
  triggerDownload(new Blob([json], { type: "application/json;charset=utf-8" }), filename);
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatTime(iso) {
  if (!iso) return "—";
  return iso.replace("T", " ").replace(/:\d\d$/, " UTC");
}

function fmtNum(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v !== "number") return String(v);
  if (Math.abs(v) >= 1000) return v.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
  if (Math.abs(v) >= 1) return v.toFixed(2);
  if (v === 0) return "0";
  return v.toPrecision(3);
}
