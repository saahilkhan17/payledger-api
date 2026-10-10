import json
import time
import uuid
from decimal import Decimal
from typing import Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Account, Transaction, JournalEntry, IdempotencyRecord, User
from app.schemas import AccountCreate, TransferCreate, AccountStatus, AccountType, EntryType
from app.services.audit_service import log_audit_event, CustomJSONEncoder


def create_account(db: Session, account_in: AccountCreate, actor: str) -> Account:
    account_number = account_in.account_number
    if not account_number:
        account_number = f"ACC-{uuid.uuid4().hex[:10].upper()}"

    existing = db.query(Account).filter(Account.account_number == account_number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account with account_number '{account_number}' already exists",
        )

    account = Account(
        account_number=account_number,
        name=account_in.name,
        type=account_in.type.value if hasattr(account_in.type, "value") else str(account_in.type),
        currency=account_in.currency.upper(),
        status=account_in.status.value if hasattr(account_in.status, "value") else str(account_in.status),
    )
    db.add(account)
    db.flush()

    # Log audit event
    log_audit_event(
        db=db,
        actor=actor,
        action="CREATE",
        entity="Account",
        entity_id=account.id,
        diff={
            "account_number": account.account_number,
            "name": account.name,
            "type": account.type,
            "currency": account.currency,
            "status": account.status,
        },
    )
    db.commit()
    db.refresh(account)
    return account


def get_account_balance(db: Session, account_id: str) -> dict:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )

    debit_sum = (
        db.query(func.coalesce(func.sum(JournalEntry.amount), 0))
        .filter(
            JournalEntry.account_id == account_id,
            JournalEntry.entry_type == "DEBIT",
        )
        .scalar()
    ) or Decimal(0)

    credit_sum = (
        db.query(func.coalesce(func.sum(JournalEntry.amount), 0))
        .filter(
            JournalEntry.account_id == account_id,
            JournalEntry.entry_type == "CREDIT",
        )
        .scalar()
    ) or Decimal(0)

    total_debit = Decimal(str(debit_sum))
    total_credit = Decimal(str(credit_sum))

    # Accounting conventions:
    # ASSET and EXPENSE: normal balance is Debit (Debit - Credit)
    # LIABILITY, EQUITY, REVENUE: normal balance is Credit (Credit - Debit)
    if account.type in (AccountType.ASSET.value, AccountType.EXPENSE.value):
        balance = total_debit - total_credit
    else:
        balance = total_credit - total_debit

    return {
        "account_id": account.id,
        "account_number": account.account_number,
        "name": account.name,
        "currency": account.currency,
        "balance": balance,
        "total_debit": total_debit,
        "total_credit": total_credit,
    }


def deposit_funds(
    db: Session,
    account_id: str,
    amount: Decimal,
    actor: str,
    description: str = "Deposit funds",
) -> Transaction:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    if account.status != AccountStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account is not ACTIVE (current status: {account.status})",
        )

    # Find or create a system treasury clearing account
    system_clearing = (
        db.query(Account).filter(Account.account_number == "SYS-TREASURY").first()
    )
    if not system_clearing:
        system_clearing = Account(
            account_number="SYS-TREASURY",
            name="System Treasury Clearing",
            type=AccountType.EQUITY.value,
            currency=account.currency,
            status=AccountStatus.ACTIVE.value,
        )
        db.add(system_clearing)
        db.flush()

    tx = Transaction(
        reference=f"DEP-{uuid.uuid4().hex[:10].upper()}",
        description=description,
        total_debit=amount,
        total_credit=amount,
        currency=account.currency,
        status="POSTED",
    )
    db.add(tx)
    db.flush()

    # Double entry:
    # Debit target account (asset increases)
    # Credit clearing account (equity/funding increases)
    debit_entry = JournalEntry(
        transaction_id=tx.id,
        account_id=account.id,
        entry_type=EntryType.DEBIT.value,
        amount=amount,
        currency=account.currency,
    )
    credit_entry = JournalEntry(
        transaction_id=tx.id,
        account_id=system_clearing.id,
        entry_type=EntryType.CREDIT.value,
        amount=amount,
        currency=account.currency,
    )
    db.add_all([debit_entry, credit_entry])

    log_audit_event(
        db=db,
        actor=actor,
        action="CREATE",
        entity="Deposit",
        entity_id=tx.id,
        diff={
            "account_id": account.id,
            "amount": str(amount),
            "currency": account.currency,
            "description": description,
        },
    )
    db.commit()
    db.refresh(tx)
    return tx


def validate_double_entry(entries: list) -> None:
    """Application-level validation that sum of debits == sum of credits."""
    total_debit = sum(Decimal(str(e["amount"])) for e in entries if e["entry_type"] == EntryType.DEBIT.value)
    total_credit = sum(Decimal(str(e["amount"])) for e in entries if e["entry_type"] == EntryType.CREDIT.value)
    if total_debit != total_credit:
        raise ValueError(
            f"Double-entry journal imbalance: total debits ({total_debit}) != total credits ({total_credit})"
        )
    if total_debit <= 0:
        raise ValueError("Transaction amount must be strictly greater than zero")


