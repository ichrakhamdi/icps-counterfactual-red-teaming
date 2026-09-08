#!/usr/bin/env python3
"""Run one deterministic protocol shard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.protocol import run_job  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--job-index", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    artifact = run_job(config, ROOT, args.job_index, args.output_dir)
    print(json.dumps({"job_index": artifact["job_index"], "records": len(artifact["records"])}))


if __name__ == "__main__":
    main()
