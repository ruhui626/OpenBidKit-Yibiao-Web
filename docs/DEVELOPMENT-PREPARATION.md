# 修改复核开发准备

本准备包基于本地 Web 版提交 `8a6b8d99e59a44778306b676ddf285304953442f`。当前工作仅增加准备文档和虚构样例，不代表“修改复核”已经开发，也不改变业务代码、数据库或模型配置。

建议首版围绕“一组 Word 版本和一份修改意见清单”建立可核对的记录。先验证证据定位和保守判断，再扩展自动分析。

## 1 事实和待验证假设

| 项目 | 状态 | 对开发的影响 |
| --- | --- | --- |
| 用户暂定以 Web 版为基础 | 已在本次沟通确定 | 在现有 React 和 Fastify 架构中增量开发 |
| 工程客户实际在哪一步被打回 | 未确认 | 内部返工、甲方审核、平台上传报错不能混为同一需求 |
| 道路维修案例、每月三份、核对三四小时 | 模拟访谈内容 | 只作演示题材，不写成真实调研数据或承诺 |
| 首版处理修改前后两份 DOCX 和文字意见 | 开发建议，待真实样本验证 | 先覆盖可提取文字；图片、签章、排版和资格评审不作保证 |
| 客户接受上传文件及向模型发送必要片段 | 未确认 | 真实资料和付费模型试跑的前置条件 |
| 未改不能被判成已改，拿不准要说明 | 首版拟定质量底线 | 需要证据校验、范围披露和人工复核，不靠模型自报置信度 |

建议联系客户时先请其回放最近一次真实返工：谁退回、理由是什么、用什么格式、哪些版本和意见还能提供。再确认使用人数、资料出网限制、谁负责最终核对、可接受的处理时间和付费方式。记录不知道的内容，不代客户填答案。

## 2 已检查的开发起点

本地访问为前端 `http://127.0.0.1:5174/`、后端 `http://127.0.0.1:3001/`、数据库 `127.0.0.1:55432`。桌面版使用 5173，开发时继续避开。当前客户端和公开设置接口 HTTP 200，独立数据库容器 healthy，专用 Node 为 22.23.4。HTTP 可达不等于登录后业务已经验收。

| 检查 | 本次结果 | 边界 |
| --- | --- | --- |
| 前端 tsc --noEmit | 14 项错误 | 是修改前已有基线；构建命令不包含类型检查 |
| 后端 tsc --noEmit | 72 项错误 | tsx 开发服务可运行不等于生产编译通过 |
| 登录、令牌、诊断脱敏专项测试 | 24 项通过 | 使用模拟数据库或临时目录，不是多客户真实验收 |
| 模型生成、Word 导出、修改复核 | 未做真实端到端验证 | 不据此承诺准确率、耗时或费用 |
| 开发工作区 | 原有三个未跟踪文件保留 | LOCAL-RUN.md、Start-LocalWeb.ps1、server/pnpm-workspace.yaml |

机器可读检查记录见 [基线](preparation/baseline.json)。本地启动方式见 [LOCAL-RUN.md](../LOCAL-RUN.md)。不为准备工作执行依赖更新、seed、db push 或生产迁移。

补充进展：独立的 Word 结构定位实验已完成，三个虚构 DOCX 共 73 个文字块原文件回查通过，160 条实验断言通过。它验证结构提取与位置，不代表新业务功能或真实模型已经通过。详见 [验证报告](WORD-EVIDENCE-VALIDATION.md)。

## 3 代码复用地图

| 工作面 | 现有入口 | 建议复用与新增边界 |
| --- | --- | --- |
| 菜单、页面切换 | client/src/app/menuConfig.ts、AppRouter.tsx | 拟在“标书检查”增加 revision-review；同步导航类型和权限映射 |
| 请求与项目选择 | client/src/shared/api/http.ts | 复用令牌和 X-Project-Id，不用前端传来的 ownerId 决定归属 |
| 文件上传 | server/src/document/multipart.ts | 可复用收流模式；新增原始文件保存、DOCX 包校验和结构块提取 |
| 文档转换 | server/src/document/parser.ts、doc2markdown/convert.mjs | 现有输出适合文本参考，不能直接充当 Word 页码或 XML 定位 |
| 鉴权与项目权限 | server/src/auth/middleware.ts、permissions.ts、index.ts | 所有新接口依次验证登录、项目归属、bid-check 权限和子资源归属 |
| 类似工作区 | server/src/rejection-check/store.ts、routes/rejection-check.ts | 参考模式；不要复用其数据库字段保存修改复核结果 |
| 长任务与进度 | server/src/tasks/service.ts、types.ts、runners/index.ts、routes/events.ts | 需新增 task type、group、state、store、恢复与取消处理；不能只注册 runner |
| 模型接口 | server/src/ai/service.ts、config/store.ts | 优先结构化请求，不为只读核对启用有 shell/write 权限的 Agent |
| 导出 | server/src/export/ | 首版可用服务器生成的静态 HTML 报告；需转义内容且不访问远程渲染站点 |

