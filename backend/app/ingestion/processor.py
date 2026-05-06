import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.postgres import SignalAggregateORM, WorkItemORM
from app.ingestion.metrics import record_processed
from app.models.enums import WorkItemStatus
from app.util.retry import retry_async
from app.workflow.alerting import AlertContext, get_alerting_strategy

logger = logging.getLogger(__name__)


def _bucket_start(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0, tzinfo=dt.tzinfo or timezone.utc)


async def persist_raw_signal(
    mongo: AsyncIOMotorDatabase,
    *,
    work_item_id: str,
    component_id: str,
    message: str,
    payload: dict,
    received_at: datetime,
) -> str:
    doc = {
        "_id": str(uuid4()),
        "work_item_id": work_item_id,
        "component_id": component_id,
        "message": message,
        "payload": payload,
        "received_at": received_at,
    }

    async def _ins():
        await mongo["raw_signals"].insert_one(doc)

    await retry_async(_ins, operation="mongo_insert_raw_signal")
    return doc["_id"]


async def _increment_signals(session: AsyncSession, work_item_id: str) -> None:
    wi = await session.get(WorkItemORM, work_item_id)
    if wi:
        wi.signal_count = (wi.signal_count or 0) + 1
    await session.commit()


async def _create_work_item(
    session: AsyncSession,
    *,
    work_item_id: str,
    component_id: str,
    component_type: str,
    severity: str,
    alert_tier: str,
    received_at: datetime,
) -> None:
    wi = WorkItemORM(
        id=work_item_id,
        component_id=component_id,
        component_type=component_type.upper(),
        severity=severity,
        alert_tier=alert_tier,
        status=WorkItemStatus.OPEN.value,
        first_signal_at=received_at,
        signal_count=1,
    )
    session.add(wi)
    await session.commit()


async def _bump_aggregate(session: AsyncSession, bucket: datetime, ctype: str) -> None:
    q = await session.execute(
        select(SignalAggregateORM).where(
            SignalAggregateORM.bucket_start == bucket,
            SignalAggregateORM.component_type == ctype,
        )
    )
    row = q.scalar_one_or_none()
    if row:
        row.count += 1
    else:
        session.add(SignalAggregateORM(id=str(uuid4()), bucket_start=bucket, component_type=ctype, count=1))
    await session.commit()


async def process_signal(
    session_factory: async_sessionmaker[AsyncSession],
    mongo: AsyncIOMotorDatabase,
    redis: Redis,
    body: dict,
):
    component_id = body["component_id"]
    component_type = body["component_type"]
    severity_hint = body.get("severity", "medium")
    message = body.get("message", "")
    payload = body.get("payload") or {}
    received_at = body.get("received_at") or datetime.now(timezone.utc)
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)

    strategy = get_alerting_strategy(component_type)
    ctx = AlertContext(component_type=component_type, component_id=component_id, severity_hint=severity_hint)
    alert_tier = strategy.alert_tier(ctx)
    severity = strategy.normalized_severity(ctx)

    debounce_key = f"debounce:wi:{component_id}"
    existing_wi = await redis.get(debounce_key)
    work_item_id: str

    if existing_wi:
        work_item_id = existing_wi

        async def _inc():
            async with session_factory() as session:
                await _increment_signals(session, work_item_id)

        await retry_async(_inc, operation="pg_increment_signal_count")
    else:
        work_item_id = str(uuid4())

        async def _create():
            async with session_factory() as session:
                await _create_work_item(
                    session,
                    work_item_id=work_item_id,
                    component_id=component_id,
                    component_type=component_type,
                    severity=severity,
                    alert_tier=alert_tier,
                    received_at=received_at,
                )

        await retry_async(_create, operation="pg_create_work_item")
        await redis.set(debounce_key, work_item_id, ex=settings.debounce_window_sec)

    await persist_raw_signal(
        mongo,
        work_item_id=work_item_id,
        component_id=component_id,
        message=message,
        payload=payload,
        received_at=received_at,
    )

    bucket = _bucket_start(received_at)
    ctype = component_type.upper()

    async def _agg():
        async with session_factory() as session:
            await _bump_aggregate(session, bucket, ctype)

    await retry_async(_agg, operation="pg_signal_aggregate")

    await redis.delete("cache:incidents:active")
    await record_processed()


async def worker_loop(
    queue: asyncio.Queue,
    session_factory: async_sessionmaker[AsyncSession],
    mongo: AsyncIOMotorDatabase,
    redis: Redis,
):
    while True:
        body = await queue.get()
        try:
            await process_signal(session_factory, mongo, redis, body)
        except Exception:
            logger.exception("signal processing failed")
        finally:
            queue.task_done()


def start_workers(
    queue: asyncio.Queue,
    session_factory: async_sessionmaker[AsyncSession],
    mongo: AsyncIOMotorDatabase,
    redis: Redis,
    n: int = 4,
) -> list[asyncio.Task]:
    return [asyncio.create_task(worker_loop(queue, session_factory, mongo, redis)) for _ in range(n)]
