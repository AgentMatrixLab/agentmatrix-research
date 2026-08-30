/* Zoo 五库因子验证面板 — 零构建前端 */
"use strict";

const API = "/api/agents/factor-lab/zoo";
const $ = (sel) => document.querySelector(sel);

const state = {
  overview: null,
  lib: null,
  factors: [],          // 当前库因子统计
  sortKey: "name",
  sortAsc: true,
  selectedFactor: null,
  tsInstruments: new Set(),  // 时序图选中的标的
  seriesCache: new Map(),    // `${lib}/${factor}` -> payload
  heatmapCache: new Map(),
  // 因子对比
  compare: [],              // [{lib, factor, instrument}]
  compareNorm: "raw",       // raw | zscore | minmax
  cmpSeriesCache: new Map(), // `${lib}/${factor}/${inst}` -> payload
  libFactorsCache: new Map(), // lib -> factor names
  instruments: [],          // 标的列表（首个 series 响应后填充）
};

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------
const fmt = (v, d = 4) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(d);
const fmtSci = (v) =>
  v === null || v === undefined || Number.isNaN(v) ? "—"
  : Math.abs(v) >= 1e5 || (Math.abs(v) < 1e-3 && v !== 0) ? v.toExponential(2)
  : Number(v).toFixed(4);

const PALETTE = ["#4f8cff", "#2ecc71", "#e6a23c", "#e05555", "#b07cff"];

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

function setStatus(msg) { $("#status-line").textContent = msg; }

// ---------------------------------------------------------------------------
// 1. 质量总览
// ---------------------------------------------------------------------------
function renderOverview() {
  const ov = state.overview;
  const m = ov.meta || {};
  const total = (ov.libraries || []).reduce((s, l) => s + l.n_factors, 0);
  const totalFail = (ov.libraries || []).reduce((s, l) => s + l.n_fail, 0);

  const cards = [
    { k: "因子总数", v: total },
    { k: "求值失败", v: totalFail, cls: totalFail ? "bad" : "good" },
    { k: "标的数", v: m.n_instruments },
    { k: "交易日数", v: m.n_days },
    { k: "随机种子", v: m.seed },
    { k: "确定性复跑", v: ov.determinism || "—", cls: ov.determinism === "PASS" ? "good" : "bad" },
    { k: "NaN 健壮性", v: ov.nan_robustness || "—", cls: ov.nan_robustness === "PASS" ? "good" : "bad" },
  ];
  $("#meta-cards").innerHTML = cards
    .map((c) => `<div class="card"><div class="k">${c.k}</div><div class="v ${c.cls || ""}">${c.v}</div></div>`)
    .join("");

  $("#meta-hint").textContent =
    `pandas ${m.pandas || "?"} / numpy ${m.numpy || "?"} · 耗时 ${m.elapsed_sec ?? "?"}s` +
    (ov.eq_fixed && ov.eq_fixed.length ? ` · 单等号笔误自动修复: ${ov.eq_fixed.join(", ")}` : "");

  // 每库卡片（点击切换库）
  $("#lib-cards").innerHTML = (ov.libraries || [])
    .map((l) => {
      const okCls = l.n_fail ? "bad" : "good";
      return `<div class="card lib-card ${l.name === state.lib ? "selected" : ""}" data-lib="${l.name}">
        <div class="lib-name">${l.name}</div>
        <div class="stats">
          <span>因子 <b>${l.n_factors}</b></span>
          <span>失败 <b class="${l.n_fail ? "bad" : "good"}">${l.n_fail}</b></span>
          <span>常数 <b>${l.n_constant}</b></span>
          <span>全NaN <b>${l.n_all_nan}</b></span>
          <span>${l.n_instruments} 标的 × ${l.n_days} 日</span>
        </div>
      </div>`;
    })
    .join("");
  document.querySelectorAll(".lib-card").forEach((el) =>
    el.addEventListener("click", () => selectLibrary(el.dataset.lib))
  );

  // 缺陷与对拍结论
  const defects = ov.zoo_defects || [];
  $("#defect-count").textContent = defects.length;
  const gt = (ov.ground_truth || [])
    .map((g) => `<span class="${g.status === "PASS" ? "pass" : "fail"}">${g.status === "PASS" ? "✓" : "✗"} ${g.lib}/${g.name}</span>`)
    .join(" · ");
  $("#defects-body").innerHTML =
    `<p class="gt-line">独立基准对拍: ${gt}</p>` +
    defects
      .map(
        (d) => `<div class="item"><b>${d.factor}</b> — ${d.issue}<br><span class="action">处理: ${d.action}</span></div>`
      )
      .join("");
}

