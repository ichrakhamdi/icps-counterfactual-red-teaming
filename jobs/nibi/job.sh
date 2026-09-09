#!/usr/bin/env bash
# One Slurm array task: one frozen policy seed, four scenarios, four methods.
set -euo pipefail

: "${CFRT_REPO_ROOT:?CFRT_REPO_ROOT is required}"
: "${CFRT_RUN_ROOT:?CFRT_RUN_ROOT is required}"
: "${CFRT_CONFIG_PATH:?CFRT_CONFIG_PATH is required}"
: "${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"

module --force purge
module load StdEnv/2023
module load "${CFRT_PYTHON_MODULE:-python/3.11}"

python_bin="${PYTHON_BIN:-python3}"
task_id="$SLURM_ARRAY_TASK_ID"
export PYTHONPYCACHEPREFIX="${SLURM_TMPDIR:-/tmp}/icps-cf-pycache-${SLURM_JOB_ID}-${task_id}"

cd "$CFRT_REPO_ROOT"
"$python_bin" scripts/preflight_protocol.py --config "$CFRT_CONFIG_PATH" >/dev/null
"$python_bin" scripts/run_protocol_job.py \
  --config "$CFRT_CONFIG_PATH" \
  --job-index "$task_id" \
  --output-dir "$CFRT_RUN_ROOT/jobs"
