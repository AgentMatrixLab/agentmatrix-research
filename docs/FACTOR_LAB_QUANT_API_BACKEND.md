# Factor Lab Quant API 后端接入说明

本文档说明 Factor Lab 如何通过本地 Flask 后端代理访问公司 Quant API v2。

## 设计原则

- 前端不直接访问公网 Quant API。
- 前端不持有、不展示、不存储 API token。
- token 只通过后端环境变量注入。
- 当前只接只读查询端点，不接 admin pull、不触发 RQData 拉取任务。
- 本接入只提供真实数据读取能力，不改变 factor_lab 的核心因子计算、truth/proof/evaluation 逻辑。

## 环境变量

推荐使用：

```powershell
$env:FACTOR_LAB_QUANT_API_TOKEN="sk-..."
$env:FACTOR_LAB_QUANT_API_BASE_URL="http://115.159.73.134:8765"
```

兼容变量：

```powershell
$env:QUANT_API_TOKEN="sk-..."
$env:QUANT_API_BASE_URL="http://115.159.73.134:8765"
```

如果未配置 token，状态接口仍可访问，但数据接口会返回 401。

## 本地 Flask 代理接口

所有接口均在本地 Flask 下：

```text
http://127.0.0.1:8012/api/agents/factor-lab/quant-api/...
```

### 状态

```text
GET /api/agents/factor-lab/quant-api/status
GET /api/agents/factor-lab/quant-api/status?remote=1
```

用途：

- 查看 base_url。
- 查看 token 是否已配置。
- `remote=1` 时会请求远端 `/health`，如果 token 已配置还会请求 `/whoami`。

注意：不会返回 token 明文。

### 数据源

```text
GET /api/agents/factor-lab/quant-api/sources
GET /api/agents/factor-lab/quant-api/ch
```

用途：

- 查看 Quant API 可用数据源。
- 查看 ClickHouse 表清单。

### 月频因子

```text
GET /api/agents/factor-lab/quant-api/factor-monthly
GET /api/agents/factor-lab/quant-api/factor-monthly/factors
GET /api/agents/factor-lab/quant-api/factor-monthly/dates
GET /api/agents/factor-lab/quant-api/factor-monthly/stats
GET /api/agents/factor-lab/quant-api/factor-monthly/latest
```

支持的查询参数：

```text
symbol, date, factor, top, order, order_by, limit, offset, with_total
```

### 因子 IC

```text
GET /api/agents/factor-lab/quant-api/factor-ic
```

当前代理远端：

```text
/ch/factor_ic
```

### 日 K

```text
GET /api/agents/factor-lab/quant-api/kline-1d
```

当前代理远端：

```text
/ch/ods_kline_1d
```

## 当前明确不接

以下能力暂不接入 Factor Lab 前端代理：

- `/admin/pull`
- `/admin/pull/jobs`
- RQData 异步拉取
- Parquet / CSV 大文件下载
- 1 分钟 K 全表
- 任意 `where` 查询

原因：

- admin pull 会触发远端任务，不属于只读展示。
- Parquet / CSV 下载需要额外的文件流和权限设计。
- `where` 可能扩大查询面，先不暴露给前端。

## 后续建议

下一步可以基于这些只读接口做三件事：

1. 在前端设置页显示 Quant API 是否已连接。
2. 在因子详情页读取 `factor_ic` 和 `factor_monthly`，补真实 IC/IR 和因子截面信息。
3. 在数据治理完成后，再接日 K / 股票池 / 成本模型，用于单因子研究和策略回测。
