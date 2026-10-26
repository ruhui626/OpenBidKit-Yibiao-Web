"""Offline DOCX structure/location experiment; not a production parser or API."""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from lxml import etree

WORD_NS = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
PART = "word/document.xml"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_package(source: Path) -> tuple[str, dict[str, bytes]]:
    if source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("prototype_file_size_limit")
    raw = source.read_bytes()
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("prototype_file_size_limit")
    raw_hash = digest(raw)
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                raise ValueError("prototype_zip_expansion_limit")
            names = [e.filename for e in entries]
            if len(names) != len(set(names)):
                raise ValueError("duplicate_zip_member")
            for entry in entries:
                name = entry.filename
                if "\\" in name or ":" in name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                    raise ValueError("unsafe_zip_member")
                if entry.flag_bits & 1 or name.lower().endswith("vbaproject.bin"):
                    raise ValueError("encrypted_or_macro_package")
            if PART not in names or "[Content_Types].xml" not in names:
                raise ValueError("not_a_docx_package")
            return raw_hash, {e.filename: archive.read(e) for e in entries if not e.is_dir()}
    except BadZipFile as error:
        raise ValueError("invalid_zip") from error


def xml_root(data: bytes):
    if re.search(br"<!DOCTYPE|<!ENTITY", data, re.IGNORECASE):
        raise ValueError("dtd_or_entity_not_allowed")
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, recover=False)
    try:
        return etree.fromstring(data, parser)
    except etree.XMLSyntaxError as error:
        raise ValueError("invalid_xml") from error


def word_local(node, uri):
    if not isinstance(node.tag, str):
        return None
    name = etree.QName(node)
    return name.localname if name.namespace == uri else None


def ancestor(node, local, uri):
    return next((p for p in node.iterancestors() if word_local(p, uri) == local), None)


def paragraph_text(paragraph, uri):
    out = []
    for item in paragraph.iterdescendants():
        if ancestor(item, "p", uri) is not paragraph:
            continue
        if any(word_local(p, uri) in {"del", "moveFrom", "txbxContent"} for p in item.iterancestors()):
            continue
        name = word_local(item, uri)
        if name == "t":
            out.append(item.text or "")
        elif name == "tab":
            out.append("\t")
        elif name in {"br", "cr"}:
            out.append("\n")
    return "".join(out)


def location(node, uri):
    namespaces = {"w": uri}
    steps = []
    for item in [*reversed(list(node.iterancestors())), node]:
        qname = etree.QName(item)
        if not qname.namespace:
            raise ValueError("unnamespaced_container")
        prefix = next((k for k, v in namespaces.items() if v == qname.namespace), None)
        if prefix is None:
            prefix = f"n{len(namespaces)}"
            namespaces[prefix] = qname.namespace
        ordinal = 1 + sum(s.tag == item.tag for s in item.itersiblings(preceding=True))
        steps.append(f"{prefix}:{qname.localname}[{ordinal}]")
    return "/" + "/".join(steps), namespaces


def block_id(file_hash, xpath):
    return digest(f"{file_hash}|{PART}|{xpath}".encode())[:24]


def table_coordinates(paragraph, table_ids, uri):
    ns = {"w": uri}
    chain = []
    for table in reversed([p for p in paragraph.iterancestors() if word_local(p, uri) == "tbl"]):
        cell = next(p for p in paragraph.iterancestors() if word_local(p, uri) == "tc" and ancestor(p, "tbl", uri) is table)
        row = ancestor(cell, "tr", uri)
        rows = table.findall(f"{{{uri}}}tr")
        cells = row.findall(f"{{{uri}}}tc")
        before = row.find("w:trPr/w:gridBefore", ns)
        start_column = int(before.get(f"{{{uri}}}val", "0")) if before is not None else 0
        for previous in cells[:cells.index(cell)]:
            span = previous.find("w:tcPr/w:gridSpan", ns)
            start_column += int(span.get(f"{{{uri}}}val", "1")) if span is not None else 1
        span = cell.find("w:tcPr/w:gridSpan", ns)
        merge = cell.find("w:tcPr/w:vMerge", ns)
        chain.append({
            "tableIndex": table_ids[table], "xmlRow": rows.index(row) + 1,
            "physicalCell": cells.index(cell) + 1, "gridColumn": start_column + 1,
            "gridSpan": int(span.get(f"{{{uri}}}val", "1")) if span is not None else 1,
            "verticalMerge": None if merge is None else merge.get(f"{{{uri}}}val", "continue"),
        })
    return chain


