from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, store
from .config import Settings, get_settings
from .db import init_db, make_pool
from .errors import ConflictError, NotFoundError, PolicyViolation
from .models import (
    ActionCatalogEntry,
    ActionProposal,
    ActionProposalCreate,
    Approval,
    ApprovalCreate,
    ApprovalRequest,
    AuditVerification,
    AutonomyLevelRequest,
    AutomationStatus,
    BreakerResetRequest,
    BreakerState,
    BriefApprovalCreate,
    BriefCheck,
    BriefCreate,
    BriefRecord,
    BriefSendCreate,
    ClockCandidate,
    ClockCandidateCreate,
    ClockConfirmation,
    ContainmentRecord,
    DispatchAckCreate,
    DispatchRecord,
    DispatchResolveCreate,
    EventEnvelope,
    ExecutionRequest,
    ExecutionResult,
    Fact,
    FactCreate,
    FactStatusChange,
    HandoffAcknowledgment,
    HandoffBrief,
    ImpactMapping,
    Incident,
    IncidentCreate,
    KillSwitchRequest,
    KillSwitchState,
    OobApprovalCreate,
    OobSignRequest,
    OobSignResult,
    PolicyDecision,
    ReadinessAssessment,
    Scorecard,
    Signal,
    SignalCreate,
    SignalIngestResult,
)
from .ports.model import get_model_port
from .seed import seed_demo

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = make_pool(settings.database_url)
        await pool.open()
        await init_db(pool)
        if settings.seed_demo:
            await seed_demo(pool)
        app.state.pool = pool
        app.state.model = get_model_port(settings.model_provider)
        try:
            yield
        finally:
            await pool.close()

    app = FastAPI(
        title="Adjutant",
        version=__version__,
        description=(
            "The Incident Commander's chief of staff. Phase 5: event-sourced "
            "incident state, gated briefs, legal-confirmed clocks, "
            "deterministic dispatch, BIA/readiness, a display-only handoff, "
            "a containment advisor with signed approvals and a dry-run-only "
            "executor, and limited-automation guards — autonomy scorecards, "
            "rate limits, circuit breakers, an independent kill switch, and "
            "an out-of-band approval channel."
        ),
        lifespan=lifespan,
    )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(
        request: Request, exc: NotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(
        request: Request, exc: ConflictError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(PolicyViolation)
    async def policy_handler(
        request: Request, exc: PolicyViolation
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    async def require_incident(request: Request, incident_id: UUID) -> Incident:
        incident = await store.get_incident(request.app.state.pool, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        return incident

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "Adjutant",
            "version": __version__,
            "docs": "/docs",
            "ui": "/ui",
            "mode": settings.app_env,
        }

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        async with request.app.state.pool.connection() as conn:
            await conn.execute("SELECT 1")
        return {"status": "ok", "app": "Adjutant"}

    @app.post("/incidents", response_model=Incident, status_code=201)
    async def create_incident(request: Request, body: IncidentCreate) -> Incident:
        return await store.create_incident(request.app.state.pool, body)

    @app.get("/incidents", response_model=list[Incident])
    async def list_incidents(request: Request) -> list[Incident]:
        return await store.list_incidents(request.app.state.pool)

    @app.get("/incidents/{incident_id}", response_model=Incident)
    async def get_incident(request: Request, incident_id: UUID) -> Incident:
        return await require_incident(request, incident_id)

    @app.post("/incidents/{incident_id}/facts", response_model=Fact, status_code=201)
    async def create_fact(
        request: Request, incident_id: UUID, body: FactCreate
    ) -> Fact:
        await require_incident(request, incident_id)
        try:
            return await store.append_fact(request.app.state.pool, incident_id, body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/incidents/{incident_id}/facts", response_model=list[Fact])
    async def list_facts(
        request: Request, incident_id: UUID, include_history: bool = False
    ) -> list[Fact]:
        await require_incident(request, incident_id)
        return await store.list_facts(
            request.app.state.pool, incident_id, include_history=include_history
        )

    @app.post(
        "/incidents/{incident_id}/signals",
        response_model=SignalIngestResult,
        status_code=201,
    )
    async def ingest_signal(
        request: Request, incident_id: UUID, body: SignalCreate
    ) -> SignalIngestResult:
        await require_incident(request, incident_id)
        return await store.ingest_signal(
            request.app.state.pool,
            incident_id,
            body,
            request.app.state.model,
        )

    @app.get(
        "/incidents/{incident_id}/signals",
        response_model=list[Signal],
    )
    async def list_signals(
        request: Request, incident_id: UUID
    ) -> list[Signal]:
        await require_incident(request, incident_id)
        return await store.list_signals(request.app.state.pool, incident_id)

    @app.get(
        "/incidents/{incident_id}/decisions",
        response_model=list[Fact],
    )
    async def list_decisions(
        request: Request, incident_id: UUID
    ) -> list[Fact]:
        await require_incident(request, incident_id)
        return await store.list_decisions(request.app.state.pool, incident_id)

    @app.patch(
        "/incidents/{incident_id}/facts/{fact_id}/status",
        response_model=dict,
    )
    async def change_fact_status(
        request: Request,
        incident_id: UUID,
        fact_id: UUID,
        body: FactStatusChange,
    ) -> dict[str, str]:
        await require_incident(request, incident_id)
        try:
            await store.change_fact_status(
                request.app.state.pool, incident_id, fact_id, body
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"fact_id": str(fact_id), "status": body.status.value}

    @app.get(
        "/incidents/{incident_id}/timeline",
        response_model=list[EventEnvelope],
    )
    async def timeline(
        request: Request, incident_id: UUID
    ) -> list[EventEnvelope]:
        await require_incident(request, incident_id)
        return await store.list_timeline(request.app.state.pool, incident_id)

    @app.post(
        "/incidents/{incident_id}/proposals",
        response_model=ActionProposal,
        status_code=201,
    )
    async def create_proposal(
        request: Request, incident_id: UUID, body: ActionProposalCreate
    ) -> ActionProposal:
        await require_incident(request, incident_id)
        return await store.create_proposal(
            request.app.state.pool, incident_id, body
        )

    @app.get(
        "/incidents/{incident_id}/proposals",
        response_model=list[ActionProposal],
    )
    async def list_proposals(
        request: Request, incident_id: UUID
    ) -> list[ActionProposal]:
        await require_incident(request, incident_id)
        return await store.list_proposals(request.app.state.pool, incident_id)

    @app.post(
        "/incidents/{incident_id}/briefs",
        response_model=BriefRecord,
        status_code=201,
    )
    async def create_brief(
        request: Request, incident_id: UUID, body: BriefCreate
    ) -> BriefRecord:
        await require_incident(request, incident_id)
        return await store.create_brief(
            request.app.state.pool, incident_id, body
        )

    @app.get(
        "/incidents/{incident_id}/briefs",
        response_model=list[BriefRecord],
    )
    async def list_briefs(
        request: Request, incident_id: UUID
    ) -> list[BriefRecord]:
        await require_incident(request, incident_id)
        return await store.list_briefs(request.app.state.pool, incident_id)

    @app.get(
        "/incidents/{incident_id}/briefs/{brief_id}",
        response_model=BriefRecord,
    )
    async def get_brief(
        request: Request, incident_id: UUID, brief_id: UUID
    ) -> BriefRecord:
        await require_incident(request, incident_id)
        return await store.get_brief_record(
            request.app.state.pool, incident_id, brief_id
        )

    @app.post(
        "/incidents/{incident_id}/briefs/{brief_id}/check",
        response_model=BriefCheck,
    )
    async def check_brief(
        request: Request, incident_id: UUID, brief_id: UUID
    ) -> BriefCheck:
        await require_incident(request, incident_id)
        return await store.check_brief_record(
            request.app.state.pool, incident_id, brief_id
        )

    @app.post(
        "/incidents/{incident_id}/briefs/{brief_id}/approve",
        response_model=BriefRecord,
    )
    async def approve_brief(
        request: Request,
        incident_id: UUID,
        brief_id: UUID,
        body: BriefApprovalCreate,
    ) -> BriefRecord:
        await require_incident(request, incident_id)
        return await store.approve_brief(
            request.app.state.pool, incident_id, brief_id, body
        )

    @app.post(
        "/incidents/{incident_id}/briefs/{brief_id}/send",
        response_model=BriefRecord,
    )
    async def send_brief(
        request: Request,
        incident_id: UUID,
        brief_id: UUID,
        body: BriefSendCreate,
    ) -> BriefRecord:
        await require_incident(request, incident_id)
        return await store.send_brief_mock(
            request.app.state.pool, incident_id, brief_id, body
        )

    @app.post(
        "/incidents/{incident_id}/clocks",
        response_model=ClockCandidate,
        status_code=201,
    )
    async def create_clock(
        request: Request, incident_id: UUID, body: ClockCandidateCreate
    ) -> ClockCandidate:
        await require_incident(request, incident_id)
        return await store.create_clock_candidate(
            request.app.state.pool, incident_id, body
        )

    @app.get(
        "/incidents/{incident_id}/clocks",
        response_model=list[ClockCandidate],
    )
    async def list_clocks(
        request: Request, incident_id: UUID
    ) -> list[ClockCandidate]:
        await require_incident(request, incident_id)
        return await store.list_clocks(request.app.state.pool, incident_id)

    @app.post(
        "/incidents/{incident_id}/clocks/{clock_id}/confirm",
        response_model=ClockCandidate,
    )
    async def confirm_clock(
        request: Request,
        incident_id: UUID,
        clock_id: UUID,
        body: ClockConfirmation,
    ) -> ClockCandidate:
        await require_incident(request, incident_id)
        return await store.confirm_clock(
            request.app.state.pool, incident_id, clock_id, body
        )

    @app.post(
        "/incidents/{incident_id}/dispatch/resolve",
        response_model=DispatchRecord,
        status_code=201,
    )
    async def resolve_dispatch(
        request: Request, incident_id: UUID, body: DispatchResolveCreate
    ) -> DispatchRecord:
        await require_incident(request, incident_id)
        return await store.resolve_dispatch(
            request.app.state.pool, incident_id, body
        )

    @app.get(
        "/incidents/{incident_id}/dispatch",
        response_model=list[DispatchRecord],
    )
    async def list_dispatch(
        request: Request, incident_id: UUID
    ) -> list[DispatchRecord]:
        await require_incident(request, incident_id)
        return await store.list_dispatch(request.app.state.pool, incident_id)

    @app.post(
        "/incidents/{incident_id}/dispatch/evaluate",
        response_model=list[DispatchRecord],
    )
    async def evaluate_dispatch(
        request: Request, incident_id: UUID
    ) -> list[DispatchRecord]:
        await require_incident(request, incident_id)
        return await store.evaluate_dispatch(
            request.app.state.pool, incident_id
        )

    @app.post(
        "/incidents/{incident_id}/dispatch/{assignment_id}/ack",
        response_model=DispatchRecord,
    )
    async def ack_dispatch(
        request: Request,
        incident_id: UUID,
        assignment_id: UUID,
        body: DispatchAckCreate,
    ) -> DispatchRecord:
        await require_incident(request, incident_id)
        return await store.ack_dispatch(
            request.app.state.pool, incident_id, assignment_id, body
        )

    @app.post(
        "/incidents/{incident_id}/impact",
        response_model=list[ImpactMapping],
        status_code=201,
    )
    async def map_impact(
        request: Request, incident_id: UUID
    ) -> list[ImpactMapping]:
        await require_incident(request, incident_id)
        return await store.map_impact(request.app.state.pool, incident_id)

    @app.get(
        "/incidents/{incident_id}/impact",
        response_model=list[ImpactMapping],
    )
    async def list_impacts(
        request: Request, incident_id: UUID
    ) -> list[ImpactMapping]:
        await require_incident(request, incident_id)
        return await store.list_impacts(request.app.state.pool, incident_id)

    @app.post(
        "/incidents/{incident_id}/readiness",
        response_model=ReadinessAssessment,
        status_code=201,
    )
    async def assess_readiness(
        request: Request, incident_id: UUID
    ) -> ReadinessAssessment:
        await require_incident(request, incident_id)
        return await store.assess_readiness(
            request.app.state.pool, incident_id
        )

    @app.get(
        "/incidents/{incident_id}/readiness",
        response_model=ReadinessAssessment,
    )
    async def latest_readiness(
        request: Request, incident_id: UUID
    ) -> ReadinessAssessment:
        await require_incident(request, incident_id)
        assessment = await store.latest_readiness(
            request.app.state.pool, incident_id
        )
        if assessment is None:
            raise HTTPException(status_code=404, detail="no readiness assessment")
        return assessment

    @app.post(
        "/incidents/{incident_id}/handoff",
        response_model=HandoffBrief,
        status_code=201,
    )
    async def create_handoff(
        request: Request, incident_id: UUID
    ) -> HandoffBrief:
        await require_incident(request, incident_id)
        return await store.create_handoff(request.app.state.pool, incident_id)

    @app.get(
        "/incidents/{incident_id}/handoff",
        response_model=HandoffBrief,
    )
    async def latest_handoff(
        request: Request, incident_id: UUID
    ) -> HandoffBrief:
        await require_incident(request, incident_id)
        handoff = await store.latest_handoff(
            request.app.state.pool, incident_id
        )
        if handoff is None:
            raise HTTPException(status_code=404, detail="no handoff brief")
        return handoff

    @app.post(
        "/incidents/{incident_id}/handoff/{handoff_id}/acknowledge",
        response_model=HandoffBrief,
    )
    async def acknowledge_handoff(
        request: Request,
        incident_id: UUID,
        handoff_id: UUID,
        body: HandoffAcknowledgment,
    ) -> HandoffBrief:
        await require_incident(request, incident_id)
        return await store.acknowledge_handoff(
            request.app.state.pool, incident_id, handoff_id, body
        )

    @app.get(
        "/incidents/{incident_id}/actions",
        response_model=list[ActionCatalogEntry],
    )
    async def list_actions(
        request: Request, incident_id: UUID
    ) -> list[ActionCatalogEntry]:
        await require_incident(request, incident_id)
        return store.get_action_catalog()

    @app.post(
        "/incidents/{incident_id}/proposals/{proposal_id}/evaluate",
        response_model=PolicyDecision,
    )
    async def evaluate_proposal(
        request: Request, incident_id: UUID, proposal_id: UUID
    ) -> PolicyDecision:
        await require_incident(request, incident_id)
        return await store.evaluate_proposal(
            request.app.state.pool, incident_id, proposal_id
        )

    @app.get(
        "/incidents/{incident_id}/policy",
        response_model=list[PolicyDecision],
    )
    async def list_policy_decisions(
        request: Request, incident_id: UUID
    ) -> list[PolicyDecision]:
        await require_incident(request, incident_id)
        return await store.list_policy_decisions(
            request.app.state.pool, incident_id
        )

    @app.post(
        "/incidents/{incident_id}/proposals/{proposal_id}/approve",
        response_model=Approval,
    )
    async def approve_proposal(
        request: Request,
        incident_id: UUID,
        proposal_id: UUID,
        body: ApprovalCreate,
    ) -> Approval:
        await require_incident(request, incident_id)
        return await store.approve_proposal(
            request.app.state.pool, incident_id, proposal_id, body
        )

    @app.get(
        "/incidents/{incident_id}/approvals",
        response_model=list[Approval],
    )
    async def list_approvals(
        request: Request, incident_id: UUID
    ) -> list[Approval]:
        await require_incident(request, incident_id)
        return await store.list_approvals(request.app.state.pool, incident_id)

    @app.post(
        "/incidents/{incident_id}/proposals/{proposal_id}/execute",
        response_model=ExecutionResult,
    )
    async def execute_proposal(
        request: Request,
        incident_id: UUID,
        proposal_id: UUID,
        body: ExecutionRequest,
    ) -> ExecutionResult:
        await require_incident(request, incident_id)
        return await store.execute_proposal(
            request.app.state.pool, incident_id, proposal_id, body
        )

    @app.get(
        "/incidents/{incident_id}/executions",
        response_model=list[ExecutionResult],
    )
    async def list_executions(
        request: Request, incident_id: UUID
    ) -> list[ExecutionResult]:
        await require_incident(request, incident_id)
        return await store.list_executions(request.app.state.pool, incident_id)

    @app.get(
        "/incidents/{incident_id}/containment",
        response_model=list[ContainmentRecord],
    )
    async def list_containment(
        request: Request, incident_id: UUID
    ) -> list[ContainmentRecord]:
        await require_incident(request, incident_id)
        return await store.containment_records(
            request.app.state.pool, incident_id
        )

    @app.post(
        "/incidents/{incident_id}/proposals/{proposal_id}/approval-request",
        response_model=ApprovalRequest,
        status_code=201,
    )
    async def create_approval_request(
        request: Request, incident_id: UUID, proposal_id: UUID
    ) -> ApprovalRequest:
        await require_incident(request, incident_id)
        return await store.create_approval_request(
            request.app.state.pool, incident_id, proposal_id
        )

    @app.get(
        "/incidents/{incident_id}/approval-requests",
        response_model=list[ApprovalRequest],
    )
    async def list_approval_requests(
        request: Request, incident_id: UUID
    ) -> list[ApprovalRequest]:
        await require_incident(request, incident_id)
        return await store.list_approval_requests(
            request.app.state.pool, incident_id
        )

    @app.post(
        "/incidents/{incident_id}/proposals/{proposal_id}/approve-oob",
        response_model=Approval,
    )
    async def approve_oob(
        request: Request,
        incident_id: UUID,
        proposal_id: UUID,
        body: OobApprovalCreate,
    ) -> Approval:
        await require_incident(request, incident_id)
        return await store.approve_oob(
            request.app.state.pool, incident_id, proposal_id, body
        )

    @app.get("/automation/status", response_model=AutomationStatus)
    async def automation_status(request: Request) -> AutomationStatus:
        return await store.automation_status(request.app.state.pool)

    @app.get("/automation/scorecards", response_model=list[Scorecard])
    async def automation_scorecards(request: Request) -> list[Scorecard]:
        return await store.scorecards(request.app.state.pool)

    @app.post("/automation/kill-switch", response_model=KillSwitchState)
    async def kill_switch(
        request: Request, body: KillSwitchRequest
    ) -> KillSwitchState:
        return await store.engage_kill_switch(request.app.state.pool, body)

    @app.post(
        "/automation/breakers/{action_id}/reset", response_model=BreakerState
    )
    async def breaker_reset(
        request: Request, action_id: str, body: BreakerResetRequest
    ) -> BreakerState:
        return await store.reset_breaker(request.app.state.pool, action_id, body)

    @app.post("/automation/levels/{action_id}")
    async def autonomy_level(
        request: Request, action_id: str, body: AutonomyLevelRequest
    ) -> dict:
        return await store.set_autonomy_level(
            request.app.state.pool, action_id, body
        )

    @app.post("/automation/mock-oob-sign", response_model=OobSignResult)
    async def mock_oob_sign(request: Request, body: OobSignRequest) -> OobSignResult:
        return await store.mock_sign_oob_bundle(
            request.app.state.pool, body.bundle_id
        )

    @app.get("/audit/verify", response_model=AuditVerification)
    async def audit_verify(request: Request) -> AuditVerification:
        return await store.verify_audit(request.app.state.pool)
    if WEB_DIST.is_dir():
        app.mount("/ui", StaticFiles(directory=str(WEB_DIST), html=True), name="ui")

    return app


app = create_app()