## 4 首版拟定流程

1. 在已有项目内新建一轮复核，上传“修改前”“修改后”各一份 DOCX；界面明确角色和原文件摘要。
2. 逐条录入修改意见，可粘贴后人工拆分、编辑和合并；保留原始文字、来源说明及“意见未收集完整”标记。
3. 显示解析覆盖范围，用户核对当前版本和意见后主动开始。
4. 每条意见显示：已修改、未修改、部分修改、无法判断；展示对应版本、原文片段和章节或结构位置。
5. 用户记录确认或异议及备注。机器结论和人工意见分开保留，不能互相覆盖。
6. 导出本轮复核报告，列明文件摘要、意见版本、未覆盖范围、未解决事项和确认人。
7. 更换文件或修改意见产生新输入版本，旧报告保留但标记已过期；旧任务晚到的结果不得覆盖当前轮。

没有模型配置时，“演示样例”单独进入带显著标识的演示模式；真实上传不返回虚构成功。报告只说明本轮修改复核情况，不标注“保证合格”“最终可交标”。

## 5 关键技术决定草案

### 文件和证据

- 为原始字节计算 SHA-256；原始文件版本不可变。现有 parser.hash 是 Markdown 文本哈希，不能替代它。
- 保留正文段落和表格单元格的结构块 ID、标题路径、OOXML 部件及序号、原始文本。块 ID 仅在一个文件版本内稳定，不假定前后版本序号一致。
- 以搜索和结构匹配寻找候选位置，模型只能引用服务器给定的 blockId。服务器校验引用确实来自本轮指定文件，原文片段真实存在。
- 页眉页脚、文本框、脚注、批注、修订痕迹、嵌入附件及图片文字在解析原型中分别验证；未支持的部分明确列为未覆盖。只有图片的文件应显示无法判断，不显示“未发现问题”。
- 前后版本对齐不是简单段落号对应；重复名称、重新排序、同名人员等情况需要多个候选及人工核对。
- 不生成虚构页码。首版在网页证据面板定位；在 WPS 原文件中可通过原文搜索辅助核对，不承诺一键跳页。

### 数据和状态

建议仅新增四类数据，正式迁移前再根据原型调整：

| 拟新增模型 | 最少字段和约束 |
| --- | --- |
| RevisionReview | id、projectId、title、inputVersion、issues JSON（稳定 issueId、文本、来源）、意见完整性标记、当前文档引用、createdBy、时间 |
| RevisionReviewDocument | id、reviewId、role、originalName、byteHash、textHash、parserVersion、原文件相对路径、块索引相对路径、coverage；上传后不可原地覆写 |
| RevisionReviewRun | id、reviewId、inputSignature、输入快照 JSON、status、validatedResults JSON、pipelineVersion、模型/提示词版本、起止时间；相同运行的结果完成后不可改写 |
| RevisionReviewConfirmation | id、runId、issueId、actorId、decision、note、时间；追加记录保留确认历史 |

JSON 仍需服务端严格 schema 校验。关联文件、run 和 issue 时验证完整父链归属，不接受用户给出的任意路径。报告按 run 快照生成，不能把当前意见与旧结果拼接。

inputSignature 基于原文件哈希、意见内容与顺序、解析器版本、流水线版本、prompt 版本和模型配置标识计算；不得包含真实密钥。模型配置标识也不等同于付款授权。

运行状态：queued → running → completed / failed / cancelled。过期是“运行绑定的输入不再是当前输入”的派生状态，不能把旧 completed 改成当前成功。数据库事务或乐观锁检查 inputVersion，防止异步写回覆盖新输入。

机器判断：modified / unmodified / partially_modified / undetermined。人工确认：confirmed / disputed / needs_follow_up，未确认用无记录表达。对未解决事项的“已知悉”不等于“修改完成”。

### 接口草案

以下路径均为拟新增，当前服务并不存在。共同要求 Authorization、X-Project-Id、bid-check 权限；客户端提供 expectedInputVersion 防止并发覆盖。

