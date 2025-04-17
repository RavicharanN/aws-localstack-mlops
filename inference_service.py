# inference_service.py
import os, io, json, logging
import boto3, torch, numpy as np
from flask import Flask, request, jsonify
from PIL import Image
from torchvision import transforms

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Use an environment variable to point to your S3 endpoint.
s3_endpoint = os.environ.get("LOCALSTACK_ENDPOINT_URL", "http://host.docker.internal:4566")
logger.info("Using S3 endpoint: %s", s3_endpoint)
s3 = boto3.client("s3", endpoint_url=s3_endpoint)

# Load your model.
try:
    logger.info("Loading model from food11.pth")
    model = torch.load("food11.pth", map_location=torch.device("cpu"))
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
                             std=[0.229, 0.224, 0.225]),
    ])
    return transform(img).unsqueeze(0)

def model_predict(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.error("Error opening image: %s", e)
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
    return classes[predicted_class.item()], float(torch.sigmoid(prob).item())

@app.route('/infer', methods=['POST'])
def infer():
    data = request.get_json()
    if not data or 's3_path' not in data:
        logger.error("Missing 's3_path' in request")
        return jsonify({"error": "Missing 's3_path' in request"}), 400

    s3_path = data['s3_path']
    if not s3_path.startswith("s3://"):
        logger.error("Invalid s3_path format: %s", s3_path)
        return jsonify({"error": "Invalid s3_path format"}), 400

    # Parse the S3 URI into bucket and key.
    parts = s3_path[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else None
    if not key:
        logger.error("Missing key in s3_path: %s", s3_path)
        return jsonify({"error": "Missing key in s3_path"}), 400

    try:
        logger.info("Retrieving S3 object. Key: %s", key)
        response = s3.get_object(Bucket=bucket, Key=key)
        image_bytes = response["Body"].read()
    except Exception as e:
        logger.error("Failed to retrieve image from S3: %s", e)
        return jsonify({"error": f"Failed to retrieve image from S3: {str(e)}"}), 500

    try:
        predicted_class, confidence = model_predict(image_bytes)
    except Exception as e:
        logger.error("Error during model prediction: %s", e)
        return jsonify({"error": f"Model prediction failed: {str(e)}"}), 500

    logger.info("Inference successful for %s: %s (confidence %f)", s3_path, predicted_class, confidence)
    return jsonify({
        "s3_path": s3_path,
        "predicted_class": predicted_class,
        "confidence": confidence
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)

