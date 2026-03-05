from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Float,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ActiveJob(Base):
    __tablename__ = "active_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slurm_job_id = Column(Integer)
    payload = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    retry_count = Column(Integer, nullable=False, server_default="0")
    x402_tx_hash = Column(Text)
    price_usdc = Column(Numeric(18, 6), nullable=False)
    client_builder_code = Column(Text)
    submitter_address = Column(Text)
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class HistoricalData(Base):
    __tablename__ = "historical_data"

    id = Column(UUID(as_uuid=True), primary_key=True)
    slurm_job_id = Column(Integer)
    submitter_address = Column(Text)
    payload = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False)
    x402_tx_hash = Column(Text)
    price_usdc = Column(Numeric(18, 6), nullable=False)
    gas_paid_wei = Column(Numeric(30, 0))
    gas_paid_usd = Column(Numeric(18, 6))
    output_hash = Column(BYTEA)
    proof_tx_hash = Column(Text)
    builder_reward_usd = Column(Numeric(18, 6), server_default="0")
    compute_duration_s = Column(Float)
    llm_cost_usd = Column(Numeric(18, 6), server_default="0")
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(
        DateTime(timezone=True), primary_key=True, nullable=False, server_default=text("now()")
    )


class PaymentSession(Base):
    __tablename__ = "payment_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(Text, nullable=False, server_default="pending")
    script = Column(Text, nullable=True)
    job_payload = Column(JSONB)
    cpus = Column(Integer, nullable=False)
    time_limit_min = Column(Integer, nullable=False)
    price = Column(Text, nullable=False)
    agent_url = Column(Text)
    job_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AgentCost(Base):
    __tablename__ = "agent_costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cost_type = Column(Text, nullable=False)
    amount_usd = Column(Numeric(18, 6), nullable=False)
    detail = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class WalletSnapshot(Base):
    __tablename__ = "wallet_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    eth_balance = Column(Numeric(30, 0), nullable=False)
    usdc_balance = Column(Numeric(18, 6), nullable=False)
    eth_price_usd = Column(Numeric(18, 2))
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AttributionLog(Base):
    __tablename__ = "attribution_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(Text, nullable=False)
    codes = Column(ARRAY(Text), nullable=False)
    is_multi = Column(Boolean, Computed("array_length(codes, 1) > 1", persisted=True))
    gas_used = Column(Numeric(30, 0))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Credit(Base):
    __tablename__ = "credits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_address = Column(Text, nullable=False, index=True)
    amount_usdc = Column(Numeric(18, 6), nullable=False)
    reason = Column(Text)
    redeemed = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(Text, nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True))
    wallet_address = Column(Text)
    amount_usdc = Column(Numeric(18, 6))
    detail = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ScalingEvent(Base):
    __tablename__ = "scaling_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(Text, nullable=False)
    node_name = Column(Text, nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