// ---------------------------------------------------------------------------
// 2. 因子统计表
// ---------------------------------------------------------------------------
function factorIsProblem(f) {
  return f.constant || f.nan_ratio === null || f.nan_ratio > 0.5 || f.n_inf > 0;
}

function renderFactorTable() {
  const q = $("#factor-search").value.trim().toLowerCase();
  const onlyProblem = $("#only-problem").checked;
  let rows = state.factors.filter((f) => {
    if (onlyProblem && !factorIsProblem(f)) return false;
    if (!q) return true;
    return f.name.toLowerCase().includes(q);
  });
  const key = state.sortKey;
  rows = rows.slice().sort((a, b) => {
    let va = a[key], vb = b[key];
    if (key === "name") { va = String(va); vb = String(vb); }
    else { va = va === null || va === undefined ? -Infinity : va; vb = vb === null || vb === undefined ? -Infinity : vb; }
    const cmp = va > vb ? 1 : va < vb ? -1 : 0;
    return state.sortAsc ? cmp : -cmp;
  });

  const tbody = $("#factor-table tbody");
  tbody.innerHTML = rows
    .map(
      (f) => {
        const tip = (f.comments || "").replace(/"/g, "&quot;");
        return `<tr data-factor="${f.name}" class="${f.name === state.selectedFactor ? "selected" : ""}">
        <td${tip ? ` title="${tip}"` : ""}>${f.name}</td>
        <td class="num">${f.nan_ratio === null ? "—" : (f.nan_ratio * 100).toFixed(1)}</td>
        <td class="num">${f.n_inf ? `<span class="badge inf">${f.n_inf}</span>` : 0}</td>
        <td class="num">${fmtSci(f.min)}</td>
        <td class="num">${fmtSci(f.mean)}</td>
        <td class="num">${fmtSci(f.max)}</td>
        <td class="num">${fmtSci(f.std)}</td>
        <td>${f.constant ? '<span class="badge const">常数</span>' : '<span class="badge ok">OK</span>'}</td>
        <td><button class="cmp-add" data-factor="${f.name}" title="加入因子对比">+ 对比</button></td>
      </tr>`;
      }
    )
    .join("");
  $("#factor-count").textContent = `${rows.length} / ${state.factors.length} 个因子`;

  tbody.querySelectorAll("tr").forEach((tr) =>
    tr.addEventListener("click", () => selectFactor(tr.dataset.factor))
  );
  tbody.querySelectorAll(".cmp-add").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      addToCompare(state.lib, btn.dataset.factor);
    })
  );
}

async function loadFactors(lib) {
  const data = await fetchJSON(`${API}/libraries/${lib}/factors`);
  state.factors = data.factors;
  state.selectedFactor = null;
  renderFactorTable();
  // 同步时序/热力图下拉
  const opts = data.factors.map((f) => `<option value="${f.name}">${f.name}</option>`).join("");
  $("#ts-factor").innerHTML = opts;
  $("#hm-factor").innerHTML = opts;
}

async function selectLibrary(lib) {
  if (lib === state.lib) return;
  state.lib = lib;
  $("#lib-select").value = lib;
  setStatus(`加载 ${lib} 因子列表…`);
  await loadFactors(lib);
  renderOverview();
  // 默认选中第一个因子
  if (state.factors.length) selectFactor(state.factors[0].name);
  setStatus("");
}

async function selectFactor(name) {
  state.selectedFactor = name;
  $("#ts-factor").value = name;
  $("#hm-factor").value = name;
  renderFactorTable();
  await Promise.all([loadSeries(), loadHeatmap()]);
}

