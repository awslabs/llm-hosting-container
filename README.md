# LLM Hosting Container

Welcome to the LLM Hosting Container GitHub repository!

This repository contains Dockerfile and associated resources for building and
hosting containers for large language models.

* HuggingFace Text Generation Inference (TGI) container

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the Apache-2.0 License.


## How to build HuggingFace Text Generation Inference (TGI) container for Neuronx

```Bash
# Neuronx TGI is available > 0.0.13
OPTIMUM_NEURON_VERSION=main
VERSION=1.0.2-0.0.13+
docker build --rm -f huggingface/pytorch/tgi/docker/1.0.2/py3/sdk2.15.0/Dockerfile --build-arg OPTIMUM_NEURON_VERSION=${OPTIMUM_NEURON_VERSION} -t neuronx-tgi:${VERSION} .
``````
