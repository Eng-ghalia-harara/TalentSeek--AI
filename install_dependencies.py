"""Install project requirements into the Python interpreter selected in VS Code."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"


def main() -> None:
    if not REQUIREMENTS.exists():
        raise FileNotFoundError(f"requirements.txt was not found: {REQUIREMENTS}")

    print(f"Python interpreter: {sys.executable}")
    print("Installing project dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=ROOT,
        check=True,
    )
    print("\nDependencies installed successfully.")
    print("Restart the VS Code Python terminal/kernel if packages were previously imported.")


if __name__ == "__main__":
    main()
