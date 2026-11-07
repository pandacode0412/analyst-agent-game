# Instructions for tests

Test business risks with fixtures separate from production data. Split real labeled captures by session or day so adjacent frames of the same round cannot leak between calibration and held-out sets. Synthetic images do not establish real-source accuracy.

Pipeline or adapter changes should cover repeated frames, two stable RESULT frames, conflicting results, missing/reused IDs, Tie overlays, shoe reset, stale/logout states, table reordering, restart, gaps, and the Asia/Ho_Chi_Minh midnight boundary. Assert both database output and UNKNOWN/GAP/conflict reasons.

Run python3 -m unittest discover -s tests -v with dependencies installed. Fourteen PostgreSQL integration tests run only when RUN_PG_TESTS=1 and a server is available; they create and drop isolated schemas. docker compose run --rm test provides that environment. Source-pipeline tests cover replay, evidence, restart, missing tables, and conflicts; real layout accuracy still needs a labeled corpus. Red-window tests must cover crossing 07:00, excluding 21:00, longer runs counted once, source/table changes, Tie, and GAP. If imports or the database connection fail, report the environment limitation clearly. Real-source acceptance criteria are in docs/14-acceptance.md.
