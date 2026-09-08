#!/usr/bin/env bash
# One Slurm array task: one frozen policy seed, four scenarios, four methods.
set -euo pipefail

: "${ISIE_REPO_ROOT:?ISIE_REPO_ROOT is required}"
: "${ISIE_RUN_ROOT:?ISIE_RUN_ROOT is required}"
: "${ISIE_CONFIG_PATH:?ISIE_CONFIG_PATH is required}"
: "${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"

module --force purge
module load StdEnv/2023
module load "${ISIE_PYTHON_MODULE:-python/3.11}"

python_bin="${PYTHON_BIN:-python3}"
task_id="$SLURM_ARRAY_TASK_ID"
export PYTHONPYCACHEPREFIX="${SLURM_TMPDIR:-/tmp}/isie2027-pycache-${SLURM_JOB_ID}-${task_id}"

cd "$ISIE_REPO_ROOT"
"$python_bin" scripts/run_protocol_job.py \
  --config "$ISIE_CONFIG_PATH" \
  --job-index "$task_id" \
  --output-dir "$ISIE_RUN_ROOT/jobs"
