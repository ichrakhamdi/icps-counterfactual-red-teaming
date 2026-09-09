# Contributing

This repository is a reproducible research artifact. Changes should preserve
the campaign constraints, frozen-policy boundary, deterministic protocol, and
separation between local outputs and tracked source files.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Required checks

Run the complete local gate before proposing a change:

```bash
make local-gate
```

For a focused change, the unit suite is available separately:

```bash
python -m unittest discover -s tests -v
```

New campaign operators must retain stage prerequisites, directed reachability,
privilege, and timing checks. New explainers must use the public frozen-policy
interface. Changes to `configs/cluster.json` modify the frozen confirmatory
protocol and should explain why a new protocol version is required.

Do not commit generated result files, trained policies, LaTeX build products,
credentials, scheduler logs, virtual environments, or private research notes.
