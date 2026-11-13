import { useState, type FormEvent, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BadgeCheck,
  Ban,
  ClipboardCheck,
  Database,
  FileSignature,
  FileText,
  FlaskConical,
  Gavel,
  Gauge,
  GitBranch,
  KeyRound,
  Network,
  Power,
  Radio,
  Send,
  ShieldAlert,
  ShieldCheck,
  Siren,
  Timer,
  UserCheck,
  Users,
  Zap,
} from "lucide-react";

import type {
  ApprovalRequest,
  AutonomyLevel,
  AutomationStatus,
  BriefAudience,
  BriefRecord,
  CheckStatus,
  ClockCandidate,
  Confidence,
  ContainmentRecord,
  DispatchRecord,
  DrPlane,
  EventEnvelope,
  Fact,
  FactStatus,
  FactTrust,
  HandoffBrief,
  HandoffItem,
  ImpactMapping,
  IntegrationHealth,
  Proposal,
  ReadinessAssessment,
  Scorecard,
  Severity,
  Signal,
} from "./api";
import { api, formatTime, renderValue, shortId } from "./api";

export type Tone = "slate" | "cyan" | "amber" | "red" | "green" | "violet";

const toneClasses: Record<Tone, string> = {
  slate: "bg-white/5 text-slate-300 ring-white/10",
  cyan: "bg-cyan-400/10 text-cyan-300 ring-cyan-400/25",
  amber: "bg-amber-400/10 text-amber-300 ring-amber-400/25",
  red: "bg-red-500/10 text-red-300 ring-red-500/25",
  green: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/25",
  violet: "bg-violet-500/10 text-violet-300 ring-violet-500/25",
};

