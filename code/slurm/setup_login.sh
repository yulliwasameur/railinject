#!/bin/bash
# Run ONCE on the Juliet login node (it has Internet; compute nodes do not).
# Creates the venv, installs the code, downloads the 4 models and the detector,
# and records the exact model revisions for the pre-registration.
source "$(dirname "$0")/common.sh"
mkdir -p "$WORK" "$RUNS" "$HF_HOME"
rsync -a --exclude runs "$(dirname "$0")/../" "$WORK/"
[ -d "$VENV" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install -q --upgrade pip
pip install -q "vllm>=0.6" openai cryptography transformers matplotlib huggingface_hub
cd "$WORK"
for M in "${!TP[@]}" protectai/deberta-v3-base-prompt-injection-v2; do
  huggingface-cli download "$M" --exclude "*.pth" "original/*" >/dev/null && echo "ok $M"
done
python - <<'PY' > "$RUNS/MODEL_REVISIONS.json"
import json
from huggingface_hub import HfApi
api = HfApi()
ms = ["Qwen/Qwen2.5-7B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-32B-Instruct",
      "meta-llama/Llama-3.3-70B-Instruct", "protectai/deberta-v3-base-prompt-injection-v2"]
print(json.dumps({m: api.model_info(m).sha for m in ms}, indent=1))
PY
python -c "from railinject.suites import test_set_hash; print(test_set_hash())" > "$RUNS/TEST_SET_SHA256.txt"
pip freeze > "$RUNS/pip-freeze.txt"
echo "setup done: $(cat "$RUNS/TEST_SET_SHA256.txt")"
