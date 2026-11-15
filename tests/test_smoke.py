def test_root_requires_api_key(client):
    response = client.get("/")
    assert response.status_code == 401


def test_root_rejects_wrong_api_key(client):
    response = client.get("/", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_root_with_api_key(client):
    response = client.get("/", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    assert response.json()["project"] == "BOL"
