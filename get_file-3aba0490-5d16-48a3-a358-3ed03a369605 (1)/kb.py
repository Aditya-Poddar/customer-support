import time
import random
import boto3
import json
from botocore.exceptions import ClientError
from utility import load_config
from concurrent.futures import ThreadPoolExecutor


# ------------------------
# Load Configurations
# ------------------------
config = load_config()
region = config.get("aws_region", "ap-south-1")

# Knowledge Base Config
kb_params = config.get("kb_generation_parameters", {})
kb_id = kb_params.get("knowledge_base_id")
model_arn = kb_params.get("model_arn")
numberOfResults = kb_params.get("numberOfResults")

# Claude Model Parameters
claude_temperature = kb_params.get("temperature")
claude_top_p = kb_params.get("top_p")
claude_top_k = kb_params.get("top_k")
claude_max_tokens = kb_params.get("max_tokens")

# DynamoDB Config
dynamodb_table_name = config.get("dynamodb_table_name")

# AWS Clients
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=region)
bedrock_runtime = boto3.client("bedrock-runtime", region_name=region)

# -----------------------------------------------------
# STEP 1: Retrieve documents
# -----------------------------------------------------
def retrieve_documents(query, max_retries=3):
    """Retrieve documents only (no generation)."""
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
            print("==== DEBUG: Retrieve Response ====")
            print(f"Found {len(retrieval_results)} documents\n")
            return retrieval_results

        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"[WARN] Retrieve throttled. Retrying in {wait:.2f}s")
                time.sleep(wait)
                continue

            print(f"[ERROR] Retrieve failed: {e}")
            return []

        except Exception as e:
            print(f"[ERROR] Retrieve exception: {e}")
            return []

    return []


# -----------------------------------------------------
# STEP 2: Generate with Claude Sonnet
# -----------------------------------------------------
def generate_with_model(query, retrieved_docs, prompt_template, max_retries=3):
    """Generate using Claude Sonnet with retrieved KB docs."""

    # Build context
    context = ""
    for i, doc in enumerate(retrieved_docs):
        text = doc.get("content", {}).get("text", "")
        context += f"[Document {i+1}]\n{text}\n\n"

    # Insert context + question into final prompt
    final_prompt = prompt_template.replace("{context}", context).replace("{question}", query)

    print("==== DEBUG: Final Prompt Info ====")
    print(f"Final prompt length: {len(final_prompt)} characters")
    print(f"Chunks included: {len(retrieved_docs)}")

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": claude_max_tokens,
        "temperature": claude_temperature,
        "top_p": claude_top_p,
        "top_k": claude_top_k,
        "messages": [
            {"role": "user", "content": final_prompt}
        ]
    }

    model_id = model_arn.split("/")[-1]

    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body)
            )

            body = json.loads(response["body"].read())
            output_text = body["content"][0]["text"]
            usage = body.get("usage", {})

            print("==== DEBUG: Generation Complete ====")
            print(f"Output length: {len(output_text)} chars")
            print(f"Tokens Used → Input: {usage.get('input_tokens', 0)}, Output: {usage.get('output_tokens', 0)}")

            return {
                "text": output_text,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            }

        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"[WARN] Model throttled. Retrying in {wait:.2f}s")
                time.sleep(wait)
                continue

            print(f"[ERROR] Model invocation failed: {e}")
            raise

        except Exception as e:
            print(f"[ERROR] Unexpected model error: {e}")
            raise

    raise Exception("Max retries reached in generate_with_model()")


