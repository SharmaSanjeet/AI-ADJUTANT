export type Severity = "sev1" | "sev2" | "sev3" | "sev4";
export type IncidentStatus = "declared" | "contained" | "resolved" | "closed";
export type FactStatus =
  | "asserted"
  | "corroborated"
  | "disputed"
  | "retracted"
  | "superseded";
export type FactTrust = "trusted" | "untrusted" | "mixed";

export interface Incident {
  id: string;
  title: string;
  severity: Severity;
  status: IncidentStatus;
  declared_at: string;
  declared_by: string;
  summary: string | null;
}

export interface Confidence {
  source_reliability: number;
  corroboration: number;
  extraction_certainty: number;
}

export interface Evidence {
  ref: string;
  kind: string;
  content_hash: string;
  excerpt: string | null;
}

export interface Fact {
  id: string;
  incident_id: string;
  attribute: string;
  value: unknown;
  source: string;
  valid_at: string;
  recorded_at: string;
  confidence: Confidence;
  status: FactStatus;
  supersedes: string | null;
  classification: string;
  trust: FactTrust;
  evidence: Evidence[];
}

export interface Signal {
  id: string;
  incident_id: string;
  kind: string;
  source: string;
  content_hash: string;
  content_excerpt: string;
  observed_at: string;
  recorded_at: string;
  trust: string;
}

export interface Proposal {
  id: string;
  incident_id: string;
  action_id: string;
  params: Record<string, unknown>;
  target_asset: string;
  tier: number;
  justification_refs: string[];
  proposed_by: string;
  created_at: string;
}

export interface EventEnvelope {
  seq: number;
  id: string;
  incident_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  source: string;
  valid_at: string | null;
  recorded_at: string;
  classification: string;
  prev_hash: string;
  hash: string;
}

export interface Audit {
  valid: boolean;
  entries: number;
  head_hash: string;
  first_broken_seq: number | null;
  reason: string | null;
}

export type BriefAudience = "ic" | "exec" | "technical" | "legal";
export type ClaimKind = "fact" | "judgment";
export type BriefStatus = "draft" | "approved" | "sent_mock";
export type CheckStatus = "passed" | "needs_review" | "failed";
export type ClockStatus = "candidate" | "confirmed";

export interface BriefClaim {
  id: string;
  kind: ClaimKind;
  text: string;
  fact_ids: string[];
  evidence_refs: string[];
}

export interface CheckIssue {
  code: string;
  claim_id: string | null;
  detail: string;
}

export interface BriefCheck {
  id: string;
  brief_id: string;
  incident_id: string;
  status: CheckStatus;
  issues: CheckIssue[];
  claims_checked: number;
  evidence: Evidence[];
  checked_at: string;
  checker: string;
}

export interface BriefApproval {
  id: string;
  brief_id: string;
  incident_id: string;
  approver: string;
  approver_role: string;
  approved_at: string;
  expires_at: string;
  check_id: string;
  acknowledgment: string | null;
}

export interface BriefSend {
  id: string;
  brief_id: string;
  incident_id: string;
  channel: "mock";
  destination: string;
  sent_at: string;
  delivery_id: string;
  adapter: "mock";
  requested_by: string;
}

export interface BriefDraft {
  id: string;
  incident_id: string;
  audience: BriefAudience;
  title: string;
  claims: BriefClaim[];
  delta_since: string | null;
  fact_ids: string[];
  generated_by: string;
  created_at: string;
  classification: string;
  status: BriefStatus;
  check_status: CheckStatus | null;
}

export interface BriefRecord {
  brief: BriefDraft;
  check: BriefCheck | null;
  approval: BriefApproval | null;
  send: BriefSend | null;
}

export interface ClockComputation {
  id: string;
  regime: string;
  label: string;
  trigger_at: string;
  due_at: string;
  duration: string;
  calendar: "calendar" | "business";
  timezone: string | null;
  holidays: string[];
  steps: string[];
  computed_at: string;
  engine: string;
}

export interface ClockCandidate {
  id: string;
  incident_id: string;
  regime: string;
  label: string;
  trigger_fact_id: string | null;
  trigger_at: string;
  due_at: string;
  status: ClockStatus;
  requires_legal_confirmation: boolean;
  computation: ClockComputation;
  created_at: string;
  confirmed_by: string | null;
  confirmed_role: string | null;
  confirmed_at: string | null;
}

export type DispatchStatus = "pending" | "acked" | "escalated" | "closed";
export type ResolutionStatus = "resolved" | "unknown_owner" | "ambiguous";

