"""Offline OCR evidence: storage image/page plus a polygon, never a claim of correct text."""
import io
import json
import math
import posixpath
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import etree
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'word-evidence-spike'))
from extract import PART, digest, location, read_package, xml_root
from header_footer import bindings_from_parts, REL_NS

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PIC = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'


def pixel_hash(image):
    rgb = image.convert('RGB')
    return digest(f'{rgb.width}x{rgb.height}|RGB|'.encode() + rgb.tobytes())


def image_meta(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > 30_000_000:
            raise ValueError('prototype_image_pixel_limit')
        if image.getexif().get(274, 1) != 1:
            raise ValueError('exif_orientation_not_covered')
        return {'width': image.width, 'height': image.height, 'pixelHash': pixel_hash(image)}


def docx_pictures(source):
    source_hash, parts = read_package(source)
    binding_map = bindings_from_parts(parts)
    pictures = []
    for part in [PART, *binding_map['parts']]:
        root = xml_root(parts[part])
        relpath = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
        rels = {}
        if relpath in parts:
            for rel in xml_root(parts[relpath]).findall(f'{{{REL_NS}}}Relationship'):
                rid = rel.get('Id')
                if not rid or rid in rels:
                    raise ValueError('duplicate_image_relationship')
                rels[rid] = rel.attrib
        for blip in root.findall(f'.//{{{A}}}blip'):
            if blip.get(f'{{{R}}}link') is not None:
                raise ValueError('external_image_not_fetched')
            rid = blip.get(f'{{{R}}}embed')
            rel = rels.get(rid)
            if not rel or rel.get('Type') != R + '/image':
                raise ValueError('image_relationship_missing_or_wrong_type')
            if rel.get('TargetMode', 'Internal') != 'Internal':
                raise ValueError('external_image_not_fetched')
            target = unquote(rel.get('Target', ''))
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '\\' in target:
                raise ValueError('unsafe_image_target')
            media = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(part), target))
            if media == '..' or media.startswith('../') or media not in parts:
                raise ValueError('image_target_missing_or_outside_package')
            raw = parts[media]
            meta = image_meta(raw)
            xpath, namespaces = location(blip, etree.QName(root).namespace)
            picture = next((p for p in blip.iterancestors() if p.tag == f'{{{PIC}}}pic'), None)
            if picture is None:
                raise ValueError('unsupported_blip_container')
            crop = picture.find(f'.//{{{A}}}srcRect')
            crop = dict(crop.attrib) if crop is not None else {}
            xfrm = picture.find(f'.//{{{A}}}xfrm')
            transform = dict(xfrm.attrib) if xfrm is not None else {}
            wrapper = next((p for p in blip.iterancestors() if p.tag in {f'{{{WP}}}inline', f'{{{WP}}}anchor'}), None)
            extent = wrapper.find(f'{{{WP}}}extent') if wrapper is not None else None
            display_unverified = any(float(v) != 0 for v in crop.values()) or any(v not in {'0', 'false'} for v in transform.values())
            pictures.append({'sourceName': source.name, 'sourceByteHash': source_hash,
                             'kind': 'docx-image', 'part': part, 'xpath': xpath, 'namespaces': namespaces,
                             'relationshipId': rid, 'mediaPart': media, 'imageByteHash': digest(raw), **meta,
                             'uses': binding_map['uses'].get(part, []), 'crop': crop, 'shapeTransform': transform,
                             'extentEmu': dict(extent.attrib) if extent is not None else None,
                             'pictureDisplayGeometryVerified': False,
                             'originalImageOnly': display_unverified,
                             'flags': ['crop_or_transform_display_unverified'] if display_unverified else [],
                             'instanceId': digest(f'{source_hash}|{part}|{xpath}'.encode())[:24]})
    return pictures, parts


def rotated_polygon(rect, angle, width, height):
    x, y, w, h = rect
    rad = math.radians(angle or 0)
    cx, cy = width / 2, height / 2
    return [[cx + (px-cx)*math.cos(rad) - (py-cy)*math.sin(rad),
             cy + (px-cx)*math.sin(rad) + (py-cy)*math.cos(rad)]
            for px, py in [(x,y), (x+w,y), (x+w,y+h), (x,y+h)]]


def original_polygon(polygon, item):
    if item.get('manualUprightCCW') == 90:
        return [[item['renderWidth'] - y, x] for x, y in polygon]
    return polygon


