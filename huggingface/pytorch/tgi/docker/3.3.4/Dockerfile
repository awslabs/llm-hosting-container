# Rust builder
FROM ghcr.io/huggingface/text-generation-inference:3.3.4 AS base

FROM base AS sagemaker

COPY /huggingface/pytorch/tgi/docker/3.3.4/start-cuda-compat.sh start-cuda-compat.sh
RUN chmod +x start-cuda-compat.sh

RUN apt-get update && apt-get upgrade -y unzip

RUN HOME_DIR=/root && \
    uv pip install pip requests PTable && \
    curl -o ${HOME_DIR}/oss_compliance.zip https://aws-dlinfra-utilities.s3.amazonaws.com/oss_compliance.zip && \
    unzip ${HOME_DIR}/oss_compliance.zip -d ${HOME_DIR}/ && \
    cp ${HOME_DIR}/oss_compliance/test/testOSSCompliance /usr/local/bin/testOSSCompliance && \
    chmod +x /usr/local/bin/testOSSCompliance && \
    chmod +x ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh && \
    ${HOME_DIR}/oss_compliance/generate_oss_compliance.sh ${HOME_DIR} python && \
    rm -rf ${HOME_DIR}/oss_compliance*

COPY /huggingface/pytorch/tgi/docker/3.3.4/THIRD-PARTY-LICENSES /root/THIRD-PARTY-LICENSES

ENV LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/root/.local/share/uv/python/cpython-3.11.11-linux-x86_64-gnu/lib/"
ENV HF_HUB_USER_AGENT_ORIGIN=aws:sagemaker:gpu-cuda:inference:tgi-native

COPY sagemaker-entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["--json-output"]

LABEL dlc_major_version="2"
LABEL com.amazonaws.ml.engines.sagemaker.dlc.framework.huggingface.tgi="true"
LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port="true"
