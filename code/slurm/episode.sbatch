#!/bin/bash
#SBATCH --job-name=ai4rails
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=16
#SBATCH --output=logs/%x-%A_%a.out
# Usage: sbatch [gpu opts] --array=0-(N-1) episode.sbatch MODEL POLICIES FRAMINGS KINDS RUN TEMP LIMIT OUTTAG
# Starts one vLLM server per array task and runs one shard. Resumable: resubmit the same command.
source "${WORK:-/projects/m26297/ai4rails}/slurm/common.sh"; activate
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
MODEL=$1; POLS=$2; FRAMS=$3; KINDS=$4; RUN=$5; TEMP=$6; LIMIT=$7; TAG=$8
SL=$(slug "$MODEL"); NSH=${SLURM_ARRAY_TASK_COUNT:-1}; SH=${SLURM_ARRAY_TASK_ID:-0}
PORT=$(( 20000 + (${SLURM_ARRAY_JOB_ID:-$$} % 2000) * 16 + SH ))
mkdir -p logs "$RUNS/$TAG"
python -m vllm.entrypoints.openai.api_server --model "$MODEL" --port $PORT \
  --tensor-parallel-size ${TP[$MODEL]} --enable-auto-tool-choice --tool-call-parser ${PARSER[$MODEL]} \
  --max-model-len 16384 --seed 0 --gpu-memory-utilization 0.90 > "logs/vllm-$SL-$TAG-$SH.log" 2>&1 &
PID=$!
for i in $(seq 1 180); do
  kill -0 $PID 2>/dev/null || { echo "vLLM died"; exit 1; }
  curl -sf localhost:$PORT/v1/models >/dev/null && break; sleep 10
done
python -m railinject.run --agent llm --model "$MODEL" --base-url http://localhost:$PORT/v1 \
  --policies "$POLS" --framings "$FRAMS" --kinds "$KINDS" --run-id "$RUN" --temperature "$TEMP" \
  --limit "$LIMIT" --shard "$SH/$NSH" --workers 16 \
  --out "$RUNS/$TAG/${SL}__run${RUN}__t${TEMP}__$SH.jsonl"
kill $PID; wait $PID 2>/dev/null || true
