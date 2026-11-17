# `scripts/`

Small repository maintenance helpers. They are convenience wrappers; the CLI is
still the supported interface.

| Script | Purpose |
| --- | --- |
| `check.sh` | Run Ruff lint, Ruff format check, and the full test suite in the project `.venv`. |

## Usage

```bash
./scripts/check.sh
```

The script uses `uv run`, so it never installs global packages and always uses
`uv.lock` and the project `.venv`.

## Adding scripts

- Keep them short and delegate real work to `uv run jobscraper ...` or
  `uv run pytest ...`.
- Use `#!/usr/bin/env bash` and `set -euo pipefail`.
- Do not hardcode personal paths, API keys, or user data.
- Document the script in this README.
