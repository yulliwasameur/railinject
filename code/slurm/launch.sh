#!/bin/bash
# ONE command for the whole campaign on Juliet (run on the login node, inside $WORK):
#   bash slurm/launch.sh pilot      -> 20 items x 11 defences per model, prints the cost estimate
#   bash slurm/launch.sh campaign   -> full grid (3 models), 70B core subset, variance runs, analysis
# Everything is resumable: re-running the same command only fills the gaps.
source "$(dirname "$0")/common.sh"; cd "$WORK"; mkdir -p logs
ALL=D0,D1,D2,D3,D4,D5,D6,D7,D7-noC2,D7-noC3,D7-noC4
SMALL=("Qwen/Qwen2.5-7B-Instruct" "meta-llama/Llama-3.1-8B-Instruct" "Qwen/Qwen2.5-32B-Instruct")
BIG="meta-llama/Llama-3.3-70B-Instruct"
gpu() { echo "--gres=gpu:a100:${TP[$1]}"; }
case "${1:-}" in
  pilot)
    for M in "${SMALL[@]}" "$BIG"; do
      sbatch $SB_ACCOUNT $SB_PART $(gpu "$M") --time=03:00:00 --array=0-0 slurm/episode.sbatch \
        "$M" "D0,D7" template benign,attack,lifecycle 0 0.0 20 pilot
    done ;;
  estimate)
    source "$VENV/bin/activate"
    python - <<'PY'
import glob, json, statistics as st
for f in sorted(glob.glob("runs/pilot/*.jsonl")):
    R = [json.loads(l) for l in open(f)]
    s = [r["seconds"] for r in R if not r["error"]]
    print(f, "episodes", len(R), "errors", sum(1 for r in R if r["error"]),
          "median s/episode", round(st.median(s), 1) if s else None)
PY
    ;;
  campaign)
    IDS=()
    for M in "${SMALL[@]}"; do         # full grid, temperature 0, 8 shards per model
      IDS+=($(sbatch --parsable $SB_ACCOUNT $SB_PART $(gpu "$M") --array=0-7 slurm/episode.sbatch \
        "$M" "$ALL" template,rulebook,urgency benign,attack,lifecycle 0 0.0 0 campaign))
    done
    IDS+=($(sbatch --parsable $SB_ACCOUNT $SB_PART $(gpu "$BIG") --array=0-3 slurm/episode.sbatch \
      "$BIG" D0,D5,D6,D7 template benign,attack,lifecycle 0 0.0 0 subset70b))
    for M in "${SMALL[@]}"; do         # variance: D0 and D7, three runs at T=0.7, one framing
      for R in 1 2 3; do
        IDS+=($(sbatch --parsable $SB_ACCOUNT $SB_PART $(gpu "$M") --array=0-1 slurm/episode.sbatch \
          "$M" D0,D7 template benign,lifecycle $R 0.7 0 variance))
      done
    done
    DEP=$(IFS=:; echo "${IDS[*]}")
    sbatch $SB_ACCOUNT $SB_PART --dependency=afterany:$DEP slurm/analyze.sbatch
    echo "submitted: ${IDS[*]}" ;;
  *) echo "usage: launch.sh pilot|estimate|campaign"; exit 1 ;;
esac
