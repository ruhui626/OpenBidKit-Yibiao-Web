# Web 架构

本系统提供标书编制、检查和共享资料管理。当前按单企业共享资料、多用户项目归属设计，不能等同于跨企业多租户隔离。拟新增的“修改复核”仍处于开发准备阶段，见 [开发准备](DEVELOPMENT-PREPARATION.md)。

## 1. 组件

- `client/`：React 19 + Vite 7，只负责 UI、请求编排和 SSE 展示。
- `server/`：Fastify 5 权威后端，负责鉴权、权限、文档解析、AI 请求、后台任务、导出和存储。
- `server/prisma/schema.prisma`：PostgreSQL schema 单一真相。
- Nginx：托管前端静态文件并反向代理 `/api` 和 SSE。
- PM2：使用项目本地 `tsx` 运行 `server/src/index.ts`。

## 2. 请求与数据边界

```text
Browser
  ├─ /             → Nginx → client/dist
  └─ /api + SSE    → Nginx → Fastify → Prisma → PostgreSQL
```

浏览器不承担权威文档解析或导出，鉴权和项目访问由服务端校验。模型配置区分普通用户脱敏视图和管理员完整视图；管理员浏览器也属于密钥暴露面，见 [配置与秘密边界](VARIABLES.md)。

## 3. 鉴权与权限

- JWT 分为两种用途：`purpose=access` 的正式会话令牌有效期为 7 天，用于常规受保护接口；`purpose=initial-password-change` 的受限令牌有效期为 10 分钟，只能用于首次改密接口，不能访问业务接口。为兼容升级，旧正式令牌未携带 `purpose` 时仍按正式会话处理。
- `mustChangePassword` 是用户的首次改密状态：全新安装时创建的默认管理员为 `true`，首次改密成功后原子更新为 `false`；已有用户和普通注册用户默认为 `false`。状态为 `true` 时不会签发正式会话令牌。
- 用户角色为 `admin` 或 `user`。
- 普通用户通过模块列表获得功能权限。服务端可授予模块白名单为 `template-settings`、`knowledge-base`、`bid-check`、`docs`、`faq`。
- 默认开放模块为仪表盘、标书生成和设置；用户管理与提示词管理仅管理员可用。
- 用户管理与提示词写操作仅管理员可用。
- 项目作用域 API 使用 `X-Project-Id`，服务端校验项目归属。
- 普通用户的模块门禁逐请求查询数据库，前端通过 `/api/me` 定时刷新菜单。管理员角色来自 JWT；角色或账户状态变化对既有令牌的即时影响需要另行验证。

## 4. 模块边界

- 标书生成：技术方案、已有方案扩写、投标计算器入口、响应与偏离表工作台。
- 格式管理：我的模板、新建模板、导出格式和共享模板。
- 知识库：方案模板库、工具模板库、公司资质库、人员资质库。
- 标书检查：标书查重和废标项检查。
- 使用文档与 FAQ：数据库文章、Markdown 渲染、管理员编辑和用户反馈。
- 管理模块：用户管理、提示词管理、基本设置。

“投标计算器”是标书生成下的评分辅助入口，定位为汇总综合报价、技术评分和商务评分规则，辅助计算标书最终得分；当前仍保持开发中提示，不在架构上承诺完整评分引擎已经落地。

## 5. 数据范围

- 用户域：用户、个人设置、平台配置、提示词、FAQ、导出模板、使用文档文章。
- 项目域：技术方案、已有方案扩写、响应与偏离表、标书查重、废标检查及后台任务。
- 公司共享域：知识库、工具资产、公司资质和人员资质。
- 大文件落在服务端运行数据目录，数据库只保存路径和结构化元数据。

## 6. 主题、品牌与开源归属

- 初始系统名称来自服务端默认配置：`易标投标工具箱web版`。
- 登录页、顶栏和导出元数据使用系统设置中的名称和 Logo；管理员可在“设置 - 基本设置”中修改。
- 客户端通过 `ThemeProvider` 管理主题，主题值为 `light` 或 `soc-dark`，存储键为 `yibiao_ui_theme`。
- `soc-dark` 主题通过 `html[data-theme='soc-dark']` 作用域覆盖历史浅色样式，尽量不改动各业务组件的结构。
- Markdown 文档和 Mermaid 预览会读取当前主题，保证使用文档在深色模式下可读。
- 开源说明组件在登录页和应用界面展示当前修改版源码、原始项目、AGPL、NOTICE 和作者归属。部署方可通过 `VITE_SOURCE_REPOSITORY_URL` 指向正在运行版本对应源码。

## 7. 使用文档种子

- 静态 Markdown 原稿位于 `server/prisma/seed-docs/`。
- 前端 `client/public/docs/` 保留同名静态文档和图片资源，便于 Markdown 图片路径稳定访问。
- 数据库文章由 `server/prisma/seed-docs.ts` 写入 `docs_articles`。
- seed 使用固定 id 幂等 upsert，刷新标题和正文，不覆盖管理员调整过的排序。

