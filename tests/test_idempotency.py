import uuid
from decimal import Decimal


def test_idempotent_transfer_retries_return_same_result_and_no_double_spend(client, accountant_headers):
    # Setup accounts
    res_a = client.post(
        "/accounts",
        json={"name": "Idemp A", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    res_b = client.post(
        "/accounts",
        json={"name": "Idemp B", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    acc_a = res_a.json()["id"]
    acc_b = res_b.json()["id"]

    # Fund account A with $100
    client.post(
        f"/accounts/{acc_a}/deposit",
        json={"amount": "100.0000"},
        headers=accountant_headers,
    )

    idempotency_key = f"key-{uuid.uuid4()}"
    transfer_payload = {
        "source_account_id": acc_a,
        "destination_account_id": acc_b,
        "amount": "40.0000",
        "currency": "USD",
        "description": "Payment with idempotency key",
    }

    # 1. First attempt -> 201 Created
    headers_with_key = {**accountant_headers, "Idempotency-Key": idempotency_key}
    res_1 = client.post("/transfers", json=transfer_payload, headers=headers_with_key)
    assert res_1.status_code == 201
    data_1 = res_1.json()
    transfer_id_1 = data_1["id"]

    # Check balance after first transfer: 100 - 40 = 60
    bal_after_1 = client.get(f"/accounts/{acc_a}/balance", headers=accountant_headers).json()
    assert Decimal(bal_after_1["balance"]) == Decimal("60.0000")

    # 2. Second attempt (retry with same Idempotency-Key) -> 200 OK with identical transfer
    res_2 = client.post("/transfers", json=transfer_payload, headers=headers_with_key)
    assert res_2.status_code == 200
    data_2 = res_2.json()
    assert data_2["id"] == transfer_id_1

    # Check balance after retry: MUST STILL BE 60 (NO double spend!)
    bal_after_2 = client.get(f"/accounts/{acc_a}/balance", headers=accountant_headers).json()
    assert Decimal(bal_after_2["balance"]) == Decimal("60.0000")

    # 3. Third attempt with same key -> still 200 OK and no extra charge
    res_3 = client.post("/transfers", json=transfer_payload, headers=headers_with_key)
    assert res_3.status_code == 200
    assert res_3.json()["id"] == transfer_id_1

    bal_after_3 = client.get(f"/accounts/{acc_a}/balance", headers=accountant_headers).json()
    assert Decimal(bal_after_3["balance"]) == Decimal("60.0000")


def test_different_idempotency_keys_create_different_transfers(client, accountant_headers):
    res_a = client.post(
        "/accounts",
        json={"name": "Multi Key A", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    res_b = client.post(
        "/accounts",
        json={"name": "Multi Key B", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    acc_a = res_a.json()["id"]
    acc_b = res_b.json()["id"]

    client.post(
        f"/accounts/{acc_a}/deposit",
        json={"amount": "200.0000"},
        headers=accountant_headers,
    )

    payload = {
        "source_account_id": acc_a,
        "destination_account_id": acc_b,
        "amount": "20.0000",
        "currency": "USD",
    }

    # Transfer with key 1
    res_1 = client.post(
        "/transfers",
        json=payload,
        headers={**accountant_headers, "Idempotency-Key": f"key-{uuid.uuid4()}"},
    )
    assert res_1.status_code == 201

    # Transfer with key 2
    res_2 = client.post(
        "/transfers",
        json=payload,
        headers={**accountant_headers, "Idempotency-Key": f"key-{uuid.uuid4()}"},
    )
    assert res_2.status_code == 201

    assert res_1.json()["id"] != res_2.json()["id"]
    bal = client.get(f"/accounts/{acc_a}/balance", headers=accountant_headers).json()
    assert Decimal(bal["balance"]) == Decimal("160.0000")
