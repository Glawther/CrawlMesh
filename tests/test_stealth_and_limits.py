from app.engine.fingerprint import FingerprintRotator
from app.engine.proxy_manager import ProxyPoolManager
from app.engine.rate_limiter import DomainRateLimiter


def test_fingerprint_rotator_coherence():
    rotator = FingerprintRotator()
    headers, label = rotator.build_headers(randomize=False)
    assert "User-Agent" in headers
    assert "Accept-Language" in headers
    assert len(label) > 5


def test_proxy_circuit_breaker_trips_on_failures():
    pool = ProxyPoolManager()
    node = pool.add_node(
        endpoint="http://10.99.0.1:8080",
        region="br-test-1",
        failure_threshold=3,
        cooldown_seconds=120.0,
    )
    assert node.circuit_state == "CLOSED"
    assert node.healthy is True

    node.record_failure()
    node.record_failure()
    assert node.circuit_state == "CLOSED"

    node.record_failure()
    assert node.circuit_state == "OPEN"
    assert node.healthy is False

    node.record_success(latency_ms=25.0)
    assert node.circuit_state == "CLOSED"
    assert node.healthy is True


def test_domain_rate_limiter_token_bucket():
    limiter = DomainRateLimiter(default_rps=1.0, burst=2.0)
    domain = "https://www.kabum.com.br/produto/123"
    assert limiter.try_acquire(domain) is True
    assert limiter.try_acquire(domain) is True
    # 3rd immediate burst call should be throttled
    assert limiter.try_acquire(domain) is False