def extract(source: Path):
    file_hash, parts = read_package(source)
    root = xml_root(parts[PART])
    uri = etree.QName(root).namespace
    if uri not in WORD_NS or etree.QName(root).localname != "document":
        raise ValueError("unsupported_word_namespace")
    ns = {"w": uri}
    body = root.find("w:body", ns)
    if body is None:
        raise ValueError("missing_document_body")
    table_ids = {t: i for i, t in enumerate(body.findall(".//w:tbl", ns), 1)}
    blocks, headings = [], []
    for ordinal, paragraph in enumerate(body.findall(".//w:p", ns), 1):
        if ancestor(paragraph, "txbxContent", uri) is not None:
            continue
        text = paragraph_text(paragraph, uri)
        if not text.strip():
            continue
        style = paragraph.find("w:pPr/w:pStyle", ns)
        style_id = style.get(f"{{{uri}}}val", "") if style is not None else ""
        heading = re.fullmatch(r"Heading([1-9])", style_id)
        if heading and ancestor(paragraph, "tbl", uri) is None:
            level = int(heading.group(1))
            headings = headings[:level - 1] + [text]
        xpath, namespaces = location(paragraph, uri)
        chain = table_coordinates(paragraph, table_ids, uri)
        flags = []
        if paragraph.xpath(".//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo", namespaces=ns):
            flags.append("tracked_changes_require_review")
        if paragraph.xpath(".//w:fldSimple | .//w:fldChar | .//w:instrText", namespaces=ns):
            flags.append("cached_field_result_only")
        if paragraph.xpath(".//w:vanish", namespaces=ns):
            flags.append("hidden_text_requires_review")
        if paragraph.xpath(".//w:numPr", namespaces=ns) or style_id.startswith("List"):
            flags.append("automatic_numbering_not_rendered")
        blocks.append({
            "id": block_id(file_hash, xpath), "part": PART, "xpath": xpath,
            "namespaces": namespaces, "kind": "table-paragraph" if chain else "body-paragraph",
            "bodyXmlParagraphOrdinal": ordinal, "headingPath": list(headings),
            "tablePath": chain, "styleId": style_id, "text": text,
            "textHash": digest(text.encode()), "flags": flags,
        })
    uncovered = []
    for pattern, label in [(r"word/header\d*\.xml", "headers"), (r"word/footer\d*\.xml", "footers"),
                           (r"word/footnotes\.xml", "footnotes"), (r"word/endnotes\.xml", "endnotes"),
                           (r"word/comments.*\.xml", "comments")]:
        if any(re.fullmatch(pattern, name) for name in parts):
            uncovered.append(label)
    for expression, label in [(".//w:drawing | .//w:pict", "image_or_drawing_contents"),
                              (".//w:txbxContent", "textboxes"), (".//w:altChunk", "embedded_alt_chunk"),
                              (".//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo", "tracked_changes_semantics"),
                              (".//w:fldSimple | .//w:fldChar", "dynamic_field_semantics")]:
        if body.xpath(expression, namespaces=ns):
            uncovered.append(label)
    return {"sourceName": source.name, "byteHash": file_hash, "parserVersion": "offline-structure-spike-v1",
            "blocks": blocks, "tableCount": len(table_ids), "coverage": {
                "supported": ["body_text", "physical_table_cells", "nested_tables", "merge_metadata"],
                "uncovered": uncovered, "pageNumbersVerified": False,
                "customHeadingStyleInheritanceVerified": False,
                "offsetUnit": "unicode-code-point",
            }}


def evidence_for(document, block, quote):
    starts = [m.start() for m in re.finditer(re.escape(quote), block["text"])] if quote else []
    if len(starts) != 1:
        raise ValueError("quote_must_be_unique_within_block")
    return {"sourceByteHash": document["byteHash"], "blockId": block["id"], "part": block["part"],
            "xpath": block["xpath"], "namespaces": block["namespaces"], "quote": quote,
            "start": starts[0], "end": starts[0] + len(quote), "offsetUnit": "unicode-code-point"}


def resolve(source: Path, evidence):
    file_hash, parts = read_package(source)
    if file_hash != evidence["sourceByteHash"]:
        raise ValueError("source_version_mismatch")
    xpath = evidence["xpath"]
    if evidence["part"] != PART or not re.fullmatch(r"(?:/[a-z][a-z0-9]*:[A-Za-z][A-Za-z0-9]*\[[1-9][0-9]*\])+", xpath):
        raise ValueError("invalid_locator")
    if evidence["blockId"] != block_id(file_hash, xpath) or evidence.get("offsetUnit") != "unicode-code-point":
        raise ValueError("invalid_block_or_offsets")
    root = xml_root(parts[PART])
    nodes = root.xpath(xpath, namespaces=evidence["namespaces"])
    uri = etree.QName(root).namespace
    if len(nodes) != 1 or word_local(nodes[0], uri) != "p":
        raise ValueError("locator_not_a_unique_paragraph")
    text = paragraph_text(nodes[0], uri)
    start, end = evidence["start"], evidence["end"]
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(text):
        raise ValueError("invalid_range")
    if text[start:end] != evidence["quote"]:
        raise ValueError("quote_does_not_match_original")
    return {"text": text, "quote": text[start:end], "xml": etree.tostring(nodes[0], encoding="unicode")}


# shortcut: this proof checks structural positions, not Word page layout or GUI navigation.
