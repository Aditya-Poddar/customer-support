# app.py
import streamlit as st
import boto3
import requests
import io
import uuid
import random
from urllib.parse import quote
from botocore.exceptions import ClientError, NoCredentialsError

# -------------------------------------------------------
# Load configuration from .streamlit/secrets.toml
# -------------------------------------------------------
AWS_ACCESS_KEY_ID     = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
AWS_REGION            = st.secrets["AWS_REGION"]
S3_BUCKET             = st.secrets["S3_BUCKET"]
KEY_PREFIX            = st.secrets["KEY_PREFIX"]
API_ENDPOINT          = st.secrets["API_ENDPOINT"]

# -------------------------------------------------------
# AUTO-GENERATE user_id + session_id ON PAGE REFRESH
# -------------------------------------------------------
def generate_user_id():
    return f"USR-{random.randint(10000, 99999)}"

def generate_session_id():
    return f"SES-{uuid.uuid4().hex[:10]}"

# Store in session_state so they don’t regenerate on button click
if "user_id" not in st.session_state:
    st.session_state["user_id"] = generate_user_id()

if "session_id" not in st.session_state:
    st.session_state["session_id"] = generate_session_id()

# -------------------------------------------------------
# Create boto3 client using AWS secrets
# -------------------------------------------------------
session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)
s3 = session.client("s3")

# -------------------------------------------------------
# Streamlit UI
# -------------------------------------------------------
st.set_page_config(page_title="S3 Upload → API Sender", layout="centered")
st.title("📤 Upload to S3 → Auto Payload Sender")

uploaded_file = st.file_uploader("Choose a file to upload")

# Automatically filled fields
user_id = st.text_input("User ID (auto-generated)", st.session_state["user_id"])
session_id = st.text_input("Session ID (auto-generated)", st.session_state["session_id"])

make_public = st.checkbox("Make file public (ACL = public-read)", False)

if st.button("Upload & Send"):
    if not uploaded_file:
        st.error("Please upload a file first.")
        st.stop()

    filename = uploaded_file.name
    key = f"{KEY_PREFIX}/{filename}".strip("/")
    key_encoded = quote(key, safe="/")

    st.info(f"Uploading **{filename}** to S3...")

    try:
        # Upload file to S3
        args = {"ContentType": uploaded_file.type or "application/octet-stream"}
        if make_public:
            args["ACL"] = "public-read"

        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=uploaded_file.getvalue(),
            **args
        )

        # Build object URL
        s3_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key_encoded}"

        st.success("Upload successful!")
        st.code(s3_url)

        # ---------------------------------------------------
        # Build API payload (your required format)
        # ---------------------------------------------------
        payload = {
            "s3_url": s3_url,
            "user_id": user_id,
            "session_id": session_id
        }

        st.subheader("📡 Payload Sent to API")
        st.code(payload, language="json")

        # Send payload to your API
        response = requests.post(API_ENDPOINT, json=payload)

        st.subheader("📝 API Response")
        try:
            st.json(response.json())
        except:
            st.text(response.text)

        if response.ok:
            st.success("Payload sent successfully!")
        else:
            st.error(f"API returned status {response.status_code}")

    except NoCredentialsError:
        st.error(" No AWS credentials found! Check .streamlit/secrets.toml.")
    except ClientError as e:
        st.error(f" AWS Error: {e}")
    except Exception as e:
        st.error(f" Unexpected error: {e}")
