"""POST /auth/login — password verification is mocked so these run without
a live BigQuery connection; agent_guardian/auth.py's real query path is
exercised manually against BigQuery, not here."""

import pytest


@pytest.fixture(scope="module")
def api_app():
    from api.main import app

    return app


@pytest.mark.asyncio
async def test_login_success(api_app, monkeypatch):
    import httpx
    import agent_guardian.auth as auth

    monkeypatch.setattr(
        auth,
        "verify_credentials",
        lambda username, password: {"userId": username, "department": "Engineering", "country": "US"},
    )

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/login", json={"username": "jdoe", "password": "correct-horse"})
        assert resp.status_code == 200
        assert resp.json() == {"userId": "jdoe", "department": "Engineering", "country": "US"}


@pytest.mark.asyncio
async def test_login_rejects_bad_credentials(api_app, monkeypatch):
    import httpx
    import agent_guardian.auth as auth

    monkeypatch.setattr(auth, "verify_credentials", lambda username, password: None)

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/login", json={"username": "jdoe", "password": "wrong"})
        assert resp.status_code == 401
        assert "username" not in resp.text.lower() or "invalid" in resp.text.lower()


def test_hash_password_is_not_reversible_encoding():
    from agent_guardian.auth import hash_password
    import bcrypt

    plaintext = "correct-horse-battery-staple"
    hashed = hash_password(plaintext)

    assert hashed != plaintext
    assert bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    assert not bcrypt.checkpw(b"wrong-password", hashed.encode("utf-8"))


def test_verify_credentials_case_insensitive(monkeypatch):
    from agent_guardian.auth import verify_credentials
    import bcrypt

    class MockRow:
        def __init__(self, data):
            self.data = data

        def __getitem__(self, key):
            return self.data[key]

    class MockJob:
        def __init__(self, rows):
            self.rows = rows

        def result(self):
            return self.rows

    class MockClient:
        def query(self, query_str, job_config=None):
            params = job_config.query_parameters if job_config else []
            username_lower = None
            for p in params:
                if p.name == "username_lower":
                    username_lower = p.value

            if username_lower == "jdoe":
                pwd_hash = bcrypt.hashpw(b"correct-horse", bcrypt.gensalt()).decode("utf-8")
                return MockJob(
                    [
                        MockRow(
                            {
                                "username": "JDoe",
                                "password_hash": pwd_hash,
                                "department": "Engineering",
                                "country": "US",
                                "is_active": True,
                            }
                        )
                    ]
                )
            return MockJob([])

    monkeypatch.setattr("agent_guardian.auth._get_client", lambda: MockClient())

    # Test exact match (ignoring case)
    res1 = verify_credentials("jdoe", "correct-horse")
    assert res1 is not None
    assert res1["userId"] == "JDoe"
    assert res1["department"] == "Engineering"

    # Test case-insensitive match
    res2 = verify_credentials("JDOE", "correct-horse")
    assert res2 is not None
    assert res2["userId"] == "JDoe"

    # Test mismatch password
    res3 = verify_credentials("jdoe", "wrong")
    assert res3 is None

    # Test mismatch username
    res4 = verify_credentials("unknown", "correct-horse")
    assert res4 is None


def test_ensure_users_table_creates_when_not_found(monkeypatch):
    from agent_guardian.auth import ensure_users_table
    from google.cloud.exceptions import NotFound

    created_datasets = []
    created_tables = []

    class MockClient:
        def get_dataset(self, ref):
            raise NotFound("Dataset not found")

        def create_dataset(self, dataset, exists_ok=True):
            created_datasets.append(dataset)

        def get_table(self, ref):
            raise NotFound("Table not found")

        def create_table(self, table, exists_ok=True):
            created_tables.append(table)

    mock_client = MockClient()
    ensure_users_table(mock_client)

    assert len(created_datasets) == 1
    assert len(created_tables) == 1
    schema_fields = {f.name: f.field_type for f in created_tables[0].schema}
    assert "username" in schema_fields
    assert "password_hash" in schema_fields
    assert "department" in schema_fields
    assert "country" in schema_fields
    assert "is_active" in schema_fields


def test_verify_credentials_handles_table_not_found(monkeypatch):
    from agent_guardian.auth import verify_credentials
    from google.cloud.exceptions import NotFound

    ensure_called = []

    class MockClient:
        def query(self, query_str, job_config=None):
            raise NotFound("Table not found")

    monkeypatch.setattr("agent_guardian.auth._get_client", lambda: MockClient())
    monkeypatch.setattr("agent_guardian.auth.ensure_users_table", lambda client=None: ensure_called.append(True))

    res = verify_credentials("jdoe", "correct-horse")
    assert res is None
    assert len(ensure_called) == 1

