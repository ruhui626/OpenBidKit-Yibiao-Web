"""Publish observed decisions, human disagreements and actual before/after quotes."""
import argparse
import json
from pathlib import Path

LABEL={'modified':'已修改','partially_modified':'部分修改','unmodified':'未修改','undetermined':'无法判断'}


def where(ev):
    loc=ev['location'];label={'paragraph':'正文段落','table':'正文表格','header':'页眉','footer':'页脚','textbox':'文本框'}.get(loc['kind'],loc['kind'])
    if loc['tablePath']:
        label+=' / '+ ' → '.join(f"表{t['tableIndex']} XML行{t['xmlRow']} 网格列{t['gridColumn']}" for t in loc['tablePath'])
    return label+' / '+ev['reference']['part']


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--repo',type=Path,required=True)
    args=p.parse_args();out=args.run/'results'
    data=json.loads((out/'review-verification.json').read_text(encoding='utf-8'))
    if data['failed']:raise ValueError('Refusing passing report with failed checks')
    cases=json.loads((args.run/'fixtures/cases.json').read_text(encoding='utf-8'))['cases']
    reports={c['id']:json.loads((out/(c['id']+'.review.json')).read_text(encoding='utf-8')) for c in cases}
    data['versions']={key:{side:r[side] for side in ['before','after']}|{'opinionHash':r['opinionHash']} for key,r in reports.items()}
    data['wordRenderAttempt']={'success':False,'reason':'LibreOffice soffice.exe was not found on PATH'}
    data['limitations']=['no real customer files','no model inference','only explicit replacement grammar','no OCR integration','no split/merge semantic matching','no Word page or GUI navigation']
    report=['# 修改前后版本对齐与逐条意见复核验证','',
            '结论：在四组模拟 Word 前后版本中，明确写出旧值和目标新值的意见可以逐条复核，并给出原文件证据。能识别只改一处、页眉残留、新增附件引入旧值，以及表格/段落移动后的对应内容。意见含糊、数量变化、语义拆分或范围未覆盖时保守输出无法判断。','',
            '**这是受限的确定性替换规则实验，不是大模型理解任意微信意见的验收。** 判定函数只接收前后文件和意见，不接收人工答案；验收脚本另读人工标注。未接入 Web、数据库、业务接口或模型，没有真实客户资料。','',
            '## 实际结果','',
            f"4 组前后版本、8 份 DOCX、24 条意见；{data['passed']} 项检查通过、0 项失败。共 {data['textEvidenceRoundTrips']} 次文本证据按指定旧/新版本回查，并用标准库 ElementTree 独立定位和读回。重复引用也计入回查次数，不是独立文档数或判断准确率。",'',
            '| 原型判断 | 条数 |', '| --- | --- |']
    for status,count in data['decisionCounts'].items():report.append(f'| {LABEL[status]} | {count} |')
    report+=['',
             f"与人工业务标注完全一致 {data['exactHumanTruthAgreement']} / {data['opinions']} 条；另有 {data['conservativeAbstentionsOnKnownTruth']} 条人工能确定而原型选择无法判断。没有将人工标注的未完成/未知意见判成已修改，样本中的误报已改数为 {data['falseModifiedCount']}。这些结果不用于承诺真实客户准确率。",'',
             '四条保守弃判必须计入限制：删除原质保承诺未提供新承诺；改正采购编号后新增同文副本；运输安排改写并拆成两段；正文和图片实际均已改、但本轮未联动 OCR。不能把按保守策略通过的检查数说成 24 条业务判断全部正确。','',
             '## 典型前后证据','',
             '| 意见 | 修改前 | 修改后 | 判断 |', '| --- | --- | --- | --- |',
             '| 项目经理赵甲改赵乙 | 正文和人员表均为赵甲 | 正文赵乙，人员表仍为赵甲 | 部分修改 |',
             '| 全文工程名称改正 | 正文两处及页眉为旧名称 | 三处均有新名称，段落已重排 | 已修改 |',
             '| 材料批次旧号改新号 | 同一段出现旧号两次 | 一处新号、一处旧号 | 部分修改 |',
             '| 全文旧编号甲改新编号乙 | 原段一处旧号 | 原段已改，但新增附件又出现旧号 | 部分修改 |',
             '| 原质保承诺12个月改24个月 | 存在12个月承诺 | 原段被删除，没有对应24个月证据 | 无法判断 |',
             '| 维修工期60天改75天 | 工期为60天 | 工期仍为60天，其他参考段落已有75天 | 未修改 |','',
             '人员表在新稿中从表1第2行变成表2第4行，仍按岗位标签和整行内容对应。项目经理与同名安全员分开限定范围；意见未要求修改的安全员旧姓名，不充当项目经理意见的残留。两份同文声明按数量相同的内容集合核对，不编造“原第1段一定对应新第2段”的编辑血缘。','',
             '## 实验方法和范围','',
             '- 支持三种明确模板：把全文的“旧值”改为“新值”；把正文可编辑文字的“旧值”改为“新值”；把“上下文标签”相关位置的“旧值”改为“新值”。支持“将”“改成”等少量同义写法。未匹配模板、旧新值相互包含等情况不猜测。',
             '- 正文、表格、页眉页脚和文本框沿用已验证提取工具。对旧/新目标值作掩码后，用周边文字、岗位行标签及容器类型匹配；位置序号只用于展示证据，不用于跨版本强行对应。',
             '- 一对一唯一上下文可对应；同文且数量一致的重复内容按组计数。数量不一致、改写拆分、缺失对应段落时仅给候选，不把模糊相似度当作完成证据。',
             '- 每条已修改必须有已验证替换、无同范围旧值、无未解决对应或覆盖缺口；部分修改同时展示已替换证据和新稿旧值残留。',
             '- 全文意见遇到图片等未覆盖内容不能确认全部完成。明确限定可编辑正文可排除图片，但正文中的未解析嵌入内容仍会阻止完成；对实际含内部 altChunk 的派生包作了负向验证。',
             '- 报告绑定两份原文件摘要和意见清单摘要。更换版本、倒置前后文件、修改意见、伪造引文或扫描图片引用会被拒绝。同一文件与自身对比也不得报成本轮已修改。','',
             '## 逐条对照','',
             '| 意见编号 | 原型判断 | 人工业务标注 | 意见 |','| --- | --- | --- | --- |']
    for row in data['rows']:
        report.append(f"| {row['issueId']} | {LABEL[row['actualStatus']]} | {LABEL[row['truthStatus']]} | {row['opinion']} |")
    report+=['','## 未完成的验收','',
             '- 真实微信表述、隐含旧值、行业合规/资格/签章判断、招标条款对照及模型真实调用尚未验证。不能用本实验代替完整 AI 审核或保证交标通过。',
             '- 本轮不联动此前 OCR；图片提供原文件中的引用位置，不能把 OCR 段落或图像变化直接判成文字已改。扫描意见仍需单独接入可信 OCR 及人工核验。',
             '- 语义改写、段落拆分合并、多级表头/复杂表格、跨容器迁移、复杂修订显示、多附件及大文件性能未全面验证。隐式或不明确范围的意见需要用户确认，不能静默套用模板。',
             '- 原文件证据是结构路径及原文，不是 Word/WPS 页码、排版或一键跳转。文档渲染尝试仍因缺少 soffice.exe 失败；八份 DOCX 只作内部结构输入，不是经排版验收的正式文档。',
             '- 状态描述的是本轮明确文字要求，不能证明外包人员的实际编辑顺序，也不构成具备防篡改签名的线上审核报告。','',
             '## 复现与记录','',
             '脚本与命令见 [实验说明](../tools/revision-review-spike/README.md)，检查记录及人工对照见 [JSON 汇总](preparation/revision-review-validation.json)。本次源 DOCX、意见清单、独立人工答案和带完整部件路径/引文的逐组复核 JSON，保存在 data/word-evidence-spike 的本轮 revision-review 目录。旧提取器和业务代码未修改，没有新增依赖、模型配置或数据库迁移。','',
             '## 附录 每条意见的前后原文','']
    for case in cases:
        review=reports[case['id']]
        for result in review['results']:
            report += [f"### {result['issueId']} {LABEL[result['status']]}",'',result['opinion'],'',result['reason'],'']
            if result.get('counts'):
                counts=result['counts'];report.append(f"原稿旧值 {counts['beforeOldOccurrences']} 处；可核对的替换 {counts['verifiedReplacements']} 处；新稿同范围旧值 {counts['afterOldOccurrences']} 处。")
                report.append('')
            for group in result['groups']:
                report+=['对齐方式：'+{'unique-context':'唯一上下文','multiset-context':'同文集合计数','unresolved':'未确认对应，仅列原文及候选'}[group['method']]+'。','']
                for side,label in [('before','修改前'),('after','修改后')]:
                    if group[side]:
                        for ev in group[side]:report.append(f"- {label}｜{where(ev)}｜{ev['reference']['quote']}")
                    else:report.append(f'- {label}｜未获得已对应原文。')
                if group.get('candidateEvidence'):
                    report.append('- 新稿候选（未证实对应，不能据此判已改）：')
                    for ev in group['candidateEvidence']:report.append(f"  - {where(ev)}｜{ev['reference']['quote']}")
                report.append('')
            if result['remainingOld']:
                report+=['新稿旧值残留：','']
                for ev in result['remainingOld']:report.append(f"- {where(ev)}｜{ev['reference']['quote']}（旧值{ev['occurrences']}处）")
                report.append('')
            if not result['groups']:
                for side,label in [('before','修改前参考位置'),('after','修改后参考位置')]:
                    for ev in result.get(side+'Evidence',[]):report.append(f"- {label}｜{where(ev)}｜{ev['reference']['quote']}")
                report.append('')
            if result.get('imageReferences'):
                for side,label in [('before','修改前'),('after','修改后')]:
                    for picture in result['imageReferences'][side]:
                        report.append(f"- {label}未复核图片｜{picture['part']} → {picture['mediaPart']}｜图片摘要 {picture['imageByteHash'][:16]}…；精确插入路径在复核 JSON 中。")
                report.append('')
            answer=next(r for r in data['rows'] if r['issueId']==result['issueId'])
            report += [f"人工业务标注：{LABEL[answer['truthStatus']]}。标注说明：{answer['authorNote']}",'']
    (args.repo/'docs/REVISION-REVIEW-VALIDATION.md').write_text('\n'.join(report),encoding='utf-8')
    (args.repo/'docs/preparation/revision-review-validation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':data['passed'],'opinions':data['opinions'],'agreement':data['exactHumanTruthAgreement'],'report':str(args.repo/'docs/REVISION-REVIEW-VALIDATION.md')},ensure_ascii=False))


if __name__=='__main__':main()
