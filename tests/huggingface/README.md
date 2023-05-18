# SageMaker DLC Test

This folder is a collection of scripts that enables users to test and validate
the Deep Learning Containers (DLC) on SageMaker.

## Requirements

- An AWS account
- SageMaker Python SDK installed

## Usage

Run the test script using the command below:

```
pip3 install -r requirements.txt

IMAGE_URI=<YOUR_IMAGE_URI>
REGION=us-east-1
INSTANCE_TYPE=ml.g5.12xlarge
NUM_GPUS=4
ROLE=<YOUR_ROLE>

python3 sagemaker_dlc_test.py --image_uri $IMAGE_URI --region $REGION --instance_type $INSTANCE_TYPE --model_id bigscience/bloom-560m --num_gpus $NUM_GPUS --task text-generation --role $ROLE --timeout 600
python3 sagemaker_dlc_test.py --image_uri $IMAGE_URI --region $REGION --instance_type $INSTANCE_TYPE --model_id EleutherAI/gpt-neox-20b --num_gpus $NUM_GPUS --task text-generation --role $ROLE --timeout 2000
python3 sagemaker_dlc_test.py --image_uri $IMAGE_URI --region $REGION --instance_type $INSTANCE_TYPE --model_id google/flan-t5-xxl --num_gpus $NUM_GPUS --task text2text-generation --role $ROLE --timeout 3000
```

The tests will deploy a SageMaker endpoint and run inference.
