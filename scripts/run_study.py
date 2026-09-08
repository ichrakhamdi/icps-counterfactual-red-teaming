#!/usr/bin/env python3
"""Run the multi-seed engineering study from a source checkout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.experiment import run_study  # noqa: E402


if __name__ == "__main__":
    configuration = json.loads((ROOT / "configs" / "default.json").read_text(encoding="utf-8"))
    artifact = run_study(configuration, ROOT)
    print(json.dumps(artifact["summary"], indent=2))
