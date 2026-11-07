CREATE INDEX idx_rounds_table_finished_desc
    ON confirmed_rounds (table_id, finished_at_utc DESC, id DESC);

CREATE INDEX idx_gaps_table_detected_desc
    ON observation_gaps (table_id, detected_at_utc DESC, id DESC);
