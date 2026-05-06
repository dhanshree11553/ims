import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.mongo import get_mongo
from app.db.postgres import AsyncSessionLocal, RCAORM, SignalAggregateORM, WorkItemORM, init_postgres
from app.db.redis_client import close_redis, get_redis
from app.ingestion.metrics import metrics_loop, record_accepted
from app.ingestion.processor import start_workers
from app.ingestion.rate_limit import check_ingestion_rate
from app.models.enums import WorkItemStatus
from app.models.schemas import IncidentSummary, RcaOut, RcaUpsert, RawSignalOut, SignalIn, StatusPatch, WorkItemDetail
from app.services.rca_validation import RcaIncompleteError, compute_mttr_seconds, validate_rca_complete
from app.workflow.state_machine import WorkItemStateMachine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

signal_queue: asyncio.Queue = asyncio.Queue(maxsize=settings.signal_queue_max)
_worker_tasks: list[asyncio.Task] = []
_metrics_task: asyncio.Task | None = None


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


def _severity_rank(sev: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(sev.lower(), 9)


async def _fetch_incident_summaries(db: AsyncSession, active_only: bool) -> list[IncidentSummary]:
    q = select(WorkItemORM).order_by(WorkItemORM.first_signal_at.desc())
    if active_only:
        q = q.where(WorkItemORM.status != WorkItemStatus.CLOSED.value)
    r = await db.execute(q)
    rows = r.scalars().all()
    return [
        IncidentSummary(
            id=w.id,
            component_id=w.component_id,
            component_type=w.component_type,
            severity=w.severity,
            alert_tier=w.alert_tier,
            status=w.status,
            signal_count=w.signal_count,
            first_signal_at=w.first_signal_at,
            updated_at=w.updated_at,
        )
        for w in rows
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres()
    mongo = get_mongo()
    await mongo["raw_signals"].create_index("work_item_id")
    await mongo["raw_signals"].create_index([("received_at", -1)])
    redis = await get_redis()
    global _worker_tasks, _metrics_task
    _worker_tasks = start_workers(signal_queue, AsyncSessionLocal, mongo, redis, n=4)
    _metrics_task = asyncio.create_task(metrics_loop(settings.log_metrics_interval_sec))
    logger.info("IMS backend started (queue max=%s)", settings.signal_queue_max)
    yield
    if _metrics_task:
        _metrics_task.cancel()
    for t in _worker_tasks:
        t.cancel()
    await close_redis()


app = FastAPI(title="Incident Management System", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    checks = {"postgres": False, "mongo": False, "redis": False}
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(select(WorkItemORM.id).limit(1))
        checks["postgres"] = True
    except Exception as e:
        logger.warning("health postgres: %s", e)
    try:
        await get_mongo().command("ping")
        checks["mongo"] = True
    except Exception as e:
        logger.warning("health mongo: %s", e)
    try:
        r = await get_redis()
        await r.ping()
        checks["redis"] = True
    except Exception as e:
        logger.warning("health redis: %s", e)
    ok = all(checks.values())
    return {"status": "ok" if ok else "degraded", "checks": checks}


@app.post("/ingest/signals")
async def ingest_signals(req: Request, body: SignalIn):
    redis = await get_redis()
    if not await check_ingestion_rate(redis, client_key=req.client.host if req.client else "global"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for ingestion")
    if signal_queue.full():
        raise HTTPException(status_code=503, detail="Server busy — ingestion queue full (backpressure)")
    payload = body.model_dump()
    if body.occurred_at:
        payload["received_at"] = body.occurred_at
    await signal_queue.put(payload)
    await record_accepted()
    return {"accepted": True, "queued": True}


@app.get("/incidents", response_model=list[IncidentSummary])
async def list_incidents(db: DbDep, active_only: bool = True):
    redis = await get_redis()
    cache_key = "cache:incidents:active"
    if active_only:
        cached = await redis.get(cache_key)
        if cached:
            return [IncidentSummary.model_validate(x) for x in json.loads(cached)]

    out = await _fetch_incident_summaries(db, active_only)
    if active_only and out:
        await redis.set(cache_key, json.dumps([o.model_dump(mode="json") for o in out]), ex=5)
    return out


@app.get("/incidents/sorted", response_model=list[IncidentSummary])
async def list_incidents_by_severity(db: DbDep, active_only: bool = True):
    items = await _fetch_incident_summaries(db, active_only)
    return sorted(
        items,
        key=lambda x: (_severity_rank(x.severity), -x.first_signal_at.timestamp()),
    )


@app.get("/incidents/{work_item_id}", response_model=WorkItemDetail)
async def get_incident(work_item_id: str, db: DbDep):
    r = await db.execute(
        select(WorkItemORM).where(WorkItemORM.id == work_item_id).options(selectinload(WorkItemORM.rca))
    )
    wi = r.scalar_one_or_none()
    if not wi:
        raise HTTPException(status_code=404, detail="Work item not found")
    mongo = get_mongo()
    cursor = mongo["raw_signals"].find({"work_item_id": work_item_id}).sort("received_at", -1).limit(500)
    signals = []
    async for doc in cursor:
        signals.append(
            {
                "id": doc["_id"],
                "work_item_id": doc["work_item_id"],
                "component_id": doc["component_id"],
                "message": doc.get("message", ""),
                "payload": doc.get("payload") or {},
                "received_at": doc["received_at"],
            }
        )
    rca_out = None
    if wi.rca:
        r = wi.rca
        rca_out = RcaOut(
            incident_start=r.incident_start,
            incident_end=r.incident_end,
            root_cause_category=r.root_cause_category,
            fix_applied=r.fix_applied,
            prevention_steps=r.prevention_steps,
            mttr_seconds=r.mttr_seconds,
        )
    return WorkItemDetail(
        id=wi.id,
        component_id=wi.component_id,
        component_type=wi.component_type,
        severity=wi.severity,
        alert_tier=wi.alert_tier,
        status=wi.status,
        signal_count=wi.signal_count,
        first_signal_at=wi.first_signal_at,
        updated_at=wi.updated_at,
        rca=rca_out,
        signals=[RawSignalOut.model_validate(s) for s in signals],
    )


@app.put("/incidents/{work_item_id}/rca")
async def upsert_rca(work_item_id: str, body: RcaUpsert, db: DbDep):
    wi = await db.get(WorkItemORM, work_item_id)
    if not wi:
        raise HTTPException(status_code=404, detail="Work item not found")
    try:
        validate_rca_complete(
            body.incident_start,
            body.incident_end,
            body.root_cause_category,
            body.fix_applied,
            body.prevention_steps,
        )
    except RcaIncompleteError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    mttr = compute_mttr_seconds(wi.first_signal_at, body.incident_end)
    existing = await db.execute(select(RCAORM).where(RCAORM.work_item_id == work_item_id))
    row = existing.scalar_one_or_none()
    if row:
        row.incident_start = body.incident_start
        row.incident_end = body.incident_end
        row.root_cause_category = body.root_cause_category
        row.fix_applied = body.fix_applied
        row.prevention_steps = body.prevention_steps
        row.mttr_seconds = mttr
    else:
        db.add(
            RCAORM(
                work_item_id=work_item_id,
                incident_start=body.incident_start,
                incident_end=body.incident_end,
                root_cause_category=body.root_cause_category,
                fix_applied=body.fix_applied,
                prevention_steps=body.prevention_steps,
                mttr_seconds=mttr,
            )
        )
    await db.commit()
    r = await get_redis()
    await r.delete("cache:incidents:active")
    return {"ok": True, "mttr_seconds": mttr}


@app.patch("/incidents/{work_item_id}/status")
async def patch_status(work_item_id: str, body: StatusPatch, db: DbDep):
    r = await db.execute(
        select(WorkItemORM).where(WorkItemORM.id == work_item_id).options(selectinload(WorkItemORM.rca))
    )
    wi = r.scalar_one_or_none()
    if not wi:
        raise HTTPException(status_code=404, detail="Work item not found")
    try:
        current = WorkItemStatus(wi.status)
        target = WorkItemStatus(body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid status") from e
    rca = wi.rca if target == WorkItemStatus.CLOSED else None
    sm = WorkItemStateMachine()
    try:
        sm.transition(current, target, rca)
    except RcaIncompleteError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    wi.status = target.value
    await db.commit()
    r = await get_redis()
    await r.delete("cache:incidents:active")
    return {"ok": True, "status": wi.status}


@app.get("/metrics/aggregates")
async def timeseries_aggregates(db: DbDep, limit: int = 100):
    r = await db.execute(select(SignalAggregateORM).order_by(SignalAggregateORM.bucket_start.desc()).limit(limit))
    rows = r.scalars().all()
    return [
        {"bucket_start": x.bucket_start.isoformat(), "component_type": x.component_type, "count": x.count}
        for x in rows
    ]
