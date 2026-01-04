import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
import time

dynamodb = boto3.resource("dynamodb")
client = boto3.client("dynamodb")
TABLE_NAME = "invoice_table"


def ensure_table_exists():
    """Create DynamoDB table if not exists."""
    try:
        client.describe_table(TableName=TABLE_NAME)
        print(f"Table '{TABLE_NAME}' already exists.")
    except client.exceptions.ResourceNotFoundException:
        print(f"Table '{TABLE_NAME}' does not exist. Creating...")
        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
            ],
            BillingMode="PAY_PER_REQUEST"
        )
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        print("Table created successfully!")


# Convert any floats inside nested data to Decimal (DynamoDB requirement)
def convert_floats_to_decimal(obj):
    if isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(v) for v in obj]
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj



def store_invoice_data(user_id, session_id, agent_name_res, confidence_score, super_wisor_child_agent_res):

    ensure_table_exists()

    table = dynamodb.Table(TABLE_NAME)

    # Prepare item
    item = {
        "session_id": session_id,
        "user_id": user_id,
        "agent_name": agent_name_res,
        "confidence_score": Decimal(str(confidence_score)),  # convert float → Decimal
        "child_agent": super_wisor_child_agent_res,
        "message": "File processed and text extracted successfully",
        "created_at": int(time.time())
    }

    # Convert nested floats if needed
    item = convert_floats_to_decimal(item)

    # Store in DynamoDB
    table.put_item(Item=item)

    return {
        "statusCode": 200,
        "user_id": user_id,
        "session_id": session_id,
        "agent_name": agent_name_res,
        "confidence_score": confidence_score,
        "child_agent": super_wisor_child_agent_res
    }
