# Narval Runbook

The detailed layout and commands are in `cluster/narval/README.md`. Every run
is isolated under:

```text
$SCRATCH/isie2027-icps-counterfactual-xai/runs/<RUN_ID>/
```

Run the local gate from a clean checkout, then submit:

```bash
make local-gate
export SLURM_ACCOUNT=def-YOUR-ALLOCATION
bash cluster/narval/submit.sh
```

The submission creates separate `jobs`, `logs`, `meta`, and `aggregate`
directories. It copies the exact configuration into `meta`, records the commit,
and refuses to reuse an existing run ID. The array is `0-29%10`: thirty seeds,
with no more than ten tasks running simultaneously.

After the array finishes:

```bash
bash cluster/narval/aggregate.sh RUN_ID
```

Aggregation requires the original commit and all thirty compatible job files.
It rejects dirty, mixed-commit, missing, duplicate, and wrong-configuration
artifacts. Final JSON, CSV, LaTeX, and SHA-256 checksums remain inside that
run's `aggregate` directory.

Set `ISIE_ARCHIVE_ROOT` to a persistent project directory before aggregation
when a long-term copy is required. Alliance scratch storage is intended for
temporary high-throughput data, while project storage is intended for durable
research data.
