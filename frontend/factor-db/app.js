/* A股因子数据库 Web 原型 — 前端逻辑 */
"use strict";

const API = "/api/factor-db";

const state = {
  factors: [],
  filtered: [],
  stats: {},
  selected: null,
  category: "",
  source: "",
  search: "",
};

const $ = (id) => document.getElementById(id);

/* ---------------- 初始化 ---------------- */
document.addEventListener("DOMContentLoaded", async () => {
  await Promise.all([loadStats(), loadFactors()]);
  renderChips();
  renderList();
  bindEvents();
  checkApiStatus();
  // 默认选中 ROE 演示详情
  if (state.filtered.length) {
    const roe = state.filtered.find((f) => f.factor_id === "QAPI33:roe_ttm");
    selectFactor((roe || state.filtered[0]).factor_id);
  }
});

function bindEvents() {
  let timer = null;
  $("searchInput").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.search = e.target.value.trim();
      applyFilter();
    }, 200);
  });

  $("apiDocLink").addEventListener("click", (e) => {
    e.preventDefault();
    alert(
      [
        "Factor DB API 端点：",
        "",
        `GET ${API}/stats                          目录统计`,
        `GET ${API}/factors?category=&search=      因子列表`,
        `GET ${API}/factors/QAPI33:roe_ttm         因子详情`,
        `GET ${API}/factors/QAPI33:roe_ttm/values?symbol=000001.SZ  因子值`,
        `GET ${API}/factors/QAPI33:roe_ttm/distribution   分布统计`,
        `GET ${API}/factors/QAPI33:roe_ttm/export?format=csv|xlsx&scope=values|meta  导出`,
        `GET ${API}/dictionary?format=json|csv|xlsx  数据字典`,
        `GET ${API}/quant-api/status               数据源状态`,
      ].join("\n")
    );
  });
}

/* ---------------- 数据加载 ---------------- */
async function loadStats() {
  try {
    const res = await fetch(`${API}/stats`);
    state.stats = await res.json();
    $("topStats").innerHTML = `共 <b>${state.stats.total_factors}</b> 个因子 · ` +
      Object.entries(state.stats.by_category || {})
        .map(([k, v]) => `${k} <b>${v}</b>`)
        .join(" · ");
  } catch {
    $("topStats").textContent = "API 不可用";
  }
}

async function loadFactors() {
  const res = await fetch(`${API}/factors?limit=500`);
  const payload = await res.json();
  state.factors = payload.factors || [];
  state.filtered = [...state.factors];
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

function renderChips() {
  const catChips = $("categoryChips");
  const byCat = state.stats.by_category || {};
  catChips.innerHTML = "";
  const all = chipEl("全部", "", state.category, () => { state.category = ""; refresh(); });
  all.classList.add("active");
  catChips.appendChild(all);
  Object.entries(byCat).forEach(([name, count]) => {
    catChips.appendChild(chipEl(name, `${name} (${count})`, state.category === name, () => {
      state.category = state.category === name ? "" : name;
      refresh();
    }));
  });

  const srcChips = $("sourceChips");
  srcChips.innerHTML = "";
  const bySrc = state.stats.by_source || {};
  const allSrc = chipEl("全部", "", state.source, () => { state.source = ""; refresh(); });
  srcChips.appendChild(allSrc);
  Object.entries(bySrc).forEach(([key, count]) => {
    const label = {
      QAPI33: "Quant API 33",
      ALPHA101: "Alpha101",
      GTJA191: "GTJA191",
      TDXGS: "通达信指标",
      JQ110: "聚宽110",
      ALPHA158: "Alpha158",
      ALPHA360: "Alpha360",
    }[key] || key;
    srcChips.appendChild(chipEl(label, `${label} (${count})`, state.source === key, () => {
      state.source = state.source === key ? "" : key;
      refresh();
    }));
  });
}

function chipEl(name, text, active, onClick) {
  const el = document.createElement("button");
  el.className = "chip" + (active ? " active" : "");
  el.innerHTML = text ? `${name} <span class="cnt">${text.match(/\((\d+)\)/)?.[1] || ""}</span>`.trim() : name;
  if (!text) el.textContent = name;
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
        <span class="tag">${f.frequency}</span>
      </div>`;
    item.addEventListener("click", () => selectFactor(f.factor_id));
    frag.appendChild(item);
  }
  list.appendChild(frag);
}

/* ---------------- 详情 ---------------- */
async function selectFactor(factorId) {
  state.selected = factorId;
  document.querySelectorAll(".factor-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === factorId);
  });
  const activeEl = document.querySelector(`.factor-item[data-id="${CSS.escape(factorId)}"]`);
  if (activeEl) activeEl.scrollIntoView({ block: "nearest" });

  const res = await fetch(`${API}/factors/${encodeURIComponent(factorId)}`);
  const factor = await res.json();
  renderDetail(factor);
  loadDistribution(factorId);
}

function metaCell(k, v) {
  return `<div class="meta-cell"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(v || "—")}</div></div>`;
}

function renderDetail(f) {
  $("detailEmpty").hidden = true;
  const panel = $("detailContent");
  panel.hidden = false;

  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-title">
        <h1>${escapeHtml(f.name_cn)}</h1>
        <div class="en">${escapeHtml(f.name_en)} · <code>${escapeHtml(f.factor_id)}</code></div>
      </div>
      <div class="detail-actions">
        <a class="btn" href="${API}/factors/${encodeURIComponent(f.factor_id)}/export?scope=meta&format=csv">导出元数据 CSV</a>
        <a class="btn primary" href="${API}/factors/${encodeURIComponent(f.factor_id)}/export?scope=values&format=csv">导出因子值 CSV</a>
        <a class="btn" href="${API}/factors/${encodeURIComponent(f.factor_id)}/export?scope=values&format=xlsx">Excel</a>
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
        <div id="latexFormula">$${escapeHtml(f.formula_latex || "")}$</div>
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

    <div class="section" id="distSection">
      <div class="section-title">因子分布</div>
      <div class="dist-controls">
        <button class="btn" id="distReload">重新计算分布</button>
        <label class="dist-note"><input type="checkbox" id="demoToggle" style="vertical-align:-2px;margin-right:4px" />演示模式（无需 token）</label>
        <span class="dist-note" id="distNote"></span>
      </div>
      <div class="chart-card">
        <canvas id="distCanvas" height="260"></canvas>
        <div class="stats-grid" id="statsGrid"></div>
      </div>
    </div>
  `;

  renderLatex();
  $("distReload").addEventListener("click", () => loadDistribution(f.factor_id));
  $("demoToggle").addEventListener("change", () => loadDistribution(f.factor_id));
}

