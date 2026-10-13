from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_crawl_endpoint_with_html_override():
    html = """
    <html>
    <head><title>Produto Teste</title></head>
    <body>
        <main>
            <h1>Notebook Gamer RTX</h1>
            <p class="price">R$ 5.499,90</p>
        </main>
    </body>
    </html>
    """
    resp = client.post(
        "/api/v1/crawl",
        json={
            "url": "https://loja-exemplo.com.br/notebook",
            "mode": "price",
            "raw_html_override": html,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["price_intel"]["detected"] is True
    assert data["price_intel"]["amount"] == 5499.90
    assert "# Notebook Gamer RTX" in data["markdown"]


def test_monitors_and_metrics_lifecycle():
    create_resp = client.post(
        "/api/v1/monitors",
        json={
            "name": "Teclado Mecânico Keychron K2",
            "url": "https://kabum.com.br/produto/rtx-4070-super-12gb",
            "store_name": "Keychron BR",
            "target_price": 4000.00,
            "current_price": 3849.90,
        },
    )
    assert create_resp.status_code == 200
    mon = create_resp.json()
    assert mon["alert_triggered"] is True

    metrics_resp = client.get("/api/v1/metrics")
    assert metrics_resp.status_code == 200
    m = metrics_resp.json()
    assert m["total_jobs"] >= 1
    assert m["active_monitors"] >= 1


def test_public_api_connectors():
    fx_resp = client.get("/api/v1/connectors/fx")
    assert fx_resp.status_code == 200
    fx = fx_resp.json()
    assert "USD_BRL" in fx
    assert fx["USD_BRL"] > 0

    ip_resp = client.get("/api/v1/connectors/ip/8.8.8.8")
    assert ip_resp.status_code == 200
    ip_data = ip_resp.json()
    assert ip_data["ip"] == "8.8.8.8"
    assert "country" in ip_data
