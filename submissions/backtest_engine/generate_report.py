"""
生成回测报告HTML — 类似聚宽的净值曲线 + 指标面板
"""
import os, sys, json, glob, argparse
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import RESULTS_DIR


def load_latest_results():
    dirs = sorted(glob.glob(os.path.join(RESULTS_DIR, "20*")))
    if not dirs:
        print("没有找到结果目录")
        return None
    return dirs[-1]


def compute_metrics_from_nav(nav_df, name="策略"):
    if len(nav_df) < 2:
        return {}
    daily_ret = nav_df['nav'].pct_change().dropna()
    n_days = len(daily_ret)
    n_years = n_days / 252
    total_ret = nav_df['nav'].iloc[-1] / nav_df['nav'].iloc[0] - 1
    ann_ret = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0
    ann_vol = daily_ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    cummax = nav_df['nav'].cummax()
    dd = nav_df['nav'] / cummax - 1
    mdd = dd.min()
    calmar = ann_ret / abs(mdd) if mdd < 0 else float('inf')
    win_rate = (daily_ret > 0).mean()
    return {
        'name': name,
        'total_return': f"{total_ret:.2%}",
        'annual_return': f"{ann_ret:.2%}",
        'annual_vol': f"{ann_vol:.2%}",
        'sharpe': f"{sharpe:.2f}",
        'max_drawdown': f"{mdd:.2%}",
        'calmar': f"{calmar:.2f}",
        'win_rate': f"{win_rate:.2%}",
        'days': n_days, 'total_ret_val': round(total_ret, 4),
        'ann_ret_val': round(ann_ret, 4), 'ann_vol_val': round(ann_vol, 4),
        'sharpe_val': round(sharpe, 4), 'mdd_val': round(mdd, 4),
    }


def generate_html(result_dir):
    nav_files = sorted(glob.glob(os.path.join(result_dir, "*_nav.csv")))
    if not nav_files:
        print("没有净值文件"); return

    strategies = []
    for nf in nav_files:
        name = os.path.basename(nf).replace("_nav.csv", "")
        # 跳过不含 date 列的旧格式文件
        peek = pd.read_csv(nf, nrows=0)
        if 'date' not in peek.columns:
            print(f"  ⚠️ {nf}: 缺少date列, 跳过"); continue
        if 'nav' not in peek.columns:
            print(f"  ⚠️ {nf}: 缺少nav列, 跳过"); continue

        df = pd.read_csv(nf, parse_dates=['date'])
        df = df.set_index('date')
        m = compute_metrics_from_nav(df, name)
        nav_series = (df['nav'] / df['nav'].iloc[0]).round(4).tolist()
        m['nav_series'] = nav_series
        if 'benchmark' in df.columns:
            m['bench_series'] = (df['benchmark'] / df['benchmark'].iloc[0]).round(4).tolist()
        strategies.append(m)

    # 从第一个文件提取日期
    ddf = pd.read_csv(nav_files[0])
    date_col = 'date' if 'date' in ddf.columns else ddf.columns[0]
    dates = list(pd.to_datetime(ddf[date_col]).dt.strftime('%Y-%m-%d'))

    strategies_json = json.dumps(strategies, ensure_ascii=False)
    dates_json = json.dumps(dates)

    # HTML前端 (用 %% 占位, 之后替换)
    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>多策略回测报告</title>
