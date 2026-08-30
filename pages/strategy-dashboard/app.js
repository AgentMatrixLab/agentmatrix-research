/* 策略监控面板 — 读取 ./data/strategies.json（factor_lab_strategy_monitor_v1 契约）
 * 静态快照版：GitHub Pages 部署，无后端依赖。
 * 路由：?id=xxx 进入策略详情（popstate 支持前进/后退），无参数为列表视图。 */
"use strict";

const state = {
  doc: null,
  filter: { search: "", status: "", category: "", rebalance: "", sort: "default" },
};

const $ = id => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
const fmt = (v, d = 4) => (v === null || v === undefined || Number.isNaN(Number(v))) ? "—" : Number(v).toFixed(d);
const isNum = v => v !== null && v !== undefined && !Number.isNaN(Number(v));

/* ═══════════ 数据加载 ═══════════ */

async function load() {
  try {
    const res = await fetch("./data/strategies.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.doc = await res.json();
    initFilterOptions();
    route();
  } catch (err) {
    $("main").innerHTML =
      `<section class="panel"><p>加载失败：${esc(err.message)}</p>
       <p class="hint">先运行 <code>python pages/strategy-dashboard/generate_data.py</code> 生成数据。</p></section>`;
  }
}

/* ═══════════ 路由（query param + popstate） ═══════════ */

function route() {
  const id = new URLSearchParams(location.search).get("id");
  if (id && state.doc.strategies.some(s => s.strategy_id === id)) {
    renderDetail(id);
  } else if (id) {
    renderNotFound(id);
  } else {
    renderList();
  }
}

function navigate(id) {
  const url = id ? `./?id=${encodeURIComponent(id)}` : "./";
  history.pushState({ id }, "", url);
  route();
}

window.addEventListener("popstate", route);

function renderNotFound(id) {
  $("list-view").style.display = "none";
  const dv = $("detail-view");
  dv.style.display = "";
  // 隐藏常规详情区块，只显示 not-found
  dv.querySelectorAll("section.panel, section.detail-header").forEach(el => el.style.display = "none");
  const nf = $("not-found");
  nf.style.display = "";
  nf.innerHTML = `<p>未找到策略：<code>${esc(id)}</code></p>
    <p><a href="./">← 返回策略列表</a></p>`;
}

/* ═══════════ 列表视图 ═══════════ */

function renderList() {
  $("detail-view").style.display = "none";
  $("list-view").style.display = "";
  const { strategies } = state.doc;

  const ready = strategies.filter(s => s.status === "backtest_ready").length;
  const validating = strategies.filter(s => s.status === "review_needed").length;
  const pending = strategies.filter(s => s.status === "not_connected").length;
  const ics = strategies.map(s => s.ic_summary?.mean_rank_ic).filter(isNum);
  const bestAbsIc = ics.length ? Math.max(...ics.map(Math.abs)) : null;
  const cats = new Set(strategies.map(s => s.factor_meta.category));

  $("stats").innerHTML = `
    <div class="stat"><div class="v">${strategies.length}</div><div class="k">策略总数</div></div>
    <div class="stat"><div class="v">${ready}</div><div class="k">回测就绪</div></div>
    <div class="stat"><div class="v">${validating}</div><div class="k">研究验证中</div></div>
    <div class="stat"><div class="v">${pending}</div><div class="k">验证待启动</div></div>
    <div class="stat"><div class="v">${cats.size}</div><div class="k">因子类别覆盖</div></div>
    <div class="stat"><div class="v">${bestAbsIc === null ? "—" : fmt(bestAbsIc)}</div><div class="k">最大 |IC|（因子验证）</div></div>`;

  $("sub-title").textContent =
    `${strategies.length} 个单因子策略 · ${new Set(strategies.flatMap(s => s.factors)).size} 个基础因子 · 快照 ${state.doc.generated_at.slice(0, 10)}`;

  renderGrid();
}

/* ── 筛选 ── */

function initFilterOptions() {
  const { strategies } = state.doc;
  const uniq = key => [...new Set(strategies.map(s => key(s)))].filter(Boolean).sort();

  for (const s of uniq(s => `${s.status}|${s.status_label}`)) {
    const [v, label] = s.split("|");
    $("filter-status").insertAdjacentHTML("beforeend", `<option value="${esc(v)}">${esc(label)}</option>`);
  }
  for (const c of uniq(s => s.factor_meta.category)) {
    $("filter-category").insertAdjacentHTML("beforeend", `<option value="${esc(c)}">${esc(c)}</option>`);
  }
  for (const r of uniq(s => s.rebalance)) {
    $("filter-rebalance").insertAdjacentHTML("beforeend", `<option value="${esc(r)}">${esc(r)}</option>`);
  }
}

function applyFilter(strategies) {
  const f = state.filter;
  const q = f.search.trim().toLowerCase();
  let out = strategies.filter(s => {
    if (f.status && s.status !== f.status) return false;
    if (f.category && s.factor_meta.category !== f.category) return false;
    if (f.rebalance && s.rebalance !== f.rebalance) return false;
    if (q) {
      const hay = [s.strategy_name, s.strategy_id, s.factor_meta.factor_id,
                   s.factor_meta.name_cn, s.factor_meta.name_en].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const key = f.sort;
  if (key !== "default") {
    const [field, dir] = key.split("_"); // absic_desc | icir_desc
    const val = s => s.ic_summary?.[field === "absic" ? "mean_rank_ic" : "icir"];
    out = [...out].sort((a, b) => {
      const va = val(a), vb = val(b);
      const na = isNum(va) ? Number(va) : -Infinity;
      const nb = isNum(vb) ? Number(vb) : -Infinity;
      return dir === "desc" ? nb - na : na - nb;
    });
  }
  return out;
}

function renderGrid() {
  const all = state.doc.strategies;
  const list = applyFilter(all);
  const total = all.length;

  $("filter-count").textContent = `${list.length} / ${total}`;
  $("empty-hint").style.display = list.length ? "none" : "";

  $("strategy-grid").innerHTML = list.map(s => {
    const m = s.factor_meta;
    const ic = s.ic_summary || {};
    return `
    <div class="strategy-card" data-sid="${esc(s.strategy_id)}">
      <div class="card-top">
        <div>
          <div class="card-name">${esc(s.strategy_name)}</div>
          <div class="card-type">${esc(s.strategy_id)} · ${esc(s.holding_rule || "")}</div>
        </div>
        <span class="badge ${s.status}">${esc(s.status_label)}</span>
      </div>
      <div class="factor-chip">
        <span class="factor-id">${esc(m.factor_id)}</span>
        <span class="factor-cat">${esc(m.name_cn)} · ${esc(m.category)} / ${esc(m.subcategory)}</span>
      </div>
      <div class="ic-row">
        ${icCell("Mean Rank IC", ic.mean_rank_ic ?? ic.raw_ic)}
        ${icCell("ICIR", ic.icir)}
        ${icCell("Alpha 衰减", ic.alpha_decay)}
      </div>
      <div class="config-line"><b>池</b> ${esc(s.universe)}</div>
      <div class="config-line"><b>调仓</b> ${esc(s.rebalance)} · ${esc(s.cost_model)}</div>
      <div class="gate-dots">${gateDots(s.factor_evidence)}</div>
      <div class="card-cta">查看详情 →</div>
    </div>`;
  }).join("");

  $("strategy-grid").querySelectorAll(".strategy-card").forEach(card => {
    card.onclick = () => navigate(card.dataset.sid);
  });
}

/* 筛选事件绑定（绑定一次） */
let filterBound = false;
function bindFilterEvents() {
  if (filterBound) return;
  filterBound = true;

  let debounce = null;
  $("filter-search").addEventListener("input", e => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.filter.search = e.target.value; renderGrid(); }, 200);
  });
  for (const [id, key] of [["filter-status", "status"], ["filter-category", "category"],
                            ["filter-rebalance", "rebalance"], ["filter-sort", "sort"]]) {
    $(id).addEventListener("change", e => { state.filter[key] = e.target.value; renderGrid(); });
  }
  $("filter-clear").addEventListener("click", () => {
    state.filter = { search: "", status: "", category: "", rebalance: "", sort: "default" };
    $("filter-search").value = "";
    $("filter-status").value = "";
    $("filter-category").value = "";
    $("filter-rebalance").value = "";
    $("filter-sort").value = "default";
    renderGrid();
  });
}

/* ═══════════ 详情视图 ═══════════ */

function kv(pairs) {
  return `<dl class="kv">${pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v ?? "—")}</dd>`).join("")}</dl>`;
}

function renderDetail(id) {
  $("list-view").style.display = "none";
  const dv = $("detail-view");
  dv.style.display = "";
  // 恢复被 not-found 隐藏的区块
  dv.querySelectorAll("section.panel, section.detail-header").forEach(el => el.style.display = "");
  $("not-found").style.display = "none";

  const s = state.doc.strategies.find(x => x.strategy_id === id);
  const m = s.factor_meta;

  document.title = `${s.strategy_name} · 策略监控面板`;
  $("detail-title").textContent = s.strategy_name;
  $("detail-sub").textContent = `${s.strategy_id} · ${s.strategy_type}`;
  $("detail-crumb").textContent = s.strategy_name;
  const badge = $("detail-badge");
  badge.textContent = s.status_label;
  badge.className = `badge ${s.status}`;

  $("detail-config").innerHTML = kv([
    ["策略类型", s.strategy_type],
    ["基础因子", m.factor_id],
    ["因子名称", `${m.name_cn}（${m.name_en}）`],
    ["因子分类", `${m.category} / ${m.subcategory} · ${m.frequency}`],
    ["股票池", s.universe],
    ["调仓频率", s.rebalance],
    ["持仓规则", s.holding_rule],
    ["成本模型", s.cost_model],
    ["策略依据", s.rationale],
  ]);

  $("detail-formula").innerHTML = `
    <div class="expr">${esc(m.formula_expr)}</div>
    <p class="hint" style="margin-top:8px">${esc(m.definition)}</p>`;

  $("detail-ic-chart").innerHTML = renderIcEvidence(s);

  const ev = s.factor_evidence;
  if (ev) {
    $("detail-gate-summary").textContent = `${ev.n_gates_passed}/${ev.n_gates_run} 闸门通过 · 生命周期状态：${ev.factor_state_label}`;
    $("detail-gates").innerHTML = ev.gates.map(g => {
      const evRows = Object.entries(g.evidence || {})
        .map(([k, v]) => `<div><b>${esc(k)}</b>：${esc(Array.isArray(v) ? `[${v.map(x => fmt(x, 4)).join(", ")}]` : fmt(v, 4))}</div>`)
        .join("");
      return `
      <div class="gate-item">
        <div class="g-head">
          <div><div class="g-name">${esc(g.label)}</div><div class="g-desc">${esc(g.desc)}</div></div>
          <span class="${g.passed ? "g-pass" : "g-fail"}">${g.passed ? "✓ 通过" : "✗ 失败"}</span>
        </div>
        ${evRows ? `<div class="g-ev">${evRows}</div>` : ""}
        ${g.reason ? `<div class="g-reason">失败原因：${esc(g.reason)}</div>` : ""}
      </div>`;
    }).join("");
  } else {
    $("detail-gate-summary").textContent = "";
    $("detail-gates").innerHTML =
      `<div class="placeholder-note">该因子的验证数据尚未生成（因子值数据待拉取任务产出），策略停留在「验证待启动」状态。</div>`;
  }

  $("detail-metrics").innerHTML = `
    <div class="placeholder-note">
      策略回测尚未运行。接入 research_core/strategy_engine 后，此处将填充年化收益 / 夏普 / 最大回撤 / 换手率（strategy_monitor_view_v1 契约字段）。
    </div>`;

  window.scrollTo(0, 0);
}

/* ═══════════ SVG 图表（纯内联，零依赖） ═══════════ */

/* Bootstrap 95% CI 可视化：点估计 + CI 区间 + 零基准线（G6 数据） */
function ciChartSvg(mean, ci95) {
  if (!isNum(mean) || !Array.isArray(ci95) || ci95.length < 2) return "";
  const [lo, hi] = ci95.map(Number);

  const W = 720, H = 150, PL = 10, PR = 10;
  const pad = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(mean)) * 1.25;
  const x = v => PL + (W - PL - PR) * ((v + pad) / (2 * pad));
  const yMid = 55, barH = 26;
  const containsZero = lo <= 0 && hi >= 0;

  return `
  <svg viewBox="0 0 ${W} ${H}" class="ci-chart" role="img" aria-label="Rank IC Bootstrap 95% 置信区间">
    <!-- 零基准线 -->
    <line x1="${x(0)}" y1="18" x2="${x(0)}" y2="95" stroke="#888" stroke-dasharray="4 3" stroke-width="1"/>
    <text x="${x(0)}" y="14" text-anchor="middle" class="axis-label">0</text>
    <!-- CI 区间 -->
    <rect x="${x(lo)}" y="${yMid - barH / 2}" width="${Math.max(x(hi) - x(lo), 2)}" height="${barH}"
          rx="4" fill="${containsZero ? "rgba(220,60,60,.18)" : "rgba(40,160,90,.22)"}"
          stroke="${containsZero ? "#c44" : "#2a5" }" stroke-width="1"/>
    <!-- 点估计 -->
    <line x1="${x(mean)}" y1="${yMid - barH / 2 - 6}" x2="${x(mean)}" y2="${yMid + barH / 2 + 6}"
          stroke="#4a7dff" stroke-width="3" stroke-linecap="round"/>
    <!-- 标签 -->
    <text x="${x(lo)}" y="${yMid + barH + 16}" text-anchor="middle" class="axis-label">${fmt(lo)}</text>
    <text x="${x(hi)}" y="${yMid + barH + 16}" text-anchor="middle" class="axis-label">${fmt(hi)}</text>
    <text x="${x(mean)}" y="${yMid - barH / 2 - 12}" text-anchor="middle" class="pt-label">${fmt(mean)}</text>
    <!-- 结论 -->
    <text x="${W / 2}" y="${H - 12}" text-anchor="middle" class="verdict ${containsZero ? "neg" : "pos"}">
      ${containsZero ? "95% CI 包含 0 → IC 不显著" : "95% CI 不含 0 → IC 显著"}
    </text>
  </svg>`;
}

/* 年度 IC 柱状图（G11 数据，当前策略因子均在 G6 短路，无数据时降级） */
function yearlyIcSvg(yearly) {
  const entries = Object.entries(yearly || {}).map(([y, v]) => [y, Number(v)]).filter(([, v]) => isNum(v));
  if (!entries.length) return "";

  const W = 720, H = 200, PB = 30, PT = 20;
  const bw = (W - 20) / entries.length * 0.6;
  const step = (W - 20) / entries.length;
  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v)), 0.001) * 1.2;
  const yMid = PT + (H - PB - PT) / 2;
  const y = v => yMid - (v / maxAbs) * ((H - PB - PT) / 2 - 4);

  const bars = entries.map(([yr, v], i) => {
    const x0 = 10 + i * step + (step - bw) / 2;
    const y0 = y(v), h = Math.abs(yMid - y0);
    const pos = v >= 0;
    return `
    <rect x="${x0}" y="${Math.min(y0, yMid)}" width="${bw}" height="${h}" rx="2"
          fill="${pos ? "rgba(40,160,90,.75)" : "rgba(220,60,60,.75)"}"/>
    <text x="${x0 + bw / 2}" y="${H - 14}" text-anchor="middle" class="axis-label">${esc(yr)}</text>
    <text x="${x0 + bw / 2}" y="${pos ? y0 - 5 : y0 + 12}" text-anchor="middle" class="pt-label">${fmt(v, 3)}</text>`;
  }).join("");

  return `
  <svg viewBox="0 0 ${W} ${H}" class="ci-chart" role="img" aria-label="年度 Rank IC">
    <line x1="10" y1="${yMid}" x2="${W - 10}" y2="${yMid}" stroke="#888" stroke-width="1"/>
    ${bars}
  </svg>`;
}

function renderIcEvidence(s) {
  const ic = s.ic_summary || {};
  const rows = [
    ["Mean Rank IC（96 个月）", ic.mean_rank_ic],
    ["ICIR", ic.icir],
    ["Raw IC（未过滤）", ic.raw_ic],
    ["Alpha 衰减", ic.alpha_decay],
  ].filter(([, v]) => isNum(v));

  const table = rows.length ? `
    <table class="ic-table">
      ${rows.map(([k, v]) =>
        `<tr><td>${esc(k)}</td><td class="num ${Number(v) >= 0 ? "pos" : "neg"}">${fmt(v)}</td></tr>`).join("")}
    </table>` : "";

  const ci = ciChartSvg(ic.mean_rank_ic, ic.bootstrap_ci95);
  const yearly = yearlyIcSvg(s.factor_yearly_ic);

  if (!table && !ci && !yearly) {
    return `<div class="placeholder-note">该因子尚未运行 IC 验证（G5/G6 未执行），无 IC 证据可展示。</div>`;
  }
  return `${table}${ci ? `<p class="hint">G6 IC 稳定性 · Bootstrap 95% 置信区间（点估计为蓝线，CI 含 0 即不显著）：</p>${ci}` : ""}
          ${yearly ? `<p class="hint">G11 市场分段 · 年度 Rank IC：</p>${yearly}` : ""}`;
}

/* ═══════════ 共用小组件 ═══════════ */

function icCell(label, value) {
  const v = isNum(value) ? fmt(value) : "—";
  const cls = isNum(value) ? (Number(value) >= 0 ? "pos" : "neg") : "";
  return `<div class="ic-cell"><div class="iv ${cls}">${v}</div><div class="ik">${esc(label)}</div></div>`;
}

function gateDots(evidence) {
  if (!evidence) return `<span class="gd-label">验证未开始</span>`;
  const dots = evidence.gates.map(g =>
    `<span class="gate-dot ${g.passed ? "pass" : "fail"}" title="${esc(g.label)} ${g.passed ? "通过" : "失败："}${esc(g.reason || "")}"></span>`).join("");
  return `${dots}<span class="gd-label">${evidence.n_gates_passed}/${evidence.n_gates_run} 闸门通过</span>`;
}

/* ═══════════ 启动 ═══════════ */

$("back-btn").onclick = () => { if (history.length > 1) history.back(); else navigate(null); };
$("reload-btn").onclick = e => { e.preventDefault(); load(); };

bindFilterEvents();
load();