// ---------------------------------------------------------------------------
// 3. 因子值时间序列（原生 canvas 折线图）
// ---------------------------------------------------------------------------
async function loadSeries() {
  const factor = $("#ts-factor").value;
  if (!factor) return;
  const key = `${state.lib}/${factor}`;
  let data = state.seriesCache.get(key);
  if (!data) {
    data = await fetchJSON(`${API}/libraries/${state.lib}/series?factor=${encodeURIComponent(factor)}`);
    state.seriesCache.set(key, data);
  }
  // 首次拿到标的列表时，填充因子对比的标的下拉
  if (!state.instruments.length && data.instruments.length) {
    state.instruments = data.instruments;
    $("#cmp-inst").innerHTML = data.instruments
      .map((i) => `<option value="${i}">${i}</option>`)
      .join("");
  }
  // 标的标签（默认选前 3 只）
  const chips = $("#ts-instruments");
  if (!state.tsInstruments.size) {
    data.instruments.slice(0, 3).forEach((i) => state.tsInstruments.add(i));
  }
  chips.innerHTML = data.instruments
    .map(
      (inst, i) =>
        `<span class="chip ${state.tsInstruments.has(inst) ? "on" : ""}" data-inst="${inst}">
           <span style="color:${PALETTE[i % PALETTE.length]}">●</span> ${inst}
         </span>`
    )
    .join("");
  chips.querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      const inst = chip.dataset.inst;
      if (state.tsInstruments.has(inst)) {
        if (state.tsInstruments.size > 1) state.tsInstruments.delete(inst);
      } else if (state.tsInstruments.size < 5) {
        state.tsInstruments.add(inst);
      }
      chips.querySelectorAll(".chip").forEach((c) =>
        c.classList.toggle("on", state.tsInstruments.has(c.dataset.inst))
      );
      drawTimeSeries(data);
    })
  );
  drawTimeSeries(data);
}

function drawTimeSeries(data) {
  const canvas = $("#ts-chart");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.height / dpr * (dpr === 1 ? 1 : 1);
  canvas.width = W * dpr; canvas.height = 320 * dpr;
  canvas.style.height = "320px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, 320);

  const pad = { l: 64, r: 16, t: 16, b: 30 };
  const plotW = W - pad.l - pad.r, plotH = 320 - pad.t - pad.b;

  const active = [...state.tsInstruments].filter((i) => data.series[i]);
  let vmin = Infinity, vmax = -Infinity, vcount = 0;
  active.forEach((inst) => {
    data.series[inst].forEach((v) => {
      if (v !== null && isFinite(v)) { vmin = Math.min(vmin, v); vmax = Math.max(vmax, v); vcount++; }
    });
  });
  if (!vcount) { ctx.fillStyle = "#8b94a8"; ctx.fillText("无有效数据", pad.l, pad.t + 20); return; }
  if (vmax === vmin) { vmax += 1; vmin -= 1; }
  const padY = (vmax - vmin) * 0.05;
  vmin -= padY; vmax += padY;
  const n = data.dates.length;
  const x = (i) => pad.l + (i / Math.max(n - 1, 1)) * plotW;
  const y = (v) => pad.t + (1 - (v - vmin) / (vmax - vmin)) * plotH;

  // 网格 + y 轴刻度
  ctx.strokeStyle = "#2a2f3e"; ctx.fillStyle = "#8b94a8"; ctx.font = "11px Consolas";
  for (let g = 0; g <= 4; g++) {
    const vy = pad.t + (g / 4) * plotH;
    ctx.beginPath(); ctx.moveTo(pad.l, vy); ctx.lineTo(W - pad.r, vy); ctx.stroke();
    const val = vmax - (g / 4) * (vmax - vmin);
    ctx.fillText(fmtSci(val), 4, vy + 4);
  }
  // x 轴日期
  for (let g = 0; g <= 6; g++) {
    const i = Math.round((g / 6) * (n - 1));
    ctx.fillText(data.dates[i], x(i) - 32, 320 - 8);
  }
  // 折线
  data.instruments.forEach((inst, idx) => {
    if (!state.tsInstruments.has(inst)) return;
    const series = data.series[inst];
    const color = PALETTE[data.instruments.indexOf(inst) % PALETTE.length];
    ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.beginPath();
    let started = false;
    series.forEach((v, i) => {
      if (v === null || !isFinite(v)) { started = false; return; }
      const px = x(i), py = y(v);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
    });
    ctx.stroke();
  });
  // 标题
  ctx.fillStyle = "#dde3ee"; ctx.font = "12px 'Segoe UI'";
  ctx.fillText(`${state.lib} / ${data.factor} — ${active.join(", ")}`, pad.l, pad.t - 2);
}

