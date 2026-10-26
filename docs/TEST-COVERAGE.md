# 测试覆盖与缺口

本页区分已有测试、本次执行与拟新增测试。源码存在测试文件不等于当前执行通过，专项通过也不等于真实文档、模型或多企业使用已验收。

## 本次执行的现有覆盖

使用项目专用 Node 22.23.4，在 server 目录执行以下六个现有测试文件；共 24 项通过，无失败、跳过或取消。测试使用模拟数据库或系统临时目录，不连接业务数据库、不调用模型。

| 既有用例 | 规则及拒绝情况 | 源码证据 | 状态 |
| --- | --- | --- | --- |
| middleware.test.ts | JWT 用途分离；改密令牌不能访问普通路由，未知用途拒绝，旧正式令牌兼容 | auth/middleware.ts | 5 项已执行通过 |
| initialPassword.test.ts | 密码长度和字符种类；默认密码拒绝 | auth/initialPassword.ts | 3 项已执行通过 |
| permissions.resources.test.ts | 历史 resources 模块过滤，不覆盖项目所有权或 bid-check 越权 | auth/permissions.ts | 2 项已执行通过 |
| routes/auth.test.ts | 初始改密、弱密码、停用账户、重放和不同用途令牌 | routes/auth.ts | 8 项已执行通过，模拟数据库 |
| ai-diagnostics/sanitize.test.ts | 密钥脱敏、UTF-8 截断、结构摘要 | ai-diagnostics/sanitize.ts | 3 项已执行通过 |
| ai-diagnostics/storage.test.ts | 路径不能越界、60 KB 上限、过期目录清理 | ai-diagnostics/storage.ts | 3 项已执行通过，临时目录 |

复现命令（从项目根目录进入 server，不使用全局 Node）：

```powershell
Set-Location 'F:\Main\OpenBidKit-Yibiao-Web\server'
& '..\data\runtime\node_modules\node\bin\node.exe' --import tsx --test src/auth/middleware.test.ts src/auth/initialPassword.test.ts src/auth/permissions.resources.test.ts src/routes/auth.test.ts src/ai-diagnostics/sanitize.test.ts src/ai-diagnostics/storage.test.ts
```

当前类型基线为前端 14 项错误、后端 72 项错误；详见 preparation/baseline.json。它们不能算通过，也不能通过跳过检查把新错误隐藏掉。

## 独立 Word 定位实验

新增 tools/word-evidence-spike 离线实验，三个虚构 DOCX 提取 73 个文字块并回查原文件，160 条断言通过。包含 25 条作者手工定义的正文与表格预期、独立 XML 定位、重复文字、错误版本、虚构引用及部分包边界检查。它与上面的 24 项现有专项测试分开统计，尚未接入生产模块。

现有 parseDocument 在本组文件均完成，保留主体文字及表格，但没有原文件定位信息。页码、WPS 跳转、真实客户文件、模型判断和上传接口权限均未验收；页面渲染因缺少 soffice.exe 未完成。完整结果见 [验证报告](WORD-EVIDENCE-VALIDATION.md) 和 [JSON 记录](preparation/word-evidence-validation.json)。

下表与拟新增测试中的生产功能覆盖仍保持未运行或待实现，不能用离线实验替换。

## 现有但本次未执行的相关覆盖
void Add(System.Object key, System.Object value), void IDictionary.Add(System.Object key, System.Object value)

| 用例 | 覆盖意图 | 状态和限制 |
| --- | --- | --- |
| document/pdfTableStitching.test.ts | PDF 表格拼接 | 存在，未运行；不证明 DOCX 证据定位 |
| export/docxBuilder.test.ts | 既有 Word 构造 | 存在，未运行；不证明 WPS 页面一致 |
| routes/response-deviation.test.ts | 招标源可用性和指纹 | 存在，未运行；不是 HTTP 项目越权测试 |
| response-deviation/store.test.ts 等 | 相关工作区保存 | 存在，未运行；新复核需独立快照契约 |
| ai/service.diagnostics.test.ts | AI 错误诊断 | 存在，未运行；不代表真实提供商已联通 |
| client/src/app/menuConfig.test.ts | 菜单结构 | 存在，未运行；新增菜单需同步权限和测试 |

## 拟新增验收

| 优先级/类型 | 用例与规则 | 期待结果/负向情况 | 依据 | 状态 |
| --- | --- | --- | --- | --- |
| P0 自动集成 | 无令牌、缺模块、他人项目；替换 review/run/document/issue ID | 401/403/404，不能取出正文、原件、报告或事件 | FLOWS.md、PERMISSIONS.md | proposed，未编写 |
| P0 自动单元+集成 | 同一错误出现两处只改一处 | partial/unmodified，不得 modified | sample-cases.json CASE-02 | proposed |
| P0 自动单元 | 模型返回不存在或其他文件 blockId | 拒绝引用，降级 undetermined | 开发准备的证据协议 | proposed |
| P0 自动集成 | 更换文件/意见后旧任务晚返回 | 当前结果不被覆盖，旧 run 仅保留历史 | inputVersion/inputSignature | proposed |
| P0 自动集成 | 取消/崩溃、重复启动、重试 | 无虚假成功、不重复写确认、恢复状态明确 | AUTOMATION.md | proposed |
| P0 自动单元 | DOCX 包伪装、损坏、过多条目/解压超限 | 明确拒绝或失败，不执行宏、不取远程关系 | 文件边界草案 | proposed |
| P0 自动单元+手工 | 图片文字、页眉旧名称、文本框及修订 | 支持部分有证据，不支持部分标未覆盖 | parser 当前缺口 | proposed |
| P0 自动集成 | 无模型、超时、invalid JSON、超出上下文 | undetermined/明确失败，不能展示演示成功 | 模型输出契约 | proposed |
| P1 自动集成 | 意见重排、拆分、合并；删除后旧 issue 回包 | 保持稳定 issueId 和版本，不能串意见 | 快照协议 | proposed |
| P1 自动集成 | 人工确认与机器结论分离 | 记录用户和时间，不能更改原机器结果 | PERMISSIONS.md | proposed |
| P1 自动单元+手工 | 报告含恶意 HTML、链接或图片 | 转义，不执行或访问远程资源 | FLOWS.md | proposed |
| P1 浏览器手工 | 两版上传→意见编辑→运行→证据→确认→历史报告 | 可完整操作，错误信息能理解，范围不含虚构页码 | 开发准备流程 | proposed |
| P1 受控真实模型 | 同一组脱敏样本与人工标注对照 | 逐条统计误判、漏项、引用正确率、成本及时间 | 客户基准 | proposed，需样本及费用授权 |

