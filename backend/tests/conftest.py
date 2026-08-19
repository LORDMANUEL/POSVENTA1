import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["MZ_BOOTSTRAP_TOKEN"] = "test-bootstrap-token"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["MEDIA_ROOT"] = "/tmp/mily-zebra-test-media"
os.environ["OLLAMA_URL"] = ""

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def owner_headers(client):
    bootstrap = client.post(
        "/bootstrap",
        headers={"X-Bootstrap-Token": "test-bootstrap-token"},
        json={
            "store_name": "Mily Zebra",
            "store_slug": "mily-zebra",
            "branch_name": "Roatán",
            "email": "owner@example.com",
            "full_name": "Owner",
            "password": "super-secure-password",
        },
    )
    assert bootstrap.status_code == 200, bootstrap.text
    return {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}
