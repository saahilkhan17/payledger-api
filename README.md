# PayLedger API

PayLedger API is a production-grade, double-entry payment ledger backend built with FastAPI, SQLAlchemy 2.0, PostgreSQL, and APScheduler.

It guarantees strict financial invariants:
- **Double-Entry Bookkeeping**: Every financial transfer consists of balanced journal entries (debits equal credits). Balance is enforced both at the application service level and at the database level via table check constraints.
- **Concurrency-Safe Idempotency**: `POST /transfers` mandates or accepts an `Idempotency-Key` header, tracked via an `idempotency_records` table to prevent double-spending under concurrent retries or network replays.
- **JWT Authentication & Role-Based Access Control (RBAC)**: Secure user registration and login issuing signed OAuth2 JWT bearer tokens supporting three roles: `admin`, `accountant`, and `viewer`.
- **Rate Limiting**: Transfer endpoints are protected using Slowapi (`30/minute` default limit).
- **Automated Background Reconciliation Worker**: Periodic ledger scanning via APScheduler verifying that transaction debit/credit totals balance with underlying journal entries, logging any discrepancies directly to the audit log.
- **Comprehensive Mutation Audit Log**: All state mutations (account creation, funding deposits, transfers, user role changes, and reconciliation discrepancies) are recorded in an append-only `audit_logs` table with actor, action, timestamp, entity ID, and JSON diffs.

---

## Architecture

```mermaid
flowchart TD
    Client["Client / Payment Service"]

    subgraph API_Layer ["PayLedger FastAPI Service"]
        Router["API Routers\n(/auth, /users, /accounts, /transfers, /audit-logs)"]
        Limiter["Slowapi Rate Limiter\n(30 req/min on transfers)"]
        Auth["JWT Auth & RBAC\n(admin / accountant / viewer)"]
        Service["Ledger Service & Audit Service"]
    end

    subgraph Background_Layer ["Reconciliation Worker"]
        Worker["APScheduler Worker\n(reconciliation_job)"]
    end

    subgraph Database ["PostgreSQL / SQLite Database"]
        Users[("users")]
        Accounts[("accounts\n(ASSET, LIABILITY, EQUITY,\nREVENUE, EXPENSE)")]
        Transactions[("transactions\n(chk_transaction_balanced:\ntotal_debit = total_credit)")]
        JournalEntries[("journal_entries\n(DEBIT / CREDIT legs)")]
        Idempotency[("idempotency_records")]
        AuditLog[("audit_logs\n(diff JSON & mutations)")]
    end

    Client -->|HTTP / Bearer Token| Router
    Router --> Limiter
    Router --> Auth
    Auth --> Service
    Service -->|Atomically insert| Transactions
    Service -->|Debit + Credit legs| JournalEntries
    Service -->|Check & claim key| Idempotency
    Service -->|Record mutation| AuditLog
    Service -->|Query balances & status| Accounts

    Worker -->|Scan transactions & sum legs| JournalEntries
    Worker -->|Verify totals| Transactions
    Worker -->|Log discrepancies| AuditLog
```

---

## Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12)
- **ASGI Server**: [Uvicorn](https://www.uvicorn.org/)
- **ORM / Database Tooling**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/), [Alembic](https://alembic.sqlalchemy.org/) migrations
- **Database**: PostgreSQL 16 (`psycopg` v3 driver) / SQLite for local self-contained tests
- **Authentication & Security**: JWT (`python-jose`), password hashing (`passlib`, `bcrypt`)
- **Rate Limiting**: `slowapi`
- **Scheduler**: [APScheduler](https://apscheduler.readthedocs.io/) (BackgroundScheduler)
- **Validation**: Pydantic v2 & `pydantic-settings`
- **Testing & Benchmarking**: `pytest`, `httpx`, `locust`

---

## Prerequisites

- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/) (v2+ recommended)
- **OR** Python 3.12+ with `pip` and a running PostgreSQL instance (or SQLite for local dev)

---

## Quickstart via Docker Compose

Run the entire stack (PostgreSQL 16, API server with automatic Alembic migrations, and dedicated background reconciliation worker):

```bash
docker compose up --build
```

- **API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Healthcheck**: [http://localhost:8000/health](http://localhost:8000/health)

To customize environment variables (such as PostgreSQL credentials or secrets), set them in your shell or create a `.env` file (see `.env.example`):

```bash
POSTGRES_USER=payledger POSTGRES_PASSWORD=mysecretpassword docker compose up --build
```

---

## Environment Variables

All settings are configured via environment variables and managed by `app.config.Settings` (`pydantic-settings`):

| Variable | Default Value | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./payledger.db` | SQLAlchemy connection string (e.g. `postgresql+psycopg://user:pass@host:5432/dbname`) |
| `SECRET_KEY` | `payledger-super-secure-secret-key-change-in-production-2026` | Secret key used for signing JWT access tokens |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT token validity window in minutes |
| `TRANSFER_RATE_LIMIT` | `30/minute` | Slowapi rate limit expression for transfer creation |
| `ENABLE_SCHEDULER` | `true` | Boolean flag (`true`/`false`) controlling whether the APScheduler reconciliation worker runs |
| `RECONCILIATION_INTERVAL_SECONDS` | `60` | Interval in seconds between periodic ledger reconciliation scans |
| `PROJECT_NAME` | `PayLedger API` | Name of the application |
| `VERSION` | `1.0.0` | API version string |
| `API_V1_STR` | `/api/v1` | Base API routing prefix (reserved) |

---

## Running Database Migrations (Alembic)

Alembic manages schema evolution for PostgreSQL and SQLite.

- **Apply all pending migrations**:
  ```bash
  alembic upgrade head
  ```
- **Revert the last migration**:
  ```bash
  alembic downgrade -1
  ```
- **Create a new migration revision**:
  ```bash
  alembic revision --autogenerate -m "describe_change"
  ```

*Note: In Docker Compose, `alembic upgrade head` is automatically executed before the Uvicorn process starts.*

---

## Local Development Without Docker

1. **Create and activate a virtual environment**:
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```
4. **Start the development server**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

---

## Running Tests

The test suite in `tests/` uses `pytest` and runs against an isolated SQLite test database with WAL mode enabled. Tests marked with `@pytest.mark.pg` run only when a PostgreSQL `DATABASE_URL` is configured and skip automatically on SQLite.

Run the test suite:

```bash
pytest -q
```

The test suite verifies:
- Double-entry balance invariants (balanced debits and credits, rejection of unbalanced entries, database check constraint validation).
- Idempotency mechanisms (`Idempotency-Key` header reuse returns original transaction and prevents duplicate debits/credits).
- High-concurrency safety (multi-threaded concurrent requests with identical idempotency keys).
- Role-Based Access Control (RBAC) ensuring `viewer` cannot initiate transfers or accounts, while `accountant` and `admin` can.
- Rate limiting behavior via `slowapi`.
- APScheduler reconciliation worker detecting simulated unbalanced ledger transactions and logging discrepancy audit events.
- Audit log persistence and JSON diff parsing.

---

## API Endpoints Summary

All routes are mounted at root level:

### Authentication (`/auth`)
- `POST /auth/register` — Register a new user (`username`, `email`, `password`, optional `role`).
- `POST /auth/login` — Authenticate with form credentials (`username`, `password`) and receive a JWT bearer token.
- `GET /auth/me` — Return details of the currently authenticated user.

### Users (`/users`) — Admin Only
- `GET /users` — Paginated list of users with optional filtering by `role` and `is_active`.
- `GET /users/{user_id}` — Get specific user details.
- `PATCH /users/{user_id}` — Update user role or active status.

### Accounts (`/accounts`)
- `POST /accounts` — Create an account (`ASSET`, `LIABILITY`, `EQUITY`, `REVENUE`, `EXPENSE`). *Requires `accountant` or `admin`.*
- `GET /accounts` — Paginated list of accounts with filtering by `status`, `type`, and `currency`.
- `GET /accounts/{account_id}` — Get account details.
- `GET /accounts/{account_id}/balance` — Get real-time balance calculated from journal entries (`normal debit` for assets/expenses; `normal credit` for liabilities/equity/revenue).
- `POST /accounts/{account_id}/deposit` — Seed or deposit funds into an account against `SYS-TREASURY`. *Requires `accountant` or `admin`.*

### Transfers (`/transfers`)
- `POST /transfers` — Execute a double-entry transfer between source and destination accounts. Supports optional or mandatory `Idempotency-Key` header and rate limiting. *Requires `accountant` or `admin`.*
- `GET /transfers` — Paginated list of transactions with filtering by `status`, `start_date`, and `end_date`.
- `GET /transfers/{transfer_id}` — Retrieve transfer record and its constituent debit/credit journal entries.

### Audit Logs (`/audit-logs`)
- `GET /audit-logs` — Paginated query of mutation audit events with filtering by `entity`, `action`, `actor`, `entity_id`, and date ranges.

### Health
- `GET /health` — Service healthcheck returning status, service name, and version.

---

## Load Testing

The repository includes a [Locust](https://locust.io/) performance test script at `scripts/load_test.py`. It simulates realistic client workflows: user registration, login, account creation, initial funding, and concurrent double-entry transfers with idempotency keys.

Run the load test manually:

```bash
locust -f scripts/load_test.py --host http://localhost:8000
```

*(Note: Load tests are intended for manual performance benchmarking and are intentionally excluded from CI).*

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI workflow (Python 3.12 + pytest)
├── alembic/
│   ├── env.py                   # Alembic environment configuration
│   ├── script.py.mako           # Migration script template
│   └── versions/
│       └── 0001_initial_schema.py # Initial database schema migration
├── app/
│   ├── __init__.py
│   ├── config.py                # Pydantic BaseSettings environment configuration
│   ├── database.py              # SQLAlchemy engine, session maker, base model
│   ├── limiter.py               # Slowapi rate limiter setup
│   ├── main.py                  # FastAPI application entrypoint and lifespan handlers
│   ├── models.py                # Database models (User, Account, Transaction, JournalEntry, etc.)
│   ├── schemas.py               # Pydantic v2 schemas and request/response models
│   ├── security.py              # Password hashing, JWT token verification, RBAC dependencies
│   ├── worker.py                # APScheduler background reconciliation job setup
│   ├── routers/
│   │   ├── accounts.py          # Account creation, listing, deposit, and balance endpoints
│   │   ├── audit_logs.py        # Audit log querying and filtering endpoints
│   │   ├── auth.py              # User registration and login endpoints
│   │   ├── transfers.py         # Transfer execution and transaction querying endpoints
│   │   └── users.py             # User management endpoints (Admin only)
│   └── services/
│       ├── audit_service.py     # Audit event logging helper
│       ├── ledger_service.py    # Double-entry transaction logic & balance calculations
│       └── reconciliation_service.py # Journal entry consistency checks & imbalance detection
├── scripts/
│   └── load_test.py             # Locust performance testing scenario
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures, test database setup, and mock clients
│   ├── test_accounts.py         # Tests for account creation and balance calculation
│   ├── test_audit_log.py        # Tests for audit trail recording
│   ├── test_auth.py             # Tests for authentication and token validation
│   ├── test_concurrency.py      # Concurrency tests for transfer execution
│   ├── test_idempotency.py      # Tests for idempotency key handling
│   ├── test_ledger_double_entry.py # Tests for double-entry invariants and constraints
│   ├── test_rate_limit.py       # Tests for endpoint rate limiting
│   ├── test_rbac.py             # Role-based access control tests
│   └── test_reconciliation.py  # Tests for reconciliation worker and discrepancy logging
├── .env.example                 # Example environment variables template
├── .gitignore                   # Git ignore patterns
├── Dockerfile                   # Multi-stage/cached Docker container image definition
├── docker-compose.yml           # Compose stack: PostgreSQL, API, and background worker
├── alembic.ini                  # Alembic CLI configuration
└── requirements.txt             # Production and test dependencies
```
