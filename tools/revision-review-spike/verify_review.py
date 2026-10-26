"""Independent human labels, real DOCX roundtrips and counterfactual checks."""
import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from review import review_pair, text_evidence_by_side, validate_report, verify_evidence


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();fixtures=args.fixtures.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    cases=json.loads((fixtures/'cases.json').read_text(encoding='utf-8'))['cases']
    # Answers are read by the checker only; review_pair accepts no answer argument or path.
    answers=json.loads((fixtures/'human-answers.json').read_text(encoding='utf-8'))
    checks=[];reports={};rows=[];reference_count=0
    def require(ok,reason):
        if not ok:raise AssertionError(reason)
    def check(name,fn):
        try:fn();checks.append({'name':name,'passed':True})
        except Exception as error:checks.append({'name':name,'passed':False,'error':f'{type(error).__name__}: {error}'})
    def independent(source,ev):
        ref=ev['reference']
        with ZipFile(source) as z:root=ET.fromstring(z.read(ref['part']))
        node=root.find('./'+'/'.join(ref['xpath'].split('/')[2:]),ref['namespaces'])
        require(node is not None,'Independent source paragraph missing')
        uri=root.tag[1:].split('}')[0];parts=[]
        def visit(item):
            if item is not node and item.tag in {f'{{{uri}}}p',f'{{{uri}}}txbxContent'}:return
            if item.tag==f'{{{uri}}}t':parts.append(item.text or '')
            if item.tag==f'{{{uri}}}tab':parts.append('\t')
            if item.tag in {f'{{{uri}}}br',f'{{{uri}}}cr'}:parts.append('\n')
            for child in item:visit(child)
        visit(node)
        require(''.join(parts)==ref['quote'],'Independent original text differs')

    for case in cases:
        sources={'before':fixtures/case['before'],'after':fixtures/case['after']}
        report=review_pair(sources['before'],sources['after'],case['opinions'])
        reports[case['id']]=report
        (out/(case['id']+'.review.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        check(case['id']+': full report evidence and source/opinion versions',lambda:require(validate_report(sources['before'],sources['after'],case['opinions'],report),'Report not validated'))
        for result in report['results']:
            answer=answers[result['issueId']]
            rows.append({'issueId':result['issueId'],'opinion':result['opinion'],'truthStatus':answer['truthStatus'],
                         'expectedConservativeDecision':answer['expectedConservativeDecision'],'actualStatus':result['status'],
                         'authorNote':answer['authorNote'],'reason':result['reason'],'counts':result.get('counts')})
            check(result['issueId']+': pre-authored conservative decision',lambda result=result,answer=answer:require(result['status']==answer['expectedConservativeDecision'],f'Expected {answer["expectedConservativeDecision"]}, got {result["status"]}'))
            if result['status']=='modified':
                check(result['issueId']+': complete has no remaining old value, unresolved group or coverage gap',lambda result=result:require(not result['remainingOld'] and not result['unresolved'] and not result['coverageGaps'] and result['counts']['verifiedReplacements']>0,'Unproved completion'))
            if result['status']=='partially_modified':
                check(result['issueId']+': partial includes proved new value and original old-value evidence',lambda result=result:require(result['counts']['verifiedReplacements']>0 and result['counts']['afterOldOccurrences']>0 and result['remainingOld'],'Partial lacks proof'))
            for number,(side,ev) in enumerate(text_evidence_by_side(result),1):
                reference_count+=1
                def roundtrip(side=side,ev=ev):
                    resolved=verify_evidence(sources[side],ev)
                    require(resolved['text']==ev['reference']['quote'],'Original evidence quote differs')
                    independent(sources[side],ev)
                check(f'{result["issueId"]}: {side} original evidence {number}',roundtrip)
        for role in ['before','after']:
            same=review_pair(sources[role],sources[role],case['opinions'])
            check(f'{case["id"]}: same {role} version cannot count as a new modification',lambda same=same:require(all(r['status'] not in {'modified','partially_modified'} for r in same['results']),'Same-file comparison reported a change'))

    results={r['issueId']:r for report in reports.values() for r in report['results']}
    manager=results['workflow-02'];moved_table=next(g for g in manager['groups'] if g['before'][0]['location']['tablePath'])
    check('Inserted table and reordered personnel rows do not pair by old coordinates',lambda:require(moved_table['before'][0]['location']['tablePath']!=moved_table['after'][0]['location']['tablePath'] and moved_table['verifiedUnchanged']==1,'Wrong table-row alignment'))
    phone=results['workflow-04']['groups'][0]
    check('Moved paragraph aligns despite different XML ordinal',lambda:require(phone['before'][0]['reference']['xpath']!=phone['after'][0]['reference']['xpath'] and phone['verifiedChanged']==1,'Ordinal alignment used'))
    check('One paragraph containing two target occurrences remains partial',lambda:require(results['workflow-08']['counts']['beforeOldOccurrences']==2 and results['workflow-08']['counts']['verifiedReplacements']==1 and results['workflow-08']['counts']['afterOldOccurrences']==1,'Repeated occurrence lost'))
    check('Header and footer are actually covered in text review',lambda:require(any(e['origin']=='header-footer' for g in results['workflow-01']['groups'] for e in g['before']) and results['workflow-06']['groups'][0]['before'][0]['origin']=='header-footer','Header/footer evidence missing'))
    check('Textbox edit has actual textbox source evidence',lambda:require(results['workflow-05']['groups'][0]['before'][0]['origin']=='textbox','Textbox edit inferred from body'))
    check('An old value introduced in a new appendix blocks completion',lambda:require(any(e['newlyUnpaired'] for e in results['ambiguity-03']['remainingOld']),'New residual not found'))
    check('Matching names in another role do not count as targeted residuals',lambda:require(results['ambiguity-04']['status']=='modified' and results['ambiguity-04']['counts']['afterOldOccurrences']==0,'Scope includes unrelated role'))
    duplicate=results['ambiguity-05']['groups'][0]
    check('Identical duplicates reviewed as a set without invented lineage',lambda:require(duplicate['method']=='multiset-context' and len(duplicate['before'])==len(duplicate['after'])==2 and duplicate['verifiedChanged']==2,'Duplicate set wrong'))
    check('One-to-many and split paragraph edits abstain',lambda:require(results['ambiguity-01']['status']==results['ambiguity-02']['status']=='undetermined' and len(results['ambiguity-01']['groups'][0]['after'])==2,'Ambiguous lineage forced'))
    check('Image coverage is not silently converted into full-document completion',lambda:require(results['coverage-01']['status']=='undetermined' and results['coverage-01']['imageReferences']['after'] and results['coverage-02']['status']=='modified','Coverage scope incorrect'))
    check('Target new value appearing in an unrelated reference does not prove an edit',lambda:require(results['vocabulary-04']['status']=='unmodified','Unrelated target value accepted'))
    check('Deletion cannot pass as successful replacement',lambda:require(results['workflow-07']['status']=='undetermined' and not results['workflow-07']['groups'][0]['after'],'Deletion interpreted as replacement'))

    # A real derived package retains old text in an unsupported internal altChunk.
    # The explicit body-text scope must not erase that coverage gap.
    from lxml import etree
    chunk_sources=[]
    for side in ['before','after']:
        with ZipFile(fixtures/f'vocabulary-{side}.docx') as z:parts={n:z.read(n) for n in z.namelist()}
        uri='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        rel_uri='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        root=etree.fromstring(parts['word/document.xml']);body=root.find(f'{{{uri}}}body')
        chunk=etree.Element(f'{{{uri}}}altChunk');chunk.set(f'{{{rel_uri}}}id','rIdOfflineChunk');body.insert(len(body)-1,chunk)
        parts['word/document.xml']=etree.tostring(root)
        rels=etree.fromstring(parts['word/_rels/document.xml.rels'])
        etree.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',Id='rIdOfflineChunk',Type=rel_uri+'/aFChunk',Target='offline-chunk.html')
        parts['word/_rels/document.xml.rels']=etree.tostring(rels)
        types=etree.fromstring(parts['[Content_Types].xml'])
        etree.SubElement(types,'{http://schemas.openxmlformats.org/package/2006/content-types}Override',PartName='/word/offline-chunk.html',ContentType='text/html')
        parts['[Content_Types].xml']=etree.tostring(types)
        parts['word/offline-chunk.html']='<html><body>合同项目：南桥修复工程。</body></html>'.encode()
        source=out/f'{side}-unsupported-chunk.bin'
        with ZipFile(source,'w',ZIP_DEFLATED) as z:
            for name,raw in parts.items():z.writestr(name,raw)
        chunk_sources.append(source)
    chunk_report=review_pair(*chunk_sources,[cases[3]['opinions'][0]])
    check('Unsupported editable body content is disclosed',lambda:require('embedded_alt_chunk' in chunk_report['results'][0]['coverageGaps'],'Body scope dropped an unsupported content gap'))
    check('Unsupported body content prevents false completion',lambda:require(chunk_report['results'][0]['status']=='undetermined','Embedded body text silently ignored'))

    case=cases[0];base=reports['workflow'];before=fixtures/case['before'];after=fixtures/case['after']
    def rejection(fn,expected):
        try:fn()
        except ValueError as error:
            require(str(error)==expected,f'Expected {expected}, got {error}');return
        raise AssertionError('Invalid report/evidence accepted')
    check('Swapping old and new files invalidates report versions',lambda:rejection(lambda:validate_report(after,before,case['opinions'],base),'report_source_version_mismatch'))
    changed_opinions=deepcopy(case['opinions']);changed_opinions[0]['text']='另一条意见'
    check('Editing the opinion list invalidates the old report',lambda:rejection(lambda:validate_report(before,after,changed_opinions,base),'report_opinion_version_mismatch'))
    for issue_id in ['workflow-01','workflow-05','workflow-06']:
        ev=deepcopy(results[issue_id]['groups'][0]['before'][0])
        check(issue_id+': before evidence cannot resolve against new version',lambda ev=ev:rejection(lambda:verify_evidence(after,ev),'source_version_mismatch'))
    fake=deepcopy(base);fake['results'][0]['groups'][0]['after'][0]['reference']['quote']='模型编造的原文'
    check('Fabricated before/after quote rejected',lambda:rejection(lambda:validate_report(before,after,case['opinions'],fake),'quote_does_not_match_original'))
    fake_picture=deepcopy(reports['coverage']);fake_picture['results'][0]['imageReferences']['after'][0]['mediaPart']='word/media/not-real.png'
    check('Fabricated scan reference rejected',lambda:rejection(lambda:validate_report(fixtures/'coverage-before.docx',fixtures/'coverage-after.docx',cases[2]['opinions'],fake_picture),'report_picture_reference_mismatch'))
    false_complete=sum(r['actualStatus']=='modified' and r['truthStatus']!='modified' for r in rows)
    check('No human-labeled incomplete or unknown issue marked complete',lambda:require(false_complete==0,'False completion occurred'))
    confusion=Counter((r['truthStatus'],r['actualStatus']) for r in rows)
    summary={'synthetic':True,'pairs':len(cases),'opinions':len(rows),'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),
             'decisionCounts':dict(Counter(r['actualStatus'] for r in rows)),
             'exactHumanTruthAgreement':sum(r['truthStatus']==r['actualStatus'] for r in rows),
             'conservativeAbstentionsOnKnownTruth':sum(r['actualStatus']=='undetermined' and r['truthStatus']!='undetermined' for r in rows),
             'falseModifiedCount':false_complete,'textEvidenceRoundTrips':reference_count,
             'confusionMatrix':[{'human':human,'actual':actual,'count':count} for (human,actual),count in confusion.items()],
             'rows':rows,'checks':checks,'method':'limited deterministic exact replacement rules; no model inference',
             'businessIntegrated':False,'realCustomerFilesVerified':False,'naturalLanguageGeneralizationVerified':False,
             'ocrIntegrated':False,'wordLayoutRendered':False}
    (out/'review-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in {'rows','checks','confusionMatrix'}},ensure_ascii=False,indent=2))
    if summary['failed']:
        print(json.dumps([c for c in checks if not c['passed']],ensure_ascii=False,indent=2));raise SystemExit(1)


if __name__=='__main__':main()
