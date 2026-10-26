# 本地 Web 版运行说明

配置日期：2026-10-24。项目位于 F:\Main\OpenBidKit-Yibiao-Web。

- 浏览器：http://127.0.0.1:5174/
- 后端：http://127.0.0.1:3001/
- 独立 PostgreSQL：127.0.0.1:55432
- 桌面版继续使用：127.0.0.1:5173
- 数据库容器：yibiao-web-postgres
- 数据库数据卷：yibiao-web-postgres-data
- 业务文件：server/data
- 专用 Node：data/runtime/node_modules/node/bin/node.exe（22.23.4）

前后端本地运行，只有数据库使用 Docker。没有切换全局 Node，没有连接其他项目的数据库。

## 登录

账号 admin，初始密码 admin。项目要求首次登录后设置新密码，请自己在页面完成。不要跳过首次改密步骤。模型 API 尚未配置，AI 生成和审核未测试。

## 以后启动

先确保 Docker Desktop 已运行，然后在 PowerShell 执行：

```powershell
& 'F:\Main\OpenBidKit-Yibiao-Web\Start-LocalWeb.ps1'
```

启动脚本使用固定端口，只启动缺少的本项目服务；遇到别的程序占用端口会报错，不会结束其他进程。它不会修改 PowerShell 执行策略。通过该脚本启动的日志保存在 data/local-run。

首次本次运行使用独立开发会话，后续可用此脚本重新启动。正常退出电脑后需要再次启动服务。

## 配置与检查记录

server/.env、client/.env、.env.postgres.local 含本地配置或凭据，均已被 Git 忽略。不要公开文件内容。

安装时 pnpm 生成了 server/pnpm-workspace.yaml，记录本项目允许初始化的依赖。原生 SQLite 依赖已在项目专用 Node 22 下成功加载。数据库结构、默认管理员、提示词与 13 篇说明文章已初始化。

已验证：前端生产构建成功；数据库 healthy；后端设置接口成功；默认管理员登录返回强制首次改密状态；浏览器登录页正常，无控制台错误；端口与桌面版分离。

未通过：上游前端 typecheck 存在 14 项类型错误，涉及 API 类型定义、导出类型和 TS lib 等；未为展示页面而修改业务源码，因此不能声称完整类型检查通过。

未验证：改密后的完整业务、真实模型生成/审核、Word 导出与复杂文件兼容性。当前没有安装 LibreOffice；旧 .doc/.wps 等格式可能需要额外转换组件。普通浏览和配置不依赖它。