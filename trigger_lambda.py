import json
import base64
import requests
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Replace the  the below line with your hosts IP
INFERENCE_SERVICE_URL = "http://192.168.1.10:8000/infer"

def lambda_handler(event, context):
    results = []
    
    for record in event.get("Records", []):
        try:
            data = base64.b64decode(record["kinesis"]["data"]).decode("utf-8")
            logger.info("Received record data: %s", data)
            try:
                response = requests.post(INFERENCE_SERVICE_URL, json={"s3_path": data})
                logger.info("Inference response: %s", response.text)
                results.append({"result": response.text})
            except Exception as e:
                logger.error("Error calling inference service: %s", e)
                results.append({"error": str(e)})
        except Exception as ex:
            logger.error("Error processing record: %s", ex)
            results.append({"error": str(ex)})
    
    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }
