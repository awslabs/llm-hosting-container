FROM ghcr.io/huggingface/text-generation-inference:3.3.6-neuron AS base

# The target image for the automated build has to be called sagemaker
FROM base AS sagemaker

# This is required to properly track hub usage metrics
ENV HF_HUB_USER_AGENT_ORIGIN="aws:sagemaker:neuron:inference:tgi-optimum-neuron"

# Create the entrypoint script.
# This is a modified version of the original TGI neuron entrypoint:
# https://github.com/huggingface/text-generation-inference/blob/79183d164728f080e1a571b7ff1f58bd0ed840b0/backends/neuron/tgi-entrypoint.sh
#
# The reason is that we add the "-- port 8080" to the original entrypoint, and we ignore parameters, because it seems
# that when the container is deployed on Sagemaker, it is invoked with the "serve" that makes the
# text-generation-launcher crash, so the parameters need to be ignored.
#
# We use a 'heredoc' pattern to keep the Dockerfile self-contained
# All content within the 'EOF' marker is written to the entrypoint.sh file
RUN cat <<'EOF' > entrypoint.sh
#!/bin/bash
set -e -o pipefail -u

export ENV_FILEPATH=$(mktemp)

trap "rm -f ${ENV_FILEPATH}" EXIT

touch $ENV_FILEPATH

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

${SCRIPT_DIR}/tgi_entry_point.py

source $ENV_FILEPATH

exec text-generation-launcher --port 8080
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
    <docutils/tools/editors/emacs/rst.el> project's licensing includes the <GPL v3> license." > /root/THIRD_PARTY_LICENSES

LABEL dlc_major_version="1"
LABEL com.amazonaws.ml.engines.sagemaker.dlc.framework.huggingface.tgi="true"
LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port="true"
