import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  FileText,
  FlaskConical,
  Gauge,
  GitBranch,
  Inbox,
  Network,
  Radio,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Siren,
  Timer,
  TriangleAlert,
  Users,
  XCircle,
} from "lucide-react";

import type {
  Audit,
  AutomationStatus,
  BriefAudience,
  BriefRecord,
  ClockCandidate,
  ContainmentRecord,
  DispatchRecord,
  EventEnvelope,
  Fact,
  HandoffBrief,
  ImpactMapping,
  Incident,
  Proposal,
  ReadinessAssessment,
  Scorecard,
  Signal,
} from "./api";
import { api, formatTime, shortId } from "./api";
import {
  BriefCard,
  ClockCard,
  ContainmentCard,
  DispatchCard,
  EmptyState,
  EventCard,
  AutomationPanel,
  FactRow,
  HandoffCard,
  ImpactCard,
  Metric,
  Panel,
  Pill,
  ProposalCard,
  ReadinessCard,
  SeverityBadge,
  SignalRow,
  Skeleton,
} from "./components";

type Tab =
  | "facts"
  | "decisions"
  | "proposals"
  | "containment"
  | "signals"
  | "briefs"
  | "clocks"
  | "dispatch"
  | "bcp"
  | "handoff"
  | "automation";

interface IncidentSnapshot {
  timeline: EventEnvelope[];
  facts: Fact[];
  decisions: Fact[];
  proposals: Proposal[];
  containment: ContainmentRecord[];
  signals: Signal[];
  briefs: BriefRecord[];
  clocks: ClockCandidate[];
  dispatch: DispatchRecord[];
  impacts: ImpactMapping[];
  readiness: ReadinessAssessment | null;
  handoff: HandoffBrief | null;
}

interface Metrics {
  events: number;
  facts: number;
  disputed: number;
  untrusted: number;
  decisions: number;
  proposals: number;
  signals: number;
  briefs: number;
  clocks: number;
  dispatch: number;
  openAcks: number;
  gaps: number;
}

const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "facts", label: "Facts", icon: ShieldCheck },
  { id: "decisions", label: "Decisions", icon: GitBranch },
  { id: "proposals", label: "Proposals", icon: ShieldAlert },
  { id: "containment", label: "Containment", icon: FlaskConical },
  { id: "signals", label: "Signals", icon: Radio },
  { id: "briefs", label: "Briefs", icon: FileText },
  { id: "clocks", label: "Clocks", icon: Timer },
  { id: "dispatch", label: "Dispatch", icon: Users },
  { id: "bcp", label: "BCP", icon: Network },
  { id: "handoff", label: "Handoff", icon: ClipboardCheck },
  { id: "automation", label: "Auto", icon: Gauge },
];

const LINKEDIN_URL = "https://www.linkedin.com/in/sanjeet-sharma-cissp-17b68570/";

