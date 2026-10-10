# PayLedger API

A production-grade **double-entry payment ledger** backend built with FastAPI and PostgreSQL.

## Problem statement

Moving money is easy to get wrong: a transfer that debits one account but never credits the other silently destroys funds, and a retried request that executes twice double-spends. PayLedger solves this the way real accounting systems do — with **double-entry bookkeeping**: every transfer writes a balanced pair of journal entries (debit + credit), the database itself enforces that debits equal credits per transaction, and **idempotency keys** make retries safe. On top of that it adds JWT authentication with role-based access control, rate limiting, a background reconciliation worker that hunts for imbalanced journals, and a full audit log of every mutation.

## Architecture

```mermaid
flowchart LR
    Client -->|JWT Bearer| API[FastAPI app]
    API --> Auth[JWT Auth + RBAC\nadmin / accountant / viewer]
    API --> RL[slowapi rate limiter]
    API --> LS[Ledger Service]
    LS -->|balanced debit+credit| DB[(PostgreSQL)]
    LS -->|idempotency key| DB
    API --> AS[Audit Service]
    AS --> AL[(audit_log table)]
    W[APScheduler worker\n(every 60s)] -->|scan for imbalance| DB
    W --> AL
    subgraph Read paths
        API -->|paginated, filterable| DB
    end
```

Key design decisions:

- **Double-entry journal** (`journal_entries` table): a transfer is one `transactions` row plus two journal rows (debit source, credit destination). A DB-level check plus application validation guarantees `SUM(debits) == SUM(credits)` per transaction — money can never be created or destroyed by a bug.
- **Idempotency** (`idempotency_keys` table): `POST /transfers` accepts an `Idempotency-Key` header. The key is stored with the resulting transaction id inside the same DB transaction, so concurrent retries with the same key return the original result instead of double-spending (proven by a threaded concurrency test).
- **RBAC**: `viewer` (read-only), `accountant` (accounts + transfers), `admin` (everything, incl. user management).
- **Reconciliation worker**: APScheduler runs every 60 s, re-sums journal entries per transaction, and writes any imbalance findings to the audit log.
- **Audit log**: every create/update/delete records actor, timestamp, action, entity, entity id, and a JSON diff.

## Quickstart

```bash
docker compose up --build
```

The API starts on http://localhost:8000 (docs at `/docs`), Postgres on 5432.
Override secrets via environment, e.g. `SECRET_KEY=... POSTGRES_PASSWORD=... docker compose up`.
To run DB migrations manually: `alembic upgrade head`.

Local dev without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head        # needs DATABASE_URL pointing at Postgres, or use sqlite default
uvicorn app.main:app --reload
```

## API examples

Register and log in:

```bash
curl -s -X POST localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"ops@example.com","password":"secret123","role":"accountant"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=ops@example.com&password=secret123' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Create two accounts and transfer between them (idempotent):

```bash
A=$(curl -s -X POST localhost:8000/accounts \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Treasury","currency":"INR"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
B=$(curl -s -X POST localhost:8000/accounts \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Vendor","currency":"INR"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Seed the source account, then transfer with an idempotency key —
# run the transfer twice with the same key: the second returns the
# original result, funds move exactly once.
curl -s -X POST localhost:8000/accounts/$A/deposit \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"amount":"1000.00"}'

curl -s -X POST localhost:8000/transfers \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: pay-2026-001' \
  -d "{\"source_account_id\":$A,\"destination_account_id\":$B,\"amount\":\"250.00\"}"

curl -s localhost:8000/accounts/$A/balance -H "Authorization: Bearer $TOKEN"
curl -s "localhost:8000/transfers?limit=10" -H "Authorization: Bearer $TOKEN"
```

Interactive docs: http://localhost:8000/docs

## Running tests

```bash
pip install -r requirements.txt
pytest -q
```

Tests default to SQLite (`DATABASE_URL` override). Postgres-only tests are marked
`@pytest.mark.pg` and skip automatically without a Postgres `DATABASE_URL`.
The suite covers: auth + RBAC (viewer blocked from transfers), double-entry
balance enforcement (incl. DB check constraint), idempotency (same key twice =
one transfer), threaded no-double-spend concurrency, the reconciliation worker,
the audit log, and rate limiting.

Load testing (manual, not in CI):

```bash
locust -f scripts/load_test.py --host http://localhost:8000
```

## Project layout

```
app/
  main.py            # FastAPI app, router wiring, scheduler startup
  config.py          # pydantic-settings (env-driven, sane local defaults)
  database.py        # SQLAlchemy engine/session
  models.py          # User, Account, Transaction, JournalEntry, IdempotencyKey, AuditLog
  schemas.py         # Pydantic v2 request/response schemas
  security.py        # JWT issue/verify, bcrypt, RBAC dependencies
  limiter.py         # slowapi rate limiter
  worker.py          # APScheduler bootstrap
  routers/           # auth, users, accounts, transfers, audit_logs
  services/          # ledger_service, audit_service, reconciliation_service
alembic/             # env.py + 0001_initial_schema migration
tests/               # pytest suite (26 tests)
scripts/load_test.py # Locust scenario (manual use only)
```

## What I would do next

- Move money with `SELECT ... FOR UPDATE` row locks already in place; next step is
  benchmarking transfer throughput under contention and tuning the isolation level.
- Add webhook delivery for transfer settlement events with signed payloads and retries.
- Multi-currency support with an FX rate table and per-currency balance rollups.
- Soft-delete for accounts with a closed-at lifecycle instead of hard deletes.
- Prometheus metrics (transfer latency histogram, reconciliation findings counter)
  and structured JSON logging.