export function Pill({
  children,
  tone = "slate",
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ring-1 ring-inset ${toneClasses[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

const severityTone: Record<Severity, Tone> = {
  sev1: "red",
  sev2: "amber",
  sev3: "cyan",
  sev4: "slate",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Pill tone={severityTone[severity]} className="px-2.5 py-1 text-[11px]">
      {severity.toUpperCase()}
    </Pill>
  );
}

const statusTone: Record<FactStatus, Tone> = {
  asserted: "cyan",
  corroborated: "green",
  disputed: "amber",
  retracted: "red",
  superseded: "slate",
};

export function StatusBadge({ status }: { status: FactStatus }) {
  return <Pill tone={statusTone[status]}>{status}</Pill>;
}

const trustTone: Record<FactTrust, Tone> = {
  trusted: "slate",
  untrusted: "amber",
  mixed: "violet",
};

const trustLabel: Record<FactTrust, string> = {
  trusted: "trusted",
  untrusted: "untrusted-derived",
  mixed: "mixed trust",
};

export function TrustBadge({ trust }: { trust: FactTrust }) {
  return <Pill tone={trustTone[trust]}>{trustLabel[trust]}</Pill>;
}

export function ConfidenceMeter({ confidence }: { confidence: Confidence }) {
  const items = [
    { label: "src", value: confidence.source_reliability },
    { label: "corr", value: Math.min(confidence.corroboration / 3, 1) },
    { label: "ext", value: confidence.extraction_certainty },
  ];

  return (
    <div
      className="flex items-center gap-2"
      title={`source ${confidence.source_reliability.toFixed(2)}, corroboration ${confidence.corroboration}, extraction ${confidence.extraction_certainty.toFixed(2)}`}
    >
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1">
          <span className="text-[9px] uppercase tracking-wider text-slate-500">
            {item.label}
          </span>
          <div className="h-1.5 w-9 overflow-hidden rounded-full bg-white/5">
            <div
              className="h-full rounded-full bg-cyan-400/70"
              style={{ width: `${Math.round(item.value * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function EvidenceChips({ fact }: { fact: Fact }) {
  if (!fact.evidence.length) {
    return <span className="text-[10px] text-slate-600">no evidence refs</span>;
  }

  return (
    <div className="flex flex-wrap gap-1">
      {fact.evidence.map((evidence) => (
        <span
          key={evidence.ref}
          title={evidence.excerpt ?? ""}
          className="rounded border border-white/5 bg-white/[0.03] px-1.5 py-0.5 font-mono text-[9px] text-slate-500"
        >
          {evidence.kind}:{evidence.ref.replace(/^signal:sha256:/, "").slice(0, 10)}
        </span>
      ))}
    </div>
  );
}

function FactDetail({ fact }: { fact: Fact }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-cyan-300">
          {fact.attribute}
        </span>
        <div className="flex items-center gap-1.5">
          <StatusBadge status={fact.status} />
          <TrustBadge trust={fact.trust} />
        </div>
      </div>
      <p className="rounded-lg border border-white/5 bg-black/20 px-3 py-2 text-sm break-words text-slate-300">
        {renderValue(fact.value)}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ConfidenceMeter confidence={fact.confidence} />
        <EvidenceChips fact={fact} />
      </div>
    </div>
  );
}

export function ProposalSummary({ proposal }: { proposal: Proposal }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="red">Advisory only</Pill>
        <span className="font-mono text-xs text-slate-200">
          {proposal.action_id}
        </span>
        <span className="text-xs text-slate-500">→ {proposal.target_asset}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <Pill
          tone={proposal.tier >= 3 ? "red" : proposal.tier === 2 ? "amber" : "cyan"}
        >
          Tier {proposal.tier}
        </Pill>
        <span>{proposal.justification_refs.length} justification refs</span>
        <span>by {proposal.proposed_by}</span>
      </div>
      <pre className="rounded-lg border border-white/5 bg-black/20 p-3 font-mono text-[10px] text-slate-400">
        {JSON.stringify(proposal.params)}
      </pre>
    </div>
  );
}

const eventMeta: Record<
  string,
  { label: string; tone: Tone; icon: LucideIcon }
> = {
  "incident.created": { label: "Incident declared", tone: "cyan", icon: Siren },
  "signal.received": { label: "Signal received", tone: "violet", icon: Radio },
  "fact.appended": { label: "Fact recorded", tone: "slate", icon: Database },
  "fact.status_changed": {
    label: "Fact status changed",
    tone: "amber",
    icon: GitBranch,
  },
  "proposal.created": {
    label: "Action proposed",
    tone: "red",
    icon: ShieldAlert,
  },
  "brief.drafted": { label: "Brief drafted", tone: "violet", icon: FileText },
  "brief.checked": { label: "Brief fact-checked", tone: "cyan", icon: BadgeCheck },
  "brief.approved": { label: "Brief approved", tone: "green", icon: ShieldCheck },
  "brief.send_mocked": { label: "Brief sent (mock)", tone: "amber", icon: Send },
  "clock.candidate_recorded": {
    label: "Regulatory clock proposed",
    tone: "amber",
    icon: Timer,
  },
  "clock.confirmed": { label: "Clock confirmed", tone: "green", icon: Timer },
  "dispatch.resolved": {
    label: "Owner resolved",
    tone: "cyan",
    icon: Users,
  },
  "dispatch.acknowledged": {
    label: "Dispatch acknowledged",
    tone: "green",
    icon: UserCheck,
  },
  "dispatch.escalated": {
    label: "Dispatch escalated",
    tone: "amber",
    icon: ArrowUpRight,
  },
  "impact.mapped": { label: "Impact mapped", tone: "violet", icon: GitBranch },
  "readiness.assessed": {
    label: "Readiness assessed",
    tone: "amber",
    icon: Network,
  },
  "handoff.drafted": {
    label: "Shift handoff drafted",
    tone: "violet",
    icon: ClipboardCheck,
  },
  "handoff.acknowledged": {
    label: "Handoff acknowledged",
    tone: "green",
    icon: UserCheck,
  },
  "policy.decided": { label: "Policy gate decided", tone: "cyan", icon: Gavel },
  "approval.signed": {
    label: "Action approved (signed)",
    tone: "green",
    icon: FileSignature,
  },
  "execution.simulated": {
    label: "Dry-run recorded",
    tone: "cyan",
    icon: FlaskConical,
  },
  "execution.refused": { label: "Execution refused", tone: "red", icon: Ban },
  "automation.kill_switch_engaged": {
    label: "Kill switch engaged",
    tone: "red",
    icon: Power,
  },
  "automation.kill_switch_released": {
    label: "Kill switch released",
    tone: "green",
    icon: Power,
  },
  "automation.breaker_tripped": {
    label: "Circuit breaker tripped",
    tone: "red",
    icon: Zap,
  },
  "automation.breaker_reset": {
    label: "Circuit breaker reset",
    tone: "green",
    icon: Zap,
  },
  "automation.level_set": {
    label: "Autonomy level set",
    tone: "amber",
    icon: Gauge,
  },
  "approval.requested": {
    label: "Approval bundle requested",
    tone: "amber",
    icon: KeyRound,
  },
  "approval.oob_signed": {
    label: "Out-of-band approval recorded",
    tone: "green",
    icon: FileSignature,
  },
};

function renderEventBody(event: EventEnvelope): ReactNode {
  const payload = event.payload as Record<string, unknown>;

  switch (event.event_type) {
    case "incident.created":
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={payload.severity as Severity} />
            <Pill>{payload.status as string}</Pill>
          </div>
          <p className="text-sm text-slate-300">{payload.title as string}</p>
          {payload.summary ? (
            <p className="text-xs leading-relaxed text-slate-500">
              {payload.summary as string}
            </p>
          ) : null}
        </div>
      );
    case "signal.received":
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="violet">{payload.kind as string}</Pill>
            <span className="text-xs text-slate-400">
              {payload.source as string}
            </span>
            <TrustBadge trust="untrusted" />
          </div>
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-lg border border-white/5 bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-slate-400">
            {payload.content_excerpt as string}
          </pre>
        </div>
      );
    case "fact.appended":
      return <FactDetail fact={payload as unknown as Fact} />;
    case "fact.status_changed":
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Pill tone="amber">{payload.status as string}</Pill>
          <span className="font-mono text-[11px] text-slate-500">
            fact {shortId(payload.fact_id as string)}
          </span>
          <span className="text-xs text-slate-400">
            {payload.reason as string}
          </span>
        </div>
      );
    case "proposal.created":
      return <ProposalSummary proposal={payload as unknown as Proposal} />;
    case "brief.drafted": {
      const audience = payload.audience as BriefAudience;
      const claims = (payload.claims as unknown[]) ?? [];
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={audienceTone[audience]}>{audienceLabel[audience]}</Pill>
            <Pill>{payload.status as string}</Pill>
            <span className="text-xs text-slate-400">
              {claims.length} cited claims
            </span>
          </div>
          <p className="text-sm text-slate-300">{payload.title as string}</p>
          <p className="text-[10px] text-slate-500">
            {payload.delta_since
              ? `delta since ${formatTime(payload.delta_since as string)}`
              : "full incident picture"}
          </p>
        </div>
      );
    }
    case "brief.checked": {
      const issues = (payload.issues as unknown[]) ?? [];
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <GateBadge status={payload.status as CheckStatus} />
            <span className="text-xs text-slate-400">
              {payload.claims_checked as number} claims re-verified
            </span>
            {issues.length ? (
              <span className="text-[10px] text-amber-300/80">
                {issues.length} issue{issues.length === 1 ? "" : "s"}
              </span>
            ) : null}
          </div>
          <p className="font-mono text-[10px] text-slate-500">
            checker {payload.checker as string} · deterministic gate
          </p>
        </div>
      );
    }
    case "brief.approved":
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Pill tone="green">{payload.approver_role as string}</Pill>
          <span className="text-slate-300">{payload.approver as string}</span>
          <span className="text-[10px] text-slate-500">
            approval expires {formatTime(payload.expires_at as string)}
          </span>
        </div>
      );
    case "brief.send_mocked":
      return (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="amber">mock transport</Pill>
            <span className="font-mono text-[11px] text-slate-300">
              {payload.destination as string}
            </span>
          </div>
          <p className="font-mono text-[10px] text-slate-500">
            delivery {shortId(payload.delivery_id as string)} · requested by{" "}
            {payload.requested_by as string}
          </p>
        </div>
      );
    case "clock.candidate_recorded":
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="amber">candidate</Pill>
            <span className="text-sm text-slate-300">
              {payload.label as string}
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            trigger {formatTime(payload.trigger_at as string)} → due{" "}
            <span className="text-amber-200">
              {formatTime(payload.due_at as string)}
            </span>
          </p>
          <p className="text-[10px] text-slate-500">
            requires legal confirmation · computation trace recorded
          </p>
        </div>
      );
    case "clock.confirmed":
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Pill tone="green">{payload.role as string}</Pill>
          <span className="text-slate-300">{payload.confirmed_by as string}</span>
          <span className="text-[10px] text-slate-500">
            clock {shortId(payload.clock_id as string)} attested
          </span>
        </div>
      );
    case "dispatch.resolved": {
      const resolution = payload.resolution as DispatchRecord["resolution"];
      const assignment = payload.assignment as DispatchRecord["assignment"];
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-cyan-300">
              {resolution.asset}
            </span>
            <ResolutionBadge status={resolution.status} />
            {resolution.owner ? (
              <span className="text-sm text-slate-300">{resolution.owner}</span>
            ) : null}
            {resolution.owner_source ? (
              <Pill>{resolution.owner_source}</Pill>
            ) : null}
            <span className="font-mono text-[10px] text-slate-500">
              confidence {resolution.confidence.toFixed(2)}
            </span>
          </div>
          <p className="text-[10px] text-slate-500">
            {resolution.steps.length} resolution steps ·{" "}
            {assignment
              ? `ack due ${formatTime(assignment.ack_due_at)} (${assignment.sla_minutes}m SLA)`
              : "no assignment (ambiguous owner)"}
          </p>
        </div>
      );
    }
    case "dispatch.acknowledged":
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Pill tone={payload.sla_met ? "green" : "amber"}>
            {payload.sla_met ? "SLA met" : "SLA missed"}
          </Pill>
          <span className="text-slate-300">{payload.acked_by as string}</span>
          <span className="text-[10px] text-slate-500">
            acked {formatTime(payload.ack_at as string)}
          </span>
          {payload.note ? (
            <span className="text-[10px] text-slate-500">
              {payload.note as string}
            </span>
          ) : null}
        </div>
      );
    case "dispatch.escalated":
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Pill tone="amber">escalated</Pill>
          <ArrowUpRight className="h-3.5 w-3.5 text-amber-300" />
          <span className="text-slate-300">
            {payload.escalated_to as string}
          </span>
          <span className="text-[10px] text-slate-500">
            {payload.note as string}
          </span>
        </div>
      );
    case "impact.mapped": {
      const mappings = (payload.mappings as ImpactMapping[]) ?? [];
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="violet">{mappings.length} assets</Pill>
            <span className="text-[10px] text-slate-500">
              deterministic BIA mapping · gaps reported, never guessed
            </span>
          </div>
          <div className="space-y-1">
            {mappings.map((mapping) => (
              <div
                key={mapping.asset}
                className="flex flex-wrap items-center gap-2 text-[11px]"
              >
                <span className="font-mono text-slate-300">{mapping.asset}</span>
                <ImpactStatusBadge status={mapping.status} />
                <span className="text-slate-500">
                  {mapping.service ?? "no service"} · RTO{" "}
                  {mapping.rto_minutes ?? "?"}m · RPO{" "}
                  {mapping.rpo_minutes ?? "?"}m
                </span>
              </div>
            ))}
          </div>
        </div>
      );
    }
    case "readiness.assessed": {
      const planes = (payload.planes as DrPlane[]) ?? [];
      const integrations = (payload.integrations as IntegrationHealth[]) ?? [];
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {planes.map((plane) => (
              <Pill key={plane.plane} tone={planeTone[plane.status]}>
                {plane.plane} · {plane.status}
              </Pill>
            ))}
          </div>
          <p className="text-[10px] text-slate-500">
            {integrations.filter((item) => item.status !== "operational").length}{" "}
            of {integrations.length} integrations not operational · unknown
            evidence fails safe to manual
          </p>
        </div>
      );
    }
    case "handoff.drafted": {
      const handoff = payload as unknown as HandoffBrief;
      return (
        <div className="space-y-2">
          <p className="text-sm text-slate-300">{handoff.summary}</p>
          <div className="flex flex-wrap gap-1.5">
            <Pill tone="amber">
              {handoff.open_approvals.length} approvals
            </Pill>
            <Pill tone="cyan">{handoff.open_acks.length} acks</Pill>
            <Pill tone="red">
              {handoff.evidence_gaps.length} evidence gaps
            </Pill>
            <Pill tone="violet">
              {handoff.pending_clocks.length} clocks
            </Pill>
          </div>
          <p className="text-[10px] text-slate-500">
            display-only handoff · no send path exists
          </p>
        </div>
      );
    }
    case "handoff.acknowledged":
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Pill tone="green">received</Pill>
          <span className="text-slate-300">
            {payload.acknowledged_by as string}
          </span>
          <span className="text-[10px] text-slate-500">
            {formatTime(payload.acknowledged_at as string)}
          </span>
        </div>
      );
    case "policy.decided": {
      const outcome = payload.decision as string;
      const reasons = (payload.reasons as unknown[]) ?? [];
      const roles = (payload.allowed_roles as unknown[]) ?? [];
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill
              tone={
                outcome === "allow" ? "green" : outcome === "deny" ? "red" : "amber"
              }
            >
              {outcome}
            </Pill>
            <span className="text-xs text-slate-400">
              {roles.length
                ? `approver roles: ${(roles as string[]).join(", ")}`
                : "no in-system approval path"}
            </span>
          </div>
          <ul className="space-y-1">
            {(reasons as string[]).map((reason, index) => (
              <li
                key={index}
                className="text-[11px] leading-relaxed text-slate-400"
              >
                {reason}
              </li>
            ))}
          </ul>
          <p className="font-mono text-[10px] text-slate-500">
            action hash {shortId(payload.action_hash as string)} ·{" "}
            {payload.policy_version as string} · deterministic gate
          </p>
        </div>
      );
    }
    case "approval.signed":
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="green">{payload.approver_role as string}</Pill>
            <span className="text-slate-300">{payload.approver as string}</span>
            <span className="text-[10px] text-slate-500">
              expires {formatTime(payload.expires_at as string)}
            </span>
          </div>
          <p className="font-mono text-[10px] text-slate-500">
            nonce {shortId(payload.nonce as string)} · signed with{" "}
            {payload.key_id as string} · sig {shortId(payload.signature as string)}
          </p>
        </div>
      );
    case "execution.simulated": {
      const steps = (payload.steps as { name: string; detail: string }[]) ?? [];
      const credential = payload.credential as
        | { scope: string; ttl_seconds: number }
        | undefined;
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="cyan">dry-run</Pill>
            <span className="font-mono text-[11px] text-slate-300">
              {payload.action_id as string}
            </span>
            <span className="text-[10px] text-slate-500">
              {steps.length} simulated steps · no system contacted
            </span>
          </div>
          <ul className="space-y-1">
            {steps.map((step, index) => (
              <li
                key={index}
                className="text-[11px] leading-relaxed text-slate-400"
              >
                <span className="font-mono text-[10px] text-slate-500">
                  {step.name}
                </span>{" "}
                — {step.detail}
              </li>
            ))}
          </ul>
          {credential ? (
            <p className="font-mono text-[10px] text-slate-500">
              mock JIT grant {credential.scope} · ttl {credential.ttl_seconds}s
            </p>
          ) : null}
        </div>
      );
    }
    case "execution.refused": {
      const reasons = (payload.reasons as unknown[]) ?? [];
      return (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="red">refused</Pill>
            <span className="font-mono text-[11px] text-slate-300">
              {payload.action_id as string}
            </span>
            <span className="text-[10px] text-slate-500">
              requested by {payload.requested_by as string}
            </span>
          </div>
          <ul className="space-y-1">
            {(reasons as string[]).map((reason, index) => (
              <li
                key={index}
                className="text-[11px] leading-relaxed text-amber-300/80"
              >
                {reason}
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case "automation.kill_switch_engaged":
      return (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="red">engaged</Pill>
            <span className="text-xs text-slate-300">
              {payload.actor as string}
            </span>
            <Pill>{payload.source as string}</Pill>
          </div>
          <p className="text-xs leading-relaxed text-slate-400">
            {payload.reason as string}
          </p>
        </div>
      );
    case "automation.kill_switch_released":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="green">released</Pill>
          <span className="text-xs text-slate-300">
            {payload.released_by as string}
          </span>
          <span className="text-xs text-slate-400">
            {payload.reason as string}
          </span>
        </div>
      );
    case "automation.breaker_tripped":
      return (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="red">{payload.action_id as string}</Pill>
            <span className="font-mono text-[10px] text-slate-500">
              {payload.consecutive_refusals as number} consecutive refusals
            </span>
          </div>
          <p className="text-xs leading-relaxed text-slate-400">
            {payload.reason as string}
          </p>
        </div>
      );
    case "automation.breaker_reset":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="green">{payload.action_id as string}</Pill>
          <span className="text-xs text-slate-300">
            reset by {payload.reset_by as string}
          </span>
        </div>
      );
    case "approval.requested":
      return (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="amber">{payload.action_id as string}</Pill>
            <Pill>{payload.topology as string}</Pill>
          </div>
          <p className="font-mono text-[10px] text-slate-500">
            bundle {shortId(payload.id as string)} · nonce{" "}
            {shortId(payload.nonce as string)} · expires{" "}
            {formatTime(payload.expires_at as string)}
          </p>
          <p className="text-[10px] leading-relaxed text-slate-500">
            The bundle is signed on an out-of-band device; Adjutant only
            verifies the attestation that comes back.
          </p>
        </div>
      );
    case "approval.oob_signed":
      return (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="green">{payload.approver_role as string}</Pill>
            <span className="text-xs text-slate-200">
              {payload.approver as string}
            </span>
            <Pill tone="violet">{payload.key_id as string}</Pill>
          </div>
          <p className="font-mono text-[10px] text-slate-500">
            nonce {shortId(payload.nonce as string)} · sig{" "}
            {shortId(payload.signature as string)}
          </p>
        </div>
      );
    default:
      return (
        <pre className="max-h-40 overflow-auto rounded-lg border border-white/5 bg-black/30 p-3 font-mono text-[11px] text-slate-400">
          {JSON.stringify(payload, null, 2)}
        </pre>
      );
  }
}

export function EventCard({ event }: { event: EventEnvelope }) {
  const meta =
    eventMeta[event.event_type] ??
    ({ label: event.event_type, tone: "slate" as Tone, icon: Activity } as const);
  const Icon = meta.icon;

  return (
    <article className="relative pl-11">
      <span className="absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-ink-850 text-slate-400">
        <Icon className="h-4 w-4" />
      </span>
      <div className="rounded-xl border border-white/5 bg-ink-900/80 p-4 shadow-panel">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-100">
                {meta.label}
              </h3>
              <Pill tone={meta.tone}>{event.event_type}</Pill>
            </div>
            <p className="mt-1 font-mono text-[10px] text-slate-500">
              {formatTime(event.recorded_at)} · seq {event.seq} · {event.source}
            </p>
          </div>
          <span
            className="font-mono text-[9px] text-slate-600"
            title={event.hash}
          >
            {shortId(event.hash)}
          </span>
        </div>
        <div className="mt-3">{renderEventBody(event)}</div>
      </div>
    </article>
  );
}

export function FactRow({ fact }: { fact: Fact }) {
  return (
    <div
      className={`rounded-lg border border-white/5 bg-white/[0.02] p-3 ${
        fact.status === "superseded" ? "opacity-50" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-[10px] leading-4 text-cyan-300">
          {fact.attribute}
        </span>
        <StatusBadge status={fact.status} />
      </div>
      <p className="mt-1 break-words text-xs leading-relaxed text-slate-300">
        {renderValue(fact.value, 160)}
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <TrustBadge trust={fact.trust} />
          <span className="font-mono text-[9px] text-slate-600">
            {fact.source}
          </span>
        </div>
        <ConfidenceMeter confidence={fact.confidence} />
      </div>
    </div>
  );
}

export function SignalRow({ signal }: { signal: Signal }) {
  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Pill tone="violet">{signal.kind}</Pill>
          <span className="text-[10px] text-slate-500">{signal.source}</span>
        </div>
        <TrustBadge trust="untrusted" />
      </div>
      <pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap font-mono text-[10px] leading-relaxed text-slate-500">
        {signal.content_excerpt}
      </pre>
      <p className="mt-1 font-mono text-[9px] text-slate-600">
        {formatTime(signal.recorded_at)}
      </p>
    </div>
  );
}

export function ProposalCard({ proposal }: { proposal: Proposal }) {
  return (
    <div className="rounded-lg border border-amber-400/10 bg-amber-400/[0.03] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10px] text-amber-200">
          {proposal.action_id}
        </span>
        <Pill tone={proposal.tier >= 3 ? "red" : "amber"}>
          Tier {proposal.tier}
        </Pill>
      </div>
      <p className="mt-1 text-xs text-slate-300">
        Target: <span className="font-mono">{proposal.target_asset}</span>
      </p>
      <p className="mt-1 text-[10px] text-slate-500">
        {proposal.justification_refs.length} evidence refs · advisory only
      </p>
    </div>
  );
}

export function Panel({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-white/5 bg-ink-900/60 shadow-panel">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
            {title}
          </h3>
          {typeof count === "number" ? (
            <span className="rounded-full bg-white/5 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">
              {count}
            </span>
          ) : null}
        </div>
      </div>
      <div className="space-y-2 p-3">{children}</div>
    </section>
  );
}

export function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-20 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
      <div className="text-lg font-semibold text-slate-100">{value}</div>
      <div className="text-[9px] uppercase tracking-[0.16em] text-slate-500">
        {label}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.01] p-6 text-center">
      <AlertTriangle className="mx-auto h-5 w-5 text-slate-600" />
      <p className="mt-2 text-sm font-medium text-slate-300">{title}</p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-white/5 ${className}`} />;
}

const audienceTone: Record<BriefAudience, Tone> = {
  ic: "cyan",
  exec: "violet",
  technical: "slate",
  legal: "amber",
};

const audienceLabel: Record<BriefAudience, string> = {
  ic: "Incident commander",
  exec: "Executive",
  technical: "Technical",
  legal: "Legal",
};

const gateTone: Record<CheckStatus, Tone> = {
  passed: "green",
  needs_review: "amber",
  failed: "red",
};

export function GateBadge({ status }: { status: CheckStatus }) {
  const label =
    status === "passed"
      ? "gate passed"
      : status === "needs_review"
        ? "needs review"
        : "gate failed";
  return <Pill tone={gateTone[status]}>{label}</Pill>;
}

function remaining(iso: string): {
  text: string;
  tone: "red" | "amber" | "slate";
} {
  const diff = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(diff);
  const days = Math.floor(abs / 86_400_000);
  const hours = Math.floor((abs % 86_400_000) / 3_600_000);
  const minutes = Math.floor((abs % 3_600_000) / 60_000);
  const body =
    days > 0 ? `${days}d ${hours}h` : hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  if (diff < 0) return { text: `overdue by ${body}`, tone: "red" };
  if (diff < 24 * 3_600_000) return { text: `${body} left`, tone: "amber" };
  return { text: `${body} left`, tone: "slate" };
}

const inputClass =
  "w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-cyan-400/40 focus:outline-none";

const selectClass = `${inputClass} appearance-none`;

const actionClass =
  "inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/25 bg-cyan-400/10 px-2.5 py-1.5 text-[11px] font-medium text-cyan-200 transition hover:bg-cyan-400/15 disabled:cursor-not-allowed disabled:opacity-40";

export function BriefCard({
  record,
  incidentId,
  onChanged,
}: {
  record: BriefRecord;
  incidentId: string;
  onChanged: () => void;
}) {
  const { brief, check, approval, send } = record;
  const [approver, setApprover] = useState("priya.nair");
  const [role, setRole] = useState("ic");
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  const [requestedBy, setRequestedBy] = useState("priya.nair");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingSend, setConfirmingSend] = useState(false);

  const gate = check?.status ?? brief.check_status;
  const needsReview = gate === "needs_review";

  async function act(task: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await task();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  const submitApproval = (event: FormEvent) => {
    event.preventDefault();
    act(() =>
      api.approveBrief(incidentId, brief.id, {
        approver,
        approver_role: role,
        review_acknowledged: ack,
        note: note || undefined,
      }),
    );
  };

  const submitSend = () => {
    if (!confirmingSend) {
      setConfirmingSend(true);
      return;
    }
    act(async () => {
      await api.sendBriefMock(incidentId, brief.id, requestedBy);
      setConfirmingSend(false);
    });
  };

  return (
    <div className="space-y-3 rounded-xl border border-white/5 bg-white/[0.02] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={audienceTone[brief.audience]}>
            {audienceLabel[brief.audience]}
          </Pill>
          <Pill tone={brief.status === "sent_mock" ? "amber" : brief.status === "approved" ? "green" : "slate"}>
            {brief.status.replace("_", " ")}
          </Pill>
        </div>
        {gate ? <GateBadge status={gate} /> : null}
      </div>

      <div>
        <h4 className="text-xs font-semibold leading-snug text-slate-100">
          {brief.title}
        </h4>
        <p className="mt-1 font-mono text-[9px] text-slate-600">
          {brief.claims.length} claims · {brief.fact_ids.length} facts ·{" "}
          {brief.delta_since
            ? `delta since ${formatTime(brief.delta_since)}`
            : "full picture"}{" "}
          · {formatTime(brief.created_at)}
        </p>
      </div>

      <ol className="space-y-1.5">
        {brief.claims.map((claim, index) => (
          <li
            key={claim.id}
            className="rounded-lg border border-white/5 bg-black/20 px-2.5 py-2"
          >
            <div className="flex items-start gap-2">
              <span className="mt-0.5 font-mono text-[9px] text-slate-600">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0 space-y-1">
                <p className="text-[11px] leading-relaxed text-slate-300">
                  {claim.text}
                </p>
                <div className="flex flex-wrap items-center gap-1.5">
                  {claim.kind === "judgment" ? (
                    <Pill tone="amber">judgment</Pill>
                  ) : null}
                  <span
                    className="font-mono text-[9px] text-slate-600"
                    title={claim.fact_ids.join(", ")}
                  >
                    {claim.fact_ids.map((id) => shortId(id)).join(" · ")}
                  </span>
                  <span className="text-[9px] text-slate-600">
                    {claim.evidence_refs.length} evidence refs
                  </span>
                </div>
              </div>
            </div>
          </li>
        ))}
      </ol>

      {check ? (
        <div className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] text-slate-500">
              fact-checker · {check.claims_checked} claims ·{" "}
              {formatTime(check.checked_at)}
            </span>
            <button
              type="button"
              onClick={() => act(() => api.checkBrief(incidentId, brief.id))}
              disabled={busy}
              className="text-[10px] font-medium text-cyan-300/80 hover:text-cyan-200 disabled:opacity-40"
            >
              re-check
            </button>
          </div>
          {check.issues.length ? (
            <ul className="space-y-1">
              {check.issues.map((issue, index) => (
                <li
                  key={`${issue.code}-${index}`}
                  className="flex items-start gap-1.5 text-[10px] leading-relaxed text-amber-200/80"
                >
                  <span className="font-mono text-amber-300/70">
                    {issue.code}
                  </span>
                  <span className="text-slate-500">{issue.detail}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[10px] text-emerald-300/70">
              Every claim traced to current, trusted, evidenced facts.
            </p>
          )}
        </div>
      ) : null}

      {approval ? (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-emerald-500/15 bg-emerald-500/[0.04] px-2.5 py-2 text-[10px] text-emerald-200/80">
          <span>
            approved by {approval.approver} ({approval.approver_role})
          </span>
          <span className="text-slate-500">
            expires {formatTime(approval.expires_at)}
          </span>
        </div>
      ) : null}

      {send ? (
        <div className="space-y-1 rounded-lg border border-amber-400/15 bg-amber-400/[0.04] px-2.5 py-2">
          <p className="font-mono text-[10px] text-amber-200/80">
            sent · {send.destination}
          </p>
          <p className="font-mono text-[9px] text-slate-500">
            {send.adapter} delivery {shortId(send.delivery_id)} · requested by{" "}
            {send.requested_by}
          </p>
        </div>
      ) : null}

      {brief.status === "draft" ? (
        <form onSubmit={submitApproval} className="space-y-2">
          <div className="grid grid-cols-2 gap-1.5">
            <input
              className={inputClass}
              value={approver}
              onChange={(event) => setApprover(event.target.value)}
              placeholder="approver"
              aria-label="Approver name"
            />
            <select
              className={selectClass}
              value={role}
              onChange={(event) => setRole(event.target.value)}
              aria-label="Approver role"
            >
              <option value="ic">IC</option>
              <option value="exec">Exec</option>
              <option value="legal">Legal</option>
              <option value="comms">Comms</option>
              <option value="security">Security</option>
            </select>
          </div>
          <input
            className={inputClass}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="approval note (optional)"
            aria-label="Approval note"
          />
          {needsReview ? (
            <label className="flex items-start gap-2 text-[10px] leading-relaxed text-amber-200/80">
              <input
                type="checkbox"
                checked={ack}
                onChange={(event) => setAck(event.target.checked)}
                className="mt-0.5 h-3 w-3 accent-amber-400"
              />
              I reviewed the judgment claims flagged by the gate.
            </label>
          ) : null}
          <button
            type="submit"
            disabled={
              busy ||
              !approver.trim() ||
              gate === "failed" ||
              (needsReview && !ack)
            }
            className={actionClass}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            {busy ? "Approving…" : "Approve brief"}
          </button>
          <p className="text-[9px] leading-relaxed text-slate-600">
            The gate re-runs against the fact ledger at approval. Approval expires
            after 30 minutes.
          </p>
        </form>
      ) : null}

      {brief.status === "approved" ? (
        <div className="space-y-2">
          <div className="grid grid-cols-[1fr_auto] gap-1.5">
            <input
              className={inputClass}
              value={requestedBy}
              onChange={(event) => setRequestedBy(event.target.value)}
              placeholder="send as"
              aria-label="Sender name"
            />
            <button
              type="button"
              onClick={submitSend}
              disabled={busy || !requestedBy.trim()}
              className={
                confirmingSend
                  ? actionClass.replace("border-cyan-400/25", "border-amber-400/30").replace("bg-cyan-400/10", "bg-amber-400/10").replace("text-cyan-200", "text-amber-200")
                  : actionClass
              }
            >
              <Send className="h-3.5 w-3.5" />
              {busy ? "Sending…" : confirmingSend ? "Confirm send" : "Send mock"}
            </button>
          </div>
          <p className="text-[9px] leading-relaxed text-slate-600">
            {confirmingSend
              ? "Click again to deliver to mock:// — no external channel exists."
              : "Transport is mocked. Nothing leaves this environment."}
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-2.5 py-1.5 text-[10px] leading-relaxed text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function ClockCard({
  clock,
  incidentId,
  onChanged,
}: {
  clock: ClockCandidate;
  incidentId: string;
  onChanged: () => void;
}) {
  const [name, setName] = useState("meera.rao");
  const [role, setRole] = useState("legal");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remain = remaining(clock.due_at);
  const remainTone =
    remain.tone === "red"
      ? "text-red-300"
      : remain.tone === "amber"
        ? "text-amber-300"
        : "text-slate-400";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    api
      .confirmClock(incidentId, clock.id, {
        confirmed_by: name,
        role,
        attestation: attested,
      })
      .then(onChanged)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Request failed"),
      )
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-2.5 rounded-xl border border-white/5 bg-white/[0.02] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone="cyan">{clock.regime.toUpperCase()}</Pill>
          <Pill tone={clock.status === "confirmed" ? "green" : "amber"}>
            {clock.status}
          </Pill>
        </div>
        <span className={`font-mono text-[10px] ${remainTone}`}>{remain.text}</span>
      </div>

      <div>
        <h4 className="text-xs font-semibold leading-snug text-slate-100">
          {clock.label}
        </h4>
        <p className="mt-1 text-[10px] text-slate-500">
          due <span className="text-slate-300">{formatTime(clock.due_at)}</span> ·
          trigger {formatTime(clock.trigger_at)}
        </p>
        <p className="mt-0.5 font-mono text-[9px] text-slate-600">
          {clock.computation.duration} · {clock.computation.calendar}
          {clock.computation.timezone ? ` · ${clock.computation.timezone}` : ""}
          {clock.trigger_fact_id
            ? ` · fact ${shortId(clock.trigger_fact_id)}`
            : ""}
        </p>
      </div>

      <details className="rounded-lg border border-white/5 bg-black/20 px-2.5 py-2">
        <summary className="cursor-pointer text-[10px] uppercase tracking-wider text-slate-500">
          computation trace · {clock.computation.engine}
        </summary>
        <ol className="mt-2 space-y-1 font-mono text-[9px] leading-relaxed text-slate-500">
          {clock.computation.steps.map((step, index) => (
            <li key={index}>
              <span className="text-slate-600">
                {String(index + 1).padStart(2, "0")}
              </span>{" "}
              {step}
            </li>
          ))}
        </ol>
        <p className="mt-2 text-[9px] text-slate-600">
          computed {formatTime(clock.computation.computed_at)}
        </p>
      </details>

      {clock.status === "confirmed" ? (
        <div className="rounded-lg border border-emerald-500/15 bg-emerald-500/[0.04] px-2.5 py-2 text-[10px] text-emerald-200/80">
          confirmed by {clock.confirmed_by} ({clock.confirmed_role}) ·{" "}
          {formatTime(clock.confirmed_at)}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-2">
          <div className="grid grid-cols-[1fr_92px] gap-1.5">
            <input
              className={inputClass}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="legal / DPO name"
              aria-label="Confirmer name"
            />
            <select
              className={selectClass}
              value={role}
              onChange={(event) => setRole(event.target.value)}
              aria-label="Confirmer role"
            >
              <option value="legal">Legal</option>
              <option value="dpo">DPO</option>
            </select>
          </div>
          <label className="flex items-start gap-2 text-[10px] leading-relaxed text-slate-400">
            <input
              type="checkbox"
              checked={attested}
              onChange={(event) => setAttested(event.target.checked)}
              className="mt-0.5 h-3 w-3 accent-emerald-400"
            />
            I confirm this deadline with legal/DPO authority. The engine only
            proposes candidates.
          </label>
          <button
            type="submit"
            disabled={busy || !name.trim() || !attested}
            className={actionClass}
          >
            <Timer className="h-3.5 w-3.5" />
            {busy ? "Recording…" : "Confirm deadline"}
          </button>
        </form>
      )}

      {error ? (
        <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-2.5 py-1.5 text-[10px] leading-relaxed text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const resolutionTone: Record<
  DispatchRecord["resolution"]["status"],
  Tone
> = {
  resolved: "green",
  unknown_owner: "red",
  ambiguous: "amber",
};

export function ResolutionBadge({
  status,
}: {
  status: DispatchRecord["resolution"]["status"];
}) {
  return (
    <Pill tone={resolutionTone[status]}>
      {status === "unknown_owner" ? "unknown owner" : status}
    </Pill>
  );
}

const impactTone: Record<ImpactMapping["status"], Tone> = {
  mapped: "green",
  partial: "amber",
  unknown: "red",
};

export function ImpactStatusBadge({
  status,
}: {
  status: ImpactMapping["status"];
}) {
  return <Pill tone={impactTone[status]}>{status}</Pill>;
}

const planeTone: Record<DrPlane["status"], Tone> = {
  healthy: "green",
  degraded: "amber",
  compromised: "red",
  unknown: "slate",
};

const integrationTone: Record<IntegrationHealth["status"], Tone> = {
  operational: "green",
  degraded: "amber",
  down: "red",
  unknown: "slate",
};

const dispatchTone: Record<
  NonNullable<DispatchRecord["assignment"]>["status"],
  Tone
> = {
  pending: "cyan",
  acked: "green",
  escalated: "amber",
  closed: "slate",
};

const stepTone: Record<"used" | "missing" | "rejected", string> = {
  used: "text-emerald-300",
  missing: "text-slate-600",
  rejected: "text-amber-300",
};

function slaCountdown(
  assignment: NonNullable<DispatchRecord["assignment"]>,
): { text: string; overdue: boolean } {
  const remainingMs = new Date(assignment.ack_due_at).getTime() - Date.now();
  const minutes = Math.round(Math.abs(remainingMs) / 60_000);
  if (remainingMs < 0) {
    return { text: `${minutes}m overdue`, overdue: true };
  }
  return { text: `${minutes}m left`, overdue: false };
}

export function DispatchCard({
  record,
  incidentId,
  onChanged,
}: {
  record: DispatchRecord;
  incidentId: string;
  onChanged: () => void;
}) {
  const { resolution, assignment } = record;
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function acknowledge() {
    if (!assignment) return;
    setBusy(true);
    setError(null);
    try {
      await api.ackDispatch(incidentId, assignment.id, name.trim());
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to acknowledge");
    } finally {
      setBusy(false);
    }
  }

  const countdown = assignment ? slaCountdown(assignment) : null;

  return (
    <div className="space-y-2.5 rounded-lg border border-white/5 bg-white/[0.02] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-cyan-300">
          {resolution.asset}
        </span>
        <ResolutionBadge status={resolution.status} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Users className="h-3.5 w-3.5 text-slate-500" />
        <span className="text-xs font-medium text-slate-200">
          {resolution.owner ?? (assignment ? assignment.owner : "unassigned")}
        </span>
        {resolution.owner_source ? (
          <Pill>{resolution.owner_source}</Pill>
        ) : null}
        <span className="font-mono text-[10px] text-slate-500">
          conf {resolution.confidence.toFixed(2)}
        </span>
      </div>

      {resolution.status === "unknown_owner" ? (
        <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-2.5 py-1.5 text-[10px] leading-relaxed text-red-300">
          First-class unknown owner. No accountable human was resolved from CMDB,
          service catalog, on-call, last assignee, or team lead. Acknowledgement
          routes to the incident commander.
        </p>
      ) : null}

      <div className="space-y-1 rounded-lg border border-white/5 bg-black/20 p-2">
        <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
          Resolution chain
        </p>
        {resolution.steps.map((step, index) => (
          <div
            key={`${step.source}-${step.attribute}-${index}`}
            className="flex items-start gap-2 text-[10px] leading-relaxed"
          >
            <span
              className={`mt-1 h-1 w-1 shrink-0 rounded-full ${
                step.outcome === "used"
                  ? "bg-emerald-400"
                  : step.outcome === "rejected"
                    ? "bg-amber-400"
                    : "bg-slate-700"
              }`}
            />
            <span className="w-24 shrink-0 font-mono text-slate-500">
              {step.source}
            </span>
            <span className={`min-w-0 flex-1 ${stepTone[step.outcome]}`}>
              <span className="font-mono">{step.attribute}</span> · {step.detail}
            </span>
          </div>
        ))}
      </div>

      {resolution.candidates.length > 1 ? (
        <div className="flex flex-wrap gap-1.5">
          {resolution.candidates.map((candidate) => (
            <Pill key={candidate.fact_id ?? candidate.owner} tone="slate">
              {candidate.owner} {candidate.confidence.toFixed(2)}
            </Pill>
          ))}
        </div>
      ) : null}

      {assignment ? (
        <div className="space-y-2 rounded-lg border border-white/5 bg-black/20 p-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={dispatchTone[assignment.status]}>
              {assignment.status}
            </Pill>
            <span className="font-mono text-[10px] text-slate-500">
              SLA {assignment.sla_minutes}m · due{" "}
              {formatTime(assignment.ack_due_at)}
            </span>
            {assignment.status === "pending" && countdown ? (
              <span
                className={`text-[10px] ${
                  countdown.overdue ? "text-red-300" : "text-slate-400"
                }`}
              >
                {countdown.text}
              </span>
            ) : null}
          </div>

          {assignment.status === "acked" ? (
            <p className="text-[10px] text-slate-400">
              acknowledged by{" "}
              <span className="text-slate-200">{assignment.ack_by}</span> at{" "}
              {formatTime(assignment.ack_at)} ·{" "}
              <span
                className={
                  assignment.sla_met ? "text-emerald-300" : "text-amber-300"
                }
              >
                {assignment.sla_met ? "SLA met" : "SLA missed"}
              </span>
            </p>
          ) : null}

          {assignment.status === "escalated" ? (
            <p className="flex items-center gap-1.5 text-[10px] text-amber-200">
              <ArrowUpRight className="h-3.5 w-3.5" />
              escalated to {assignment.escalated_to} at{" "}
              {formatTime(assignment.escalated_at)}
            </p>
          ) : null}

          {assignment.status === "pending" ? (
            <div className="flex gap-1.5">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="human name"
                className={`${inputClass} flex-1`}
              />
              <button
                type="button"
                onClick={acknowledge}
                disabled={busy || !name.trim()}
                className={actionClass}
              >
                <UserCheck className="h-3.5 w-3.5" />
                {busy ? "…" : "Ack"}
              </button>
            </div>
          ) : null}

          {error ? (
            <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function ImpactCard({ mapping }: { mapping: ImpactMapping }) {
  return (
    <div className="space-y-2 rounded-lg border border-white/5 bg-white/[0.02] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-cyan-300">
          {mapping.asset}
        </span>
        <ImpactStatusBadge status={mapping.status} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
        <span>service {mapping.service ?? "—"}</span>
        <span className="text-slate-700">·</span>
        <span>criticality {mapping.criticality ?? "—"}</span>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        <div className="rounded-md border border-white/5 bg-black/20 px-2 py-1.5">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">RTO</p>
          <p className="font-mono text-[11px] text-slate-300">
            {mapping.rto_minutes !== null ? `${mapping.rto_minutes}m` : "—"}
          </p>
        </div>
        <div className="rounded-md border border-white/5 bg-black/20 px-2 py-1.5">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">RPO</p>
          <p className="font-mono text-[11px] text-slate-300">
            {mapping.rpo_minutes !== null ? `${mapping.rpo_minutes}m` : "—"}
          </p>
        </div>
        <div className="rounded-md border border-white/5 bg-black/20 px-2 py-1.5">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">
            deadline
          </p>
          <p className="font-mono text-[10px] text-amber-200">
            {formatTime(mapping.rto_deadline)}
          </p>
        </div>
      </div>
      {mapping.gaps.length ? (
        <div className="flex flex-wrap gap-1">
          {mapping.gaps.map((gap) => (
            <Pill key={gap} tone="amber">
              {gap}
            </Pill>
          ))}
        </div>
      ) : (
        <p className="text-[10px] text-emerald-300/80">
          complete BIA mapping · no gaps
        </p>
      )}
    </div>
  );
}

export function ReadinessCard({
  assessment,
}: {
  assessment: ReadinessAssessment;
}) {
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <p className="flex items-center gap-1.5 text-[9px] uppercase tracking-[0.16em] text-slate-600">
          <Network className="h-3 w-3" />
          DR planes
        </p>
        {assessment.planes.map((plane) => (
          <div
            key={plane.plane}
            className="rounded-lg border border-white/5 bg-white/[0.02] p-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-slate-300">{plane.plane}</span>
              <Pill tone={planeTone[plane.status]}>{plane.status}</Pill>
            </div>
            <div className="mt-1 space-y-0.5">
              {plane.checks.map((check) => (
                <p
                  key={check.name}
                  className="flex items-start gap-1.5 text-[10px] leading-relaxed"
                  title={check.detail}
                >
                  <span
                    className={`mt-1 h-1 w-1 shrink-0 rounded-full ${
                      check.outcome === "pass"
                        ? "bg-emerald-400"
                        : check.outcome === "fail"
                          ? "bg-red-400"
                          : "bg-slate-600"
                    }`}
                  />
                  <span className="font-mono text-slate-500">{check.name}</span>
                  <span className="text-slate-500">· {check.detail}</span>
                </p>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-1.5">
        <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
          Integration degraded modes
        </p>
        <div className="grid grid-cols-1 gap-1">
          {assessment.integrations.map((health) => (
            <div
              key={health.integration}
              className="flex items-center justify-between gap-2 rounded-md border border-white/5 bg-black/20 px-2 py-1.5"
            >
              <span className="font-mono text-[11px] text-slate-300">
                {health.integration}
              </span>
              <div className="flex items-center gap-1.5">
                <Pill tone={integrationTone[health.status]}>
                  {health.status}
                </Pill>
                <Pill tone={health.mode === "normal" ? "slate" : "amber"}>
                  {health.mode}
                </Pill>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[10px] leading-relaxed text-slate-600">
          Missing or untrusted health evidence resolves to unknown and manual
          mode. The engine never assumes a capability is available.
        </p>
      </div>
    </div>
  );
}

function HandoffSection({
  title,
  tone,
  items,
}: {
  title: string;
  tone: Tone;
  items: HandoffItem[];
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
          {title}
        </p>
        <Pill tone={tone}>{items.length}</Pill>
      </div>
      {items.length ? (
        items.map((item) => (
          <div
            key={item.key}
            className="flex items-start justify-between gap-2 rounded-md border border-white/5 bg-black/20 px-2 py-1.5"
          >
            <span className="min-w-0 text-[10px] leading-relaxed text-slate-300">
              {item.label}
            </span>
            <span className="shrink-0 font-mono text-[9px] text-slate-500">
              {item.status}
            </span>
          </div>
        ))
      ) : (
        <p className="px-1 text-[10px] text-slate-600">none</p>
      )}
    </div>
  );
}

export function HandoffCard({
  handoff,
  incidentId,
  onChanged,
}: {
  handoff: HandoffBrief;
  incidentId: string;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function acknowledge() {
    setBusy(true);
    setError(null);
    try {
      await api.acknowledgeHandoff(incidentId, handoff.id, name.trim());
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to acknowledge");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-white/5 bg-white/[0.02] p-3">
      <div>
        <p className="text-xs font-medium leading-snug text-slate-200">
          {handoff.title}
        </p>
        <p className="mt-1 text-[10px] text-slate-500">{handoff.summary}</p>
      </div>

      <div className="flex flex-wrap gap-1">
        {handoff.checks.map((check) => (
          <span
            key={check}
            className="rounded-md border border-white/5 bg-black/20 px-1.5 py-1 font-mono text-[9px] text-slate-500"
          >
            {check}
          </span>
        ))}
      </div>

      <HandoffSection
        title="Open approvals"
        tone="amber"
        items={handoff.open_approvals}
      />
      <HandoffSection
        title="Open acknowledgements"
        tone="cyan"
        items={handoff.open_acks}
      />
      <HandoffSection
        title="Evidence gaps"
        tone="red"
        items={handoff.evidence_gaps}
      />
      <HandoffSection
        title="Pending clocks"
        tone="violet"
        items={handoff.pending_clocks}
      />
      <HandoffSection
        title="Readiness snapshot"
        tone="slate"
        items={handoff.readiness}
      />

      {handoff.acknowledged_at ? (
        <p className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] text-emerald-300">
          Received by {handoff.acknowledged_by} at{" "}
          {formatTime(handoff.acknowledged_at)}
        </p>
      ) : (
        <div className="space-y-1.5">
          <p className="text-[10px] leading-relaxed text-slate-600">
            Display-only handoff. Nothing is sent to any channel; the incoming
            commander records receipt here.
          </p>
          <div className="flex gap-1.5">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="incoming commander"
              className={`${inputClass} flex-1`}
            />
            <button
              type="button"
              onClick={acknowledge}
              disabled={busy || !name.trim()}
              className={actionClass}
            >
              <ClipboardCheck className="h-3.5 w-3.5" />
              {busy ? "…" : "Receive"}
            </button>
          </div>
        </div>
      )}

      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}

const outcomeTone: Record<string, Tone> = {
  allow: "green",
  deny: "red",
  escalate: "amber",
};

function CatalogSection({
  label,
  items,
}: {
  label: string;
  items: string[];
}) {
  return (
    <div className="space-y-1">
      <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
        {label}
      </p>
      {items.length ? (
        items.map((item, index) => (
          <p
            key={index}
            className="rounded-md border border-white/5 bg-black/20 px-2 py-1.5 text-[10px] leading-relaxed text-slate-300"
          >
            {item}
          </p>
        ))
      ) : (
        <p className="px-1 text-[10px] text-slate-600">none recorded</p>
      )}
    </div>
  );
}

export function ContainmentCard({
  record,
  incidentId,
  onChanged,
  channel = "in-band",
}: {
  record: ContainmentRecord;
  incidentId: string;
  onChanged: () => void;
  channel?: "in-band" | "out-of-band";
}) {
  const { proposal, catalog, decision, approval, execution } = record;
  const approvalSpent = record.approval_spent;
  const [name, setName] = useState("");
  const [role, setRole] = useState("ic");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [oobRequest, setOobRequest] = useState<ApprovalRequest | null>(null);
  const [oobSignature, setOobSignature] = useState<string | null>(null);

  const roles = decision?.allowed_roles ?? [];
  const activeRole = roles.includes(role) ? role : (roles[0] ?? "ic");
  const expiry = approval ? remaining(approval.expires_at) : null;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-xl border border-white/5 bg-ink-900/80 p-4 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-100">
              {catalog?.title ?? proposal.action_id}
            </h3>
            <Pill tone={proposal.tier === 3 ? "red" : proposal.tier === 2 ? "amber" : "cyan"}>
              tier {proposal.tier}
            </Pill>
            {catalog?.never_automate ? (
              <Pill tone="red">never-automate</Pill>
            ) : null}
            {catalog?.business_hours_only ? (
              <Pill tone="violet">business hours only</Pill>
            ) : null}
          </div>
          <p className="mt-1 font-mono text-[10px] text-slate-500">
            {proposal.target_asset} · proposal {shortId(proposal.id)} · proposed
            by {proposal.proposed_by} · {formatTime(proposal.created_at)}
          </p>
        </div>
      </div>

      {catalog?.never_automate ? (
        <p className="rounded-lg border border-red-500/25 bg-red-500/10 px-2.5 py-2 text-[11px] leading-relaxed text-red-300">
          On the never-automate list: Adjutant will not approve or execute this
          action. A human decision must be made outside this system.
        </p>
      ) : null}

      {catalog ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
              Blast radius
            </p>
            <p className="rounded-md border border-white/5 bg-black/20 px-2 py-1.5 text-[10px] leading-relaxed text-slate-300">
              {catalog.blast_radius}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
              Preconditions
            </p>
            {catalog.preconditions.map((item, index) => (
              <p
                key={index}
                className="rounded-md border border-white/5 bg-black/20 px-2 py-1.5 text-[10px] leading-relaxed text-slate-300"
              >
                {item}
              </p>
            ))}
          </div>
          <CatalogSection
            label="Evidence preservation"
            items={catalog.evidence_preservation}
          />
          <CatalogSection label="Rollback" items={catalog.rollback} />
        </div>
      ) : (
        <p className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-2.5 py-2 text-[11px] text-amber-300">
          '{proposal.action_id}' is not in the action catalog. The policy gate
          will deny it.
        </p>
      )}

      <div className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
            Policy gate
          </p>
          {decision ? (
            <Pill tone={outcomeTone[decision.decision] ?? "slate"}>
              {decision.decision}
            </Pill>
          ) : (
            <Pill>not evaluated</Pill>
          )}
        </div>
        {decision ? (
          <>
            <ul className="space-y-1">
              {decision.reasons.map((reason, index) => (
                <li
                  key={index}
                  className="text-[11px] leading-relaxed text-slate-400"
                >
                  {reason}
                </li>
              ))}
            </ul>
            <p className="font-mono text-[10px] text-slate-500">
              action hash {shortId(decision.action_hash)} ·{" "}
              {decision.policy_version} · {formatTime(decision.evaluated_at)}
              {roles.length ? ` · approver roles: ${roles.join(", ")}` : ""}
            </p>
          </>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(() => api.evaluateProposal(incidentId, proposal.id))
            }
            className={actionClass}
          >
            <Gavel className="h-3.5 w-3.5" />
            {busy ? "…" : "Run policy gate"}
          </button>
        )}
      </div>

      {approval ? (
        <div className="space-y-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone="green">{approval.approver_role}</Pill>
              <span className="text-xs text-slate-200">{approval.approver}</span>
            </div>
            {expiry ? <Pill tone={expiry.tone}>{expiry.text}</Pill> : null}
          </div>
          <p className="font-mono text-[10px] text-slate-500">
            nonce {shortId(approval.nonce)} · key {approval.key_id} · sig{" "}
            {shortId(approval.signature)}
          </p>
          {approvalSpent ? (
            <p className="text-[10px] text-slate-500">
              This approval has been consumed by a dry-run and can never be
              replayed.
            </p>
          ) : null}
        </div>
      ) : decision?.decision === "allow" && !catalog?.never_automate ? (
        channel === "out-of-band" ? (
          <div className="space-y-1.5 rounded-lg border border-amber-400/25 bg-amber-400/[0.05] p-3">
            <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
              Out-of-band approval channel
            </p>
            <p className="text-[10px] leading-relaxed text-slate-500">
              In-band approval is refused in this profile. Request a signed
              bundle, approve it on a separate control plane, then submit the
              attestation here for verification.
            </p>
            {oobRequest ? (
              <>
                <p className="font-mono text-[10px] text-slate-500">
                  bundle {shortId(oobRequest.id)} · nonce{" "}
                  {shortId(oobRequest.nonce)} · expires{" "}
                  {formatTime(oobRequest.expires_at)} · {oobRequest.topology}
                </p>
                {oobSignature ? (
                  <>
                    <p className="break-all font-mono text-[10px] text-slate-400">
                      attestation {oobSignature}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      <input
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        placeholder="approver name"
                        className={`${inputClass} flex-1 min-w-[10rem]`}
                      />
                      <select
                        value={activeRole}
                        onChange={(event) => setRole(event.target.value)}
                        className={`${selectClass} w-28`}
                      >
                        {roles.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={busy || !name.trim()}
                        onClick={() =>
                          run(async () => {
                            await api.approveOob(incidentId, proposal.id, {
                              bundle_id: oobRequest.id,
                              approver: name.trim(),
                              approver_role: activeRole,
                              attestation_signature: oobSignature,
                            });
                            setOobRequest(null);
                            setOobSignature(null);
                          })
                        }
                        className={actionClass}
                      >
                        <FileSignature className="h-3.5 w-3.5" />
                        {busy ? "…" : "Submit OOB approval"}
                      </button>
                    </div>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const signed = await api.mockOobSign(oobRequest.id);
                        setOobSignature(signed.signature);
                      })
                    }
                    className={actionClass}
                  >
                    <KeyRound className="h-3.5 w-3.5" />
                    {busy ? "…" : "Mock-sign bundle (drill)"}
                  </button>
                )}
              </>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const created = await api.createApprovalRequest(
                      incidentId,
                      proposal.id,
                    );
                    setOobRequest(created);
                  })
                }
                className={actionClass}
              >
                <KeyRound className="h-3.5 w-3.5" />
                {busy ? "…" : "Request approval bundle"}
              </button>
            )}
          </div>
        ) : (
        <div className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-3">
          <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
            Approval required
          </p>
          <div className="flex flex-wrap gap-1.5">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="approver name"
              className={`${inputClass} flex-1 min-w-[10rem]`}
            />
            <select
              value={activeRole}
              onChange={(event) => setRole(event.target.value)}
              className={`${selectClass} w-28`}
            >
              {roles.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={busy || !name.trim()}
              onClick={() =>
                run(async () => {
                  await api.approveProposal(incidentId, proposal.id, {
                    approver: name.trim(),
                    approver_role: activeRole,
                  });
                })
              }
              className={actionClass}
            >
              <FileSignature className="h-3.5 w-3.5" />
              {busy ? "…" : "Approve & sign"}
            </button>
          </div>
          <p className="text-[10px] leading-relaxed text-slate-600">
            Human-only. Agent, system, bot, and model actors are rejected.
            Approval expires in 15 minutes and binds to the action hash.
          </p>
        </div>
        )
      ) : null}

      {execution ? (
        <div
          className={`space-y-1.5 rounded-lg border p-3 ${
            execution.status === "simulated"
              ? "border-cyan-400/20 bg-cyan-400/[0.06]"
              : "border-amber-400/20 bg-amber-400/[0.06]"
          }`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={execution.status === "simulated" ? "cyan" : "amber"}>
              {execution.status === "simulated" ? "dry-run simulated" : "refused"}
            </Pill>
            <span className="text-[10px] text-slate-500">
              {formatTime(execution.started_at)} · requested by{" "}
              {execution.requested_by}
            </span>
          </div>
          {execution.status === "simulated" ? (
            <ul className="space-y-1">
              {execution.steps.map((step, index) => (
                <li
                  key={index}
                  className="text-[11px] leading-relaxed text-slate-400"
                >
                  <span className="font-mono text-[10px] text-slate-500">
                    {step.name}
                  </span>{" "}
                  — {step.detail}
                </li>
              ))}
            </ul>
          ) : (
            <ul className="space-y-1">
              {execution.reasons.map((reason, index) => (
                <li
                  key={index}
                  className="text-[11px] leading-relaxed text-amber-300/80"
                >
                  {reason}
                </li>
              ))}
            </ul>
          )}
          {execution.credential ? (
            <p className="font-mono text-[10px] text-slate-500">
              mock JIT grant {execution.credential.scope} · ttl{" "}
              {execution.credential.ttl_seconds}s ·{" "}
              {execution.credential.broker}
            </p>
          ) : null}
        </div>
      ) : approval && !approvalSpent ? (
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(() =>
              api.executeProposal(incidentId, proposal.id, name.trim() || approval.approver),
            )
          }
          className={actionClass}
        >
          <FlaskConical className="h-3.5 w-3.5" />
          {busy ? "…" : "Dry-run execute"}
        </button>
      ) : null}

      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}

const autonomyTone: Record<AutonomyLevel, Tone> = {
  shadow: "slate",
  suggest: "amber",
  approve: "green",
};

const autonomyLevels: AutonomyLevel[] = ["shadow", "suggest", "approve"];

export function AutomationPanel({
  status,
  scorecards,
  onChanged,
}: {
  status: AutomationStatus | null;
  scorecards: Scorecard[];
  onChanged: () => void;
}) {
  if (!status) {
    return <Skeleton className="h-48 w-full" />;
  }

  return (
    <div className="space-y-3">
      <section className="space-y-3 rounded-xl border border-white/5 bg-ink-900/80 p-4 shadow-panel">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-100">
            Automation posture
          </h3>
          <Pill tone="violet">{status.config_profile}</Pill>
          <Pill tone={status.approval_channel === "in-band" ? "cyan" : "amber"}>
            {status.approval_channel} approvals
          </Pill>
          <Pill tone={status.promotion_enabled ? "amber" : "slate"}>
            promotion {status.promotion_enabled ? "enabled" : "disabled"}
          </Pill>
        </div>
        <p className="font-mono text-[10px] text-slate-500">
          {status.autonomy_version} · {status.thresholds_version} · topology{" "}
          {status.oob_topology} · checked {formatTime(status.checked_at)}
        </p>
        <p className="text-[10px] leading-relaxed text-slate-600">
          Limited automation: every action type starts at shadow level and only
          a human can raise it. Demotions are deterministic; promotions need
          scorecard thresholds and a config flag.
        </p>
        <KillSwitchControl status={status} onChanged={onChanged} />
      </section>

      <section className="space-y-2.5 rounded-xl border border-white/5 bg-ink-900/80 p-4 shadow-panel">
        <h3 className="text-sm font-semibold text-slate-100">
          Guards per action type
        </h3>
        {status.breakers.map((breaker) => {
          const limit = status.rate_limits.find(
            (rate) => rate.action_id === breaker.action_id,
          );
          const pct = limit
            ? Math.min(
                100,
                Math.round((limit.used_in_window * 100) / limit.max_per_window),
              )
            : 0;
          return (
            <div
              key={breaker.action_id}
              className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-2.5"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={breaker.tripped ? "red" : "green"}>
                  {breaker.tripped ? "breaker tripped" : "breaker ok"}
                </Pill>
                <span className="font-mono text-[11px] text-slate-200">
                  {breaker.action_id}
                </span>
                <span className="text-[10px] text-slate-500">
                  {breaker.consecutive_refusals} consecutive refusals
                </span>
              </div>
              {breaker.tripped && breaker.reason ? (
                <p className="text-[10px] leading-relaxed text-red-300/80">
                  {breaker.reason}
                </p>
              ) : null}
              {limit ? (
                <div className="space-y-1">
                  <p className="text-[10px] text-slate-500">
                    rate limit {limit.used_in_window}/{limit.max_per_window}{" "}
                    simulated per {Math.round(limit.window_seconds / 60)}min
                  </p>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                    <div
                      className={`h-full rounded-full ${pct >= 100 ? "bg-red-400" : "bg-cyan-400"}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              ) : null}
              {breaker.tripped ? (
                <BreakerResetControl
                  actionId={breaker.action_id}
                  onChanged={onChanged}
                />
              ) : null}
            </div>
          );
        })}
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
            Autonomy scorecards · 30d window
          </h3>
          <span className="rounded-full bg-white/5 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">
            {scorecards.length}
          </span>
        </div>
        {scorecards.length ? (
          scorecards.map((card) => (
            <ScorecardCard
              key={card.action_id}
              card={card}
              promotionEnabled={status.promotion_enabled}
              onChanged={onChanged}
            />
          ))
        ) : (
          <EmptyState
            title="No scorecards yet"
            detail="Scorecards appear once an action type is proposed. Shadow level is the default for every catalog action."
          />
        )}
      </section>
    </div>
  );
}

