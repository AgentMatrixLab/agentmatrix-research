# QUANT DESK · 量化策略面板

前后端一体的量化回测平台，支持上传 Backtrader 策略、回测、净值展示。

## 项目结构

```
quant-desk/
├── server/              # FastAPI 后端
│   ├── main.py          # API + 静态文件服务
│   ├── engine_adapter.py # Backtrader 引擎适配器
│   ├── config.py        # 配置（路径 / 参数）
│   ├── db.py            # SQLite 数据层
│   ├── job_queue.py     # 回测任务队列
│   ├── seed.py          # 种子策略数据
│   ├── requirements.txt # Python 依赖
│   └── static/          # 构建产物（npm run build 生成）
├── src/                 # React 前端源码
├── public/              # 静态资源
├── data/                # K 线数据目录（需自行放置）
├── index.html           # 入口 HTML
├── package.json         # 前端依赖
├── start.bat            # 一键启动
└── README.md
```

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r server/requirements.txt
```

### 2. 安装前端依赖并构建

```bash
npm install
npm run build
```

### 3. (可选) 放置 K 线数据用于回测

将 `kline_1d.parquet` 放到 `data/` 目录下，或设置环境变量:

```bash
set QUANT_DATA_DIR=D:\your\data\path
```

不放置数据文件时，服务器仍可正常运行（含 7 个种子策略的净值展示），
但上传策略进行回测会因缺少数据而报错。

### 4. 启动

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8100
```

或双击 `start.bat`。

浏览器打开 `http://localhost:8100`。

### 5. 开发模式（前端热更新）

```bash
# 终端 1: 启动后端
python -m uvicorn server.main:app --host 0.0.0.0 --port 8100

# 终端 2: 启动前端开发服务器
npm run dev
```

## 策略上传格式

策略必须为 `bt.Strategy` 子类，包含 `def next(self)` 方法:

```python
import backtrader as bt

class MyStrategy(bt.Strategy):
    params = (("fast", 5), ("slow", 20))

    def __init__(self):
        self.sma_fast = bt.indicators.SMA(self.data.close, period=self.params.fast)
        self.sma_slow = bt.indicators.SMA(self.data.close, period=self.params.slow)

    def next(self):
        if self.sma_fast[0] > self.sma_slow[0] and not self.position:
            self.buy()
        elif self.sma_fast[0] < self.sma_slow[0] and self.position:
            self.sell()
```

## K 线数据格式

`kline_1d.parquet` 需包含字段: `symbol`, `trade_date`, `open`, `high`, `low`, `close`, `volume`
