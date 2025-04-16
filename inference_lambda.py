import os
import io
import json
import base64
import logging
from decimal import Decimal
from datetime import datetime

import boto3
import torch
import numpy as np
from PIL import Image
from torchvision import transforms

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables: S3 endpoint and model location
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "http://129.114.25.165:4566")
MODEL_S3_PATH = os.environ.get("MODEL_S3_PATH", "s3://food11-classifier/food11.pth")  # e.g., "s3://my-models/food11.pth"

# Initialize the S3 client (using S3_ENDPOINT for local testing)
s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT)

def load_model_from_s3(model_s3_path):
    """
    Load the PyTorch model from S3.
    Expected model_s3_path format: 's3://bucket/key'
    """
    if not model_s3_path.startswith("s3://"):
        raise ValueError("MODEL_S3_PATH must be a valid S3 URI")
    # Parse the S3 URI.
    parts = model_s3_path[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1]
    logger.info("Fetching model from bucket %s with key %s", bucket, key)
    response = s3.get_object(Bucket=bucket, Key=key)
    model_bytes = response["Body"].read()
    return torch.load(io.BytesIO(model_bytes), map_location=torch.device("cpu"))

# Load the model once per container (cold start)
try:
    logger.info("Loading model from S3: %s", MODEL_S3_PATH)
    model = load_model_from_s3(MODEL_S3_PATH)
    model.eval()
    logger.info("Model loaded successfully.")
except Exception as e:
    logger.error("Failed to load model: %s", e)
    raise

def preprocess_image(img):
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    return transform(img).unsqueeze(0)

def model_predict(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.error("Error processing image: %s", e)
        raise
    img = preprocess_image(img)
    classes = np.array([
        "Bread", "Dairy product", "Dessert", "Egg", "Fried food",
        "Meat", "Noodles/Pasta", "Rice", "Seafood", "Soup",
        "Vegetable/Fruit"
    ])
    with torch.no_grad():
        output = model(img)
        prob, predicted_class = torch.max(output, 1)
    confidence = float(torch.sigmoid(prob).item())
    return classes[predicted_class.item()], confidence

def lambda_handler(event, context):
    """
    Lambda handler that processes Kinesis events.
    Each record should carry a payload that is a base64-encoded JSON string containing "s3_path".
    """
    logger.info("Received event: %s", json.dumps(event))
    results = []
    
    for record in event.get("Records", []):
        try:
            # Extract and decode the base64 data from the record.
            kinesis_data = record["kinesis"]["data"]
            decoded_data = base64.b64decode(kinesis_data).decode("utf-8")
            data = json.loads(decoded_data)
            s3_path = data.get("s3_path")
            if not s3_path:
                logger.error("Missing s3_path in data: %s", data)
                continue

            # Parse the s3_path assuming format "s3://bucket/key"
            parts = s3_path[5:].split("/", 1)
            bucket, key = parts[0], parts[1]
            logger.info("Fetching image from bucket %s, key %s", bucket, key)
            response = s3.get_object(Bucket=bucket, Key=key)
            image_bytes = response["Body"].read()

            # Run inference.
            predicted_class, confidence = model_predict(image_bytes)
            result = {
                "s3_path": s3_path,
                "predicted_class": predicted_class,
                "confidence": Decimal(str(confidence)),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            results.append(result)
            logger.info("Processed record: %s", result)
        except Exception as e:
            logger.error("Error processing record: %s", e)
    
    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }
