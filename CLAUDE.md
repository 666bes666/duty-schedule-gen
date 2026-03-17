# Claude Code Instructions for duty-schedule-gen

## Branching Flow

dev -> test -> main

Commit directly to `dev`. Do NOT create feature branches.
NEVER push directly to main (except hotfixes).

### Delivery:
1. Commit directly to `dev`
2. Run local checks before push
3. **Push to GitHub immediately** — never keep commits only local
4. PR dev -> test (ci-test must be green)
5. PR test -> main (ci-main must be green)
6. Update version -> tag -> release

### Hotfix:
1. Branch from main
2. PR directly to main
3. Cherry-pick into dev and test

### Release Policy:
- **Always push to GitHub immediately** after committing. Do not accumulate local-only commits.
- **Merge PRs via GitHub** (gh pr merge), not locally. This ensures CI checks run and branch protection is respected.
- After merging a hotfix PR into main, cherry-pick into dev and test, then push both.

## Before Every Push

Run locally:
```
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run pytest tests/ -q --ignore=tests/ui
```

## Before Merge to Next Branch

Ensure CI on current branch is green.

## Code Rules

- NO comments in source code (no `#`-comments). All notes go in NOTES.md
- No docstrings required
- Coverage minimum: 80%. New features MUST include tests
- Conventional Commits: feat:, fix:, docs:, test:, refactor:, ci:

## Tools

- Package manager: uv (NOT pip, NOT poetry)
- Tests: `uv run pytest tests/ -q` (or `--ignore=tests/ui` without playwright)
- Lint: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
- Type check: `uv run mypy src/`
- Security: `uv run bandit -r src/ -c pyproject.toml`

## Local Docker

For local development and staging:
```
docker compose up dev       # development with hot-reload (port 8501)
docker compose up staging   # staging-like build (port 8502)
```

Do NOT use Docker for cloud deployment — this is a local-only setup.

## CI/CD Levels

| Branch | Workflow | Checks | Time |
|--------|----------|--------|------|
| dev | ci-dev.yml | lint, unit+integration tests, smoke | ~20s |
| test | ci-test.yml | + mypy, 4 platforms, security, performance | ~45s |
| main | ci-main.yml | + 6 platforms, UI/Playwright, system, e2e, build | ~2min |
| main (push) | ci-tag.yml | auto-create git tag on version change | ~5s |
| tag v*.*.* | release.yml | build + GitHub Release | ~1min |

## Project Structure

- `src/duty_schedule/` — main package (models, scheduler, calendar, cli, logging, export/)
- `app.py` — Streamlit UI
- `tests/unit/` — unit tests
- `tests/integration/` — integration tests
- `tests/contract/` — contract tests
- `tests/e2e/` — end-to-end CLI tests
- `tests/system/` — system tests
- `tests/performance/` — benchmarks
- `tests/ui/` — Playwright UI tests (require ci-ui group)
