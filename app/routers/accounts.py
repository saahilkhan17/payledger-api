from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, User
from app.schemas import (
    AccountCreate,
    AccountResponse,
    AccountBalanceResponse,
    AccountDeposit,
    PaginatedResponse,
    AccountStatus,
    AccountType,
    UserRole,
    TransferResponse,
)
from app.security import get_current_user, require_roles
from app.services.ledger_service import create_account, get_account_balance, deposit_funds

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ledger account (Accountant or Admin)",
)
def create_new_account(
    account_in: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTANT)),
):
    return create_account(db, account_in, actor=current_user.username)


@router.get(
    "",
    response_model=PaginatedResponse[AccountResponse],
    summary="List accounts with pagination and filtering",
)
def list_accounts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[AccountStatus] = None,
    type: Optional[AccountType] = None,
    currency: Optional[str] = Query(None, min_length=3, max_length=3),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Account)
    if status:
        query = query.filter(Account.status == status.value)
    if type:
        query = query.filter(Account.type == type.value)
    if currency:
        query = query.filter(Account.currency == currency.upper())

    total = query.count()
    items = query.order_by(Account.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Get account details by ID",
)
def get_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    return account


@router.get(
    "/{account_id}/balance",
    response_model=AccountBalanceResponse,
    summary="Calculate and return the real-time double-entry balance for an account",
)
def get_balance(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_account_balance(db, account_id)


@router.post(
    "/{account_id}/deposit",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deposit funds into an account (Accountant or Admin)",
)
def deposit(
    account_id: str,
    deposit_in: AccountDeposit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTANT)),
):
    tx = deposit_funds(
        db=db,
        account_id=account_id,
        amount=deposit_in.amount,
        actor=current_user.username,
        description=deposit_in.description or "Account deposit",
    )
    return tx
