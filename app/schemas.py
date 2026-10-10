from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Enums
class UserRole(str, Enum):
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class EntryType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class TransactionStatus(str, Enum):
    POSTED = "POSTED"
    PENDING = "PENDING"
    VOIDED = "VOIDED"


# Generic Pagination
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    skip: int
    limit: int


# Auth & Users
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr


class UserRegister(UserBase):
    password: str = Field(..., min_length=6, max_length=72)
    role: Optional[UserRole] = UserRole.VIEWER


class UserResponse(UserBase):
    id: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    exp: Optional[int] = None


# Accounts
class AccountCreate(BaseModel):
    account_number: Optional[str] = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    type: AccountType = AccountType.ASSET
    currency: str = Field("USD", min_length=3, max_length=3)
    status: AccountStatus = AccountStatus.ACTIVE


class AccountResponse(BaseModel):
    id: str
    account_number: str
    name: str
    type: AccountType
    currency: str
    status: AccountStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountBalanceResponse(BaseModel):
    account_id: str
    account_number: str
    name: str
    currency: str
    balance: Decimal
    total_debit: Decimal
    total_credit: Decimal

    model_config = ConfigDict(from_attributes=True)


class AccountDeposit(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=4)
    description: Optional[str] = Field("Deposit funds", max_length=255)


# Transfers & Journal Entries
class TransferCreate(BaseModel):
    source_account_id: str
    destination_account_id: str
    amount: Decimal = Field(..., gt=0, decimal_places=4)
    currency: str = Field("USD", min_length=3, max_length=3)
    description: Optional[str] = Field(None, max_length=255)
    reference: Optional[str] = Field(None, max_length=64)


class JournalEntryResponse(BaseModel):
    id: str
    transaction_id: str
    account_id: str
    entry_type: EntryType
    amount: Decimal
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransferResponse(BaseModel):
    id: str
    reference: Optional[str]
    description: Optional[str]
    total_debit: Decimal
    total_credit: Decimal
    currency: str
    status: TransactionStatus
    idempotency_key: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    journal_entries: List[JournalEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)


# Audit Log
class AuditLogResponse(BaseModel):
    id: int
    actor: str
    timestamp: datetime
    action: str
    entity: str
    entity_id: str
    diff: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)
