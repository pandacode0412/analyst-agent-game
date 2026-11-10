# 17 — Structured source integration and live DOM trial

## Current boundary

The source-independent path is implemented: structured capture → `StructuredExportAdapter` → per-table `SourceCoordinator` → conservative phase validator → transactional PostgreSQL round/evidence writer → reports. A configurable DOM reader can populate the same path when an authorized page exposes explicit text fields. The repository still has **no validated adapter for a named Baccarat website**. `config/real_dom.example.yaml` contains placeholder selectors and must not be treated as a working site configuration.

The older `monitor-browser` and `monitor-image` commands remain marker-observation only. `monitor-dom` uses the structured path. Without `--trusted-round-ids`, it cannot confirm a round. With that flag, the operator asserts that the exact page, selectors, ID/reset semantics, phase and result labels, and evidence policy passed the source review in docs/15-source-survey.md and the held-out tests in docs/14-acceptance.md. The flag is a technical gate, not proof of accuracy.

## Try the synthetic structured export

The file `samples/structured_export_demo.jsonl` contains four synthetic captures for one round. It has BETTING, DEALING, and two stable RESULT frames, a shoe ID, a round ID, a final BANKER result, and a changed roadmap revision. Use a disposable database or a separate Compose project:

    docker compose run --rm replay-export-demo

Expected first result: three `OBSERVED` states and one `INSERTED`. Replaying the same file returns duplicate-frame statuses and no new round. This fixture does not establish any website's accuracy. The command-line equivalent is:

    docker compose run --rm replay-export-demo python -m agent.cli replay-export \
      --input samples/structured_export_demo.jsonl \
      --source-id DEMO_STRUCTURED --tables S01 --trusted-round-ids

For a real authorized structured export, leave `--trusted-round-ids` off until the source identity and round semantics are independently validated. Each JSONL line follows the field contract in `samples/STRUCTURED_EXPORT_SCHEMA.md`. Each frame is committed separately, so a later invalid line does not roll back prior valid frames. Use a fresh database for a new source or layout during evaluation.

## Configure an authorized DOM page

1. Complete docs/15-source-survey.md and obtain permission to observe the source at the intended capture rate.
2. Copy `config/real_dom.example.yaml` to a private configuration. Set the real URL, fixed viewport, stable table selectors, visible table label, phase, round ID, shoe ID if IDs reset, final result, and roadmap revision. `root` must uniquely select the intended table. The visible `label` must equal the configured table ID. Set phase/result maps for the source's exact text.
3. Run a short observation-only trial and inspect the cropped table evidence under `output/dom_evidence/`:

    docker compose run --rm monitor-dom python -m agent.cli monitor-dom \
      --config config/my_source_dom.yaml --iterations 30 --interval 5

4. Compare every extracted field against an independently labeled capture corpus. Include Tie, shoe reset, login/error states, table reordering, missing selectors, and page delays. Store the corpus and review decision outside the repository if it contains private data.
5. Only after the source passes the acceptance gate, run with `--trusted-round-ids`. Use `--iterations 0` for an open-ended worker. The worker records missing-table, adapter, out-of-order timestamp, restart, and capture-gap events and fails closed when it cannot establish continuity. It does not detect a frozen page whose content stops changing while captures continue; that check belongs in a source-specific adapter.

The DOM reader only handles fields exposed as accessible text in one page context. Canvas-only content, cross-origin iframes, login/session workflows, and source-specific result behavior need a separate reviewed adapter. There is no generic safe way to infer these from a screenshot or marker count.

## Session lifecycle for a page that requires login

Some authorized sources show tables only to a logged-in account and present a CAPTCHA at login. The agent never solves, bypasses, or outsources a CAPTCHA. The design is "human logs in, agent observes":

1. **Credentials.** The account owner puts `SITE_USERNAME` and `SITE_PASSWORD` in `secrets/site.env`. `secrets/` is ignored by Git and is never mounted into jobs other than `monitor-dom`; do not put site credentials in `.env`, which every Compose job receives and `docker compose config` prints. Programs never print these values.
2. **First login by a human.** The operator logs in once in a visible browser (for example a local noVNC session bound to `127.0.0.1`) and solves any CAPTCHA. The browser session is saved as a Playwright storage state at `secrets/session_state.json`. Treat that file like a password.
3. **Reuse.** `monitor-dom` loads the storage state when the config's `session` block names it, and saves it again after a successful login.
4. **Logged-out detection.** Before each capture the worker checks the configured logged-out signals (the login URL fragment or a visible login form). A logged-out page records `LOGGED_OUT` gaps for every configured table. No round is confirmed from a logged-out or login page.
5. **Automatic re-login, without CAPTCHA only.** At most once per `relogin_backoff_seconds`, the worker fills the configured username and password fields and submits. If the configured CAPTCHA pattern appears, it stops interacting, records `CAPTCHA_REQUIRED` gaps, prints `MANUAL_LOGIN_REQUIRED`, and waits for a human to log in again. If the page stays on the login form, it records `LOGIN_FAILED` gaps. It never retries in a tight loop.
6. **Accounting.** Time spent logged out is a GAP, so strict and tie-transparent runs never continue across it.

Configuration (all fields optional; omit the block for a page without login):

    session:
      storage_state: secrets/session_state.json
      login_url: https://provider.example/login
      logged_out_url_fragment: /login
      username_selector: "input[type=text]"
      password_selector: "input[type=password]"
      captcha_pattern: "请完成安全验证|captcha"
      relogin_backoff_seconds: 600

Only account owners may provide credentials, and only for a source they may observe automatically. The worker performs no deposit, withdrawal, or wagering action.

## Lobby counter reader (`reader: lobby_counters`)

`agent/adapters/lobby_counters.py` reads a multi-table lobby that renders each table as a text card, possibly inside a cross-origin iframe, and implements evidence level B2 in docs/05-round-verification.md. Configuration:

    reader: lobby_counters
    lobby:
      frame_url_contains: /egret/hall      # iframe whose document holds the cards
      card_selector: div.game.isHallGame
      name_selector: .table-name
      countdown_selector: .time
      counter_selector: .bootReport__count # [total, Banker, Player, Tie, ...]
      table_id_pattern: "([A-Z]\\d+)$"     # table ID taken from the visible name
    tables:
      - id: B06

Per table and frame the reader maps the card to the structured contract:

| Card state | Phase | round_id | final_result | revision |
|---|---|---|---|---|
| Countdown visible, counters unchanged | BETTING | total + 1 | null | counters |
| No countdown, counters unchanged since the countdown | DEALING | total + 1 | null | counters |
| total rose by exactly 1 with exactly one of Banker/Player/Tie +1 | RESULT | new total | that side | counters |
| total rose by more than 1, fell, inconsistent delta, unreadable counters | UNKNOWN | — | — | — |

`shoe_id` is a local namespace `<first-seen UTC>` that changes when the total falls or after UNKNOWN, so the existing coordinator, validator, two-frame RESULT rule, and gap handling apply unchanged. A card whose numeric DOM id changes for the same table name is treated as a different table and fails closed. Only cards currently rendered are readable: a virtualized or filtered lobby view (for example a "good road" view whose membership changes) yields a TABLE_MISSING gap for configured tables that are not shown. The coordinator records one TABLE_MISSING gap per continuous absence (not one per frame) and still resets that table's validator on every missing frame. Choose a stable lobby view and list only tables you can keep visible.

The reader saves only a JSON manifest per frame (raw card text plus the mapped table states); it saves no screenshots. The text manifest is the evidence reference for each confirmed round. An 8-minute real trial produced about 1.2 MB of manifests, while screenshots had produced 58 MB and were removed. Trusted round IDs stay off until a held-out comparison against the roadmap passes.

### Automatic table discovery (`tables: auto`)

A lobby whose visible tables change (filtered or virtualized views) cannot be covered by a fixed table list. With `tables: auto`, available only for `reader: lobby_counters`, every card whose visible name matches `table_id_pattern` becomes an observed table the first time it appears. Rules:

- A newly discovered table starts a fresh local shoe namespace and needs a full BETTING → DEALING → RESULT → RESULT cycle; rounds before discovery are never inferred.
- A table that disappears gets one TABLE_MISSING gap per continuous absence. When it reappears it starts a new namespace, so missed rounds stay missed.
- Two cards resolving to the same table ID in one frame are ambiguous; that table is treated as missing for the frame.
- A worker restart still records WORKER_RESTART for every table it has a checkpoint for, when that table is first seen in the new run.

