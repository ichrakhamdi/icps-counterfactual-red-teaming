#!/usr/bin/env bash
# Create an isolated run directory and submit the 30-task Narval array.
set -euo pipefail

: "${SLURM_ACCOUNT:?Set SLURM_ACCOUNT to your Alliance allocation, for example def-example}"
: "${SCRATCH:?SCRATCH is not defined; run this script on Narval}"

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
array_spec="${CFRT_ARRAY_SPEC:-0-29%10}"

if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]; then
  echo "Run ID must contain only letters, digits, dots, underscores, and hyphens." >&2
  exit 2
fi

if [[ -e "$run_root" ]]; then
  echo "Run directory already exists: $run_root" >&2
  exit 2
fi

mkdir -p "$run_root/jobs" "$run_root/logs" "$run_root/meta" "$run_root/aggregate"
cp "$repo_root/configs/cluster.json" "$run_root/meta/cluster.json"
printf '%s\n' "$commit" > "$run_root/meta/git-commit.txt"
printf '%s\n' "$repo_root" > "$run_root/meta/repository-path.txt"
printf '%s\n' "$run_id" > "$run_root/meta/run-id.txt"
printf '%s\n' "$timestamp" > "$run_root/meta/submitted-utc.txt"
printf '%s\n' "$SLURM_ACCOUNT" > "$run_root/meta/slurm-account.txt"
printf '%s\n' "$array_spec" > "$run_root/meta/array-spec.txt"

job_id="$(sbatch --parsable \
  --job-name=icps-cf \
  --account="$SLURM_ACCOUNT" \
  --array="$array_spec" \
  --cpus-per-task=1 \
  --mem=2G \
  --time=01:00:00 \
  --output="$run_root/logs/slurm-%A_%a.out" \
  --export="ALL,CFRT_REPO_ROOT=$repo_root,CFRT_RUN_ROOT=$run_root,CFRT_CONFIG_PATH=$run_root/meta/cluster.json" \
  "$repo_root/jobs/narval/job.sh")"

printf '%s\n' "$job_id" > "$run_root/meta/slurm-job-id.txt"
printf 'Submitted array job %s\nRun ID: %s\nRun directory: %s\n' "$job_id" "$run_id" "$run_root"
