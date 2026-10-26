"""Separate structural assertions for headers/footers; no GUI, DB, model or network."""
import argparse
import copy
import json
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET

from lxml import etree

from extract import PART, digest
from header_footer import extract_header_footer, header_footer_evidence, resolve_header_footer, hf_block_id


def run(fixtures, output, repo, node):
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixtures / 'header-footer-manifest.json').read_text(encoding='utf-8'))
    checks, documents, examples = [], {}, []

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def check(name, fn):
        try:
            fn()
            checks.append({'name': name, 'passed': True})
        except Exception as error:
            checks.append({'name': name, 'passed': False, 'error': f'{type(error).__name__}: {error}'})

    def independent(source, block):
        with ZipFile(source) as package:
            root = ET.fromstring(package.read(block['part']))
        require(root.find('./' + '/'.join(block['xpath'].split('/')[2:]), block['namespaces']) is not None,
                'Independent standard-library XML lookup did not find the paragraph')

    for name, spec in manifest.items():
        source = fixtures / name
        document = extract_header_footer(source)
        documents[name] = document
        (output / f'{source.stem}.structure.json').write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        check(f'{name}: active section inventory', lambda: require(document['sectionCount'] == spec['sectionCount'], 'Wrong section count'))
        check(f'{name}: unreferenced parts disclosed but not treated as used', lambda: require(document['unreferencedParts'] == spec['unreferencedParts'] and all(b['part'] not in spec['unreferencedParts'] for b in document['blocks']), 'Unused header/footer mixed into used content'))
        for i, expected in enumerate(spec['expectations'], 1):
            def verify_authored(expected=expected):
                matches = [b for b in document['blocks'] if b['part'] == expected['part'] and b['text'] == expected['text']]
                require(len(matches) == 1, f'Authored text not located uniquely: {expected}')
                block = matches[0]
                if 'table' in expected:
                    require(block['tablePath'] and all(block['tablePath'][-1][k] == v for k, v in expected['table'].items()), 'Header/footer cell coordinates differ')
                if 'flag' in expected:
                    require(expected['flag'] in block['flags'], 'Dynamic field not marked for review')
                require(resolve_header_footer(source, header_footer_evidence(document, block, expected['text']))['text'] == expected['text'], 'Source quote differs')
                independent(source, block)
            check(f'{name}: authored paragraph/cell {i}', verify_authored)
        for i, expected in enumerate(spec['bindings'], 1):
            def verify_binding(expected=expected):
                matches = [b for b in document['bindings'] if all(b[k] == expected[k] for k in ['section', 'kind', 'variant'])]
                require(len(matches) == 1 and all(matches[0].get(k) == v for k, v in expected.items()), f'Wrong binding: {expected}; actual={matches}')
            check(f'{name}: authored section binding {i}', verify_binding)
        for block in document['blocks']:
            def round_trip(block=block):
                ev = header_footer_evidence(document, block, block['text'])
                require(resolve_header_footer(source, ev)['text'] == block['text'], 'Original part text differs')
                independent(source, block)
            check(f"{name}: original-part locator {block['id']}", round_trip)
        if 'duplicateQuote' in spec:
            repeated = [b for b in document['blocks'] if b['text'] == spec['duplicateQuote']]
            check(f'{name}: identical quotes and XPath remain separate by part', lambda: require(len(repeated) == spec['duplicateCount'] and len({b['id'] for b in repeated}) == len(repeated) and len({b['xpath'] for b in repeated}) < len(repeated), 'Part identity missing or identical text collapsed'))
            footer = spec['inheritedDefaultFooterPart']
            check(f'{name}: one footer maps to three sections without duplicating physical blocks', lambda: require([u['section'] for u in document['uses'][footer]] == [1, 2, 3] and [u['inherited'] for u in document['uses'][footer]] == [False, True, True], 'Inherited footer ownership wrong'))
            check(f'{name}: same first header enabled in section1 but disabled in section2', lambda: require([u['enabledBySettings'] for u in document['uses'][spec['firstHeaderPart']]] == [True, False], 'Inactive first-page definition treated as visible'))
        if name == 'headers-after.docx':
            for kind, quote in [('header', '页眉首页：演示旧路维修工程'), ('footer', '页脚默认：演示旧路维修工程')]:
                block = next(b for b in document['blocks'] if b['text'] == quote and b['kind'] == kind)
                examples.append({'label': '正文已改但该处仍留旧项目名', 'sourceName': name, 'evidence': header_footer_evidence(document, block, quote), 'tablePath': block['tablePath']})

    before = documents['headers-before.docx']
    source = fixtures / 'headers-before.docx'
    block = next(b for b in before['blocks'] if b['text'].startswith('页眉首页：'))
    ev = header_footer_evidence(before, block, block['text'])

    def rejected(source, evidence, reason):
        try:
            resolve_header_footer(source, evidence)
        except ValueError as error:
            require(str(error) == reason, f'Expected {reason}, got {error}')
            return
        raise AssertionError('Invalid evidence accepted')

    check('Changed original file rejected', lambda: rejected(fixtures / 'headers-after.docx', ev, 'source_version_mismatch'))
    fake = copy.deepcopy(ev)
    fake['quote'] = fake['quote'].replace('旧路', '新路')
    check('Fabricated header quote rejected', lambda: rejected(source, fake, 'quote_does_not_match_original'))
    fake_use = copy.deepcopy(ev)
    fake_use['uses'][0]['section'] = 999
    check('Fabricated section ownership rejected', lambda: rejected(source, fake_use, 'header_footer_binding_mismatch'))
    body_part = copy.deepcopy(ev)
    body_part['part'] = PART
    check('Body part cannot impersonate a header', lambda: rejected(source, body_part, 'part_not_referenced_header_footer'))
    ghost = copy.deepcopy(ev)
    ghost['part'] = 'word/unused-header.xml'
    check('Unreferenced header cannot impersonate displayed content', lambda: rejected(source, ghost, 'part_not_referenced_header_footer'))
    repeated = [b for b in before['blocks'] if b['text'] == '重复标记：待核对。' and b['kind'] == 'header']
    swapped = header_footer_evidence(before, repeated[0], repeated[0]['text'])
    swapped['part'] = repeated[1]['part']
    swapped['blockId'] = hf_block_id(before['byteHash'], swapped['part'], swapped['xpath'])
    check('Same quote in another header cannot reuse section context', lambda: rejected(source, swapped, 'header_footer_binding_mismatch'))

    with ZipFile(source) as archive:
        members = {n: archive.read(n) for n in archive.namelist()}
    with tempfile.TemporaryDirectory(prefix='header-footer-negative-') as temporary:
        temporary = Path(temporary).resolve()
        require(temporary.is_relative_to(Path(tempfile.gettempdir()).resolve()) and temporary.name.startswith('header-footer-negative-'), 'Temporary path boundary failed')
        first_ref_root = etree.fromstring(members[PART])
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        ref = first_ref_root.xpath('.//w:headerReference', namespaces=ns)[0]
        rid = ref.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        default_part = manifest['headers-before.docx']['defaultHeaderPart']
        negative_cases = {
            'missing-relationship': 'header_footer_relationship_missing',
            'external-relationship': 'header_footer_relationship_external',
            'wrong-relationship-type': 'header_footer_relationship_type_mismatch',
            'missing-part': 'header_footer_part_missing',
            'wrong-root': 'header_footer_part_root_mismatch',
            'wrong-content-type': 'header_footer_content_type_mismatch',
            'package-escape': 'header_footer_target_outside_package',
            'duplicate-reference': 'duplicate_header_footer_reference',
        }
        for label, reason in negative_cases.items():
            changed = dict(members)
            doc, rels, types = (etree.fromstring(changed[n]) for n in [PART, 'word/_rels/document.xml.rels', '[Content_Types].xml'])
            rel = next(r for r in rels if r.get('Id') == rid)
            if label == 'missing-relationship':
                rels.remove(rel)
            elif label == 'external-relationship':
                rel.set('TargetMode', 'External'); rel.set('Target', 'https://example.invalid/not-fetched')
            elif label == 'wrong-relationship-type':
                rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image')
            elif label == 'missing-part':
                changed.pop(default_part)
            elif label == 'wrong-root':
                changed[default_part] = b'<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
            elif label == 'wrong-content-type':
                next(n for n in types if n.get('PartName') == '/' + default_part).set('ContentType', 'application/xml')
            elif label == 'package-escape':
                rel.set('Target', '../../../outside.xml')
            elif label == 'duplicate-reference':
                original = doc.xpath('.//w:headerReference', namespaces=ns)[0]
                original.getparent().append(copy.deepcopy(original))
            for name, tree in [(PART, doc), ('word/_rels/document.xml.rels', rels), ('[Content_Types].xml', types)]:
                changed[name] = etree.tostring(tree, encoding='UTF-8', xml_declaration=True)
            candidate = temporary / (label + '.bin')
            with ZipFile(candidate, 'w', ZIP_DEFLATED) as archive:
                for name, data in changed.items():
                    archive.writestr(name, data)
            def reject_package(candidate=candidate, reason=reason):
                try:
                    extract_header_footer(candidate)
                except ValueError as error:
                    require(str(error) == reason, f'Expected {reason}, got {error}')
                    return
                raise AssertionError('Malformed relationship silently accepted')
            check('Relationship validation: ' + label, reject_package)

    current_file = output / 'current-parser.json'
    proc = subprocess.run([str(node), '--import', 'tsx', str(Path(__file__).with_name('compare-current.mjs')), str(repo), str(fixtures), str(current_file), *manifest], cwd=repo / 'server', capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    reports = json.loads(current_file.read_text(encoding='utf-8'))['reports'] if current_file.exists() else []
    current = []
    for name, document in documents.items():
        parsed = next((r for r in reports if r.get('sourceName') == name), {})
        check(f'{name}: existing parser completes', lambda parsed=parsed: require(parsed.get('ok'), f'Current parser failed: {parsed}'))
        markdown = parsed.get('markdown', '')
        current.append({'sourceName': name, 'ok': bool(parsed.get('ok')), 'hasLocators': 'blocks' in parsed,
                        'headerMarkerFound': '页眉首页：' in markdown or '开关样例默认页眉' in markdown,
                        'footerMarkerFound': '页脚默认：' in markdown or '开关样例默认页脚' in markdown})
        check(f'{name}: original bytes unchanged', lambda name=name, document=document: require(digest((fixtures / name).read_bytes()) == document['byteHash'], 'A reader modified the fixture'))
    result = {'synthetic': True, 'passed': sum(c['passed'] for c in checks), 'failed': sum(not c['passed'] for c in checks),
              'checks': checks, 'fixtureCount': len(documents), 'blockCounts': {n: len(d['blocks']) for n, d in documents.items()},
              'originalPartRoundTrips': sum(len(d['blocks']) for d in documents.values()),
              'sectionBindings': sum(len(d['bindings']) for d in documents.values()), 'authoredExpectations': sum(len(s['expectations']) for s in manifest.values()),
              'sourceHashes': {n: d['byteHash'] for n, d in documents.items()}, 'currentParser': current,
              'currentParserProcessExit': proc.returncode, 'examples': examples, 'renderVerified': False,
              'pageNumbersVerified': False, 'customerFilesVerified': False, 'businessIntegrated': False}
    (output / 'header-footer-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['passed', 'failed', 'blockCounts', 'originalPartRoundTrips', 'sectionBindings', 'currentParser']}, ensure_ascii=False))
    if result['failed']:
        print(json.dumps([c for c in checks if not c['passed']], ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    args = parser.parse_args()
    run(args.fixtures.resolve(), args.output.resolve(), args.repo.resolve(), args.node.resolve())
