import warnings
warnings.filterwarnings(action="ignore", message=r"datetime.datetime.utcnow") 
import re
from strands import Agent, tool
from strands.models import BedrockModel
from kb import *
from utility import *
from Agents.sub_feature_request_agent import *
from Agents.sub_general_agent import *
from Agents.sub_invoice_agent import *
from Agents.sub_support_ticket_agent import *


SYSTEM_PROMPT = """
You are an AI orchestrator that analyzes user queries and routes them to the appropriate specialized agent.

AVAILABLE AGENTS:

1. Invoice_Agent
   - Invoice generation, processing, and management
   - Invoice status, payment tracking
   - Billing queries, invoice discrepancies
   - Examples: "Generate invoice for order #123", "Invoice payment status", "Send invoice to client"

2. Feature_Request_Agent
   - New feature suggestions or requests
   - Product enhancement ideas
   - Functionality improvements
   - Examples: "Can we add dark mode?", "I'd like a new reporting feature", "Suggest adding export to Excel"

3. Support_Ticket_Agent
   - Technical issues, bugs, errors
   - System problems, access issues
   - Troubleshooting requests
   - Examples: "I can't log in", "The system is showing an error", "My account is locked"

4. General_Assistant_Agent
   - External organizations (e.g., "Google's policy", "at Tesla")
   - Public figures (e.g., "Rishabh Pant's salary")
   - Industry benchmarks (e.g., "average tech salary")
   - General knowledge, news, weather, current events
   - Best practices and how-to guides

ROUTING LOGIC:

1. INVOICE QUERIES → Invoice_Agent
   - Keywords: invoice, billing, payment status, bill, receipt
   - Intent: generate, send, check, track invoices

2. FEATURE REQUESTS → Feature_Request_Agent
   - Keywords: add, suggest, want, need, can you implement, wish, request feature
   - Intent: suggesting new functionality or improvements
   - Phrases: "it would be nice if", "can we have", "I'd like to see"

3. SUPPORT TICKETS → Support_Ticket_Agent
   - Keywords: error, bug, issue, problem, not working, broken, can't access, locked
   - Intent: reporting technical problems or requesting help
   - Phrases: "I'm unable to", "system is down", "getting an error"

4. EXTERNAL/GENERAL → General_Assistant_Agent
   - Explicit mention of other companies
   - Public figures/celebrities
   - Industry standards or general knowledge
   - Current events, weather, news

DECISION RULES:
- "Invoice" or "billing" = Invoice_Agent
- "Can you add" or "I want feature" = Feature_Request_Agent
- "Error" or "not working" = Support_Ticket_Agent
- When unclear → General_Assistant_Agent

RESPONSE FORMAT:
{
    "identified_agent": "<agent_name>",
    "confidence": <0-1 float>
}
Where:
- `identified_agent` is one of: "Invoice_Agent", "Feature_Request_Agent", "Support_Ticket_Agent", or "General_Assistant_Agent"
- `confidence` is a number between 0 and 1 indicating your confidence in this routing decision

EXAMPLES:

Invoice_Agent:
- "Generate invoice for order #789"
- "Check invoice payment status"
- "Send invoice to client"
- "Invoice #456 is incorrect"

Feature_Request_Agent:
- "Can we add dark mode?"
- "I'd like a bulk upload feature"
- "Suggest adding email notifications"
- "It would be nice to have Excel export"

Support_Ticket_Agent:
- "I can't log in to the system"
- "Getting error 404"
- "My account is locked"
- "Dashboard not loading"
- "System is very slow"

General_Assistant_Agent:
- "What is Google's leave policy?"
- "Rishabh Pant's LSG salary"
- "Average software engineer salary in India"
- "What's the weather today?"
"""


def get_agent_name(response_str: str) -> str:
    """Extract agent name from response string."""
    match = re.search(r'"identified_agent"\s*:\s*"([^"]+)"', response_str)
    if match:
        return match.group(1)
    return "General_Assistant_Agent"  # Default fallback


def extract_agent_and_confidence(response_str: str):
    """
    Extract agent name and confidence score from model JSON response.
    """
    agent_match = re.search(r'"identified_agent"\s*:\s*"([^"]+)"', response_str)
    conf_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', response_str)

    agent_name = agent_match.group(1) if agent_match else "General_Assistant_Agent"
    confidence = float(conf_match.group(1)) if conf_match else 0.50  # default
    
    return agent_name, confidence

def call_instructor_agent(user_query: str, event) -> str:
    """
    Instructor agent to orchestrate user query to appropriate specialized agent.
    """
    try:
        # Create a Bedrock model with guardrail configuration
        bedrock_model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",               
        )
        
        instructor_agent = Agent(
            name="Instructor Agent",
            model=bedrock_model,
            system_prompt=SYSTEM_PROMPT
        )
        
        response = instructor_agent(f"User Query: {user_query}")
        print("Response from instructor agent:", response)
        content = str(response)
        
        # Extract session and user info
        session_id = event.get("session_id")
        user_id = event.get("user_id")
        
        # Route to appropriate agent based on identified agent
        # agent_name = get_agent_name(content.lower())
        # print(f"Identified agent: {agent_name}")

        # Extract routing info
        agent_name, confidence = extract_agent_and_confidence(content)
        agent_name_lower = agent_name.lower()   # convert to lowercase for routing only
        print(f"Identified Agent: {agent_name} | Confidence: {confidence}")
        
        if agent_name_lower == "invoice_agent":
            agent_response = call_invoice_agent(user_query, event)
            final_res = remove_nulls(agent_response) 
        elif agent_name_lower == "feature_request_agent":
            agent_response = call_feature_request_agent(user_query, event)
            final_res = remove_nulls(agent_response) 
        elif agent_name_lower == "support_ticket_agent":
            agent_response = extract_support_ticket_from_kb(user_query, event)
            final_res = remove_nulls(agent_response) 
        else:  
            final_res = {"res": "Human Agent will respond on your query shortly.."}

        

        return final_res, confidence, agent_name_lower

    except Exception as e:
        return f"Error: {e}"