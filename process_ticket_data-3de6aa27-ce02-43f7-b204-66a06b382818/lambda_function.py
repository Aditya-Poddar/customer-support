import os
import io
import json
import boto3
import pandas as pd
from urllib.parse import unquote_plus

s3 = boto3.client("s3")

INPUT_BUCKET = os.getenv("INPUT_BUCKET", "lai2-handson-111225")
INPUT_PREFIX = os.getenv("INPUT_PREFIX", "data/support_ticket/")
OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", INPUT_BUCKET)
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "customer_support_agent/support_ticket/")
CHUNK_RECORDS = int(os.getenv("CHUNK_RECORDS", "200"))
SINGLE_FILE_THRESHOLD_BYTES = int(os.getenv("SINGLE_FILE_THRESHOLD_BYTES", str(50 * 1024 * 1024)))


def upload_bytes(bucket: str, key: str, b: bytes, content_type: str="application/json"):
    s3.put_object(Bucket=bucket, Key=key, Body=b, ContentType=content_type)


def safe_read_csv(content):
    """
    Try reading CSV using robust settings.
    If pandas fails, fallback to manual split.
    """
    try:
        return pd.read_csv(
            io.StringIO(content),
            dtype=str,
            keep_default_na=False,
            na_values=[],
            encoding="utf-8",
            engine="python",          # More tolerant parser
            on_bad_lines="skip"       # Skip malformed rows
        )
    except Exception as e:
        print("❌ Pandas failed, switching to manual parse:", str(e))
        lines = content.split("\n")
        header = lines[0].split(",")
        rows = []

        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) != len(header):
                continue
            rows.append(dict(zip(header, parts)))

        return pd.DataFrame(rows)


def process_object(key: str):
    key = unquote_plus(key)
    head = s3.head_object(Bucket=INPUT_BUCKET, Key=key)
    size = head.get("ContentLength", 0)

    base = key.split("/")[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base

    obj = s3.get_object(Bucket=INPUT_BUCKET, Key=key)
    body = obj["Body"].read().decode("utf-8", errors="replace")

    # ---------- SMALL FILE ----------
    if size <= SINGLE_FILE_THRESHOLD_BYTES:
        df = safe_read_csv(body)
        records = df.to_dict(orient="records")

        out_key = f"{OUTPUT_PREFIX.rstrip('/')}/{stem}.json"
        upload_bytes(OUTPUT_BUCKET, out_key, json.dumps(records, indent=2).encode("utf-8"))
        return [out_key]

    # ---------- LARGE FILE ----------
    uploaded = []
    stream = io.StringIO(body)

    try:
        chunk_iter = pd.read_csv(
            stream,
            dtype=str,
            keep_default_na=False,
            na_values=[],
            chunksize=CHUNK_RECORDS,
            encoding="utf-8",
            engine="python",
            on_bad_lines="skip"
        )
    except Exception:
        # fallback: split manually
        lines = body.split("\n")
        header = lines[0].split(",")

        chunk, counter = [], 0
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) != len(header):
                continue
            chunk.append(dict(zip(header, parts)))

            if len(chunk) == CHUNK_RECORDS:
                counter += 1
                out_key = f"{OUTPUT_PREFIX.rstrip('/')}/{stem}_chunk_{counter}.json"
                upload_bytes(OUTPUT_BUCKET, out_key, json.dumps(chunk, indent=2).encode("utf-8"))
                uploaded.append(out_key)
                chunk = []
        return uploaded

    for i, chunk_df in enumerate(chunk_iter):
        records = chunk_df.to_dict(orient="records")
        out_key = f"{OUTPUT_PREFIX.rstrip('/')}/{stem}_chunk_{i+1}.json"

        upload_bytes(OUTPUT_BUCKET, out_key, json.dumps(records, indent=2).encode("utf-8"))
        uploaded.append(out_key)

    return uploaded


def lambda_handler(event, context):
    uploaded_summary = {}

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=INPUT_BUCKET, Prefix=INPUT_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue

            try:
                uploaded_summary[key] = process_object(key)
            except Exception as e:
                uploaded_summary[key] = {"error": str(e)}

    return {"status": "completed", "summary": uploaded_summary}
