import uuid
from decimal import Decimal
from app.models import Transaction, JournalEntry, Account, AuditLog
from app.services.reconciliation_service import run_reconciliation


def test_reconciliation_detects_imbalance_and_writes_audit_log(db):
    # 1. Clean test account
    acc = Account(
        account_number=f"REC-{uuid.uuid4().hex[:6]}",
        name="Reconciliation Test Acc",
        type="ASSET",
        currency="USD",
        status="ACTIVE",
    )
    db.add(acc)
    db.flush()

    # 2. Artificially create a transaction with imbalanced journal entries
    # Transaction record itself has totals=100/100, but only ONE journal entry of 100 DEBIT is added
    tx = Transaction(
        reference=f"REC-TX-{uuid.uuid4().hex[:6]}",
        description="Artificially imbalanced transaction",
        total_debit=Decimal("100.0000"),
        total_credit=Decimal("100.0000"),
        currency="USD",
        status="POSTED",
    )
    db.add(tx)
    db.flush()

    je = JournalEntry(
        transaction_id=tx.id,
        account_id=acc.id,
        entry_type="DEBIT",
        amount=Decimal("100.0000"),
        currency="USD",
    )
    db.add(je)
    db.commit()

    # 3. Execute reconciliation scan
    recon_result = run_reconciliation(db)
    assert recon_result["discrepancies_found"] >= 1

    # Find the discrepancy for our transaction
    discrepancy = next(
        (d for d in recon_result["discrepancies"] if d["transaction_id"] == tx.id),
        None,
    )
    assert discrepancy is not None
    assert discrepancy["error"] == "Journal imbalance detected"

    # 4. Assert audit_log entry was created
    log_entry = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity == "Transaction",
            AuditLog.entity_id == tx.id,
            AuditLog.action == "RECONCILIATION_DISCREPANCY",
        )
        .first()
    )
    assert log_entry is not None
    assert log_entry.actor == "SYSTEM_RECONCILIATION_WORKER"
    assert "Journal imbalance detected" in log_entry.diff
