"""Human-readable evidence and observed OCR limitations, generated from completed checks."""
import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True);p.add_argument('--repo',type=Path,required=True)
    args=p.parse_args(); results=args.run/'results'
    data=json.loads((results/'image-ocr-results.json').read_text(encoding='utf-8'))
    if data['failed']: raise ValueError('Cannot publish passing report with failed checks')
    index=json.loads((results/'evidence-index.json').read_text(encoding='utf-8'))
    data['visualReview']={'scanPagesInspected':[1,2,3],'skewOverlayInspected':True,
                          'wordLayoutRendered':False,'realCustomerFiles':False}
    data['wordRenderAttempt']={'success':False,'error':'LibreOffice soffice.exe was not found on PATH','installedSoftware':False}
    data['qualityMetric']='NFKC plus whitespace removal only; punctuation substitutions remain errors; exactLineMatches means each authored line appears in concatenated OCR text'
    data['regression']={}
    for label,folder,name in [('body','body-regression','results.json'),('headerFooter','header-footer-regression','header-footer-results.json'),('textboxes','textbox-regression','textbox-verification.json')]:
        result=json.loads((args.run/folder/name).read_text(encoding='utf-8'))
        if result['failed']:raise ValueError('Regression checks failed')
        data['regression'][label]={'passed':result['passed'],'failed':result['failed']}
    report=['# 图片和扫描件 OCR 与证据定位验证','',
            '结论：本组模拟资料能够实际运行离线中文 OCR，并把结果绑定到 Word 中的具体图片引用、原图文字区域，或扫描 PDF 的具体页与显示区域。但识别出的文字仍会出错，不能据此自动判定资料合格或修改完成。','',
            '本次只新增 tools/image-ocr-spike 独立实验及文档，不修改生产解析器、页面、接口或数据库；不安装 OCR 软件，不调用收费模型，不发送样本到外部服务。','',
            '## 样本与实际结果','',
            '- 5 张模拟图片：清晰、模糊并加红色圆形遮挡、倾斜 5 度、严重模糊、空白。文字为人工绘制的虚构项目、姓名、编号、日期、金额。',
            '- 1 份 Word：6 处插图、2 份复用的图片内容，包含正文、正文表格、页眉和页脚，其中一处图片被裁剪并旋转。',
            '- 1 份 3 页纯图片 PDF；先确认每页没有可选文字层，再渲染与 OCR。第 3 页有 CropBox 和 90 度页面旋转，明确按样本设置人工指定转正，不是自动方向检测。','',
            f"合计 {data['sourceOccurrences']} 个来源位置、{data['uniqueOcrInputs']} 个去重后的 OCR 输入，保存 {data['ocrLineEvidenceCount']} 条逐行证据。{data['passed']} 项结构、原图回查和区域检查通过，0 项失败。这不代表识别准确率 100%；复用图片在不同位置的证据分别记录。",'',
            '| 输入 | OCR 行数 | 76 个标准化原文字符的编辑差异 | 可完整匹配的原文行 / 6 |',
            '| --- | --- | --- | --- |']
    for q in data['quality']:
        if q['sourceName']=='blank.png':continue
        label=q['sourceName']+(f" 第{q['page']}页" if q['page'] else '')
        report.append(f"| {label} | {q['ocrLineCount']} | {q['characterEdits']} | {q['exactLineMatches']} / 6 |")
    report+=['','字符比较只统一全半角及空白，不抹掉标点差异。OCR 可能把标签和金额拆成两行，因此逐条原文是否完整出现按合并文字判断，区域测试按空间关系合并同一原文行，不假定 OCR 行数必须相等。样本小且人工构造，不能推算真实标书准确率。','',
             '## 确实出现的识别错误','',
             '- 清晰图片：姓名、编号、日期值可找回，但金额 `1234567.89元` 被读成 `1234567·89元`，小数点变成中点。不能因为图像清晰就直接确认金额。',
             '- 模糊图片：证书编号丢字，标签标点也有错误；红色遮挡和降低分辨率共同影响本组结果，未单独量化各自影响。',
             '- 扫描 PDF 第1页：编号中的 `0/1` 被识别成 `O/I`，即 `AB0123456789` 变成 `ABOI23456789`。同一图片换成不同渲染分辨率后，错误也会变化。',
             '- 严重模糊图与空白图都返回零行；统一记录“未识别到文字，无法据此证明空白或材料缺失”。',
             '- 本地 Windows OCR 不提供本实验可用的字符置信度；全部证据都保留原始识别文本并要求人工核对，没有编造可信分数或自动通过阈值。','',
             '## 证据能定位到哪里','',
             '| 来源 | 本次验证通过 | 未承诺 |',
             '| --- | --- | --- |',
             '| 独立图片 | 原文件版本、原始像素、字词四边形、行框及原图裁片 | 识别文字一定正确 |',
             '| Word 插图 | 原 DOCX 版本、正文/页眉页脚部件、图片关系、具体插入引用路径、原图内区域；同图复用可区分位置 | Word/WPS 页码及页面上的绝对坐标 |',
             '| 图片被裁剪/旋转的 Word 插图 | 找回完整底图及原图区域，并标记显示范围未验证 | 完整底图中识别到的文字在页面上一定可见 |',
             '| 扫描 PDF | 原 PDF 版本、1 起始物理页序号、渲染图、原图区域及裁剪旋转后的显示页坐标 | 印刷页码、自动纠正所有拍照方向、未旋转的 PDF 底层坐标 |','',
             f"对清晰图片、倾斜图片、PDF 第1页和第3页的 24 组人工预设行区域作独立比对，最小区域交并比为 {data['minimumAuthoredRegionIoU']:.3f}，高于本实验事先设置的 0.55 阈值。它衡量文字区域的重叠程度，不衡量字符识别准确率。已人工查看三页扫描图的识别框和倾斜图片识别框，倾斜角按 Windows OCR 的返回值围绕图像中心映射；PDF 第3页另反向还原人工转正操作。",'',
             '证据回查核对原文件摘要、图片引用、OCR 索引记录、原图像素及区域。错误文字、区域、OCR 结果标识、原文件版本、图片引用或 PDF 页序号均被拒绝；外部图片关系不访问，缺失引用明确失败。此机制用于本地一致性验证，不是对任意被篡改索引的数字签名或公网上传安全审计。','',
             '## 当前 Web 版对照','',
             '现有 parseDocument 处理该 Word 时仅输出正文，图片中的模拟项目名、姓名未出现，也没有图片区域证据。处理这份纯扫描 PDF 时实际报错“PDF 未检测到可选中文字层”。因此目前 Web 业务尚未拥有本次验证的 OCR 与定位能力。','',
             '## 范围和未验证项','',
             '- 本轮使用 Windows.Media.Ocr 的 zh-Hans-CN，说明本机离线实验可行；不能直接照搬为 Linux 服务器部署方案。尚未比较 PaddleOCR、云 OCR 或视觉模型。',
             '- 没有真实客户文件、复杂多栏/跨行表格、手写、弯曲拍照、真实印章覆盖、多语言、大体量标书与性能验收。每个内容样本只有 6 行，不作为真实准确率基准。',
             '- DOCX 样本只作结构输入；本轮打包渲染器仍因缺少 soffice.exe 失败，尚无 Word/WPS 排版验收。旧版 VML 图片、OLE、矢量图、图表、浮动叠放和兼容分支没有宣称全覆盖。',
             '- 本次只读并标记裁剪/形状变换，不计算其页面可见范围；扫描 PDF 第3页采用人工已知方向转正，不宣称支持任意自动转正。',
             '- 识别结果可定位，不等于语义结论正确；姓名、编号、金额、日期仍需对原图确认。本实验不生成“已修改/合格”业务状态。','',
             '## 复现与产物','',
             '复现步骤见 [实验说明](../tools/image-ocr-spike/README.md)，逐条测试及识别误差见 [JSON 验证记录](preparation/image-ocr-validation.json)。原图、PDF 页面图、识别多边形、原图裁片、全部原始 OCR 响应和对照输出保存在本次 data/word-evidence-spike/image-ocr 运行目录。','',
             '原有实验回归分别为：'+ '、'.join(f"{label} {r['passed']} 项通过" for label,r in data['regression'].items())+'。分开计数，不混作 OCR 准确率。','',
             '参考：[微软 Windows OCR 的行/词结果与坐标](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine?view=winrt-26100)、[词框坐标说明](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrword)、[微软示例中的旋转框叠加](https://github.com/microsoft/Windows-universal-samples/blob/main/Samples/OCR/cpp/OcrCapturedImage.xaml.cpp)。','']
    (args.repo/'docs/IMAGE-OCR-EVIDENCE-VALIDATION.md').write_text('\n'.join(report),encoding='utf-8')
    (args.repo/'docs/preparation/image-ocr-validation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    # A compact evidence example: original amount pixels next to the uncorrected OCR output.
    clean_item=next(i for i in index['items'] if i['sourceName']=='clean.png')
    block=next(b for b in index['blocks'] if b['itemId']==clean_item['instanceId'] and b['lineIndex']==5)
    x,y,w,h=block['bboxOnOriginalImage']
    im=Image.open(args.run/'fixtures/clean.png').convert('RGB')
    crop=im.crop((int(x)-10,int(y)-10,math.ceil(x+w)+10,math.ceil(y+h)+10))
    preview=Image.new('RGB',(1050,330),'white');draw=ImageDraw.Draw(preview)
    font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',26)
    draw.text((25,15),'模拟样本：原图区域可定位，但 OCR 文字仍可能出错',font=font,fill='black')
    draw.text((25,65),'原图金额：',font=font,fill='black')
    crop.thumbnail((980,90));preview.paste(crop,(25,105))
    draw.text((25,205),'OCR 原始结果：'+''.join(block['ocrText'].split()),font=font,fill=(170,20,20))
    draw.text((25,260),'小数点被识别成中点，必须查看原图核对。',font=font,fill='black')
    preview.save(results/'ocr-evidence-preview.png')
    print(json.dumps({'report':str(args.repo/'docs/IMAGE-OCR-EVIDENCE-VALIDATION.md'),'passed':data['passed'],'preview':str(results/'ocr-evidence-preview.png')},ensure_ascii=False))


if __name__=='__main__':main()
