import json
from text_extraction import *
from urllib.parse import unquote
from kb import *
from dynamodb import *
from dynamodb_chat_context import *
from Agents.strands_agent import call_instructor_agent


def lambda_handler(event, context):
    """
    Expects:
    {
      "s3_url": "s3://bucket/path/to/file.pdf",
      "user_id": "123",
      "session_id": "abc"
    }
    """
    method = event.get("method")
    query = event.get("query")
    user_id = event.get("user_id")
    session_id = event.get("session_id")
    s3_url = event.get("s3_url")
    

    try:
        if method == "test_kb":
            final_query = f"Query: {query}"
            super_wisor_agent, confidence_score, agent_name_res = call_instructor_agent(final_query, event)

        else:
            if not s3_url:
                return {"statusCode": 400, "body": json.dumps({"message": "Missing s3_url in payload"})}

            clean_s3_url = unquote(s3_url)
            result = process_s3_url(clean_s3_url)
            extracted_text_data = result["extracted_text"]
            final_query = f"Query: {query} and extracted text: {extracted_text_data}"
            super_wisor_agent, confidence_score, agent_name_res = call_instructor_agent(final_query,event)

        if agent_name_res == "invoice_agent":
            store_invoice_data(user_id, session_id, agent_name_res, confidence_score, super_wisor_agent)

        # store the chat context into db
        store_chat_data(user_id, session_id, agent_name_res, confidence_score, super_wisor_agent)

        return {
            "statusCode": 200,
            "user_id": user_id,
            "session_id": session_id,
            "agent_name": agent_name_res,
            "confidence score": confidence_score,
            "child agent res": super_wisor_agent,
            # "extracted_text": result["extracted_text"]
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "error": str(e)
        }
