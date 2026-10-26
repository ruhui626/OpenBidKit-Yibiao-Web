"""Fixture assertions plus independent stdlib XML lookup against original bytes."""
import argparse
import copy
import json
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from extract import extract, evidence_for, resolve, digest, block_id, PART


def run(fixtures, output, repo, node):
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixtures / 'manifest.json').read_text(encoding='utf-8'))
    documents, checks, examples = {}, [], []

    def check(name, fn):
        try:
            fn()
            checks.append({'name': name, 'passed': True})
        except Exception as error:
            checks.append({'name': name, 'passed': False, 'error': f'{type(error).__name__}: {error}'})

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def reject(source, evidence, expected):
        try:
            resolve(source, evidence)
        except ValueError as error:
            require(str(error) == expected, f'Expected {expected}, got {error}')
            return
        raise AssertionError('Invalid evidence was accepted')

    def matching(document, expected):
        matches = []
        for block in document['blocks']:
            if block['text'] != expected['text'] or ('kind' in expected and block['kind'] != expected['kind']):
                continue
            chain = block['tablePath']
            if 'tableDepth' in expected and len(chain) != expected['tableDepth']:
                continue
            if any(key in expected for key in ['tableIndex', 'xmlRow', 'gridColumn', 'gridSpan', 'verticalMerge']):
                if not chain or any(chain[-1].get(k) != expected[k] for k in ['tableIndex', 'xmlRow', 'gridColumn', 'gridSpan', 'verticalMerge'] if k in expected):
                    continue
            if 'requiredFlag' in expected and expected['requiredFlag'] not in block['flags']:
                continue
            matches.append(block)
        return matches

    def independent_lookup(source, block):
        with ZipFile(source) as package:
            root = ET.fromstring(package.read(PART))
        steps = block['xpath'].split('/')[2:]
        node = root.find('./' + '/'.join(steps), block['namespaces'])
        require(node is not None, f"Independent XPath did not locate {block['xpath']}")
        require(node.tag.endswith('}p'), 'Not a paragraph in original XML')
        return node

    for name, spec in manifest.items():
        source = fixtures / name
        document = extract(source)
        documents[name] = document
        (output / f'{source.stem}.structure.json').write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        check(f'{name}: expected table count', lambda: require(document['tableCount'] == spec['expectedTableCount'], 'Table inventory differs'))
        for index, expected in enumerate(spec['expectations'], 1):
            def verify_expected(expected=expected):
                found = matching(document, expected)
                require(len(found) == 1, f'Expected one match for {expected}, got {len(found)}')
                actual = resolve(source, evidence_for(document, found[0], expected['text']))
                require(actual['text'] == expected['text'], 'Original paragraph text differs from authored expectation')
                independent_lookup(source, found[0])
            check(f'{name}: authored expectation {index}', verify_expected)
        for block in document['blocks']:
            def round_trip(block=block):
                evidence = evidence_for(document, block, block['text'])
                require(resolve(source, evidence)['text'] == block['text'], 'Evidence round trip changed text')
                independent_lookup(source, block)
            check(f"{name}: original locator {block['id']}", round_trip)
        for excluded in spec.get('mustNotInclude', []):
            check(f'{name}: uncovered text excluded: {excluded}', lambda excluded=excluded: require(all(excluded not in b['text'] for b in document['blocks']), 'Uncovered material was included as supported text'))
        if 'duplicateQuote' in spec:
            found = [b for b in document['blocks'] if b['text'] == spec['duplicateQuote']]
            check(f'{name}: repeated text has separate original positions', lambda: require(len(found) == spec['duplicateCount'] and len({b['xpath'] for b in found}) == len(found), 'Repeated text collapsed'))
            for b in found:
                examples.append({'sourceName': name, 'label': '重复文字的不同位置', 'evidence': evidence_for(document, b, b['text']), 'tablePath': b['tablePath'], 'headingPath': b['headingPath']})
        if name != 'edges.docx':
            b = next(b for b in document['blocks'] if b['text'] == '示例甲' and b['tablePath'][-1]['tableIndex'] == 1)
            examples.append({'sourceName': name, 'label': '人员表里的未改姓名', 'evidence': evidence_for(document, b, b['text']), 'tablePath': b['tablePath'], 'headingPath': b['headingPath']})

    before, after, edges = (documents[n] for n in ['before.docx', 'after.docx', 'edges.docx'])
    b = next(b for b in before['blocks'] if b['text'].startswith('项目名称：'))
    evidence = evidence_for(before, b, '演示旧路维修工程')
    check('Old evidence rejects changed source version', lambda: reject(fixtures / 'after.docx', evidence, 'source_version_mismatch'))
    tampered = copy.deepcopy(evidence)
    tampered['quote'] = '虚构不存在的项目'
    check('Fabricated quotation rejected', lambda: reject(fixtures / 'before.docx', tampered, 'quote_does_not_match_original'))
    wrong_path = copy.deepcopy(evidence)
    wrong_path['xpath'] = '/w:document[1]/w:body[1]/w:p[9999]'
    wrong_path['blockId'] = block_id(before['byteHash'], wrong_path['xpath'])
    check('Nonexistent paragraph rejected', lambda: reject(fixtures / 'before.docx', wrong_path, 'locator_not_a_unique_paragraph'))
    unsafe = copy.deepcopy(evidence)
    unsafe['xpath'] = '//w:p'
    check('Non-generated broad XPath rejected', lambda: reject(fixtures / 'before.docx', unsafe, 'invalid_locator'))
    wrong_range = copy.deepcopy(evidence)
    wrong_range['end'] = 999999
    check('Out-of-bounds quotation offsets rejected', lambda: reject(fixtures / 'before.docx', wrong_range, 'invalid_range'))
    unicode_block = next(b for b in edges['blocks'] if b['text'].startswith('现场🌧️'))
    unicode_evidence = evidence_for(edges, unicode_block, '🌧️')
    check('Unicode offsets explicitly use code points', lambda: require(unicode_evidence['end'] - unicode_evidence['start'] == 2 and resolve(fixtures / 'edges.docx', unicode_evidence)['quote'] == '🌧️', 'Unicode offsets shifted'))
    check('Repeated block IDs not reused across file versions', lambda: require(not ({b['id'] for b in before['blocks']} & {b['id'] for b in after['blocks']}), 'IDs escaped file-version binding'))
    check('Boundary coverage disclosed', lambda: require({'headers', 'footers', 'footnotes', 'image_or_drawing_contents', 'textboxes', 'tracked_changes_semantics', 'dynamic_field_semantics'} <= set(edges['coverage']['uncovered']), 'A known unsupported part was not disclosed'))

    with tempfile.TemporaryDirectory(prefix='word-evidence-negative-') as temporary:
        temporary = Path(temporary)
        same = temporary / 'renamed-package.bin'
        same.write_bytes((fixtures / 'before.docx').read_bytes())
        check('Renaming same bytes preserves valid evidence', lambda: require(resolve(same, evidence)['quote'] == evidence['quote'], 'Filename incorrectly used as identity'))
        snapshot = temporary / 'changing-source.bin'
        snapshot.write_bytes((fixtures / 'before.docx').read_bytes())
        class ChangingSource:
            name = snapshot.name
            def stat(self):
                return snapshot.stat()
            def read_bytes(self):
                raw = snapshot.read_bytes()
                snapshot.write_bytes((fixtures / 'after.docx').read_bytes())
                return raw
            def __fspath__(self):
                return str(snapshot)
        def snapshot_consistency():
            captured = extract(ChangingSource())
            require(captured['byteHash'] == before['byteHash'], 'Hash was not from captured bytes')
            require([b['text'] for b in captured['blocks']] == [b['text'] for b in before['blocks']], 'Hash and extracted content came from different snapshots')
        check('Hash and XML read from the same byte snapshot', snapshot_consistency)
        with ZipFile(fixtures / 'before.docx') as original:
            members = {n: original.read(n) for n in original.namelist()}
        aliased = temporary / 'prefix-alias.bin'
        with ZipFile(aliased, 'w') as archive:
            for n, data in members.items():
                if n == PART:
                    data = data.replace(b'xmlns:w=', b'xmlns:x=').replace(b'<w:', b'<x:').replace(b'</w:', b'</x:').replace(b' w:', b' x:')
                archive.writestr(n, data)
        alias_doc = extract(aliased)
        check('Word namespace URI independent from w prefix', lambda: require([b['text'] for b in alias_doc['blocks']] == [b['text'] for b in before['blocks']], 'Prefix alias changed extraction'))
        for block in alias_doc['blocks']:
            check(f"Alias original locator {block['id']}", lambda block=block: require(resolve(aliased, evidence_for(alias_doc, block, block['text']))['text'] == block['text'], 'Alias evidence failed'))

        bad = temporary / 'not-a-zip.bin'
        bad.write_bytes(b'not a DOCX')
        def invalid_package():
            try:
                extract(bad)
            except ValueError as error:
                require(str(error) == 'invalid_zip', str(error))
                return
            raise AssertionError('Invalid DOCX accepted')
        check('Non-ZIP DOCX rejected', invalid_package)

        for case, extra_name, extra_data in [('traversal', '../escape.xml', b'<x/>'), ('dtd', PART, b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///never-read">]><x>&e;</x>')]:
            candidate = temporary / f'{case}.bin'
            with ZipFile(candidate, 'w') as archive:
                for n, data in members.items():
                    archive.writestr(n, extra_data if n == extra_name else data)
                if extra_name not in members:
                    archive.writestr(extra_name, extra_data)
            def reject_package(candidate=candidate, case=case):
                try:
                    extract(candidate)
                except ValueError as error:
                    require(str(error) == ('unsafe_zip_member' if case == 'traversal' else 'dtd_or_entity_not_allowed'), str(error))
                    return
                raise AssertionError('Unsafe package accepted')
            check(f'Package boundary: {case}', reject_package)

    comparison_file = output / 'current-parser.json'
    proc = subprocess.run([str(node), '--import', 'tsx', str(Path(__file__).with_name('compare-current.mjs')), str(repo), str(fixtures), str(comparison_file)], cwd=repo / 'server', capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    comparison = json.loads(comparison_file.read_text(encoding='utf-8')) if comparison_file.exists() else {'reports': [], 'processError': proc.stderr[-1000:]}
    comparison_summary = []
    for report in comparison['reports']:
        entry = {k: report[k] for k in ['sourceName', 'stage', 'ok', 'error', 'fields', 'chars'] if k in report}
        if report.get('ok'):
            markdown = report['markdown']
            (output / f"{Path(report['sourceName']).stem}.current.md").write_text(markdown, encoding='utf-8')
            entry.update({'hasOriginalLocators': any(k in report for k in ['blocks', 'locations', 'xpath']), 'headerTextFound': '页眉旧项目' in markdown, 'managerTextFound': '示例甲' in markdown, 'nestedTableTextFound': '隐患记录' in markdown, 'textboxTextFound': '文本框内旧项目' in markdown, 'footnoteTextFound': 'FOOTNOTE_ONLY_SYNTHETIC' in markdown.replace('\\_', '_'), 'cachedDateFound': '2026-10-24' in markdown, 'hiddenTextFound': '隐藏文字：' in markdown})
        comparison_summary.append(entry)
    for filename, document in documents.items():
        check(f'{filename}: original bytes unchanged after comparison', lambda filename=filename, document=document: require(digest((fixtures / filename).read_bytes()) == document['byteHash'], 'A fixture was modified by a reader'))
        check(f'{filename}: current parser completes', lambda filename=filename: require(any(r.get('sourceName') == filename and r.get('ok') for r in comparison_summary), 'Current parser failed on synthetic DOCX'))
    (output / 'evidence-examples.json').write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {'synthetic': True, 'fixtures': list(documents), 'checks': checks, 'passed': sum(c['passed'] for c in checks), 'failed': sum(not c['passed'] for c in checks), 'blockCounts': {n: len(d['blocks']) for n, d in documents.items()}, 'originalLocatorRoundTrips': sum(len(d['blocks']) for d in documents.values()), 'evidenceExamples': len(examples), 'currentParser': comparison_summary, 'currentParserProcessExit': proc.returncode, 'pageOrWpsNavigationVerified': False, 'rendererVerified': False, 'customerAccuracyVerified': False}
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['passed', 'failed', 'blockCounts', 'originalLocatorRoundTrips', 'currentParser']}, ensure_ascii=False))
    if result['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    args = parser.parse_args()
    run(args.fixtures.resolve(), args.output.resolve(), args.repo.resolve(), args.node.resolve())
