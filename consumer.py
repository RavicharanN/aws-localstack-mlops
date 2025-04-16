# consumer.py
import os
import json
import time
import logging
import uuid
import requests
import boto3
from datetime import datetime
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
# Kinesis configuration
KINESIS_ENDPOINT = os.environ.get("KINESIS_ENDPOINT_URL", "http://host.docker.internal:4566")
STREAM_NAME = os.environ.get("KINESIS_STREAM_NAME", "my-kinesis-stream")
SHARD_ID = os.environ.get("KINESIS_SHARD_ID", "shardId-000000000000")

# DynamoDB configuration
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT_URL", "http://host.docker.internal:4566")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "InferenceResults")

# --- Clients Initialization ---
# Kinesis client setup
kinesis = boto3.client("kinesis", endpoint_url=KINESIS_ENDPOINT)

# DynamoDB resource setup
dynamodb = boto3.resource("dynamodb", endpoint_url=DYNAMODB_ENDPOINT)

def create_table_if_not_exists(dynamodb_resource, table_name):
    """
    Create the DynamoDB table if it doesn't exist.
    The table uses "id" as the partition key.
    """
    existing_tables = [table.name for table in dynamodb_resource.tables.all()]
    if table_name not in existing_tables:
        logger.info("Creating DynamoDB table: %s", table_name)
        table = dynamodb_resource.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
        logger.info("DynamoDB table %s created.", table_name)
        return table
    else:
        logger.info("DynamoDB table %s already exists.", table_name)
        return dynamodb_resource.Table(table_name)

# Get or create the table.
table = create_table_if_not_exists(dynamodb, DYNAMODB_TABLE)

def get_shard_iterator():
    """
    Gets a shard iterator to start polling the Kinesis stream.
    """
    response = kinesis.get_shard_iterator(
        StreamName=STREAM_NAME,
        ShardId=SHARD_ID,
        ShardIteratorType="LATEST"  # Use "TRIM_HORIZON" to read from the beginning.
    )
    return response["ShardIterator"]

def write_to_dynamodb(item):
    """
    Writes an item (inference result) to DynamoDB.
    """
    try:
        table.put_item(Item=item)
        logger.info("Wrote item to DynamoDB: %s", item)
    except Exception as e:
        logger.error("Error writing to DynamoDB: %s", e)

def process_event(s3_path):
    """
    Calls the inference API with the provided S3 path, augments the result,
    and writes the enriched event to DynamoDB.
    """
    url = "http://localhost:8000/infer"  # Inference service endpoint.
    payload = {"s3_path": s3_path}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            result = res.json()
            result["confidence"] = Decimal(str(result["confidence"]))
            # Enrich the inference result with timestamp and a unique id.
            result["timestamp"] = datetime.utcnow().isoformat() + "Z"
            result["id"] = str(uuid.uuid4())
            logger.info("Inference result: %s", result)
            write_to_dynamodb(result)
        else:
            logger.error("Inference API error: %s", res.text)
    except Exception as e:
        logger.error("Error calling inference API: %s", e)

def poll_kinesis(shard_iterator):
    """
    Polls the Kinesis stream and processes each event.
    """
    while True:
        response = kinesis.get_records(ShardIterator=shard_iterator, Limit=10)
        records = response.get("Records", [])
        for record in records:
            try:
                # Kinesis records are binary; decode and load them as JSON.
                data_str = record["Data"].decode("utf-8")
                event = json.loads(data_str)
                s3_path = event.get("s3_path")
                if s3_path:
                    logger.info("Received event with s3_path: %s", s3_path)
                    process_event(s3_path)
                else:
                    logger.error("Event missing 's3_path': %s", event)
            except Exception as e:
                logger.error("Error processing record: %s", e)
        shard_iterator = response.get("NextShardIterator")
        time.sleep(1)

if __name__ == "__main__":
    iterator = get_shard_iterator()
    poll_kinesis(iterator)
