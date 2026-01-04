# # app.py
# import streamlit as st
# import boto3
# import requests
# import io
# import uuid
# import random
# from urllib.parse import quote
# from botocore.exceptions import ClientError, NoCredentialsError

# # -------------------------------------------------------
# # Load configuration from .streamlit/secrets.toml
# # -------------------------------------------------------
# AWS_ACCESS_KEY_ID     = st.secrets["AWS_ACCESS_KEY_ID"]
# AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
# AWS_REGION            = st.secrets["AWS_REGION"]
# S3_BUCKET             = st.secrets["S3_BUCKET"]
# KEY_PREFIX            = st.secrets["KEY_PREFIX"]
# API_ENDPOINT          = st.secrets["API_ENDPOINT"]

# # -------------------------------------------------------
# # AUTO-GENERATE user_id + session_id ON PAGE REFRESH
# # -------------------------------------------------------
# def generate_user_id():
#     return f"USR-{random.randint(10000, 99999)}"

# def generate_session_id():
#     return f"SES-{uuid.uuid4().hex[:10]}"

# # Store in session_state so they don't regenerate on button click
# if "user_id" not in st.session_state:
#     st.session_state["user_id"] = generate_user_id()

# if "session_id" not in st.session_state:
#     st.session_state["session_id"] = generate_session_id()

# # -------------------------------------------------------
# # Create boto3 client using AWS secrets
# # -------------------------------------------------------
# session = boto3.Session(
#     aws_access_key_id=AWS_ACCESS_KEY_ID,
#     aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
#     region_name=AWS_REGION
# )
# s3 = session.client("s3")

# # -------------------------------------------------------
# # Streamlit UI
# # -------------------------------------------------------
# st.set_page_config(page_title="S3 Upload & Query API", layout="centered")
# st.title("📤 File Upload & Query API Interface")

# # Automatically filled fields (at the top)
# user_id = st.text_input("User ID (auto-generated)", st.session_state["user_id"])
# session_id = st.text_input("Session ID (auto-generated)", st.session_state["session_id"])

# st.divider()

# # -------------------------------------------------------
# # TAB 1: FILE UPLOAD MODE
# # -------------------------------------------------------
# tab1, tab2 = st.tabs(["📁 File Upload", "💬 Query Mode"])

# with tab1:
#     st.subheader("Upload File to S3")
#     uploaded_file = st.file_uploader("Choose a file to upload")
#     make_public = st.checkbox("Make file public (ACL = public-read)", False)

#     if st.button("Upload & Send to API", key="upload_btn"):
#         if not uploaded_file:
#             st.error("Please upload a file first.")
#         else:
#             filename = uploaded_file.name
#             key = f"{KEY_PREFIX}/{filename}".strip("/")
#             key_encoded = quote(key, safe="/")

#             st.info(f"Uploading **{filename}** to S3...")

#             try:
#                 # Upload file to S3
#                 args = {"ContentType": uploaded_file.type or "application/octet-stream"}
#                 if make_public:
#                     args["ACL"] = "public-read"

#                 s3.put_object(
#                     Bucket=S3_BUCKET,
#                     Key=key,
#                     Body=uploaded_file.getvalue(),
#                     **args
#                 )

#                 # Build object URL
#                 s3_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key_encoded}"

#                 st.success("✅ Upload successful!")
#                 st.code(s3_url)

#                 # Build API payload with s3_url
#                 payload = {
#                     "s3_url": s3_url,
#                     "user_id": user_id,
#                     "session_id": session_id
#                 }

#                 st.subheader("📡 Payload Sent to API")
#                 st.json(payload)

#                 # Send payload to your API
#                 response = requests.post(API_ENDPOINT, json=payload)

#                 st.subheader("📝 API Response")
#                 try:
#                     st.json(response.json())
#                 except:
#                     st.text(response.text)

#                 if response.ok:
#                     st.success("✅ Payload sent successfully!")
#                 else:
#                     st.error(f"❌ API returned status {response.status_code}")

#             except NoCredentialsError:
#                 st.error("❌ No AWS credentials found! Check .streamlit/secrets.toml.")
#             except ClientError as e:
#                 st.error(f"❌ AWS Error: {e}")
#             except Exception as e:
#                 st.error(f"❌ Unexpected error: {e}")

# # -------------------------------------------------------
# # TAB 2: QUERY MODE
# # -------------------------------------------------------
# with tab2:
#     st.subheader("Send Query to API")
    
#     query_input = st.text_area(
#         "Enter your query:", 
#         placeholder="e.g., how to resolve System Interruption",
#         height=100
#     )

