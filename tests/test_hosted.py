import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.auth import COOKIE, CSRF_COOKIE, digest
from app.quotas import reserve_model_call, BudgetExceeded

ORIGIN = "https://ragvanta.example"
PASSWORD = "a-long-synthetic-test-password"


@pytest.fixture
def hosted(tmp_path):
    settings = Settings(data_dir=tmp_path, deployment="hosted", public_url=ORIGIN, _env_file=None)
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        auth = client.app.state.auth
        auth.create_user("alice", PASSWORD)
        auth.create_user("bob", PASSWORD)
        yield client, settings


def login(client, username="alice"):
    response = client.post("/auth/login", json={"username": username, "password": PASSWORD},
                           headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}


def test_no_anonymous_data(hosted):
    client, _ = hosted
    for path in ("/v1/collections", "/v1/scenarios", "/v1/experiments", "/auth/me", "/v1/reports/x"):
        assert client.get(path).status_code == 401
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/", headers={"host": "attacker.test"}).status_code == 400


def test_session_security_and_logout(hosted):
    client, _ = hosted
    headers = login(client)
    assert client.get("/auth/me").json()["username"] == "alice"
    rows = client.app.state.lab.store.query("SELECT * FROM sessions")
    token = client.cookies.get(COOKIE)
    assert rows[0]["token_hash"] == digest(token)
    assert token not in str(rows)
    assert client.post("/v1/collections", json={"name": "x"}).status_code == 403
    assert client.post("/v1/collections", json={"name": "x"}, headers={"Origin": ORIGIN}).status_code == 403
    assert client.post("/v1/collections", json={"name": "x"}, headers=headers | {"Origin": "https://evil.test"}).status_code == 403
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert client.app.state.auth.session(token) is None


def test_tenant_isolation_all_routes(hosted):
    client, _ = hosted
    alice = login(client)
    cid = client.post("/v1/collections", json={"name": "private"}, headers=alice).json()["id"]
    upload = client.post("/v1/documents", data={"collection_id": cid, "synthetic": "true"},
                         files={"file": ("policy.txt", b"Return window is 7 days.")}, headers=alice)
    assert upload.status_code == 201, upload.text
    did = upload.json()["id"]
    report = client.post("/v1/experiments", json={"limit": 1}, headers=alice).json()
    run_id = report["id"]
    bob = login(client, "bob")
    assert client.get("/v1/collections").json() == []
    assert client.get("/v1/experiments").json() == []
    for path in (f"/v1/documents?collection_id={cid}", f"/v1/documents/{did}/chunks",
                 f"/v1/experiments/{run_id}", f"/v1/experiments/{run_id}/results", f"/v1/reports/{run_id}"):
        assert client.get(path).status_code == 404, path
    assert client.post("/v1/chat", json={"question": "return window", "collection_id": cid}, headers=bob).status_code == 404
    assert client.post("/v1/documents", data={"collection_id": cid, "synthetic": "true"},
                       files={"file": ("policy.txt", b"other")}, headers=bob).status_code == 404


def test_cookie_headers_and_revocation(hosted):
    client, _ = hosted
    response = client.post("/auth/login", json={"username": "alice", "password": PASSWORD}, headers={"Origin": ORIGIN})
    cookies = response.headers.get_list("set-cookie")
    assert "HttpOnly" in cookies[0] and "Secure" in cookies[0] and "SameSite=strict" in cookies[0]
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    client.app.state.auth.disable_user("alice")
    assert client.get("/auth/me").status_code == 401


def test_login_bruteforce_and_generic_errors(hosted):
    client, _ = hosted
    for _ in range(5):
        r = client.post("/auth/login", json={"username": "alice", "password": "bad"}, headers={"Origin": ORIGIN})
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid credentials"
    assert client.post("/auth/login", json={"username": "alice", "password": PASSWORD}, headers={"Origin": ORIGIN}).status_code == 429


def test_quotas_and_synthetic_confirmation(hosted):
    client, config = hosted
    config.max_collections = 1
    headers = login(client)
    cid = client.post("/v1/collections", json={"name": "first"}, headers=headers).json()["id"]
    assert client.post("/v1/collections", json={"name": "second"}, headers=headers).status_code == 413
    assert client.post("/v1/documents", data={"collection_id": cid}, files={"file": ("p.txt", b"test")}, headers=headers).status_code == 400
    config.daily_user_model_calls = 1
    scoped = config.model_copy(update={"actor_id": "alice"})
    reserve_model_call(client.app.state.lab.store, scoped)
    with pytest.raises(BudgetExceeded):
        reserve_model_call(client.app.state.lab.store, scoped)


def test_hosted_configuration_rejects_unsafe_origin():
    with pytest.raises(ValueError):
        Settings(deployment="hosted", public_url="http://example.test", _env_file=None)
    with pytest.raises(ValueError):
        Settings(deployment="hosted", public_url=ORIGIN, api_token="shared", _env_file=None)


def test_delete_document_requires_owner(hosted):
    client, _ = hosted
    headers = login(client)
    cid = client.post('/v1/collections', json={'name': 'delete-test'}, headers=headers).json()['id']
    did = client.post('/v1/documents', data={'collection_id': cid, 'synthetic': 'true'},
                      files={'file': ('p.txt', b'Test policy is 7 days.')}, headers=headers).json()['id']
    other = login(client, 'bob')
    assert client.delete(f'/v1/documents/{did}', headers=other).status_code == 404
    owner = login(client)
    assert client.delete(f'/v1/documents/{did}', headers=owner).status_code == 204
    assert client.get(f'/v1/documents/{did}/chunks').status_code == 404


def test_restart_invalidates_pending_run(tmp_path):
    import json
    import time
    from app.storage import Store
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?,?,?,?)', ('pending', 'alice', time.time(), 'running',
                   json.dumps({'id': 'pending', 'status': 'running', 'cases': [], 'metrics': {}})))
    with TestClient(create_app(Settings(data_dir=tmp_path, deployment='hosted', public_url=ORIGIN, _env_file=None))):
        assert store.query("SELECT status FROM runs WHERE id='pending'")[0]["status"] == "interrupted"


def test_collection_delete_requires_owner_origin_and_csrf(hosted):
    client, _ = hosted
    alice = login(client)
    cid = client.post('/v1/collections', json={'name': 'Owned by Alice'}, headers=alice).json()['id']
    bob = login(client, 'bob')
    assert client.delete('/v1/collections/' + cid, headers=bob).status_code == 404
    alice = login(client)
    assert client.delete('/v1/collections/' + cid, headers={'Origin': ORIGIN}).status_code == 403
    assert client.delete('/v1/collections/' + cid, headers=alice | {'Origin': 'https://evil.test'}).status_code == 403
    assert client.delete('/v1/collections/' + cid, headers=alice).status_code == 204
