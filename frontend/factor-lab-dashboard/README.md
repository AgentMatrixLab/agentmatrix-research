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
