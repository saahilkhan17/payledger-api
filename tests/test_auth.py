import uuid


def test_register_success(client):
    uid = uuid.uuid4().hex[:6]
    payload = {
        "username": f"user_{uid}",
        "email": f"user_{uid}@example.com",
        "password": "Password123!",
        "role": "viewer",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == payload["username"]
    assert data["email"] == payload["email"]
    assert data["role"] == "viewer"
    assert "id" in data


def test_register_duplicate_username(client):
    uid = uuid.uuid4().hex[:6]
    payload = {
        "username": f"dup_{uid}",
        "email": f"dup1_{uid}@example.com",
        "password": "Password123!",
        "role": "viewer",
    }
    res1 = client.post("/auth/register", json=payload)
    assert res1.status_code == 201

    payload["email"] = f"dup2_{uid}@example.com"
    res2 = client.post("/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already registered" in res2.json()["detail"]


def test_login_oauth2_success(client):
    uid = uuid.uuid4().hex[:6]
    password = "MySecurePassword123!"
    client.post(
        "/auth/register",
        json={
            "username": f"login_{uid}",
            "email": f"login_{uid}@example.com",
            "password": password,
            "role": "accountant",
        },
    )

    response = client.post(
        "/auth/login",
        data={"username": f"login_{uid}", "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    response = client.post(
        "/auth/login",
        data={"username": "non_existent_user", "password": "wrongpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 401


def test_get_current_user_me(client):
    uid = uuid.uuid4().hex[:6]
    password = "ValidPassword123!"
    uname = f"me_{uid}"
    client.post(
        "/auth/register",
        json={
            "username": uname,
            "email": f"{uname}@example.com",
            "password": password,
            "role": "admin",
        },
    )

    login_res = client.post(
        "/auth/login",
        data={"username": uname, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_res.json()["access_token"]

    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["username"] == uname
    assert me_data["role"] == "admin"


def test_get_current_user_unauthorized(client):
    res = client.get("/auth/me")
    assert res.status_code == 401
