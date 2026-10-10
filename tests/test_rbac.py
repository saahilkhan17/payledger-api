import uuid


def test_viewer_cannot_create_account(client, viewer_headers):
    payload = {
        "name": "Unauthorized Account",
        "type": "ASSET",
        "currency": "USD",
    }
    response = client.post("/accounts", json=payload, headers=viewer_headers)
    assert response.status_code == 403
    assert "Operation not permitted" in response.json()["detail"]


def test_viewer_cannot_create_transfer(client, viewer_headers, accountant_headers):
    # Setup accounts with accountant
    res_a = client.post(
        "/accounts",
        json={"name": "Src Acc", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    res_b = client.post(
        "/accounts",
        json={"name": "Dst Acc", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    src_id = res_a.json()["id"]
    dst_id = res_b.json()["id"]

    # Fund src account
    client.post(
        f"/accounts/{src_id}/deposit",
        json={"amount": "100.0000"},
        headers=accountant_headers,
    )

    # Viewer tries to initiate transfer
    tx_payload = {
        "source_account_id": src_id,
        "destination_account_id": dst_id,
        "amount": "25.0000",
        "currency": "USD",
    }
    response = client.post("/transfers", json=tx_payload, headers=viewer_headers)
    assert response.status_code == 403
    assert "Operation not permitted" in response.json()["detail"]


def test_viewer_can_read_endpoints(client, viewer_headers):
    res_accounts = client.get("/accounts", headers=viewer_headers)
    assert res_accounts.status_code == 200
    assert "items" in res_accounts.json()

    res_transfers = client.get("/transfers", headers=viewer_headers)
    assert res_transfers.status_code == 200
    assert "items" in res_transfers.json()


def test_accountant_can_create_accounts_and_transfers(client, accountant_headers):
    # Accountant creates accounts
    res_a = client.post(
        "/accounts",
        json={"name": "Acc A", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    assert res_a.status_code == 201
    src_id = res_a.json()["id"]

    res_b = client.post(
        "/accounts",
        json={"name": "Acc B", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    assert res_b.status_code == 201
    dst_id = res_b.json()["id"]

    # Deposit funds
    dep_res = client.post(
        f"/accounts/{src_id}/deposit",
        json={"amount": "500.0000"},
        headers=accountant_headers,
    )
    assert dep_res.status_code == 201

    # Transfer funds
    tx_res = client.post(
        "/transfers",
        json={
            "source_account_id": src_id,
            "destination_account_id": dst_id,
            "amount": "50.0000",
            "currency": "USD",
        },
        headers=accountant_headers,
    )
    assert tx_res.status_code == 201
    assert tx_res.json()["status"] == "POSTED"


def test_accountant_cannot_manage_users(client, accountant_headers):
    res = client.get("/users", headers=accountant_headers)
    assert res.status_code == 403


def test_admin_can_manage_users(client, admin_headers):
    # Admin can list users
    res = client.get("/users", headers=admin_headers)
    assert res.status_code == 200
    users_data = res.json()
    assert users_data["total"] >= 1

    # Admin can inspect user
    target_user_id = users_data["items"][0]["id"]
    get_res = client.get(f"/users/{target_user_id}", headers=admin_headers)
    assert get_res.status_code == 200

    # Admin can update user role
    update_res = client.patch(
        f"/users/{target_user_id}",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert update_res.status_code == 200
