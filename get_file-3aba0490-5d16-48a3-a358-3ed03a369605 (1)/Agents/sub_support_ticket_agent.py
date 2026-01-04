import warnings
warnings.filterwarnings(action="ignore", message=r"datetime\.datetime\.utcnow")
import json
import time
import random
import boto3
from botocore.exceptions import ClientError
from strands import Agent
from strands.models import BedrockModel
from utility import load_config

# ------------------------
# Load Configurations
# ------------------------
config = load_config()
region = config.get("aws_region", "ap-south-1")

kb_params = config.get("kb_generation_parameters", {})
kb_id = kb_params.get("knowledge_base_id")
numberOfResults = kb_params.get("numberOfResults", 5)

# AWS Clients
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=region)

# ============================================================
#              KNOWLEDGE BASE RETRIEVAL
# ============================================================
def retrieve_from_kb(query, max_retries=3):
    """Retrieve documents from Knowledge Base with retry logic."""
    for attempt in range(max_retries):
        try:
            response = bedrock_agent_runtime.retrieve(
                knowledgeBaseId=kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": numberOfResults
                    }
                }
            )
            
            retrieval_results = response.get("retrievalResults", [])
            print(f"[INFO] Retrieved {len(retrieval_results)} documents from KB")
            
            # Format retrieved documents
            context = ""
            sources = []
            for i, doc in enumerate(retrieval_results):
                text = doc.get("content", {}).get("text", "")
                metadata = doc.get("metadata", {})
                score = doc.get("score", 0)
                
                context += f"[Document {i+1}]\n{text}\n\n"
                sources.append({
                    "document_id": i+1,
                    "score": score,
                    "metadata": metadata
                })
            
            return {
                "context": context,
                "sources": sources,
                "count": len(retrieval_results)
            }
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"[WARN] KB throttled. Retrying in {wait:.2f}s")
                time.sleep(wait)
                continue
            
            print(f"[ERROR] KB retrieval failed: {e}")
            return None
            
        except Exception as e:
            print(f"[ERROR] KB exception: {e}")
            return None
    
    return None


# ============================================================
#         SUPPORT TICKET EXTRACTION FROM KB
# ============================================================
SUPPORT_EXTRACTION_PROMPT = """
You are a Support Ticket Data Extraction Agent. Extract structured support ticket information
from the provided Knowledge Base context.

Return ONLY valid JSON. No explanation. No markdown.

Output Schema:
{
  "ticket_id": string | null,
  "customer": {
    "name": string | null,
    "email": string | null,
    "company": string | null,
    "account_id": string | null
  },
  "issue": {
    "category": string | null,
    "priority": string | null,
    "description": string | null,
    "status": string | null
  },
  "resolution": {
    "solution": string | null,
    "resolved_by": string | null,
    "resolution_time": string | null
  },
  "kb_sources": [
    {
      "document_id": number | null,
      "relevance_score": number | null
    }
  ]
}

Context from Knowledge Base:
{context}

User Query: {query}

Extract the relevant support ticket information from the context above.
"""

def extract_support_ticket_from_kb(query: str, event: dict) -> dict:
    """
    Retrieve from KB and extract support ticket information.
    """
    try:
        # Retrieve from KB
        kb_data = retrieve_from_kb(query)
        
        if not kb_data or kb_data["count"] == 0:
            return {
                "error": "No relevant documents found in Knowledge Base",
                "query": query
            }
        
        # Create extraction agent
        bedrock_model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        
        extraction_agent = Agent(
            name="Support Ticket KB Extraction Agent",
            model=bedrock_model,
            system_prompt=SUPPORT_EXTRACTION_PROMPT
        )
        
        # Format prompt with KB context
        prompt = SUPPORT_EXTRACTION_PROMPT.replace("{context}", kb_data["context"]).replace("{query}", query)
        
        # Call agent
        response = extraction_agent(prompt)
        response_str = str(response).strip()
        
        # Extract JSON
        start = response_str.find("{")
        end = response_str.rfind("}")
        
        if start == -1 or end == -1:
            return {
                "error": "No JSON detected in agent output",
                "raw_output": response_str
            }
        
        json_text = response_str[start:end + 1]
        parsed_json = json.loads(json_text)
        
        # Add metadata
        parsed_json["_meta"] = {
            "session_id": event.get("session_id"),
            "user_id": event.get("user_id"),
            "kb_documents_retrieved": kb_data["count"],
            "sources": kb_data["sources"]
        }
        
        return parsed_json
        
    except Exception as e:
        return {
            "error": "Exception during KB extraction",
            "message": str(e)
        }

