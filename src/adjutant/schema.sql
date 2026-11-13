CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    declared_at TIMESTAMPTZ NOT NULL,
    declared_by TEXT NOT NULL,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS events (
    seq BIGSERIAL PRIMARY KEY,
    id UUID NOT NULL UNIQUE,
    incident_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    source TEXT NOT NULL,
    valid_at TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL,
    classification TEXT NOT NULL DEFAULT 'internal',
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_events_incident_seq ON events (incident_id, seq);

CREATE TABLE IF NOT EXISTS facts (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    attribute TEXT NOT NULL,
    value JSONB NOT NULL,
    source TEXT NOT NULL,
    valid_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    confidence JSONB NOT NULL,
    status TEXT NOT NULL,
    supersedes UUID,
    classification TEXT NOT NULL,
    trust TEXT NOT NULL DEFAULT 'trusted',
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb
);

ALTER TABLE facts ADD COLUMN IF NOT EXISTS trust TEXT NOT NULL DEFAULT 'trusted';

CREATE INDEX IF NOT EXISTS ix_facts_incident ON facts (incident_id, recorded_at);

CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_excerpt TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    trust TEXT NOT NULL DEFAULT 'untrusted',
    UNIQUE (incident_id, content_hash)
);

CREATE INDEX IF NOT EXISTS ix_signals_incident ON signals (incident_id, recorded_at);

