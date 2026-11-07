# 08 — Continuous operation and daily scheduling

## What exists now

Compose provides a persistent PostgreSQL db service and on-demand jobs: preview, monitor-image, capture-browser, monitor-browser, monitor-dom, replay-export-demo, import-demo, import-gaps-demo, report, test, and migrate-sqlite. monitor-browser --iterations N exits after N frames. The configured DOM worker accepts `--iterations 0` for continuous capture and reconnect attempts, but its placeholder selectors are not a validated source and it has not passed a production soak test.

A production worker still needs measured reconnect/backoff, heartbeat and health status, permitted session handling, verified page freshness, rate limits, retention, graceful shutdown, a clear table owner, and operational metrics. The structured coordinator now has per-table checkpoints and GAP records; a restart cannot recover rounds unseen during downtime.

## Browser loop trial

Use only an authorized page with ROIs calibrated to its viewport. For a technical loop trial:

    docker compose run --rm monitor-browser python -m agent.cli monitor-browser \
      --url https://example.com --width 1280 --height 720 \
      --config config/synthetic_tables.yaml \
      --iterations 60 --interval 5

example.com contains no Baccarat data. Marker readings from it are meaningless as game results. Limit and delete screenshots that contain personal account information.

For a reviewed DOM layout, use the observation-only `monitor-dom` trial in docs/17-source-integration.md. Crop and retain only the permitted table evidence needed for an audit. Do not enable trusted round IDs on the placeholder config.

## Daily report scheduling

On a host whose local clock is Asia/Ho_Chi_Minh, an example cron entry runs at 00:05 and allows Python to select the prior local day:

    5 0 * * * cd /opt/Baccarat_Agent_Implementation_v2 && /usr/bin/docker compose run --rm report python -m agent.cli report >> /var/log/baccarat-report.log 2>&1

Verify the host timezone and Docker path. Cron implementations differ in TZ handling. On a UTC host, 17:05 UTC is 00:05 the next day in Ho Chi Minh City; verify the selected date at the actual job time. A scheduler container is another option. Kubernetes is unnecessary at prototype scale.

Running a report again currently overwrites the same workbook. Automatic email or chat delivery needs report_runs with date, watermark, checksum, generated/sent state, and idempotent retry. This prototype does not send reports.

## Scaling tables

Partition table ownership across workers only after measuring real CPU, RAM, browser contexts, render latency, and coverage. PostgreSQL is the default shared store; use connection limits or pooling after benchmarking, and keep table ownership explicit. A worker needs a heartbeat, backlog, last observation age, and last confirmed age. Stale frames create UNKNOWN/GAP, not inferred rounds.

## Security and resilience

Use a session only where authorized. Keep the PostgreSQL password in untracked .env or a deployment secret store, not committed Compose files; do not publish credentials or cookies in logs. Do not bypass CAPTCHA or anti-bot controls. Save the smallest useful masked evidence, apply retention limits, make pg_dump or physical backups, and test restoration. Benchmark before setting worker resource limits.
