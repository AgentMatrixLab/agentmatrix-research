# 私有因子入口部署状态

本次增量提供GitHub Pages与服务器备用站点共用的静态界面和私有提交协议。原研究面板、共享密码及研究API不修改。

## 可发布内容

- 门户链接到40日换手率真实公开摘要、私有提交工作区和服务器研究备用入口。
- 原因子库目录增量增加40日候选，聚合IC及验证局限来自获准公开的真实研究结果；不存在正式入库批准或线上提交回执。
- 私有提交界面使用独立`private-config.js`，不继承旧面板的共享密码或服务配置。
- 私有数据库增量迁移包含RLS、事务RPC、私有附件、冻结及独立审核，已应用于新项目。此次登录修复不更改数据库权限。

## 2026-11-17 临时密码登录

用户明确确认暂时采用“已验证邮箱＋独立密码”，取消本工作区强制MFA。此节取代下面历史记录中的管理员MFA要求，不等于邮件OTP已经上线。

- 新迁移`202611170001_private_factor_password_only.sql`只替换`pf_member`及`pf_admin`，服务端检查`auth.users.email_confirmed_at`、有效成员及受控管理员角色。作者隔离、冻结和禁止自审不变。
- 页面移除TOTP设置与验证控件，不调用MFA API；密码设置和邮件恢复入口保留。
- 不更改全项目Auth配置，不删除已有验证器绑定，不代改用户密码；其他应用不由本工作区决定登录规则。
- 本地新迁移40项数据库检查、30项浏览器断言、客户端与DOM测试及3项部署检查通过。旧迁移仍单独测试其历史MFA行为。
- 服务器真实临时账号验证密码管理员aal1可访问，未确认邮箱管理员不可访问；作者、其他协作者和匿名Storage隔离仍成立。刷新、退出及无验证器页面通过。
- 权限撤销测试使用无缓存独立请求。已下载或缓存的内容不能被追溯撤回，本次不保证缓存即时撤销。
- 真实用户检查到已有已确认邮箱、已设置密码和有效管理员角色，但测试账号成功不代表用户本人已经完成本轮登录。

新迁移必须最后应用，不能只重新运行旧初始迁移，否则会恢复旧MFA要求。

## 2026-11-16 登录验收

当前项目为 `wcexkmmpqmaqwiywntnc.supabase.co`。公开注册关闭，私有界面只使用 publishable key。旧项目不可解析的记录仅为历史状态，不再代表当前服务。

本次定位并修复：

- 登录框原有 `minlength=8`，与后端允许6位的既有密码不一致，浏览器会在发送请求前拦截。登录不再自行施加密码长度限制；设置新密码仍要求至少12位。
- 密码登录处理和 `SIGNED_IN` 回调同时重建页面，导致状态相互覆盖。保留初始化和显式登录处理，回调仅记录密码恢复事件，不重入认证。
- 管理员等待MFA时自动展开设置区，明确区分认证成功与二次验证未完成。
- MFA验证码失败保留尚未验证的设置密钥，成功或退出后清除；认证服务故障不再误报成密码错误。
- 发布配置启用新项目，与服务器一致；保留禁用门禁供维护使用，禁止回退到公开私有混合数据。

真实服务器验收使用独立临时账号，不读取或修改真实用户密码：

- 6位有效密码登录、刷新保持会话、退出清除页面。
- 真实TOTP注册与验证，管理员aal1不能访问私有内容，aal2可以访问。
- 测试作者通过真实RPC预约并上传私有附件，下载内容一致。
- 另一协作者及匿名访客不能读取已知ID的测试记录或已知路径的附件。
- 测试附件与草稿已清理，临时成员停用、临时账号禁用。没有提交或批准研究因子。

这些结果不等于用户本人已经登录或完成MFA。默认邮件服务没有自定义SMTP，接口接受请求仍不代表邮件送达。本次不声称解决邮件交付问题。

## 双入口

GitHub Pages门户：`https://agentmatrixlab.github.io/agentmatrix-research/`。

服务器保留原研究站点`https://factor.liangjun.net.cn/factor-lab/`，新增备用工作区目录`/factor-lab/workspace/`，内容与本次Pages目录来自同一发布包。不覆盖原研究页面、配置、共享密码或API。

不同站点使用同一账号和后端，但浏览器会话不自动跨域共享，两个域名分别密码登录；当前无需TOTP。

## Nginx模块类型

服务器必须把 `.mjs` 返回为 JavaScript，不能仅凭HTTP200判断页面可用。当前在既有 `server` 块中使用下列精确location，位于通用 `/factor-lab/` 规则之前。更新配置时保留或替换此规则，不重复添加相同location：

```nginx
location = /factor-lab/workspace/submission-client.mjs {
    alias /var/www/factor-lab/workspace/submission-client.mjs;
    types { application/javascript mjs; }
    default_type application/javascript;
    add_header Cache-Control "no-store";
    add_header X-Content-Type-Options "nosniff";
}
```

先备份现有配置，`nginx -t`成功后才reload；不得覆盖其他站点或研究API配置。浏览器验收必须确认模块Content-Type、初始化提示以及真实认证后的工作区，不只检查错误密码响应。

## 本地验证

已执行本地PGlite PostgreSQL39项身份/审核/冻结/附件检查、客户端12项检查、既有DOM测试及发布入口3项pytest检查。新增25项真实Chromium及Supabase SDK检查，网络使用固定测试响应；与上面的真实后端验收分开记录。

测试命令：

```powershell
python -B -X utf8 -m pytest tests/test_private_entry_deployment.py -q -p no:cacheprovider --noconftest
node tests/private-factor-client.cjs
node tests/private-factor-panel.cjs "$env:TEMP/amx-private-pg-tests/node_modules/linkedom"
node tests/private-factor-db.cjs "$env:TEMP/amx-private-pg-tests/node_modules/@electric-sql/pglite" supabase/migrations/202611150001_private_factor_submissions.sql
node tests/private-factor-db.cjs "$env:TEMP/amx-private-pg-tests/node_modules/@electric-sql/pglite" supabase/migrations/202611150001_private_factor_submissions.sql supabase/migrations/202611170001_private_factor_password_only.sql
node tests/private-factor-auth-browser.cjs "$env:TEMP/amx-private-pg-tests/node_modules/playwright"
```

浏览器测试使用Playwright 1.65.1的Chromium；本机复用已安装浏览器时可设置 `AMX_CHROMIUM_PATH`。CI自动安装对应浏览器。禁止把会话、密码、TOTP密钥或管理令牌写入测试产物。

## 数据边界

公开文件仅含获准的公式、聚合诊断和局限；不发布逐股因子值、私有附件、用户身份或秘密。上传界面不执行代码，人工检查不等于恶意软件扫描认证。

以上真实身份检查已覆盖基本读取隔离和MFA门禁，但不代表所有线上写入、自审、旧策略组合攻击均已穷尽。40日原始证据仍须由合法作者登录上传，只有取得服务端提交ID和冻结哈希才算提交完成，不能假冒作者或自动批准因子入库。
