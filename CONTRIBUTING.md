# Contributing to Synapse

Thank you for considering contributing to Synapse. This project welcomes fixes, tests, documentation improvements, and features that fit the edge-first, brokerless scope described in the README and `docs/`.

## Code of Conduct

There is no separate Code of Conduct document yet; please interact respectfully and professionally.

## Development setup

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

See [`.env.example`](.env.example) for monitor/sensor variables (copy to `.env` when using Docker Compose).

### Quality checks (run before pushing)

```sh
ruff check src tests tools
ruff format src tests tools   # or `ruff format --check src tests tools` in CI
mypy src
pytest -q --tb=short
```

CI on `main` / `master` runs the same checks (see `.github/workflows/ci.yml`).

### Optional: Git commit identity

If you use GitHub’s private email or a project-specific identity, configure it locally (do not commit secrets):

```sh
git config user.name "Your Name"
git config user.email "your-id@users.noreply.github.com"
```

## Reporting bugs

Open an issue and include:

- OS and version
- Python version (`python -V`)
- What you expected vs what happened
- Steps to reproduce and relevant logs

## Suggesting enhancements

Open an issue first so direction and scope stay aligned with the project goals.

## Pull request process

1. Fork the repository and create a branch from `main`.
2. Follow existing layout: network I/O in `src/network/`, domain state in `src/core/`, keep the boundary clear.
3. Add or update tests under `tests/` for behavior changes.
4. Ensure `ruff`, `mypy`, and `pytest` pass locally (see above).
5. Open a PR with a concise description of the problem and the change.

Pull requests are reviewed as time allows. Thank you.
