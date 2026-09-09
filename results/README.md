# Generated results

This directory is the default destination for local pilot, smoke, and study
artifacts. JSON, CSV, trained tables, logs, and generated paper fragments are
excluded from Git so provisional or machine-specific outputs cannot be
published accidentally.

The confirmatory Nibi run is written to an isolated directory under
`$SCRATCH/icps-counterfactual-red-teaming/runs/<RUN_ID>/`. Only the validated
contents of its `aggregate/` directory should be used to prepare paper results.

Run `python scripts/run_demo.py`, `python scripts/run_study.py`, or `make smoke`
to generate local artifacts.
