# 权限矩阵

本页以当前代码为准区分已有门禁和修改复核拟定要求。数据访问由 Fastify 路由和 Prisma 查询控制；本次未发现配置数据库行级安全策略的代码，不能依赖数据库自动补足路由遗漏。

## 当前身份与作用域

- 角色为 admin / user。正式 JWT 包含用户 ID、角色和用途；createRequireAdmin 读取令牌角色。
- createRequireProject 读取 X-Project-Id 并查询 Project，允许所有者和管理员；getProjectIdHeader 仅辅助路由事件，不做鉴权，不能拿它保护复核接口。
- createRequireModule 对普通用户查询 User.modules；管理员跳过模块查询。可授予模块见 server/src/auth/permissions.ts。
- client/src/shared/permissions.ts 控制菜单，服务端门禁仍必须存在。
- 项目内的子资源还需检查 parent.projectId，不能仅凭通过项目头校验就读取任意 runId/documentId。

## 当前代码矩阵

| 资源/操作 | 未登录 | 普通用户 | 管理员 | 边界依据 |
| --- | --- | --- | --- | --- |
| 登录、公开系统名称 | 可访问 | 可访问 | 可访问 | server/src/index.ts 公开路由 |
| 项目列表 | 401 | 查询自己项目 | 查询全部项目 | routes/projects.ts |
| 指定项目工作区 | 401 | 仅自己项目 | 任意项目 | auth/middleware.ts |
| 废标/查重工作区接口 | 401 | 自己项目 + bid-check | 任意项目 | index.ts 项目组内模块门禁 |
| 当前 /tasks/* 启动接口 | 401 | 依项目归属，无统一 bid-check 门禁 | 任意项目 | index.ts、routes/tasks.ts；非缺陷定论，新增复核须另设门禁 |
| 项目 SSE | 401 | 自己项目 | 任意项目 | routes/events.ts；没有按 bid-check 再过滤 |
| 共享知识库、公司/人员资料 | 401 | knowledge-base 模块内共享 | 可管理 | document/paths.ts 的 shared 目录；不是多租户隔离 |
| 读取模型配置 | 401 | key 脱敏 | 可读取完整配置 | routes/config.ts、config/store.ts |
| 修改平台配置/用户/提示词 | 401 | 403（个人偏好单独允许） | 允许 | routes/config.ts、index.ts |
| AI 诊断明细 | 401 | 403 | 允许 | index.ts 的管理员路由组 |

现有矩阵是代码结构说明，不等于所有路径已经做过真实越权验收。令牌角色变更即时性、账号停用后已有令牌、模块权限撤销后长连接均待专项验证。

## 拟定修改复核矩阵

新模块放在 bid-check 下，沿用单企业项目所有者/管理员模式。暂不引入“同事协作者”角色，真实多人项目协作权限待访谈后确定。

| 操作 | 普通用户要求 | 管理员要求 | 负向验收 |
| --- | --- | --- | --- |
| 新建/读取/上传/编辑意见 | 登录 + bid-check + 项目所有者 | 登录 + 有效项目 | 他人项目或缺模块 403 |
| 读取某文档或证据块 | 上述要求 + 文档属于该 review / project | 同样校验父链 | 换 documentId、blockId 不能串文件 |
| 启动、取消、读取运行 | 上述要求 + run 属于该 review | 同样校验父链 | 不走默认开放 tasks 路径绕过模块门禁 |
| 记录人工意见 | 上述要求 + issue 属于 run 快照 | 同样校验父链 | 客户端提交伪造 actorId 或机器结论被拒绝 |
| 下载原文件/报告 | 上述要求 + 固定版本归属 | 同样校验父链 | 不能用路径参数访问 .env 或其他项目 |
| 订阅进度 | 项目归属 + 复核模块可见性 | 有效项目 | SSE 不包含未授权正文，撤权后受保护详情不可再取 |

输入值不是身份：客户端的 projectId、userId、ownerId、role、runId 都需服务端验证。历史报告不可通过静态公开文件路径暴露。
