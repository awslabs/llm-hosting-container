FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu24.04 AS deps

ARG llamacpp_version=b4827
ARG llamacpp_cuda=ON
ARG llamacpp_native=ON
ARG llamacpp_cpu_arm_arch=native
ARG cuda_arch=75-real;80-real;86-real;89-real;90-real

WORKDIR /opt/src

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt upgrade -y && apt install -y \
    clang \
    cmake \
    curl \
    git \
    python3-dev \
    unzip \
    libssl-dev \
    pkg-config \
    tar

ADD https://github.com/ggml-org/llama.cpp/archive/refs/tags/${llamacpp_version}.tar.gz /opt/src/
RUN mkdir -p llama.cpp \
 && tar -xzf ${llamacpp_version}.tar.gz -C llama.cpp --strip-components=1 \
 && cd llama.cpp \
 && cmake -B build \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_INSTALL_LIBDIR=/usr/lib \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_CUDA_ARCHITECTURES=${cuda_arch} \
    -DGGML_CUDA=${llamacpp_cuda} \
    -DGGML_NATIVE=${llamacpp_native} \
    -DGGML_CPU_ARM_ARCH=${llamacpp_cpu_arm_arch} \
    -DLLAMA_BUILD_COMMON=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_SERVER=OFF \
 && cmake --build build --parallel --config Release \
 && cmake --install build

WORKDIR /app
COPY rust-toolchain.toml rust-toolchain.toml
RUN curl -sSf https://sh.rustup.rs | sh -s -- --no-modify-path --default-toolchain 1.85.1 --profile minimal -y
ENV PATH="/root/.cargo/bin:$PATH"
RUN cargo install cargo-chef --locked

FROM deps AS planner
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

FROM deps AS builder
COPY --from=planner /app/recipe.json recipe.json
RUN cargo chef cook \
    --recipe-path recipe.json \
    --profile release \
    --package text-generation-router-llamacpp
COPY . .
RUN cargo build \
    --profile release \
    --package text-generation-router-llamacpp --frozen

FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu24.04
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt upgrade -y && apt install -y \
    python3-venv \
    python3-pip

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY backends/llamacpp/requirements.txt requirements.txt
COPY --from=builder /opt/src/llama.cpp/gguf-py gguf-py
COPY --from=builder /opt/src/llama.cpp/convert_hf_to_gguf.py /bin/

RUN pip3 install --no-cache-dir \
    -r requirements.txt \
    -e gguf-py

COPY --from=builder /usr/lib/libllama.so /usr/lib/
COPY --from=builder /usr/lib/libggml*.so /usr/lib/
COPY --from=builder /app/target/release/text-generation-router-llamacpp /usr/bin/

ENV HF_HUB_ENABLE_HF_TRANSFER=1

FROM deps AS sagemaker

RUN HOME_DIR=/root && \
    pip3 requests PTable && \
    curl -o ${HOME_DIR}/oss_compliance.zip https://aws-dlinfra-utilities.s3.amazonaws.com/oss_compliance.zip && \
    unzip ${HOME_DIR}/oss_compliance.zip -d ${HOME_DIR}/ && \
    cp ${HOME_DIR}/oss_compliance/test/testOSSCompliance /usr/local/bin/testOSSCompliance && \
    chmod +x /usr/local/bin/testOSSCompliance && \
    chmod +x ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh && \
    ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh ${HOME_DIR} python && \
    rm -rf ${HOME_DIR}/oss_compliance*

    ENV LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/root/.local/share/uv/python/cpython-3.11.11-linux-x86_64-gnu/lib/"
    ENV HF_HUB_USER_AGENT_ORIGIN=aws:sagemaker:gpu-cuda:inference:tgi-llamacpp

COPY /huggingface/pytorch/tgillamacpp/docker/3.2.3/THIRD-PARTY-LICENSES /root/THIRD-PARTY-LICENSES
COPY /huggingface/pytorch/tgillamacpp/docker/3.2.3/gpu/start-cuda-compat.sh /root/start-cuda-compat.sh
RUN chmod +x /root/start-cuda-compat.sh

COPY /huggingface/pytorch/tgillamacpp/docker/3.2.3/gpu/entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh 

ENTRYPOINT ["./entrypoint.sh"]
CMD ["--json-output"]

LABEL dlc_major_version="2"
LABEL com.amazonaws.ml.engines.sagemaker.dlc.framework.huggingface.tgi="true"
LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port="true"