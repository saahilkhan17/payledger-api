import uuid


def test_audit_logs_record_mutations(client, admin_headers, accountant_headers):
    # 1. Register a user -> should record audit log
    uid = uuid.uuid4().hex[:6]
    user_payload = {
        "username": f"audit_user_{uid}",
        "email": f"audit_{uid}@example.com",
        "password": "Password123!",
        "role": "viewer",
    }
    user_res = client.post("/auth/register", json=user_payload)
    assert user_res.status_code == 201
    created_user_id = user_res.json()["id"]

    # 2. Accountant creates an account -> should record audit log
    acc_res = client.post(
        "/accounts",
        json={"name": f"Audit Acc {uid}", "type": "ASSET", "currency": "USD"},
        headers=accountant_headers,
    )
    assert acc_res.status_code == 201
    created_acc_id = acc_res.json()["id"]

    # 3. Admin updates user -> should record audit log
    update_res = client.patch(
        f"/users/{created_user_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert update_res.status_code == 200

    # 4. Query /audit-logs endpoint
    # Filter by entity User
    logs_user = client.get("/audit-logs?entity=User", headers=admin_headers)
    assert logs_user.status_code == 200
    user_items = logs_user.json()["items"]
    assert any(log["entity_id"] == created_user_id for log in user_items)

    # Filter by entity Account
    logs_acc = client.get("/audit-logs?entity=Account", headers=admin_headers)
    assert logs_acc.status_code == 200
    acc_items = logs_acc.json()["items"]
    assert any(log["entity_id"] == created_acc_id for log in acc_items)

    # Check diff structure
    found_acc_log = next(log for log in acc_items if log["entity_id"] == created_acc_id)
    assert found_acc_log["action"] == "CREATE"
    assert found_acc_log["actor"] != ""
    assert isinstance(found_acc_log["diff"], dict)
    assert found_acc_log["diff"]["name"] == f"Audit Acc {uid}"