## 8. AI 与通用模型互通

AI 配置和密钥持久化在服务端数据库。普通用户读取配置时密钥被脱敏，管理员配置接口当前返回完整配置。文本模型、生图模型和 Agent 运行时通过服务端配置读取服务商、模型名称、Base URL 和密钥，再由后端或本地 AI Proxy 发起调用。

部署方可以按安全策略选择三种互通方式：

1. 连接公网通用大模型服务：服务端出网访问模型 API，适合快速启用，但需要确认招标文件、客户资料和生成内容是否允许发送给外部服务。
2. 连接企业统一模型网关：通过内网或受控出口访问 OpenAI-compatible 网关，便于做审计、限流、密钥轮换和模型统一管理。
3. 连接本地或私有化模型服务：将 Base URL 指向内网推理服务，数据流转范围更可控，但需要自行保障模型能力、上下文长度和并发性能。

服务端的 AI Proxy 会把平台配置转换为运行时可用的模型请求，避免各业务模块直接持有密钥。日志和诊断输出只应包含服务商、模型名、Base URL 连通性和错误摘要，不应输出完整 API Key。

## 9. Web 运行边界

Web 版以浏览器、HTTP API、SSE 进度推送、PostgreSQL 和服务端运行数据目录为边界。前端业务通过 `/api` 调用服务端，不直接读写数据库和服务端文件系统。模型密钥的管理员读取边界见 [配置与秘密边界](VARIABLES.md)。

运行时数据边界：

- 数据库保存结构化业务数据、权限、配置、文档文章和任务元数据；
- 上传文件、导出结果、文档解析中间文件保存到服务端运行数据目录；
- `.env`、数据库备份、上传目录、日志和客户文件由部署环境管理，不进入源码仓库；
- Nginx 只暴露前端静态资源、`/api` 和必要的 SSE 路由，数据库与后端内部端口不应直接暴露到公网。

## 10. 已知边界与开发准备

- 当前文档解析返回 Markdown 及其哈希，不返回原始 DOCX 字节摘要和稳定结构位置；图片被剥离。新增修改复核需单独建立版本、结构块及覆盖范围，见 server/src/document/parser.ts。
- 知识库、公司和人员资质使用 shared 目录，当前项目归属不是跨公司隔离，见 server/src/document/paths.ts。
- 既有任务接口与 SSE 按项目授权，不统一叠加 bid-check 模块权限；新增复核的详情、任务、下载和事件必须明确门禁，见 server/src/index.ts、routes/tasks.ts、routes/events.ts。
- Pi 运行时有 read/bash/edit/write 等工具；任务工作目录不等于操作系统沙箱。修改复核首版拟采用无工具的结构化模型请求，见 server/src/agent/pi/piSessionFactory.ts。
- Mermaid 远程渲染会发送图表内容，AI 诊断失败响应也可能含业务信息；密钥脱敏不是标书正文脱敏，见 server/src/export/mermaid.ts、server/src/ai-diagnostics/storage.ts。
- 本次类型基线为前端 14 项、后端 72 项错误；现有六个登录/诊断测试文件共 24 项通过，不能替代真实文件和模型验收。

## 11. 相关文档

以下文件沿用仓库现有 docs 目录；新增修改复核设计均标为草案，尚无业务实现。

- [功能清单](FEATURES.md)
- [部署说明](DEPLOYMENT.md)
- [修改复核开发准备](DEVELOPMENT-PREPARATION.md)
- [Word 提取与原文件定位验证](WORD-EVIDENCE-VALIDATION.md)
- [页眉页脚提取与证据定位验证](HEADER-FOOTER-EVIDENCE-VALIDATION.md)
- [文本框提取与证据定位验证](TEXTBOX-EVIDENCE-VALIDATION.md)
- [图片和扫描件 OCR 与证据定位验证](IMAGE-OCR-EVIDENCE-VALIDATION.md)
- [修改前后版本与逐条意见复核验证](REVISION-REVIEW-VALIDATION.md)
- [权限与关键流程](FLOWS.md)
- [权限矩阵](PERMISSIONS.md)
- [配置与秘密边界](VARIABLES.md)
- [测试覆盖与缺口](TEST-COVERAGE.md)
- [任务及模型自动化](AUTOMATION.md)
- [后台作业](BACKGROUND-JOBS.md)
- [开发基线](preparation/baseline.json)
- [虚构验收样例](preparation/sample-cases.json)
- [拟定数据契约示例](preparation/revision-review-contract.json)

修改复核首版未设计邮件通知或公开索引页面，因此本准备包不新增邮件及 SEO 文档。后台任务和模型工具已分别记录，不能按“无自动化”省略。
