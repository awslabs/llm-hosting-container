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
