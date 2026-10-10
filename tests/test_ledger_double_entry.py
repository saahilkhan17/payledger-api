from decimal import Decimal
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import Transaction, JournalEntry
from app.services.ledger_service import validate_double_entry


def test_double_entry_transfer_creates_balanced_legs(client, accountant_headers):
    # Create accounts
    res_a = client.post(
        "/accounts",
        json={"name": "Checking Account", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    res_b = client.post(
        "/accounts",
        json={"name": "Savings Account", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    acc_a = res_a.json()["id"]
    acc_b = res_b.json()["id"]

    # Fund account A with $1,000.00
    dep_res = client.post(
        f"/accounts/{acc_a}/deposit",
        json={"amount": "1000.0000"},
        headers=accountant_headers,
    )
    assert dep_res.status_code == 201

    # Transfer $250.00 from A to B
    tx_res = client.post(
        "/transfers",
        json={
            "source_account_id": acc_a,
            "destination_account_id": acc_b,
            "amount": "250.0000",
            "currency": "USD",
            "description": "Savings allocation",
        },
        headers=accountant_headers,
    )
    assert tx_res.status_code == 201
    tx_data = tx_res.json()
    assert Decimal(tx_data["total_debit"]) == Decimal("250.0000")
    assert Decimal(tx_data["total_credit"]) == Decimal("250.0000")
    assert len(tx_data["journal_entries"]) == 2

    debits = [e for e in tx_data["journal_entries"] if e["entry_type"] == "DEBIT"]
    credits = [e for e in tx_data["journal_entries"] if e["entry_type"] == "CREDIT"]
    assert len(debits) == 1
    assert len(credits) == 1
    assert debits[0]["account_id"] == acc_b
    assert Decimal(debits[0]["amount"]) == Decimal("250.0000")
    assert credits[0]["account_id"] == acc_a
    assert Decimal(credits[0]["amount"]) == Decimal("250.0000")

    # Check Balances:
    # A had 1000, transferred 250 -> 750 remaining
    bal_a = client.get(f"/accounts/{acc_a}/balance", headers=accountant_headers).json()
    assert Decimal(bal_a["balance"]) == Decimal("750.0000")

    # B received 250 -> 250
    bal_b = client.get(f"/accounts/{acc_b}/balance", headers=accountant_headers).json()
    assert Decimal(bal_b["balance"]) == Decimal("250.0000")


def test_insufficient_funds_rejected(client, accountant_headers):
    res_a = client.post(
        "/accounts",
        json={"name": "Low Balance Acc", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    res_b = client.post(
        "/accounts",
        json={"name": "Destination Acc", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    acc_a = res_a.json()["id"]
    acc_b = res_b.json()["id"]

    # Fund with $50
    client.post(
        f"/accounts/{acc_a}/deposit",
        json={"amount": "50.0000"},
        headers=accountant_headers,
    )

    # Attempt to transfer $100 -> must fail with 400 Insufficient funds
    tx_res = client.post(
        "/transfers",
        json={
            "source_account_id": acc_a,
            "destination_account_id": acc_b,
            "amount": "100.0000",
            "currency": "USD",
        },
        headers=accountant_headers,
    )
    assert tx_res.status_code == 400
    assert "Insufficient funds" in tx_res.json()["detail"]


def test_app_level_double_entry_validation():
    # Balanced entries should pass
    balanced = [
        {"entry_type": "DEBIT", "amount": Decimal("100.00")},
        {"entry_type": "CREDIT", "amount": Decimal("100.00")},
    ]
    validate_double_entry(balanced)  # should not raise

    # Imbalanced entries must raise ValueError
    imbalanced = [
        {"entry_type": "DEBIT", "amount": Decimal("100.00")},
        {"entry_type": "CREDIT", "amount": Decimal("90.00")},
    ]
    with pytest.raises(ValueError, match="Double-entry journal imbalance"):
        validate_double_entry(imbalanced)


def test_db_check_constraint_enforces_balanced_transaction(db):
    """Assert DB CHECK constraint rejects imbalanced transactions."""
    imbalanced_tx = Transaction(
        reference="FAIL-IMBALANCED",
        description="Should violate check constraint",
        total_debit=Decimal("100.0000"),
        total_credit=Decimal("50.0000"),  # Imbalance!
        currency="USD",
        status="POSTED",
    )
    db.add(imbalanced_tx)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_db_check_constraint_positive_amount(db):
    """Assert DB CHECK constraint rejects non-positive journal amounts."""
    balanced_tx = Transaction(
        reference="VALID-TX-REF",
        description="Balanced tx",
        total_debit=Decimal("50.0000"),
        total_credit=Decimal("50.0000"),
        currency="USD",
        status="POSTED",
    )
    db.add(balanced_tx)
    db.flush()

    invalid_entry = JournalEntry(
        transaction_id=balanced_tx.id,
        account_id="dummy-acc-id",
        entry_type="DEBIT",
        amount=Decimal("-10.0000"),  # Negative amount!
        currency="USD",
    )
    db.add(invalid_entry)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
