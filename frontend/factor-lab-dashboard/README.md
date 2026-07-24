# Factor Lab 因子库前端 MVP

这是一个零构建的本地前端页面，用来展示 Factor Lab 本地 Flask 接口返回的因子库状态。

## 启动后端

```powershell
python backend/factor_lab_api.py
```

默认接口地址：

```text
http://127.0.0.1:8012/api/agents/factor-lab/factor-library
```

## 打开前端

直接用浏览器打开：

```text
frontend/factor-lab-dashboard/index.html
```

如果浏览器限制本地文件请求，可以在该目录启动一个静态服务：

```powershell
python -m http.server 5173
```

然后访问：

```text
http://127.0.0.1:5173
```

## 推荐访问方式

本地开发推荐直接使用 Flask 托管的页面：

```text
http://127.0.0.1:8012/factor-lab-dashboard
```

这样前端和 API 同源，最少遇到跨域或本地文件权限问题。

## 真实数据与密钥

- 前端只读本地 Flask 后端，不直接访问 Quant API。
- Quant API token 只放在 `.env` 或后端运行环境里，不要写入 `config.js`、`app.js` 或任何提交到 GitHub 的文件。
- 真实研究和策略运行产物由后端生成并落在 `runtime/factor_lab/`、`data/factor_lab/` 等本地目录，这些目录已被 `.gitignore` 排除。
- 如果部署到 GitHub Pages，只需要在 `config.js` 里设置后端地址，例如 `window.FACTOR_LAB_API_HOST = "https://your-factor-lab-api.example.com"`。

## 常用页面

- 因子库看板：`http://127.0.0.1:8012/factor-lab-dashboard`
- 后端健康检查：`http://127.0.0.1:8012/api/agents/factor-lab/health`
- 因子库数据接口：`http://127.0.0.1:8012/api/agents/factor-lab/factor-library`
