import logging
import sys
import argparse
import time
import signal
import json

from sagemaker.huggingface import HuggingFaceModel


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError("Test timed out")


# Running test
def run_test(args):
    endpoint_name = args.model_id.replace("/","-") + "-" + time.strftime("%Y-%m-%d-%H-%M-%S", time.gmtime())

    hub = {
        'HF_MODEL_ID':args.model_id,
        'HF_TASK':args.task,
        'SM_NUM_GPUS':args.num_gpus
    }

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(int(args.timeout))

    try:
        # Create Hugging Face Model Class
        model = HuggingFaceModel(
            name=endpoint_name,
            env=hub,
            role=args.role,
            image_uri=args.image_uri
        )
        predictor = model.deploy(instance_type=args.instance_type,
                                 initial_instance_count=1,
                                 endpoint_name=endpoint_name)
        logging.info("Endpoint deployment complete.")

        data = {"inputs": "What is Deep Learning?"}
        output = predictor.predict(data)
        logging.info("Output: " + json.dumps(output))
        assert "generated_text" in output[0]
    except TimeoutError:
        logging.error("Test timed out after {} seconds".format(args.timeout))
    finally:
        predictor.delete_model()
        predictor.delete_endpoint()
        signal.alarm(0)


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, format="%(message)s", level=logging.INFO)

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--image_uri", type=str, required=True)
    arg_parser.add_argument("--region", type=str,required=True)
    arg_parser.add_argument("--instance_type", type=str, required=True)
    arg_parser.add_argument("--model_id", type=str, required=True)
    arg_parser.add_argument("--num_gpus", type=str, required=True)
    arg_parser.add_argument("--task", type=str, required=True)
    arg_parser.add_argument("--role", type=str, required=True)
    arg_parser.add_argument("--timeout", type=str, required=True)

    args = arg_parser.parse_args()
    run_test(args)
