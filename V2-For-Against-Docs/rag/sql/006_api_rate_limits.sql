CREATE TABLE IF NOT EXISTS api_rate_limits (
    rate_limit_id BIGSERIAL PRIMARY KEY,
    organization_id TEXT REFERENCES organizations(organization_id) ON DELETE SET NULL,
    user_id TEXT NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    route_key TEXT NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    window_seconds INTEGER NOT NULL CHECK (window_seconds > 0),
    request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    last_request_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS api_rate_limits_user_route_window_uidx
ON api_rate_limits (user_id, route_key, window_started_at);

CREATE INDEX IF NOT EXISTS api_rate_limits_org_route_window_idx
ON api_rate_limits (organization_id, route_key, window_started_at DESC);

CREATE INDEX IF NOT EXISTS api_rate_limits_last_request_idx
ON api_rate_limits (last_request_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('006_api_rate_limits', 'Database-backed fixed-window rate limits for expensive API routes')
ON CONFLICT (version) DO NOTHING;
