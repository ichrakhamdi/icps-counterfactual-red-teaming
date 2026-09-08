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

project_slug="isie2027-icps-counterfactual-xai"
commit="$(git -C "$repo_root" rev-parse HEAD)"
short_commit="${commit:0:8}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_id="${1:-${timestamp}-${short_commit}}"
runs_root="${ISIE_RUNS_ROOT:-$SCRATCH/$project_slug/runs}"
run_root="$runs_root/$run_id"

if [[ -e "$run_root" ]]; then
  echo "Run directory already exists: $run_root" >&2
  exit 2
fi

mkdir -p "$run_root/jobs" "$run_root/logs" "$run_root/meta" "$run_root/aggregate"
cp "$repo_root/configs/cluster.json" "$run_root/meta/cluster.json"
printf '%s\n' "$commit" > "$run_root/meta/git-commit.txt"
printf '%s\n' "$repo_root" > "$run_root/meta/repository-path.txt"
printf '%s\n' "$run_id" > "$run_root/meta/run-id.txt"

job_id="$(sbatch --parsable \
  --job-name=isie27-cf \
  --account="$SLURM_ACCOUNT" \
  --array=0-29%10 \
  --cpus-per-task=1 \
  --mem=2G \
  --time=01:00:00 \
  --output="$run_root/logs/slurm-%A_%a.out" \
  --export="ALL,ISIE_REPO_ROOT=$repo_root,ISIE_RUN_ROOT=$run_root,ISIE_CONFIG_PATH=$run_root/meta/cluster.json" \
  "$repo_root/cluster/narval/job.sh")"

printf '%s\n' "$job_id" > "$run_root/meta/slurm-job-id.txt"
printf 'Submitted array job %s\nRun ID: %s\nRun directory: %s\n' "$job_id" "$run_id" "$run_root"
