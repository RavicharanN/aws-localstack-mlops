import os
import io
import json
import base64
import uuid
import logging
from decimal import Decimal
from datetime import datetime

import boto3
import onnxruntime as ort
import numpy as np
from PIL import Image

# Simple resize/normalize without torchvision
def preprocess_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((224, 224))
    arr = np.array(img).astype(np.float32) / 255.0
    # normalize
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    # HWC to NCHW
    arr = np.transpose(arr, (2,0,1))[None, :]
    return arr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment
S3_ENDPOINT      = os.environ["LOCALSTACK_ENDPOINT_URL"]
MODEL_S3_PATH    = os.environ["MODEL_S3_PATH"]      # e.g. s3://my-models/food11.onnx
DDB_ENDPOINT     = os.environ["LOCALSTACK_ENDPOINT_URL"]
DDB_TABLE        = os.environ["DYNAMODB_TABLE"]

# AWS clients
s3  = boto3.client("s3",      endpoint_url=S3_ENDPOINT)
ddb = boto3.resource("dynamodb", endpoint_url=DDB_ENDPOINT).Table(DDB_TABLE)

# Load model once per cold start
def _load_model():
    bucket, key = MODEL_S3_PATH[5:].split("/",1)
    resp = s3.get_object(Bucket=bucket, Key=key)
    model_bytes = resp["Body"].read()
    # write to /tmp (only writable area in Lambda)
    path = "/tmp/model.onnx"
    with open(path, "wb") as f:
        f.write(model_bytes)
    return ort.InferenceSession(path, providers=["CPUExecutionProvider"])

session = _load_model()
input_name  = session.get_inputs()[0].name
output_name = session.get_outputs()[0].name

CLASSES = [
    "Bread","Dairy product","Dessert","Egg","Fried food",
    "Meat","Noodles/Pasta","Rice","Seafood","Soup",
    "Vegetable/Fruit"
]

def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event))
    for record in event["Records"]:
        # Decode Kinesis base64 payload
        payload = base64.b64decode(record["kinesis"]["data"])
        data    = json.loads(payload)
        s3_path = data["s3_path"]

        # Fetch image
        bucket, key = s3_path[5:].split("/",1)
        img_obj = s3.get_object(Bucket=bucket, Key=key)
        img_bytes = img_obj["Body"].read()

        # Preprocess & infer
        inp = preprocess_image(img_bytes)
        out = session.run([output_name], {input_name: inp})[0]
        probs = np.exp(out) / np.sum(np.exp(out), axis=1, keepdims=True)
        idx   = int(np.argmax(probs, axis=1)[0])
        conf  = float(probs[0, idx])
        cls   = CLASSES[idx]

        # Persist to DynamoDB
        item = {
            "id":              str(uuid.uuid4()),
            "timestamp":       datetime.utcnow().isoformat()+"Z",
            "s3_path":         s3_path,
            "predicted_class": cls,
            "confidence":      Decimal(str(conf))
        }
        ddb.put_item(Item=item)
        logger.info("Wrote to DynamoDB: %s", item)

    return {"statusCode": 200}
