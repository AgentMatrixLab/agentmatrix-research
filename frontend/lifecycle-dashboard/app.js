/* 因子生命周期监控面板 — 读取 /api/factor-db/lifecycle/* */
"use strict";

const API = "/api/factor-db/lifecycle";
const PIPELINE_ORDER = [
  "0_conceived", "1_implemented", "2_validated", "3_strategy_candidate",
  "4_live_ready", "6_published", "7_deprecated", "8_retired", "9_rejected",
];
const GATE_ORDER = [
  "g4_data_quality", "g5_executability", "g6_ic_stability", "g7_multiple_testing",
  "g8_oos_retention", "g9_cost_resilience", "g10_style_neutrality",
  "g11_market_segments", "g12_redundancy",
];

const state = { overview: null, factors: [], stateFilter: "", search: "" };
const els = {};
["pipeline", "pipeline-hint", "funnel-hint", "gate-funnel", "oos-list", "oos-max",
 "state-select", "factor-search", "factor-tbody", "factor-count", "evidence-feed",
 "drawer", "drawer-mask", "drawer-title", "drawer-sub", "drawer-body", "drawer-close",
 "reload-btn", "sub-title"].forEach(id => {
  els[id.replace(/-(\w)/g, (_, c) => c.toUpperCase())] = document.getElementById(id);
});

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function load() {
  try {
    const [ovRes, facRes, evRes] = await Promise.all([
      fetch(`${API}/overview`), fetch(`${API}/factors`), fetch(`${API}/evidence?limit=50`),
    ]);
    if (!ovRes.ok) {
      const err = await ovRes.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${ovRes.status}`);
    }
    state.overview = await ovRes.json();
    state.factors = (await facRes.json()).factors;
    const ev = await evRes.json();
    render(ev.events || []);
  } catch (err) {
    document.getElementById("main").innerHTML =
      `<section class="panel"><p>加载失败：${esc(err.message)}</p>
       <p class="hint">先运行 <code>python -X utf8 -m research_core.factor_db.g2_skeleton_run</code> 生成数据，再启动 <code>python -X utf8 -m research_core.factor_db.api</code></p></section>`;
  }
}

function render(evidence) {
  renderPipeline();
  renderFunnel();
  renderOos();
  renderStateSelect();
  renderTable();
  renderEvidenceFeed(evidence);
  els.subTitle.textContent =
    `${state.overview.total} 因子 · ${state.overview.validated} 成年 · ${state.overview.rejected} 死亡 · 预注册切分 ${state.overview.prereg_split || "—"}`;
}

/* ── 流水线 ── */
function renderPipeline() {
  const { state_counts, state_view } = state.overview;
  els.pipeline.innerHTML = PIPELINE_ORDER.map((s, i) => {
    const v = state_view[s] || {};
    const n = state_counts[s] || 0;
    const empty = n === 0 ? "empty" : "";
    const arrow = i < PIPELINE_ORDER.length - 1
      ? `<div class="pipe-arrow">→</div>` +
        (s === "1_implemented" || s === "2_validated" ? `<div class="pipe-arrow branch">↘</div>` : "")
      : "";
    return `
      <div class="pipe-stage ${empty}" style="--sc:${v.color}" title="${esc(v.desc)}">
        <div class="s-label">${esc(v.label)}</div>
        <div class="s-count">${n}</div>
        <div class="s-name">${esc(s.split("_")[1])}</div>
      </div>${arrow}`;
  }).join("");
  const dead = state_counts["9_rejected"] || 0;
  els.pipelineHint.textContent = `任意闸门失败即入死亡态（当前 ${dead} 个）· 点击状态过滤总表`;
  [...els.pipeline.children].forEach((el, idx) => {
    if (!el.classList.contains("pipe-stage")) return;
    const s = PIPELINE_ORDER[idx >= PIPELINE_ORDER.length ? 0 : 0] || null;
  });
  // 绑定过滤（pipe-stage 顺序与 PIPELINE_ORDER 一致，中间夹 arrow）
  const stages = [...els.pipeline.querySelectorAll(".pipe-stage")];
  stages.forEach((el, i) => {
    el.style.cursor = "pointer";
    el.onclick = () => {
      state.stateFilter = state.stateFilter === PIPELINE_ORDER[i] ? "" : PIPELINE_ORDER[i];
      renderStateSelect();
      renderTable();
    };
  });
}

/* ── 漏斗 ── */
function renderFunnel() {
  const funnel = state.overview.gate_funnel;
  const max = Math.max(1, ...funnel.map(f => f.deaths));
  els.gateFunnel.innerHTML = funnel.map(f => `
    <div class="funnel-row">
      <div class="funnel-label">${esc(f.label)}</div>
      <div class="funnel-bar-wrap"><div class="funnel-bar ${f.deaths ? "" : "zero"}" style="width:${(f.deaths / max * 100).toFixed(1)}%"></div></div>
      <div class="funnel-count ${f.deaths ? "" : "zero"}">${f.deaths}</div>
      <div class="funnel-desc">${esc(f.desc)}</div>
    </div>`).join("");
  const totalDeaths = funnel.reduce((a, f) => a + f.deaths, 0);
  els.funnelHint.innerHTML = `逐道短路（修正 C）· 共拦截 <b>${totalDeaths}</b> 个因子`;
}

/* ── OOS 封存 ── */
function renderOos() {
  const max = state.overview.max_oos_access || 3;
  els.oosMax.textContent = max;
  const used = state.factors.filter(f => f.oos_access_used > 0);
  if (!used.length) {
    els.oosList.innerHTML = `<p class="oos-none">尚无因子开封过封存 holdout</p>`;
    return;
  }
  els.oosList.innerHTML = used.map(f => {
    const dots = Array.from({ length: max }, (_, i) => {
      const cls = f.oos_access_used >= max ? "exhausted" : (i < f.oos_access_used ? "used" : "");
      return `<span class="oos-dot ${cls}"></span>`;
    }).join("");
    return `
      <div class="oos-row">
        <div class="oos-name" title="${esc(f.factor_id)}">${esc(f.factor_id)}</div>
        <div class="oos-dots">${dots}</div>
      </div>`;
  }).join("");
}

/* ── 状态过滤 ── */
function renderStateSelect() {
  const sv = state.overview.state_view;
  const opts = Object.keys(sv).map(s =>
    `<option value="${s}" ${state.stateFilter === s ? "selected" : ""}>${esc(sv[s].label)} · ${s}</option>`).join("");
  els.stateSelect.innerHTML = `<option value="">全部状态</option>${opts}`;
  els.stateSelect.onchange = () => { state.stateFilter = els.stateSelect.value; renderTable(); };
}

/* ── 总表 ── */
function renderTable() {
  const sv = state.overview.state_view;
  let rows = state.factors;
  if (state.stateFilter) rows = rows.filter(f => f.state === state.stateFilter);
  if (state.search) {
    const q = state.search.toLowerCase();
    rows = rows.filter(f => f.factor_id.toLowerCase().includes(q));
  }
  els.factorTbody.innerHTML = rows.map(f => {
    const v = sv[f.state] || { label: f.state, color: "#8b949e" };
    // 闸门格子：按固定顺序 pass/fail/skipped
    const passedSet = new Set(f.executed_order);
    const failGate = f.first_failure;
    const cells = GATE_ORDER.map(g => {
      if (g === failGate) return `<span class="gate-cell fail" title="${esc(g)} 拦截"></span>`;
      if (passedSet.has(g)) return `<span class="gate-cell pass" title="${esc(g)} 通过"></span>`;
      return `<span class="gate-cell skipped" title="未执行（短路）"></span>`;
    }).join("");
    const reason = f.first_failure
      ? `<span class="reason">${esc(f.first_failure)}</span>`
      : `<span class="reason na">—</span>`;
    const oos = f.oos_access_remaining;
    const oosCls = oos === 0 ? "zero" : (oos === 3 ? "full" : "");
    return `
      <tr data-fid="${esc(f.factor_id)}">
        <td>${esc(f.factor_id)}</td>
        <td><span class="state-badge" style="background:${v.color}">${esc(v.label)}</span></td>
        <td><span class="gate-progress">${cells}</span></td>
        <td>${reason}</td>
        <td><span class="oos-remain ${oosCls}">${oos}/${state.overview.max_oos_access}</span></td>
      </tr>`;
  }).join("");
  els.factorCount.textContent = `显示 ${rows.length} / ${state.factors.length} 个因子 · 点击行查看九道闸门证据`;
  [...els.factorTbody.querySelectorAll("tr")].forEach(tr => {
    tr.onclick = () => openDrawer(tr.dataset.fid);
  });
}

/* ── 证据链 ── */
function renderEvidenceFeed(events) {
  if (!events.length) {
    els.evidenceFeed.innerHTML = `<p class="oos-none">账本为空——尚无因子通过九道验真</p>`;
    return;
  }
  els.evidenceFeed.innerHTML = events.map(e => `
    <div class="ev-row">
      <span class="ev-time">${esc(e.timestamp)}</span>
      <span class="ev-transition">${esc(e.factor_id)} ${esc(e.transition)}</span>
      <span class="ev-meta">闸门 ${esc(e.gate)} · ${esc(e.approved_by)}</span>
    </div>`).join("");
}

/* ── 详情抽屉 ── */
async function openDrawer(fid) {
  try {
    const res = await fetch(`${API}/factors/${encodeURIComponent(fid)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    els.drawerTitle.textContent = fid;
    els.drawerSub.innerHTML =
      `状态 <b>${esc(d.state_label)}</b> · ${d.n_gates_passed}/${d.n_gates_run} 道通过` +
      (d.first_failure ? ` · 死因 <span class="reason">${esc(d.first_failure)}</span>` : "");
    const gates = d.gates.map(g => `
      <div class="gate-card ${g.passed ? "pass" : "fail"}">
        <div class="gc-head">
          <span class="gc-title">${esc(g.label)}</span>
          <span class="gc-status">${g.passed ? "PASS" : "FAIL"}</span>
        </div>
        <div class="gc-desc">${esc(g.desc)}</div>
        <pre>${esc(JSON.stringify(g.evidence, null, 2))}</pre>
        ${g.reason ? `<div class="gc-reason">${esc(g.reason)}</div>` : ""}
      </div>`).join("");
    const tl = (d.timeline || []).map(e => `
      <div class="ev-row">
        <span class="ev-time">${esc(e.timestamp)}</span>
        <span class="ev-transition">${esc(e.transition)}</span>
        <span class="ev-meta">闸门 ${esc(e.gate)} · ${esc(e.approved_by)}</span>
      </div>`).join("");
    els.drawerBody.innerHTML = gates + (tl ? `<h3 class="tl-title">证据链时间线</h3>${tl}` : "");
    els.drawer.classList.add("open");
    els.drawerMask.classList.add("open");
  } catch (err) {
    els.drawerBody.innerHTML = `<p>详情加载失败：${esc(err.message)}</p>`;
    els.drawer.classList.add("open");
    els.drawerMask.classList.add("open");
  }
}

function closeDrawer() {
  els.drawer.classList.remove("open");
  els.drawerMask.classList.remove("open");
}

els.drawerClose.onclick = closeDrawer;
els.drawerMask.onclick = closeDrawer;
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
els.reloadBtn.onclick = () => load();
let searchTimer = null;
els.factorSearch.oninput = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.search = els.factorSearch.value.trim(); renderTable(); }, 200);
};

load();
