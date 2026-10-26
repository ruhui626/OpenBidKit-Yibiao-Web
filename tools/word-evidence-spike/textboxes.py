"""Offline storage-level textbox index. It never selects a rendered compatibility branch."""
from copy import deepcopy

from lxml import etree

from extract import (PART, WORD_NS, ancestor, digest, evidence_for, location,
                     read_package, table_coordinates, word_local, xml_root)
from header_footer import bindings_from_parts, hf_block_id

MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
WPS = 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape'
VML = 'urn:schemas-microsoft-com:vml'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'


def nearest(node, tag):
    return next((p for p in node.iterancestors() if p.tag == tag), None)


def textbox_text(paragraph, box, uri):
    out = []
    for item in paragraph.iterdescendants():
        if ancestor(item, 'p', uri) is not paragraph or ancestor(item, 'txbxContent', uri) is not box:
            continue
        if any(word_local(p, uri) in {'del', 'moveFrom'} for p in item.iterancestors()):
            continue
        name = word_local(item, uri)
        if name == 't':
            out.append(item.text or '')
        elif name == 'tab':
            out.append('\t')
        elif name in {'br', 'cr'}:
            out.append('\n')
    return ''.join(out)


def alternate_context(box, uri):
    contexts = []
    for group in reversed([p for p in box.iterancestors() if p.tag == f'{{{MC}}}AlternateContent']):
        branch = next(p for p in [box, *box.iterancestors()] if p.getparent() is group)
        xpath, _ = location(group, uri)
        branch_path, _ = location(branch, uri)
        requires = branch.get('Requires', '').split()
        contexts.append({'groupXPath': xpath, 'branchXPath': branch_path,
                         'branch': etree.QName(branch).localname,
                         'requires': [{'prefix': p, 'namespace': branch.nsmap.get(p)} for p in requires]})
    return contexts


