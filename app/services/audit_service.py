import json
from decimal import Decimal
from datetime import datetime, date
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models import AuditLog


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (Decimal, float)):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if hasattr(obj, "dict"):
            return obj.dict()
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return super().default(obj)


def log_audit_event(
    db: Session,
    actor: str,
    action: str,
    entity: str,
    entity_id: str,
    diff: Optional[Any] = None,
    commit: bool = False,
) -> AuditLog:
    diff_text = None
    if diff is not None:
        if isinstance(diff, str):
            diff_text = diff
        else:
            diff_text = json.dumps(diff, cls=CustomJSONEncoder)

    audit_entry = AuditLog(
        actor=actor,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        diff=diff_text,
    )
    db.add(audit_entry)
    if commit:
        db.commit()
        db.refresh(audit_entry)
    else:
        db.flush()
    return audit_entry
