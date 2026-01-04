import warnings
warnings.filterwarnings(action="ignore", message=r"datetime\.datetime\.utcnow")

import json
from strands import Agent
from strands.models import BedrockModel
from kb import *


# ============================================================
#              SYSTEM PROMPT FOR INVOICE AGENT
# ============================================================

SYSTEM_PROMPT = """
You are an Invoice Extraction Agent. Your job is to read the user's provided invoice text
or OCR result and return a JSON object containing the extracted invoice fields.

Return ONLY valid JSON. No explanation. No markdown.

Output Schema:
{
  "invoice_number": string | null,
  "invoice_date": string | null,
  "supplier": {
    "name": string | null,
    "address": string | null,
    "gstin": string | null
  },
  "buyer": {
    "name": string | null,
    "address": string | null,
    "gstin": string | null
  },
  "items": [
    {
      "description": string | null,
      "quantity": number | null,
      "unit_price": number | null,
      "total": number | null
    }
  ],
  "subtotal": number | null,
  "tax": {
    "taxable_amount": number | null,
    "tax_amount": number | null,
    "tax_breakdown": [
      {
        "tax_type": string | null,
        "rate_percent": number | null,
        "amount": number | null
      }
    ]
  },
  "total": number | null,
  "currency": string | null,
  "notes": string | null
}

Rules:
1. Return only the JSON object.
2. Use null when a value is missing.
3. For numbers, return numeric values (float) if possible.
4. For dates, return ISO format (YYYY-MM-DD) when detectable.
5. Do not add any text before or after the JSON.
"""


# ============================================================
#            MAIN ORCHESTRATION FUNCTION (CLEAN)
# ============================================================

def call_invoice_agent(user_query: str, event: dict) -> dict:
    """
    Calls the Invoice Agent and returns structured JSON.
    """

    try:
        # Create model
        bedrock_model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )

        # Create agent
        invoice_agent = Agent(
            name="Invoice Extraction Agent",
            model=bedrock_model,
            system_prompt=SYSTEM_PROMPT
        )

        # Build prompt
        prompt = (
            "Extract invoice information from the following text. "
            "Return ONLY JSON as per schema:\n\n" + user_query
        )

        # Call the agent
        response = invoice_agent(prompt)
        response_str = str(response).strip()

        # --------------------------------------------------
        # Extract JSON from model output
        # --------------------------------------------------
        start = response_str.find("{")
        end = response_str.rfind("}")

        if start == -1 or end == -1:
            return {
                "error": "No JSON detected in model output",
                "raw_output": response_str
            }

        json_text = response_str[start:end + 1]

        # --------------------------------------------------
        # Parse JSON safely
        # --------------------------------------------------
        try:
            parsed_json = json.loads(json_text)
        except json.JSONDecodeError as e:
            return {
                "error": "JSON parsing failed",
                "message": str(e),
                "json_text": json_text
            }

        # Attach metadata if provided
        parsed_json["_meta"] = {
            "session_id": event.get("session_id"),
            "user_id": event.get("user_id")
        }

        return parsed_json

    except Exception as e:
        return {
            "error": "Exception occurred during invoice extraction",
            "message": str(e)
        }