function renderLatex() {
  const el = $("latexFormula");
  if (!el || !window.katex) return;
  const raw = el.textContent.replace(/^\$/, "").replace(/\$$/, "");
  try {
    katex.render(raw, el, { displayMode: true, throwOnError: false });
  } catch {
    el.textContent = raw;
  }
}

/* ---------------- 分布图 ---------------- */
async function loadDistribution(factorId) {
  const note = $("distNote");
  const canvas = $("distCanvas");
  if (!canvas) return;
  note.textContent = "加载中…";
  note.className = "dist-note";

  const demo = $("demoToggle") && $("demoToggle").checked ? "&demo=1" : "";
  try {
    const res = await fetch(`${API}/factors/${encodeURIComponent(factorId)}/distribution?bins=36${demo}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      note.textContent = `暂无真实数据（${err.error || res.status}）— 可勾选"演示模式"查看形态`;
      note.className = "dist-note demo";
      drawEmpty(canvas);
      $("statsGrid").innerHTML = "";
      return;
    }
    const dist = await res.json();
    note.textContent = `${dist.note} · 截面日期 ${dist.trade_date} · 样本 ${dist.sample_count}`;
    note.className = "dist-note" + (dist.demo ? " demo" : "");
    drawHistogram(canvas, dist.histogram, dist.stats);
    renderStatsGrid(dist.stats);
  } catch (e) {
    note.textContent = "分布加载失败: " + e.message;
  }
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

  // 网格线
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
    const val = Math.round(maxCount * (1 - i / 4));
    ctx.fillText(String(val), 8, yy + 3);
  }

  // 直方柱
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

  // 中位数/分位线
  const qline = (v, color, label) => {
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
  if (stats) {
    qline(stats.p25, "rgba(52,211,153,0.7)", "P25");
    qline(stats.p50, "rgba(251,191,36,0.9)", "P50");
    qline(stats.p75, "rgba(52,211,153,0.7)", "P75");
  }

  // X 轴刻度
  ctx.fillStyle = "#8a9bb0";
  for (let i = 0; i <= 6; i++) {
    const v = lo + ((hi - lo) / 6) * i;
    ctx.fillText(fmtNum(v), x(v) - 14, height - 10);
  }
}

function drawEmpty(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 800;
  canvas.width = width * dpr;
  canvas.height = 260 * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, 260);
  ctx.fillStyle = "#8a9bb0";
  ctx.font = "13px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("暂无分布数据", width / 2, 130);
  ctx.textAlign = "left";
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

/* ---------------- API 状态 ---------------- */
async function checkApiStatus() {
  try {
    const res = await fetch(`${API}/quant-api/status`);
    const s = await res.json();
    $("apiStatus").textContent = s.token_configured
      ? `Quant API: 已连接（${s.base_url}）`
      : "Quant API: token 未配置（因子值查询不可用，可勾选演示模式）";
  } catch {
    $("apiStatus").textContent = "Quant API: 状态未知";
  }
}

/* ---------------- 工具 ---------------- */
function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtNum(v) {
  if (v === null || v === undefined) return "—";
  if (Math.abs(v) >= 1000) return v.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
  if (Math.abs(v) >= 1) return Number(v).toFixed(2);
  if (v === 0) return "0";
  return Number(v).toPrecision(3);
}
