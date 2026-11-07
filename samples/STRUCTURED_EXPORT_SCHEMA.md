# Structured export JSONL contract

One UTF-8 JSON object per line represents one captured source state. This is an input contract for an authorized export or a labeled replay, not a website scraper. The example in `structured_export_demo.jsonl` is synthetic.

| Field | Rule |
|---|---|
| `source_id` | Stable source name; must match the CLI `--source-id` |
| `frame_id` | Unique capture ID within the source |
| `captured_at_utc` | Offset-aware ISO-8601 capture time; order must increase per table |
| `evidence_ref` | Retrievable private evidence reference or manifest path |
| `tables` | Array of visible table-state objects; missing configured tables become GAP |
| `tables[].table_id` | Stable visible table identity |
| `tables[].shoe_id` | Required when round IDs reset per shoe; empty only with reviewed `--globally-unique-ids` policy |
| `tables[].round_id` | Published source round ID, never a screenshot hash or local timestamp |
| `tables[].phase` | BETTING, DEALING, RESULT, or UNKNOWN after source-specific mapping |
| `tables[].final_result` | BANKER, PLAYER, TIE, or null; only the published final outcome |
| `tables[].roadmap_revision` | A stable source revision/fingerprint that changes after the round; not a raw marker count |
| `tables[].evidence_ref` | Optional per-table evidence reference; otherwise frame reference plus table ID is used |

The coordinator requires a reviewed source ID rule, BETTING → DEALING → two independent matching RESULT frames, a changed revision, and continuous capture before it writes a confirmed round. The CLI's `--trusted-round-ids` switch enables that reviewed ID rule; do not use it solely because fields exist or OCR is confident. Unknown or missing fields fail closed. The target source's permission, layout, color mapping, timing, and ground truth must be recorded through docs/15-source-survey.md and docs/14-acceptance.md.
