# 权限与关键流程

本页记录现有 Web 实现和修改复核的拟定流程。标为“拟定”的路径尚未开发。全局架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 现有登录流程

用户 → client/src/shared/api/auth.tsx → POST /api/login → routes/auth.ts → User。

默认管理员须完成初始改密。登录此时返回用途受限的短期令牌；正式访问令牌由 auth/middleware.ts 校验。受限令牌访问普通受保护接口返回 401。首次改密接口验证令牌用途、用户状态和密码规则，成功更新用户并签发正式令牌。现有测试使用模拟数据库，见 TEST-COVERAGE.md。

正式令牌保存在浏览器 localStorage；这不是 HttpOnly Cookie。角色声明来自签名令牌，模块权限另经数据库查询。没有在本次准备中证明所有停用/降权操作会立刻使已签发令牌失效，上线前需单独验证。

## 现有项目文件导入和任务

参与者为已经登录、具有 bid-check 模块权限的项目所有者，或管理员。

| 步骤 | 数据和副作用 | 权限与拒绝路径 |
| --- | --- | --- |
| 前端选择项目 | http.ts 注入 X-Project-Id 和正式令牌 | 前端不是权威，伪造头不能代替服务端授权 |
| 进入 /rejection-check/import-document | 读取 multipart 流 | index.ts 顺序挂 verifyToken、createRequireProject、createRequireModule |
| 校验项目 | 读取 Project.ownerId | 无效项目头 400、项目不存在 404、他人项目 403 |
| 导入 | 临时文件 → parser → Markdown → store / 数据库及工作区 | 文件解析失败由路由映射；临时目录在 finally 清理；不输出原文件稳定位置 |
| 开始检查 | /tasks/start-rejection-check → TaskService → runner → AI | 任务路由受项目门禁；现有任务入口未整体挂 bid-check，新增复核不能照搬后假定模块门禁仍成立 |
| 接收事件 | /events?projectId=… → project 校验 → eventBus | SSE 另校验项目归属；同一个项目事件不按 bid-check 模块再过滤 |
| 完成 | runner 更新工作区并推送任务事件 | 模型输出和敏感上下文的细项须由具体 runner 检查 |

关联代码：server/src/index.ts、auth/middleware.ts、routes/rejection-check.ts、routes/tasks.ts、routes/events.ts、document/multipart.ts。

## 拟定修改复核流程

成功条件是保存一轮可追溯复核记录，不是自动保证标书合格。详细接口和字段见 [开发准备](DEVELOPMENT-PREPARATION.md)。

1. UI 创建 review，服务端校验登录、project 和 bid-check；归属来自数据库。
2. 上传前后版本，服务端校验包结构、解压/大小/耗时边界，保存不可变原文件和 byteHash；不使用上传文件名构造目录。
3. 结构提取器在本地生成块索引，记录正文、表格和未覆盖部件。未解析部分不能被模型补写成已检查。
4. 保存意见清单，带 expectedInputVersion；并发旧写入 409。更改任何输入使当前运行过期。
5. 用户主动运行，服务端固定输入快照、流水线版本和限额；无模型时不伪造判断，不自动切换有费用的模型。
6. 服务端按权限从该快照取候选原文，必要时向已配置模型发送所需片段。模型输入视为不可信文档数据，不能开启 shell 或写文件工具。
7. 模型只返回 issueId、状态、理由和候选 blockId；服务端验证 schema、意见覆盖和引用。没有可验证证据的“已改”降级为无法判断。
8. 写回前比较 inputVersion/inputSignature；过期运行只能存历史，不能覆盖当前结果。
9. UI 阅读证据时，校验 review → document → block 和当前 project 的完整归属。
10. 人工确认仅追加到指定 run+issue，记录用户和时间；不能覆盖原机器结论。
11. 报告由服务端使用固定快照生成，列明历史/当前版本、未覆盖范围、机器结论和人工意见；输出 HTML 转义，不加载远程脚本或图片。

模型调用、文件下载、事件订阅、取消任务和报告下载都是独立权限入口，不能只保护主页面。首次实现需防止把完整复核证据经项目公共 SSE 推送给没有 bid-check 权限的用户；建议事件只带无正文的运行状态，详情走受保护接口，并验证权限撤销后的行为。

## 不包含的流程

本包不设计邮件通知、自动投标、付款或公开分享报告。它们不是首版复核的前提。多家公司共用一套服务时的租户隔离另行设计，当前不能把项目归属等同于企业隔离。
