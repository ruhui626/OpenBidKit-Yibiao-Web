"""Run real local OCR, test provenance/regions, and measure errors against synthetic truth."""
import argparse
import io
import json
import math
import subprocess
import unicodedata
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageDraw
from pypdf import PdfReader

from image_evidence import (digest, pixel_hash, image_meta, docx_pictures, build_index,
                            evidence_for_line, resolve_evidence, rotated_polygon)


def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).split())


def distance(a, b):
    row = list(range(len(b)+1))
    for i, x in enumerate(a, 1):
        new = [i]
        for j, y in enumerate(b, 1): new.append(min(new[-1]+1, row[j]+1, row[j-1]+(x != y)))
        row = new
    return row[-1]


def iou(a, b):
    intersection = max(0, min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0])) * max(0, min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))
    return intersection/(a[2]*a[3]+b[2]*b[3]-intersection) if intersection else 0


def bounds(points):
    x1, y1 = min(p[0] for p in points), min(p[1] for p in points)
    return [x1, y1, max(p[0] for p in points)-x1, max(p[1] for p in points)-y1]


def run(fixtures, output, repo, node, poppler):
    output.mkdir(parents=True, exist_ok=False)
    for name in ['inputs', 'media', 'renders', 'overlays', 'crops']: (output/name).mkdir()
    spec = json.loads((fixtures/'fixture-manifest.json').read_text(encoding='utf-8'))
    assets, items, checks = {}, [], []

    def require(ok, message):
        if not ok: raise AssertionError(message)

    def check(name, fn):
        try:
            fn(); checks.append({'name': name, 'passed': True})
        except Exception as error:
            checks.append({'name': name, 'passed': False, 'error': f'{type(error).__name__}: {error}'})

    def asset(raw, suffix='.png'):
        asset_id = digest(raw)
        if asset_id not in assets:
            meta = image_meta(raw)
            path = output/'inputs'/(asset_id+suffix)
            path.write_bytes(raw)
            assets[asset_id] = {'path': str(path), 'imageByteHash': asset_id, **meta}
        return asset_id

    for name in spec['standaloneImages']:
        raw = (fixtures/name).read_bytes(); aid = asset(raw, Path(name).suffix)
        items.append({'kind': 'image', 'sourceName': name, 'sourceByteHash': digest(raw),
                      'assetId': aid, 'originalPixelHash': assets[aid]['pixelHash'],
                      'instanceId': digest(('image|'+name+'|'+aid).encode())[:24]})
    pictures, parts = docx_pictures(fixtures/spec['docx']['name'])
    for picture in pictures:
        aid = asset(parts[picture['mediaPart']], Path(picture['mediaPart']).suffix)
        items.append({**picture, 'assetId': aid, 'originalPixelHash': picture['pixelHash']})
    pdf_path = fixtures/spec['pdf']['name']; reader = PdfReader(pdf_path)
    scale = spec['pdf']['renderScale']
    completed = subprocess.run([str(poppler), '-r', str(72*scale), '-cropbox', '-png', str(pdf_path), str(output/'renders/page')], capture_output=True, text=True, timeout=60)
    if completed.returncode: raise RuntimeError(completed.stderr)
    for index, page in enumerate(reader.pages, 1):
        if page.get('/UserUnit', 1) != 1: raise ValueError('prototype_pdf_user_unit_not_supported')
        raster = output/'renders'/f'page-{index}.png'
        raw = raster.read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            original = image.copy(); width, height = image.size
        upright = spec['pdf']['manualUprightCCWByPage'].get(str(index), 0)
        if upright:
            image = original.transpose(Image.Transpose.ROTATE_90)
            stream = io.BytesIO(); image.save(stream, format='PNG'); input_raw = stream.getvalue()
        else: input_raw = raw
        aid = asset(input_raw)
        box = [float(v) for v in page.cropbox]; rotation = int(page.rotation) % 360
        pw, ph = box[2]-box[0], box[3]-box[1]
        if rotation in {90, 270}: pw, ph = ph, pw
        source_hash = digest(pdf_path.read_bytes())
        items.append({'kind': 'pdf-page', 'sourceName': pdf_path.name, 'sourceByteHash': source_hash,
                      'page': index, 'cropBox': box, 'pageRotation': rotation,
                      'displayWidthPt': pw, 'displayHeightPt': ph, 'renderWidth': width, 'renderHeight': height,
                      'renderDpi': 72*scale, 'manualUprightCCW': upright,
                      'rasterPath': str(raster), 'rasterByteHash': digest(raw), 'assetId': aid,
                      'originalPixelHash': pixel_hash(original),
                      'instanceId': digest(f'{source_hash}|page|{index}|{72*scale}|{upright}'.encode())[:24]})
    jobs = [{'id': key, 'path': value['path']} for key, value in assets.items()]
    jobs_file = output/'ocr-jobs.json'; raw_file = output/'ocr-raw.json'
    jobs_file.write_text(json.dumps(jobs, ensure_ascii=False), encoding='utf-8')
    proc = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(Path(__file__).with_name('windows_ocr.ps1')), '-Manifest', str(jobs_file), '-Output', str(raw_file)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    if proc.returncode: raise RuntimeError(proc.stderr)
    ocr = json.loads(raw_file.read_text(encoding='utf-8-sig'))
    if not all(r['ok'] for r in ocr['results']): raise RuntimeError(json.dumps(ocr, ensure_ascii=False))
    index = build_index(items, assets, ocr)
    (output/'evidence-index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')

    check('No hidden PDF text used as OCR', lambda: require(len(reader.pages) == spec['pdf']['pages'] and all(not (p.extract_text() or '').strip() for p in reader.pages), 'Expected image-only PDF'))
    check('Word image occurrence inventory', lambda: require(len(pictures) == 6 and len({p['imageByteHash'] for p in pictures}) == 2, 'Occurrence/media count incorrect'))
    check('One media reused in separate body/header locations stays separate', lambda: require(len({p['instanceId'] for p in pictures}) == 6 and len({p['part'] for p in pictures}) == 3, 'Picture occurrences collapsed'))
    check('Cropping and rotation never presented as verified page display', lambda: require(sum(p['originalImageOnly'] for p in pictures) == 1 and not any(p['pictureDisplayGeometryVerified'] for p in pictures), 'Transformed image falsely mapped to a Word page'))
    check('OCR is local and provides no invented confidence', lambda: require(ocr['engine'] == 'Windows.Media.Ocr' and all(r['confidence'] is None for r in ocr['results']) and all(b['reviewRequired'] and b['confidence'] is None for b in index['blocks']), 'Confidence or approval invented'))
    check('Duplicate media does not require duplicate recognition', lambda: require(len(assets) == 8 and len(items) == 14, 'Unexpected OCR inputs or source occurrences'))
    check('Blank and unreadable images both remain undetermined', lambda: require(all(i['status'] == 'no_text_detected_not_proof_of_blank' for i in items if i['sourceName'] in ['blank.png', 'unreadable.png']), 'Empty OCR interpreted as a missing item or verified blank page'))

    for block in index['blocks']:
        def original_roundtrip(block=block):
            resolved = resolve_evidence(fixtures, index, evidence_for_line(index, block))
            require(resolved['ocrText'] == block['ocrText'] and resolved['crop'].width > 0 and resolved['crop'].height > 0 and not resolved['textCorrectnessVerified'], 'Original image region not recovered')
        check('Original source and region: '+block['id'], original_roundtrip)

    for picture in pictures:
        def independent(picture=picture):
            import xml.etree.ElementTree as ET
            root = ET.fromstring(parts[picture['part']])
            found = root.find('./'+'/'.join(picture['xpath'].split('/')[2:]), picture['namespaces'])
            require(found is not None and found.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed') == picture['relationshipId'], 'Independent image reference lookup failed')
        check('Independent Word image locator: '+picture['instanceId'], independent)

    gt = spec['regions']
    for item in items:
        if item['kind'] == 'pdf-page':
            check(f'PDF page {item["page"]}: raster matches cropped/rotated page dimensions', lambda item=item: require(item['renderWidth'] == math.ceil(item['displayWidthPt']*scale) and item['renderHeight'] == math.ceil(item['displayHeightPt']*scale), 'PDF frame wrong'))
    geometry = []
    for item in items:
        if not ((item['kind'] == 'image' and item['sourceName'] in ['clean.png','skew.png']) or item['kind'] == 'pdf-page' and item['page'] in [1, 3]): continue
        expected_regions = []
        for truth_region in gt:
            expected = truth_region['rect']
            if item['kind'] == 'image' and item['sourceName'] == 'skew.png':
                expected = bounds(rotated_polygon(expected, -5, 1800, 2400))
            if item['kind'] == 'pdf-page':
                x,y,w,h = expected
                # Independently authored fixture layout: image scaled from 1800x2400 to 540x720 points.
                points = [[px*.3, py*.3] for px,py in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]]
                if item['page'] == 3: points = [[696-(py-12), px-15] for px,py in points]
                expected = bounds([[px*scale,py*scale] for px,py in points])
            expected_regions.append(expected)
        # OCR may split one physical line into label/value lines. Associate by spatial overlap,
        # then check the union against the authored area; never assume identical line counts.
        grouped = {i: [] for i in range(len(gt))}
        for block in [b for b in index['blocks'] if b['itemId'] == item['instanceId']]:
            best = max(range(len(gt)), key=lambda i:iou(expected_regions[i], block['bboxOnOriginalImage']))
            grouped[best].append(block['bboxOnOriginalImage'])
        for line_number, expected in enumerate(expected_regions):
            points = [p for x,y,w,h in grouped[line_number] for p in [(x,y),(x+w,y+h)]]
            score = iou(expected, bounds(points)) if points else 0
            geometry.append({'sourceName': item['sourceName'], 'page': item.get('page'), 'line': line_number+1, 'iou': score,
                             'ocrLineParts':len(grouped[line_number])})
            check(f'Authored region overlap {item["sourceName"]}:{item.get("page",0)}:{line_number}', lambda score=score: require(score >= .55, 'Recognition region does not match the independently authored line area'))

    first = index['blocks'][0]; ev = evidence_for_line(index, first)
    def reject(fake, expected='ocr_evidence_does_not_match_index', candidate_index=index):
        try: resolve_evidence(fixtures, candidate_index, fake)
        except ValueError as error:
            require(str(error) == expected, 'Wrong rejection: '+str(error)); return
        raise AssertionError('False OCR evidence accepted')
    for name, change in [('fabricated OCR text', lambda e:e['block'].__setitem__('ocrText','伪造姓名')),
                         ('fabricated region', lambda e:e['block'].__setitem__('bboxOnOriginalImage',[-100,0,1,1])),
                         ('wrong OCR result', lambda e:e.__setitem__('ocrResultHash','wrong')),
                         ('wrong source image', lambda e:e['source'].__setitem__('sourceName','degraded.jpg'))]:
        fake=deepcopy(ev); change(fake); check('Reject '+name, lambda fake=fake:reject(fake))
    pdf_block = next(b for b in index['blocks'] if next(i for i in items if i['instanceId']==b['itemId'])['kind']=='pdf-page')
    fake = evidence_for_line(index,pdf_block); fake['source']['page']=2
    check('Reject wrong PDF page', lambda:reject(fake))
    doc_block = next(b for b in index['blocks'] if next(i for i in items if i['instanceId']==b['itemId'])['kind']=='docx-image')
    fake_doc = evidence_for_line(index,doc_block); fake_doc['source']['xpath'] += '/a:blip[99]'
    check('Reject wrong Word image occurrence', lambda:reject(fake_doc))
    detached = evidence_for_line(index,first); detached['block']['bboxOnOriginalImage'][0]=-999
    check('Returned evidence cannot mutate original index', lambda:require(first['bboxOnOriginalImage'][0]>=0,'Shared mutable index'))
    wrong_version = deepcopy(index); wrong_version['items'][0]['sourceByteHash']='wrong'
    wrong_ev = evidence_for_line(wrong_version, wrong_version['blocks'][0])
    check('Reject a different original file version', lambda:reject(wrong_ev,'source_version_mismatch',wrong_version))

    # Malformed image relationships are rejected without fetching outside the DOCX.
    for mode in ['external','missing']:
        changed = dict(parts)
        from lxml import etree
        relpath='word/_rels/document.xml.rels'; rels=etree.fromstring(changed[relpath])
        rel=next(r for r in rels if r.get('Id')==pictures[0]['relationshipId'])
        if mode=='external': rel.set('TargetMode','External'); rel.set('Target','https://example.invalid/not-fetched')
        else: rels.remove(rel)
        changed[relpath]=etree.tostring(rels)
        path=output/(mode+'.docx')
        with ZipFile(path,'w',ZIP_DEFLATED) as z:
            for key,raw in changed.items():z.writestr(key,raw)
        def reject_package(path=path, mode=mode):
            try: docx_pictures(path)
            except ValueError as error:
                require(str(error)==('external_image_not_fetched' if mode=='external' else 'image_relationship_missing_or_wrong_type'),'Wrong package rejection');return
            raise AssertionError('Bad image relation accepted')
        check('Reject '+mode+' image relationship',reject_package)

    truth = normalize(''.join(r['text'] for r in gt)); quality=[]
    for item in items:
        if item['kind']=='docx-image':continue
        record=next(r for r in ocr['results'] if r['id']==item['assetId'])
        observed=normalize(''.join(line['text'] for line in record['lines']))
        quality.append({'sourceName':item['sourceName'],'page':item.get('page'), 'ocrLineCount':len(record['lines']),
                        'characterEdits':distance(truth,observed) if item['sourceName']!='blank.png' else len(observed),
                        'truthCharacters':len(truth) if item['sourceName']!='blank.png' else 0,
                        'exactLineMatches':sum(normalize(g['text']) in observed for g in gt),
                        'criticalValues':{'person': '张明' in observed,'certificate': 'AB0123456789' in observed,
                                          'date':'2028年12月31日' in observed,'amount':'1234567.89元' in observed},
                        'textAngle':record['textAngle'],'rawLines':[line['text'] for line in record['lines']],
                        'status':item['status']})
    for item in items:
        if item['kind']=='docx-image' or item['sourceName'] in ['unreadable.png','blank.png']:continue
        image = Image.open(item['rasterPath'] if item['kind']=='pdf-page' else fixtures/item['sourceName']).convert('RGB')
        draw=ImageDraw.Draw(image)
        for block in [b for b in index['blocks'] if b['itemId']==item['instanceId']]:
            for polygon in block['wordPolygonsOnOriginalImage']:draw.line([tuple(p) for p in polygon]+[tuple(polygon[0])],fill='red',width=3)
        name=Path(item['sourceName']).stem+('-page'+str(item['page']) if item['kind']=='pdf-page' else '')+'.png'
        image.save(output/'overlays'/name)
    for label, block in [('clean', first), ('word', doc_block), ('scan', pdf_block)]:
        resolved=resolve_evidence(fixtures,index,evidence_for_line(index,block));resolved['crop'].save(output/'crops'/(label+'.png'))
    current_file=output/'current-parser.json'
    current_proc=subprocess.run([str(node),'--import','tsx',str(repo/'tools/word-evidence-spike/compare-current.mjs'),str(repo),str(fixtures),str(current_file),'images.docx','scans.pdf'],cwd=repo/'server',capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    current=json.loads(current_file.read_text(encoding='utf-8')) if current_file.exists() else {'reports':[],'error':current_proc.stderr}
    check('Existing parser comparison recorded both file outcomes', lambda:require(current_proc.returncode==0 and {r.get('sourceName') for r in current.get('reports',[])}=={'images.docx','scans.pdf'},'Incomplete parser comparison'))
    check('OCR input files unchanged after recognition', lambda:require(all(digest(Path(a['path']).read_bytes())==key for key,a in assets.items()),'OCR input bytes changed'))
    check('Every original source unchanged including empty OCR inputs',lambda:require(all(digest((fixtures/i['sourceName']).read_bytes())==i['sourceByteHash'] for i in items),'Original source version changed'))
    summary={'synthetic':True,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),
             'sourceOccurrences':len(items),'docxOccurrences':len(pictures),'uniqueOcrInputs':len(assets),'ocrLineEvidenceCount':len(index['blocks']),
             'quality':quality,'geometry':geometry,'minimumAuthoredRegionIoU':min(g['iou'] for g in geometry),
             'checks':checks,'engine':ocr['engine'],'language':ocr['language'],'confidenceAvailable':False,
             'businessIntegrated':False,'paidModelCalls':False,'realCustomerFilesVerified':False,
             'wordPageLocationsVerified':False,'manualUprightPdfPages':[3],
             'sourceHashes':{name:digest((fixtures/name).read_bytes()) for name in [*spec['standaloneImages'],'images.docx','scans.pdf']},
             'currentParser':[{'sourceName':r.get('sourceName'),'ok':r.get('ok'),'chars':r.get('chars'),'error':r.get('error'),
                               'ocrProjectFound':'青松路' in r.get('markdown',''),'ocrPersonFound':'张明' in r.get('markdown',''),
                               'imageEvidenceReturned':'blocks' in r} for r in current.get('reports',[])]}
    (output/'image-ocr-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in {'checks','quality','geometry','sourceHashes'}},ensure_ascii=False,indent=2))
    if summary['failed']:
        print(json.dumps([c for c in checks if not c['passed']],ensure_ascii=False,indent=2));raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['fixtures','output','repo','node','poppler']:p.add_argument('--'+key,type=Path,required=True)
    run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})
