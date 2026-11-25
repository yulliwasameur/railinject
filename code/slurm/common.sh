#!/bin/bash
# Shared settings for MesoNET Juliet (A100 80 GB, project M26297).
# Conventions copied from the papierA campaign (account and partition checked there on 09/11/2026).
set -euo pipefail
export WORK=${WORK:-/projects/m26297/ai4rails}
export VENV=$WORK/.venv
export HF_HOME=${HF_HOME:-/projects/m26297/hf}          # shared model cache
export RUNS=$WORK/runs
export SB_ACCOUNT="--account=m26297"
export SB_PART="--partition=mesonet"
# model table: name | tensor-parallel | vLLM tool-call parser
declare -gA TP=( ["Qwen/Qwen2.5-7B-Instruct"]=1 ["meta-llama/Llama-3.1-8B-Instruct"]=1
                 ["Qwen/Qwen2.5-32B-Instruct"]=2 ["meta-llama/Llama-3.3-70B-Instruct"]=4 )
declare -gA PARSER=( ["Qwen/Qwen2.5-7B-Instruct"]=hermes ["meta-llama/Llama-3.1-8B-Instruct"]=llama3_json
                     ["Qwen/Qwen2.5-32B-Instruct"]=hermes ["meta-llama/Llama-3.3-70B-Instruct"]=llama3_json )
slug() { echo "$1" | tr '/' '_' ; }
activate() { source "$VENV/bin/activate"; cd "$WORK"; }
