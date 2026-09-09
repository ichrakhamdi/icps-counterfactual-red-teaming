# Nibi execution

The workflow targets the Alliance Nibi login host and standard Slurm/module
environment described in the [Nibi system documentation](https://docs.alliancecan.ca/wiki/Nibi/en).

Each submission receives its own directory:

```text
$SCRATCH/icps-counterfactual-red-teaming/runs/<RUN_ID>/
├── aggregate/   # validated JSON, CSV, LaTeX table, checksums
├── jobs/        # job_0000.json ... job_0029.json
├── logs/        # one Slurm log per array task
└── meta/        # frozen config, Git commit, run ID, Slurm job ID
```

From a clean clone on Nibi:

```bash
module load StdEnv/2023
git clone https://github.com/ichrakhamdi/icps-counterfactual-red-teaming.git
cd icps-counterfactual-red-teaming

export SLURM_ACCOUNT=def-YOUR-ALLOCATION
bash jobs/nibi/submit.sh cf-v2-$(date -u +%Y%m%dT%H%M%SZ)
```

The submit command prints the generated run ID. Use it for every later command:

```bash
squeue -u "$USER"
bash jobs/nibi/aggregate.sh RUN_ID
```

To choose a recognizable, still unique name:

```bash
bash jobs/nibi/submit.sh cf-v2-$(date -u +%Y%m%dT%H%M%SZ)
```

The exact array range is derived from the number of seeds in the frozen
configuration. It is throttled to ten simultaneous CPU tasks by default. Use a
lower throttle while other jobs are active, for example:

```bash
export CFRT_MAX_CONCURRENT=4
bash jobs/nibi/submit.sh cf-v2-$(date -u +%Y%m%dT%H%M%SZ)
```

Override `CFRT_RUNS_ROOT` only when another scratch location is preferred. Set
`CFRT_ARCHIVE_ROOT` before aggregation to copy the complete validated run to a
persistent project directory.

Download only the compact validated artifacts to a local results directory:

```bash
mkdir -p results-nibi/RUN_ID
rsync -av USER@nibi.alliancecan.ca:\
  scratch/icps-counterfactual-red-teaming/runs/RUN_ID/aggregate/ \
  results-nibi/RUN_ID/
```
