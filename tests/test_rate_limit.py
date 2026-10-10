import uuid
import pytest
from app.limiter import limiter


@pytest.mark.rate_limit
def test_rate_limit_exceeded_on_transfers(client, accountant_headers):
    """
    Asserts that exceeding the rate limit on POST /transfers returns HTTP 429 Too Many Requests.
    Rate limit configured on POST /transfers is 30/minute.
    """
    limiter.reset()

    # Create and fund accounts
    res_a = client.post(
        "/accounts",
        json={"name": "RateLimit Src", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    res_b = client.post(
        "/accounts",
        json={"name": "RateLimit Dst", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    acc_a = res_a.json()["id"]
    acc_b = res_b.json()["id"]

    client.post(
        f"/accounts/{acc_a}/deposit",
        json={"amount": "10000.0000"},
        headers=accountant_headers,
    )

    payload = {
        "source_account_id": acc_a,
        "destination_account_id": acc_b,
        "amount": "1.0000",
        "currency": "USD",
    }

    status_codes = []
    # Rate limit is 30 per minute; execute 35 requests
    for i in range(35):
        key = f"rl-key-{i}-{uuid.uuid4()}"
        res = client.post(
            "/transfers",
            json=payload,
            headers={**accountant_headers, "Idempotency-Key": key},
        )
        status_codes.append(res.status_code)
        if res.status_code == 429:
            break

    # We must have encountered at least one 429 Too Many Requests
    assert 429 in status_codes, f"Rate limit 429 was not triggered. Codes observed: {status_codes}"
