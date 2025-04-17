#!/bin/bash
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