export interface OwnerCandidate {
  source: string;
  owner: string;
  contact: string;
  confidence: number;
  fact_id: string | null;
  evidence_refs: string[];
  note: string | null;
}

export interface ResolutionStep {
  source: string;
  attribute: string;
  outcome: "used" | "missing" | "rejected";
  detail: string;
  fact_id: string | null;
}

export interface OwnerResolution {
  id: string;
  incident_id: string;
  asset: string;
  status: ResolutionStatus;
  owner: string | null;
  owner_source: string | null;
  contact: string | null;
  confidence: number;
  candidates: OwnerCandidate[];
  steps: ResolutionStep[];
  resolved_at: string;
  resolver: string;
}

export interface DispatchAssignment {
  id: string;
  incident_id: string;
  resolution_id: string;
  asset: string;
  owner: string;
  contact: string;
  role: "primary" | "escalation";
  channel: "mock";
  status: DispatchStatus;
  assigned_at: string;
  ack_due_at: string;
  sla_minutes: number;
  ack_at: string | null;
  ack_by: string | null;
  sla_met: boolean | null;
  escalated_at: string | null;
  escalated_to: string | null;
  note: string | null;
}

export interface DispatchRecord {
  resolution: OwnerResolution;
  assignment: DispatchAssignment | null;
}

export interface ImpactMapping {
  id: string;
  incident_id: string;
  asset: string;
  service: string | null;
  criticality: string | null;
  rto_minutes: number | null;
  rpo_minutes: number | null;
  rto_deadline: string | null;
  status: "mapped" | "partial" | "unknown";
  gaps: string[];
  evidence_refs: string[];
  mapped_at: string;
  engine: string;
}

export interface ReadinessCheck {
  name: string;
  outcome: "pass" | "fail" | "unknown";
  detail: string;
  evidence_refs: string[];
}

export interface DrPlane {
  plane: string;
  status: "healthy" | "degraded" | "compromised" | "unknown";
  checks: ReadinessCheck[];
}

export interface IntegrationHealth {
  integration: string;
  status: "operational" | "degraded" | "down" | "unknown";
  mode: "normal" | "read_only" | "manual";
  detail: string;
  evidence_refs: string[];
}

export interface ReadinessAssessment {
  id: string;
  incident_id: string;
  planes: DrPlane[];
  integrations: IntegrationHealth[];
  checked_at: string;
  engine: string;
}

export interface HandoffItem {
  key: string;
  label: string;
  status: string;
  ref: string | null;
}

export interface HandoffBrief {
  id: string;
  incident_id: string;
  title: string;
  summary: string;
  open_approvals: HandoffItem[];
  open_acks: HandoffItem[];
  evidence_gaps: HandoffItem[];
  pending_clocks: HandoffItem[];
  readiness: HandoffItem[];
  checks: string[];
  generated_by: string;
  created_at: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  note: string | null;
}

export type PolicyOutcome = "allow" | "deny" | "escalate";

export interface ActionCatalogEntry {
  action_id: string;
  title: string;
  description: string;
  tier: number;
  blast_radius: string;
  rollback: string[];
  evidence_preservation: string[];
  preconditions: string[];
  requires_approval: boolean;
  never_automate: boolean;
  business_hours_only: boolean;
  write_scope: string;
  catalog_version: string;
}

export interface PolicyDecision {
  id: string;
  incident_id: string;
  proposal_id: string;
  decision: PolicyOutcome;
  reasons: string[];
  required_approvals: number;
  allowed_roles: string[];
  action_hash: string;
  policy_version: string;
  evaluated_at: string;
  evaluator: string;
}

export interface Approval {
  id: string;
  incident_id: string;
  proposal_id: string;
  action_id: string;
  approver: string;
  approver_role: string;
  decision: "approved";
  decided_at: string;
  expires_at: string;
  nonce: string;
  action_hash: string;
  signature: string;
  key_id: string;
  note: string | null;
}

export interface ExecutionStep {
  name: string;
  status: "simulated" | "refused" | "planned";
  detail: string;
}

export interface CredentialGrant {
  scope: string;
  ttl_seconds: number;
  broker: string;
  purpose: string;
  note: string;
}

export interface ExecutionResult {
  id: string;
  incident_id: string;
  proposal_id: string;
  approval_id: string | null;
  action_id: string;
  target_asset: string;
  status: "simulated" | "refused";
  dry_run: boolean;
  steps: ExecutionStep[];
  reasons: string[];
  credential: CredentialGrant | null;
  requested_by: string;
  started_at: string;
  finished_at: string;
  executor: string;
}

