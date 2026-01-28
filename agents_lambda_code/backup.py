"""
textract_model.py (function-based)

Now includes:
- If extension == ".txt": read file directly and return its text
"""

import os
import time
from urllib.parse import urlparse
import boto3

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def parse_s3_url(s3_url):
    parsed = urlparse(s3_url)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
    else:
        netloc_parts = parsed.netloc.split(".")
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


def extract_text_from_blocks(blocks):
    lines = []
    for block in blocks:
        if block.get("BlockType") == "LINE":
            lines.append(block.get("Text", ""))
    return "\n".join(lines).strip()


def detect_text_from_bytes(file_path, textract_client=None):
    textract = textract_client or boto3.client("textract")
    with open(file_path, "rb") as f:
        data = f.read()
    resp = textract.detect_document_text(Document={"Bytes": data})
    blocks = resp.get("Blocks", [])
    return extract_text_from_blocks(blocks)


def start_and_poll_pdf(bucket, key, textract_client=None, max_attempts=60, poll_interval=2):
    textract = textract_client or boto3.client("textract")

    start_resp = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )
    job_id = start_resp["JobId"]

    attempt = 0
    job_status = "IN_PROGRESS"
    all_blocks = []

    while attempt < max_attempts and job_status == "IN_PROGRESS":
        time.sleep(poll_interval)
        attempt += 1

        get_resp = textract.get_document_text_detection(JobId=job_id)
        job_status = get_resp.get("JobStatus")

        if job_status == "SUCCEEDED":
            all_blocks.extend(get_resp.get("Blocks", []))
            next_token = get_resp.get("NextToken")
            while next_token:
                paged = textract.get_document_text_detection(JobId=job_id, NextToken=next_token)
                all_blocks.extend(paged.get("Blocks", []))
                next_token = paged.get("NextToken")
            return extract_text_from_blocks(all_blocks)

        elif job_status == "FAILED":
            raise RuntimeError(f"Textract job failed for JobId={job_id}")

    raise TimeoutError(f"Timed out waiting for Textract PDF job after {attempt} attempts")


def process_s3_url(
    s3_url,
    download_dir="/tmp",
    s3_client=None,
    textract_client=None,
    max_attempts=60,
    poll_interval=2
):
    s3 = s3_client or boto3.client("s3")
    textract = textract_client or boto3.client("textract")

    bucket, key = parse_s3_url(s3_url)
    file_name = os.path.basename(key)
    ext = os.path.splitext(file_name.lower())[1]
    download_path = os.path.join(download_dir, file_name)

    # Download file
    download_s3_object(bucket, key, download_path, s3_client=s3)

    # -------------------------------
    # NEW: .TXT FILE HANDLING
    # -------------------------------
    if ext == ".txt":
        with open(download_path, "r", encoding="utf-8", errors="ignore") as f:
            extracted_text = f.read()

        return {
            "file_name": file_name,
            "s3_bucket": bucket,
            "s3_key": key,
            "extension": ext,
            "extracted_text": extracted_text
        }

    # Images → synchronous Textract
    if ext in IMAGE_EXTS:
        extracted_text = detect_text_from_bytes(download_path, textract_client=textract)

    # PDF → async Textract job
    elif ext == ".pdf":
        extracted_text = start_and_poll_pdf(
            bucket, key,
            textract_client=textract,
            max_attempts=max_attempts,
            poll_interval=poll_interval
        )

    # Other file types → fallback Textract attempt
    else:
        try:
            extracted_text = detect_text_from_bytes(download_path, textract_client=textract)
        except Exception as e:
            raise ValueError(f"Unsupported extension {ext} and detect_document_text failed: {e}")

    return {
        "file_name": file_name,
        "s3_bucket": bucket,
        "s3_key": key,
        "extension": ext,
        "extracted_text": extracted_text
    }
