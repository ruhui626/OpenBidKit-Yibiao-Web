"""Offline header/footer evidence experiment; section bindings are not page layout."""
import posixpath
import re
from urllib.parse import unquote, urlsplit

from lxml import etree

from extract import (PART, WORD_NS, ancestor, digest, evidence_for, location,
                     paragraph_text, read_package, table_coordinates, word_local, xml_root)

REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'
REL_BASES = ['http://schemas.openxmlformats.org/officeDocument/2006/relationships/',
             'http://purl.oclc.org/ooxml/officeDocument/relationships/']
CT = {kind: f'application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml' for kind in ['header', 'footer']}


def target_part(value):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '\\' in value:
        raise ValueError('header_footer_target_not_internal_part')
    path = unquote(parsed.path)
    path = posixpath.normpath(path.lstrip('/') if path.startswith('/') else posixpath.join('word', path))
    if path in {'.', '..'} or path.startswith('../') or ':' in path or '\\' in path:
        raise ValueError('header_footer_target_outside_package')
    return path


def on_off(node, uri):
    if node is None:
        return False
    value = node.get(f'{{{uri}}}val', 'true').lower()
    if value not in {'true', 'false', '1', '0', 'on', 'off'}:
        raise ValueError('invalid_on_off_value')
    return value in {'true', '1', 'on'}


def bindings_from_parts(parts):
    root = xml_root(parts[PART])
    uri = etree.QName(root).namespace
    if uri not in WORD_NS:
        raise ValueError('unsupported_word_namespace')
    ns = {'w': uri}
    relationships = {}
    if 'word/_rels/document.xml.rels' in parts:
        for rel in xml_root(parts['word/_rels/document.xml.rels']).findall(f'{{{REL_NS}}}Relationship'):
            rel_id = rel.get('Id')
            if not rel_id or rel_id in relationships:
                raise ValueError('duplicate_or_missing_relationship_id')
            relationships[rel_id] = dict(rel.attrib)
    content_types = {unquote(n.get('PartName', '')).lstrip('/'): n.get('ContentType')
                     for n in xml_root(parts['[Content_Types].xml']).findall(f'{{{CT_NS}}}Override')}
    even_odd = False
    settings = [r for r in relationships.values() if r.get('Type') in {b + 'settings' for b in REL_BASES}]
    if len(settings) > 1:
        raise ValueError('multiple_settings_relationships')
    if settings:
        rel = settings[0]
        if rel.get('TargetMode', 'Internal') != 'Internal':
            raise ValueError('settings_relationship_external')
        settings_path = target_part(rel.get('Target', ''))
        if settings_path not in parts:
            raise ValueError('settings_part_missing')
        even_odd = on_off(xml_root(parts[settings_path]).find('w:evenAndOddHeaders', ns), uri)
    body = root.find('w:body', ns)
    if body is None:
        raise ValueError('missing_document_body')
    sections = body.xpath('.//w:p/w:pPr/w:sectPr[not(ancestor::w:tbl) and not(ancestor::w:txbxContent) and not(ancestor::w:sectPrChange) and not(ancestor::w:del) and not(ancestor::w:moveFrom)] | ./w:sectPr', namespaces=ns)
    if not sections:
        raise ValueError('missing_section_properties')
    previous, bindings, used_parts = {}, [], {}
    for section_index, section in enumerate(sections, 1):
        first = on_off(section.find('w:titlePg', ns), uri)
        page_start = section.find('w:pgNumType', ns)
        for kind in ['header', 'footer']:
            for variant in ['default', 'first', 'even']:
                key = kind, variant
                references = [r for r in section.findall(f'w:{kind}Reference', ns) if r.get(f'{{{uri}}}type') == variant]
                if len(references) > 1:
                    raise ValueError('duplicate_header_footer_reference')
                definition = previous.get(key)
                if references:
                    ids = [v for k, v in references[0].attrib.items() if etree.QName(k).localname == 'id' and etree.QName(k).namespace in {b.rstrip('/') for b in REL_BASES}]
                    rel_id = ids[0] if len(ids) == 1 else None
                    if rel_id not in relationships:
                        raise ValueError('header_footer_relationship_missing')
                    rel = relationships[rel_id]
                    if rel.get('TargetMode', 'Internal') != 'Internal':
                        raise ValueError('header_footer_relationship_external')
                    if rel.get('Type') not in {b + kind for b in REL_BASES}:
                        raise ValueError('header_footer_relationship_type_mismatch')
                    part = target_part(rel.get('Target', ''))
                    if part not in parts:
                        raise ValueError('header_footer_part_missing')
                    if content_types.get(part) != CT[kind]:
                        raise ValueError('header_footer_content_type_mismatch')
                    part_root = xml_root(parts[part])
                    if etree.QName(part_root).namespace != uri or etree.QName(part_root).localname != ('hdr' if kind == 'header' else 'ftr'):
                        raise ValueError('header_footer_part_root_mismatch')
                    if part in used_parts and used_parts[part] != kind:
                        raise ValueError('header_footer_part_kind_conflict')
                    used_parts[part] = kind
                    definition = {'part': part, 'relationshipId': rel_id, 'definedInSection': section_index}
                    previous[key] = definition
                enabled = variant == 'default' or (first if variant == 'first' else even_odd)
                bindings.append({'section': section_index, 'kind': kind, 'variant': variant,
                                 'enabledBySettings': enabled, 'titlePageDifferent': first,
                                 'evenAndOddDifferent': even_odd,
                                 'pageNumberStartSetting': page_start.get(f'{{{uri}}}start') if page_start is not None else None,
                                 'part': definition['part'] if definition else None,
                                 'relationshipId': definition['relationshipId'] if definition else None,
                                 'definedInSection': definition['definedInSection'] if definition else None,
                                 'inherited': bool(definition and not references),
                                 'blank': definition is None})
    uses = {part: [b for b in bindings if b['part'] == part] for part in used_parts}
    unreferenced = sorted(p for p, ct in content_types.items() if ct in CT.values() and p not in used_parts)
    return {'bindings': bindings, 'parts': used_parts, 'uses': uses, 'unreferencedParts': unreferenced,
            'sectionCount': len(sections), 'evenAndOddDifferent': even_odd}


