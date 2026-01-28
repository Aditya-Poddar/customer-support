import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import time

dynamodb = boto3.resource("dynamodb")
client = boto3.client("dynamodb")

TABLE_NAME = "customer_segmentation_agent"   # UPDATED TABLE NAME
TTL_DAYS = 30                                 # FIXED 30 DAYS TTL


def ensure_table_exists():
    """Create DynamoDB table with user_id (HASH) + session_id (RANGE) if not exists."""
    try:
        client.describe_table(TableName=TABLE_NAME)
        print(f"Table '{TABLE_NAME}' already exists.")
    except client.exceptions.ResourceNotFoundException:
        print(f"Table '{TABLE_NAME}' does not exist. Creating...")

        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "session_id", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST"
        )

        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        print("Table created successfully!")


def convert_floats_to_decimal(obj):
    """Recursively convert all float values to Decimal for DynamoDB."""
    if isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(v) for v in obj]
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj


# --------------------------------------------------------
# ✅ SAME FUNCTION NAME YOU REQUESTED (DO NOT CHANGE)
# --------------------------------------------------------
def store_chat_data(user_id, session_id, agent_name_res, confidence_score, super_wisor_child_agent_res):

    ensure_table_exists()
    table = dynamodb.Table(TABLE_NAME)

    # Current UTC timestamp
    unix_ts = int(time.time())
    created_at_utc_iso = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()

    # IST timestamp
    ist_offset = timedelta(hours=5, minutes=30)
    created_at_ist = datetime.fromtimestamp(unix_ts, tz=timezone.utc).astimezone(timezone(ist_offset))
    created_at_ist_iso = created_at_ist.isoformat()

    # TTL (Store only as value, NOT enabled on table)
    ttl_epoch = unix_ts + TTL_DAYS * 24 * 3600  # 30 days

    # Item to store
    item = {
        "user_id": user_id,                
        "session_id": session_id,         
        "agent_name": agent_name_res,
        "confidence_score": confidence_score,
        "child_agent": super_wisor_child_agent_res,
        "created_at_utc_iso": created_at_utc_iso,
        "created_at_ist_iso": created_at_ist_iso,

        # TTL attribute (not active unless manually enabled)
        "ttl_epoch": ttl_epoch,

        "message": "File processed and text extracted successfully"
    }

    # Convert floats → Decimal
    item = convert_floats_to_decimal(item)

    # Store in DynamoDB
    table.put_item(Item=item)

    # Return clean JSON response
    return {
        "statusCode": 200,
        "user_id": user_id,
        "session_id": session_id,
        "agent_name": agent_name_res,
        "confidence_score": confidence_score,
        "child_agent": super_wisor_child_agent_res,
        "created_at_utc_iso": created_at_utc_iso,
        "created_at_ist_iso": created_at_ist_iso,
        "ttl_epoch": ttl_epoch
    }
