"""Offline conservative exact-replacement review, not a general natural-language/model verifier."""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'word-evidence-spike'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'image-ocr-spike'))
from extract import PART, digest, evidence_for, extract, resolve
from header_footer import extract_header_footer, header_footer_evidence, resolve_header_footer
from textboxes import extract_textboxes, textbox_evidence, resolve_textbox
from image_evidence import docx_pictures


def norm(text):
    return ''.join(unicodedata.normalize('NFKC', text).split())


def snapshot(source):
    body, hf, boxes = extract(source), extract_header_footer(source), extract_textboxes(source)
    pictures, _ = docx_pictures(source)
    hashes = {body['byteHash'], hf['byteHash'], boxes['byteHash'], digest(source.read_bytes())}
    if len(hashes) != 1:
        raise ValueError('source_changed_while_extracting')
    blocks = []
    for origin, document in [('body', body), ('header-footer', hf), ('textbox', boxes)]:
        for block in document['blocks']:
            blocks.append({**block, 'origin': origin})
    # Table labels travel with a row even when tables/rows are inserted or reordered.
    for block in blocks:
        if block['tablePath'] and block['origin'] != 'textbox':
            row = [(t['tableIndex'], t['xmlRow']) for t in block['tablePath']]
            peers = [b for b in blocks if b['origin'] == block['origin'] and b['part'] == block['part'] and [(t['tableIndex'], t['xmlRow']) for t in b['tablePath']] == row]
            block['context'] = ' | '.join(b['text'] for b in peers)
        else:
            block['context'] = block['text']
        block['channel'] = ('table' if block['tablePath'] else 'paragraph') if block['origin'] == 'body' else block.get('kind', 'textbox')
    gaps = [g for g in body['coverage']['uncovered'] if g not in {'headers', 'footers', 'textboxes', 'image_or_drawing_contents'}]
    if pictures:
        gaps.append('images_not_reviewed_by_this_experiment')
    gaps.extend(g['reason'] for g in boxes['coverage']['uncovered'])
    return {'sourceName': source.name, 'byteHash': body['byteHash'], 'blocks': blocks,
            'pictures': pictures, 'coverageGaps': sorted(set(gaps)),
            'documents': {'body': body, 'header-footer': hf, 'textbox': boxes}}


def parse_opinion(text):
    endings = r'[。.!]?'
    for label, expression in [
        ('all', r'(?:把|将)全文的“([^”]+)”(?:改为|改成)“([^”]+)”'),
        ('body-text', r'(?:把|将)正文可编辑文字的“([^”]+)”(?:改为|改成)“([^”]+)”'),
        ('context', r'(?:把|将)“([^”]+)”相关位置的“([^”]+)”(?:改为|改成)“([^”]+)”')]:
        match = re.fullmatch(expression + endings, text.strip())
        if match:
            context, old, new = match.groups() if label == 'context' else (None, *match.groups())
            if old == new or old in new or new in old:
                return None
            return {'kind': 'exact-replacement', 'scope': label, 'context': context, 'old': old, 'new': new}
    return None


def eligible(document, rule):
    blocks = document['blocks']
    if rule['scope'] == 'body-text':
        return [b for b in blocks if b['part'] == PART]
    if rule['scope'] == 'context':
        return [b for b in blocks if norm(rule['context']) in norm(b['context'])]
    return blocks


def masked(text, rule):
    values = sorted([rule['old'], rule['new']], key=len, reverse=True)
    return norm(re.sub('|'.join(re.escape(v) for v in values), '<替换值>', text))


def signature(block, rule):
    return (block['channel'], masked(block['context'], rule), masked(block['text'], rule))


def evidence(document, block):
    helper = {'body': evidence_for, 'header-footer': header_footer_evidence, 'textbox': textbox_evidence}[block['origin']]
    return deepcopy({'origin': block['origin'], 'sourceName': document['sourceName'],
                     'location': {'kind': block['channel'], 'tablePath': block['tablePath'],
                                  'headingPath': block.get('headingPath', [])},
                     'reference': helper(document['documents'][block['origin']], block, block['text'])})


def verify_evidence(source, item):
    helpers = {'body': resolve, 'header-footer': resolve_header_footer, 'textbox': resolve_textbox}
    if item.get('origin') not in helpers:
        raise ValueError('unsupported_evidence_origin')
    return helpers[item['origin']](source, item['reference'])


def nearby(document, text, limit=3):
    ranked = []
    for block in document['blocks']:
        match = SequenceMatcher(None, norm(text), norm(block['context']), autojunk=False).find_longest_match()
        if match.size >= 3:
            ranked.append((match.size, block))
    return [evidence(document, b) for _, b in sorted(ranked, key=lambda r:r[0], reverse=True)[:limit]]


