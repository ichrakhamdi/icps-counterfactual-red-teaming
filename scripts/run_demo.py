#!/usr/bin/env python3
"""Run the dependency-free engineering pilot from a source checkout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from icps_xai.evaluation.experiment import run_pilot  # noqa: E402


if __name__ == "__main__":
    configuration = json.loads((ROOT / "configs" / "default.json").read_text(encoding="utf-8"))
    print(json.dumps(run_pilot(configuration, ROOT), indent=2))