<!-- <meta http-equiv="refresh" content="300"> -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#0d1117; color:#c9d1d9; padding:20px; }
.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
.header h1 { font-size:24px; color:#f0f6fc; }
.header .date { color:#8b949e; font-size:14px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:24px; }
.card { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; }
.card .lbl { font-size:12px; color:#8b949e; margin-bottom:4px; }
.card .val { font-size:22px; font-weight:600; }
.chart-box { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:20px; margin-bottom:24px; }
.chart-box h3 { font-size:16px; margin-bottom:12px; color:#f0f6fc; }
.chart-wrap { position:relative; height:350px; }
table { width:100%; border-collapse:collapse; background:#161b22; border-radius:8px; overflow:hidden; }
th { background:#21262d; color:#8b949e; font-weight:500; font-size:12px; padding:12px 16px; text-align:right; }
th:first-child { text-align:left; }
td { padding:12px 16px; text-align:right; border-top:1px solid #21262d; font-size:14px; }
td:first-child { text-align:left; font-weight:500; color:#f0f6fc; }
tr:hover td { background:#1c2128; }
.green { color:#3fb950; }
.red { color:#f85149; }
.legend { display:flex; flex-wrap:wrap; gap:16px; margin-bottom:12px; }
.legend-item { display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer; }
.legend-dot { width:12px; height:12px; border-radius:3px; }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>📊 多策略回测报告</h1>
    <div class="date" id="reportDate"></div>
  </div>
</div>

<div class="cards" id="summaryCards"></div>

<div class="chart-box">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
    <h3>累计净值曲线</h3>
    <div class="legend" id="chartLegend"></div>
  </div>
  <div class="chart-wrap"><canvas id="navChart"></canvas></div>
</div>

<div class="chart-box">
  <h3>回撤曲线</h3>
  <div class="chart-wrap"><canvas id="ddChart"></canvas></div>
</div>

<div class="chart-box">
  <h3>绩效指标对比</h3>
  <table>
    <thead><tr id="metricsHeader"></tr></thead>
    <tbody id="metricsBody"></tbody>
  </table>
</div>

<script>
const DATA = __DATA__;
const DATES = __DATES__;
const COLORS = ['#3fb950','#58a6ff','#d29922','#f85149','#bc8cff','#f0883e','#79c0ff','#ff7b72'];
const COLORS_RGB = ['rgba(63,185,80,','rgba(88,166,255,','rgba(210,153,34,','rgba(248,81,73,','rgba(188,140,255,','rgba(240,136,62,','rgba(121,192,255,','rgba(255,123,114,'];

document.getElementById('reportDate').textContent = DATES[0]+' ~ '+DATES[DATES.length-1]+'  (共'+DATES.length+'个交易日)';

// 指标卡片（取第一个策略）
const s = DATA[0];
const cards = [
  ['总收益率', s.total_return, s.total_ret_val>=0],
  ['年化收益', s.annual_return, s.ann_ret_val>=0],
  ['年化波动', s.annual_vol, false],
  ['夏普比率', s.sharpe, s.sharpe_val>=0],
  ['最大回撤', s.max_drawdown, false],
  ['卡尔玛', s.calmar, s.calmar!=='inf'&&parseFloat(s.calmar)>=0],
  ['日胜率', s.win_rate, true],
  ['交易日', s.days, true],
];
document.getElementById('summaryCards').innerHTML = cards.map(c =>
  '<div class="card"><div class="lbl">'+c[0]+'</div><div class="val '+(c[2]?'green':'red')+'">'+c[1]+'</div></div>'
).join('');

// 图例
const active = {};
DATA.forEach(function(s,i) { active[s.name]=true; });
document.getElementById('chartLegend').innerHTML = DATA.map(function(s,i){
  let html = '<div class="legend-item" onclick="toggle('+i+')" data-i="'+i+'">'+
    '<div class="legend-dot" style="background:'+COLORS[i%COLORS.length]+'"></div>'+s.name+'</div>';
  if(s.bench_series) {
    html += '<div class="legend-item" style="padding-left:0;opacity:0.7">'+
      '<div class="legend-dot" style="background:transparent;border:2px dashed '+COLORS[(i+1)%COLORS.length]+'"></div>沪深300</div>';
  }
  return html;
}).join('');

function toggle(i) {
  const s = DATA[i];
  const el = document.querySelector('.legend-item[data-i="'+i+'"]');
  active[s.name] = !active[s.name];
  el.style.opacity = active[s.name] ? 1 : 0.3;
  updateChart();
}

// 净值曲线
let nc;
function initNavChart() {
  nc = new Chart(document.getElementById('navChart'), {
    type:'line', data:{labels:DATES,datasets:[]},
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return ctx.raw.toFixed(4);}}}},
      scales: {
        x:{ticks:{maxTicksLimit:20,color:'#8b949e'},grid:{color:'#21262d'}},
        y:{min:0, ticks:{color:'#8b949e',callback:function(v){return v.toFixed(2);}},grid:{color:'#21262d'}}
      }
    }
  });
}

function updateChart() {
  const ds = [];
  DATA.forEach(function(s,i){
    if(!active[s.name]) return;
    ds.push({
      label:s.name, data:s.nav_series,
      borderColor:COLORS[i%COLORS.length],
      backgroundColor:COLORS_RGB[i%COLORS_RGB.length]+'0.1)',
      borderWidth:2, pointRadius:0, tension:0.1, fill:false
    });
    // 基准曲线 (虚线)
    if(s.bench_series && active[s.name]) {
      ds.push({
        label:s.name+' 基准(沪深300)', data:s.bench_series,
        borderColor:COLORS[(i+1)%COLORS.length],
        backgroundColor:'transparent',
        borderWidth:1.5, borderDash:[6,3], pointRadius:0, tension:0.1, fill:false
      });
    }
  });
  nc.data.datasets = ds;
  nc.update();
}

// 回撤图
let dc;
function initDDChart() {
  const s0 = DATA[0];
  if(!s0||!s0.nav_series) return;
  let cm = s0.nav_series[0];
  const dd = s0.nav_series.map(function(v){ cm=Math.max(cm,v); return v/cm-1; });
  dc = new Chart(document.getElementById('ddChart'), {
    type:'line', data:{
      labels:DATES,
      datasets:[{
        label:s0.name+' 回撤', data:dd,
        borderColor:'#f85149', backgroundColor:'rgba(248,81,73,0.15)',
        borderWidth:1.5, pointRadius:0, fill:true, tension:0.1
      }]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return (ctx.raw*100).toFixed(2)+'%';}}}},
      scales:{
        x:{ticks:{maxTicksLimit:15,color:'#8b949e'},grid:{color:'#21262d'}},
        y:{ticks:{color:'#8b949e',callback:function(v){return (v*100).toFixed(0)+'%';}},grid:{color:'#21262d'}}
      }
    }
  });
}

// 指标表
const fields = [
  ['name','策略名','left'],
  ['total_return','总收益率'],['annual_return','年化收益'],
  ['annual_vol','年化波动'],['sharpe','夏普比率'],
  ['max_drawdown','最大回撤'],['calmar','卡尔玛'],
  ['win_rate','日胜率'],['days','交易日数']
];
document.getElementById('metricsHeader').innerHTML = fields.map(function(f){
  return '<th style="text-align:'+(f[2]||'right')+'">'+f[1]+'</th>';
}).join('');
document.getElementById('metricsBody').innerHTML = DATA.map(function(s){
  return '<tr>'+fields.map(function(f){
    var v = s[f[0]]||'-', cls='';
    if(f[0]!=='name'&&f[0]!=='days'){
      var num = parseFloat(String(v).replace(/[^0-9.\-]/g,''));
      cls = num>=0?'green':'red';
    }
    return '<td class="'+cls+'">'+v+'</td>';
  }).join('')+'</tr>';
}).join('');

initNavChart();
updateChart();
initDDChart();
</script>
</body>
</html>""".replace("__DATA__", strategies_json).replace("__DATES__", dates_json)

    out_path = os.path.join(result_dir, "report.html")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"报告已生成: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", nargs="?")
    args = parser.parse_args()
    result_dir = args.result_dir or load_latest_results()
    if not result_dir or not os.path.exists(result_dir):
        print(f"目录不存在: {result_dir}")
        return
    print(f"生成报告: {result_dir}")
    out = generate_html(result_dir)
    if out:
        print(f"打开: file://{os.path.abspath(out)}")
        # 尝试用默认浏览器打开
        try:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(out)}")
        except:
            pass

if __name__ == "__main__":
    main()
