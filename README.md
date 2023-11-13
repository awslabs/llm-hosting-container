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
git clone -b main --single-branch https://github.com/huggingface/optimum-neuron.git
cd optimum-neuron
pip install build
export VERSION=$(python -W ignore -c "from optimum.neuron.version import __version__; print(__version__)")
make dist/optimum-neuron-${VERSION}.tar.gz dist/optimum_neuron-${VERSION}-py3-none-any.whl
cd ..
cp -r optimum-neuron/dist/ dist/
docker build --rm -f huggingface/pytorch/tgi/docker/1.0.2/py3/sdk2.15.0/Dockerfile --build-arg VERSION=${VERSION} -t neuronx-tgi:${VERSION} .
``````