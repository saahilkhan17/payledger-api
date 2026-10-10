import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog, User
from app.schemas import AuditLogResponse, PaginatedResponse
from app.security import get_current_user

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get(
    "",
    response_model=PaginatedResponse[AuditLogResponse],
    summary="Query audit log entries with pagination and filtering",
)
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    entity: Optional[str] = Query(None, description="Filter by entity type (e.g. Account, Transfer, User)"),
    action: Optional[str] = Query(None, description="Filter by action (e.g. CREATE, UPDATE, RECONCILIATION_DISCREPANCY)"),
    actor: Optional[str] = Query(None, description="Filter by actor username"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(AuditLog)
    if entity:
        query = query.filter(AuditLog.entity == entity)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)

    total = query.count()
    raw_items = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()

    items = []
    for log_item in raw_items:
        parsed_diff = None
        if log_item.diff:
            try:
                parsed_diff = json.loads(log_item.diff)
            except Exception:
                parsed_diff = log_item.diff

        items.append(
            AuditLogResponse(
                id=log_item.id,
                actor=log_item.actor,
                timestamp=log_item.timestamp,
                action=log_item.action,
                entity=log_item.entity,
                entity_id=log_item.entity_id,
                diff=parsed_diff,
            )
        )

    return {"items": items, "total": total, "skip": skip, "limit": limit}
