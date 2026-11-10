# 02 — Installation and PostgreSQL demo

## Requirements

Windows 10/11 with Docker Desktop and WSL 2, or Ubuntu with Docker Engine and Compose v2. Check docker --version, docker compose version, and docker info. Allow several GB of disk space for Playwright plus the PostgreSQL volume, and at least 4 GB of free RAM for the demo. The first build needs internet access. No Baccarat account is needed.

Use CPython 3.12.x for a host installation. The Docker application image is Playwright 1.55.0 on Ubuntu 24.04 Noble, and the database image is PostgreSQL 17. Exact Python patch and indirect package versions are not currently locked. The package-by-package inventory and release requirements are in docs/16-dependencies-and-version-policy.md.

Copy .env.example to .env and replace POSTGRES_PASSWORD with a unique password before connecting the database to anything beyond a local demo. .env is ignored by Git. The Compose database port is bound to 127.0.0.1 only.

## PowerShell

    Copy-Item .env.example .env
    docker compose build
    docker compose up -d db
    docker compose run --rm preview
    docker compose run --rm monitor-image
    docker compose run --rm import-demo
    docker compose run --rm import-gaps-demo
    docker compose run --rm replay-export-demo
    docker compose run --rm report
    docker compose run --rm test

Open output\roi_preview.png and output\reports\baccarat_daily_2026-10-19.xlsx.

## Ubuntu or WSL shell

    cp .env.example .env
    docker compose build
    docker compose up -d db
    docker compose run --rm preview
    docker compose run --rm monitor-image
    docker compose run --rm import-demo
    docker compose run --rm import-gaps-demo
    docker compose run --rm replay-export-demo
    docker compose run --rm report
    docker compose run --rm test

The db health check must pass before jobs that need storage start. PostgreSQL data lives in the named pg_data volume; output images and workbooks live under output/ on the host. No SQLite file is created by the new runtime.

## Expected behavior

- preview loads a synthetic six-table image and writes an annotated PNG. R/B labels are marker counts, not round counts.
- monitor-image reads the same image three times and writes 18 observation rows (six tables times three frames). It writes zero confirmed rounds.
- import-demo adds 46 synthetic confirmed rows. A second import reports 46 exact duplicates and inserts zero.
- import-gaps-demo adds one synthetic gap for B07. Run it once because current gap import is not deduplicated.
- report writes five Excel sheets for REPORT_DATE=2026-10-19 from .env. Override the command for another date:

    docker compose run --rm report python -m agent.cli report --date 2026-10-20

- report-red-window writes a separate Excel workbook for verified red-result runs first reaching 13 between 07:00 and 21:00 local time. Confirm the site's red mapping before choosing BANKER or PLAYER:

    docker compose run --rm report python -m agent.cli report-red-window \
      --date 2026-10-19 --source DEMO_FIXTURE --red-outcome BANKER

  This command reads confirmed rounds only. It marks observation coverage UNKNOWN and cannot establish that no rounds were missed.

- replay-export-demo processes four synthetic structured frames and stores one evidence-backed confirmed round on first run. Keep its data separate from real sources.
- test runs 72 tests: seventeen PostgreSQL integration tests in isolated temporary schemas, one Chromium DOM-reader smoke test, three end-to-end simulated-site tests that need both, and fifty-one source-independent tests. The server must be healthy.

Keep synthetic and real data in separate databases or Compose projects.

## Inspect, back up, and reset

Inspect counts without exposing the database to the network:

    docker compose exec db psql -U baccarat -d baccarat -c "SELECT COUNT(*) FROM confirmed_rounds"

Replace the user/database names if you changed POSTGRES_USER or POSTGRES_DB. For backups, use pg_dump and verify a restore; see docs/06-data-model.md. docker compose down leaves the named volume intact. docker compose down -v **deletes the PostgreSQL volume** and is appropriate only for a disposable demo after a verified backup. Do not run it against production data.

## Legacy SQLite import

If you have data/agent.sqlite3 from the old version, back it up and use a fresh empty PostgreSQL database:

    docker compose run --rm migrate-sqlite

The tool takes a consistent read-only snapshot of the SQLite file and imports observations, confirmed rounds, and gaps in one PostgreSQL transaction. It refuses a nonempty target, preventing a partial merge. See docs/06-data-model.md for validation steps.

## Host Python without Docker

Use a Python 3.12 virtual environment, install Python dependencies from requirements.txt, and provide a PostgreSQL 17 server. Set PGHOST, PGPORT, PGDATABASE, PGUSER, and PGPASSWORD, or DATABASE_URL. For the fifteen database integration tests also set RUN_PG_TESTS=1. Set RUN_BROWSER_TESTS=1 only when Playwright Chromium and its system libraries are installed. Without either dependency, those twenty-one tests skip and the other fifty-one still run. Compose is the documented runtime path and enables both integration groups. The current version ranges mean a host install may differ from another install; see docs/16-dependencies-and-version-policy.md before treating it as a reproducible release.

For the structured export and DOM source path, see docs/17-source-integration.md. `config/real_dom.example.yaml` contains placeholder selectors and `https://example.com`; it is not a ready Baccarat source.
