# aws-localstack-mlops
Using localstack to demonstrate an ML pipeline built using the services of a commercial clod 

### Setting up localstack

Pull the LocalStack Docker image:

```
docker pull localstack/localstack
```

Run LocalStack as a container
```
docker run --rm -it -p 4566:4566 -p 4571:4571 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --add-host=host.docker.internal:host-gateway \
  -e AWS_ACCESS_KEY_ID=test \
  -e export AWS_SECRET_ACCESS_KEY=test
  localstack/localstack
```

### Create an S3 bucket and load the model

Set env vars (ToDO; move to `~/.aws/credentials`)
```
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
```

```
pip install awscli awscli-local
```

Create a food11classifier bucket and upload the `model.pth` onto the bucket 

```
awslocal s3 mb s3://food11-classifier

awslocal s3 cp food11.pth s3://food11-classifier/food11.pth
```

Check if the model has been successfully uploaded
```
 awslocal s3 ls s3://food11-classifier/
```

### (Optional) Create Dummy policy on S3 

We will create a demo policy that allows public readwrite to S3 is defined at `s3_bucket_policy.json`. This doesn't have any effect on the access when localstack community edition and is just a demonstration of how access is potentially controlled on production. 


Create a policy
```
awslocal s3api put-bucket-policy --bucket food11-classifier --policy file://s3_bucket_policy.json
```

Verify if the policy is in place 
```
awslocal s3api get-bucket-policy --bucket food11-classifier
```

### Upload the testset onto  S3 

Create bucket named `test-images` and upload the testset (used for demo) from the current directory to S3 
```
awslocal s3 mb s3://test-images
awslocal s3 cp test-images/ s3://test-images/ --recursive
```

### Create a Kinesis stream 

We will use a kinesis stream to ingest inference requests onto our pipeline. A lambda will poll from this and run the inference on the incoming reuqwests in the stream. Lets create a single instance of a kinesis stream
```
awslocal kinesis create-stream --stream-name food11-inference-stream --shard-count 1
```
To verify, run: 

```
awslocal kinesis describe-stream --stream-name food11-inference-stream
```

Send a dummy test event to the kinesis stream. The `partition-key = 1` is a simple static partition key that we will use for demo purposes

```
awslocal kinesis put-record --stream-name food11-inference-stream --partition-key "1" --data "s3://test-images/0.jpg"
```

You should see a console output with a `ShardId` and a `SequenceNumber`

## Running Inferenece - EC2

First we spin up an EC2 instance that will run a consumer script that polls the latest events added to the kinesis stream. The inference is offloaded onto our Flask inference server running on port 8000. In the localstack community edition, the EC2 instance works equaivalent to just deploying a docker container. We will run a flask app in a docker container on localhost. 

```
docker build -t inference-service .

sudo docker run --rm -p 8000:8000 \
   --add-host=host.docker.internal:host-gateway \
   inference-service
```
Leave this running in a console. 

Push an event into the kinesis stream to verify if the consumer polls from our stream. If the consumer picks it up you will see an log like this on the docker container
```
INFO:__main__:Inference result: {'confidence': 0.9677120447158813, 'predicted_class': 
'Bread', 's3_path': 's3://test-images/2.jpg', 'timestamp': '2025-04-16T00:02:31.478226Z'}
```

To test the inference server individually run: 

```
curl -X POST "http://localhost:8000/infer" -H "Content-Type: application/json" -d '{"s3_path": "s3://test-images/2.jpg"}'
```

However when the inference requests are sporadic running an EC2 instance might too expensive to always keep running it. 


## Running inference - Lambda (torch deployment)

Having an EC2 instance running all the time when the when there are no continous stream of requests may not always be a very cost friendly idea. So we will setup a lambda that gets triggered everytime theres a new event on the kinesis stream. For this, Make sure the `inference_lambda.py` file is present in your working directory and run:

```
mkdir lambda_trigger_package
cp inference_lambda.py lambda_trigger_package/
pip install -r requirements.txt -t lambda_trigger_package/
cd lambda_trigger_package
zip -r ../trigger_lambda.zip .
cd ..
``` 

Create a lambda function 

```
awslocal lambda create-function \
  --function-name food11-trigger-lambda \
  --runtime python3.11 \
  --handler inference_lambda.lambda_handler \
  --memory-size 128 \
  --timeout 30 \
  --zip-file fileb://trigger_lambda.zip \
  --role arn:aws:iam::000000000000:role/lambda-role
```

**!! This should fail !!**

The reason being lambda are usually supported only for lightweight compute and cannot have heavy dependencies like Pytorch. The lambda deployment should fail with: 

```
An error occurred (RequestEntityTooLargeException) when calling the CreateFunction operation: Zipped size must be smaller than 52428800 bytes
```

## Running inference - Lambda (onnx deployment)

TODO

### Map Lambda to kinesis

Now that we setup our lambda trigger, we need to make it to our kinesis stream. Create an event source mapping from your Kinesis stream (e.g., food11-inference-stream) to trigger this Lambda by running:

```
awslocal lambda create-event-source-mapping \
  --function-name food11-trigger-lambda \
  --batch-size 1 \
  --starting-position LATEST \
  --event-source-arn arn:aws:kinesis:us-east-1:000000000000:stream/food11-inference-stream
```

Now lets push a dummy event to kinesis to see if the trigger is working as expected. First we encode a valid image path on S3 to base64 and publish it as an event to kinesis 

```
echo -n "s3://test-images/your_image.jpg" | base64
```

Copy the result of this base64 to your clipboard then run:

```
awslocal kinesis put-record \
  --stream-name food11-inference-stream \
  --partition-key "1" \
  --data "czM6Ly90ZXN0LWltYWdlcy95b3VyX2ltYWdlLmpwZw=="
```

The docker logs should show if the lambda trigger is working as expected when an event is pushed into the stream:

```
2025-04-09T16:35:40.946  INFO --- [et.reactor-0] localstack.request.aws     : AWS kinesis.PutRecord => 200
2025-04-09T16:36:20.866  INFO --- [et.reactor-0] localstack.request.http    : POST /_localstack_lambda/f0551557c97966a9bf4b5f1b62b29653/status/f0551557c97966a9bf4b5f1b62b29653/ready => 202
2025-04-09T16:36:20.877  INFO --- [et.reactor-2] localstack.request.http    : POST /_localstack_lambda/f0551557c97966a9bf4b5f1b62b29653/invocations/20d3ddc4-4dd4-434c-9b6c-9494a26a5dd8/logs => 202
2025-04-09T16:36:20.879  INFO --- [et.reactor-0] localstack.request.http    : POST /_localstack_lambda/f0551557c97966a9bf4b5f1b62b29653/invocations/20d3ddc4-4dd4-434c-9b6c-9494a26a5dd8/response => 202
```
