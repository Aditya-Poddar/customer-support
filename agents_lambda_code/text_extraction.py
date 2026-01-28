"""
textract_model.py

Function-based Textract helper that:
- parses s3 URLs
- downloads file to download_dir (e.g. /tmp for Lambda)
- for .txt -> reads file content directly
- for images -> analyze_document (FORMS + TABLES) synchronously
- for pdf -> StartDocumentAnalysis (FORMS + TABLES) async + polling using get_document_analysis
- converts TABLE blocks to structured JSON (rows of cells)
- converts FORMS (key-value pairs) to dict
- returns a dict:
    {
      "file_name": ...,
      "s3_bucket": ...,
      "s3_key": ...,
      "extension": ...,
      "extracted_text": "...",        # concatenated LINE blocks (plain text)
      "tables": [ { "table_index": 0, "rows": [[cell,...],...] }, ... ],
      "forms": { "FieldName": "Value", ... }
    }
"""

import os
import time
from urllib.parse import urlparse
import boto3

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# ---------- S3/URL helpers ----------
def parse_s3_url(s3_url):
    parsed = urlparse(s3_url)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
    else:
        netloc_parts = parsed.netloc.split(".")
        # virtual-hosted style: bucket.s3.region.amazonaws.com
        if len(netloc_parts) >= 3 and "s3" in netloc_parts:
            bucket = netloc_parts[0]
            key = parsed.path.lstrip("/")
        else:
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if len(path_parts) == 2:
                bucket, key = path_parts
            else:
                raise ValueError(f"Unable to parse S3 URL: {s3_url}")
    return bucket, key

def download_s3_object(bucket, key, download_path, s3_client=None):
    s3 = s3_client or boto3.client("s3")
    os.makedirs(os.path.dirname(download_path), exist_ok=True)
    s3.download_file(bucket, key, download_path)

# ---------- Block helpers ----------
def _blocks_map(blocks):
    """
    Return maps for convenient lookup:
      - id_map: block_id -> block
      - child_map: block_id -> list(child block ids)
    """
    id_map = {}
    child_map = {}
    for b in blocks:
        bid = b.get("Id") or b.get("BlockId") or b.get("Id")  # consistency
        id_map[bid] = b
        # collect relationships children (if any)
        rels = b.get("Relationships", [])
        children = []
        for r in rels:
            if r.get("Type") in ("CHILD", "VALUE", "KEY"):
                children.extend(r.get("Ids", []))
        child_map[bid] = children
    return id_map, child_map

def _get_text_for_block(block, id_map):
    """
    Given a block that is a WORD/SELECTION_ELEMENT/LINE, reconstruct text using children if needed.
    For WORD blocks, block["Text"] exists. For SELECTION_ELEMENT, use SelectionStatus.
    For blocks that have CHILD relationships to WORD/SELECTION_ELEMENT, walk them.
    """
    text_chunks = []
    rels = block.get("Relationships", [])
    for r in rels:
        if r.get("Type") == "CHILD":
            for cid in r.get("Ids", []):
                child = id_map.get(cid, {})
                btype = child.get("BlockType")
                if btype == "WORD":
                    text_chunks.append(child.get("Text", ""))
                elif btype == "SELECTION_ELEMENT":
                    # selection elements: SelectionStatus is 'SELECTED' or 'NOT_SELECTED'
                    if child.get("SelectionStatus") == "SELECTED":
                        text_chunks.append("X")
    # If no CHILD relationship, maybe block itself has "Text"
    if not text_chunks:
        if "Text" in block:
            return block.get("Text", "")
    return " ".join(text_chunks).strip()

def extract_plain_text_from_blocks(blocks):
    """
    Return concatenated LINE blocks as plain text (joined with newlines).
    """
    lines = []
    for b in blocks:
        if b.get("BlockType") == "LINE":
            lines.append(b.get("Text", ""))
    return "\n".join(lines).strip()

