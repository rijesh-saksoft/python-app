# FDE service template

This is the starting point for every trainee repository. It already has the layout, tooling,
container files and checks that the Technical Playbook asks for, so you spend your time on
the service, not on set-up.

## Quick start (five commands)

```bash
uv lock && uv sync           # write uv.lock (commit it), then install exactly what it says
uv run pytest                # run the tests
uv run ruff check            # lint
uv run ruff format --check   # formatting
uv run uvicorn app.main:app --reload   # run the service, then open http://127.0.0.1:8000/docs
```

The template ships without `uv.lock` on purpose: `uv lock` picks the current stable release of every
library on the day you start. Commit `uv.lock` in your first pull request. The `Dockerfile` and the CI
workflow install from it (`--locked`), so both fail until it is committed.

## Before you start
1. Replace every `<PLACEHOLDER>` you will use. `starter_kit/PLACEHOLDERS.md` names the official page
   for each one: use the current stable release and pin it.
2. Copy the env files: `cp .env.example .env` and `cp app.env.example app.env`, then fill them in.
   Never commit them.
3. Rename the project in `pyproject.toml` and change the one-sentence description.

## What is where

| Path | What it holds |
|---|---|
| `app/main.py` | Builds the FastAPI app; request IDs and one error format |
| `app/config.py` | The only place that reads configuration |
| `app/logging_config.py` | JSON logging with the request ID |
| `app/routers/` | Thin HTTP routes (`/health`, `/health/ready`, `/ask`) |
| `app/services/` | The logic (start here for the assistant) |
| `app/models/` | Pydantic data shapes |
| `tests/` | pytest tests |
| `sql/schema.sql` | The one definition of the database |
| `Dockerfile`, `docker-compose.yml`, `Caddyfile` | Run it in containers behind HTTPS |
| `.github/` | CI workflow (checks, secret scan, image build), pull request template, code owners |
| `.gitattributes` | Stores every text file with LF line endings, so Windows and Linux tools agree |
| `docs/` | The document set to fill in by day 19 |
| `AGENTS.md`, `CLAUDE.md` | Rules that AI coding tools read |

## Configuration

Every setting is explained in `app.env.example` (name, meaning, example). The app reads them
only through `app/config.py`.

## Run the stack in containers

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

## Documents

See `docs/`. Fill each one in; run every command you write in a clean checkout.
