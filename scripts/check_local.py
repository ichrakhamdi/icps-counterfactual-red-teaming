#!/usr/bin/env python3
"""Fail-fast local release gate for code, protocol, determinism, and paper."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONPYCACHEPREFIX="/tmp/icps_cf_release_pycache")


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=ENV, check=True)


def stable_job(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for record in payload["records"]:
        record.pop("runtime_seconds", None)
    payload.pop("git_commit", None)
    payload.pop("git_dirty", None)
    payload.pop("created_utc", None)
    payload.pop("platform", None)
    payload.pop("python", None)
    return payload


def main() -> None:
    run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run(["bash", "-n", "jobs/narval/job.sh"])
    run(["bash", "-n", "jobs/narval/submit.sh"])
    run(["bash", "-n", "jobs/narval/aggregate.sh"])

    with tempfile.TemporaryDirectory(prefix="icps_cf_gate_", dir="/tmp") as directory:
        first = Path(directory) / "first"
        second = Path(directory) / "second"
        for output in (first, second):
            run(
                [
                    sys.executable,
                    "scripts/run_local_protocol.py",
                    "--config",
                    "configs/local_gate.json",
                    "--output-dir",
                    str(output),
                ]
            )
        if stable_job(first / "job_0000.json") != stable_job(second / "job_0000.json"):
            raise SystemExit("determinism gate failed: repeated protocol jobs differ")

    forbidden = ("harp", "option-critic", "admissible action")
    for path in ROOT.joinpath("src").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        hits = [term for term in forbidden if term in text]
        if hits:
            raise SystemExit(f"thesis-boundary gate failed in {path}: {hits}")

    if shutil.which("pdflatex") and shutil.which("bibtex"):
        tex_env = dict(ENV, TEXMFVAR="/tmp/icps_cf_release_texmf")
        commands = (
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            ["bibtex", "main"],
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
        )
        for command in commands:
            print("+", " ".join(command), flush=True)
            subprocess.run(command, cwd=ROOT / "paper", env=tex_env, check=True)
        log = (ROOT / "paper" / "main.log").read_text(encoding="utf-8", errors="replace")
        forbidden_log = ("LaTeX Warning:", "Undefined control sequence", "Overfull \\hbox")
        hits = [term for term in forbidden_log if term in log]
        if hits:
            raise SystemExit(f"paper gate failed: {hits}")
    else:
        print("paper gate skipped: pdflatex/bibtex unavailable")
    print("LOCAL RELEASE GATE: PASS")


if __name__ == "__main__":
    main()
