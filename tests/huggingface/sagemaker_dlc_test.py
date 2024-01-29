import logging
import sys
import argparse
import time
import signal
import json
import os
import pytest

from sagemaker.huggingface import HuggingFaceModel


logging.basicConfig(stream=sys.stdout, format="%(message)s", level=logging.INFO)


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError("Test timed out")

def run_test(args):
    default_env = { "HF_MODEL_ID": args.model_id }
    if args.model_revision:
        default_env["HF_MODEL_REVISION"] = args.model_revision
    if args.instance_type.startswith("ml.inf2"):
        default_env["MAX_CONCURRENT_REQUESTS"] = "1"
        default_env["MAX_BATCH_PREFILL_TOKENS"] = "1024"
        default_env["MAX_INPUT_LENGTH"] = "1024"
        default_env["MAX_TOTAL_TOKENS"] = "2048"
        default_env["MAX_BATCH_TOTAL_TOKENS"] = "2048"
    else:
        default_env["SM_NUM_GPUS"] = "4"

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(int(args.timeout))
    predictor = None
    try:
        # Create Hugging Face Model Class
        endpoint_name = args.model_id.replace("/","-").replace(".", "-")[:40]
        endpoint_name = endpoint_name + "-" + time.strftime("%Y-%m-%d-%H-%M-%S", time.gmtime())
        model = HuggingFaceModel(
            name=endpoint_name,
            env=default_env,
            role=args.role,
            image_uri=args.image_uri
        )
        predictor = model.deploy(instance_type=args.instance_type,
                                 initial_instance_count=1,
                                 endpoint_name=endpoint_name,
                                 container_startup_health_check_timeout=1800
        )
        logging.info("Endpoint deployment complete.")

        data = {"inputs": "What is Deep Learning?"}
        output = predictor.predict(data)
        logging.info("Output: " + json.dumps(output))
        assert "generated_text" in output[0]
    finally:
        if predictor:
            predictor.delete_model()
            predictor.delete_endpoint()
        signal.alarm(0)

@pytest.mark.parametrize("model_id, model_revision, instance_type", [
    pytest.param("bigscience/bloom-560m", None, "ml.g5.12xlarge", marks=pytest.mark.gpu),
    pytest.param("EleutherAI/gpt-neox-20b", None, "ml.g5.24xlarge", marks=pytest.mark.gpu),
    pytest.param("google/flan-t5-xxl", None, "ml.g5.24xlarge", marks=pytest.mark.gpu),
    pytest.param("aws-neuron/Mistral-7B-Instruct-v0.1-neuron-1x2048-24-cores", None, "ml.inf2.48xlarge", marks=pytest.mark.inf2),
])
def test(model_id: str, model_revision: str, instance_type: str, timeout: str = "1500"):
    image_uri = os.getenv("IMAGE_URI")
    test_role_arn = os.getenv("TEST_ROLE_ARN")
    assert image_uri, f"Please set IMAGE_URI environment variable."
    assert test_role_arn, f"Please set TEST_ROLE_ARN environment variable."
    args = argparse.Namespace(
        image_uri=image_uri,
        instance_type=instance_type,
        model_id=model_id,
        model_revision=model_revision,
        role=test_role_arn,
        timeout=timeout)

    logging.info(f"Running sanity test with the following args: {args}.")
    run_test(args)


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--image_uri", type=str, required=True)
    arg_parser.add_argument("--instance_type", type=str, required=True)
    arg_parser.add_argument("--model_id", type=str, required=True)
    arg_parser.add_argument("--model_revision", type=str, required=False)
    arg_parser.add_argument("--role", type=str, required=True)
    arg_parser.add_argument("--timeout", type=str, required=True)

    args = arg_parser.parse_args()
    run_test(args)
