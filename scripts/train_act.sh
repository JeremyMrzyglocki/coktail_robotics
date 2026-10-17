#!/usr/bin/env bash
# Train ACT on a LeRobotDataset from the Hugging Face Hub and push the policy back to the Hub.
# Meant for a GPU machine (e.g. AWS EC2 g5.xlarge), run from the repo root. See docs/PIPELINE.md.
#
#   export HF_TOKEN=hf_...        # write token: reads the dataset, pushes the model
#   ./scripts/train_act.sh antonin-leroy/<dataset> antonin-leroy/<model_name> [extra lerobot-train args]
#
# Env overrides: STEPS (100000), BATCH_SIZE (8), DEVICE (cuda), WANDB (false).
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 antonin-leroy/<dataset> antonin-leroy/<model_name> [extra lerobot-train args]" >&2
    exit 1
fi
DATASET=$1
MODEL=$2
shift 2
: "${HF_TOKEN:?export HF_TOKEN=hf_... (a Hugging Face write token)}"

cd "$(dirname "$0")/.."
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
uv sync

JOB="act_$(basename "$MODEL")_$(date +%Y%m%d_%H%M%S)"
uv run lerobot-train \
    --dataset.repo_id="$DATASET" \
    --policy.type=act \
    --policy.device="${DEVICE:-cuda}" \
    --policy.repo_id="$MODEL" \
    --policy.push_to_hub=true \
    --output_dir="outputs/train/$JOB" \
    --job_name="$JOB" \
    --steps="${STEPS:-100000}" \
    --batch_size="${BATCH_SIZE:-8}" \
    --wandb.enable="${WANDB:-false}" \
    "$@"
echo "Done: outputs/train/$JOB, model pushed to https://huggingface.co/$MODEL"
