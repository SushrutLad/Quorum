import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from db import connect  # noqa: E402
from seed import seed  # noqa: E402


@pytest.fixture
def app(tmp_path):
    path = str(tmp_path / "test.db")
    seed(path)                      # every test gets a fresh copy of the demo data
    return create_app({"TESTING": True, "DATABASE": path})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    conn = connect(app.config["DATABASE"])
    yield conn
    conn.close()


def login(client, username, password):
    client.get("/logout")
    return client.post("/login", data={"username": username, "password": password})
