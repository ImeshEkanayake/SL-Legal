CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS organizations (
    organization_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_users (
    user_id TEXT PRIMARY KEY,
    organization_id TEXT REFERENCES organizations(organization_id) ON DELETE SET NULL,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'lawyer',
    status TEXT NOT NULL DEFAULT 'active',
    external_auth_subject TEXT,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS organization_memberships (
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, user_id)
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS projects_org_idx ON projects(organization_id, status);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
    case_number TEXT,
    title TEXT NOT NULL,
    short_title TEXT,
    jurisdiction TEXT,
    court TEXT,
    matter_type TEXT,
    procedural_posture TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    confidentiality_level TEXT NOT NULL DEFAULT 'confidential',
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    created_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cases_org_status_idx ON cases(organization_id, status);
CREATE INDEX IF NOT EXISTS cases_project_idx ON cases(project_id);
CREATE INDEX IF NOT EXISTS cases_title_trgm_idx ON cases USING gin(title gin_trgm_ops);

CREATE TABLE IF NOT EXISTS case_permissions (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    granted_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, user_id)
);

CREATE TABLE IF NOT EXISTS case_parties (
    party_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    party_name TEXT NOT NULL,
    party_role TEXT NOT NULL,
    represented_by TEXT,
    contact_summary TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS case_parties_case_idx ON case_parties(case_id);

CREATE TABLE IF NOT EXISTS case_documents (
    case_document_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    document_role TEXT NOT NULL,
    document_kind TEXT,
    uploaded_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    local_path TEXT,
    source_url TEXT,
    file_hash TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    privilege_status TEXT NOT NULL DEFAULT 'unknown',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS case_documents_case_idx ON case_documents(case_id, document_role);
CREATE INDEX IF NOT EXISTS case_documents_document_idx ON case_documents(document_id);

CREATE TABLE IF NOT EXISTS case_raw_inputs (
    raw_input_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    input_type TEXT NOT NULL,
    content TEXT NOT NULL,
    submitted_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    source_case_document_id TEXT REFERENCES case_documents(case_document_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case_facts (
    fact_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    raw_input_id TEXT REFERENCES case_raw_inputs(raw_input_id) ON DELETE SET NULL,
    fact_text TEXT NOT NULL,
    fact_category TEXT NOT NULL,
    certainty_label TEXT NOT NULL,
    materiality TEXT NOT NULL DEFAULT 'unknown',
    disputed_status TEXT NOT NULL DEFAULT 'unknown',
    source_span_start INTEGER,
    source_span_end INTEGER,
    source_quote TEXT,
    extracted_by_agent_run_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (certainty_label IN ('explicitly_stated', 'inferred', 'ambiguous', 'missing', 'contradictory'))
);

CREATE INDEX IF NOT EXISTS case_facts_case_idx ON case_facts(case_id, fact_category);
CREATE INDEX IF NOT EXISTS case_facts_text_trgm_idx ON case_facts USING gin(fact_text gin_trgm_ops);

CREATE TABLE IF NOT EXISTS case_fact_sources (
    fact_source_id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL REFERENCES case_facts(fact_id) ON DELETE CASCADE,
    case_document_id TEXT REFERENCES case_documents(case_document_id) ON DELETE SET NULL,
    document_id TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    page_id TEXT REFERENCES pages(page_id) ON DELETE SET NULL,
    chunk_id TEXT REFERENCES retrieval_chunks(chunk_id) ON DELETE SET NULL,
    page_number INTEGER,
    source_span_start INTEGER,
    source_span_end INTEGER,
    source_quote TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case_timeline_events (
    timeline_event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    event_date DATE,
    date_label TEXT,
    event_text TEXT NOT NULL,
    certainty_label TEXT NOT NULL DEFAULT 'explicitly_stated',
    source_fact_id TEXT REFERENCES case_facts(fact_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS case_timeline_case_date_idx ON case_timeline_events(case_id, event_date);

CREATE TABLE IF NOT EXISTS case_issues (
    issue_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    issue_text TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    priority TEXT NOT NULL DEFAULT 'normal',
    inferred_reason TEXT,
    created_by_agent_run_id TEXT,
    approved_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS case_issues_case_idx ON case_issues(case_id, status);

CREATE TABLE IF NOT EXISTS case_evidence_items (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    description TEXT,
    case_document_id TEXT REFERENCES case_documents(case_document_id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'unreviewed',
    relevance_summary TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS case_evidence_case_idx ON case_evidence_items(case_id, status);

INSERT INTO schema_migrations (version, description)
VALUES ('002_workspace_cases', 'Organizations, projects, cases, MECE facts, issues, evidence, and case document schema')
ON CONFLICT (version) DO NOTHING;