def review_one(before, after, opinion):
    text = opinion['text']
    result = {'issueId': opinion['id'], 'opinion': text, 'rule': parse_opinion(text),
              'beforeHash': before['byteHash'], 'afterHash': after['byteHash'],
              'groups': [], 'remainingOld': [], 'beforeEvidence': [], 'afterEvidence': [],
              'unresolved': [], 'coverageGaps': [], 'status': 'undetermined'}
    rule = result['rule']
    if rule is None:
        result.update(reason='意见不属于本实验可验证的明确替换规则，需要人工解释或业务资料。',
                      beforeEvidence=nearby(before, text), afterEvidence=nearby(after, text),
                      imageReferences={'before': before['pictures'], 'after': after['pictures']})
        return result
    previous, current = eligible(before, rule), eligible(after, rule)
    targets = [b for b in previous if rule['old'] in b['text']]
    if not targets:
        result.update(reason='修改前未找到指定旧值，不能凭新稿已有新值判断本轮已修改。',
                      beforeEvidence=nearby(before, text), afterEvidence=nearby(after, text))
        return result
    groups_before, groups_after = defaultdict(list), defaultdict(list)
    for block in targets:
        groups_before[signature(block, rule)].append(block)
    for block in current:
        if rule['old'] in block['text'] or rule['new'] in block['text']:
            groups_after[signature(block, rule)].append(block)
    changed, same, aligned_after = 0, 0, set()
    for key, old_blocks in groups_before.items():
        new_blocks = groups_after.get(key, [])
        before_ev, after_ev = [evidence(before,b) for b in old_blocks], [evidence(after,b) for b in new_blocks]
        group = {'method': 'unique-context' if len(old_blocks) == len(new_blocks) == 1 else 'multiset-context',
                 'before': before_ev, 'after': after_ev, 'verifiedChanged': 0, 'verifiedUnchanged': 0}
        if len(old_blocks) != len(new_blocks):
            hints = nearby(after, old_blocks[0]['context'])
            group.update(method='unresolved', candidateEvidence=hints,
                         reason='上下文数量不一致或发生改写/拆分/删除，不能强行按段落号配对。')
            result['unresolved'].append(group['reason'])
        elif any(b['flags'] for b in [*old_blocks,*new_blocks]):
            group.update(method='unresolved', reason='候选涉及修订、隐藏内容、域或兼容显示等未验证状态。')
            result['unresolved'].append(group['reason'])
        else:
            # A duplicate group is reviewed as a set, without inventing one-to-one lineage.
            group['verifiedChanged'] = sum(b['text'].count(rule['new']) for b in new_blocks) - sum(b['text'].count(rule['new']) for b in old_blocks)
            group['verifiedUnchanged'] = sum(b['text'].count(rule['old']) for b in new_blocks)
            changed += max(0, group['verifiedChanged']); same += group['verifiedUnchanged']
            aligned_after.update(b['id'] for b in new_blocks)
        result['groups'].append(group)
    result['remainingOld'] = [dict(evidence(after,b), occurrences=b['text'].count(rule['old']),
                                   newlyUnpaired=b['id'] not in aligned_after)
                              for b in current if rule['old'] in b['text']]
    old_total = sum(e['occurrences'] for e in result['remainingOld'])
    gaps = set(before['coverageGaps'] + after['coverageGaps'])
    if rule['scope'] == 'body-text':
        gaps -= {'images_not_reviewed_by_this_experiment', 'footnotes', 'endnotes', 'comments'}
    result['coverageGaps'] = sorted(gaps)
    if result['coverageGaps']:
        result['imageReferences'] = {'before': before['pictures'], 'after': after['pictures']}
    if changed > 0 and old_total > 0:
        result.update(status='partially_modified', reason='有可核对的替换，同时新稿仍保留本意见范围内的旧值。')
    elif result['unresolved'] or result['coverageGaps']:
        result.update(reason='部分位置或覆盖范围无法核对，不能把旧值未检出当作已经改全。')
    elif changed > 0 and old_total == 0:
        result.update(status='modified', reason='本实验范围内原有目标均有对应替换证据，且新稿未检出同范围旧值。')
    elif same > 0 and changed == 0:
        result.update(status='unmodified', reason='对应位置仍为旧值，没有发现可核对的替换。')
    else:
        result['reason'] = '没有足够对应证据。'
    result['counts'] = {'beforeOldOccurrences': sum(b['text'].count(rule['old']) for b in targets),
                        'verifiedReplacements': changed, 'afterOldOccurrences': old_total,
                        'unresolvedGroups': len(result['unresolved'])}
    return result


def review_pair(before_path, after_path, opinions):
    before, after = snapshot(before_path), snapshot(after_path)
    results = [review_one(before,after,opinion) for opinion in opinions]
    return {'synthetic': True, 'method': 'conservative exact-replacement rules; no model calls',
            'before': {'sourceName': before['sourceName'], 'byteHash': before['byteHash']},
            'after': {'sourceName': after['sourceName'], 'byteHash': after['byteHash']},
            'opinionHash': digest(json.dumps(opinions,sort_keys=True,ensure_ascii=False).encode()),
            'results': results, 'businessIntegrated': False, 'pageNumbersVerified': False}


def text_evidence_by_side(result):
    for side in ['before', 'after']:
        yield from ((side, e) for e in result.get(side+'Evidence', []))
        for group in result['groups']:
            yield from ((side, e) for e in group[side])
            if side == 'after':
                yield from ((side, e) for e in group.get('candidateEvidence', []))
    yield from (('after', e) for e in result['remainingOld'])


def validate_report(before_path, after_path, opinions, report):
    sources = {'before': before_path, 'after': after_path}
    for side, source in sources.items():
        if report[side]['byteHash'] != digest(source.read_bytes()):
            raise ValueError('report_source_version_mismatch')
    if report['opinionHash'] != digest(json.dumps(opinions,sort_keys=True,ensure_ascii=False).encode()):
        raise ValueError('report_opinion_version_mismatch')
    if [(r['issueId'],r['opinion']) for r in report['results']] != [(o['id'],o['text']) for o in opinions]:
        raise ValueError('report_opinion_list_mismatch')
    for result in report['results']:
        for side, item in text_evidence_by_side(result):
            verify_evidence(sources[side], item)
        for side, references in result.get('imageReferences', {}).items():
            current, _ = docx_pictures(sources[side])
            if references != current:
                raise ValueError('report_picture_reference_mismatch')
    return True


# shortcut: contextual exact replacement handles movement/reordering and duplicate sets, but abstains on paraphrases and split/merge lineage.
