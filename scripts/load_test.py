import uuid
from locust import HttpUser, task, between


class PayLedgerUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        """Simulate user workflow: Register -> Login -> Create Accounts -> Fund Source."""
        uid = uuid.uuid4().hex[:8]
        self.username = f"loadtest_{uid}"
        self.email = f"loadtest_{uid}@example.com"
        self.password = "StrongPass123!"

        # 1. Register
        reg_payload = {
            "username": self.username,
            "email": self.email,
            "password": self.password,
            "role": "accountant",
        }
        res = self.client.post("/auth/register", json=reg_payload)
        if res.status_code != 201:
            return

        # 2. Login (OAuth2 Form Data)
        login_res = self.client.post(
            "/auth/login",
            data={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if login_res.status_code != 200:
            return

        token_data = login_res.json()
        self.token = token_data.get("access_token")
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}

        # 3. Create Source Account
        res_a = self.client.post(
            "/accounts",
            json={
                "name": f"Source-{uid}",
                "type": "ASSET",
                "currency": "USD",
                "status": "ACTIVE",
            },
            headers=self.auth_headers,
        )
        self.account_a_id = res_a.json().get("id") if res_a.status_code == 201 else None

        # 4. Create Destination Account
        res_b = self.client.post(
            "/accounts",
            json={
                "name": f"Destination-{uid}",
                "type": "ASSET",
                "currency": "USD",
                "status": "ACTIVE",
            },
            headers=self.auth_headers,
        )
        self.account_b_id = res_b.json().get("id") if res_b.status_code == 201 else None

        # 5. Initial Deposit to Source Account
        if self.account_a_id:
            self.client.post(
                f"/accounts/{self.account_a_id}/deposit",
                json={"amount": "10000.0000", "description": "Initial funding"},
                headers=self.auth_headers,
            )

    @task(3)
    def transfer_funds(self):
        """Execute double-entry transfer with idempotency key."""
        if not getattr(self, "account_a_id", None) or not getattr(self, "account_b_id", None):
            return

        idempotency_key = str(uuid.uuid4())
        headers = {
            **self.auth_headers,
            "Idempotency-Key": idempotency_key,
        }
        payload = {
            "source_account_id": self.account_a_id,
            "destination_account_id": self.account_b_id,
            "amount": "10.0000",
            "currency": "USD",
            "description": "Locust automated transfer",
        }
        self.client.post("/transfers", json=payload, headers=headers)

    @task(2)
    def check_balance(self):
        """Check balance of accounts."""
        if getattr(self, "account_a_id", None):
            self.client.get(f"/accounts/{self.account_a_id}/balance", headers=self.auth_headers)

    @task(1)
    def list_transfers(self):
        """List transfers."""
        if getattr(self, "auth_headers", None):
            self.client.get("/transfers?limit=10", headers=self.auth_headers)
