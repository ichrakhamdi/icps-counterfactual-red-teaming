#!/usr/bin/env bash
# Validate a complete isolated run and generate final artifacts in that run only.
set -euo pipefail

: "${SCRATCH:?SCRATCH is not defined; run this script on Narval}"
if [[ $# -ne 1 ]]; then
  echo "Usage: bash jobs/narval/aggregate.sh RUN_ID" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
project_slug="icps-counterfactual-red-teaming"
runs_root="${CFRT_RUNS_ROOT:-$SCRATCH/$project_slug/runs}"
run_root="$runs_root/$1"
config="$run_root/meta/cluster.json"

if [[ ! -f "$config" ]]; then
  echo "Unknown run or missing configuration: $run_root" >&2
  exit 2
fi

expected_commit="$(cat "$run_root/meta/git-commit.txt")"
current_commit="$(git -C "$repo_root" rev-parse HEAD)"
if [[ "$current_commit" != "$expected_commit" ]]; then
  echo "Checkout $expected_commit before aggregating this run." >&2
  exit 2
fi

module --force purge
module load StdEnv/2023
module load "${CFRT_PYTHON_MODULE:-python/3.11}"
python_bin="${PYTHON_BIN:-python3}"

mkdir -p "$run_root/aggregate"
"$python_bin" "$repo_root/scripts/aggregate_protocol.py" \
  --config "$config" \
  --input-dir "$run_root/jobs" \
  --output "$run_root/aggregate/confirmatory.json" \
  --latex-output "$run_root/aggregate/confirmatory_table.tex"

(
  cd "$run_root"
  sha256sum meta/cluster.json meta/git-commit.txt jobs/job_*.json \
    aggregate/confirmatory.json aggregate/confirmatory.csv \
    aggregate/confirmatory_table.tex > aggregate/SHA256SUMS
)

if [[ -n "${CFRT_ARCHIVE_ROOT:-}" ]]; then
  archive="$CFRT_ARCHIVE_ROOT/$project_slug/$1"
  if [[ -e "$archive" ]]; then
    echo "Archive already exists: $archive" >&2
    exit 2
  fi
  mkdir -p "$(dirname "$archive")"
  cp -R "$run_root" "$archive"
  printf 'Archived to %s\n' "$archive"
fi

printf 'Validated artifacts: %s\n' "$run_root/aggregate"
