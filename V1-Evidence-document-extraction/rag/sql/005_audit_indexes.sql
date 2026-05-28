CREATE INDEX IF NOT EXISTS audit_events_org_created_cursor_idx
ON audit_events (organization_id, created_at DESC, audit_event_id DESC);

CREATE INDEX IF NOT EXISTS audit_events_org_user_created_cursor_idx
ON audit_events (organization_id, user_id, created_at DESC, audit_event_id DESC);

CREATE INDEX IF NOT EXISTS audit_events_org_case_created_cursor_idx
ON audit_events (organization_id, case_id, created_at DESC, audit_event_id DESC);

CREATE INDEX IF NOT EXISTS audit_events_org_event_created_cursor_idx
ON audit_events (organization_id, event_type, created_at DESC, audit_event_id DESC);

CREATE INDEX IF NOT EXISTS audit_events_org_entity_created_cursor_idx
ON audit_events (organization_id, entity_type, entity_id, created_at DESC, audit_event_id DESC);

CREATE INDEX IF NOT EXISTS audit_events_case_created_cursor_idx
ON audit_events (case_id, created_at DESC, audit_event_id DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('005_audit_indexes', 'Cursor pagination indexes for audit event streams')
ON CONFLICT (version) DO NOTHING;
