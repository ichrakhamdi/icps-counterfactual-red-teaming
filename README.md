# Counterfactual Red-Teaming for Autonomous ICPS Response

This independent research repository supports an IEEE ISIE 2027 paper on
physically feasible counterfactual explanations for autonomous industrial
threat-response policies.

The prototype answers one question: **what is the smallest executable change
to a multi-stage campaign that makes a frozen responder choose a weaker action
and thereby increases physical impact?**

The project is self-contained. It uses a three-stage process, a flat tabular
Q-learning responder, fixed scripted campaigns, and an offline counterfactual
search. It does not import unpublished thesis implementations or results.

## Quick start

The reference implementation uses only the Python standard library.

```bash
python3 scripts/run_demo.py
python3 scripts/run_study.py
python3 -m unittest discover -s tests -v
make local-gate
```

The demo trains and freezes one generic responder and searches for a feasible
counterfactual campaign. The study command repeats the pipeline over independent
responder seeds and generates aggregate artifacts. Both write machine-readable
results under `results/` plus LaTeX tables under `paper/generated/`.

## Repository map

- `ARCHITECTURE.md`: component boundaries and data flow.
- `docs/EXPERIMENT_PROTOCOL.md`: hypotheses, baselines, metrics, and statistics.
- `src/icps_xai/`: simulator, campaign model, responder, and XAI search.
- `tests/`: executable unit and integration tests.
- `paper/`: standalone IEEE conference-paper draft.
- `cluster/narval/`: isolated Slurm launch, collection, and run layout.
- `docs/CLUSTER_RUNBOOK.md`: reproducible Narval commands.

`make local-gate` is required before a cluster launch. It compiles the Python
sources, runs invariant and integration tests, checks the Slurm scripts, repeats
the protocol to verify deterministic content, enforces the thesis boundary in
source code, and compiles the paper without warnings.

The software for the declared simulation study is complete. Confirmatory
numbers are intentionally absent until `configs/cluster.json` is run on the
cluster and all 30 job artifacts pass aggregation.
