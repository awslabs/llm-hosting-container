# Fetch and extract the TGI sources
FROM alpine AS tgi
RUN mkdir -p /tgi
ADD https://github.com/huggingface/text-generation-inference/archive/refs/tags/v1.4.1.tar.gz /tgi/sources.tar.gz
RUN tar -C /tgi -xf /tgi/sources.tar.gz --strip-components=1

# Build cargo components (adapted from TGI original Dockerfile)
# Note that the build image is aligned on the same Linux version as the base image (Debian bookworm/ Ubuntu 22.04)
FROM lukemathwalker/cargo-chef:latest-rust-1.75-bookworm AS chef
WORKDIR /usr/src

ARG CARGO_REGISTRIES_CRATES_IO_PROTOCOL=sparse

FROM chef as planner
COPY --from=tgi /tgi/Cargo.toml Cargo.toml
COPY --from=tgi /tgi/Cargo.lock Cargo.lock
COPY --from=tgi /tgi/rust-toolchain.toml rust-toolchain.toml
COPY --from=tgi /tgi/proto proto
COPY --from=tgi /tgi/benchmark benchmark
COPY --from=tgi /tgi/router router
COPY --from=tgi /tgi/launcher launcher
RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS builder

RUN PROTOC_ZIP=protoc-21.12-linux-x86_64.zip && \
    curl -OL https://github.com/protocolbuffers/protobuf/releases/download/v21.12/$PROTOC_ZIP && \
    unzip -o $PROTOC_ZIP -d /usr/local bin/protoc && \
    unzip -o $PROTOC_ZIP -d /usr/local 'include/*' && \
    rm -f $PROTOC_ZIP

COPY --from=planner /usr/src/recipe.json recipe.json
RUN cargo chef cook --release --recipe-path recipe.json

COPY --from=tgi /tgi/Cargo.toml Cargo.toml
COPY --from=tgi /tgi/Cargo.lock Cargo.lock
COPY --from=tgi /tgi/rust-toolchain.toml rust-toolchain.toml
COPY --from=tgi /tgi/proto proto
COPY --from=tgi /tgi/benchmark benchmark
COPY --from=tgi /tgi/router router
COPY --from=tgi /tgi/launcher launcher
RUN cargo build --release --workspace --exclude benchmark

# Fetch optimum-neuron sources
FROM alpine/git AS optimum-neuron
RUN git clone --depth 1 --branch v0.0.21 https://github.com/huggingface/optimum-neuron.git /optimum-neuron

# Python base image
FROM ubuntu:22.04 AS base

RUN apt-get update -y \
 && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-setuptools \
    python-is-python3 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean
RUN pip3 --no-cache-dir install --upgrade pip

# Python server build image
FROM base AS pyserver

RUN apt-get update -y \
 && apt-get install -y --no-install-recommends \
    make \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN install -d /pyserver
WORKDIR /pyserver
COPY --from=optimum-neuron /optimum-neuron/text-generation-inference/server server
COPY --from=tgi /tgi/proto proto
RUN pip3 install -r server/build-requirements.txt
RUN VERBOSE=1 BUILDDIR=/pyserver/build PROTODIR=/pyserver/proto make -C server gen-server

# Neuron base image (used for deployment)
FROM base AS neuron

# Install system prerequisites
RUN apt-get update -y \
 && apt-get install -y --no-install-recommends \
    gnupg2 \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN echo "deb https://apt.repos.neuron.amazonaws.com jammy main" > /etc/apt/sources.list.d/neuron.list
RUN wget -qO - https://apt.repos.neuron.amazonaws.com/GPG-PUB-KEY-AMAZON-AWS-NEURON.PUB | apt-key add -

# Install neuronx packages
RUN apt-get update -y \
 && apt-get install -y --no-install-recommends \
    aws-neuronx-dkms=2.16.7.0 \
    aws-neuronx-collectives=2.20.22.0-c101c322e \
    aws-neuronx-runtime-lib=2.20.22.0-1b3ca6425 \
    aws-neuronx-tools=2.17.1.0 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

ENV PATH="/opt/bin/:/opt/aws/neuron/bin:${PATH}"

RUN pip3 install \
    neuronx-cc==2.13.66.0 \
    torch-neuronx==1.13.1.1.14.0 \
    transformers-neuronx==0.10.0.21 \
    --extra-index-url=https://pip.repos.neuron.amazonaws.com

# Install HuggingFace packages
RUN pip3 install \
    hf_transfer

# Install optimum-neuron
COPY --from=optimum-neuron /optimum-neuron optimum-neuron
RUN pip3 install ./optimum-neuron

# TGI base env
ENV HUGGINGFACE_HUB_CACHE=/tmp \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    PORT=80

# Install router
COPY --from=builder /usr/src/target/release/text-generation-router /usr/local/bin/text-generation-router
# Install launcher
COPY --from=builder /usr/src/target/release/text-generation-launcher /usr/local/bin/text-generation-launcher
# Install python server
COPY --from=pyserver /pyserver/build/dist dist
RUN pip install dist/text-generation-server*.tar.gz

# AWS Sagemaker compatible image
FROM neuron as sagemaker

COPY --from=optimum-neuron /optimum-neuron/text-generation-inference/sagemaker-entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]


RUN apt-get update && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*
RUN HOME_DIR=/root && \
    pip install requests && \
    curl -o ${HOME_DIR}/oss_compliance.zip https://aws-dlinfra-utilities.s3.amazonaws.com/oss_compliance.zip && \
    unzip ${HOME_DIR}/oss_compliance.zip -d ${HOME_DIR}/ && \
    cp ${HOME_DIR}/oss_compliance/test/testOSSCompliance /usr/local/bin/testOSSCompliance && \
    chmod +x /usr/local/bin/testOSSCompliance && \
    chmod +x ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh && \
    ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh ${HOME_DIR} python && \
    rm -rf ${HOME_DIR}/oss_compliance*

RUN echo "N.B.: Although this image is released under the Apache-2.0 License, the Dockerfile used to build the image \
has an indirect documentation dependency on third party <docutils/tools/editors/emacs/rst.el> project. The \
<docutils/tools/editors/emacs/rst.el> project's licensing includes the <GPL v3> license. \
\n\n\
N.B.: Although this image is released under the Apache-2.0 License, the Dockerfile used to build the image uses the \
third party <Text Generation Inference (TGI)> project. The <Text Generation Inference (TGI)> project's licensing \
includes the <HFOIL --> https://github.com/huggingface/text-generation-inference/blob/main/LICENSE> \
license." > /root/THIRD_PARTY_LICENSES

LABEL dlc_major_version="1"
LABEL com.amazonaws.ml.engines.sagemaker.dlc.framework.huggingface.tgi="true"
LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port="true"
