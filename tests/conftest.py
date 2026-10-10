import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Ensure test settings before importing app
TEST_DB_FILE = "./test_payledger.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_FILE}"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["ENABLE_SCHEDULER"] = "false"

from app.config import settings
settings.DATABASE_URL = TEST_DB_URL
settings.ENABLE_SCHEDULER = False

from app.database import Base, get_db
from app.limiter import limiter
from app.main import app
from app.models import User
from app.security import get_password_hash, create_access_token

test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def pytest_configure(config):
    config.addinivalue_line("markers", "pg: marks tests as requiring PostgreSQL")
    config.addinivalue_line("markers", "rate_limit: marks tests for rate limiting")


def pytest_collection_modifyitems(config, items):
    db_url = os.environ.get("DATABASE_URL", "sqlite")
    if "sqlite" in db_url:
        skip_pg = pytest.mark.skip(reason="PostgreSQL-specific test (skipped on SQLite)")
        for item in items:
            if "pg" in item.keywords:
                item.add_marker(skip_pg)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    for ext in ["", "-wal", "-shm"]:
        fpath = f"{TEST_DB_FILE}{ext}"
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass


@pytest.fixture
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_rate_limit():
    limiter.reset()
    yield
    limiter.reset()


def _create_user_and_token(role: str, username_prefix: str) -> dict:
    session = TestingSessionLocal()
    try:
        uname = f"{username_prefix}_{role}"
        existing = session.query(User).filter(User.username == uname).first()
        if not existing:
            u = User(
                username=uname,
                email=f"{uname}@example.com",
                hashed_password=get_password_hash("SecretPassword123!"),
                role=role,
                is_active=True,
            )
            session.add(u)
            session.commit()
            session.refresh(u)
            existing = u

        token = create_access_token({"sub": existing.username, "role": existing.role})
        return {
            "user": existing,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    finally:
        session.close()


@pytest.fixture
def admin_headers():
    data = _create_user_and_token("admin", "admin_user")
    return data["headers"]


@pytest.fixture
def accountant_headers():
    data = _create_user_and_token("accountant", "accountant_user")
    return data["headers"]


@pytest.fixture
def viewer_headers():
    data = _create_user_and_token("viewer", "viewer_user")
    return data["headers"]
