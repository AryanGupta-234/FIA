def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "research_only"


def test_research_validation(client):
    response = client.post("/api/v1/research", json={"query": "x"})
    assert response.status_code == 422
