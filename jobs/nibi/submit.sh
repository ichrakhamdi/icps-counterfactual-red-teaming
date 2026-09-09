#!/usr/bin/env bash
# Validate the frozen protocol, create an isolated run, and submit on Nibi.
set -euo pipefail

: "${SLURM_ACCOUNT:?Set SLURM_ACCOUNT to your Alliance allocation, for example def-example}"
: "${SCRATCH:?SCRATCH is not defined; run this script on Nibi}"

repo_root="$(git rev-parse --show-toplevel)"
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "Refusing to submit from a dirty worktree." >&2
  exit 2
fi

project_slug="icps-counterfactual-red-teaming"
commit="$(git -C "$repo_root" rev-parse HEAD)"
short_commit="${commit:0:8}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_id="${1:-${timestamp}-${short_commit}}"
runs_root="${CFRT_RUNS_ROOT:-$SCRATCH/$project_slug/runs}"
run_root="$runs_root/$run_id"
python_bin="${PYTHON_BIN:-python3}"
config_path="$repo_root/configs/cluster.json"
seed_count="$("$python_bin" "$repo_root/scripts/preflight_protocol.py" --config "$config_path" --print-job-count)"
max_concurrent="${CFRT_MAX_CONCURRENT:-10}"
memory="${CFRT_MEMORY:-2G}"
walltime="${CFRT_WALLTIME:-01:00:00}"

if [[ ! "$seed_count" =~ ^[1-9][0-9]*$ ]]; then
  echo "Protocol preflight returned an invalid job count: $seed_count" >&2
  exit 2
fi
if [[ ! "$max_concurrent" =~ ^[1-9][0-9]*$ ]]; then
  echo "CFRT_MAX_CONCURRENT must be a positive integer." >&2
  exit 2
fi
if (( max_concurrent > seed_count )); then
  max_concurrent="$seed_count"
fi
array_spec="0-$((seed_count - 1))%$max_concurrent"

if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]; then
  echo "Run ID must contain only letters, digits, dots, underscores, and hyphens." >&2
  exit 2
fi

if [[ -e "$run_root" ]]; then
  echo "Run directory already exists: $run_root" >&2
  exit 2
fi

mkdir -p "$run_root/jobs" "$run_root/logs" "$run_root/meta" "$run_root/aggregate"
cp "$config_path" "$run_root/meta/cluster.json"
printf '%s\n' "$commit" > "$run_root/meta/git-commit.txt"
printf '%s\n' "$repo_root" > "$run_root/meta/repository-path.txt"
printf '%s\n' "$run_id" > "$run_root/meta/run-id.txt"
printf '%s\n' "$timestamp" > "$run_root/meta/submitted-utc.txt"
printf '%s\n' "$SLURM_ACCOUNT" > "$run_root/meta/slurm-account.txt"
printf '%s\n' "$array_spec" > "$run_root/meta/array-spec.txt"
printf '%s\n' "${CC_CLUSTER:-nibi}" > "$run_root/meta/cluster-name.txt"
printf '%s\n' "$memory" > "$run_root/meta/memory.txt"
printf '%s\n' "$walltime" > "$run_root/meta/walltime.txt"

job_id="$(sbatch --parsable \
  --job-name=icps-cf \
  --account="$SLURM_ACCOUNT" \
  --array="$array_spec" \
  --nodes=1 \
  --cpus-per-task=1 \
  --mem="$memory" \
  --time="$walltime" \
  --output="$run_root/logs/slurm-%A_%a.out" \
  --export="ALL,CFRT_REPO_ROOT=$repo_root,CFRT_RUN_ROOT=$run_root,CFRT_CONFIG_PATH=$run_root/meta/cluster.json" \
  "$repo_root/jobs/nibi/job.sh")"

printf '%s\n' "$job_id" > "$run_root/meta/slurm-job-id.txt"
printf 'Submitted array job %s\nRun ID: %s\nRun directory: %s\n' "$job_id" "$run_id" "$run_root"
