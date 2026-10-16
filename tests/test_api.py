def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "research_only"


def test_research_validation(client):
    response = client.post("/api/v1/research", json={"query": "x"})
    assert response.status_code == 422


def test_products_offers_and_history_routes(client):
    assert client.get("/api/v1/products").status_code == 200
    assert client.get("/api/v1/offers").status_code == 200
    assert client.get("/api/v1/history").status_code == 200



def test_price_alert_routes(client):
    assert client.get("/api/v1/alerts").status_code == 200
    assert client.get("/api/v1/alerts?unread_only=true").status_code == 200
    assert client.post("/api/v1/alerts/999999/read").status_code == 404
