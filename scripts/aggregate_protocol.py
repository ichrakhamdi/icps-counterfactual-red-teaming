#!/usr/bin/env python3
"""Validate and aggregate all deterministic protocol shards."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.protocol import aggregate_jobs, write_confirmatory_latex  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--latex-output",
        type=Path,
        default=ROOT / "paper" / "generated" / "confirmatory_table.tex",
    )
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    artifact = aggregate_jobs(config, args.input_dir, args.output)
    write_confirmatory_latex(args.latex_output, artifact["summary"])
    print(json.dumps(artifact["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
