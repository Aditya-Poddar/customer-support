import warnings
warnings.filterwarnings(action="ignore", message=r"datetime\.datetime\.utcnow")
import json
from strands import Agent
from strands.models import BedrockModel
from kb import *

# ============================================================
#         SYSTEM PROMPT FOR FEATURE REQUEST AGENT
# ============================================================
SYSTEM_PROMPT = """
You are a Feature Request Analysis Agent. Your job is to analyze user feature requests
and extract structured information to help product teams prioritize and implement features.

Return ONLY valid JSON. No explanation. No markdown.

Output Schema:
{
  "feature_title": string | null,
  "description": string | null,
  "category": string | null,
  "priority": string | null,
  "requester": {
    "name": string | null,
    "email": string | null,
    "organization": string | null,
    "role": string | null
  },
  "business_value": {
    "impact": string | null,
    "urgency": string | null,
    "affected_users": number | null,
    "revenue_impact": string | null
  },
  "technical_details": {
    "proposed_solution": string | null,
    "affected_components": [string] | null,
    "estimated_complexity": string | null,
    "dependencies": [string] | null
  },
  "use_cases": [
    {
      "scenario": string | null,
      "user_story": string | null,
      "expected_outcome": string | null
    }
  ],
  "acceptance_criteria": [string] | null,
  "related_features": [string] | null,
  "attachments": [
    {
      "type": string | null,
      "description": string | null,
      "url": string | null
    }
  ],
  "status": string | null,
  "tags": [string] | null,
  "notes": string | null
}

Field Guidelines:
- category: "UI/UX", "Backend", "Integration", "Performance", "Security", "Analytics", etc.
- priority: "Critical", "High", "Medium", "Low"
- impact: "High", "Medium", "Low" (business impact)
- urgency: "Immediate", "Short-term", "Long-term"
- estimated_complexity: "Low", "Medium", "High", "Very High"
- status: "New", "Under Review", "Planned", "In Progress", "Completed", "Rejected"

Rules:
1. Return only the JSON object.
2. Use null when a value is missing or cannot be determined.
3. Extract user stories in "As a [role], I want [feature], so that [benefit]" format when possible.
4. Infer priority and complexity based on the request details if not explicitly stated.
5. Categorize the request appropriately based on its nature.
6. Extract any technical requirements or constraints mentioned.
7. Identify related features or dependencies from the context.
8. Do not add any text before or after the JSON.
"""

# ============================================================
#            MAIN ORCHESTRATION FUNCTION
# ============================================================
def call_feature_request_agent(user_query: str, event: dict) -> dict:
    """
    Calls the Feature Request Agent and returns structured JSON.
    
    Args:
        user_query: The feature request text from the user
        event: Event dictionary containing session metadata
        
    Returns:
        Structured JSON with extracted feature request information
    """
    try:
        # Create model
        bedrock_model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        
        # Create agent
        feature_agent = Agent(
            name="Feature Request Analysis Agent",
            model=bedrock_model,
            system_prompt=SYSTEM_PROMPT
        )
        
        # Build prompt
        prompt = (
            "Analyze the following feature request and extract structured information. "
            "Return ONLY JSON as per schema:\n\n" + user_query
        )
        
        # Call the agent
        response = feature_agent(prompt)
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
        
        # Attach metadata
        parsed_json["_meta"] = {
            "session_id": event.get("session_id"),
            "user_id": event.get("user_id"),
            "timestamp": event.get("timestamp"),
            "source": event.get("source", "api")
        }
        
        return parsed_json
        
    except Exception as e:
        return {
            "error": "Exception occurred during feature request analysis",
            "message": str(e),
            "session_id": event.get("session_id"),
            "user_id": event.get("user_id")
        }

