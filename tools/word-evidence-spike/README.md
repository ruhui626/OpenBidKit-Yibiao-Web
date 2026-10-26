# Word 提取与证据定位实验

这是独立离线实验，不是生产上传接口。只新增 tools 和说明，不接页面、数据库或模型，也不修改 server/src/document/parser.ts。

## 文件

- make_fixtures.py：使用 python-docx 生成三个虚构 DOCX，含正文、复杂表格及未覆盖部件。
- extract.py：使用原始字节 SHA-256、OOXML 路径和 Unicode 码点范围记录证据；读回时验证版本和原文。
- verify.py：手工预期、原文件逐块回查、标准库独立 XML 定位、负向引用测试，并调用未修改的现有解析器对照。
- compare-current.mjs：通过项目现有 tsx 调用 parseDocument，不调用任何模型。
- write_reports.py：生成 Markdown 结果、JSON 记录和无脚本的静态结构预览。

## 复现

当前机器使用 Codex 已提供的 Python 3.12（lxml、python-docx、Pillow）和项目专用 Node 22；不新增项目依赖。测试图片使用 Windows 微软雅黑字体，其他系统需在生成器中替换字体路径。每次生成请选择一个新的空目录，不覆盖旧样本。

```powershell
$spikeRepo = 'F:\Main\OpenBidKit-Yibiao-Web'
$spikePython = 'C:\Users\hr\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$spikeNode = Join-Path $spikeRepo 'data\runtime\node_modules\node\bin\node.exe'
$spikeTools = Join-Path $spikeRepo 'tools\word-evidence-spike'
$spikeRun = Join-Path $spikeRepo ('data\word-evidence-spike\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $spikePython (Join-Path $spikeTools 'make_fixtures.py') --output (Join-Path $spikeRun 'fixtures')
& $spikePython (Join-Path $spikeTools 'verify.py') --fixtures (Join-Path $spikeRun 'fixtures') --output (Join-Path $spikeRun 'results') --repo $spikeRepo --node $spikeNode
```

生成器会创建独立 DOCX 测试输入；它们不是经视觉验收的正式文件。对文档进行正式交付时仍需按文档工具要求完成渲染和页面检查。本次渲染尝试因缺少 LibreOffice soffice.exe 未能完成，记录见 docs/WORD-EVIDENCE-VALIDATION.md。

## 成功与限制

成功只表示本组样本能提取，并能按结构位置回查原文。返回的表格行列是 XML 结构坐标；没有 Word 页码，没有桌面一键跳转。

extract.py 的正文原型只覆盖正文和表格，将页眉页脚、图片、文本框、脚注、评论等单独标为未覆盖；修订、隐藏文字、缓存域标记人工复核。内置 Heading1..9 提供标题路径，自定义样式继承和自动编号渲染尚未验证。结构索引不等于自动找对语义证据，也不等于修改意见已经满足。

原文件哈希是版本身份；不复用另存后文件或另一个版本的证据。偏移单位为 Unicode 码点，未来接 JavaScript 界面时不能直接当 UTF-16 字符串下标使用。

本实验不对真实客户文件准确率、大文件性能、完整 ZIP/XML 安全性或跨企业权限给出保证。公开服务接入前需要完整输入边界与权限实现。
## 页眉页脚独立验证

新增 header_footer.py、make_header_footer_fixtures.py、verify_header_footer.py 和 write_header_footer_report.py。此扩展单独读取关系、分节引用和页眉页脚部件，不改变 extract.py 原正文入口的覆盖范围，也不接入生产解析器。

三个新增虚构 DOCX 共 52 个文字块回查通过，映射 48 组节和类型关系，154 条断言通过。包含首页/默认/偶数页类型、跨节沿用、未启用定义、缺失首页定义、非标准命名的部件、未引用部件、表格和缓存页码域。完整结果见 docs/HEADER-FOOTER-EVIDENCE-VALIDATION.md。配置允许使用不等于实际某一页已经显示。

在上方 PowerShell 变量已设置后，可选择新的空目录复现：

```powershell
$hfRun = Join-Path $spikeRepo ('data\word-evidence-spike\header-footer-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $spikePython (Join-Path $spikeTools 'make_header_footer_fixtures.py') --output (Join-Path $hfRun 'fixtures')
& $spikePython (Join-Path $spikeTools 'verify_header_footer.py') --fixtures (Join-Path $hfRun 'fixtures') --output (Join-Path $hfRun 'results') --repo $spikeRepo --node $spikeNode
```

compare-current.mjs 现在可额外接受样本文件名；不提供时仍验证原来的三份正文/表格样本。原文定位回归仍为 160 条断言、73 个文字块通过。Word 页面渲染和 WPS 一键跳转仍未验证，本轮渲染器也因缺少 soffice.exe 未能生成页面图片。

## 文本框独立验证

新增 textboxes.py、make_textbox_fixtures.py、verify_textboxes.py、write_textbox_report.py。只索引原文件保存的文本框文字，复用原文件读取、路径及页眉页脚引用工具，不修改之前两个提取入口或业务解析器。

三个模拟 DOCX 含 33 个保存的文本框容器（包括兼容副本和空框），36 个非空文字块逐块回查；114 条断言通过。涵盖 DrawingML/VML、正文和页眉页脚、框内及锚点表格、重复文字、兼容副本差异、版本及错误上下文。新版与兼容副本分开记录，不根据文本相同就合并，也不声称全部同时显示。串联框排版、图形文字和图片 OCR 等仍未覆盖。

现有 parseDocument 能输出本组部分 VML/Fallback 文字，Markdown 加粗标记会切断整句，不能按原始整句缺失推断完全没提取；新版框和定位仍有缺口。详见 docs/TEXTBOX-EVIDENCE-VALIDATION.md。

沿用上方 PowerShell 变量，选择新的空目录复现：

```powershell
$textboxRun = Join-Path $spikeRepo ('data\word-evidence-spike\textboxes-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $spikePython (Join-Path $spikeTools 'make_textbox_fixtures.py') --output (Join-Path $textboxRun 'fixtures')
& $spikePython (Join-Path $spikeTools 'verify_textboxes.py') --fixtures (Join-Path $textboxRun 'fixtures') --output (Join-Path $textboxRun 'results') --repo $spikeRepo --node $spikeNode
```

正文/表格回归 160 条、页眉页脚回归 154 条通过。未接入完整文件审查；没有客户真实样本、页面图片、实际页码或 WPS 点击跳转验收。本轮打包渲染器仍因缺少 soffice.exe 失败，未安装新软件。
