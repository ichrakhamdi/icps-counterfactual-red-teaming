"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .experiment import run_pilot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.json"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = run_pilot(config, args.root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