def build_index(items, assets, ocr):
    records = {r['id']: r for r in ocr['results']}
    blocks = []
    for item in items:
        asset = assets[item['assetId']]
        record = records[item['assetId']]
        if not record['ok']:
            item['status'] = 'ocr_failed'; continue
        if (record['width'], record['height']) != (asset['width'], asset['height']):
            raise ValueError('ocr_image_dimensions_mismatch')
        item['status'] = 'text_detected_requires_review' if record['lines'] else 'no_text_detected_not_proof_of_blank'
        for line_index, line in enumerate(record['lines']):
            if not line['words']:
                continue
            polygons = [original_polygon(rotated_polygon(w['rect'], record['textAngle'], asset['width'], asset['height']), item) for w in line['words']]
            points = [p for polygon in polygons for p in polygon]
            x1, y1 = min(p[0] for p in points), min(p[1] for p in points)
            x2, y2 = max(p[0] for p in points), max(p[1] for p in points)
            block = {'id': digest(f'{item["instanceId"]}|{line_index}'.encode())[:24],
                     'itemId': item['instanceId'], 'assetId': item['assetId'], 'lineIndex': line_index,
                     'ocrText': line['text'], 'wordPolygonsOnOriginalImage': polygons,
                     'bboxOnOriginalImage': [x1, y1, x2-x1, y2-y1],
                     'coordinateFrame': 'original embedded image pixels' if item['kind'] != 'pdf-page' else 'cropped and rotated PDF display raster pixels',
                     'reviewRequired': True, 'confidence': None}
            if item['kind'] == 'pdf-page':
                block['bboxOnDisplayedPagePoints'] = [x1 * item['displayWidthPt']/item['renderWidth'], y1 * item['displayHeightPt']/item['renderHeight'], (x2-x1)*item['displayWidthPt']/item['renderWidth'], (y2-y1)*item['displayHeightPt']/item['renderHeight']]
            blocks.append(block)
    return {'items': items, 'assets': assets, 'blocks': blocks, 'ocrResultHash': digest(json.dumps(ocr, sort_keys=True, ensure_ascii=False).encode()),
            'engine': ocr['engine'], 'language': ocr['language'], 'confidenceAvailable': False,
            'businessIntegrated': False, 'scope': 'offline synthetic inputs, manual visual review required'}


def evidence_for_line(index, block):
    item = next(i for i in index['items'] if i['instanceId'] == block['itemId'])
    return deepcopy({'source': item, 'block': block, 'ocrResultHash': index['ocrResultHash']})


def resolve_evidence(fixtures, index, evidence):
    item = next((i for i in index['items'] if i['instanceId'] == evidence['source']['instanceId']), None)
    block = next((b for b in index['blocks'] if b['id'] == evidence['block']['id']), None)
    if item is None or block is None or evidence != evidence_for_line(index, block) or block['itemId'] != item['instanceId']:
        raise ValueError('ocr_evidence_does_not_match_index')
    # Only the trusted local index determines which source to open.
    source = fixtures / item['sourceName']
    if source.parent != fixtures or digest(source.read_bytes()) != item['sourceByteHash']:
        raise ValueError('source_version_mismatch')
    if item['kind'] == 'docx-image':
        pictures, parts = docx_pictures(source)
        current = next((p for p in pictures if p['instanceId'] == item['instanceId']), None)
        if current is None or any(current[k] != item[k] for k in current):
            raise ValueError('image_occurrence_mismatch')
        raw = parts[item['mediaPart']]
    elif item['kind'] == 'image':
        raw = source.read_bytes()
    else:
        raw = Path(item['rasterPath']).read_bytes()
        if digest(raw) != item['rasterByteHash']:
            raise ValueError('pdf_display_raster_changed')
    with Image.open(io.BytesIO(raw)) as im:
        if pixel_hash(im) != item['originalPixelHash']:
            raise ValueError('original_image_pixels_changed')
        bbox = block['bboxOnOriginalImage']
        x, y, w, h = bbox
        if not all(math.isfinite(n) for n in bbox) or w <= 0 or h <= 0 or x < 0 or y < 0 or x+w > im.width+1 or y+h > im.height+1:
            raise ValueError('ocr_region_outside_source_image')
        crop = im.crop((max(0, math.floor(x)), max(0, math.floor(y)), min(im.width, math.ceil(x+w)), min(im.height, math.ceil(y+h))))
    return {'ocrText': block['ocrText'], 'source': item, 'crop': crop, 'textCorrectnessVerified': False}


# shortcut: PDF boxes use the displayed CropBox/Rotate frame; Word uses original image pixels, not document page coordinates.
