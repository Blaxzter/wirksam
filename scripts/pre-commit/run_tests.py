#!/usr/bin/env python3
"""Run pytest for pre-commit hook.

Uses pytest-testmon to only run tests affected by changed code.
First run executes all tests to build the dependency map (.testmondata).
Subsequent runs only re-run tests whose dependencies changed.

To force a full run: uv run pytest --testmon-forcerun
To disable testmon:  uv run pytest --no-testmon
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    """Run tests using uv with testmon for incremental test selection."""
    backend_dir = Path(__file__).parent.parent.parent / "backend"
    os.chdir(backend_dir)

    pytest_args = ["uv", "run", "pytest", "--testmon"]

    try:
        result = subprocess.run(pytest_args, check=False)
        sys.exit(result.returncode)
    except FileNotFoundError:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--testmon"],
            check=False,
        )
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