export interface ContainmentRecord {
  proposal: Proposal;
  catalog: ActionCatalogEntry | null;
  decision: PolicyDecision | null;
  approval: Approval | null;
  execution: ExecutionResult | null;
  approval_spent: boolean;
}

export type AutonomyLevel = "shadow" | "suggest" | "approve";

export interface ActionWindowStats {
  action_id: string;
  window_start: string;
  window_end: string;
  proposals: number;
  allows: number;
  denies: number;
  escalates: number;
  approvals: number;
  approvals_expired: number;
  approvals_consumed: number;
  simulated: number;
  refusals: number;
  breaker_trips: number;
}

export interface AutonomyRecommendation {
  action_id: string;
  current_level: AutonomyLevel;
  eligible_for_promotion: boolean;
  promotion_reasons: string[];
  hold_reasons: string[];
  demotion_reasons: string[];
  demotion_target: AutonomyLevel | null;
  thresholds_version: string;
  computed_at: string;
  engine: string;
}

export interface Scorecard {
  action_id: string;
  catalog: ActionCatalogEntry | null;
  stats: ActionWindowStats;
  recommendation: AutonomyRecommendation;
  level: AutonomyLevel;
  level_set_by: string | null;
  level_set_at: string | null;
  computed_at: string;
  engine: string;
}

export interface KillSwitchState {
  engaged: boolean;
  engaged_by: string | null;
  engaged_at: string | null;
  reason: string | null;
  released_by: string | null;
  released_at: string | null;
  source: "database" | "environment";
}

export interface BreakerState {
  action_id: string;
  tripped: boolean;
  tripped_at: string | null;
  reason: string | null;
  consecutive_refusals: number;
  reset_at: string | null;
  reset_by: string | null;
}

export interface RateLimitState {
  action_id: string;
  window_seconds: number;
  max_per_window: number;
  used_in_window: number;
}

export interface AutomationStatus {
  kill_switch: KillSwitchState;
  breakers: BreakerState[];
  rate_limits: RateLimitState[];
  config_profile: string;
  approval_channel: "in-band" | "out-of-band";
  oob_topology: string;
  autonomy_version: string;
  thresholds_version: string;
  promotion_enabled: boolean;
  checked_at: string;
}

export interface ApprovalRequest {
  id: string;
  incident_id: string;
  proposal_id: string;
  action_id: string;
  action_hash: string;
  nonce: string;
  bundle: Record<string, unknown>;
  topology: string;
  status: "pending" | "approved" | "expired";
  created_at: string;
  expires_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface OobSignResult {
  bundle_id: string;
  signature: string;
  key_id: string;
  note: string;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function getOptional<T>(path: string): Promise<T | null> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function post<T>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") {
      return `${response.status} · ${data.detail}`;
    }
  } catch {
    // Non-JSON error body falls through to the status text.
  }
  return `${response.status} ${response.statusText}`;
}