function KillSwitchControl({
  status,
  onChanged,
}: {
  status: AutomationStatus;
  onChanged: () => void;
}) {
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ks = status.kill_switch;

  async function toggle(engaged: boolean) {
    setBusy(true);
    setError(null);
    try {
      await api.setKillSwitch({
        engaged,
        actor: actor.trim(),
        reason: reason.trim(),
      });
      setReason("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kill switch failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`space-y-2 rounded-lg border p-3 ${
        ks.engaged
          ? "border-red-500/30 bg-red-500/[0.08]"
          : "border-emerald-500/20 bg-emerald-500/[0.05]"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Power
          className={`h-4 w-4 ${ks.engaged ? "text-red-300" : "text-emerald-300"}`}
        />
        <span
          className={`text-sm font-semibold ${ks.engaged ? "text-red-200" : "text-emerald-200"}`}
        >
          {ks.engaged ? "Kill switch ENGAGED" : "Kill switch not engaged"}
        </span>
        <Pill>{ks.source}</Pill>
      </div>
      {ks.engaged ? (
        <p className="text-[10px] leading-relaxed text-red-200/80">
          {ks.engaged_by ? `engaged by ${ks.engaged_by}` : "engaged"} ·{" "}
          {formatTime(ks.engaged_at)} · {ks.reason} — approvals and executions
          are refused until released.
        </p>
      ) : (
        <p className="text-[10px] leading-relaxed text-slate-500">
          Engaging stops every approval and execution across all incidents
          instantly. Advisory evaluation keeps working.
        </p>
      )}
      {ks.source === "environment" ? (
        <p className="text-[10px] leading-relaxed text-amber-300/80">
          The KILL_SWITCH environment variable overrides this state — clear it
          in the deployment config first.
        </p>
      ) : null}
      <div className="flex flex-wrap gap-1.5">
        <input
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          placeholder="human actor"
          className={`${inputClass} flex-1 min-w-[8rem]`}
        />
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={ks.engaged ? "release reason" : "engage reason"}
          className={`${inputClass} flex-1 min-w-[12rem]`}
        />
        <button
          type="button"
          disabled={busy || !actor.trim() || !reason.trim()}
          onClick={() => toggle(!ks.engaged)}
          className={
            ks.engaged
              ? actionClass
              : "inline-flex items-center justify-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/15 px-2 py-1.5 text-[10px] font-medium text-red-200 transition hover:border-red-400/50 hover:text-red-100 disabled:opacity-40"
          }
        >
          <Power className="h-3.5 w-3.5" />
          {busy ? "…" : ks.engaged ? "Release" : "Engage"}
        </button>
      </div>
      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}

function BreakerResetControl({
  actionId,
  onChanged,
}: {
  actionId: string;
  onChanged: () => void;
}) {
  const [actor, setActor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reset() {
    setBusy(true);
    setError(null);
    try {
      await api.resetBreaker(actionId, { actor: actor.trim() });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <input
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          placeholder="human actor"
          className={`${inputClass} flex-1 min-w-[8rem]`}
        />
        <button
          type="button"
          disabled={busy || !actor.trim()}
          onClick={reset}
          className={actionClass}
        >
          <Zap className="h-3.5 w-3.5" />
          {busy ? "…" : "Reset breaker"}
        </button>
      </div>
      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}

function ScorecardCard({
  card,
  promotionEnabled,
  onChanged,
}: {
  card: Scorecard;
  promotionEnabled: boolean;
  onChanged: () => void;
}) {
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [level, setLevel] = useState<AutonomyLevel>(card.level);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = card.recommendation;

  async function applyLevel() {
    setBusy(true);
    setError(null);
    try {
      await api.setAutonomyLevel(card.action_id, {
        level,
        actor: actor.trim(),
        reason: reason.trim(),
      });
      setReason("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Level change failed");
    } finally {
      setBusy(false);
    }
  }

  const stats: { label: string; value: number; warn: boolean }[] = [
    { label: "proposals", value: card.stats.proposals, warn: false },
    { label: "allows", value: card.stats.allows, warn: false },
    { label: "simulated", value: card.stats.simulated, warn: false },
    {
      label: "refusals",
      value: card.stats.refusals,
      warn: card.stats.refusals > 0,
    },
    { label: "denies", value: card.stats.denies, warn: card.stats.denies > 0 },
    { label: "escalates", value: card.stats.escalates, warn: false },
    {
      label: "expired approvals",
      value: card.stats.approvals_expired,
      warn: card.stats.approvals_expired > 0,
    },
    {
      label: "breaker trips",
      value: card.stats.breaker_trips,
      warn: card.stats.breaker_trips > 0,
    },
  ];

  return (
    <div className="space-y-2.5 rounded-xl border border-white/5 bg-ink-900/80 p-3.5 shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-semibold text-slate-100">
            {card.catalog?.title ?? card.action_id}
          </h4>
          <Pill tone={autonomyTone[card.level]}>{card.level}</Pill>
        </div>
        <span className="font-mono text-[10px] text-slate-500">
          {card.action_id}
          {card.level_set_by ? ` · set by ${card.level_set_by}` : ""}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-1.5">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-md border border-white/5 bg-black/20 px-2 py-1.5"
          >
            <p
              className={`text-sm font-semibold ${stat.warn ? "text-amber-300" : "text-slate-200"}`}
            >
              {stat.value}
            </p>
            <p className="text-[9px] text-slate-600">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="space-y-1 rounded-lg border border-white/5 bg-black/20 p-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={rec.eligible_for_promotion ? "green" : "slate"}>
            {rec.eligible_for_promotion
              ? "eligible for promotion"
              : "holding at current level"}
          </Pill>
          <span className="font-mono text-[9px] text-slate-600">
            {rec.engine} · {rec.thresholds_version}
          </span>
        </div>
        {rec.promotion_reasons.length ? (
          <ul className="space-y-0.5">
            {rec.promotion_reasons.map((reason, index) => (
              <li
                key={`p-${index}`}
                className="text-[10px] leading-relaxed text-emerald-300/70"
              >
                + {reason}
              </li>
            ))}
          </ul>
        ) : null}
        {rec.hold_reasons.length ? (
          <ul className="space-y-0.5">
            {rec.hold_reasons.map((reason, index) => (
              <li
                key={`h-${index}`}
                className="text-[10px] leading-relaxed text-amber-300/70"
              >
                · {reason}
              </li>
            ))}
          </ul>
        ) : null}
        {rec.demotion_reasons.length ? (
          <ul className="space-y-0.5">
            {rec.demotion_reasons.map((reason, index) => (
              <li
                key={`d-${index}`}
                className="text-[10px] leading-relaxed text-red-300/80"
              >
                ↓ {reason}
                {rec.demotion_target ? ` → ${rec.demotion_target}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {promotionEnabled ? (
        <div className="space-y-1.5">
          <div className="flex flex-wrap gap-1.5">
            <select
              value={level}
              onChange={(event) =>
                setLevel(event.target.value as AutonomyLevel)
              }
              className={`${selectClass} w-28`}
            >
              {autonomyLevels.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <input
              value={actor}
              onChange={(event) => setActor(event.target.value)}
              placeholder="human actor"
              className={`${inputClass} flex-1 min-w-[8rem]`}
            />
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="reason"
              className={`${inputClass} flex-1 min-w-[10rem]`}
            />
            <button
              type="button"
              disabled={busy || !actor.trim() || !reason.trim()}
              onClick={applyLevel}
              className={actionClass}
            >
              <Gauge className="h-3.5 w-3.5" />
              {busy ? "…" : "Set level"}
            </button>
          </div>
          <p className="text-[9px] leading-relaxed text-slate-600">
            Level changes are human-only audited events. Demotion below the
            selected level still applies automatically on refusals.
          </p>
        </div>
      ) : (
        <p className="text-[9px] leading-relaxed text-slate-600">
          Promotion is disabled by configuration — actions hold at shadow
          regardless of scorecard. Enable the autonomy-promotion flag to allow
          level changes.
        </p>
      )}
      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}
