# aws-localstack-mlops
Using localstack to demonstrate an ML pipeline built using the services of a commercial clod 

### Setting up localstack

Pull the LocalStack Docker image:

```
docker pull localstack/localstack
```

Run LocalStack as a container
```
docker run --rm -it -p 4566:4566 -p 4571:4571 localstack/localstack
```

### Create an S3 bucket and load the model

Set env vars (ToDO; move to `~/.aws/credentials`)
```
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
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

This doesn't have any effect on the localstack community edition. A policy that allows public readwrite to S3 is defined at `s3_bucket_policy.json`

Create a policy
```
awslocal s3api put-bucket-policy --bucket food11-classifier --policy file://s3_bucket_policy.json
```

Verify if the policy is put in place 
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


