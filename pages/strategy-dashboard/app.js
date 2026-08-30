/* 策略监控面板 — 读取 ./data/strategies.json（factor_lab_strategy_monitor_v1 契约）
 * 静态快照版：GitHub Pages 部署，无后端依赖。 */
"use strict";

const state = { doc: null };
const els = {};
["sub-title", "stats", "strategy-grid", "drawer", "drawer-mask",
 "drawer-title", "drawer-sub", "drawer-body", "drawer-close", "reload-btn"]
  .forEach(id => { els[id.replace(/-(\w)/g, (_, c) => c.toUpperCase())] = document.getElementById(id); });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
const fmt = (v, d = 4) => (v === null || v === undefined || Number.isNaN(Number(v))) ? "—" : Number(v).toFixed(d);

async function load() {
  try {
    const res = await fetch("./data/strategies.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.doc = await res.json();
    render();
  } catch (err) {
    document.getElementById("main").innerHTML =
      `<section class="panel"><p>加载失败：${esc(err.message)}</p>
       <p class="hint">先运行 <code>python pages/strategy-dashboard/generate_data.py</code> 生成数据。</p></section>`;
  }
}

function render() {
  const { strategies } = state.doc;
  renderStats(strategies);
  renderGrid(strategies);
  els.subTitle.textContent =
    `${strategies.length} 个单因子策略 · ${new Set(strategies.flatMap(s => s.factors)).size} 个基础因子 · 快照 ${state.doc.generated_at.slice(0, 10)}`;
}

function renderStats(strategies) {
  const ready = strategies.filter(s => s.status === "backtest_ready").length;
  const validating = strategies.filter(s => s.status === "review_needed").length;
  const pending = strategies.filter(s => s.status === "not_connected").length;
  const ics = strategies.map(s => s.ic_summary?.mean_rank_ic).filter(v => v !== null && v !== undefined);
  const bestAbsIc = ics.length ? Math.max(...ics.map(Math.abs)) : null;
  const cats = new Set(strategies.map(s => s.factor_meta.category));
  els.stats.innerHTML = `
    <div class="stat"><div class="v">${strategies.length}</div><div class="k">策略总数</div></div>
    <div class="stat"><div class="v">${ready}</div><div class="k">回测就绪</div></div>
    <div class="stat"><div class="v">${validating}</div><div class="k">研究验证中</div></div>
    <div class="stat"><div class="v">${pending}</div><div class="k">验证待启动</div></div>
    <div class="stat"><div class="v">${cats.size}</div><div class="k">因子类别覆盖</div></div>
    <div class="stat"><div class="v">${bestAbsIc === null ? "—" : fmt(bestAbsIc)}</div><div class="k">最大 |IC|（因子验证）</div></div>`;
}

function icCell(label, value, digits = 4) {
  const v = (value === null || value === undefined) ? "—" : fmt(value, digits);
  const cls = value === null || value === undefined ? "" : (value >= 0 ? "pos" : "neg");
  return `<div class="ic-cell"><div class="iv ${cls}">${v}</div><div class="ik">${label}</div></div>`;
}

function gateDots(evidence) {
  if (!evidence) return `<span class="gd-label">验证未开始</span>`;
  const dots = evidence.gates.map(g =>
    `<span class="gate-dot ${g.passed ? "pass" : "fail"}" title="${esc(g.label)} ${g.passed ? "通过" : "失败："}${esc(g.reason || "")}"></span>`).join("");
  return `${dots}<span class="gd-label">${evidence.n_gates_passed}/${evidence.n_gates_run} 闸门通过</span>`;
}

function renderGrid(strategies) {
  els.strategyGrid.innerHTML = strategies.map(s => {
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
    </div>`;
  }).join("");

  els.strategyGrid.querySelectorAll(".strategy-card").forEach(card => {
    card.onclick = () => openDrawer(card.dataset.sid);
  });
}

function kv(pairs) {
  return `<dl class="kv">${pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v ?? "—")}</dd>`).join("")}</dl>`;
}

function gateSection(evidence) {
  if (!evidence) {
    return `<div class="placeholder-note">该因子的验证数据尚未生成（因子值数据待阶段 1 拉取任务产出），策略停留在「验证待启动」状态。</div>`;
  }
  const items = evidence.gates.map(g => {
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
  return `
    <div class="d-section">
      <h3>因子验证闸门（${evidence.n_gates_passed}/${evidence.n_gates_run} 通过 · 生命周期状态：${esc(evidence.factor_state_label)}）</h3>
      ${items}
    </div>`;
}

function openDrawer(sid) {
  const s = state.doc.strategies.find(x => x.strategy_id === sid);
  if (!s) return;
  const m = s.factor_meta;
  els.drawerTitle.textContent = s.strategy_name;
  els.drawerSub.textContent = `${s.strategy_id} · ${s.strategy_type}`;

  els.drawerBody.innerHTML = `
    <div class="d-section">
      <h3>策略配置</h3>
      ${kv([
        ["策略类型", s.strategy_type],
        ["基础因子", m.factor_id],
        ["因子名称", `${m.name_cn}（${m.name_en}）`],
        ["因子分类", `${m.category} / ${m.subcategory} · ${m.frequency}`],
        ["股票池", s.universe],
        ["调仓频率", s.rebalance],
        ["持仓规则", s.holding_rule],
        ["成本模型", s.cost_model],
        ["策略依据", s.rationale],
      ])}
    </div>
    <div class="d-section">
      <h3>因子公式（伪代码）</h3>
      <div class="expr">${esc(m.formula_expr)}</div>
      <p class="hint" style="margin-top:8px">${esc(m.definition)}</p>
    </div>
    ${gateSection(s.factor_evidence)}
    <div class="d-section">
      <h3>回测指标（待接入）</h3>
      <div class="placeholder-note">
        策略回测尚未运行。接入 research_core/strategy_engine 后，此处将填充年化收益 / 夏普 / 最大回撤 / 换手率（strategy_monitor_view_v1 契约字段）。
      </div>
    </div>`;

  els.drawer.classList.add("open");
  els.drawerMask.classList.add("open");
}

function closeDrawer() {
  els.drawer.classList.remove("open");
  els.drawerMask.classList.remove("open");
}

els.drawerClose.onclick = closeDrawer;
els.drawerMask.onclick = closeDrawer;
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
els.reloadBtn.onclick = () => { closeDrawer(); load(); };

load();