// ---------------------------------------------------------------------------
// 3.5 因子对比（多因子时序叠加，支持归一化）
// ---------------------------------------------------------------------------
async function loadLibFactorNames(lib) {
  if (state.libFactorsCache.has(lib)) return state.libFactorsCache.get(lib);
  const data = await fetchJSON(`${API}/libraries/${lib}/factors`);
  const names = data.factors.map((f) => f.name);
  state.libFactorsCache.set(lib, names);
  return names;
}

async function fillCmpFactorOptions(lib) {
  const names = await loadLibFactorNames(lib);
  $("#cmp-factor").innerHTML = names
    .map((n) => `<option value="${n}">${n}</option>`)
    .join("");
}

function addToCompare(lib, factor, instrument) {
  const inst = instrument || $("#cmp-inst").value || "MOCK000";
  if (state.compare.length >= 8) {
    setStatus("对比最多叠加 8 条，请先移除部分因子");
    return;
  }
  const dup = state.compare.find(
    (c) => c.lib === lib && c.factor === factor && c.instrument === inst
  );
  if (dup) {
    setStatus(`${lib}/${factor}@${inst} 已在对比中`);
    return;
  }
  state.compare.push({ lib, factor, instrument: inst });
  renderCompareChips();
  refreshCompare();
}

function removeFromCompare(idx) {
  state.compare.splice(idx, 1);
  renderCompareChips();
  refreshCompare();
}

function renderCompareChips() {
  const box = $("#cmp-chips");
  if (!state.compare.length) {
    box.innerHTML = '<span class="hint">尚未添加对比因子</span>';
    return;
  }
  box.innerHTML = state.compare
    .map(
      (c, i) => `<span class="chip on">
        <span style="color:${PALETTE[i % PALETTE.length]}">●</span>
        ${c.lib}/${c.factor}@${c.instrument}
        <span class="chip-x" data-idx="${i}" title="移除">✕</span>
      </span>`
    )
    .join("");
  box.querySelectorAll(".chip-x").forEach((el) =>
    el.addEventListener("click", () => removeFromCompare(Number(el.dataset.idx)))
  );
}

function normalize(values, mode) {
  if (mode === "raw") return values;
  const valid = values.filter((v) => v !== null && isFinite(v));
  if (!valid.length) return values;
  if (mode === "zscore") {
    const mean = valid.reduce((s, v) => s + v, 0) / valid.length;
    const std = Math.sqrt(valid.reduce((s, v) => s + (v - mean) ** 2, 0) / valid.length) || 1;
    return values.map((v) => (v === null || !isFinite(v) ? null : (v - mean) / std));
  }
  // minmax
  const min = Math.min(...valid), max = Math.max(...valid);
  const span = max - min || 1;
  return values.map((v) => (v === null || !isFinite(v) ? null : (v - min) / span));
}

async function refreshCompare() {
  if (!state.compare.length) {
    const canvas = $("#cmp-chart");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }
  setStatus("加载对比因子…");
  const results = await Promise.all(
    state.compare.map(async (item) => {
      const key = `${item.lib}/${item.factor}/${item.instrument}`;
      let data = state.cmpSeriesCache.get(key);
      if (!data) {
        data = await fetchJSON(
          `${API}/libraries/${item.lib}/series?factor=${encodeURIComponent(item.factor)}&instrument=${encodeURIComponent(item.instrument)}`
        );
        state.cmpSeriesCache.set(key, data);
      }
      return {
        item,
        dates: data.dates,
        values: normalize(data.series[item.instrument] || [], state.compareNorm),
      };
    })
  );
  drawCompare(results);
  setStatus(`就绪 — ${state.lib}`);
}

