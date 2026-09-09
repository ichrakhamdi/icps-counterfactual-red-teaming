# Nibi Runbook

The detailed layout and commands are in `jobs/nibi/README.md`. Every run
is isolated under:

```text
$SCRATCH/icps-counterfactual-red-teaming/runs/<RUN_ID>/
```

Run the local gate from a clean checkout, then submit:

```bash
make local-gate
export SLURM_ACCOUNT=def-YOUR-ALLOCATION
bash jobs/nibi/submit.sh
```

The submission creates separate `jobs`, `logs`, `meta`, and `aggregate`
directories. It copies the exact configuration into `meta`, records the commit,
submission time, account, cluster, resources, derived array specification, and
Slurm job ID, and refuses to reuse an existing run ID. The array range is
derived from the configured seed count, with no more than ten tasks running
simultaneously by default.

When other work is already running, reduce concurrency without changing the
scientific configuration:

```bash
export CFRT_MAX_CONCURRENT=4
```

After the array finishes:

```bash
bash jobs/nibi/aggregate.sh RUN_ID
```

Aggregation requires the original commit and every configured job file.
It rejects dirty, mixed-commit, missing, duplicate, and wrong-configuration
artifacts. Final JSON, CSV, LaTeX, and SHA-256 checksums remain inside that
run's `aggregate` directory.

Set `CFRT_ARCHIVE_ROOT` to a persistent project directory before aggregation
when a long-term copy is required. Alliance scratch storage is intended for
temporary high-throughput data, while project storage is intended for durable
research data.
