import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProxyNode:
    id: str
    endpoint: str
    region: str = "br-saopaulo-1"
    protocol: str = "HTTP/S"
    latency_ms: float = 45.0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    failure_threshold: int = 3
    cooldown_seconds: float = 60.0

    @property
    def circuit_state(self) -> str:
        now = time.monotonic()
        if self.consecutive_failures >= self.failure_threshold:
            if now < self.cooldown_until:
                return "OPEN"
            return "HALF-OPEN"
        return "CLOSED"

    @property
    def healthy(self) -> bool:
        return self.circuit_state != "OPEN"

    def record_success(self, latency_ms: float) -> None:
        self.success_count += 1
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self.latency_ms = round((self.latency_ms * 0.7) + (latency_ms * 0.3), 1)

    def record_failure(self) -> None:
        self.failure_count += 1
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.cooldown_until = time.monotonic() + self.cooldown_seconds

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "endpoint": self.endpoint,
            "region": self.region,
            "protocol": self.protocol,
            "healthy": self.healthy,
            "latency_ms": round(self.latency_ms, 1),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "circuit_state": self.circuit_state,
        }


class ProxyPoolManager:
    """Manages proxy rotation with weighted latency selection and circuit breaking."""

    def __init__(self) -> None:
        self._nodes: Dict[str, ProxyNode] = {}
        self._rr_idx: int = 0
        self._seed_default_nodes()

    def _seed_default_nodes(self) -> None:
        defaults = [
            ProxyNode(
                id="node-br-sp01",
                endpoint="http://189.12.44.10:8080",
                region="br-saopaulo-1",
                protocol="HTTP/2",
                latency_ms=34.2,
                success_count=148,
                failure_count=2,
            ),
            ProxyNode(
                id="node-br-rj02",
                endpoint="http://200.18.91.204:3128",
                region="br-riodejaneiro-1",
                protocol="HTTP/S",
                latency_ms=48.7,
                success_count=96,
                failure_count=1,
            ),
            ProxyNode(
                id="node-us-va01",
                endpoint="http://45.33.18.91:3128",
                region="us-east-1",
                protocol="SOCKS5",
                latency_ms=112.5,
                success_count=84,
                failure_count=0,
            ),
            ProxyNode(
                id="node-eu-de01",
                endpoint="http://138.201.88.19:8080",
                region="eu-central-1",
                protocol="HTTP/S",
                latency_ms=164.0,
                success_count=52,
                failure_count=1,
            ),
        ]
        for node in defaults:
            self._nodes[node.id] = node

    def add_node(
        self,
        endpoint: str,
        region: str = "br-saopaulo-1",
        protocol: str = "HTTP/S",
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
    ) -> ProxyNode:
        node_id = f"node-{uuid.uuid4().hex[:6]}"
        node = ProxyNode(
            id=node_id,
            endpoint=endpoint,
            region=region,
            protocol=protocol,
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )
        self._nodes[node_id] = node
        return node

    def remove_node(self, node_id: str) -> bool:
        return self._nodes.pop(node_id, None) is not None

    def select_proxy(self) -> Optional[ProxyNode]:
        healthy_nodes = [n for n in self._nodes.values() if n.healthy]
        if not healthy_nodes:
            return None
        healthy_nodes.sort(key=lambda n: n.latency_ms)
        selected = healthy_nodes[self._rr_idx % len(healthy_nodes)]
        self._rr_idx += 1
        return selected

    def list_nodes(self) -> List[Dict]:
        return [n.to_dict() for n in self._nodes.values()]

    def healthy_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.healthy)


proxy_pool = ProxyPoolManager()
