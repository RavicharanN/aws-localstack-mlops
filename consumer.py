# consumer.py
import os
import json
import time
import logging
import requests
import boto3
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration through environment variables.
KINESIS_ENDPOINT = os.environ.get("KINESIS_ENDPOINT_URL", "http://host.docker.internal:4566")
STREAM_NAME = os.environ.get("KINESIS_STREAM_NAME", "my-kinesis-stream")
SHARD_ID = os.environ.get("KINESIS_SHARD_ID", "shardId-000000000000")

kinesis = boto3.client("kinesis", endpoint_url=KINESIS_ENDPOINT)

def get_shard_iterator():
    response = kinesis.get_shard_iterator(
        StreamName=STREAM_NAME,
        ShardId=SHARD_ID,
        ShardIteratorType="LATEST"  # Alternatively, "TRIM_HORIZON" if you want to read from the beginning.
    )
    return response["ShardIterator"]

def poll_kinesis(shard_iterator):
    while True:
        response = kinesis.get_records(ShardIterator=shard_iterator, Limit=10)
        records = response.get("Records", [])
        for record in records:
            try:
                data_str = record["Data"].decode("utf-8")
                event = json.loads(data_str)
                s3_path = event.get("s3_path")
                if s3_path:
                    logger.info("Received event with s3_path: %s", s3_path)
                    process_event(s3_path)
                else:
                    logger.error("Received event does not contain 's3_path': %s", event)
            except Exception as e:
                logger.error("Error processing record: %s", e)
        shard_iterator = response.get("NextShardIterator")
        time.sleep(1)

def process_event(s3_path):
    url = "http://localhost:8000/infer"  # Assuming the inference service is on the same container.
    payload = {"s3_path": s3_path}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            result = res.json()
            # Add additional metadata.
            result["timestamp"] = datetime.utcnow().isoformat() + "Z"
            logger.info("Inference result: %s", result)
            # TODO: Forward this result to another stream or persistence layer as needed.
        else:
            logger.error("Inference API error: %s", res.text)
    except Exception as e:
        logger.error("Error calling inference API: %s", e)

if __name__ == "__main__":
    iterator = get_shard_iterator()
    poll_kinesis(iterator)
