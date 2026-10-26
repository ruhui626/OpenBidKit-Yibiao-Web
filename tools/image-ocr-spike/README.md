# 图片和扫描件 OCR 离线验证

这是开发前实验，不是 Web 上传接口或完整标书审查功能。没有修改现有业务、安装软件、调用收费模型或上传样本。

- `make_ocr_fixtures.py`：5 张人工绘制图片、含 6 处插图的 Word、3 页无文字层扫描 PDF；包含模糊、倾斜、空白、复用图片、裁剪和旋转。
- `windows_ocr.ps1`：调用本机已有 Windows.Media.Ocr 简体中文组件，保留原始行、词框及倾斜角；不提供或编造置信度。
- `image_evidence.py`：Word 图片引用及原图索引、识别框映射、原图区域回查。外部图片不下载，缺失引用明确失败。
- `verify_image_ocr.py`：实际 OCR、手工原文/区域预期、图片和扫描页回查、错误证据拒绝、现有解析器对照、识别误差及可视化。
- `write_ocr_report.py`：根据已通过结果和原有三组回归生成 Markdown、JSON 和紧凑的原图对照图。

## 已验证与边界

5 张图片、6 个 Word 插图位置和 3 个 PDF 页面合计 14 个来源位置。复用图片去重后为 8 个 OCR 输入，保存 74 条逐行证据；127 项结构/定位检查通过。不是字符准确率 100%。清晰图也有金额小数点识别错误，扫描图有 0/O、1/I 混淆；严重模糊与空白的空结果不能区分。

Word 证据定位到插图引用和原图像素，不提供 WPS 页码。裁剪/旋转的完整底图可能包含页面未显示文字，明确标记未验证。PDF 使用 1 起始物理页序号及裁剪、旋转后的显示页坐标；第 3 页采用已知样本方向人工指定转正，不是自动方向检测。图像倾斜词框按引擎返回角度围绕中心映射，生成多边形叠加供核对。

Windows OCR 引擎及语言包是本机依赖，不是 Linux 生产部署选型结论。真实客户资料、手写、复杂表格、任意拍照变形、大文件、完整安全边界和线上效果未验收。DOCX 排版渲染仍缺少 soffice.exe；PDF 的三个渲染页与倾斜图片框已人工查看。

报告：`docs/IMAGE-OCR-EVIDENCE-VALIDATION.md`；逐条检查及误差：`docs/preparation/image-ocr-validation.json`。

## 复现

使用已有运行时和安装的简体中文 OCR。Windows PowerShell 5.1 运行 WinRT，Windows OCR 需要可正常读取系统语言组件与注册表；不要修改执行策略、关闭安全软件或更改系统语言包来绕过错误。Codex 沙箱权限不足时应请求正常权限执行。

```powershell
$ocrRepo = 'F:\Main\OpenBidKit-Yibiao-Web'
$ocrPython = 'C:\Users\hr\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$ocrNode = Join-Path $ocrRepo 'data\runtime\node_modules\node\bin\node.exe'
$ocrPoppler = 'C:\Users\hr\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe'
$ocrTools = Join-Path $ocrRepo 'tools\image-ocr-spike'
$ocrRun = Join-Path $ocrRepo ('data\word-evidence-spike\image-ocr-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $ocrPython (Join-Path $ocrTools 'make_ocr_fixtures.py') --output (Join-Path $ocrRun 'fixtures')
& $ocrPython (Join-Path $ocrTools 'verify_image_ocr.py') --fixtures (Join-Path $ocrRun 'fixtures') --output (Join-Path $ocrRun 'results') --repo $ocrRepo --node $ocrNode --poppler $ocrPoppler
```

输入和输出均选择新目录，不覆盖旧实验。生成器的 Word/PDF 只是内部输入，按相应文档工具要求标记创建操作并渲染核对后才能正式交付。报告生成器另外读取本次运行目录下原有正文、页眉页脚、文本框三组回归结果；不能用缺失的回归记录生成通过报告。