# ---------- Forms (key-value) parsing ----------
def get_kv_map(blocks):
    """
    Parse key-value pairs from analysis blocks using typical Textract block relationships.
    Returns dict mapping key text -> value text.
    """
    id_map, child_map = _blocks_map(blocks)
    # find key blocks and value blocks
    key_map = {}
    value_map = {}
    # Identify KEY_VALUE_SET blocks with EntityTypes
    for b in blocks:
        if b.get("BlockType") == "KEY_VALUE_SET":
            entity_types = b.get("EntityTypes", [])
            if "KEY" in entity_types:
                key_map[b["Id"]] = b
            elif "VALUE" in entity_types:
                value_map[b["Id"]] = b

    # helper: given a KEY block, find linked VALUE block ids via Relationships 'VALUE'
    def _get_value_ids_for_key(key_block):
        value_ids = []
        for rel in key_block.get("Relationships", []) or []:
            if rel.get("Type") == "VALUE":
                value_ids.extend(rel.get("Ids", []))
        return value_ids

    # helper: get text for a key or value block by traversing CHILD->WORD/SELECTION_ELEMENT
    def _block_text(b):
        # If b has CHILD relationships, get words from them
        text = _get_text_for_block(b, id_map)
        if text:
            return text
        # fallback: if has children directly in child_map
        texts = []
        for cid in child_map.get(b["Id"], []):
            child = id_map.get(cid, {})
            if child.get("BlockType") == "WORD":
                texts.append(child.get("Text", ""))
            elif child.get("BlockType") == "SELECTION_ELEMENT":
                if child.get("SelectionStatus") == "SELECTED":
                    texts.append("X")
        return " ".join(texts).strip()

    kv = {}
    # For each key block, find corresponding value block(s) and build texts
    for kid, kblock in key_map.items():
        key_text = _block_text(kblock)
        value_texts = []
        for vid in _get_value_ids_for_key(kblock):
            vblock = value_map.get(vid) or id_map.get(vid)
            if vblock:
                value_texts.append(_block_text(vblock))
        kv[key_text] = "\n".join([vt for vt in value_texts if vt]).strip()
    return kv

# ---------- Tables parsing ----------
def get_tables_from_blocks(blocks):
    """
    Reconstruct TABLE blocks into a list of tables. Each table becomes:
      { "table_index": int, "rows": [ [cell_text, ...], ... ] }
    This aims to preserve ordering using RowIndex/ColumnIndex metadata in CELL blocks.
    """
    id_map, child_map = _blocks_map(blocks)
    tables = []
    table_count = 0
    # find TABLE blocks
    for b in blocks:
        if b.get("BlockType") == "TABLE":
            table_count += 1
            table_id = b.get("Id")
            # find CELL children of this TABLE (via Relationships)
            cell_ids = []
            for rel in b.get("Relationships", []) or []:
                if rel.get("Type") == "CHILD":
                    cell_ids.extend(rel.get("Ids", []))
            # collect cells by (RowIndex, ColumnIndex)
            cells_by_pos = {}
            max_row = 0
            max_col = 0
            for cid in cell_ids:
                cell = id_map.get(cid, {})
                if not cell or cell.get("BlockType") != "CELL":
                    continue
                row = cell.get("RowIndex", 0)
                col = cell.get("ColumnIndex", 0)
                if row > max_row: max_row = row
                if col > max_col: max_col = col
                # get text inside cell by traversing CHILD -> WORD/SELECTION_ELEMENT
                text = _get_text_for_block(cell, id_map)
                # fallback: if empty, try to collect child WORD blocks manually
                if not text:
                    pieces = []
                    for rel in cell.get("Relationships", []) or []:
                        if rel.get("Type") == "CHILD":
                            for subid in rel.get("Ids", []):
                                sub = id_map.get(subid, {})
                                if sub.get("BlockType") == "WORD":
                                    pieces.append(sub.get("Text", ""))
                                elif sub.get("BlockType") == "SELECTION_ELEMENT":
                                    if sub.get("SelectionStatus") == "SELECTED":
                                        pieces.append("X")
                    text = " ".join(pieces).strip()
                cells_by_pos[(row, col)] = text

            # build 2D rows (1-indexed)
            rows = []
            for r in range(1, max_row+1):
                row_cells = []
                for c in range(1, max_col+1):
                    row_cells.append(cells_by_pos.get((r,c), ""))
                rows.append(row_cells)

            tables.append({
                "table_index": table_count - 1,
                "rows": rows
            })
    return tables

# ---------- Main processing logic ----------
def analyze_local_image(file_path, textract_client=None):
    """
    For images we can call analyze_document synchronously with Synchronous API.
    Note: analyze_document is synchronous and supports FORMS + TABLES.
    """
    textract = textract_client or boto3.client("textract")
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    resp = textract.analyze_document(Document={"Bytes": img_bytes}, FeatureTypes=["TABLES", "FORMS"])
    blocks = resp.get("Blocks", [])
    plain_text = extract_plain_text_from_blocks(blocks)
    tables = get_tables_from_blocks(blocks)
    forms = get_kv_map(blocks)
    return plain_text, tables, forms

