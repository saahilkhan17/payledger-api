import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Numeric,
    ForeignKey,
    Text,
    Integer,
    CheckConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="viewer", nullable=False)  # admin, accountant, viewer
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    transactions = relationship("Transaction", back_populates="creator")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_number = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    type = Column(String(20), nullable=False)  # ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    currency = Column(String(3), default="USD", nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, FROZEN, CLOSED
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    journal_entries = relationship("JournalEntry", back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference = Column(String(64), unique=True, index=True, nullable=True)
    description = Column(String(255), nullable=True)
    total_debit = Column(Numeric(18, 4), nullable=False)
    total_credit = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    status = Column(String(20), default="POSTED", nullable=False)  # POSTED, PENDING, VOIDED
    idempotency_key = Column(String(255), unique=True, index=True, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("total_debit = total_credit", name="chk_transaction_balanced"),
        CheckConstraint("total_debit > 0", name="chk_transaction_positive"),
    )

    creator = relationship("User", back_populates="transactions")
    journal_entries = relationship(
        "JournalEntry", back_populates="transaction", cascade="all, delete-orphan"
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id = Column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id = Column(
        String(36), ForeignKey("accounts.id"), nullable=False, index=True
    )
    entry_type = Column(String(10), nullable=False)  # DEBIT, CREDIT
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_journal_entry_amount_positive"),
        CheckConstraint(
            "entry_type IN ('DEBIT', 'CREDIT')", name="chk_journal_entry_type"
        ),
    )

    transaction = relationship("Transaction", back_populates="journal_entries")
    account = relationship("Account", back_populates="journal_entries")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    request_path = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=True)
    status = Column(String(20), default="PROCESSING", nullable=False)  # PROCESSING, COMPLETED, FAILED
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    resource_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String(100), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=get_utc_now, index=True, nullable=False)
    action = Column(String(50), index=True, nullable=False)  # CREATE, UPDATE, DELETE, RECONCILIATION_DISCREPANCY
    entity = Column(String(50), index=True, nullable=False)  # Account, Transaction, Transfer, User
    entity_id = Column(String(64), index=True, nullable=False)
    diff = Column(Text, nullable=True)
