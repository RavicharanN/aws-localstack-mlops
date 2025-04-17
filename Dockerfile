# Use an official lightweight Python image.
FROM python:3.11-slim

# AWS credentials (used here for LocalStack; override in production if needed).
ENV AWS_ACCESS_KEY_ID=test
ENV AWS_SECRET_ACCESS_KEY=test
ENV AWS_DEFAULT_REGION=us-east-1

# LocalStack endpoints and resource configuration.
ENV LOCALSTACK_ENDPOINT_URL=http://host.docker.internal:4566
ENV KINESIS_STREAM_NAME=food11-inference-stream
ENV DYNAMODB_TABLE=InferenceResults

# Set the working directory in the container.
WORKDIR /app

# Copy the requirements file into the container.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code and the model file.
COPY inference_service.py .
COPY food11.pth .
COPY consumer.py .

# Expose port 8000 for Flask.
EXPOSE 8000

# Run the Flask service.
#CMD ["python", "inference_service.py"]
CMD ["bash", "-c", "python inference_service.py & python consumer.py"]
