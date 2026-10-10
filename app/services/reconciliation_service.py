import logging
from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Transaction, JournalEntry
from app.schemas import EntryType
from app.services.audit_service import log_audit_event

logger = logging.getLogger(__name__)


def run_reconciliation(db: Session) -> Dict[str, Any]:
    """
    Scans journal entries for imbalanced transactions where debits != credits,
    or where journal totals mismatch transaction records, and logs findings to audit_logs.
    """
    transactions = db.query(Transaction).all()
    discrepancies: List[Dict[str, Any]] = []

    for tx in transactions:
        debit_sum = (
            db.query(func.coalesce(func.sum(JournalEntry.amount), 0))
            .filter(
                JournalEntry.transaction_id == tx.id,
                JournalEntry.entry_type == "DEBIT",
            )
            .scalar()
        ) or Decimal(0)

        credit_sum = (
            db.query(func.coalesce(func.sum(JournalEntry.amount), 0))
            .filter(
                JournalEntry.transaction_id == tx.id,
                JournalEntry.entry_type == "CREDIT",
            )
            .scalar()
        ) or Decimal(0)

        debit_sum = Decimal(str(debit_sum))
        credit_sum = Decimal(str(credit_sum))
        tx_debit = Decimal(str(tx.total_debit))
        tx_credit = Decimal(str(tx.total_credit))

        is_imbalanced = (debit_sum != credit_sum) or (debit_sum != tx_debit) or (credit_sum != tx_credit)

        if is_imbalanced:
            discrepancy_data = {
                "error": "Journal imbalance detected",
                "transaction_id": str(tx.id),
                "journal_debit_sum": str(debit_sum),
                "journal_credit_sum": str(credit_sum),
                "imbalance_amount": str(abs(debit_sum - credit_sum)),
                "tx_total_debit": str(tx_debit),
                "tx_total_credit": str(tx_credit),
            }
            discrepancies.append(discrepancy_data)

            log_audit_event(
                db=db,
                actor="SYSTEM_RECONCILIATION_WORKER",
                action="RECONCILIATION_DISCREPANCY",
                entity="Transaction",
                entity_id=str(tx.id),
                diff=discrepancy_data,
                commit=True,
            )
            logger.warning("Reconciliation discrepancy found: %s", discrepancy_data)

    logger.info(
        "Reconciliation run finished: scanned %d transactions, found %d discrepancies",
        len(transactions),
        len(discrepancies),
    )
    return {
        "scanned_transactions": len(transactions),
        "discrepancies_found": len(discrepancies),
        "discrepancies": discrepancies,
    }
