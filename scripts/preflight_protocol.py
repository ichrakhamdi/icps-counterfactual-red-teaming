#!/usr/bin/env python3
"""Validate a protocol configuration before local or Slurm execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.evaluation.protocol import METHODS, scenario_suite, validate_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--print-job-count", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    jobs = len(config["evaluation_policy_seeds"])
    if args.print_job_count:
        print(jobs)
        return
    summary = {
        "status": "valid",
        "protocol_name": config["protocol_name"],
        "jobs": jobs,
        "scenarios_per_job": len(scenario_suite(config)),
        "methods_per_scenario": len(METHODS),
        "records_expected": jobs * len(scenario_suite(config)) * len(METHODS),
        "search_evaluations_per_method": config["search_evaluation_budget"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
