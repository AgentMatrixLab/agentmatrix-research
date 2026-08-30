/* 因子信任分级总面板 — 读取 /api/agents/factor-lab/trust/registry */
"use strict";

const API = "/api/agents/factor-lab/trust/registry";
const PAGE_SIZE = 50;

const state = {
  registry: null,
  tierFilter: new Set(),      // 空集 = 全部
  source: "",
  search: "",
  sortKey: "tier",
  sortAsc: true,
  page: 0,
};

const els = {};
["tier-cards", "tier-legend", "gen-hint", "sub-title", "tier-filter", "source-select",
 "factor-search", "trust-table", "factor-count", "page-info", "prev-page", "next-page",
 "reload-btn"].forEach(id => { els[id.replace(/-(\w)/g, (_, c) => c.toUpperCase())] = document.getElementById(id); });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function load() {
  try {
    const res = await fetch(API);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.registry = await res.json();
    render();
  } catch (err) {
    document.querySelector("main").innerHTML =
      `<section class="panel"><p>加载失败：${esc(err.message)}（后端 factor_lab_api 需在 8012 端口运行）</p></section>`;
  }
}

function tierColor(t) {
  return (state.registry.tier_definitions[t] || {}).color || "#8b949e";
}

function render() {
  renderTierCards();
  renderLegend();
  renderGateNote();
  renderSourceSelect();
  renderTable();
}

function renderTierCards() {
  const counts = state.registry.tier_counts;
  const defs = state.registry.tier_definitions;
  els.tierCards.innerHTML = state.registry.tier_order.map(t => {
    const d = defs[t] || {};
    const active = state.tierFilter.size === 0 || state.tierFilter.has(t) ? "" : "dim";
    const isActive = state.tierFilter.has(t);
    return `<div class="tier-card ${isActive ? "active" : ""}" data-tier="${t}"
        style="--tc:${d.color}">
      <div class="t-label">${t} · ${esc(d.label || "")}</div>
      <div class="t-count">${counts[t] ?? 0}</div>
      <div class="t-desc">${esc((d.desc || "").slice(0, 40))}…</div>
    </div>`;
  }).join("");
  els.tierCards.querySelectorAll(".tier-card").forEach(card => {
    card.addEventListener("click", () => {
      const t = card.dataset.tier;
      if (state.tierFilter.has(t)) {
        state.tierFilter.clear();          // 再次点击取消 → 全部
      } else {
        state.tierFilter.clear();
        state.tierFilter.add(t);           // 单选
      }
      state.page = 0;
      render();
    });
  });
  els.genHint.textContent = `生成于 ${state.registry.generated_at}（UTC）`;
  const m = state.registry.mock_meta || {};
  els.subTitle.textContent = `${Object.values(counts).reduce((a, b) => a + b, 0)} 因子 · mock ${m.n_instruments || "?"} 股 × ${m.n_days || "?"} 天 · 每个因子凭什么可信，如实标注`;
}

function renderLegend() {
  const defs = state.registry.tier_definitions;
  els.tierLegend.innerHTML = state.registry.tier_order.map(t => {
    const d = defs[t] || {};
    return `<div class="lg" style="--tc:${d.color}"><b>${t} — ${esc(d.label)}</b>${esc(d.desc)}</div>`;
  }).join("");
}

function renderGateNote() {
  const g = state.registry.verification_gates || {};
  if (g.gates_passed_max > 0) {
    document.getElementById("gates-panel").style.display = "none";
  }
}

function renderSourceSelect() {
  const sources = Object.keys(state.registry.by_source || {}).sort();
  const cur = state.source;
  els.sourceSelect.innerHTML =
    `<option value="">全部来源（${sources.length}）</option>` +
    sources.map(s => {
      const c = state.registry.by_source[s];
      const total = Object.values(c).reduce((a, b) => a + b, 0);
      return `<option value="${s}" ${s === cur ? "selected" : ""}>${s}（${total}）</option>`;
    }).join("");
}

function filtered() {
  let rows = state.registry.factors.slice();
  if (state.tierFilter.size) rows = rows.filter(f => state.tierFilter.has(f.tier));
  if (state.source) rows = rows.filter(f => f.source === state.source);
  if (state.search) {
    const n = state.search.toLowerCase();
    rows = rows.filter(f =>
      f.factor_id.toLowerCase().includes(n) ||
      (f.name_cn || "").toLowerCase().includes(n) ||
      (f.name_en || "").toLowerCase().includes(n));
  }
  const k = state.sortKey;
  const dir = state.sortAsc ? 1 : -1;
  rows.sort((a, b) => {
    const av = a[k] ?? "", bv = b[k] ?? "";
    return av < bv ? -dir : av > bv ? dir : 0;
  });
  return rows;
}

function renderTable() {
  const rows = filtered();
  const start = state.page * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);
  const tbody = els.trustTable.querySelector("tbody");
  const tOrder = state.registry.tier_order;
  const colors = {};
  state.registry.tier_order.forEach(t => { colors[t] = tierColor(t); });

  tbody.innerHTML = pageRows.map(f => {
    const ev = (f.evidence || []).map(e => {
      const [tag, ...rest] = String(e).split(": ");
      return `<div><code style="color:${evColor(tag)}">${esc(tag)}</code> ${esc(rest.join(": "))}</div>`;
    }).join("");
    const view = f.tier === "B"
      ? `<a href="http://127.0.0.1:8013/factor-db/" target="_blank">查值</a>`
      : `<span class="hint">${f.tier === "D" ? "—已淘汰" : "待验真"}</span>`;
    return `<tr>
      <td class="fid">${esc(f.factor_id)}</td>
      <td>${esc(f.name_cn || f.name_en || "")}</td>
      <td>${esc(f.source)}</td>
      <td><span class="badge" style="--tc:${colors[f.tier]}">${f.tier}</span></td>
      <td class="evidence">${ev || '<span class="hint">无证据记录</span>'}</td>
      <td>${view}</td>
    </tr>`;
  }).join("");

  els.trustTable.querySelectorAll("thead th[data-sort]").forEach(th => {
    th.onclick = () => {
      const k = th.dataset.sort;
      if (state.sortKey === k) state.sortAsc = !state.sortAsc;
      else { state.sortKey = k; state.sortAsc = k === "factor_id" || k === "name_cn"; }
      state.page = 0;
      renderTable();
    };
  });

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  els.pageInfo.textContent = `第 ${state.page + 1} / ${totalPages} 页`;
  els.prevPage.disabled = state.page === 0;
  els.nextPage.disabled = state.page >= totalPages - 1;
  els.factorCount.textContent = `匹配 ${rows.length} / ${state.registry.factors.length} 个因子`;
}

function evColor(tag) {
  if (tag.startsWith("real_data")) return "#3b82f6";
  if (tag.startsWith("mock_fail") || tag.startsWith("zoo_defect")) return "#ef4444";
  if (tag.startsWith("mock_constant")) return "#f59e0b";
  return "#8b949e";
}

/* 事件绑定 */
els.sourceSelect.addEventListener("change", e => {
  state.source = e.target.value;
  state.page = 0;
  renderTable();
});
els.factorSearch.addEventListener("input", e => {
  state.search = e.target.value.trim();
  state.page = 0;
  renderTable();
});
els.prevPage.addEventListener("click", () => { state.page = Math.max(0, state.page - 1); renderTable(); });
els.nextPage.addEventListener("click", () => { state.page += 1; renderTable(); });
els.reloadBtn.addEventListener("click", e => { e.preventDefault(); load(); });

load();
