from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.models import Transaction, User, IdempotencyRecord
from app.schemas import (
    TransferCreate,
    TransferResponse,
    PaginatedResponse,
    TransactionStatus,
    UserRole,
)
from app.security import get_current_user, require_roles
from app.services.ledger_service import execute_transfer

router = APIRouter(prefix="/transfers", tags=["Transfers"])


@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new double-entry transfer with idempotency and rate limiting",
)
@limiter.limit(settings.TRANSFER_RATE_LIMIT)
def create_new_transfer(
    request: Request,
    response: Response,
    transfer_in: TransferCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTANT)),
):
    is_retry = False
    if idempotency_key:
        existing_idemp = (
            db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.key == idempotency_key)
            .first()
        )
        if existing_idemp and existing_idemp.status == "COMPLETED":
            is_retry = True

    tx = execute_transfer(
        db=db,
        transfer_in=transfer_in,
        actor_user=current_user,
        idempotency_key=idempotency_key,
    )

    if is_retry:
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_201_CREATED

    return tx


@router.get(
    "",
    response_model=PaginatedResponse[TransferResponse],
    summary="List transfers with pagination and date/status filtering",
)
def list_transfers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[TransactionStatus] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Transaction)
    if status:
        query = query.filter(Transaction.status == status.value)
    if start_date:
        query = query.filter(Transaction.created_at >= start_date)
    if end_date:
        query = query.filter(Transaction.created_at <= end_date)

    total = query.count()
    items = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get(
    "/{transfer_id}",
    response_model=TransferResponse,
    summary="Get transfer details and balanced journal entry legs",
)
def get_transfer(
    transfer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = db.query(Transaction).filter(Transaction.id == transfer_id).first()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transfer '{transfer_id}' not found",
        )
    return tx