## 缺口与门禁

- 最高风险缺口：当前没有新复核模块，因此没有实现或测试版本绑定、逐条证据校验和人工闭环。不得把 existing 栏的 24 项套到这些规则上。
- 已有角色/模块测试不等于所有资源访问已测试；现有项目门禁、SSE 与新模块之间的覆盖需补足。
- 客户资料、人工答案、出网许可和基准时间尚缺，真实准确率未知。
- CONTRIBUTING.md 要求前端 npm run build、后端 Prisma generate，权限改动需管理员/普通用户双向验证；本次只写文档，因此未重建产物或重新生成客户端。
- 该贡献指南没有给出一条覆盖全部测试的统一门禁。后续实现需记录本次所改模块的必要检查，并保留 14/72 旧错误基线；任何旧错误修复独立说明。

## 文本框离线补充验证

独立实验见 [文本框提取与证据定位验证](TEXTBOX-EVIDENCE-VALIDATION.md)。三个模拟 DOCX 保存的 33 个文本框容器含兼容副本及空框，36 个非空块可逐块回查，114 条断言通过；有手工内容/表格预期、标准库独立定位、版本/引用/上下文负向检查。保留兼容分支关系，不断言 Word/WPS 的实际显示。此后原正文/表格 160 条、页眉页脚 154 条回归均通过，分开统计。

现有业务解析器对照只证明本组文件的部分 VML/Fallback 文字可读、新版及定位存在缺口；不代表已经补上 Web 功能。真实客户与 WPS 文件、完整 OpenXML 架构、排版/页码/点击跳转、串联文本框文字分页、图形文字/OCR、大文件及真实模型均未验收。打包渲染器本轮仍缺少 soffice.exe，没有页面图片。

## 图片和扫描件离线补充验证

独立实验见 [图片和扫描件 OCR 与证据定位验证](IMAGE-OCR-EVIDENCE-VALIDATION.md)。5 张模拟图片、Word 的 6 处插图及 3 个纯扫描 PDF 页面合计 14 个来源位置、8 个去重后的 OCR 输入，保存 74 条逐行证据；127 项结构、原图回查、手工区域重叠、空结果及错误证据检查通过。PDF 三页及倾斜图片识别框已人工查看。原有正文 160 项、页眉页脚 154 项、文本框 114 项回归通过，分开统计。

这些通过项不是字符正确率。清晰图片也读错金额小数点；模糊图片与扫描页出现编号漏字、0/O 和 1/I 混淆。严重模糊图和空白图都返回空识别，不能据此断言材料缺失。全部 OCR 证据要求核对原图，没有编造置信度或自动通过结果。

Word 仅验证插图引用和原图区域，裁剪旋转的页面可见范围、WPS 页码和跳转未验收；PDF 第3页按已知样本方向人工转正，不是任意自动转正。真实客户资料、复杂表格、手写、拍照变形、大文件、Linux OCR 选型和完整上传服务未验收。现有 Web 解析器未实现该实验能力，其本次扫描 PDF 实测报“PDF 未检测到可选中文字层”。

## 版本对齐与意见复核离线补充验证

见 [修改前后版本与逐条意见复核验证](REVISION-REVIEW-VALIDATION.md)。4 组版本、8 份 DOCX、24 条人工编写意见，144 项检查通过，73 次文本证据按原版本回查并独立读取。结果为已修改8、部分修改5、未修改3、无法判断8；人工业务标注一致20条，另4条保守弃判。未将本组人工标注的未完成/未知意见报为已修改。检查通过数不等于业务判断全部正确，也不等于真实准确率。

本轮验证明确旧值/新值的替换规则、上下文/岗位行匹配、段落及表格重排、重复同文集合、同一段两处只改一处、新增旧值残留、删除/拆分/数量变化保守判断、意见和文件版本失效、伪造引文/图片引用拒绝。真实派生包的未解析内部 altChunk 也会阻止确认全文或可编辑正文已改全。

判定函数不接收人工答案；检查脚本独立读取业务标注和保守策略预期，二者分别统计。没有调用模型或联动 OCR，也未验收真实微信意见、业务合规/签章、复杂语义拆合、WPS 页码和跳转、大文件及线上服务。文档渲染仍缺少 soffice.exe，DOCX 只作内部结构输入。原有提取器和业务源码未改，已有业务测试与旧实验本轮未重新执行，不计作本轮通过数。
