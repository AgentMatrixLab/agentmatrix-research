# Factor Lab双入口同步

2026-11-17按用户要求，将服务器现有Factor Lab新版页面同步至GitHub Pages。

## 内容来源

`pages/factor-lab-dashboard/app.js`和`styles.css`来自服务器现有静态部署，不改动研究逻辑。
图片及ECharts本地资源与服务器一致。HTML仅去掉服务器专用`config.local.js`引用并更新脚本版本号。
Pages的`config.js`指向`https://factor.liangjun.net.cn`，不再读取旧Supabase镜像或演示快照。
未复制运行数据、行情、私有证据、服务器本地配置或后台凭据。

## 登录与数据

使用服务器现有Factor Lab访问密码，通过`/api/agents/factor-lab/auth/login`取得令牌，
随后数据请求携带Bearer令牌。这里不是私有提交工作区的独立账号登录。
未改变API密码、鉴权或用户权限；前端便利密码不能作为服务器数据授权证明。
服务器API不可用时，不能把页面可见当作数据已加载。

## 服务器跨域配置

在现有Factor Lab API代理location中限定响应允许来源为
`https://agentmatrixlab.github.io`，不是通配符。不启用跨域Cookie凭据。
保留原代理、认证、TLS和研究后端。配置修改前备份，`nginx -t`成功后reload。
同一GitHub Pages源下的页面属于同一浏览器安全边界，API仍必须依靠令牌保护。

```nginx
proxy_hide_header Access-Control-Allow-Origin;
proxy_hide_header Access-Control-Allow-Headers;
proxy_hide_header Access-Control-Allow-Methods;
add_header Access-Control-Allow-Origin "https://agentmatrixlab.github.io" always;
add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
add_header Vary "Origin" always;
add_header Strict-Transport-Security "max-age=31536000" always;
```

## 验证

`node tests/factor-lab-pages-sync.cjs`检查API连接、无服务器专用配置、策略构建/看板容器及本地资源。
同步前测试因API配置为空失败，更新后7项断言通过。
真实Chromium使用Pages来源及待发布资产验证服务器密码认证、因子/绩效/新鲜度/策略接口，
全部返回200，监控页加载542行，未发生pageerror。测试不写入或删除研究策略。
上线后重复真实浏览器检查；接口成功不等于研究结果或交易执行已通过验证。

## 后续更新

后续页面更新应先合并仓库并发布同版资产到服务器，避免再次只改服务器。
本次为人工同步，不宣称建立了服务器到Pages的自动定时同步。
部署差异仅限API host和服务器本地配置；不得将服务器目录整体作为公开发布包。
