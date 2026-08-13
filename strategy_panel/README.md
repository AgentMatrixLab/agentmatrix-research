# Strategy Backtest Panel （策略回测面板）

基于 Backtrader + FastAPI + React 的 A 股量化策略回测与展示系统。

## 功能概览

- **策略总览**：自动选取 Top5 策略，按逆波动率加权构建组合，实时显示组合净值与 KPI
- **个体策略**：每个策略的独立回测曲线、净值、持仓、交易明细
- **每日流水线**：自动拉取数据 → 回测 → 更新数据库 → 重启网站
- **Supabase 信号集成**：从外部信号表拉取调仓信号，自动回测
- **A 股真实交易规则**：沪深主板(100股整)、创业板(100股整/上限30万)、科创板(200股起/上限10万)、北交所(100股起)

## 项目结构

```
strategy_panel/
├── frontend/              # React + TypeScript + Vite 前端
│   ├── src/
│   │   ├── api/           # API 客户端与类型定义
│   │   ├── components/    # UI 组件（FolioSection, NavChart, HoldingsTable...）
│   │   ├── pages/         # 页面（Home, Portfolio, Positions, Trades, Risk）
│   │   ├── hooks/         # React Hooks（useOverview, useDashboard）
│   │   └── store/         # Zustand 状态管理
│   ├── package.json
│   └── vite.config.ts
├── server/                # FastAPI 后端
│   ├── main.py            # 14 个 API 端点
│   ├── db.py              # SQLite 数据库操作
│   └── requirements.txt
├── engine/                # 回测引擎
│   ├── bt_shared.py       # Backtrader 统一引擎（含 A 股交易规则）
│   ├── daily_pipeline.py  # 每日自动流水线（7 步）
│   ├── build_folio.py     # 逆波动率加权组合构建
│   ├── build_kline_adj_full.py  # 复权 K 线重建
│   ├── seed_from_json.py  # 从 JSON 写入 KPI + 净值
│   ├── seed_holdings_trades.py  # 从 JSON 写入持仓 + 交易
│   ├── fetch_supabase_signals.py # Supabase 信号拉取（只读）
│   ├── data_manager.py    # 数据增量更新
│   ├── setup_scheduler.ps1 # Windows 计划任务（每日 10:00）
│   └── strategies/
│       ├── dividend_yield_v6.py  # 红利 v6（每年 1/7 月调仓）
│       ├── micro_cap.py          # 微盘股（每月调仓）
│       └── supabase_signals.py   # Supabase 信号跟随
└── scripts/               # 运行脚本
    ├── rerun_dividend_v6_bt.py
    ├── rerun_micro_bt.py
    ├── rerun_supabase_bt.py
    └── check_api.py
```

## 环境要求

- Python 3.10+
- Node.js 18+
- SQLite3

## 快速启动

### 1. 启动后端

```bash
cd strategy_panel/server
pip install -r requirements.txt
python main.py
# 服务运行在 http://localhost:8100
```

### 2. 启动前端

```bash
cd strategy_panel/frontend
npm install
npm run dev
# 开发服务器运行在 http://localhost:5173
```

### 3. 首次数据初始化

```bash
cd strategy_panel/engine

# 更新数据（需要 RQData API 权限）
python update_data.py

# 重建复权 K 线
python build_kline_adj_full.py

# 运行所有回测
python ../scripts/rerun_dividend_v6_bt.py
python ../scripts/rerun_micro_bt.py
python ../scripts/rerun_supabase_bt.py

# 构建组合 + 种子数据库
python build_folio.py
python seed_from_json.py
python seed_holdings_trades.py
```

## 每日流水线

```bash
cd strategy_panel/engine
python daily_pipeline.py
```

自动执行 7 步：
1. 更新 K 线数据（增量拉取）
2. 重建复权 K 线
3. 数据校验
4. 红利 v6 回测
5. 微盘股回测
6. Supabase 信号 + 回测
7. 组合构建 + 种子数据库 + 重启服务器

### 设置定时任务（Windows）

以管理员权限运行：

```powershell
powershell -File strategy_panel/engine/setup_scheduler.ps1
```

每天 10:00 自动触发流水线。

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/overview` | GET | 策略总览（Folio + 所有策略列表） |
| `/api/strategies` | GET | 策略列表 |
| `/api/strategies/{id}` | GET | 策略详情（含持仓、交易记录） |
| `/api/strategies/{id}/nav` | GET | 净值曲线 |
| `/api/strategies/{id}/source` | GET | 策略源码 |
| `/api/check` | GET | 健康检查 |

## 修改指南

### 添加新策略

1. 在 `engine/strategies/` 下创建策略文件，实现 `get_signals(tradable_df) -> DataFrame` 方法：

```python
def get_signals(tradable_df: pd.DataFrame) -> pd.DataFrame:
    """
    tradable_df: columns = ['symbol', 'trade_date']
    返回: DataFrame with columns ['symbol', 'weight']
    """
    # 你的选股逻辑
    return result_df
```

2. 创建回测脚本（参考 `scripts/rerun_dividend_v6_bt.py`）

3. 在 `engine/seed_from_json.py` 的 `seed()` 函数中添加 `seed_strategy()`

4. 在 `engine/build_folio.py` 中添加策略到候选列表

5. 在 `engine/daily_pipeline.py` 中添加回测步骤

### 修改交易规则

编辑 `engine/bt_shared.py` 中的 `_lot_size()` 方法。

### 修改组合策略

编辑 `engine/build_folio.py`（权重算法）+ `server/main.py` 中的 `/api/overview` 端点（Folio 选择逻辑）。

### 修改前端

编辑 `frontend/src/components/FolioSection.tsx`（策略总览面板）或其他组件。

## Supabase 信号集成（只读）

`engine/fetch_supabase_signals.py` 从 Supabase `signals` 表拉取信号：

- 读取 `daily_stock_pool` + `monthly_etf_pool`
- 自动过滤 ETF 品种
- 解析 `note` 字段中的持股和卖出信号
- 符号格式转换（`SHSE.605589` → `605589.SH`）
- 输出 `supabase_signals.json` 供回测使用

## 数据说明

- 数据源：RQData API（`http://115.159.73.134:8765`）
- K 线存储：Parquet 格式（`data/kline_adj.parquet`）
- 回测输出：JSON 格式（`output/*.json`）
- 前端数据库：SQLite（`server/bt_panel.db`）

## 许可

MIT
