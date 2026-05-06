from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings
from app.models.enums import WorkItemStatus


class Base(DeclarativeBase):
    pass


class WorkItemORM(Base):
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    component_id: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    component_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    alert_tier: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WorkItemStatus.OPEN.value)
    first_signal_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rca: Mapped["RCAORM | None"] = relationship("RCAORM", back_populates="work_item", uselist=False)


class RCAORM(Base):
    __tablename__ = "rca_records"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    work_item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("work_items.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    incident_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    incident_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    root_cause_category: Mapped[str] = mapped_column(String(128), nullable=False)
    fix_applied: Mapped[str] = mapped_column(Text, nullable=False)
    prevention_steps: Mapped[str] = mapped_column(Text, nullable=False)
    mttr_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    work_item: Mapped["WorkItemORM"] = relationship("WorkItemORM", back_populates="rca")


class SignalAggregateORM(Base):
    __tablename__ = "signal_aggregates"
    __table_args__ = (UniqueConstraint("bucket_start", "component_type", name="uq_signal_agg_bucket_type"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    component_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    count: Mapped[int] = mapped_column(nullable=False, default=0)


engine = create_async_engine(settings.postgres_dsn, pool_pre_ping=True, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


async def init_postgres():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