def hf_block_id(file_hash, part, xpath):
    return digest(f'{file_hash}|{part}|{xpath}'.encode())[:24]


def extract_header_footer(source):
    file_hash, parts = read_package(source)
    binding_map = bindings_from_parts(parts)
    blocks, uncovered = [], []
    for part, kind in binding_map['parts'].items():
        root = xml_root(parts[part])
        uri = etree.QName(root).namespace
        ns = {'w': uri}
        tables = {t: i for i, t in enumerate(root.findall('.//w:tbl', ns), 1)}
        for paragraph in root.findall('.//w:p', ns):
            if ancestor(paragraph, 'txbxContent', uri) is not None:
                continue
            text = paragraph_text(paragraph, uri)
            if not text.strip():
                continue
            xpath, namespaces = location(paragraph, uri)
            flags = []
            for expression, label in [('.//w:fldSimple | .//w:fldChar | .//w:instrText', 'cached_field_result_only'),
                                      ('.//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo', 'tracked_changes_require_review'),
                                      ('.//w:vanish', 'hidden_text_requires_review')]:
                if paragraph.xpath(expression, namespaces=ns):
                    flags.append(label)
            blocks.append({'id': hf_block_id(file_hash, part, xpath), 'part': part, 'kind': kind,
                           'xpath': xpath, 'namespaces': namespaces, 'text': text,
                           'textHash': digest(text.encode()), 'tablePath': table_coordinates(paragraph, tables, uri),
                           'uses': binding_map['uses'][part], 'flags': flags})
        for expression, label in [('.//w:txbxContent', 'textboxes'), ('.//w:drawing | .//w:pict', 'image_or_drawing_contents'),
                                  ('.//w:fldSimple | .//w:fldChar', 'dynamic_field_semantics')]:
            if root.xpath(expression, namespaces=ns):
                uncovered.append({'part': part, 'reason': label})
    return {'sourceName': source.name, 'byteHash': file_hash, 'blocks': blocks, **binding_map,
            'coverage': {'pageNumbersVerified': False, 'renderVerified': False, 'uncovered': uncovered,
                         'enabledDoesNotProveRenderedOnPage': True}}


def header_footer_evidence(document, block, quote):
    return {**evidence_for(document, block, quote), 'uses': block['uses']}


def resolve_header_footer(source, evidence):
    file_hash, parts = read_package(source)
    if file_hash != evidence['sourceByteHash']:
        raise ValueError('source_version_mismatch')
    binding_map = bindings_from_parts(parts)
    part, xpath = evidence['part'], evidence['xpath']
    if part not in binding_map['parts']:
        raise ValueError('part_not_referenced_header_footer')
    if evidence.get('uses') != binding_map['uses'][part]:
        raise ValueError('header_footer_binding_mismatch')
    if not re.fullmatch(r'(?:/[a-z][a-z0-9]*:[A-Za-z][A-Za-z0-9]*\[[1-9][0-9]*\])+', xpath):
        raise ValueError('invalid_locator')
    if evidence['blockId'] != hf_block_id(file_hash, part, xpath) or evidence.get('offsetUnit') != 'unicode-code-point':
        raise ValueError('invalid_block_or_offsets')
    root = xml_root(parts[part])
    nodes = root.xpath(xpath, namespaces=evidence['namespaces'])
    uri = etree.QName(root).namespace
    if len(nodes) != 1 or word_local(nodes[0], uri) != 'p':
        raise ValueError('locator_not_a_unique_paragraph')
    text = paragraph_text(nodes[0], uri)
    start, end = evidence['start'], evidence['end']
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(text):
        raise ValueError('invalid_range')
    if text[start:end] != evidence['quote']:
        raise ValueError('quote_does_not_match_original')
    return {'text': text, 'quote': text[start:end], 'uses': binding_map['uses'][part],
            'xml': etree.tostring(nodes[0], encoding='unicode')}


# shortcut: bindings describe section definitions and settings, never actual rendered pages.
