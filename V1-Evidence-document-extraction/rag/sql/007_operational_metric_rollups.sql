CREATE TABLE IF NOT EXISTS operational_metric_rollups (
    rollup_date DATE NOT NULL,
    metric_name TEXT NOT NULL,
    source TEXT NOT NULL,
    label_hash TEXT NOT NULL,
    labels JSONB NOT NULL DEFAULT '{}'::jsonb,
    metric_value NUMERIC NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (rollup_date, metric_name, source, label_hash)
);

CREATE INDEX IF NOT EXISTS operational_metric_rollups_date_metric_idx
ON operational_metric_rollups (rollup_date DESC, metric_name);

CREATE INDEX IF NOT EXISTS operational_metric_rollups_labels_gin_idx
ON operational_metric_rollups USING GIN (labels);

INSERT INTO schema_migrations (version, description)
VALUES ('007_operational_metric_rollups', 'Daily operational metric rollups for compliance reporting')
ON CONFLICT (version) DO NOTHING;
