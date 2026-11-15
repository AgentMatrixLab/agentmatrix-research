# 私有因子入口部署状态

本次增量提供GitHub Pages与服务器备用站点共用的静态界面和私有提交协议。原研究面板、共享密码及研究API不修改。

## 可发布内容

- 门户链接到40日换手率真实公开摘要、私有提交工作区和服务器研究备用入口。
- 原因子库目录增量增加40日候选，聚合IC及验证局限来自获准公开的真实研究结果；不存在正式入库批准或线上提交回执。
- 私有提交界面使用独立`private-config.js`，不继承旧面板的共享密码或服务配置。
- 私有数据库增量迁移包含RLS、事务RPC、私有附件、冻结及独立审核。此迁移尚未应用线上。

## 当前阻断

原配置Supabase项目域名`rebyrzrvnfbwvmbjvhzj.supabase.co`在2026-11-15的本机、服务器及公共DNS查询中无法解析；不能推定项目是暂停、删除或迁移，必须由项目管理员核验。

因此发布配置`PRIVATE_FACTOR_BACKEND_ENABLED=false`且不包含旧项目密钥。工作区明确显示后端未开通，隐藏登录、拒绝上传，不回退到公开数据或演示。

恢复原项目或确定已有替代项目后，必须核验邀请制账号、关闭开放注册、管理员MFA、实际RLS及Storage请求；验证完成后才能填入公开项目URL与publishable key并启用。service_role与数据库密码不得进入Pages。

## 双入口

GitHub Pages门户：`https://agentmatrixlab.github.io/agentmatrix-research/`。

服务器保留原研究站点`https://factor.liangjun.net.cn/factor-lab/`，新增备用工作区目录`/factor-lab/workspace/`，内容与本次Pages目录来自同一发布包。不覆盖原研究页面、配置、共享密码或API。

不同站点的浏览器会话不能自动共享；启用后登录同一账号和后端，但各域名仍需建立自己的认证会话。

## 本地验证

已执行本地PGlite PostgreSQL39项身份/审核/冻结/附件检查、客户端12项检查、DOM14项检查及发布入口两项pytest检查。不等于线上Auth、MFA和Storage已验证。

测试命令：

```powershell
python -B -X utf8 -m pytest tests/test_private_entry_deployment.py -q -p no:cacheprovider
node tests/private-factor-client.cjs
node tests/private-factor-panel.cjs "$env:TEMP/amx-private-pg-tests/node_modules/linkedom"
node tests/private-factor-db.cjs "$env:TEMP/amx-private-pg-tests/node_modules/@electric-sql/pglite" supabase/migrations/202611150001_private_factor_submissions.sql
```

## 数据边界

公开文件仅含获准的公式、聚合诊断和局限；不发布逐股因子值、私有附件、用户身份或秘密。上传界面不执行代码，人工检查不等于恶意软件扫描认证。

恢复后先用访客、协作者A、协作者B、管理员低/高验证级别执行真实越权检查。40日原始证据由合法作者登录上传，只有取得服务端提交ID和冻结哈希才算提交完成，不能假冒作者或自动批准因子入库。
