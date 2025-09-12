FROM ghcr.io/huggingface/text-generation-inference:3.3.4-neuron AS base

# The target image for the automated build has to be called sagemaker
FROM base AS sagemaker

# This is required to properly track hub usage metrics
ENV HF_HUB_USER_AGENT_ORIGIN="aws:sagemaker:neuron:inference:tgi-optimum-neuron"

# Create the entrypoint script
# We use a 'heredoc' pattern to keep the Dockerfile self-contained
# All content within the 'EOF' marker is written to the entrypoint.sh file
RUN cat <<'EOF' > entrypoint.sh
#!/bin/bash

if [[ -z "${HF_MODEL_ID}" ]]; then
  echo "HF_MODEL_ID must be set"
  exit 1
fi
export MODEL_ID="${HF_MODEL_ID}"

if [[ -n "${HF_MODEL_REVISION}" ]]; then
  export REVISION="${HF_MODEL_REVISION}"
fi

if [[ -z "${MAX_BATCH_SIZE}" ]]; then
  echo "MAX_BATCH_SIZE must be set to the model static batch size"
  exit 1
fi

text-generation-launcher --port 8080
EOF
# Make the generated entrypoint script executable
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]

RUN apt-get update \
    && apt-get upgrade -y linux-libc-dev \
    && apt-get install -y --no-install-recommends curl unzip libsqlite3-0 libxml2 \
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
