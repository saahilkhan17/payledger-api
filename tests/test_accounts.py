import uuid
from decimal import Decimal


def test_create_and_get_account(client, accountant_headers):
    payload = {
        "name": "Treasury Account",
        "type": "ASSET",
        "currency": "USD",
        "status": "ACTIVE",
    }
    res = client.post("/accounts", json=payload, headers=accountant_headers)
    assert res.status_code == 201
    data = res.json()
    acc_id = data["id"]
    assert data["name"] == payload["name"]
    assert data["account_number"].startswith("ACC-")

    get_res = client.get(f"/accounts/{acc_id}", headers=accountant_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == acc_id


def test_list_accounts_pagination_and_filter(client, accountant_headers):
    uid = uuid.uuid4().hex[:6]
    for i in range(5):
        client.post(
            "/accounts",
            json={
                "name": f"Filter Acc {uid} {i}",
                "type": "LIABILITY" if i % 2 == 0 else "ASSET",
                "currency": "EUR" if i == 0 else "USD",
                "status": "ACTIVE",
            },
            headers=accountant_headers,
        )

    # Test pagination
    page_res = client.get("/accounts?skip=0&limit=2", headers=accountant_headers)
    assert page_res.status_code == 200
    data = page_res.json()
    assert len(data["items"]) == 2
    assert data["limit"] == 2

    # Test filter by type
    type_res = client.get("/accounts?type=LIABILITY", headers=accountant_headers)
    assert type_res.status_code == 200
    for acc in type_res.json()["items"]:
        assert acc["type"] == "LIABILITY"

    # Test filter by currency
    curr_res = client.get("/accounts?currency=EUR", headers=accountant_headers)
    assert curr_res.status_code == 200
    for acc in curr_res.json()["items"]:
        assert acc["currency"] == "EUR"


def test_get_account_balance(client, accountant_headers):
    # Create asset account
    res = client.post(
        "/accounts",
        json={"name": "Balance Check Acc", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    acc_id = res.json()["id"]

    # Balance initially 0
    bal_res_0 = client.get(f"/accounts/{acc_id}/balance", headers=accountant_headers)
    assert bal_res_0.status_code == 200
    assert Decimal(bal_res_0.json()["balance"]) == Decimal("0.0000")

    # Deposit $500
    client.post(
        f"/accounts/{acc_id}/deposit",
        json={"amount": "500.0000"},
        headers=accountant_headers,
    )

    bal_res_1 = client.get(f"/accounts/{acc_id}/balance", headers=accountant_headers)
    assert bal_res_1.status_code == 200
    assert Decimal(bal_res_1.json()["balance"]) == Decimal("500.0000")
    assert Decimal(bal_res_1.json()["total_debit"]) == Decimal("500.0000")
    assert Decimal(bal_res_1.json()["total_credit"]) == Decimal("0.0000")
