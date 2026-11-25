#!/bin/bash
#SBATCH --job-name=ai4rails-analyze
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/%x-%j.out
source "${WORK:-/projects/m26297/ai4rails}/slurm/common.sh"; activate
mkdir -p "$RUNS/paper"
python -m railinject.analyze "$RUNS/campaign/*.jsonl" "$RUNS/subset70b/*.jsonl" --out "$RUNS/paper"
python -m railinject.analyze "$RUNS/variance/*.jsonl" --any-temp --out "$RUNS/paper/variance" || true
echo "results in $RUNS/paper"
