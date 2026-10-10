import uuid
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed


def test_concurrent_transfers_same_idempotency_key_no_double_spend(client, accountant_headers):
    """
    Spawns multiple concurrent threads attempting to execute a transfer
    with the exact same Idempotency-Key. Asserts only one transfer is executed
    and no double-spending occurs.
    """
    res_a = client.post(
        "/accounts",
        json={"name": "Concurrent Src", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    res_b = client.post(
        "/accounts",
        json={"name": "Concurrent Dst", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    acc_a = res_a.json()["id"]
    acc_b = res_b.json()["id"]

    # Initial balance: $100.00
    initial_funds = Decimal("100.0000")
    client.post(
        f"/accounts/{acc_a}/deposit",
        json={"amount": str(initial_funds)},
        headers=accountant_headers,
    )

    transfer_amount = Decimal("30.0000")
    shared_idempotency_key = f"concurrent-key-{uuid.uuid4()}"
    headers = {
        **accountant_headers,
        "Idempotency-Key": shared_idempotency_key,
    }
    payload = {
        "source_account_id": acc_a,
        "destination_account_id": acc_b,
        "amount": str(transfer_amount),
        "currency": "USD",
        "description": "Concurrent stress transfer",
    }

    results = []

    def make_request():
        return client.post("/transfers", json=payload, headers=headers)

    concurrency_count = 8
    with ThreadPoolExecutor(max_workers=concurrency_count) as executor:
        futures = [executor.submit(make_request) for _ in range(concurrency_count)]
        for fut in as_completed(futures):
            results.append(fut.result())

    # All responses must be successful (200 OK or 201 Created)
    status_codes = [r.status_code for r in results]
    assert all(code in (200, 201) for code in status_codes), f"Unexpected status codes: {status_codes}"

    # All responses must refer to the exact same transfer ID
    transfer_ids = set(r.json()["id"] for r in results)
    assert len(transfer_ids) == 1, f"Expected 1 unique transfer ID, got: {transfer_ids}"

    # Verify balance was deducted EXACTLY ONCE
    bal_res = client.get(f"/accounts/{acc_a}/balance", headers=accountant_headers)
    assert bal_res.status_code == 200
    final_balance = Decimal(bal_res.json()["balance"])
    expected_balance = initial_funds - transfer_amount
    assert final_balance == expected_balance, f"Balance mismatch: {final_balance} != {expected_balance}"
