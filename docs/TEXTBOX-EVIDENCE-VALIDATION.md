# 文本框文字提取与证据定位验证

结论：本组模拟 DOCX 中，正文、表格锚点及页眉页脚里的新版 DrawingML 和旧版 VML 文本框文字，可从原始部件读取，并回查到对应文本框、段落和引文范围。能力只存在于独立离线实验，未接入 Web 业务。

这次验证的是文件中保存的文字及结构位置，不是页面渲染结果。新版与兼容副本分别保留；不把兼容副本直接算成屏幕上另一个文本框，也不根据其中旧名直接断言当前页面仍显示旧名。

## 实际结果

| 模拟文件 | 保存的文本框容器数 | 非空文字块 | 兼容组数 |
| --- | --- | --- | --- |
| textboxes-before.docx | 12 | 14 | 2 |
| textboxes-after.docx | 12 | 14 | 2 |
| textboxes-edges.docx | 9 | 8 | 1 |

合计 33 个保存的文本框容器、36 个非空文字块，114 条断言通过、0 条失败。计数包括兼容副本和空容器，不是屏幕上的文本框数量或客户准确率。每块原文均回查，同时用标准库 ElementTree 独立定位并读取文字。手工预期来自样本构造，不由提取器生成。

此前实验回归：正文和表格 160 条、页眉页脚 154 条全部通过，分开统计。原有 extract.py、header_footer.py 与业务解析器保持不变。

## 已验证的范围

- 普通和浮动 DrawingML 文本框、VML 文本框；跨文字片段、中文、表情、制表符及换行。浮动仅表示读取到该结构，不表示坐标或遮挡已验证。
- 正文表格单元格锚定的文本框，以及文本框内部表格。内外两组表格位置分别记录。
- 默认页眉、首页页眉和页脚中的文本框；同一页眉由两节沿用时只读取一次，保留两节用途。
- 不同文本框中相同文字保留不同证据；一段中引文出现两次时拒绝自动猜测。
- 新版和兼容副本相同、不同，以及含未知要求的多候选分支。保留每一分支的路径和要求，比较段落文字，不擅自选定 Word/WPS 当前显示哪一份。
- 隐藏文字、修订和域缓存标记人工核对。读取缓存页码不等于知道真实页码；删除文字不并入当前提取文本，也不代表已验收所有修订显示模式。
- 空框记录为空；未引用页眉单独披露，不作为已使用文本框内容。

## 证据与错误引用

证据绑定原文件 SHA-256、部件名、命名空间明确的文本框及段落路径、引文和 Unicode 码点范围；页眉页脚还绑定节用途，兼容分支保留容器关系。位置不依赖文本框名称唯一，也不依赖原文全局唯一。

错误版本、伪造文字、伪造文本框/节上下文、修改命名空间、正文冒充文本框、未引用页眉冒充使用中内容、兼容分支互换后保留旧上下文以及无效下标，都被拒绝。证据生成后修改它，也不会改变已提取索引。此校验不等于防篡改签名或公开上传服务安全验收。

## 残留示例

修改后样本的正文和一个正文文本框已改成“演示新路维修工程”，另一个浮动框、旧格式框及页眉页脚仍保存旧名，可分别回查。一个兼容组的新版保存新名、Fallback 保存旧名：该情况报告为“兼容内容不一致，需核对显示”，不能直接宣称客户提交页仍有旧名。

- 原文片段 `旧路`；部件 `word/document.xml`；段落路径 `/w:document[1]/w:body[1]/w:p[8]/w:r[2]/n1:AlternateContent[1]/n1:Fallback[1]/w:pict[1]/n2:shape[1]/n2:textbox[1]/w:txbxContent[1]/w:p[1]`；兼容副本：是。
- 原文片段 `旧路`；部件 `word/header1.xml`；段落路径 `/w:hdr[1]/w:p[1]/w:r[1]/w:drawing[1]/n1:inline[1]/n2:graphic[1]/n2:graphicData[1]/n3:wsp[1]/n3:txbx[1]/w:txbxContent[1]/w:p[1]`；兼容副本：否。
- 原文片段 `旧路`；部件 `word/header2.xml`；段落路径 `/w:hdr[1]/w:p[1]/w:r[1]/w:drawing[1]/n1:inline[1]/n2:graphic[1]/n2:graphicData[1]/n3:wsp[1]/n3:txbx[1]/w:txbxContent[1]/w:p[1]`；兼容副本：否。
- 原文片段 `旧路`；部件 `word/footer1.xml`；段落路径 `/w:ftr[1]/w:p[1]/w:r[1]/w:pict[1]/n1:shape[1]/n1:textbox[1]/w:txbxContent[1]/w:p[1]`；兼容副本：否。

## 现有 Web 解析器对照

未修改的 parseDocument 在三个样本中均完成本地解析。最初按整句比对 Markdown 会被加粗标记切断，不能据此说“文本框文字全部丢失”。去掉本组样本使用的加粗标记后，确实能找回部分 VML 文本框和 Fallback 文字；但新版 DrawingML、框内表格及页眉页脚的测试段落仍未检出，也没有返回原文件证据定位字段。修改后样本中，它输出的是兼容组的旧名 Fallback，故单凭扁平文字无法判断 Word/WPS 实际显示。完整原始输出与归一化对照保存在 JSON 记录；不能将本次原型通过表述成 Web 产品已具备完整能力。

## 尚未验证

- 仅有 python-docx 加手工 OOXML 构造的三个模拟样本，没有客户真实 Word/WPS 另存文件，没有全量 OpenXML 架构验证。复杂组合形状、嵌套兼容分支等未逐类验证。
- 打包渲染器尝试失败：缺少 LibreOffice soffice.exe。未安装软件，没有产生页面图片；真实显示分支、文本框溢出/遮挡、页码、阅读顺序和 WPS 点击跳转均未验收。样本只作为内部输入，不作为正式 Word 文件交付。
- 串联文本框仅标记共享文字流需要核对，尚不能确定文字实际分布到哪个页面/框。图片 OCR、a:t 图形文字及 VML textpath 水印未纳入本轮 Word 文本框提取；样本中的后两类明确披露为未覆盖。
- 没有验证大标书性能、语义判断、修改意见是否满足、模型费用或线上服务；没有调用模型、接入数据库、修改页面或业务接口。

## 复现与记录

脚本和复现命令见 [离线实验说明](../tools/word-evidence-spike/README.md)。结果摘要及每条断言见 [JSON 验证记录](preparation/textbox-evidence-validation.json)。源文件哈希见 JSON 的 files；模拟原件及逐块结构保存在 data/word-evidence-spike 的本次独立运行目录。

参考：[微软 Word 文本框容器](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.textboxcontent?view=openxml-3.0.1)、[VML 文本框](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.vml.textbox?view=openxml-3.0.1)、[兼容分支的 Requires 属性](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.alternatecontentchoice?view=openxml-3.0.1)、[新版文本框与共享文字流](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.office2010.word.drawingshape.textboxinfo2?view=openxml-3.0.1)。这些资料用于解释存储结构，不代替真实排版验收。