export const api = {
  incidents: () => get<Incident[]>("/incidents"),
  timeline: (id: string) => get<EventEnvelope[]>(`/incidents/${id}/timeline`),
  facts: (id: string) =>
    get<Fact[]>(`/incidents/${id}/facts?include_history=true`),
  decisions: (id: string) => get<Fact[]>(`/incidents/${id}/decisions`),
  proposals: (id: string) => get<Proposal[]>(`/incidents/${id}/proposals`),
  signals: (id: string) => get<Signal[]>(`/incidents/${id}/signals`),
  briefs: (id: string) => get<BriefRecord[]>(`/incidents/${id}/briefs`),
  clocks: (id: string) => get<ClockCandidate[]>(`/incidents/${id}/clocks`),
  audit: () => get<Audit>("/audit/verify"),
  createBrief: (id: string, audience: BriefAudience) =>
    post<BriefRecord>(`/incidents/${id}/briefs`, { audience }),
  checkBrief: (id: string, briefId: string) =>
    post<BriefCheck>(`/incidents/${id}/briefs/${briefId}/check`),
  approveBrief: (
    id: string,
    briefId: string,
    body: {
      approver: string;
      approver_role: string;
      review_acknowledged: boolean;
      note?: string;
    },
  ) => post<BriefRecord>(`/incidents/${id}/briefs/${briefId}/approve`, body),
  sendBriefMock: (id: string, briefId: string, requestedBy: string) =>
    post<BriefRecord>(`/incidents/${id}/briefs/${briefId}/send`, {
      requested_by: requestedBy,
    }),
  confirmClock: (
    id: string,
    clockId: string,
    body: { confirmed_by: string; role: string; attestation: boolean; note?: string },
  ) => post<ClockCandidate>(`/incidents/${id}/clocks/${clockId}/confirm`, body),
  dispatch: (id: string) =>
    get<DispatchRecord[]>(`/incidents/${id}/dispatch`),
  resolveDispatch: (id: string, asset: string) =>
    post<DispatchRecord>(`/incidents/${id}/dispatch/resolve`, { asset }),
  ackDispatch: (id: string, assignmentId: string, ackedBy: string) =>
    post<DispatchRecord>(
      `/incidents/${id}/dispatch/${assignmentId}/ack`,
      { acked_by: ackedBy },
    ),
  evaluateDispatch: (id: string) =>
    post<DispatchRecord[]>(`/incidents/${id}/dispatch/evaluate`),
  impacts: (id: string) => get<ImpactMapping[]>(`/incidents/${id}/impact`),
  mapImpact: (id: string) =>
    post<ImpactMapping[]>(`/incidents/${id}/impact`),
  readiness: (id: string) =>
    getOptional<ReadinessAssessment>(`/incidents/${id}/readiness`),
  assessReadiness: (id: string) =>
    post<ReadinessAssessment>(`/incidents/${id}/readiness`),
  handoff: (id: string) => getOptional<HandoffBrief>(`/incidents/${id}/handoff`),
  createHandoff: (id: string) => post<HandoffBrief>(`/incidents/${id}/handoff`),
  acknowledgeHandoff: (id: string, handoffId: string, acknowledgedBy: string) =>
    post<HandoffBrief>(
      `/incidents/${id}/handoff/${handoffId}/acknowledge`,
      { acknowledged_by: acknowledgedBy },
    ),
  containment: (id: string) =>
    get<ContainmentRecord[]>(`/incidents/${id}/containment`),
  actions: (id: string) =>
    get<ActionCatalogEntry[]>(`/incidents/${id}/actions`),
  evaluateProposal: (id: string, proposalId: string) =>
    post<PolicyDecision>(
      `/incidents/${id}/proposals/${proposalId}/evaluate`,
    ),
  approveProposal: (
    id: string,
    proposalId: string,
    body: { approver: string; approver_role: string; note?: string },
  ) => post<Approval>(`/incidents/${id}/proposals/${proposalId}/approve`, body),
  executeProposal: (
    id: string,
    proposalId: string,
    requestedBy: string,
    dryRun = true,
  ) =>
    post<ExecutionResult>(`/incidents/${id}/proposals/${proposalId}/execute`, {
      requested_by: requestedBy,
      dry_run: dryRun,
    }),
  automationStatus: () => get<AutomationStatus>("/automation/status"),
  scorecards: () => get<Scorecard[]>("/automation/scorecards"),
  setKillSwitch: (body: { engaged: boolean; actor: string; reason: string }) =>
    post<KillSwitchState>("/automation/kill-switch", body),
  resetBreaker: (actionId: string, body: { actor: string; note?: string }) =>
    post<BreakerState>(`/automation/breakers/${actionId}/reset`, body),
  setAutonomyLevel: (
    actionId: string,
    body: { level: AutonomyLevel; actor: string; reason: string },
  ) => post<Record<string, unknown>>(`/automation/levels/${actionId}`, body),
  createApprovalRequest: (id: string, proposalId: string) =>
    post<ApprovalRequest>(
      `/incidents/${id}/proposals/${proposalId}/approval-request`,
    ),
  mockOobSign: (bundleId: string) =>
    post<OobSignResult>("/automation/mock-oob-sign", { bundle_id: bundleId }),
  approveOob: (
    id: string,
    proposalId: string,
    body: {
      bundle_id: string;
      approver: string;
      approver_role: string;
      attestation_signature: string;
      note?: string;
    },
  ) => post<Approval>(`/incidents/${id}/proposals/${proposalId}/approve-oob`, body),
};

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function shortId(id: string | null): string {
  return id ? id.slice(0, 8) : "—";
}

export function renderValue(value: unknown, max = 260): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") {
    return value.length > max ? `${value.slice(0, max)}…` : value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    const text = JSON.stringify(value);
    return text.length > max ? `${text.slice(0, max)}…` : text;
  } catch {
    return String(value);
  }
}