| 方法和路径 | 用途 | 关键约束 |
| --- | --- | --- |
| POST /api/revision-reviews | 创建复核轮 | 项目归属来自服务器校验 |
| GET /api/revision-reviews/:id | 查看当前输入和运行摘要 | 检查 review.projectId 与当前项目相同 |
| POST /api/revision-reviews/:id/documents?role=before\|after | 上传单个版本 | 校验 DOCX 包，不只看扩展名；返回新 inputVersion |
| PUT /api/revision-reviews/:id/issues | 保存意见清单 | 稳定 issueId、完整性标记及 expectedInputVersion |
| POST /api/revision-reviews/:id/runs | 主动开始分析 | 固定输入快照；幂等键、同轮互斥、限额和模型缺失处理 |
| GET /api/revision-reviews/:id/runs/:runId | 查看历史运行和覆盖范围 | 不因为 runId 存在就放行 |
| POST /api/revision-reviews/:id/runs/:runId/cancel | 取消运行 | 中止后不接受成功写回；网络请求尽力取消 |
| GET /api/revision-reviews/:id/documents/:documentId/blocks/:blockId | 阅读证据 | documentId 必须属于本轮；原文仅发给获授权用户 |
| GET /api/revision-reviews/:id/documents/:documentId/download | 下载原始 DOCX | 完整父链鉴权，固定服务端路径，attachment 下载 |
| POST /api/revision-reviews/:id/runs/:runId/items/:issueId/confirmations | 人工确认或异议 | 追加记录；客户端不能提交或覆盖机器结果 |
| GET /api/revision-reviews/:id/runs/:runId/report | 导出本轮报告 | 有未解决事项也如实列出；旧输入快照显示历史状态 |

错误应区分：401 未登录；403 无权限；404 资源不存在；409 输入过期或任务冲突；413 超限；415 不支持格式；422 文件损坏、无法解析或结果引用不合法；503 模型未配置/不可用。不要复用现有“所有异常都 409”的宽泛行为。

试点建议每份文件 20 MiB、每轮 50 条意见，具体值经样本调整；同时限制 ZIP 条目数、解压总量和解析耗时。所有限额都属于拟定规则，不是现有已实现能力。超限不得静默截断后宣称全量复核。

## 6 开发顺序和完成条件

| 阶段 | 工作 | 完成条件 |
| --- | --- | --- |
| P0 真实需求与资料 | 确认退回环节、脱敏三件套、出网限制、人工基准 | 有一份客户确认的事实记录；没有资料时继续做虚构原型，不能宣称需求已验证 |
| P1 基线和结构定位原型 | 单独处理阻塞所改模块的旧错误；用小 DOCX 验证正文/表格/未覆盖部件 | 可以重现同版本定位并揭示漏读；不必先重构整个仓库 |
| P2 保存和页面 | 新数据迁移草案、完整权限链、上传和意见编辑、独立演示模式 | 无模型也能演示；真实文件只呈现实际解析结果 |
| P3 复核流水线 | 候选检索、结构化模型判断、服务端证据校验、unknown 降级 | 不执行文档中的指令；没有有效证据不能判定已修改 |
| P4 运行与确认 | 任务状态、取消、恢复、过期输入保护、人工记录、报告 | 旧任务不串版本，报告和原文件绑定 |
| P5 试点验收 | 自动测试、浏览器流程、受控模型测试、客户对照 | 分开记录专项通过、真实效果、成本和时间；未通过不对外承诺 |

第一批开发前需确定：试点是否限一家企业、客户能否上传资料、能否调用外部模型、哪些 Word 部件必须覆盖、真实基准与可接受失败形式。模型品牌、定价和支付以后按实际样本选择，本包不预先采购。

## 7 验收方法

虚构样例见 [sample-cases.json](preparation/sample-cases.json)，数据契约示例见 [revision-review-contract.json](preparation/revision-review-contract.json)。它们不是测试结果，也不是已接通接口。

- 逐条意见有且只有一个机器状态，不能丢项；拆分意见必须由用户确认。
- 所有证据须可在对应文件和块中复现；引用伪造时降级为无法判断并记录原因。
- 未改判已改单独统计，不能用总体准确率掩盖；小样例中不允许出现这种误判，真实精度仍需独立样本验证。
- 显式记录未覆盖部件、模糊意见、缺失同事意见、模型缺失或超时。
- 人工计时与等待模型时间分开，先测当前流程，再测工具辅助；没有真实计时前不承诺从三四小时降到一小时。
- 修改复核、签章检查、格式合规、投标资格判断和平台提交成功分别验收。

## 8 相关开发文档

沿用仓库现有 docs 目录，不新增平行的 documentation 目录。当前架构主入口仍为 [ARCHITECTURE.md](ARCHITECTURE.md)。

- [权限与关键流程](FLOWS.md)
- [权限矩阵](PERMISSIONS.md)
- [配置与秘密边界](VARIABLES.md)
- [测试覆盖与缺口](TEST-COVERAGE.md)
- [任务及模型自动化](AUTOMATION.md)
- [后台作业](BACKGROUND-JOBS.md)
