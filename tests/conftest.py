import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["BOL_API_KEY"] = "test-key"

# No real Postgres in smoke tests: every connection is a mock.
psycopg2.connect = MagicMock(name="psycopg2.connect")


@pytest.fixture(scope="session")
def client():
    os.chdir(ROOT)
    from fastapi.testclient import TestClient
    import app as bol_app

    return TestClient(bol_app.app)