function drawCompare(results) {
  const canvas = $("#cmp-chart");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = 360;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.height = H + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const pad = { l: 64, r: 16, t: 44, b: 30 };
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;

  let vmin = Infinity, vmax = -Infinity, vcount = 0;
  results.forEach((r) =>
    r.values.forEach((v) => {
      if (v !== null && isFinite(v)) { vmin = Math.min(vmin, v); vmax = Math.max(vmax, v); vcount++; }
    })
  );
  if (!vcount) {
    ctx.fillStyle = "#8b94a8"; ctx.font = "13px 'Segoe UI'";
    ctx.fillText("无有效数据", pad.l, pad.t + 20);
    return;
  }
  if (vmax === vmin) { vmax += 1; vmin -= 1; }
  const padY = (vmax - vmin) * 0.05;
  vmin -= padY; vmax += padY;

  const dates = results[0].dates;
  const n = dates.length;
  const x = (i) => pad.l + (i / Math.max(n - 1, 1)) * plotW;
  const y = (v) => pad.t + (1 - (v - vmin) / (vmax - vmin)) * plotH;

  // 网格 + y 轴刻度
  ctx.strokeStyle = "#2a2f3e"; ctx.fillStyle = "#8b94a8"; ctx.font = "11px Consolas";
  for (let g = 0; g <= 4; g++) {
    const vy = pad.t + (g / 4) * plotH;
    ctx.beginPath(); ctx.moveTo(pad.l, vy); ctx.lineTo(W - pad.r, vy); ctx.stroke();
    ctx.fillText(fmtSci(vmax - (g / 4) * (vmax - vmin)), 4, vy + 4);
  }
  for (let g = 0; g <= 6; g++) {
    const i = Math.round((g / 6) * (n - 1));
    ctx.fillText(dates[i], x(i) - 32, H - 8);
  }

  // 折线
  results.forEach((r, idx) => {
    const color = PALETTE[idx % PALETTE.length];
    ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.beginPath();
    let started = false;
    r.values.forEach((v, i) => {
      if (v === null || !isFinite(v)) { started = false; return; }
      const px = x(i), py = y(v);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
    });
    ctx.stroke();
  });

  // 图例（顶部横排）
  ctx.font = "11.5px 'Segoe UI'";
  let lx = pad.l;
  results.forEach((r, idx) => {
    const color = PALETTE[idx % PALETTE.length];
    ctx.fillStyle = color;
    ctx.fillRect(lx, 8, 10, 10);
    const label = `${r.item.lib}/${r.item.factor}@${r.item.instrument}`;
    ctx.fillStyle = "#dde3ee";
    ctx.fillText(label, lx + 14, 17);
    lx += 14 + ctx.measureText(label).width + 22;
    if (lx > W - 220 && idx < results.length - 1) { lx = pad.l; /* 简单换行省略 */ }
  });

  const normLabel = { raw: "原值", zscore: "z-score", minmax: "min-max" }[state.compareNorm];
  ctx.fillStyle = "#8b94a8";
  ctx.fillText(`归一化: ${normLabel}`, W - pad.r - 100, 17);
}


async function loadHeatmap() {
  const factor = $("#hm-factor").value;
  if (!factor) return;
  const key = `${state.lib}/${factor}`;
  let data = state.heatmapCache.get(key);
  if (!data) {
    data = await fetchJSON(`${API}/libraries/${state.lib}/heatmap?factor=${encodeURIComponent(factor)}`);
    state.heatmapCache.set(key, data);
  }
  drawHeatmap(data);
}