function LinkedinBadge({ className = "" }: { className?: string }) {
  return (
    <a
      href={LINKEDIN_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Sanjeet Sharma on LinkedIn"
      title="Sanjeet Sharma on LinkedIn"
      className={`inline-flex shrink-0 transition hover:opacity-100 ${className}`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-hidden="true"
        className="h-3 w-3"
      >
        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.125 2.062 2.062 0 0 1 0 4.125zM7.119 20.452H3.554V9h3.565v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
      </svg>
    </a>
  );
}

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<IncidentSnapshot | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [automation, setAutomation] = useState<AutomationStatus | null>(null);
  const [scorecards, setScorecards] = useState<Scorecard[]>([]);
  const [tab, setTab] = useState<Tab>("facts");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const activeIdRef = useRef<string | null>(null);

  const refresh = useCallback(async (incidentId: string) => {
    const [
      timeline,
      facts,
      decisions,
      proposals,
      containment,
      signals,
      briefs,
      clocks,
      dispatch,
      impacts,
      readiness,
      handoff,
      auditResult,
      automationStatus,
      scorecardList,
    ] = await Promise.all([
      api.timeline(incidentId),
      api.facts(incidentId),
      api.decisions(incidentId),
      api.proposals(incidentId),
      api.containment(incidentId),
      api.signals(incidentId),
      api.briefs(incidentId),
      api.clocks(incidentId),
      api.dispatch(incidentId),
      api.impacts(incidentId),
      api.readiness(incidentId),
      api.handoff(incidentId),
      api.audit(),
      api.automationStatus(),
      api.scorecards(),
    ]);

    if (activeIdRef.current !== incidentId) return;

    setSnapshot({
      timeline,
      facts,
      decisions,
      proposals,
      containment,
      signals,
      briefs,
      clocks,
      dispatch,
      impacts,
      readiness,
      handoff,
    });
    setAudit(auditResult);
    setAutomation(automationStatus);
    setScorecards(scorecardList);
    setLastUpdated(new Date());
    setError(null);
  }, []);

  useEffect(() => {
    activeIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    let cancelled = false;

    async function loadIncidents() {
      try {
        const list = await api.incidents();
        if (cancelled) return;
        setIncidents(list);
        setSelectedId((current) => {
          if (current && list.some((incident) => incident.id === current)) {
            return current;
          }
          return list[0]?.id ?? null;
        });
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load incidents");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadIncidents();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    setSnapshot(null);

    async function tick(initial: boolean) {
      if (initial) setLoading(true);
      else setRefreshing(true);
      try {
        if (initial) {
          await refresh(selectedId!);
        } else {
          const list = await api.incidents();
          if (!cancelled) setIncidents(list);
          await refresh(selectedId!);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load incident");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    tick(true);
    const timer = window.setInterval(() => {
      if (!cancelled) tick(false);
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedId, refresh]);

  const selectedIncident = useMemo(
    () => incidents.find((incident) => incident.id === selectedId) ?? null,
    [incidents, selectedId],
  );

  const metrics = useMemo<Metrics | null>(() => {
    if (!snapshot) return null;
    const activeFacts = snapshot.facts.filter(
      (fact) => fact.status !== "superseded" && fact.status !== "retracted",
    );
    return {
      events: snapshot.timeline.length,
      facts: activeFacts.length,
      disputed: snapshot.facts.filter((fact) => fact.status === "disputed").length,
      untrusted: snapshot.facts.filter((fact) => fact.trust === "untrusted").length,
      decisions: snapshot.decisions.length,
      proposals: snapshot.proposals.length,
      signals: snapshot.signals.length,
      briefs: snapshot.briefs.length,
      clocks: snapshot.clocks.length,
      dispatch: snapshot.dispatch.length,
      openAcks: snapshot.dispatch.filter(
        (record) =>
          record.assignment !== null && record.assignment.status !== "acked",
      ).length,
      gaps: snapshot.handoff?.evidence_gaps.length ?? 0,
    };
  }, [snapshot]);

  const counts: Record<Tab, number> = {
    facts: snapshot?.facts.length ?? 0,
    decisions: snapshot?.decisions.length ?? 0,
    proposals: snapshot?.proposals.length ?? 0,
    containment: snapshot?.containment.length ?? 0,
    signals: snapshot?.signals.length ?? 0,
    briefs: snapshot?.briefs.length ?? 0,
    clocks: snapshot?.clocks.length ?? 0,
    dispatch: snapshot?.dispatch.length ?? 0,
    bcp: snapshot?.impacts.length ?? 0,
    handoff: snapshot?.handoff ? 1 : 0,
    automation: scorecards.length,
  };

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-20 border-b border-white/5 bg-ink-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-400/20 bg-cyan-400/10">
              <Siren className="h-4.5 w-4.5 text-cyan-300" />
            </div>
            <div>
              <div className="flex items-baseline gap-2">
                <h1 className="text-sm font-semibold tracking-[0.18em] text-slate-100">
                  ADJUTANT
                </h1>
                <span className="text-[10px] text-slate-500">
                  by Sanjeet Sharma
                </span>
                <LinkedinBadge className="self-center text-slate-600 hover:text-cyan-300" />
              </div>
              <p className="text-[10px] text-slate-500">
                Incident coordination · human-commanded · advisory AI
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <AuditChip audit={audit} />
            <div className="hidden items-center gap-1.5 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1.5 text-[10px] text-slate-500 sm:flex">
              <Clock3 className="h-3.5 w-3.5" />
              {lastUpdated ? formatTime(lastUpdated.toISOString()) : "never"}
            </div>
            <button
              type="button"
              onClick={() => selectedId && refresh(selectedId)}
              disabled={!selectedId || refreshing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 transition hover:border-cyan-400/30 hover:text-white disabled:opacity-40"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
              />
              Refresh
            </button>
          </div>
        </div>
      </header>

      {error ? (
        <div className="mx-auto mt-3 flex w-full max-w-[1600px] items-center gap-2 px-5">
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            <TriangleAlert className="h-4 w-4" />
            API error: {error}
          </div>
        </div>
      ) : null}

      <main className="mx-auto grid w-full max-w-[1600px] flex-1 gap-4 px-5 py-4 lg:grid-cols-[280px_minmax(0,1fr)_370px]">
        <IncidentRail
          incidents={incidents}
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            setTab("facts");
          }}
        />

        <section className="min-w-0 space-y-4">
          {loading && !selectedIncident ? (
            <Skeleton className="h-40 w-full" />
          ) : selectedIncident ? (
            <IncidentHeader incident={selectedIncident} metrics={metrics} />
          ) : (
            <EmptyState
              title="No incidents recorded"
              detail="Start the stack with SEED_DEMO=true to load the synthetic ransomware scenario."
            />
          )}

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-cyan-300" />
              <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                Event timeline
              </h2>
              <span className="rounded-full bg-white/5 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">
                {snapshot?.timeline.length ?? 0}
              </span>
            </div>
            <span className="inline-flex items-center gap-1.5 text-[10px] text-slate-600">
              <span className="live-dot h-1.5 w-1.5 rounded-full bg-emerald-400" />
              live · 5s poll
            </span>
          </div>

          <div className="space-y-3">
            {loading && !snapshot ? (
              <>
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </>
            ) : snapshot && snapshot.timeline.length ? (
              snapshot.timeline.map((event) => (
                <EventCard key={event.id} event={event} />
              ))
            ) : (
              <EmptyState
                title="Timeline is empty"
                detail="Signals and facts appended to this incident will appear here in order."
              />
            )}
          </div>
        </section>

        <aside className="min-w-0 space-y-3">
          <div className="grid grid-cols-3 gap-1 rounded-xl border border-white/5 bg-ink-900/60 p-1">
            {tabs.map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`flex flex-col items-center gap-1 rounded-lg px-1 py-2 text-[10px] font-medium transition ${
                    active
                      ? "bg-cyan-400/10 text-cyan-200 ring-1 ring-inset ring-cyan-400/25"
                      : "text-slate-500 hover:bg-white/5 hover:text-slate-300"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span className="flex items-center gap-1">
                    {item.label}
                    <span className="font-mono text-[9px] text-slate-600">
                      {counts[item.id]}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          {tab === "facts" ? (
            <Panel title="Fact ledger" count={snapshot?.facts.length ?? 0}>
              {snapshot?.facts.length ? (
                snapshot.facts.map((fact) => <FactRow key={fact.id} fact={fact} />)
              ) : (
                <p className="px-1 py-4 text-center text-xs text-slate-600">
                  No facts recorded yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "decisions" ? (
            <Panel title="Decision log" count={snapshot?.decisions.length ?? 0}>
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                Decisions are first-class facts with a{" "}
                <span className="font-mono text-slate-500">decision/</span>{" "}
                attribute, so they carry the same provenance as everything else.
              </p>
              {snapshot?.decisions.length ? (
                snapshot.decisions.map((decision) => (
                  <FactRow key={decision.id} fact={decision} />
                ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No decisions logged yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "proposals" ? (
            <Panel title="Action proposals" count={snapshot?.proposals.length ?? 0}>
              <div className="flex items-start gap-2 rounded-lg border border-amber-400/15 bg-amber-400/[0.04] p-2 text-[10px] leading-relaxed text-amber-200/80">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Proposals are advisory. Adjutant never executes containment; a human
                approves every action.
              </div>
              {snapshot?.proposals.length ? (
                snapshot.proposals.map((proposal) => (
                  <ProposalCard key={proposal.id} proposal={proposal} />
                ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No proposals raised yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "containment" ? (
            <Panel
              title="Containment advisor"
              count={snapshot?.containment.length ?? 0}
            >
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                Advisory only. The policy gate decides allow / deny / escalate
                from the catalog and cited evidence; approvals are signed and
                expire; the executor is dry-run only and refuses real actions.
                Never-automate actions always escalate.
              </p>
              {snapshot?.containment.length ? (
                snapshot.containment
                  .slice()
                  .reverse()
                  .map((record) => (
                    <ContainmentCard
                      key={record.proposal.id}
                      record={record}
                      incidentId={selectedId!}
                      channel={automation?.approval_channel ?? "in-band"}
                      onChanged={() => refresh(selectedId!)}
                    />
                  ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No action proposals to advise on yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "signals" ? (
            <Panel title="Quarantined signals" count={snapshot?.signals.length ?? 0}>
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                Raw inbound content is untrusted. Only allowlisted fields become typed
                facts.
              </p>
              {snapshot?.signals.length ? (
                snapshot.signals.map((signal) => (
                  <SignalRow key={signal.id} signal={signal} />
                ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No signals ingested yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "briefs" ? (
            <Panel title="Audience briefs" count={snapshot?.briefs.length ?? 0}>
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                Claims are generated deterministically from evidenced facts and
                re-verified by the gate at approval and send. No model writes
                prose here.
              </p>
              {selectedId ? (
                <BriefComposer
                  incidentId={selectedId}
                  onChanged={() => refresh(selectedId)}
                />
              ) : null}
              {snapshot?.briefs.length ? (
                snapshot.briefs.map((record) => (
                  <BriefCard
                    key={record.brief.id}
                    record={record}
                    incidentId={selectedId!}
                    onChanged={() => refresh(selectedId!)}
                  />
                ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No briefs drafted yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "clocks" ? (
            <Panel title="Regulatory clocks" count={snapshot?.clocks.length ?? 0}>
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                The clock engine proposes deadlines as candidates from typed
                triggers. A deadline only binds after a legal or DPO attestation.
              </p>
              {snapshot?.clocks.length ? (
                snapshot.clocks.map((clock) => (
                  <ClockCard
                    key={clock.id}
                    clock={clock}
                    incidentId={selectedId!}
                    onChanged={() => refresh(selectedId!)}
                  />
                ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No clocks proposed yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "dispatch" ? (
            <Panel title="Dispatch board" count={snapshot?.dispatch.length ?? 0}>
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                Owners resolve through a fixed fallback chain with recorded
                confidence and per-source steps. Unknown owners are a first-class
                outcome, never an empty string. Acknowledgements are human-only
                and SLA-tracked.
              </p>
              {selectedId ? (
                <DispatchActions
                  incidentId={selectedId}
                  onChanged={() => refresh(selectedId)}
                />
              ) : null}
              {snapshot?.dispatch.length ? (
                snapshot.dispatch
                  .slice()
                  .reverse()
                  .map((record) => (
                    <DispatchCard
                      key={record.resolution.id}
                      record={record}
                      incidentId={selectedId!}
                      onChanged={() => refresh(selectedId!)}
                    />
                  ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No assets resolved yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "bcp" ? (
            <Panel
              title="Business impact & readiness"
              count={snapshot?.impacts.length ?? 0}
            >
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                BIA values come only from typed service facts. Missing RTO, RPO,
                or service mappings surface as gaps instead of guessed numbers.
                Unknown integration or DR evidence fails safe to manual.
              </p>
              {selectedId ? (
                <BcpActions
                  incidentId={selectedId}
                  onChanged={() => refresh(selectedId)}
                />
              ) : null}
              {snapshot?.impacts.length ? (
                snapshot.impacts.map((mapping) => (
                  <ImpactCard key={mapping.id} mapping={mapping} />
                ))
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No impact mapping yet.
                </p>
              )}
              {snapshot?.readiness ? (
                <ReadinessCard assessment={snapshot.readiness} />
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No readiness assessment yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "handoff" ? (
            <Panel title="Shift handoff" count={snapshot?.handoff ? 1 : 0}>
              <p className="px-1 text-[10px] leading-relaxed text-slate-600">
                The handoff is assembled from projections and verified counts:
                open approvals, open acknowledgements, evidence gaps, pending
                clocks, and readiness. It is display-only — no send path exists.
              </p>
              {selectedId ? (
                <HandoffActions
                  incidentId={selectedId}
                  onChanged={() => refresh(selectedId)}
                />
              ) : null}
              {snapshot?.handoff ? (
                <HandoffCard
                  handoff={snapshot.handoff}
                  incidentId={selectedId!}
                  onChanged={() => refresh(selectedId!)}
                />
              ) : (
                <p className="py-2 text-center text-xs text-slate-600">
                  No handoff drafted yet.
                </p>
              )}
            </Panel>
          ) : null}

          {tab === "automation" ? (
            <AutomationPanel
              status={automation}
              scorecards={scorecards}
              onChanged={() => selectedId && refresh(selectedId)}
            />
          ) : null}
        </aside>
      </main>

      <footer className="mx-auto flex w-full max-w-[1600px] flex-wrap items-center justify-between gap-2 border-t border-white/5 px-5 py-3 text-[10px] text-slate-600">
        <span>
          Adjutant by Sanjeet Sharma
          <LinkedinBadge className="ml-1 align-middle text-slate-600 hover:text-cyan-300" />{" "}
          · synthetic demo environment · briefs are gate-checked, sends are
          human-approved, clocks are legal-confirmed, dispatch is human-acked,
          handoffs are display-only, containment is dry-run only, automation is
          guarded by an independent kill switch
        </span>
        <span className="font-mono">
          {selectedIncident ? `incident ${shortId(selectedIncident.id)}` : "—"}
          {audit ? ` · audit ${audit.entries} entries` : ""}
        </span>
      </footer>
    </div>
  );
}

const audiences: { id: BriefAudience; label: string }[] = [
  { id: "ic", label: "IC" },
  { id: "exec", label: "Exec" },
  { id: "technical", label: "Technical" },
  { id: "legal", label: "Legal" },
];

function BriefComposer({
  incidentId,
  onChanged,
}: {
  incidentId: string;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<BriefAudience | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function draft(audience: BriefAudience) {
    setBusy(audience);
    setError(null);
    try {
      await api.createBrief(incidentId, audience);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to draft brief");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-lg border border-white/5 bg-black/20 p-2.5">
      <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
        Draft brief for
      </p>
      <div className="mt-1.5 grid grid-cols-4 gap-1">
        {audiences.map((audience) => (
          <button
            key={audience.id}
            type="button"
            onClick={() => draft(audience.id)}
            disabled={busy !== null}
            className="rounded-lg border border-white/10 bg-white/5 px-1 py-1.5 text-[10px] font-medium text-slate-300 transition hover:border-cyan-400/30 hover:text-white disabled:opacity-40"
          >
            {busy === audience.id ? "…" : audience.label}
          </button>
        ))}
      </div>
      {error ? (
        <p className="mt-1.5 text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : (
        <p className="mt-1.5 text-[9px] leading-relaxed text-slate-600">
          Delta since the last brief for that audience. If no cited facts
          qualify, drafting is refused.
        </p>
      )}
    </div>
  );
}

const actionButton =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-[10px] font-medium text-slate-300 transition hover:border-cyan-400/30 hover:text-white disabled:opacity-40";

function DispatchActions({
  incidentId,
  onChanged,
}: {
  incidentId: string;
  onChanged: () => void;
}) {
  const [asset, setAsset] = useState("");
  const [busy, setBusy] = useState<"resolve" | "evaluate" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: "resolve" | "evaluate") {
    if (kind === "resolve" && !asset.trim()) return;
    setBusy(kind);
    setError(null);
    try {
      if (kind === "resolve") {
        await api.resolveDispatch(incidentId, asset.trim());
        setAsset("");
      } else {
        await api.evaluateDispatch(incidentId);
      }
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dispatch action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-2.5">
      <div className="flex gap-1.5">
        <input
          value={asset}
          onChange={(event) => setAsset(event.target.value)}
          placeholder="asset id, e.g. FIN-SRV-0007"
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-slate-200 outline-none placeholder:text-slate-600 focus:border-cyan-400/40"
        />
        <button
          type="button"
          onClick={() => run("resolve")}
          disabled={busy !== null || !asset.trim()}
          className={actionButton}
        >
          <Users className="h-3.5 w-3.5" />
          {busy === "resolve" ? "…" : "Resolve"}
        </button>
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[9px] leading-relaxed text-slate-600">
          Deterministic fallback chain · no model involved
        </p>
        <button
          type="button"
          onClick={() => run("evaluate")}
          disabled={busy !== null}
          className={actionButton}
        >
          <Timer className="h-3.5 w-3.5" />
          {busy === "evaluate" ? "…" : "Evaluate SLAs"}
        </button>
      </div>
      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}

function BcpActions({
  incidentId,
  onChanged,
}: {
  incidentId: string;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<"impact" | "readiness" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: "impact" | "readiness") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "impact") await api.mapImpact(incidentId);
      else await api.assessReadiness(incidentId);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "BCP action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-2.5">
      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          onClick={() => run("impact")}
          disabled={busy !== null}
          className={actionButton}
        >
          <GitBranch className="h-3.5 w-3.5" />
          {busy === "impact" ? "…" : "Map impact"}
        </button>
        <button
          type="button"
          onClick={() => run("readiness")}
          disabled={busy !== null}
          className={actionButton}
        >
          <Network className="h-3.5 w-3.5" />
          {busy === "readiness" ? "…" : "Assess readiness"}
        </button>
      </div>
      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}

function HandoffActions({
  incidentId,
  onChanged,
}: {
  incidentId: string;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function draft() {
    setBusy(true);
    setError(null);
    try {
      await api.createHandoff(incidentId);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to draft handoff");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-2.5">
      <button
        type="button"
        onClick={draft}
        disabled={busy}
        className={`${actionButton} w-full`}
      >
        <ClipboardCheck className="h-3.5 w-3.5" />
        {busy ? "Assembling…" : "Draft new handoff"}
      </button>
      {error ? (
        <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
      ) : null}
    </div>
  );
}

function AuditChip({ audit }: { audit: Audit | null }) {  if (!audit) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1.5 text-[10px] text-slate-500">
        <Inbox className="h-3.5 w-3.5" />
        audit pending
      </div>
    );
  }

  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[10px] ${
        audit.valid
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
          : "border-red-500/25 bg-red-500/10 text-red-300"
      }`}
      title={
        audit.valid
          ? `Hash chain intact across ${audit.entries} entries`
          : (audit.reason ?? "Hash chain broken")
      }
    >
      {audit.valid ? (
        <CheckCircle2 className="h-3.5 w-3.5" />
      ) : (
        <XCircle className="h-3.5 w-3.5" />
      )}
      {audit.valid ? "audit verified" : "audit broken"}
      <span className="font-mono text-[9px] opacity-70">{audit.entries}</span>
    </div>
  );
}

function IncidentRail({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="min-w-0 space-y-3">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
          Incidents
        </h2>
        <span className="rounded-full bg-white/5 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">
          {incidents.length}
        </span>
      </div>

      {incidents.length ? (
        <div className="space-y-2">
          {incidents.map((incident) => {
            const active = incident.id === selectedId;
            return (
              <button
                key={incident.id}
                type="button"
                onClick={() => onSelect(incident.id)}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  active
                    ? "border-cyan-400/25 bg-cyan-400/[0.06] shadow-panel"
                    : "border-white/5 bg-ink-900/50 hover:border-white/10 hover:bg-ink-900"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <SeverityBadge severity={incident.severity} />
                  <Pill tone={incident.status === "declared" ? "amber" : "green"}>
                    {incident.status}
                  </Pill>
                </div>
                <p
                  className={`mt-2 text-xs font-medium leading-snug ${
                    active ? "text-slate-100" : "text-slate-300"
                  }`}
                >
                  {incident.title}
                </p>
                <p className="mt-1.5 font-mono text-[9px] text-slate-600">
                  {formatTime(incident.declared_at)} · {incident.declared_by}
                </p>
              </button>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="No incidents"
          detail="Seeded demo data appears here when the stack starts."
        />
      )}

      <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
        <p className="text-[10px] leading-relaxed text-slate-600">
          Event-sourced state. Every timeline entry is hash-chained, append-only, and
          replayable.
        </p>
      </div>
    </aside>
  );
}

function IncidentHeader({
  incident,
  metrics,
}: {
  incident: Incident;
  metrics: Metrics | null;
}) {
  const synthetic = incident.title.toUpperCase().startsWith("SYNTHETIC");

  return (
    <section className="overflow-hidden rounded-2xl border border-white/5 bg-ink-900/70 shadow-panel">
      <div className="border-b border-white/5 bg-gradient-to-r from-cyan-400/[0.06] via-transparent to-violet-400/[0.05] px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={incident.severity} />
          <Pill tone={incident.status === "declared" ? "amber" : "green"}>
            {incident.status}
          </Pill>
          {synthetic ? <Pill tone="violet">synthetic data</Pill> : null}
          <span className="ml-auto font-mono text-[10px] text-slate-500">
            {incident.id}
          </span>
        </div>
        <h2 className="mt-2 text-lg font-semibold leading-snug text-slate-100">
          {incident.title}
        </h2>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
          {incident.summary ?? "No summary provided."}
        </p>
        <p className="mt-2 font-mono text-[10px] text-slate-600">
          declared {formatTime(incident.declared_at)} by {incident.declared_by}
        </p>
      </div>

      <div className="flex flex-wrap gap-2 px-5 py-3">
        {metrics ? (
          <>
            <Metric label="events" value={metrics.events} />
            <Metric label="facts" value={metrics.facts} />
            <Metric label="disputed" value={metrics.disputed} />
            <Metric label="untrusted" value={metrics.untrusted} />
            <Metric label="decisions" value={metrics.decisions} />
            <Metric label="proposals" value={metrics.proposals} />
            <Metric label="signals" value={metrics.signals} />
            <Metric label="briefs" value={metrics.briefs} />
            <Metric label="clocks" value={metrics.clocks} />
            <Metric label="dispatch" value={metrics.dispatch} />
            <Metric label="open acks" value={metrics.openAcks} />
            <Metric label="gaps" value={metrics.gaps} />
          </>
        ) : (
          <div className="flex gap-2">
            <Skeleton className="h-14 w-20" />
            <Skeleton className="h-14 w-20" />
            <Skeleton className="h-14 w-20" />
          </div>
        )}
      </div>
    </section>
  );
}
