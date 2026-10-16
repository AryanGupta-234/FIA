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


def test_product_matches_route_requires_existing_product(client):
    assert client.get("/api/v1/products/999999/matches").status_code == 404


def test_offer_feed_can_explicitly_include_stale_entries(client):
    assert client.get("/api/v1/offers?include_stale=true").status_code == 200


def test_preferences_expose_threshold_and_reject_invalid_value(client):
    preferences = client.get("/api/v1/preferences")
    assert preferences.status_code == 200
    assert 0 <= preferences.json()["price_alert_threshold_percent"] <= 100
    invalid = client.put(
        "/api/v1/preferences",
        json={"price_alert_threshold_percent": 101},
    )
    assert invalid.status_code == 422
