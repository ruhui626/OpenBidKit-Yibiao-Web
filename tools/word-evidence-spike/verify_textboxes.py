"""Authored text expectations, independent XML lookup, negative evidence and parser comparison."""
import argparse
import copy
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from extract import PART, digest, extract
from header_footer import extract_header_footer
from textboxes import extract_textboxes, textbox_evidence, resolve_textbox


def run(fixtures, output, repo, node):
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixtures / 'textbox-manifest.json').read_text(encoding='utf-8'))
    documents, checks, examples = {}, [], []

    def require(ok, reason):
        if not ok:
            raise AssertionError(reason)

    def check(name, fn):
        try:
            fn()
            checks.append({'name': name, 'passed': True})
        except Exception as error:
            checks.append({'name': name, 'passed': False, 'error': f'{type(error).__name__}: {error}'})

    def independent(source, block):
        with ZipFile(source) as z:
            root = ET.fromstring(z.read(block['part']))
        node = root.find('./' + '/'.join(block['xpath'].split('/')[2:]), block['namespaces'])
        require(node is not None, 'Independent XML lookup failed')
        uri = root.tag[1:].split('}')[0]
        pieces = []
        def visit(item):
            local = item.tag.rsplit('}', 1)[-1]
            if item is not node and item.tag in {f'{{{uri}}}p', f'{{{uri}}}txbxContent', f'{{{uri}}}del', f'{{{uri}}}moveFrom'}:
                return
            if item.tag == f'{{{uri}}}t': pieces.append(item.text or '')
            if item.tag == f'{{{uri}}}tab': pieces.append('\t')
            if item.tag in {f'{{{uri}}}br', f'{{{uri}}}cr'}: pieces.append('\n')
            for child in item: visit(child)
        visit(node)
        require(''.join(pieces) == block['text'], 'Independent source text differs')

    for name, spec in manifest.items():
        source = fixtures / name
        document = extract_textboxes(source)
        documents[name] = document
        (output / (source.stem + '.structure.json')).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        check(name + ': authored textbox count including empty', lambda: require(len(document['boxes']) == len(spec['boxes']), 'Wrong box count'))
        check(name + ': authored nonempty paragraph count', lambda: require(len(document['blocks']) == len(spec['expected']), 'Wrong block count'))
        check(name + ': alternative copy comparisons', lambda: require([g['paragraphTextsAgree'] for g in document['alternateGroups']] == spec['expectedGroupsAgree'] and all(g['displayedBranch'] is None for g in document['alternateGroups']), 'Alternative content lost or assumed visible'))
        check(name + ': unused header excluded and disclosed', lambda: require(document['unreferencedHeaderFooterParts'] == spec['unreferencedParts'] and all(b['part'] not in spec['unreferencedParts'] for b in document['blocks']), 'Unused header included'))
        check(name + ': distinct IDs and exact source hash', lambda: require(len({b['id'] for b in document['blocks']}) == len(document['blocks']) and document['byteHash'] == digest(source.read_bytes()), 'IDs or source hash incorrect'))
        for i, expected in enumerate(spec['expected'], 1):
            def authored(expected=expected):
                candidates = [b for b in document['blocks'] if b['part'] == expected['part'] and b['text'] == expected['text'] and all(b['textbox'].get(k) == expected[k] for k in ['representation', 'drawingId', 'shapeId'] if k in expected)]
                require(len(candidates) == 1, f'Expected text/box not found uniquely: {expected}')
                block = candidates[0]
                if 'gridColumn' in expected:
                    require(len(block['tablePath']) == 1 and block['tablePath'][0]['gridColumn'] == expected['gridColumn'] and block['textbox']['anchorTablePath'][0]['gridColumn'] == 1, 'Inside and outside table positions mixed')
                if 'flag' in expected:
                    require(expected['flag'] in block['flags'], 'Missing review flag')
            check(f'{name}: authored content {i}', authored)
        for block in document['blocks']:
            def roundtrip(block=block):
                ev = textbox_evidence(document, block, block['text'])
                require(resolve_textbox(source, ev)['text'] == block['text'], 'Wrong original text')
                independent(source, block)
            check(f'{name}: source roundtrip {block["id"]}', roundtrip)
        legacy_body = extract(source)
        legacy_hf = extract_header_footer(source)
        markers = [e['text'] for e in spec['expected']]
        check(name + ': original indexes do not merge textbox text into anchor paragraphs', lambda: require(not any(marker in b['text'] for marker in markers for b in [*legacy_body['blocks'], *legacy_hf['blocks']]), 'Anchor paragraph includes textbox content'))
        check(name + ': source unchanged after extraction', lambda: require(document['byteHash'] == digest(source.read_bytes()), 'Fixture mutated'))

    before = documents['textboxes-before.docx']
    after = documents['textboxes-after.docx']
    source = fixtures / 'textboxes-before.docx'
    ev = textbox_evidence(before, before['blocks'][0], before['blocks'][0]['text'])
    detached = textbox_evidence(before, before['blocks'][0], before['blocks'][0]['text'])
    detached['namespaces']['w'] = 'urn:modified-output'
    detached['textbox']['boxId'] = 'modified-output'
    check('Changing returned evidence cannot mutate the extracted index', lambda: require(before['blocks'][0]['namespaces']['w'] != 'urn:modified-output' and before['blocks'][0]['textbox']['boxId'] != 'modified-output', 'Returned evidence shares mutable index data'))

    def rejected(source, evidence, reason):
        try:
            resolve_textbox(source, evidence)
        except ValueError as error:
            require(str(error) == reason, f'Expected {reason}, got {error}')
            return
        raise AssertionError('Invalid evidence accepted')

    check('Evidence bound to exact original version', lambda: rejected(fixtures / 'textboxes-after.docx', ev, 'source_version_mismatch'))
    fake = copy.deepcopy(ev); fake['quote'] = fake['quote'].replace('旧路', '新路')
    check('Fabricated quote rejected', lambda: rejected(source, fake, 'quote_does_not_match_original'))
    fake_context = copy.deepcopy(ev); fake_context['textbox']['boxId'] = 'fabricated'
    check('Fabricated textbox context rejected', lambda: rejected(source, fake_context, 'textbox_context_mismatch'))
    fake_ns = copy.deepcopy(ev); fake_ns['namespaces']['w'] = 'urn:wrong'
    check('Fabricated namespace mapping rejected', lambda: rejected(source, fake_ns, 'textbox_context_mismatch'))
    fake_range = copy.deepcopy(ev); fake_range['start'] = True
    check('Boolean offset rejected', lambda: rejected(source, fake_range, 'invalid_range'))
    body_block = extract(source)['blocks'][0]
    fake_body = copy.deepcopy(ev); fake_body.update(xpath=body_block['xpath'], blockId=body_block['id'])
    check('Body paragraph cannot impersonate textbox evidence', lambda: rejected(source, fake_body, 'locator_not_an_indexed_textbox_paragraph'))
    repeated = [b for b in before['blocks'] if b['text'] == '同名重复文本']
    check('Same text in separate boxes stays distinct', lambda: require(len(repeated) == 2 and repeated[0]['textbox']['boxId'] != repeated[1]['textbox']['boxId'] and repeated[0]['id'] != repeated[1]['id'], 'Duplicate boxes collapsed'))
    twin = [b for b in before['blocks'] if b['text'].startswith('兼容一致：')]
    swapped = textbox_evidence(before, twin[0], twin[0]['text'])
    swapped.update(part=twin[1]['part'], xpath=twin[1]['xpath'], namespaces=twin[1]['namespaces'], blockId=twin[1]['id'])
    check('Compatibility copy cannot inherit another box context', lambda: rejected(source, swapped, 'textbox_context_mismatch'))
    hf = next(b for b in before['blocks'] if b['part'] != PART)
    wrong_use = textbox_evidence(before, hf, hf['text']); wrong_use['textbox']['uses'][0]['section'] = 99
    check('Forged header section context rejected', lambda: rejected(source, wrong_use, 'textbox_context_mismatch'))
    check('Inherited header physical textbox extracted once with two section uses', lambda: require([u['section'] for u in hf['textbox']['uses']] == [1, 2] and len([b for b in before['blocks'] if b['part'] == hf['part']]) == 1, 'Inherited header duplicated or lost'))
    edge = documents['textboxes-edges.docx']; edge_source = fixtures / 'textboxes-edges.docx'
    emoji = next(b for b in edge['blocks'] if b['text'].startswith('前缀😀'))
    partial = textbox_evidence(edge, emoji, '工程\t名称')
    check('Unicode code-point offset and tab/newline extraction', lambda: require(partial['start'] == 4 and resolve_textbox(edge_source, partial)['quote'] == '工程\t名称', 'Unicode offset incorrect'))
    ambiguous = next(b for b in edge['blocks'] if b['text'] == '同名/同名')
    def ambiguity():
        try:
            textbox_evidence(edge, ambiguous, '同名')
        except ValueError as error:
            require(str(error) == 'quote_must_be_unique_within_block', 'Wrong ambiguity error'); return
        raise AssertionError('Ambiguous quote accepted')
    check('Repeated quote within a paragraph requires disambiguation', ambiguity)
    fake_unused = textbox_evidence(edge, emoji, emoji['text']); fake_unused['part'] = 'word/unused-textbox-header.xml'
    check('Unused header cannot impersonate used textbox', lambda: rejected(edge_source, fake_unused, 'locator_not_an_indexed_textbox_paragraph'))
    check('Linked textbox and non-container drawing text disclosed', lambda: require({c['reason'] for c in edge['coverage']['uncovered']} == {'linked_textbox_page_distribution_unverified', 'drawing_text_outside_w_txbxContent', 'vml_textpath_outside_w_txbxContent'}, 'Uncovered drawing scope lost'))
    check('Empty textbox recorded but not invented as text', lambda: require(len([b for b in edge['boxes'] if not b['blockIds']]) == 1, 'Empty box lost'))
    for block in after['blocks']:
        if '旧路' in block['text']:
            examples.append({'sourceName': 'textboxes-after.docx', 'evidence': textbox_evidence(after, block, '旧路'), 'visibility': 'stored-content-only'})
    check('Changed body still leaves textbox evidence', lambda: require('新路' in ''.join(b['text'] for b in extract(fixtures / 'textboxes-after.docx')['blocks']) and any(e['evidence']['textbox']['representation'] == 'vml' for e in examples) and any(e['evidence']['textbox']['alternateContexts'] for e in examples), 'Residue case missing'))

    comparison = output / 'current-parser.json'
    completed = subprocess.run([str(node), '--import', 'tsx', str(repo / 'tools/word-evidence-spike/compare-current.mjs'), str(repo), str(fixtures), str(comparison), *manifest], cwd=repo / 'server', capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    current = json.loads(comparison.read_text(encoding='utf-8')) if comparison.exists() else {'reports': [], 'error': completed.stderr[-1200:]}
    current_summary = []
    for report in current.get('reports', []):
        name = report.get('sourceName')
        if name not in documents:
            current_summary.append({'stage': report.get('stage'), 'ok': report.get('ok'), 'error': report.get('error')}); continue
        content = report.get('markdown', report.get('content', ''))
        if not isinstance(content, str): content = json.dumps(content, ensure_ascii=False)
        normalized = content.replace('**', '').replace('__', '')
        texts = sorted(set(b['text'] for b in documents[name]['blocks']))
        current_summary.append({'sourceName': name, 'ok': report.get('ok'), 'fields': report.get('fields'),
                                'parserLabel': report.get('parserLabel'),
                                'exactTextboxParagraphsFound': [t for t in texts if t in content],
                                'exactTextboxParagraphsMissing': [t for t in texts if t not in content],
                                'formattingNormalizedParagraphsFound': [t for t in texts if t in normalized],
                                'formattingNormalizedParagraphsMissing': [t for t in texts if t not in normalized],
                                'sourceEvidenceReturned': any(k in report for k in ['blocks', 'locations', 'evidence', 'sourceMap'])})
    check('Current parser comparison completed for all fixtures', lambda: require(completed.returncode == 0 and len(current_summary) == len(manifest) and all(r['ok'] for r in current_summary), 'Current parser comparison failed'))
    for name, document in documents.items():
        check(name + ': file unchanged after current parser', lambda name=name, document=document: require(digest((fixtures / name).read_bytes()) == document['byteHash'], 'Original changed'))
    summary = {'synthetic': True, 'passed': sum(c['passed'] for c in checks), 'failed': sum(not c['passed'] for c in checks),
               'files': [{'sourceName': n, 'sha256': d['byteHash'], 'textboxContainers': len(d['boxes']), 'nonemptyBlocks': len(d['blocks']), 'alternateGroups': len(d['alternateGroups'])} for n, d in documents.items()],
               'totalBlocks': sum(len(d['blocks']) for d in documents.values()),
               'totalTextboxContainers': sum(len(d['boxes']) for d in documents.values()),
               'currentParser': current_summary, 'examples': examples, 'checks': checks,
               'businessIntegrated': False, 'paidModelCalls': False, 'renderVerified': False,
               'pageNumbersVerified': False, 'customerFilesVerified': False, 'displayedBranchesVerified': False}
    (output / 'textbox-verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k not in {'checks', 'examples'}}, ensure_ascii=False, indent=2))
    if summary['failed']:
        print(json.dumps([c for c in checks if not c['passed']], ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for key in ['fixtures', 'output', 'repo', 'node']: p.add_argument('--' + key, type=Path, required=True)
    run(**{key: value.resolve() for key, value in vars(p.parse_args()).items()})