// 蓝-米-红色带
function heatColor(t) {
  const stops = [
    [106 / 255, 123 / 255, 162 / 255],
    [216 / 255, 201 / 255, 138 / 255],
    [192 / 255, 57 / 255, 43 / 255],
  ];
  const pos = t * (stops.length - 1);
  const i = Math.min(Math.floor(pos), stops.length - 2);
  const f = pos - i;
  const c = stops[i].map((v, k) => Math.round(v + f * (stops[i + 1][k] - v)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function drawHeatmap(data) {
  const canvas = $("#hm-canvas");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth;
  const H = 360;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.height = H + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const pad = { l: 70, r: 16, t: 26, b: 40 };
  const nD = data.dates.length, nI = data.instruments.length;
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
  const cw = plotW / nD, ch = plotH / nI;
  const span = data.vmax - data.vmin || 1;

  // 色块
  for (let i = 0; i < nI; i++) {
    for (let d = 0; d < nD; d++) {
      const v = data.matrix[d][i];   // matrix[日期][标的]
      ctx.fillStyle = v === null || !isFinite(v) ? "#3a3f4b" : heatColor((v - data.vmin) / span);
      ctx.fillRect(pad.l + d * cw, pad.t + i * ch, Math.ceil(cw), Math.ceil(ch));
    }
  }
  // 轴标注
  ctx.fillStyle = "#8b94a8"; ctx.font = "10px Consolas";
  for (let g = 0; g <= 6; g++) {
    const d = Math.round((g / 6) * (nD - 1));
    ctx.fillText(data.dates[d], pad.l + d * cw - 26, H - 22);
  }
  const stepI = Math.ceil(nI / 16);
  for (let i = 0; i < nI; i += stepI) {
    ctx.fillText(data.instruments[i], 6, pad.t + i * ch + ch);
  }
  // 标题 + 色带范围
  ctx.fillStyle = "#dde3ee"; ctx.font = "12px 'Segoe UI'";
  ctx.fillText(`${state.lib} / ${data.factor}`, pad.l, pad.t - 8);
  ctx.fillStyle = "#8b94a8"; ctx.font = "10px Consolas";
  ctx.fillText(`${fmtSci(data.vmin)}`, W - pad.r - 130, pad.t - 8);
  ctx.fillText(`→ ${fmtSci(data.vmax)}`, W - pad.r - 50, pad.t - 8);
}

// ---------------------------------------------------------------------------
// 事件绑定 & 启动
// ---------------------------------------------------------------------------
function bindEvents() {
  $("#reload-btn").addEventListener("click", () => location.reload());
  $("#lib-select").addEventListener("change", (e) => selectLibrary(e.target.value));
  $("#factor-search").addEventListener("input", renderFactorTable);
  $("#only-problem").addEventListener("change", renderFactorTable);
  $("#ts-factor").addEventListener("change", () => {
    state.tsInstruments.clear();
    state.seriesCache.clear();
    selectFactor($("#ts-factor").value);
  });
  $("#hm-factor").addEventListener("change", () => loadHeatmap());
  // 因子对比
  $("#cmp-lib").addEventListener("change", (e) => fillCmpFactorOptions(e.target.value));
  $("#cmp-add").addEventListener("click", () => {
    const lib = $("#cmp-lib").value;
    const factor = $("#cmp-factor").value;
    const inst = $("#cmp-inst").value;
    if (lib && factor) addToCompare(lib, factor, inst);
  });
  document.querySelectorAll('input[name="cmp-norm"]').forEach((radio) =>
    radio.addEventListener("change", () => {
      state.compareNorm = radio.value;
      refreshCompare();
    })
  );
  document.querySelectorAll("#factor-table th[data-sort]").forEach((th) =>
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (state.sortKey === k) state.sortAsc = !state.sortAsc;
      else { state.sortKey = k; state.sortAsc = true; }
      renderFactorTable();
    })
  );
  window.addEventListener("resize", () => {
    const key1 = `${state.lib}/${$("#ts-factor").value}`;
    const s = state.seriesCache.get(key1);
    if (s) drawTimeSeries(s);
    const h = state.heatmapCache.get(key1);
    if (h) drawHeatmap(h);
    if (state.compare.length) refreshCompare();
  });
}

async function init() {
  bindEvents();
  try {
    state.overview = await fetchJSON(`${API}/overview`);
    if (!state.overview.available) {
      setStatus("未找到 zoo mock 输出（runtime/zoo_mock/out/*.parquet）。请先运行 python -X utf8 runtime\\zoo_mock\\run_zoo_mock.py");
      return;
    }
    const libs = state.overview.libraries.map((l) => l.name);
    $("#lib-select").innerHTML = libs.map((l) => `<option value="${l}">${l}</option>`).join("");
    $("#cmp-lib").innerHTML = libs.map((l) => `<option value="${l}">${l}</option>`).join("");
    state.lib = libs.includes("GTJA191") ? "GTJA191" : libs[0];
    $("#lib-select").value = state.lib;
    $("#cmp-lib").value = state.lib;
    renderOverview();
    setStatus("");
    await loadFactors(state.lib);
    await fillCmpFactorOptions(state.lib);
    renderCompareChips();
    renderOverview();
    if (state.factors.length) await selectFactor(state.factors[0].name);
    // 默认对比示例：挑一个非常数因子展示（可自行增删/换库）
    const firstVar = state.factors.find((f) => !f.constant) || state.factors[0];
    if (firstVar) addToCompare(state.lib, firstVar.name);
    setStatus(`就绪 — ${state.lib}`);
  } catch (e) {
    setStatus(`加载失败: ${e.message}`);
    console.error(e);
  }
}

init();
