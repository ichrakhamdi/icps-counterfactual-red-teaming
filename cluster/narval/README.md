# Narval execution

Each submission receives its own directory:

```text
$SCRATCH/isie2027-icps-counterfactual-xai/runs/<RUN_ID>/
├── aggregate/   # validated JSON, CSV, LaTeX table, checksums
├── jobs/        # job_0000.json ... job_0029.json
├── logs/        # one Slurm log per array task
└── meta/        # frozen config, Git commit, run ID, Slurm job ID
```

From a clean clone on Narval:

```bash
module load StdEnv/2023
git clone https://github.com/ichrakhamdi/isie2027-icps-counterfactual-xai.git
cd isie2027-icps-counterfactual-xai

export SLURM_ACCOUNT=def-YOUR-ALLOCATION
bash cluster/narval/submit.sh cf-v1-$(date -u +%Y%m%dT%H%M%SZ)
```

The submit command prints the generated run ID. Use it for every later command:

```bash
squeue -u "$USER"
bash cluster/narval/aggregate.sh RUN_ID
```

To choose a recognizable, still unique name:

```bash
bash cluster/narval/submit.sh cf-v1-$(date -u +%Y%m%dT%H%M%SZ)
```

The array is throttled to ten simultaneous CPU tasks so it does not crowd other
work. Use a lower throttle while other jobs are active, for example:

```bash
export ISIE_ARRAY_SPEC=0-29%4
bash cluster/narval/submit.sh cf-v1-$(date -u +%Y%m%dT%H%M%SZ)
```

Override `ISIE_RUNS_ROOT` only when another scratch location is preferred. Set
`ISIE_ARCHIVE_ROOT` before aggregation to copy the complete validated run to a
persistent project directory.

Download only the compact validated artifacts to a local results directory:

```bash
mkdir -p results-narval/RUN_ID
rsync -av USER@narval.alliancecan.ca:\
  scratch/isie2027-icps-counterfactual-xai/runs/RUN_ID/aggregate/ \
  results-narval/RUN_ID/
```
