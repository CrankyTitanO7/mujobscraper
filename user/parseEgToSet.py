"""Compatibility wrapper for the old copy-the-examples workflow.

Prefer the CLI, which also creates CSV tables and directories:

    uv run jobscraper init
    uv run jobscraper init --force   # back up and replace existing configs
"""

from __future__ import annotations

from pathlib import Path

from jobscraper.config import find_project_root
from jobscraper.services.init import initialize_project


def main() -> None:
    root = find_project_root(Path.cwd())
    for path in initialize_project(root):
        print(f"initialized {path}")


if __name__ == "__main__":
    main()