#     if st.button("Send Query", key="query_btn"):
#         if not query_input.strip():
#             st.error("Please enter a query first.")
#         else:
#             # Build API payload with query
#             payload = {
#                 "user_id": user_id,
#                 "session_id": session_id,
#                 "method": "test_kb",
#                 "query": query_input.strip()
#             }

#             st.subheader("📡 Payload Sent to API")
#             st.json(payload)

#             try:
#                 # Send payload to your API
#                 response = requests.post(API_ENDPOINT, json=payload)

#                 st.subheader("📝 API Response")
#                 try:
#                     st.json(response.json())
#                 except:
#                     st.text(response.text)

#                 if response.ok:
#                     st.success("✅ Query sent successfully!")
#                 else:
#                     st.error(f"❌ API returned status {response.status_code}")

#             except Exception as e:
#                 st.error(f"❌ Unexpected error: {e}")








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
# Streamlit UI - Compact Layout
# -------------------------------------------------------
st.set_page_config(
    page_title="File Upload & Query API", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for compact spacing
st.markdown("""
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 1rem;
        max-width: 1200px;
    }
    h1 {
        margin-bottom: 1rem;
        font-size: 2rem;
    }
    .stTextInput > div > div > input {
        padding: 0.5rem;
    }
    .stTextArea > div > div > textarea {
        padding: 0.5rem;
    }
    [data-testid="stVerticalBlock"] {
        gap: 0.5rem;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📤 File Upload & Query API Interface")

# Compact session info in columns
col1, col2 = st.columns(2)
with col1:
    user_id = st.text_input("User ID", st.session_state["user_id"], label_visibility="collapsed", placeholder="User ID")
with col2:
    session_id = st.text_input("Session ID", st.session_state["session_id"], label_visibility="collapsed", placeholder="Session ID")

# -------------------------------------------------------
# TAB INTERFACE - More space efficient
# -------------------------------------------------------
tab1, tab2 = st.tabs(["📁 File Upload", "💬 Query Mode"])

with tab1:
    uploaded_file = st.file_uploader("Choose a file", label_visibility="collapsed")
    
    col_check, col_btn = st.columns([3, 1])
    with col_check:
        make_public = st.checkbox("Make file public", False)
    with col_btn:
        upload_btn = st.button("Upload & Send", key="upload_btn", use_container_width=True)

    if upload_btn:
        if not uploaded_file:
            st.error("Please upload a file first.")
        else:
            filename = uploaded_file.name
            key = f"{KEY_PREFIX}/{filename}".strip("/")
            key_encoded = quote(key, safe="/")

            with st.spinner(f"Uploading {filename}..."):
                try:
                    args = {"ContentType": uploaded_file.type or "application/octet-stream"}
                    if make_public:
                        args["ACL"] = "public-read"

                    s3.put_object(
                        Bucket=S3_BUCKET,
                        Key=key,
                        Body=uploaded_file.getvalue(),
                        **args
                    )

                    s3_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key_encoded}"
                    st.success("✅ Upload successful!")
                    
                    with st.expander("📎 S3 URL", expanded=False):
                        st.code(s3_url, language="text")

                    payload = {
                        "s3_url": s3_url,
                        "user_id": user_id,
                        "session_id": session_id
                    }

                    with st.expander("📡 API Payload", expanded=True):
                        st.json(payload)

                    response = requests.post(API_ENDPOINT, json=payload)

                    with st.expander("📝 API Response", expanded=True):
                        try:
                            st.json(response.json())
                        except:
                            st.text(response.text)

                    if response.ok:
                        st.success("✅ API call successful!")
                    else:
                        st.error(f"❌ API returned {response.status_code}")

                except NoCredentialsError:
                    st.error("❌ No AWS credentials found!")
                except ClientError as e:
                    st.error(f"❌ AWS Error: {e}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

with tab2:
    query_input = st.text_area(
        "Enter your query:", 
        placeholder="e.g., how to resolve System Interruption",
        height=150,
        label_visibility="collapsed"
    )

    if st.button("Send Query", key="query_btn", use_container_width=True):
        if not query_input.strip():
            st.error("Please enter a query first.")
        else:
            payload = {
                "user_id": user_id,
                "session_id": session_id,
                "method": "test_kb",
                "query": query_input.strip()
            }

            with st.expander("📡 API Payload", expanded=True):
                st.json(payload)

            try:
                with st.spinner("Sending query..."):
                    response = requests.post(API_ENDPOINT, json=payload)

                with st.expander("📝 API Response", expanded=True):
                    try:
                        st.json(response.json())
                    except:
                        st.text(response.text)

                if response.ok:
                    st.success("✅ Query sent successfully!")
                else:
                    st.error(f"❌ API returned {response.status_code}")

            except Exception as e:
                st.error(f"❌ Error: {e}")