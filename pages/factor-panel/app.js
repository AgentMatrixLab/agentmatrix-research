/* Factor Console — renders pages/factor-panel/data/panel.json.
 *
 * Zero-build static page, same convention as the sibling dashboards.
 * It renders only what the generator measured; every panel that has no
 * production data yet says so instead of drawing a placeholder curve.
 */
(function () {
  "use strict";

  var STATE = {
    data: null,
    view: "funnel",
    page: 1,
    pageSize: 60,
    sortKey: "readiness",
    sortDir: "asc",
    filters: { q: "", source: "", tier: "", readiness: "", state: "" }
  };

  var READINESS_LABEL = {
    runnable_now: "现成可算",
    alias_only: "别名可算",
    needs_numerics: "缺算子",
    unparsable: "语法不通"
  };
  var READINESS_CLASS = {
    runnable_now: "ok",
    alias_only: "blue",
    needs_numerics: "warn",
    unparsable: "bad"
  };
  var STATUS_LABEL = {
    real: "真实产物",
    computed: "由仓库实测",
    not_run: "未运行",
    placeholder: "占位快照",
    not_implemented: "未实现"
  };

  // ── helpers ────────────────────────────────────────────────
  function el(id) { return document.getElementById(id); }

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function num(value) {
    if (typeof value !== "number" || !isFinite(value)) { return "—"; }
    return value.toLocaleString("zh-CN");
  }

  function pct(value) {
    if (typeof value !== "number" || !isFinite(value)) { return "—"; }
    return (value * 100).toFixed(1) + "%";
  }

  function emptyBox(text) {
    return '<div class="empty">' + esc(text) + "</div>";
  }

  // ── KPI strip ──────────────────────────────────────────────
  function renderKpis() {
    var d = STATE.data;
    var counts = d.catalog.readiness.counts;
    var del = d.delivery;
    var cards = [
      { k: "交付目标", v: num(del.target_factors), sub: "客户要求可用实盘因子数", cls: "is-target" },
      { k: "当前过闸", v: num(del.validated_factors), sub: "尚无真实运行产物", cls: "is-gap" },
      { k: "缺口", v: num(del.gap_to_target), sub: "距 " + del.deadline, cls: "is-gap" },
      { k: "因子目录", v: num(d.catalog.total), sub: "九源合一", cls: "" },
      { k: "引擎可算", v: num(d.catalog.readiness.runnable), sub: pct(d.catalog.readiness.runnable_ratio) + " 的目录", cls: "is-ok" },
      { k: "缺算子阻塞", v: num(counts.needs_numerics + counts.unparsable), sub: "需补实现或改语法", cls: "" }
    ];
    el("kpis").innerHTML = cards.map(function (c) {
      return '<div class="kpi ' + c.cls + '">' +
        '<div class="kpi-k">' + esc(c.k) + "</div>" +
        '<div class="kpi-v">' + c.v + "</div>" +
        '<div class="kpi-sub">' + esc(c.sub) + "</div></div>";
    }).join("");
  }

  // ── Funnel ─────────────────────────────────────────────────
  function renderFunnel() {
    var stages = STATE.data.funnel;
    var max = Math.max.apply(null, stages.map(function (s) { return s.count; }).concat([1]));
    el("funnel").innerHTML = stages.map(function (s) {
      var pctWidth = Math.max((s.count / max) * 100, s.count > 0 ? 3 : 1.5);
      return '<div class="fstage status-' + esc(s.status) + '">' +
        '<div class="fstage-label">' + esc(s.label) +
          ' <span class="badge ' + esc(s.status) + '">' + esc(STATUS_LABEL[s.status] || s.status) + "</span></div>" +
        '<div class="fstage-bar"><div class="fstage-fill" style="width:' + pctWidth.toFixed(2) + '%"></div></div>' +
        '<div class="fstage-count">' + num(s.count) + "</div>" +
        (s.detail ? '<div class="fstage-detail">' + esc(s.detail) + "</div>" : "") +
        '<div class="fstage-ev">证据 · ' + esc(s.evidence) + "</div>" +
        "</div>";
    }).join("");
  }

  function renderReadiness() {
    var c = STATE.data.catalog.readiness.counts;
    var total = STATE.data.catalog.readiness.total;
    var order = ["runnable_now", "alias_only", "needs_numerics", "unparsable"];
    var desc = {
      runnable_now: "表达式与现有算子完全对齐，可直接计算",
      alias_only: "只差算子别名映射（如 Ref→时序平移），无需新数值实现",
      needs_numerics: "引用了未实现的算子，需先补数值实现",
      unparsable: "语法不在当前文法内（如 WorldQuant 的 ?: 三元式）"
    };
    el("readiness").innerHTML = order.map(function (key) {
      return '<div class="rcard ' + READINESS_CLASS[key] + '">' +
        '<div class="rcard-v">' + num(c[key]) + "</div>" +
        '<div class="rcard-k">' + esc(READINESS_LABEL[key]) +
          " · " + pct(total ? c[key] / total : 0) + "</div>" +
        '<div class="rcard-d">' + esc(desc[key]) + "</div></div>";
    }).join("");
  }

  function renderBlockers() {
    var r = STATE.data.catalog.readiness;
    function rows(obj, label) {
      var entries = Object.keys(obj).map(function (k) { return [k, obj[k]]; });
      if (!entries.length) { return emptyBox("无 " + label + " 阻塞"); }
      return '<table class="dense"><thead><tr><th>' + esc(label) +
        '</th><th class="num">阻塞因子数</th></tr></thead><tbody>' +
        entries.slice(0, 24).map(function (e) {
          return "<tr><td class=\"mono\">" + esc(e[0]) +
            '</td><td class="num">' + num(e[1]) + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    el("op-blockers").innerHTML = rows(r.operator_blockers, "算子");
    el("field-blockers").innerHTML = rows(r.unknown_fields, "字段");
  }

  // ── Matrix ─────────────────────────────────────────────────
  function fillSelect(id, values, label) {
    var select = el(id);
    select.innerHTML = '<option value="">' + esc(label) + "（全部）</option>" +
      values.map(function (v) {
        return '<option value="' + esc(v) + '">' + esc(v) + "</option>";
      }).join("");
  }

  function uniqueSorted(list) {
    var seen = Object.create(null);
    list.forEach(function (v) { if (v) { seen[v] = true; } });
    return Object.keys(seen).sort();
  }

  function renderFilterOptions() {
    var factors = STATE.data.factors;
    fillSelect("f-source", uniqueSorted(factors.map(function (f) { return f.source; })), "来源");
    fillSelect("f-tier", uniqueSorted(factors.map(function (f) { return f.tier; })), "分层");

    var rd = el("f-readiness");
    rd.innerHTML = '<option value="">引擎可算（全部）</option>' +
      ["runnable_now", "alias_only", "needs_numerics", "unparsable"].map(function (k) {
        return '<option value="' + k + '">' + esc(READINESS_LABEL[k]) + "</option>";
      }).join("");

    var st = el("f-state");
    var states = STATE.data.lifecycle.states;
    st.innerHTML = '<option value="">状态（全部）</option>' +
      Object.keys(states).map(function (k) {
        return '<option value="' + esc(k) + '">' + esc(k + " " + (states[k].label || "")) + "</option>";
      }).join("");
  }

  function filtered() {
    var f = STATE.filters;
    var q = f.q.trim().toLowerCase();
    var rows = STATE.data.factors.filter(function (row) {
      if (f.source && row.source !== f.source) { return false; }
      if (f.tier && row.tier !== f.tier) { return false; }
      if (f.readiness && row.readiness !== f.readiness) { return false; }
      if (f.state && row.state !== f.state) { return false; }
      if (q) {
        var hay = (row.factor_id + " " + (row.name_cn || "") + " " +
                   (row.name_en || "") + " " + (row.formula_expr || "")).toLowerCase();
        if (hay.indexOf(q) === -1) { return false; }
      }
      return true;
    });

    var key = STATE.sortKey;
    var dir = STATE.sortDir === "asc" ? 1 : -1;
    var rank = { runnable_now: 0, alias_only: 1, needs_numerics: 2, unparsable: 3 };
    rows.sort(function (a, b) {
      var av = key === "readiness" ? rank[a.readiness] : a[key];
      var bv = key === "readiness" ? rank[b.readiness] : b[key];
      if (av === bv) { return a.factor_id < b.factor_id ? -1 : 1; }
      if (av === undefined || av === null) { return 1; }
      if (bv === undefined || bv === null) { return -1; }
      return av < bv ? -dir : dir;
    });
    return rows;
  }

  function renderMatrix() {
    var rows = filtered();
    var total = rows.length;
    var pages = Math.max(Math.ceil(total / STATE.pageSize), 1);
    if (STATE.page > pages) { STATE.page = pages; }
    var start = (STATE.page - 1) * STATE.pageSize;
    var slice = rows.slice(start, start + STATE.pageSize);
    var states = STATE.data.lifecycle.states;

    el("matrix-meta").textContent =
      "匹配 " + num(total) + " / " + num(STATE.data.factors.length) + " 个因子" +
      "　·　引擎可算 " + num(rows.filter(function (r) {
        return r.readiness === "runnable_now" || r.readiness === "alias_only";
      }).length);

    el("matrix-body").innerHTML = slice.length ? slice.map(function (row) {
      var blockers = [];
      if (row.blocking_operators && row.blocking_operators.length) {
        blockers.push(row.blocking_operators.slice(0, 3).join(", "));
      }
      if (row.missing_fields && row.missing_fields.length) {
        blockers.push("字段 " + row.missing_fields.slice(0, 2).join(", "));
      }
      if (row.parse_error) { blockers.push("语法"); }
      var stateLabel = (row.state_label || (states[row.state] && states[row.state].label) || "");
      return '<tr data-fid="' + esc(row.factor_id) + '">' +
        '<td><div class="fid">' + esc(row.factor_id) + "</div>" +
          '<div style="color:var(--fg-dim);font-size:11.5px">' + esc(row.name_cn || "") + "</div></td>" +
        "<td>" + esc(row.source) + "</td>" +
        "<td>" + esc(row.category || "") + "</td>" +
        '<td><span class="pill tier-' + esc(row.tier || "") + '">' + esc(row.tier || "—") + "</span></td>" +
        '<td><span class="pill rd-' + esc(row.readiness) + '">' +
          esc(READINESS_LABEL[row.readiness] || row.readiness) + "</span></td>" +
        '<td><span class="pill st">' + esc(row.state.split("_")[0] + " " + stateLabel) + "</span></td>" +
        '<td style="color:var(--fg-dim);font-size:11.5px">' +
          esc(blockers.join(" · ") || "—") + "</td></tr>";
    }).join("") : '<tr><td colspan="7">' + emptyBox("没有匹配的因子") + "</td></tr>";

    var buttons = [];
    buttons.push('<span class="pg-info">第 ' + STATE.page + " / " + pages + " 页</span>");
    buttons.push('<button data-pg="1"' + (STATE.page === 1 ? " disabled" : "") + ">首页</button>");
    buttons.push('<button data-pg="' + (STATE.page - 1) + '"' + (STATE.page === 1 ? " disabled" : "") + ">上一页</button>");
    buttons.push('<button data-pg="' + (STATE.page + 1) + '"' + (STATE.page === pages ? " disabled" : "") + ">下一页</button>");
    buttons.push('<button data-pg="' + pages + '"' + (STATE.page === pages ? " disabled" : "") + ">末页</button>");
    el("pager").innerHTML = buttons.join("");
  }

  // ── Lifecycle ──────────────────────────────────────────────
  function renderStates() {
    var states = STATE.data.lifecycle.states;
    var counts = STATE.data.lifecycle.state_counts;
    el("states").innerHTML = Object.keys(states).map(function (key) {
      var s = states[key];
      var n = counts[key] || 0;
      return '<div class="state' + (n === 0 ? " is-empty" : "") + '" style="border-left-color:' + esc(s.color) + '">' +
        '<div class="state-n" style="color:' + esc(s.color) + '">' + num(n) + "</div>" +
        '<div class="state-l">' + esc(key) + " " + esc(s.label || "") + "</div>" +
        '<div class="state-d">' + esc(s.desc || "") + "</div></div>";
    }).join("");
  }

  function renderTransitions() {
    var rows = STATE.data.lifecycle.transitions || [];
    if (!rows.length) { el("transitions").innerHTML = emptyBox("无迁移规则"); return; }
    el("transitions").innerHTML =
      '<thead><tr><th>从</th><th>到</th><th>闸门</th><th>批准方</th></tr></thead><tbody>' +
      rows.map(function (t) {
        return "<tr><td class=\"mono\">" + esc(t.from) + "</td>" +
          "<td class=\"mono\">" + esc(t.to) + "</td>" +
          "<td class=\"mono\">" + esc(t.gate) + "</td>" +
          "<td>" + esc(t.approver) + "</td></tr>";
      }).join("") + "</tbody>";
  }

  function renderEvents() {
    var events = STATE.data.lifecycle.events || [];
    if (!events.length) {
      el("events").innerHTML = emptyBox(
        "暂无事件。事件流会在真实验证运行产出后自动填充 —— 不预置演示事件。"
      );
      return;
    }
    el("events").innerHTML = events.slice(0, 200).map(function (e) {
      var at = e.timestamp || e.at || "";
      var transition = e.transition || e.to || e.event || "";
      var gate = e.gate || "";
      var approver = e.approved_by || e.approver || "";
      var bits = [];
      if (gate) { bits.push("闸门 " + gate); }
      if (approver) { bits.push("批准 " + approver); }
      if (typeof e.oos_access_remaining === "number") {
        bits.push("OOS 剩余 " + e.oos_access_remaining);
      }
      return '<div class="event">' +
        '<div class="event-t">' + esc(String(at).replace("T", " ").slice(0, 19)) + "</div>" +
        '<div class="event-f">' + esc(e.factor_id || "") + "</div>" +
        "<div><strong>" + esc(transition) + "</strong>" +
          (bits.length
            ? '<div style="color:var(--fg-faint);font-size:11.5px;margin-top:2px">' +
              esc(bits.join("　·　")) + "</div>"
            : "") +
        "</div></div>";
    }).join("");
  }

  // ── Gates ──────────────────────────────────────────────────
  function renderGates() {
    var g = STATE.data.gates;
    if (!g || !g.available) {
      el("gates").innerHTML = emptyBox("未找到 configs/validation_gates.yaml");
      el("gate-meta").innerHTML = "";
      return;
    }
    el("gates").innerHTML = g.rows.map(function (row, i) {
      var lines = Object.keys(row.thresholds).map(function (k) {
        return "<div>" + esc(k) + " = " + esc(JSON.stringify(row.thresholds[k])) + "</div>";
      }).join("");
      return '<div class="gate"><div class="gate-i">闸门 ' + (i + 1) + "</div>" +
        '<div class="gate-n">' + esc(row.gate) + "</div>" +
        '<div class="gate-t">' + (lines || "<div>—</div>") + "</div></div>";
    }).join("");

    var split = g.split || {};
    var cost = g.cost || {};
    var meta = [
      ["训练期", split.train_start + " → " + split.train_end],
      ["样本外期", split.oos_start + " → " + split.oos_end],
      ["预测期（主）", (g.primary_horizon || "—") + " 日 ｜ 全部 " + JSON.stringify(g.forward_horizons || [])],
      ["风格暴露", JSON.stringify(g.styles || [])],
      ["成本（往返）", String(cost.round_trip_total)],
      ["佣金 / 印花税 / 冲击", cost.commission_per_side + " / " + cost.stamp_tax_sell + " / " + cost.impact_per_side],
      ["发布模式", JSON.stringify(g.release || {})]
    ];
    el("gate-meta").innerHTML = meta.map(function (m) {
      return '<div class="gm"><div class="gm-k">' + esc(m[0]) + "</div>" +
        '<div class="gm-v">' + esc(m[1]) + "</div></div>";
    }).join("");
  }

  // ── Live ───────────────────────────────────────────────────
  function renderStrategies() {
    var s = STATE.data.strategies;
    if (!s.rows.length) { el("strategies").innerHTML = emptyBox("策略台账为空"); return; }
    el("strategies").innerHTML = s.rows.map(function (row) {
      return '<div class="st-card"><div class="st-id">' + esc(row.strategy_id || row.id) + "</div>" +
        '<div class="st-st"><span class="badge placeholder">' + esc(row.status || "unknown") + "</span></div>" +
        (row.name ? '<div style="margin-top:6px;font-size:12.3px">' + esc(row.name) + "</div>" : "") +
        "</div>";
    }).join("");
  }

  function renderPipeline() {
    var steps = [
      { n: "1", name: "因子值快照", d: "RQData 全 A 面板 + 因子长表，Parquet + sidecar 校验", s: "not_run" },
      { n: "2", name: "验证与打分", d: "八道门槛 + 综合分与分层", s: "not_run" },
      { n: "3", name: "策略合成", d: "因子加权 → 目标持仓 → 回测", s: "placeholder" },
      { n: "4", name: "每日信号文件", d: "T-1 收盘后生成，供文件单 / 条件单直接导入", s: "not_run" },
      { n: "5", name: "Supabase 信号表", d: "本地 QMT / 掘金量化读取同一份信号", s: "not_run" },
      { n: "6", name: "成交回传对账", d: "实际成交 vs 目标信号，输出偏差报告", s: "not_run" }
    ];
    el("pipeline").innerHTML = steps.map(function (s) {
      return '<div class="pipe' + (s.s === "not_run" ? "" : " n") + '">' +
        '<div class="pipe-step">STEP ' + esc(s.n) + "</div>" +
        '<div class="pipe-name">' + esc(s.name) + "</div>" +
        '<div class="pipe-d">' + esc(s.d) + "</div>" +
        '<div class="pipe-s"><span class="badge ' + esc(s.s) + '">' +
          esc(STATUS_LABEL[s.s] || s.s) + "</span></div></div>";
    }).join("");
  }

  // ── Drawer ─────────────────────────────────────────────────
  function openDrawer(factorId) {
    var row = STATE.data.factors.filter(function (f) { return f.factor_id === factorId; })[0];
    if (!row) { return; }
    var states = STATE.data.lifecycle.states;
    var st = states[row.state] || {};
    var chips = function (list, cls) {
      if (!list || !list.length) { return '<span style="color:var(--fg-faint)">—</span>'; }
      return list.map(function (v) {
        return '<span class="chip ' + (cls || "") + '">' + esc(v) + "</span>";
      }).join("");
    };

    el("drawer-body").innerHTML =
      '<h2 class="dw-h">' + esc(row.name_cn || row.factor_id) + "</h2>" +
      '<div class="dw-id">' + esc(row.factor_id) + "</div>" +
      '<div class="dw-sub">' + esc(row.name_en || "") + "</div>" +

      '<div class="dw-sec"><h3>交付状态</h3><dl class="dw-kv">' +
        "<dt>引擎可算</dt><dd><span class=\"pill rd-" + esc(row.readiness) + '">' +
          esc(READINESS_LABEL[row.readiness]) + "</span></dd>" +
        "<dt>生命周期</dt><dd>" + esc(row.state + " " + (st.label || "")) + "</dd>" +
        "<dt>信任分层</dt><dd><span class=\"pill tier-" + esc(row.tier || "") + '">' +
          esc(row.tier || "—") + "</span></dd>" +
        "<dt>是否入监控</dt><dd>" + (row.monitored ? "是" : "否（仅目录登记）") + "</dd>" +
      "</dl></div>" +

      '<div class="dw-sec"><h3>公式</h3><div class="dw-code">' +
        esc(row.formula_expr || "—") + "</div></div>" +

      '<div class="dw-sec"><h3>阻塞项</h3>' +
        "<div style=\"font-size:12px;color:var(--fg-faint);margin-bottom:5px\">缺失算子</div>" +
        chips(row.blocking_operators, "bad") +
        "<div style=\"font-size:12px;color:var(--fg-faint);margin:8px 0 5px\">缺失字段</div>" +
        chips(row.missing_fields, "bad") +
        "<div style=\"font-size:12px;color:var(--fg-faint);margin:8px 0 5px\">可用别名</div>" +
        chips(row.aliased_operators, "good") +
      "</div>" +

      (row.parse_error
        ? '<div class="dw-sec"><h3>解析错误</h3><div class="dw-code">' + esc(row.parse_error) + "</div></div>"
        : "") +

      '<div class="dw-sec"><h3>台账</h3><dl class="dw-kv">' +
        "<dt>来源</dt><dd>" + esc(row.source) + "</dd>" +
        "<dt>大类</dt><dd>" + esc(row.category || "—") + "</dd>" +
        "<dt>子类</dt><dd>" + esc(row.subcategory || "—") + "</dd>" +
        "<dt>频率</dt><dd>" + esc(row.frequency || "—") + "</dd>" +
        "<dt>数据起点</dt><dd>" + esc(row.history_start || "—") + "</dd>" +
      "</dl></div>" +

      (row.definition
        ? '<div class="dw-sec"><h3>定义</h3><div style="font-size:12.5px;color:var(--fg-dim)">' +
          esc(row.definition) + "</div></div>"
        : "") +

      (row.gates
        ? '<div class="dw-sec"><h3>门槛实测</h3><dl class="dw-kv">' +
          "<dt>全过</dt><dd>" + esc(String(row.gates.passed_all)) + "</dd>" +
          "<dt>首败门槛</dt><dd>" + esc(row.gates.first_failure || "—") + "</dd>" +
          "<dt>通过 / 执行</dt><dd>" + esc(row.gates.n_gates_passed + " / " + row.gates.n_gates_run) + "</dd>" +
          "</dl></div>"
        : '<div class="dw-sec"><h3>门槛实测</h3><div style="font-size:12.5px;color:var(--fg-faint)">' +
          "该因子尚未进入验证流水线，无门槛结果。</div></div>");

    el("drawer").classList.add("is-open");
    el("drawer").setAttribute("aria-hidden", "false");
    el("scrim").hidden = false;
  }

  function closeDrawer() {
    el("drawer").classList.remove("is-open");
    el("drawer").setAttribute("aria-hidden", "true");
    el("scrim").hidden = true;
  }

  // ── Wiring ─────────────────────────────────────────────────
  function switchView(name) {
    STATE.view = name;
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
      t.classList.toggle("is-active", t.getAttribute("data-view") === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".view"), function (v) {
      v.classList.toggle("is-active", v.id === "view-" + name);
    });
    if (window.location.hash !== "#" + name) {
      window.history.replaceState(null, "", "#" + name);
    }
  }

  function viewFromHash() {
    var name = (window.location.hash || "").replace(/^#/, "");
    var known = ["funnel", "matrix", "lifecycle", "gates", "live"];
    return known.indexOf(name) === -1 ? "funnel" : name;
  }

  function bind() {
    el("tabs").addEventListener("click", function (ev) {
      var t = ev.target.closest(".tab");
      if (t) { switchView(t.getAttribute("data-view")); }
    });

    el("q").addEventListener("input", function (ev) {
      STATE.filters.q = ev.target.value; STATE.page = 1; renderMatrix();
    });
    ["source", "tier", "readiness", "state"].forEach(function (key) {
      el("f-" + key).addEventListener("change", function (ev) {
        STATE.filters[key] = ev.target.value; STATE.page = 1; renderMatrix();
      });
    });
    el("f-reset").addEventListener("click", function () {
      STATE.filters = { q: "", source: "", tier: "", readiness: "", state: "" };
      el("q").value = "";
      ["source", "tier", "readiness", "state"].forEach(function (k) { el("f-" + k).value = ""; });
      STATE.page = 1; renderMatrix();
    });

    document.querySelectorAll("table.matrix thead .sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-key");
        if (STATE.sortKey === key) {
          STATE.sortDir = STATE.sortDir === "asc" ? "desc" : "asc";
        } else {
          STATE.sortKey = key; STATE.sortDir = "asc";
        }
        document.querySelectorAll("table.matrix thead .sortable").forEach(function (o) {
          o.classList.remove("asc", "desc");
        });
        th.classList.add(STATE.sortDir);
        STATE.page = 1; renderMatrix();
      });
    });

    el("matrix-body").addEventListener("click", function (ev) {
      var tr = ev.target.closest("tr[data-fid]");
      if (tr) { openDrawer(tr.getAttribute("data-fid")); }
    });

    el("pager").addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-pg]");
      if (!b || b.disabled) { return; }
      STATE.page = parseInt(b.getAttribute("data-pg"), 10);
      renderMatrix();
      document.querySelector(".table-wrap").scrollTop = 0;
    });

    el("drawer-close").addEventListener("click", closeDrawer);
    el("scrim").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { closeDrawer(); }
    });
    window.addEventListener("hashchange", function () {
      switchView(viewFromHash());
    });
  }

  // ── Boot ───────────────────────────────────────────────────
  function boot() {
    fetch("data/panel.json", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      })
      .then(function (data) {
        STATE.data = data;

        el("m-commit").textContent = data.code_commit;
        el("m-generated").textContent = (data.generated_at || "").replace("T", " ").slice(0, 16);
        el("m-countdown").textContent = "D-" + Math.max(data.delivery.days_remaining, 0).toFixed(1);

        el("honesty").innerHTML =
          "<strong>数据口径：</strong>" + esc(data.honesty.statement) +
          " 已发现真实验证运行产物 <strong>" + data.honesty.validation_runs_found + "</strong> 份。" +
          " 目录快照模式：" + esc(data.honesty.catalog_mode || "—") + "。";

        el("foot-note").textContent =
          "生成器 " + data.generator + " · commit " + data.code_commit +
          " · schema v" + data.schema_version;

        renderKpis();
        renderFunnel();
        renderReadiness();
        renderBlockers();
        renderFilterOptions();
        renderMatrix();
        renderStates();
        renderTransitions();
        renderEvents();
        renderGates();
        renderStrategies();
        renderPipeline();
        bind();
        switchView(viewFromHash());
      })
      .catch(function (err) {
        el("main").innerHTML = '<div class="panel"><div class="callout warn">' +
          "<strong>无法加载 panel.json。</strong> " + esc(String(err)) +
          "<br><br>请在仓库根目录运行：<code>python -X utf8 scripts/build_factor_panel.py</code>" +
          "，并通过本地服务器打开本页（<code>file://</code> 下的 fetch 会被浏览器拦截）。" +
          "</div></div>";
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