CREATE TABLE IF NOT EXISTS proposals (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    action_id TEXT NOT NULL,
    params JSONB NOT NULL,
    target_asset TEXT NOT NULL,
    tier INT NOT NULL,
    justification_refs JSONB NOT NULL,
    proposed_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_proposals_incident ON proposals (incident_id, created_at);

CREATE TABLE IF NOT EXISTS briefs (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    audience TEXT NOT NULL,
    title TEXT NOT NULL,
    claims JSONB NOT NULL DEFAULT '[]'::jsonb,
    delta_since TIMESTAMPTZ,
    fact_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    classification TEXT NOT NULL DEFAULT 'internal',
    status TEXT NOT NULL DEFAULT 'draft',
    check_status TEXT
);

CREATE INDEX IF NOT EXISTS ix_briefs_incident ON briefs (incident_id, created_at);

CREATE TABLE IF NOT EXISTS brief_checks (
    id UUID PRIMARY KEY,
    brief_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    status TEXT NOT NULL,
    issues JSONB NOT NULL DEFAULT '[]'::jsonb,
    claims_checked INT NOT NULL DEFAULT 0,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL,
    checker TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_brief_checks_brief ON brief_checks (brief_id, checked_at);

CREATE TABLE IF NOT EXISTS brief_approvals (
    id UUID PRIMARY KEY,
    brief_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    approver TEXT NOT NULL,
    approver_role TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    check_id UUID NOT NULL,
    acknowledgment TEXT
);

CREATE INDEX IF NOT EXISTS ix_brief_approvals_brief ON brief_approvals (brief_id, approved_at);

CREATE TABLE IF NOT EXISTS brief_sends (
    id UUID PRIMARY KEY,
    brief_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    channel TEXT NOT NULL,
    destination TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    delivery_id TEXT NOT NULL,
    adapter TEXT NOT NULL,
    requested_by TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_brief_sends_brief ON brief_sends (brief_id, sent_at);

CREATE TABLE IF NOT EXISTS clocks (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    regime TEXT NOT NULL,
    label TEXT NOT NULL,
    trigger_fact_id UUID,
    trigger_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    requires_legal_confirmation BOOLEAN NOT NULL DEFAULT TRUE,
    computation JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_by TEXT,
    confirmed_role TEXT,
    confirmed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_clocks_incident ON clocks (incident_id, due_at);

CREATE TABLE IF NOT EXISTS dispatch_resolutions (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    asset TEXT NOT NULL,
    status TEXT NOT NULL,
    owner TEXT,
    owner_source TEXT,
    contact TEXT,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    resolved_at TIMESTAMPTZ NOT NULL,
    resolver TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_dispatch_resolutions_incident
    ON dispatch_resolutions (incident_id, resolved_at);

CREATE TABLE IF NOT EXISTS dispatch_assignments (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    resolution_id UUID NOT NULL,
    asset TEXT NOT NULL,
    owner TEXT NOT NULL,
    contact TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'primary',
    channel TEXT NOT NULL DEFAULT 'mock',
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_at TIMESTAMPTZ NOT NULL,
    ack_due_at TIMESTAMPTZ NOT NULL,
    sla_minutes INT NOT NULL,
    ack_at TIMESTAMPTZ,
    ack_by TEXT,
    sla_met BOOLEAN,
    escalated_at TIMESTAMPTZ,
    escalated_to TEXT,
    note TEXT
);

CREATE INDEX IF NOT EXISTS ix_dispatch_assignments_incident
    ON dispatch_assignments (incident_id, ack_due_at);

CREATE TABLE IF NOT EXISTS impact_mappings (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    asset TEXT NOT NULL,
    service TEXT,
    criticality TEXT,
    rto_minutes INT,
    rpo_minutes INT,
    rto_deadline TIMESTAMPTZ,
    status TEXT NOT NULL,
    gaps JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    mapped_at TIMESTAMPTZ NOT NULL,
    engine TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_impact_mappings_incident
    ON impact_mappings (incident_id, mapped_at);

CREATE TABLE IF NOT EXISTS readiness_assessments (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    planes JSONB NOT NULL DEFAULT '[]'::jsonb,
    integrations JSONB NOT NULL DEFAULT '[]'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL,
    engine TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_readiness_assessments_incident
    ON readiness_assessments (incident_id, checked_at);

CREATE TABLE IF NOT EXISTS handoffs (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    open_approvals JSONB NOT NULL DEFAULT '[]'::jsonb,
    open_acks JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_gaps JSONB NOT NULL DEFAULT '[]'::jsonb,
    pending_clocks JSONB NOT NULL DEFAULT '[]'::jsonb,
    readiness JSONB NOT NULL DEFAULT '[]'::jsonb,
    checks JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    note TEXT
);

CREATE INDEX IF NOT EXISTS ix_handoffs_incident
    ON handoffs (incident_id, created_at);

CREATE TABLE IF NOT EXISTS policy_decisions (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    decision TEXT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_approvals INT NOT NULL DEFAULT 1,
    allowed_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    action_hash TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    evaluator TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_policy_decisions_incident
    ON policy_decisions (incident_id, evaluated_at);

CREATE INDEX IF NOT EXISTS ix_policy_decisions_proposal
    ON policy_decisions (proposal_id, evaluated_at);

CREATE TABLE IF NOT EXISTS containment_approvals (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    action_id TEXT NOT NULL,
    approver TEXT NOT NULL,
    approver_role TEXT NOT NULL,
    decision TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    nonce TEXT NOT NULL UNIQUE,
    action_hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    key_id TEXT NOT NULL,
    note TEXT
);

CREATE INDEX IF NOT EXISTS ix_containment_approvals_proposal
    ON containment_approvals (proposal_id, decided_at);

CREATE TABLE IF NOT EXISTS action_executions (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    approval_id UUID,
    action_id TEXT NOT NULL,
    target_asset TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT TRUE,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    credential JSONB,
    requested_by TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    executor TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_action_executions_incident
    ON action_executions (incident_id, started_at);

DROP INDEX IF EXISTS ux_action_executions_approval;

CREATE UNIQUE INDEX IF NOT EXISTS ux_action_executions_approval
    ON action_executions (approval_id)
    WHERE approval_id IS NOT NULL AND status = 'simulated';

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    action_id TEXT NOT NULL,
    action_hash TEXT NOT NULL,
    nonce TEXT NOT NULL UNIQUE,
    bundle JSONB NOT NULL,
    topology TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT
);

CREATE INDEX IF NOT EXISTS ix_approval_requests_incident
    ON approval_requests (incident_id, created_at);

CREATE INDEX IF NOT EXISTS ix_approval_requests_proposal
    ON approval_requests (proposal_id, created_at);

CREATE OR REPLACE FUNCTION forbid_event_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS events_append_only ON events;

CREATE TRIGGER events_append_only
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION forbid_event_mutation();
