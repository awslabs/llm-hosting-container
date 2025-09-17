FROM ghcr.io/huggingface/text-generation-inference:3.3.6-neuron AS base

# The target image for the automated build has to be called sagemaker
FROM base AS sagemaker

# This is required to properly track hub usage metrics
ENV HF_HUB_USER_AGENT_ORIGIN="aws:sagemaker:neuron:inference:tgi-optimum-neuron"

# Launch original TGI neuron entrypoint, but with port 8080
ENTRYPOINT ["./tgi-entrypoint.sh", "--port", "8080"]

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
    <docutils/tools/editors/emacs/rst.el> project's licensing includes the <GPL v3> license." > /root/THIRD_PARTY_LICENSES

LABEL dlc_major_version="1"
LABEL com.amazonaws.ml.engines.sagemaker.dlc.framework.huggingface.tgi="true"
LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port="true"
