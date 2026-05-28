CREATE TABLE IF NOT EXISTS chat_threads (
    thread_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_threads_case_idx ON chat_threads(case_id, status);
CREATE INDEX IF NOT EXISTS chat_threads_org_idx ON chat_threads(organization_id, status);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES chat_threads(thread_id) ON DELETE CASCADE,
    parent_message_id TEXT REFERENCES chat_messages(message_id) ON DELETE SET NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete',
    token_count INTEGER,
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (role IN ('system', 'user', 'assistant', 'tool', 'reviewer'))
);

CREATE INDEX IF NOT EXISTS chat_messages_thread_idx ON chat_messages(thread_id, created_at);

CREATE TABLE IF NOT EXISTS agent_runs (
    agent_run_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,
    thread_id TEXT REFERENCES chat_threads(thread_id) ON DELETE SET NULL,
    agent_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    model TEXT,
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_runs_case_idx ON agent_runs(case_id, agent_type, status);
CREATE INDEX IF NOT EXISTS agent_runs_thread_idx ON agent_runs(thread_id, created_at);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'case_facts_agent_run_fk'
    ) THEN
        ALTER TABLE case_facts
            ADD CONSTRAINT case_facts_agent_run_fk
            FOREIGN KEY (extracted_by_agent_run_id)
            REFERENCES agent_runs(agent_run_id)
            ON DELETE SET NULL
            NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'case_issues_agent_run_fk'
    ) THEN
        ALTER TABLE case_issues
            ADD CONSTRAINT case_issues_agent_run_fk
            FOREIGN KEY (created_by_agent_run_id)
            REFERENCES agent_runs(agent_run_id)
            ON DELETE SET NULL
            NOT VALID;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS agent_steps (
    agent_step_id TEXT PRIMARY KEY,
    agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    step_type TEXT NOT NULL,
    title TEXT NOT NULL,
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'complete',
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_run_id, step_index)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    agent_run_id TEXT REFERENCES agent_runs(agent_run_id) ON DELETE CASCADE,
    message_id TEXT REFERENCES chat_messages(message_id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'complete',
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS tool_calls_agent_idx ON tool_calls(agent_run_id, started_at);

CREATE TABLE IF NOT EXISTS case_research_packs (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    pack_id TEXT NOT NULL REFERENCES research_packs(pack_id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by_agent_run_id TEXT REFERENCES agent_runs(agent_run_id) ON DELETE SET NULL,
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, pack_id)
);

ALTER TABLE research_packs
    ADD COLUMN IF NOT EXISTS case_id TEXT REFERENCES cases(case_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS source_thread_id TEXT REFERENCES chat_threads(thread_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS source_agent_run_id TEXT REFERENCES agent_runs(agent_run_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS token_budget INTEGER,
    ADD COLUMN IF NOT EXISTS pack_hash TEXT;

ALTER TABLE research_pack_items
    ADD COLUMN IF NOT EXISTS reranker_score NUMERIC(12,6),
    ADD COLUMN IF NOT EXISTS authority_score NUMERIC(12,6),
    ADD COLUMN IF NOT EXISTS source_quality_flags TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS selected_text TEXT,
    ADD COLUMN IF NOT EXISTS page_start INTEGER,
    ADD COLUMN IF NOT EXISTS page_end INTEGER;

CREATE TABLE IF NOT EXISTS legal_claims (
    claim_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    thread_id TEXT REFERENCES chat_threads(thread_id) ON DELETE SET NULL,
    message_id TEXT REFERENCES chat_messages(message_id) ON DELETE SET NULL,
    pack_id TEXT REFERENCES research_packs(pack_id) ON DELETE SET NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    support_status TEXT NOT NULL DEFAULT 'unverified',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    created_by_agent_run_id TEXT REFERENCES agent_runs(agent_run_id) ON DELETE SET NULL,
    reviewed_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS legal_claims_case_idx ON legal_claims(case_id, support_status);

CREATE TABLE IF NOT EXISTS legal_claim_citations (
    claim_id TEXT NOT NULL REFERENCES legal_claims(claim_id) ON DELETE CASCADE,
    pack_item_id TEXT NOT NULL REFERENCES research_pack_items(pack_item_id) ON DELETE CASCADE,
    citation_role TEXT NOT NULL DEFAULT 'support',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (claim_id, pack_item_id, citation_role)
);

CREATE TABLE IF NOT EXISTS document_annotations (
    annotation_id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,
    case_document_id TEXT REFERENCES case_documents(case_document_id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(document_id) ON DELETE CASCADE,
    page_number INTEGER,
    annotation_type TEXT NOT NULL,
    quote TEXT,
    note TEXT,
    coordinates JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS document_annotations_case_idx ON document_annotations(case_id, page_number);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    thread_id TEXT REFERENCES chat_threads(thread_id) ON DELETE SET NULL,
    pack_id TEXT REFERENCES research_packs(pack_id) ON DELETE SET NULL,
    draft_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    version INTEGER NOT NULL DEFAULT 1,
    created_by_agent_run_id TEXT REFERENCES agent_runs(agent_run_id) ON DELETE SET NULL,
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS drafts_case_idx ON drafts(case_id, draft_type, status);

CREATE TABLE IF NOT EXISTS review_items (
    review_item_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    item_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'normal',
    assigned_to_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    reviewed_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    decision TEXT,
    comment TEXT,
    due_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS review_items_case_status_idx ON review_items(case_id, status, priority);

CREATE TABLE IF NOT EXISTS app_tasks (
    task_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'normal',
    assigned_to_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    due_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS app_tasks_case_idx ON app_tasks(case_id, status, priority);

CREATE TABLE IF NOT EXISTS background_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    queue_name TEXT NOT NULL DEFAULT 'default',
    priority INTEGER NOT NULL DEFAULT 100,
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS background_jobs_queue_idx ON background_jobs(queue_name, status, priority, run_after);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_event_id BIGSERIAL PRIMARY KEY,
    organization_id TEXT REFERENCES organizations(organization_id) ON DELETE SET NULL,
    case_id TEXT REFERENCES cases(case_id) ON DELETE SET NULL,
    user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    before_state JSONB,
    after_state JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_events_case_idx ON audit_events(case_id, created_at);
CREATE INDEX IF NOT EXISTS audit_events_entity_idx ON audit_events(entity_type, entity_id);

INSERT INTO schema_migrations (version, description)
VALUES ('003_chat_agents_review', 'Chat, agents, research-pack links, claims, annotations, drafts, review, jobs, and audit schema')
ON CONFLICT (version) DO NOTHING;
