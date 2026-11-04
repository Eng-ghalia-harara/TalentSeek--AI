"""Convenience launcher: run this file with VS Code's Run Python File button."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

command = [
    sys.executable,
    "-m",
    "streamlit",
    "run",
    str(ROOT / "app.py"),
]
raise SystemExit(subprocess.call(command, cwd=ROOT))
