# 修改前后版本与逐条意见复核实验

这是离线实验，不是完整功能或任意自然语言意见的大模型验收。只新增本目录脚本、模拟输入及报告，不修改已有提取工具或业务代码，不调用模型，不新增依赖或迁移。

- `make_review_fixtures.py`：4 组版本、8 份 DOCX、24 条意见。意见与独立人工答案分别保存，不把答案传入判定函数。
- `review.py`：复用正文、表格、页眉页脚及文本框提取；明确替换规则解析、上下文/岗位行对齐、重复集合计数、旧值残留、保守弃判、原文和意见版本校验。
- `verify_review.py`：人工答案对照、前后原文回查、标准库独立 XML 读回、文件自身对比、错误版本/意见/引文/扫描引用及未解析正文内容检查。
- `write_review_report.py`：生成状态分布、人工判断差异和每条意见前后证据。

## 已验证和限制

144 项检查通过、0 项失败；73 次文本证据回查。24 条意见结果：已修改8、部分修改5、未修改3、无法判断8。与人工业务标注一致20条，另外4条原型保守选择无法判断，不能说业务判断全部正确；本组没有把人工标注的未完成/未知意见报成已修改。

只支持明确提供旧值、新值及范围的少量模板：

- 把全文的“旧值”改为“新值”。
- 把正文可编辑文字的“旧值”改为“新值”。
- 把“岗位或上下文标签”相关位置的“旧值”改为“新值”。

段落、表格插入或重排后按内容上下文对应，不拿旧段号/行号寻找新位置；重复同文按相同数量的集合核对，不虚构逐段血缘。上下文改写、数量变化或拆分时仅给候选，保守弃判。新稿旧值检查包含本轮范围中新增加的位置，不能仅看原来问题位置。

“补齐并盖章”“优化方案”等意见不作行业判断。图片仅提供引用位置，本轮未联动 OCR；全文件范围有未覆盖内容时不能报全部完成。旧值未检出或原段被删除不等于替换成功。

## 复现

使用已有 Codex Python、python-docx、lxml、Pillow，不安装项目依赖。新目录保存输入和结果，不覆盖旧实验。

```powershell
$reviewRepo = 'F:\Main\OpenBidKit-Yibiao-Web'
$reviewPython = 'C:\Users\hr\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$reviewTools = Join-Path $reviewRepo 'tools\revision-review-spike'
$reviewRun = Join-Path $reviewRepo ('data\word-evidence-spike\revision-review-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $reviewPython (Join-Path $reviewTools 'make_review_fixtures.py') --output (Join-Path $reviewRun 'fixtures')
& $reviewPython (Join-Path $reviewTools 'verify_review.py') --fixtures (Join-Path $reviewRun 'fixtures') --output (Join-Path $reviewRun 'results')
& $reviewPython (Join-Path $reviewTools 'write_review_report.py') --run $reviewRun --repo $reviewRepo
```

生成器会创建内部 DOCX 结构输入；使用文档技能运行时应先按其要求标记创建操作。由于缺少 soffice.exe，本轮未渲染出 Word 页面，不将样本作为正式 Word 文档交付。

报告 `docs/REVISION-REVIEW-VALIDATION.md` 包含24条意见前后原文；机器记录 `docs/preparation/revision-review-validation.json` 包含人工业务答案与保守策略答案的独立对照。详细引文、文件摘要、部件路径、表格坐标及图片引用保存在本轮逐组 JSON。

未验证：真实客户/微信泛化、真实模型、复杂语义拆合、OCR 联动、WPS 页码和跳转、大文件性能、公网上传和完整业务权限。已有业务基线与此前实验未在本轮重新执行，不将旧检查数计为本轮通过数。
