FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu24.04 AS deps

ARG llamacpp_version=b4651
ARG llamacpp_cuda=OFF
ARG cuda_arch=75-real;80-real;86-real;89-real;90-real

WORKDIR /opt/src

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y \
    clang \
    cmake \
    curl \
    git \
    python3-dev \
    libssl-dev \
    pkg-config \
    tar

ADD https://github.com/ggerganov/llama.cpp/archive/refs/tags/${llamacpp_version}.tar.gz /opt/src/
RUN tar -xzf ${llamacpp_version}.tar.gz \
 && cd llama.cpp-${llamacpp_version} \
 && cmake -B build \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_INSTALL_LIBDIR=/usr/lib \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_CUDA_ARCHITECTURES=${cuda_arch} \
    -DGGML_CUDA=${llamacpp_cuda} \
    -DLLAMA_BUILD_COMMON=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_SERVER=OFF \
 && cmake --build build --parallel --config Release \
 && cmake --install build

WORKDIR /app
COPY rust-toolchain.toml rust-toolchain.toml
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --default-toolchain none
ENV PATH="/root/.cargo/bin:$PATH"
RUN cargo install cargo-chef --locked

FROM deps AS planner
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

FROM deps AS builder
COPY --from=planner /app/recipe.json recipe.json
RUN cargo chef cook \
    --recipe-path recipe.json \
    --profile release-opt \
    --package text-generation-router-llamacpp
COPY . .
RUN cargo build \
    --profile release-opt \
    --package text-generation-router-llamacpp --frozen

FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu24.04 as base

RUN apt update && apt upgrade -y && apt install -y \
    python3-venv \
    python3-pip \
    curl \
    unzip

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY backends/llamacpp/requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY --from=builder /usr/lib/libllama.so /usr/lib/
COPY --from=builder /usr/lib/libggml*.so /usr/lib/
COPY --from=builder /app/target/release-opt/text-generation-router-llamacpp /usr/bin/

ENV HF_HUB_ENABLE_HF_TRANSFER=1


# AWS Sagemaker compatible image
FROM base AS sagemaker

# Create the entrypoint script directly inside the Dockerfile
COPY --chmod=775 /huggingface/pytorch/tgi/docker/backends/llamacpp/commits/cfd4fbb/entrypoint.sh entrypoint.sh

RUN HOME_DIR=/root && \
    pip install requests setuptools && \
    curl -o ${HOME_DIR}/oss_compliance.zip https://aws-dlinfra-utilities.s3.amazonaws.com/oss_compliance.zip && \
    unzip ${HOME_DIR}/oss_compliance.zip -d ${HOME_DIR}/ && \
    cp ${HOME_DIR}/oss_compliance/test/testOSSCompliance /usr/local/bin/testOSSCompliance && \
    chmod +x /usr/local/bin/testOSSCompliance && \
    chmod +x ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh && \
    ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh ${HOME_DIR} python && \
    rm -rf ${HOME_DIR}/oss_compliance*
    
COPY /huggingface/pytorch/tgi/docker/backends/llamacpp/commits/cfd4fbb/THIRD-PARTY-LICENSES /root/THIRD-PARTY-LICENSES

#RUN /opt/conda/bin/conda clean -py

ENTRYPOINT ["./entrypoint.sh"]
CMD ["--json-output"]

LABEL dlc_major_version="2"
LABEL com.amazonaws.ml.engines.sagemaker.dlc.framework.huggingface.tgi="true"
LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port="true"