# -----------------------------------------------------
# STEP 3: Retrieve → Generate
# -----------------------------------------------------
def retrieve_and_generate(query):
    try:
        retrieved_docs = retrieve_documents(query)

        if not retrieved_docs:
            return {
                "statusCode": 404,
                "response": "No relevant documents found."
            }

        # Build prompt template
        # prompt_template = f"""
        # ```
        # You are a professional customer support agent. Your task is to respond to customer support tickets in a clear, helpful, and well-structured format. 

        # For each support ticket response, follow these guidelines:

        # **STRUCTURE:**
        # 1. **Acknowledgment**: Thank the customer and acknowledge their specific issue
        # 2. **Understanding**: Show you understand the impact/urgency of their problem
        # 3. **Action Items**: Clearly list what you need from them or what you'll do next
        # 4. **Timeline**: Provide realistic expectations when possible
        # 5. **Next Steps**: Clear instructions on what happens next
        # 6. **Professional Closing**: Offer additional support and contact information

        # **TONE AND STYLE:**
        # - Use clear, professional language
        # - Avoid technical jargon unless necessary
        # - Be empathetic and understanding
        # - Use bullet points or numbered lists for clarity
        # - Keep paragraphs short and scannable
        # - Use proper formatting with line breaks

        # **RESPONSE FORMAT:**
        # - Start with a personalized greeting
        # - Use clear section headers when appropriate
        # - Include specific action items in bullet points
        # - End with a professional signature line

        # **EXAMPLE STRUCTURE:**

        # Dear [Customer Name],

        # Thank you for contacting us regarding [specific issue]. I understand this [type of impact] is affecting your [business operations/daily activities], and I'm here to help resolve this as quickly as possible.

        # **What I need from you:**
        # • [Specific information request 1]
        # • [Specific information request 2]
        # • [Specific information request 3]

        # **What we're doing:**
        # • [Action being taken 1]
        # • [Action being taken 2]

        # **Next Steps:**
        # [Clear timeline and expectations]

        # Please don't hesitate to reach out if you have any questions or need immediate assistance at [contact information].

        # Best regards,
        # [Support Team Name]

        # Now, rewrite the following support ticket response to make it more readable and professional:

        # [INSERT ORIGINAL RESPONSE HERE]
        # ```
        # ## Context Information
        # {retrieved_docs}

        # ## User Question
        # {query}

        # This prompt will help generate support responses that are:
        # - More visually organized
        # - Easier to scan and read
        # - More actionable for customers
        # - Professional and empathetic
        # - Clear about next steps and expectations
        # """

        prompt_template = f"""
        You are a professional customer support agent. Respond to support tickets with precision, clarity, and actionable information.

        ## CORE PRINCIPLES:
        - Be concise and direct - respect the customer's time
        - Provide specific, actionable solutions
        - Include only relevant information from context
        - Use clear formatting for scannability

        ## RESPONSE STRUCTURE:

        **Greeting & Acknowledgment** (1-2 sentences)
        Acknowledge the specific issue without unnecessary pleasantries.

        **Solution/Action** (Primary focus)
        - State the direct answer or solution first
        - Provide step-by-step instructions if needed
        - Include relevant details from context documentation
        - Specify what you need from the customer (if anything)

        **Timeline** (When applicable)
        Provide realistic timeframes for resolution or next steps.

        **Closing** (1 sentence)
        Offer further assistance if needed.

        ## FORMATTING RULES:
        - Use bullet points for multiple items or steps
        - Bold important information (account numbers, deadlines, key actions)
        - Keep paragraphs to 2-3 sentences max
        - No fluff or filler content

        ## QUALITY CHECKS:
        ✓ Does this answer the customer's question directly?
        ✓ Is every sentence necessary and valuable?
        ✓ Can the customer take action based on this response?
        ✓ Have I referenced relevant context documentation?

        ---

        ## Context Information:
        {retrieved_docs}

        ## Customer Question:
        {query}

        Generate a response that prioritizes accuracy and usefulness over length.
        """

        with ThreadPoolExecutor(max_workers=1) as executor:
            future_answer = executor.submit(
                generate_with_model, query, retrieved_docs, prompt_template
            )
            answer_output = future_answer.result()

        return {
            "statusCode": 200,
            "response": answer_output["text"]
        }

    except Exception as e:
        return {
            "statusCode": 400,
            "response": f"Error: {str(e)}"
        }
