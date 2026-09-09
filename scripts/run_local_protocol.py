#!/usr/bin/env python3
"""Run every shard in a configuration and aggregate locally."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.evaluation.protocol import aggregate_jobs, run_job  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    for index in range(len(config["evaluation_policy_seeds"])):
        run_job(config, ROOT, index, args.output_dir)
    aggregate = aggregate_jobs(config, args.output_dir, args.output_dir / "aggregate.json")
    print(json.dumps(aggregate["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
