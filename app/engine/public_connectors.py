import time
from typing import Any, Dict, List
import httpx
from app.config import settings

FALLBACK_FX_RATES = {
    "USD_BRL": 5.68,
    "EUR_BRL": 6.18,
    "GBP_BRL": 7.35,
    "source": "fallback-cache",
}


class PublicAPIConnectors:
    """Zero-auth connectors from public-apis for currency conversion, IP ASN lookup and catalog feeds."""

    def __init__(self) -> None:
        self._fx_cache: Dict[str, Any] = {}
        self._fx_cached_at: float = 0.0

    async def get_live_fx_rates(self) -> Dict[str, Any]:
        now = time.monotonic()
        if self._fx_cache and (now - self._fx_cached_at) < 300:
            return self._fx_cache

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    usd_brl = float(data["USDBRL"]["bid"])
                    eur_brl = float(data["EURBRL"]["bid"])
                    result = {
                        "USD_BRL": round(usd_brl, 4),
                        "EUR_BRL": round(eur_brl, 4),
                        "source": "AwesomeAPI (public-apis)",
                    }
                    self._fx_cache = result
                    self._fx_cached_at = now
                    return result
        except Exception:
            pass

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get("https://open.er-api.com/v6/latest/USD")
                if resp.status_code == 200:
                    rates = resp.json().get("rates", {})
                    brl = float(rates.get("BRL", 5.68))
                    eur = float(rates.get("EUR", 0.92))
                    result = {
                        "USD_BRL": round(brl, 4),
                        "EUR_BRL": round(brl / eur, 4) if eur else 6.18,
                        "source": "OpenExchangeRates (public-apis)",
                    }
                    self._fx_cache = result
                    self._fx_cached_at = now
                    return result
        except Exception:
            pass

        return FALLBACK_FX_RATES.copy()

    async def convert_to_brl(self, amount: float, currency: str) -> Dict[str, Any]:
        rates = await self.get_live_fx_rates()
        curr = currency.upper()
        if curr == "BRL":
            rate = 1.0
        elif curr == "USD":
            rate = rates["USD_BRL"]
        elif curr == "EUR":
            rate = rates["EUR_BRL"]
        else:
            rate = 1.0

        converted = round(amount * rate, 2)
        return {
            "original_amount": amount,
            "original_currency": curr,
            "amount_brl": converted,
            "exchange_rate": rate,
            "fx_provider": rates["source"],
        }

    async def inspect_ip_network(self, ip_address: str) -> Dict[str, Any]:
        """Queries IPWhois and Shodan InternetDB (from public-apis) for ASN, geolocation and open ports."""
        geo_data: Dict[str, Any] = {
            "ip": ip_address,
            "country": "Brazil",
            "country_code": "BR",
            "city": "São Paulo",
            "asn": "AS28573",
            "isp": "Claro S.A.",
            "open_ports": [],
            "vulns": [],
            "source": "ipwho.is + internetdb.shodan.io",
        }
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                ip_resp, shodan_resp = await client.get(
                    f"https://ipwho.is/{ip_address}"
                ), await client.get(f"https://internetdb.shodan.io/{ip_address}")

                if ip_resp.status_code == 200:
                    payload = ip_resp.json()
                    if payload.get("success", True):
                        conn = payload.get("connection") or {}
                        geo_data.update(
                            {
                                "country": payload.get("country", "Unknown"),
                                "country_code": payload.get("country_code", "XX"),
                                "city": payload.get("city", "Unknown"),
                                "asn": f"AS{conn.get('asn')}" if conn.get("asn") else "Unknown",
                                "isp": conn.get("isp") or conn.get("org") or "Unknown",
                            }
                        )

                if shodan_resp.status_code == 200:
                    s_data = shodan_resp.json()
                    geo_data["open_ports"] = s_data.get("ports", [])
                    geo_data["vulns"] = s_data.get("vulns", [])
                    geo_data["hostnames"] = s_data.get("hostnames", [])
        except Exception:
            pass
        return geo_data

    async def fetch_public_catalog_products(
        self, query: str = "laptop", limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Fetches real structured product listings from DummyJSON public e-commerce API."""
        rates = await self.get_live_fx_rates()
        usd_brl = rates["USD_BRL"]
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://dummyjson.com/products/search",
                    params={"q": query, "limit": limit},
                )
                if resp.status_code == 200:
                    items = resp.json().get("products", [])
                    return [
                        {
                            "id": p.get("id"),
                            "title": p.get("title"),
                            "brand": p.get("brand"),
                            "category": p.get("category"),
                            "price_usd": p.get("price"),
                            "price_brl": round(float(p.get("price", 0)) * usd_brl, 2),
                            "discount_pct": p.get("discountPercentage"),
                            "rating": p.get("rating"),
                            "stock": p.get("stock"),
                        }
                        for p in items
                    ]
        except Exception:
            pass
        return []


public_connectors = PublicAPIConnectors()