def extract_textboxes(source):
    file_hash, parts = read_package(source)
    binding_map = bindings_from_parts(parts)
    boxes, blocks, alternatives, uncovered = [], [], [], []
    for part in [PART, *binding_map['parts']]:
        root = xml_root(parts[part])
        uri = etree.QName(root).namespace
        if uri not in WORD_NS:
            raise ValueError('unsupported_word_namespace')
        ns = {'w': uri}
        scope = root.find('w:body', ns) if part == PART else root
        all_tables = {t: i for i, t in enumerate(scope.findall('.//w:tbl', ns), 1)}
        for box in scope.findall('.//w:txbxContent', ns):
            parent = box.getparent()
            representation = ('drawingml' if parent.tag == f'{{{WPS}}}txbx' else
                              'vml' if parent.tag == f'{{{VML}}}textbox' else 'unknown')
            box_path, box_ns = location(box, uri)
            anchor = ancestor(box, 'p', uri)
            flags = ['compatibility_branch_not_render_verified'] if alternate_context(box, uri) else []
            if representation == 'unknown':
                flags.append('unsupported_textbox_wrapper')
            if ancestor(box, 'txbxContent', uri) is not None:
                flags.append('nested_textbox_flow_requires_review')
            if any(word_local(p, uri) in {'del', 'ins', 'moveFrom', 'moveTo'} for p in box.iterancestors()):
                flags.append('tracked_changes_require_review')
            shape = nearest(box, f'{{{WPS}}}wsp') if representation == 'drawingml' else nearest(box, f'{{{VML}}}shape')
            doc_props = next((n for p in box.iterancestors() if p.tag in {f'{{{WP}}}anchor', f'{{{WP}}}inline'}
                              for n in p.findall(f'{{{WP}}}docPr')), None)
            meta = {'boxId': hf_block_id(file_hash, part, box_path), 'part': part,
                    'boxXPath': box_path, 'namespaces': box_ns, 'representation': representation,
                    'shapeId': (shape.get('id') if shape is not None else None),
                    'drawingId': doc_props.get('id') if doc_props is not None else None,
                    'storyId': parent.get('id') if representation == 'drawingml' else None,
                    'anchorXPath': location(anchor, uri)[0] if anchor is not None else None,
                    'anchorTablePath': table_coordinates(anchor, all_tables, uri) if anchor is not None else [],
                    'alternateContexts': alternate_context(box, uri),
                    'uses': binding_map['uses'].get(part, []), 'flags': flags}
            tables = {t: i for i, t in enumerate(box.findall('.//w:tbl', ns), 1)}
            own_blocks = []
            for paragraph in box.findall('.//w:p', ns):
                if ancestor(paragraph, 'txbxContent', uri) is not box:
                    continue
                text = textbox_text(paragraph, box, uri)
                if not text.strip():
                    continue
                xpath, namespaces = location(paragraph, uri)
                paragraph_flags = list(flags)
                for expression, label in [('.//w:fldSimple | .//w:fldChar | .//w:instrText', 'cached_field_result_only'),
                                          ('.//w:vanish', 'hidden_text_requires_review'),
                                          ('.//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo', 'tracked_changes_require_review')]:
                    if paragraph.xpath(expression, namespaces=ns):
                        paragraph_flags.append(label)
                chain = table_coordinates(paragraph, {**all_tables, **tables}, uri)
                local_tables = {v for v in tables}
                local_chain = [entry for table, entry in zip(reversed([p for p in paragraph.iterancestors() if word_local(p, uri) == 'tbl']), chain) if table in local_tables]
                block = {'id': hf_block_id(file_hash, part, xpath), 'part': part,
                         'xpath': xpath, 'namespaces': namespaces, 'text': text,
                         'textHash': digest(text.encode()), 'tablePath': local_chain,
                         'textbox': meta, 'flags': sorted(set(paragraph_flags))}
                blocks.append(block)
                own_blocks.append(block)
            boxes.append({**meta, 'blockIds': [b['id'] for b in own_blocks], 'nonemptyParagraphCount': len(own_blocks)})
        for group in scope.findall(f'.//{{{MC}}}AlternateContent'):
            if not group.findall('.//w:txbxContent', ns):
                continue
            group_path, _ = location(group, uri)
            branches = []
            for branch in group:
                branch_path, _ = location(branch, uri)
                branch_blocks = [b for b in blocks if b['part'] == part and any(c['branchXPath'] == branch_path for c in b['textbox']['alternateContexts'])]
                branches.append({'branchXPath': branch_path, 'branch': etree.QName(branch).localname,
                                 'boxCount': len(branch.findall('.//w:txbxContent', ns)),
                                 'texts': [b['text'] for b in branch_blocks], 'blockIds': [b['id'] for b in branch_blocks]})
            alternatives.append({'part': part, 'groupXPath': group_path, 'branches': branches,
                                 'paragraphTextsAgree': len({tuple(b['texts']) for b in branches}) == 1,
                                 'displayedBranch': None, 'requiresManualDisplayReview': True})
        for node in scope.findall(f'.//{{{WPS}}}linkedTxbx'):
            uncovered.append({'part': part, 'xpath': location(node, uri)[0], 'reason': 'linked_textbox_page_distribution_unverified', 'storyId': node.get('id'), 'sequence': node.get('seq')})
        for tag, reason in [(f'{{{A}}}t', 'drawing_text_outside_w_txbxContent'), (f'{{{VML}}}textpath', 'vml_textpath_outside_w_txbxContent')]:
            for node in scope.findall('.//' + tag):
                if ancestor(node, 'txbxContent', uri) is None:
                    uncovered.append({'part': part, 'xpath': location(node, uri)[0], 'reason': reason})
    return {'sourceName': source.name, 'byteHash': file_hash, 'parserVersion': 'offline-textbox-spike-v1',
            'boxes': boxes, 'blocks': blocks, 'alternateGroups': alternatives,
            'unreferencedHeaderFooterParts': binding_map['unreferencedParts'],
            'coverage': {'pageNumbersVerified': False, 'renderVerified': False,
                         'displayedBranchesVerified': False, 'uncovered': uncovered,
                         'offsetUnit': 'unicode-code-point'}}


def textbox_evidence(document, block, quote):
    return deepcopy({**evidence_for(document, block, quote), 'textbox': block['textbox']})


def resolve_textbox(source, evidence):
    document = extract_textboxes(source)
    if document['byteHash'] != evidence['sourceByteHash']:
        raise ValueError('source_version_mismatch')
    block = next((b for b in document['blocks'] if b['part'] == evidence['part'] and b['xpath'] == evidence['xpath']), None)
    if block is None:
        raise ValueError('locator_not_an_indexed_textbox_paragraph')
    if any(evidence.get(key) != block[key] for key in ['namespaces', 'textbox']) or evidence.get('blockId') != block['id']:
        raise ValueError('textbox_context_mismatch')
    start, end = evidence['start'], evidence['end']
    if evidence.get('offsetUnit') != 'unicode-code-point' or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(block['text']):
        raise ValueError('invalid_range')
    if block['text'][start:end] != evidence['quote']:
        raise ValueError('quote_does_not_match_original')
    return {'text': block['text'], 'quote': block['text'][start:end], 'textbox': block['textbox']}


# shortcut: stored alternatives are separate evidence, never inferred screen content or page coordinates.
