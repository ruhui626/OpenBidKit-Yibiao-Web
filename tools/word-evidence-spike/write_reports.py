"""Write a static, escaped proof preview; it is not a product screen or Word render."""
import argparse
import html
import json
from pathlib import Path

from extract import resolve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--docs', type=Path, required=True)
    args = parser.parse_args()
    result = json.loads((args.results / 'results.json').read_text(encoding='utf-8'))
    examples = json.loads((args.results / 'evidence-examples.json').read_text(encoding='utf-8'))
    documents = {name: json.loads((args.results / f'{Path(name).stem}.structure.json').read_text(encoding='utf-8')) for name in result['fixtures']}
    assert result['failed'] == 0
    args.docs.mkdir(parents=True, exist_ok=True)
    preparation = args.docs / 'preparation'
    preparation.mkdir(parents=True, exist_ok=True)
    summary = {k: v for k, v in result.items() if k != 'checks'}
    summary.update({'snapshotDate': '2026-10-24', 'rendererFailure': 'LibreOffice soffice.exe was not found on PATH; no page images produced.', 'previewBrowserVerified': False, 'previewBrowserFailure': 'In-app browser disallows file URLs; no alternate route was attempted.', 'sourceHashes': {name: d['byteHash'] for name, d in documents.items()}, 'evidenceExamples': examples, 'independentXmlLookup': 'Python standard-library ElementTree resolves the generated paths against original ZIP bytes; authored text/table expectations are checked separately.', 'businessIntegration': False, 'paidModelCalls': False, 'notes': ['Only synthetic python-docx fixtures; no original customer documents.', f"{result['passed']} is an assertion count, not an accuracy estimate on that many documents.", 'A valid location does not establish that the cited paragraph semantically satisfies the modification request.']})
    (preparation / 'word-evidence-validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    after = next(e for e in examples if e['sourceName'] == 'after.docx' and e['label'] == '人员表里的未改姓名')
    xml = resolve(args.fixtures / 'after.docx', after['evidence'])['xml']
    rows = '\n'.join(f"| {name} | {len(d['blocks'])} | {d['tableCount']} | 通过 |" for name, d in documents.items())
    report = f'''# Word 提取与原文件定位验证

结论：在本次三个虚构 DOCX 中，正文、物理表格单元格和嵌套表格可以提取为结构块，并通过原文件 SHA-256、OOXML 部件、段落路径和原文偏移准确找回。现有 Web 解析器能读到主体文字，但没有返回这组定位信息，不能直接作为证据定位层。

本次是独立实验，不是已接入业务系统的功能。三个文件由 python-docx 生成，不代表真实 WPS、不同 Word 版本或大体量标书的兼容性。

## 实际执行结果

| 虚构文件 | 非空文字块 | 表格数 含嵌套表 | 原文件定位回查 |
| --- | --- | --- | --- |
{rows}

共 {result['originalLocatorRoundTrips']} 个文字块逐个从原 DOCX ZIP 的 word/document.xml 回查，全部一致。另有 25 个手工指定的正文/表格内容与坐标预期，以及不同命名空间前缀、重复文字和错误引用测试；全部实验合计 {result['passed']} 条断言通过、{result['failed']} 条失败。断言数不是文件数量，也不能换算成真实客户准确率。

定位用 lxml 完成后，再用 Python 标准库 ElementTree 独立解析原始 XML、按生成路径查找一次；关键文本和表格坐标的预期来自样本作者手工定义，而非提取器自产答案。所有原文件在现有解析器比较后字节摘要保持不变。

## 能定位到哪里

- 正文：具体 Word XML 段落、内置标题路径和段落内 Unicode 码点范围。拆开的多个 run 合并为连续原文，制表符与换行保留。
- 表格：具体表格、XML 物理行、实际网格列、单元格内段落；保留横向合并跨度、纵向合并元数据和嵌套表格层级。
- 重复文字：同一句“复核备注：待核对。”在每个主样本出现三次，分别有不同原文路径和块 ID，不靠一句全文搜索猜位置。
- 文件版本：旧稿的定位信息用于新稿时被拒绝；原文件改名但字节不变时仍可核验。Word 另存后即使看起来一样，也应重新计算版本和解析。

具体例子：after.docx 正文已经是“项目经理：示例乙。”，但人员表第 2 个 XML 行、第 2 个网格列仍为“示例甲”。该遗漏能回查到：

```text
{after['evidence']['xpath']}
```

同一个文件中的此单元格原文为“示例甲”。这里的行列是表格结构坐标，不是 Word 页码。位置有效只说明引用确实存在，不证明它一定是修改意见针对的语义对象；自动选择证据和判断是否改全尚未验证。

## 现有解析器的实际表现

- 三个样本均解析成功；主样本保留正文、嵌套表格以及 HTML colspan/rowspan 信息。
- 被加粗分隔的 run 会进入 Markdown 格式标记；不能直接用原始 Markdown 子串代替 Word 原文证据。
- 页眉和页脚未进入输出。边界样本中的图片文字没有 OCR 结果。
- 文本框文字、脚注和隐藏文字可进入 Markdown，但没有逐项来源标记或原文件坐标；脚注下划线经过 Markdown 转义，不能用未解码的裸字符串误判为缺失。
- 边界样本 DATE 域的缓存结果 2026-10-24 没出现在输出；修订内容得到一个文本视图，但没有说明修订痕迹是否已经清理。
- 返回字段只有 markdown、parserLabel、chars、hash、fallbackToLocal。现有 hash 是转换后文本摘要，不能替代原始 DOCX 文件摘要。

## 不能宣称已完成的能力

1. 未验证 Word/WPS 页面和一键跳转。本次调用打包渲染器后，诊断到缺少 soffice.exe，未生成页面图片，没有安装新软件或操作用户的 Word/WPS。HTML 结构预览只检查了内部定位链接和外部资源边界，未做浏览器视觉验收；内置浏览器拒绝 file 协议，未采用其他路径绕过。
2. 原型主动将页眉页脚、文本框、脚注/尾注、评论、图片、嵌入内容列为未覆盖；修订、隐藏文字和动态域额外标记人工复核。不能把正文通过扩大成“全文检查通过”。
3. 未验证自定义标题样式继承、自动编号的渲染结果、所有复杂表格形态、真实 WPS 保存文件和大文件性能。
4. 没有模型、自动跨版本语义对齐、网页上传、账号权限、数据库、报告业务入口或客户准确率验收。
5. ZIP 和 XML 有基本边界检查，但实验通过不代表完整安全审计；不要把独立脚本当成可直接暴露公网的上传服务。

## 后续建议

保留原始文件和结构索引作为证据来源，沿用现有解析器处理文本参考。下一次先补充少量真实脱敏的 Word/WPS 样本，检查表格和特殊部件，再决定如何整合到 Web。当前无需开发完整页面或增加 OCR、Word 改写及自动提交。

实验脚本在 [tools/word-evidence-spike](../tools/word-evidence-spike/README.md)。运行记录见 [JSON 记录](preparation/word-evidence-validation.json)，可查看 [结构提取预览](preparation/word-evidence-preview.html)。预览不是 Word 页面渲染，原始测试 DOCX 放在项目 data/word-evidence-spike 下作为内部测试输入，未按正式文档交付。
'''
    (args.docs / 'WORD-EVIDENCE-VALIDATION.md').write_text(report, encoding='utf-8')
    escape = html.escape
    cards = []
    for i, e in enumerate(examples, 1):
        ev = e['evidence']
        chain = ' → '.join(f"表{p['tableIndex']} XML行{p['xmlRow']} 网格列{p['gridColumn']}" for p in e['tablePath']) or '正文 / ' + ' / '.join(e['headingPath'])
        cards.append(f'<li><a href="#b-{ev["blockId"]}">{escape(e["sourceName"])}：{escape(e["label"])}</a><p>{escape(chain)} · <mark>{escape(ev["quote"])}</mark></p><details><summary>原文件定位</summary><code>{escape(ev["xpath"])}</code></details></li>')
    sections = []
    for name, document in documents.items():
        blocks = []
        for block in document['blocks']:
            coords = ' → '.join(f"表{p['tableIndex']} / XML行{p['xmlRow']} / 网格列{p['gridColumn']} / 跨{p['gridSpan']}列" for p in block['tablePath']) or ' / '.join(block['headingPath']) or '正文'
            flags = '；'.join(block['flags'])
            blocks.append(f'<article id="b-{block["id"]}"><small>{escape(coords)}</small><p class="text">{escape(block["text"])}</p>{f"<p>需注意：{escape(flags)}</p>" if flags else ""}<details><summary>OOXML 路径</summary><code>{escape(block["xpath"])}</code></details></article>')
        sections.append(f'<section><h2>{escape(name)} · {len(document["blocks"])} 个文字块</h2><details><summary>文件版本与未覆盖范围</summary><p>SHA-256：<code>{escape(document["byteHash"])}</code></p><p>{escape("、".join(document["coverage"]["uncovered"]))}</p></details>{"".join(blocks)}</section>')
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>Word 提取定位验证</title><style>body{{font:16px/1.65 system-ui,'Microsoft YaHei',sans-serif;background:#f5f7fa;color:#172033;margin:0}}main{{max-width:1120px;margin:auto;padding:32px 20px}}h1{{font-size:28px}}h2{{font-size:21px}}.intro,section,nav{{background:white;border:1px solid #dbe0e8;border-radius:8px;padding:20px;margin:20px 0}}article{{border-top:1px solid #e0e5ec;padding:12px 8px;scroll-margin-top:16px}}article:target{{background:#fff2b6;outline:2px solid #b58c18}}small{{color:#59667a}}.text{{white-space:pre-wrap;margin:6px 0}}code{{font:12px/1.6 Consolas,monospace;overflow-wrap:anywhere}}li{{margin-bottom:18px}}a{{color:#165baf}}mark{{background:#fff0a5}}summary{{cursor:pointer}}.limit{{color:#825600}}.counts{{font-weight:600}}</style><main><header><h1>Word 正文与表格定位验证</h1><p>虚构样本的结构提取预览；不是 Word 排版预览，也不是已经接入系统的业务界面。</p></header><div class="intro"><p class="counts">3 个 DOCX · {result['originalLocatorRoundTrips']} 个原文件定位回查通过 · {result['passed']} 条实验断言通过</p><p>点击下面的证据条目，可跳到此页对应的原文结构块。后台实验已经按原 DOCX 字节摘要和 OOXML 路径回查。</p><p class="limit">页码、Word/WPS 界面跳转、真实客户文件和模型判断均未验证。尚无可用 LibreOffice 页面渲染结果。</p></div><nav><h2>证据定位示例</h2><ol>{''.join(cards)}</ol></nav>{''.join(sections)}<footer><p>所有名称和业务内容均为虚构。本预览不加载外部资源，也不执行文档中的代码或链接。</p></footer></main></html>'''
    (preparation / 'word-evidence-preview.html').write_text(page, encoding='utf-8')
    print(json.dumps({'report': str(args.docs / 'WORD-EVIDENCE-VALIDATION.md'), 'preview': str(preparation / 'word-evidence-preview.html'), 'summary': str(preparation / 'word-evidence-validation.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
