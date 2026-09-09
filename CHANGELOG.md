# Changelog

## 0.2.1 — 2026-09-09

- Corrected the Cyber-CF ablation so physical impact cannot guide its search or
  final selection.
- Added target-specific sensor replay and actuator-override dynamics.
- Externalized all confirmatory training, seed-stream, scenario, search, and
  aggregation settings into the hashed protocol configuration.
- Added strict protocol preflight, stronger provenance rejection, and a
  Nibi-specific array whose size is derived from the configured seed count.
- Counted invalid and duplicate campaign proposals, and corrected the paired
  bootstrap to resample independent policy seeds.
- Added regression tests for baseline isolation, provenance, and asset-specific
  physics; the IEEE manuscript now builds without warnings or column overflow.

## 0.2.0 — 2026-09-09

- Reorganized the Python package by research responsibility: core campaign
  logic, models, simulators, explainers, and evaluation.
- Added reproducible Alliance Slurm launch material.
- Expanded the repository presentation, architecture, execution modes,
  generated-output policy, and citation guidance.
- Retained the frozen 30-seed confirmatory protocol and public policy boundary.

## 0.1.1 — 2026-09-08

- Adopted the paper-and-scope repository name.
- Isolated cluster run outputs and hardened aggregation provenance checks.

## 0.1.0 — 2026-09-08

- Published the initial implementation, tests, paper draft, and protocol.
