from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.db import Base, get_db
from app.main import app
from app import models  # noqa: F401


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db_client() -> Generator[TestClient, None, None]:
    if not settings.test_database_url:
        pytest.skip(
            "TEST_DATABASE_URL is not set. Use a dedicated hosted Postgres database for tests."
        )

    engine = create_engine(settings.test_database_url, pool_pre_ping=True)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS products CASCADE"))
            connection.execute(text("DROP TABLE IF EXISTS customers CASCADE"))
            connection.execute(text("DROP TABLE IF EXISTS suppliers CASCADE"))
        engine.dispose()