A fixed list remains supported and is preferable when the operator must restrict the report to specific tables.

## Run settings (`run:` block)

Operators can keep every run choice in the source configuration instead of command-line flags:

    run:
      start_at: "07:00"            # optional local time; wait until then before observing
      stop_at: "21:00"             # optional local time; stop observing at this time
      duration_minutes: 60         # optional; stop after this long (the earlier stop wins)
      interval_seconds: 1          # pause between captures
      trusted_round_ids: false     # enable only after the source passed acceptance
      report_on_exit: true         # print and export the reached-13 report when stopping
      report_window: {start: "07:00", end: "21:00"}
      report_dir: output/reports
      login_reminder_seconds: 300  # repeat MANUAL_LOGIN_REQUIRED while blocked

Times use Asia/Ho_Chi_Minh. If `start_at` has already passed today, observation starts at once, unless today's `stop_at` has also passed, in which case it waits for tomorrow's `start_at`. A `stop_at` not later than the start is taken on the following day. A command-line flag, when given, overrides the matching setting. For a quick test, `--start-now` ignores `start_at` and `--duration-minutes N` stops after N minutes (the earlier of that and `stop_at` wins); `--iterations` also remains available, and a run with a stop time and no `--iterations` runs until that time. The exit report covers the local date on which observation started. While a login is required, the worker repeats `MANUAL_LOGIN_REQUIRED reason=<state>` every `login_reminder_seconds`, including the logged-out backoff state.

## Exporting a session from a real browser

When the site rejects logins from an automated browser, the operator logs in with a real Chrome started with a separate profile and a local debug port:

    & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\baccarat-agent-chrome" <login URL>

After login, `tools/export_chrome_session.py` attaches read-only to that browser, and writes the site's cookies and localStorage (Playwright's own export omits localStorage for an attached browser) to `secrets/session_state.json` without printing values. Close that Chrome window when it is not needed: any local program can control it through the debug port.

## Capture interval and missed rounds

The validator needs at least one BETTING frame, one DEALING frame, and two distinct RESULT frames for every round. A full capture iteration (navigation check, DOM read, table crop, database transaction) must therefore take clearly less than the shortest displayed phase; measure it on the target machine and keep the `--interval` well below that phase length. When an iteration is slower and a phase is missed, the round is **not** confirmed: the error costs recall and coverage, never a wrong round. Repeated frames of one phase are expected and harmless.

`tests/test_live_simulation.py` runs the whole path against a local simulated page: login without CAPTCHA, a 16-round sequence with 13 Banker results, the DOM reader, the coordinator, PostgreSQL in an isolated schema, and `report-streaks`. It also checks that a CAPTCHA blocks login and records one `CAPTCHA_REQUIRED` gap. It requires both `RUN_BROWSER_TESTS=1` and `RUN_PG_TESTS=1` and takes about two minutes. It proves the plumbing, not a real website's accuracy.

## Persistence and reporting

Migration 003 adds source-round evidence, idempotent source gaps, processed frame keys, checkpoints, and quarantined conflicts. The writer stores a source-prefixed key in the existing `confirmed_rounds` table so a second source's raw round ID cannot overwrite it. A shoe ID must be included when the source reuses round IDs by shoe. On restart the coordinator records a GAP and requires a new BETTING → DEALING → RESULT cycle. It does not infer rounds missed while stopped.

`source_round_evidence` keeps the two frame IDs and evidence references for confirmed rounds. The 07:00–21:00 red report includes these references when available. Existing reviewed CSV rows may lack them. Observation coverage remains `UNKNOWN` because the project has no independently verified source ledger or measured coverage ratio. The current `observation_gaps` table is keyed only by table, so a database with multiple sources reusing the same table ID is not supported by the red report; it rejects that case. Keep real and synthetic sources in separate databases.

Review the source-specific red-to-outcome mapping before running:

    docker compose run --rm report python -m agent.cli report-red-window \
      --date 2026-10-19 --source DEMO_STRUCTURED --red-outcome BANKER

This fixture has only one round, so its reached-13 count is zero.
