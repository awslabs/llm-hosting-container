#!/bin/bash

verlt() {
    [ "$1" = "$2" ] && return 1 || [ "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}

if [ -f /usr/local/cuda/compat/libcuda.so.1 ]; then
    CUDA_COMPAT_MAX_DRIVER_VERSION=$(readlink /usr/local/cuda/compat/libcuda.so.1 | cut -d'.' -f 3-)
    echo "CUDA compat package should be installed for NVIDIA driver smaller than ${CUDA_COMPAT_MAX_DRIVER_VERSION}"
    NVIDIA_DRIVER_VERSION=$(sed -n 's/^NVRM.*Kernel Module *\([0-9.]*\).*$/\1/p' /proc/driver/nvidia/version 2>/dev/null || true)
    echo "Current installed NVIDIA driver version is ${NVIDIA_DRIVER_VERSION}"
    if verlt $NVIDIA_DRIVER_VERSION $CUDA_COMPAT_MAX_DRIVER_VERSION; then
        echo "Adding CUDA compat to LD_LIBRARY_PATH"
        export LD_LIBRARY_PATH=/usr/local/cuda/compat:$LD_LIBRARY_PATH
        echo $LD_LIBRARY_PATH
    else
        echo "Skipping CUDA compat setup as newer NVIDIA driver is installed"
    fi
else
    echo "Skipping CUDA compat setup as package not found"
fi

if [[ -z "${HF_MODEL_ID}" ]]; then
  echo "HF_MODEL_ID must be set"
  exit 1
fi
export MODEL_ID="${HF_MODEL_ID}"

if [[ -z "${HF_MODEL_GGUF}" ]]; then
  echo "HF_MODEL_GGUF must be set"
  exit 1
fi

mkdir models

if [[ -n "$HF_MODEL_GGUF_DIR" ]]; then
    huggingface-cli download "{$HF_MODEL_GGUF}" --include "${HF_MODEL_GGUF_DIR}"/*.gguf --local-dir ./models/"${HF_MODEL_GGUF}"
    echo "Downloaded model gguf files to ./models/${HF_MODEL_GGUF}/${HF_MODEL_GGUF_DIR}"
    export MODEL_GGUF="$(find ./models/"${HF_MODEL_GGUF}"/"${HF_MODEL_GGUF_DIR}" -maxdepth 1 -type f -name "*.gguf" | sort | head -n 1)"
else
    huggingface-cli download "${HF_MODEL_GGUF}" --local-dir "./models/${HF_MODEL_GGUF}"
    echo "Downloaded model gguf files to ./models/${HF_MODEL_GGUF}"
    export MODEL_GGUF="$(find ./models/"${HF_MODEL_GGUF}" -maxdepth 1 -type f -name "*.gguf" | sort | head -n 1)"
fi

if [[ -z "${MODEL_GGUF}" ]]; then
    echo "No gguf files found in ./models/${HF_MODEL_GGUF}"
    exit 1
fi

text-generation-router-llamacpp --port 8080