def execute_transfer(
    db: Session,
    transfer_in: TransferCreate,
    actor_user: User,
    idempotency_key: Optional[str] = None,
) -> Transaction:
    # 1. Idempotency handling
    idemp_rec = None
    if idempotency_key:
        idemp_rec = (
            db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.key == idempotency_key)
            .first()
        )
        if idemp_rec:
            if idemp_rec.status == "COMPLETED" and idemp_rec.resource_id:
                # Return the previously completed transaction
                existing_tx = (
                    db.query(Transaction)
                    .filter(Transaction.id == idemp_rec.resource_id)
                    .first()
                )
                if existing_tx:
                    return existing_tx
            elif idemp_rec.status == "PROCESSING":
                # Another concurrent request is processing this key. Wait/poll.
                for _ in range(50):
                    time.sleep(0.05)
                    db.expire_all()
                    current_rec = (
                        db.query(IdempotencyRecord)
                        .filter(IdempotencyRecord.key == idempotency_key)
                        .first()
                    )
                    if current_rec and current_rec.status == "COMPLETED":
                        existing_tx = (
                            db.query(Transaction)
                            .filter(Transaction.id == current_rec.resource_id)
                            .first()
                        )
                        if existing_tx:
                            return existing_tx
                    elif current_rec and current_rec.status == "FAILED":
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Original transaction for this Idempotency-Key failed",
                        )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Concurrent request with the same Idempotency-Key is still processing",
                )

        # Attempt to claim the idempotency key atomically
        try:
            idemp_rec = IdempotencyRecord(
                key=idempotency_key,
                user_id=actor_user.id,
                request_path="/transfers",
                status="PROCESSING",
            )
            db.add(idemp_rec)
            db.commit()
            db.refresh(idemp_rec)
        except IntegrityError:
            db.rollback()
            # Another thread just claimed it in race condition: poll for completion
            for _ in range(50):
                time.sleep(0.05)
                current_rec = (
                    db.query(IdempotencyRecord)
                    .filter(IdempotencyRecord.key == idempotency_key)
                    .first()
                )
                if current_rec and current_rec.status == "COMPLETED":
                    existing_tx = (
                        db.query(Transaction)
                        .filter(Transaction.id == current_rec.resource_id)
                        .first()
                    )
                    if existing_tx:
                        return existing_tx
                elif current_rec and current_rec.status == "FAILED":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Original transaction for this Idempotency-Key failed",
                    )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent request with the same Idempotency-Key is in progress",
            )

    try:
        # 2. Validate accounts
        if transfer_in.source_account_id == transfer_in.destination_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination accounts must be different",
            )

        source_acc = (
            db.query(Account)
            .filter(Account.id == transfer_in.source_account_id)
            .first()
        )
        if not source_acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source account '{transfer_in.source_account_id}' not found",
            )

        dest_acc = (
            db.query(Account)
            .filter(Account.id == transfer_in.destination_account_id)
            .first()
        )
        if not dest_acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination account '{transfer_in.destination_account_id}' not found",
            )

        if source_acc.status != AccountStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source account is not ACTIVE (status: {source_acc.status})",
            )

        if dest_acc.status != AccountStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destination account is not ACTIVE (status: {dest_acc.status})",
            )

        currency = transfer_in.currency.upper()
        if source_acc.currency != currency or dest_acc.currency != currency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Currency mismatch. Accounts must match transfer currency '{currency}'",
            )

        # 3. Check sufficient balance if source is ASSET
        if source_acc.type == AccountType.ASSET.value:
            current_bal = get_account_balance(db, source_acc.id)["balance"]
            if current_bal < transfer_in.amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient funds: available balance is {current_bal}, requested {transfer_in.amount}",
                )

        # 4. Prepare double-entry journal entries
        # Credit source account (reduces asset), Debit destination account (increases asset)
        entries = [
            {"account_id": dest_acc.id, "entry_type": EntryType.DEBIT.value, "amount": transfer_in.amount},
            {"account_id": source_acc.id, "entry_type": EntryType.CREDIT.value, "amount": transfer_in.amount},
        ]

        # Application-level validation
        validate_double_entry(entries)

        # 5. Create Transaction record with balanced totals
        ref = transfer_in.reference or f"TX-{uuid.uuid4().hex[:10].upper()}"
        tx = Transaction(
            reference=ref,
            description=transfer_in.description,
            total_debit=transfer_in.amount,
            total_credit=transfer_in.amount,
            currency=currency,
            status="POSTED",
            idempotency_key=idempotency_key,
            created_by=actor_user.id,
        )
        db.add(tx)
        db.flush()

        # 6. Create Journal Entries
        j_entries = []
        for e in entries:
            je = JournalEntry(
                transaction_id=tx.id,
                account_id=e["account_id"],
                entry_type=e["entry_type"],
                amount=e["amount"],
                currency=currency,
            )
            j_entries.append(je)
        db.add_all(j_entries)

        # 7. Record Audit Log
        log_audit_event(
            db=db,
            actor=actor_user.username,
            action="CREATE",
            entity="Transfer",
            entity_id=tx.id,
            diff={
                "reference": tx.reference,
                "source_account_id": source_acc.id,
                "destination_account_id": dest_acc.id,
                "amount": str(transfer_in.amount),
                "currency": currency,
                "idempotency_key": idempotency_key,
            },
        )

        # 8. Mark idempotency record as completed
        if idemp_rec:
            idemp_rec.status = "COMPLETED"
            idemp_rec.resource_id = tx.id
            idemp_rec.response_code = 200
            idemp_rec.response_body = json.dumps(
                {
                    "id": tx.id,
                    "reference": tx.reference,
                    "total_debit": str(tx.total_debit),
                    "total_credit": str(tx.total_credit),
                },
                cls=CustomJSONEncoder,
            )

        db.commit()
        db.refresh(tx)
        return tx

    except Exception as exc:
        db.rollback()
        if idemp_rec:
            # Mark idempotency as failed so subsequent calls can handle it
            try:
                fail_rec = (
                    db.query(IdempotencyRecord)
                    .filter(IdempotencyRecord.key == idempotency_key)
                    .first()
                )
                if fail_rec:
                    fail_rec.status = "FAILED"
                    db.commit()
            except Exception:
                pass
        raise exc