def start_and_poll_document_analysis(bucket, key, textract_client=None, max_attempts=120, poll_interval=2):
    """
    StartDocumentAnalysis for PDFs (or other file types stored in S3) and poll get_document_analysis until SUCCEEDED.
    """
    textract = textract_client or boto3.client("textract")
    start_resp = textract.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=["TABLES", "FORMS"]
    )
    job_id = start_resp["JobId"]
    attempt = 0
    job_status = "IN_PROGRESS"
    all_blocks = []
    while attempt < max_attempts and job_status == "IN_PROGRESS":
        time.sleep(poll_interval)
        attempt += 1
        get_resp = textract.get_document_analysis(JobId=job_id)
        job_status = get_resp.get("JobStatus")
        if job_status == "SUCCEEDED":
            all_blocks.extend(get_resp.get("Blocks", []))
            next_token = get_resp.get("NextToken")
            while next_token:
                paged = textract.get_document_analysis(JobId=job_id, NextToken=next_token)
                all_blocks.extend(paged.get("Blocks", []))
                next_token = paged.get("NextToken")
            plain_text = extract_plain_text_from_blocks(all_blocks)
            tables = get_tables_from_blocks(all_blocks)
            forms = get_kv_map(all_blocks)
            return plain_text, tables, forms
        elif job_status == "FAILED":
            raise RuntimeError(f"Textract analysis job failed (JobId={job_id})")
        # else continue polling
    raise TimeoutError(f"Timed out waiting for Textract analysis (JobId={job_id}) after {attempt} attempts")

def detect_text_from_bytes_as_plain(file_path, textract_client=None):
    """
    Fallback detect_document_text to obtain LINE blocks only (no tables/forms).
    """
    textract = textract_client or boto3.client("textract")
    with open(file_path, "rb") as f:
        data = f.read()
    resp = textract.detect_document_text(Document={"Bytes": data})
    blocks = resp.get("Blocks", [])
    return extract_plain_text_from_blocks(blocks)

def process_s3_url(
    s3_url,
    download_dir="/tmp",
    s3_client=None,
    textract_client=None,
    max_attempts=120,
    poll_interval=2
):
    """
    Main entry point.
    Returns {
        file_name, s3_bucket, s3_key, extension,
        extracted_text (plain),
        tables (list of tables as rows arrays),
        forms (dict of key->value)
    }
    """
    s3 = s3_client or boto3.client("s3")
    textract = textract_client or boto3.client("textract")

    bucket, key = parse_s3_url(s3_url)
    file_name = os.path.basename(key)
    ext = os.path.splitext(file_name.lower())[1]
    download_path = os.path.join(download_dir, file_name)

    # download
    download_s3_object(bucket, key, download_path, s3_client=s3)

    # .txt => read directly
    if ext == ".txt":
        with open(download_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return {
            "file_name": file_name,
            "s3_bucket": bucket,
            "s3_key": key,
            "extension": ext,
            "extracted_text": text,
            "tables": [],
            "forms": {}
        }

    # images => synchronous analyze_document (tables + forms)
    if ext in IMAGE_EXTS:
        plain_text, tables, forms = analyze_local_image(download_path, textract_client=textract)
        return {
            "file_name": file_name,
            "s3_bucket": bucket,
            "s3_key": key,
            "extension": ext,
            "extracted_text": plain_text,
            "tables": tables,
            "forms": forms
        }

    # pdf => async StartDocumentAnalysis & poll
    if ext == ".pdf":
        plain_text, tables, forms = start_and_poll_document_analysis(
            bucket, key, textract_client=textract, max_attempts=max_attempts, poll_interval=poll_interval
        )
        return {
            "file_name": file_name,
            "s3_bucket": bucket,
            "s3_key": key,
            "extension": ext,
            "extracted_text": plain_text,
            "tables": tables,
            "forms": forms
        }

    # fallback -> try synchronous detect_document_text for best-effort plain text,
    # but try analyze_document via S3 StartDocumentAnalysis if you want tables/forms on other file types.
    try:
        plain_text = detect_text_from_bytes_as_plain(download_path, textract_client=textract)
        return {
            "file_name": file_name,
            "s3_bucket": bucket,
            "s3_key": key,
            "extension": ext,
            "extracted_text": plain_text,
            "tables": [],
            "forms": {}
        }
    except Exception as e:
        raise RuntimeError(f"Failed to extract text for extension {ext}: {e}")
