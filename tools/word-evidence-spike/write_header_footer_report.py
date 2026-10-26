"""Record the offline results without presenting a rendered-Word claim."""
import argparse
import datetime
import json
from pathlib import Path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--body-regression', type=Path, required=True)
    parser.add_argument('--docs', type=Path, required=True)
    args = parser.parse_args()
    result = json.loads((args.results / 'header-footer-results.json').read_text(encoding='utf-8'))
    body = json.loads((args.body_regression / 'results.json').read_text(encoding='utf-8'))
    assert result['failed'] == 0 and body['failed'] == 0
    sources = {
        'headerInheritance': 'https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/5de15e59-3ec1-4f80-aa4d-00bdd447b86f',
        'firstPageInheritance': 'https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/bce5f993-d683-4aa7-825e-bce25c64e8b8',
        'evenAndOdd': 'https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.evenandoddheaders',
    }
    summary = {k: v for k, v in result.items() if k != 'checks'}
    summary.update({'checkedAt': datetime.datetime.now().astimezone().isoformat(),
                    'bodyRegression': {'passed': body['passed'], 'failed': body['failed'], 'originalLocatorRoundTrips': body['originalLocatorRoundTrips']},
                    'rendererFailure': 'LibreOffice soffice.exe was not found on PATH; no page images produced.',
                    'paidModelCalls': False, 'referenceSources': sources,
                    'scope': 'Linked header/footer part text and table paragraphs, section definitions and settings. Not page layout, Word/WPS GUI navigation or a production feature.'})
    args.docs.mkdir(parents=True, exist_ok=True)
    preparation = args.docs / 'preparation'
    preparation.mkdir(parents=True, exist_ok=True)
    (preparation / 'header-footer-evidence-validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = []
    for name, count in result['blockCounts'].items():
        document = json.loads((args.results / f'{Path(name).stem}.structure.json').read_text(encoding='utf-8'))
        rows.append(f"| {name} | {document['sectionCount']} | {len(document['bindings'])} | {count} | 通过 |")
    examples = []
    for e in result['examples']:
        ev = e['evidence']
        uses = '；'.join(f"第{u['section']}节 {u['variant']} 类型 {'配置允许选用' if u['enabledBySettings'] else '配置未启用'}{' 沿用前节' if u['inherited'] else ''}" for u in ev['uses'])
        examples.append(f"- 原文：**{ev['quote']}**。部件：\u0060{ev['part']}\u0060，位置：\u0060{ev['xpath']}\u0060。关系：{uses}。")
    text = f'''# 页眉页脚提取与证据定位验证

结论：本次三个虚构 DOCX 的页眉、页脚文字及其中的表格单元格能够提取，并按原始文件摘要、关系指向的部件和段落路径回查。所属节、首页/默认/偶数页类型、跨节沿用和启用状态可一并保留。原有 Web 解析器在本组样本中未输出这些页眉页脚文字，仍不能直接承担这层证据定位。

仅新增独立离线实验，不接入页面、数据库、模型或业务接口。正文实验入口保持原来的覆盖范围；尚未把两个索引整合成完整文件审查流程。

## 实际验证结果

| 虚构文件 | 节数 | 节和类型关系数 | 非空页眉页脚文字块 | 回查原文件 |
| --- | --- | --- | --- | --- |
{chr(10).join(rows)}

共 {result['originalPartRoundTrips']} 个文字块逐个回查原 DOCX 中对应部件，全部一致；共有 {result['sectionBindings']} 组节/类型映射。内容包含 {result['authoredExpectations']} 条作者手工指定的文字及表格坐标预期，另对分节关系、重复文字、版本和错误引用作断言。合计 {result['passed']} 条断言通过、{result['failed']} 条失败。断言数不是文档数量，也不是客户准确率。

每条结构定位除用 lxml 回查，还用 Python 标准库 ElementTree 独立读取原 ZIP 部件再定位一次。测试前后原文件字节摘要不变。此前正文和表格实验回归：{body['passed']} 条断言通过，{body['originalLocatorRoundTrips']} 个原文文字块仍可回查；它与本次页眉页脚实验分开统计。

## 验证覆盖

1. 首页、默认和偶数页的页眉页脚分别保留类型。显式关闭 titlePg 或 evenAndOddHeaders 时，保留未启用定义，但不把它表述成当前页面显示内容。
2. 分节沿用按各自类型逐节传递，不把首页定义与默认定义混用。一个物理页脚可被三节沿用，提取一次并记录三个用途。
3. 首节启用首页不同、但没有首页引用时记录为空定义，不擅自用默认页眉页脚填补。
4. 页眉页脚里的表格单元格记录 XML 行、网格列和段落路径。拆开的普通/加粗文字片段合并为原文。
5. 不同部件有相同文字和相同 XPath 时，仍用文件摘要加部件名区分；换部件不能沿用原来的节上下文。
6. 跟随 document.xml.rels 的实际 Target。本例把一个页眉改名为 word/custom-header-A.xml，仍可找到，不依赖 header1.xml 这样的固定命名。
7. 包内存在但未被任何节引用的页眉单独列出，不混入已使用定义。PAGE 域只能提取缓存结果，并标记待核对，不能把缓存数字当成真实页码。

这些是结构和配置层面的验证。enabledBySettings 仅表示配置允许选用；实际出现在第几页、是否有足够页面用到该类型、连续分节的页面效果，以及从偶数页开始时的选择，都需要排版引擎或 Word/WPS 另行验证。本原型不据此生成物理页码。

## 具体残留示例

headers-after.docx 的正文和第一节默认页眉已写成“演示新路维修工程”，但仍存在以下旧名称定义：

{chr(10).join(examples)}

这说明即使正文或默认页眉已经改好，其他类型仍可能有残留。它不是“自动判断所有修改已经完成”的模型能力验收。

## 拒绝错误证据和异常关系

- 旧版本引用用于新版本、伪造原文、伪造所属节、正文冒充页眉，以及未引用部件冒充使用中的页眉，都被拒绝。
- 同文同位置换到另一个页眉部件，不能沿用原来的节上下文。
- 缺失关系、外部关系、错误关系类型、缺失部件、错误 XML 根、错误内容类型、越出包边界的 Target 和重复类型引用，均明确失败，不按文件名猜测或静默当作空白。
- 外部关系测试没有发起请求，不向作者服务器或模型发送数据。

## 当前 Web 解析器对照

三个虚构文件均能被当前 parseDocument 读取正文，但页眉页脚测试标记均未出现在返回 Markdown 中，也没有返回原文件定位。故本次新增的结构读取是独立验证层，尚未修改生产解析器。

## 尚未验证

- 本轮调用了打包的文档渲染器，仍因缺少 soffice.exe 无法生成页面图片。没有安装新软件，也没有操作用户的 Word/WPS。实际排版、显示页码和一键跳转未验收。
- 仅测试 python-docx 生成的虚构文件，没有真实客户、真实 WPS 另存文件或大体量标书。不同格式和复杂布局兼容性仍待样本验证。
- 页眉页脚内的图片、Logo、文本框内部文字、动态域实时计算、修订显示视图等不能由本轮普通文字提取推断为已覆盖。
- 基本 ZIP/XML 与关系校验不等于完整安全审计，不把实验脚本直接暴露成公网上传服务。

## 复现和证据

脚本及命令见 [离线实验说明](../tools/word-evidence-spike/README.md)。完整结果摘要见 [JSON 验证记录](preparation/header-footer-evidence-validation.json)。虚构原文件和逐条断言记录保存在 data/word-evidence-spike 独立实验目录，不提交到源码或作为正式 Word 文档交付。

参考规则：[微软 headerReference 与默认类型继承说明]({sources['headerInheritance']})、[首页类型继承说明]({sources['firstPageInheritance']})、[奇偶页开关说明]({sources['evenAndOdd']})。这些规则用于解释结构关系，不替代本地 Word/WPS 的实际显示验收。
'''
    (args.docs / 'HEADER-FOOTER-EVIDENCE-VALIDATION.md').write_text(text, encoding='utf-8')
    print(json.dumps({'report': str(args.docs / 'HEADER-FOOTER-EVIDENCE-VALIDATION.md'), 'assertions': result['passed'], 'roundTrips': result['originalPartRoundTrips']}, ensure_ascii=False))
