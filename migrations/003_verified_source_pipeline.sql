CREATE TABLE source_round_evidence (
    source_id TEXT NOT NULL,
    table_id TEXT NOT NULL,
    source_round_id TEXT NOT NULL,
    stored_round_id TEXT NOT NULL,
    first_frame_id TEXT NOT NULL,
    second_frame_id TEXT NOT NULL,
    first_evidence_ref TEXT NOT NULL,
    second_evidence_ref TEXT NOT NULL,
    time_policy TEXT NOT NULL,
    recorded_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, table_id, source_round_id)
);

CREATE TABLE source_conflicts (
    event_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    table_id TEXT NOT NULL,
    source_round_id TEXT NOT NULL,
    existing_payload JSONB NOT NULL,
    incoming_payload JSONB NOT NULL,
    detected_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    review_status TEXT NOT NULL DEFAULT 'OPEN'
);

CREATE TABLE source_gaps (
    source_id TEXT NOT NULL,
    table_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    detected_at_utc TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (source_id, table_id, event_key)
);

CREATE TABLE processed_source_frames (
    source_id TEXT NOT NULL,
    table_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    captured_at_utc TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, table_id, frame_id)
);

CREATE TABLE worker_checkpoints (
    source_id TEXT NOT NULL,
    table_id TEXT NOT NULL,
    last_frame_id TEXT NOT NULL,
    last_captured_at_utc TIMESTAMPTZ NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, table_id)
);

CREATE INDEX idx_source_gaps_time ON source_gaps (detected_at_utc, source_id, table_id);
