import json
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup
from app.models.schemas import PriceDetectionResult

BRL_REGEX = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+(?:,\d{2}))")
USD_REGEX = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+(?:\.\d{2}))")
OUT_OF_STOCK_PATTERNS = re.compile(
    r"\b(esgotado|indispon[ií]vel|out of stock|sold out|sem estoque)\b",
    re.IGNORECASE,
)


def parse_number_string(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d,\.]", "", str(raw).strip())
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def format_currency(amount: float, currency: str = "BRL") -> str:
    if currency.upper() == "BRL":
        formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    return f"$ {amount:,.2f}"


def _extract_from_json_ld(soup: BeautifulSoup) -> Optional[PriceDetectionResult]:
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        raw_text = script.string or script.get_text()
        if not raw_text:
            continue
        try:
            data = json.loads(raw_text)
        except Exception:
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                candidates.extend(graph)
            item_type = str(item.get("@type", "")).lower()
            if "product" in item_type or "offers" in item:
                title = item.get("name")
                offers = item.get("offers")
                if isinstance(offers, list) and offers:
                    offers = offers[0]
                if isinstance(offers, dict):
                    raw_price = (
                        offers.get("price")
                        or offers.get("lowPrice")
                        or offers.get("highPrice")
                    )
                    amount = parse_number_string(str(raw_price)) if raw_price is not None else None
                    if amount:
                        currency = offers.get("priceCurrency", "BRL")
                        avail = str(offers.get("availability", "InStock")).lower()
                        in_stock = "outofstock" not in avail and "soldout" not in avail
                        return PriceDetectionResult(
                            detected=True,
                            currency=currency,
                            amount=round(amount, 2),
                            formatted=format_currency(amount, currency),
                            in_stock=in_stock,
                            source_method="json-ld",
                            product_title=title,
                        )
    return None


def _extract_from_meta(soup: BeautifulSoup) -> Optional[PriceDetectionResult]:
    price_meta = (
        soup.find("meta", property="product:price:amount")
        or soup.find("meta", property="og:price:amount")
        or soup.find(attrs={"itemprop": "price"})
    )
    if price_meta:
        content = price_meta.get("content") or price_meta.get_text()
        amount = parse_number_string(str(content))
        if amount:
            curr_meta = (
                soup.find("meta", property="product:price:currency")
                or soup.find("meta", property="og:price:currency")
                or soup.find(attrs={"itemprop": "priceCurrency"})
            )
            currency = (
                (curr_meta.get("content") or "BRL") if curr_meta else "BRL"
            )
            return PriceDetectionResult(
                detected=True,
                currency=currency,
                amount=round(amount, 2),
                formatted=format_currency(amount, currency),
                in_stock=True,
                source_method="meta-itemprop",
            )
    return None


def detect_price(
    html: str, custom_selector: Optional[str] = None
) -> PriceDetectionResult:
    if not html:
        return PriceDetectionResult(detected=False)

    soup = BeautifulSoup(html, "html.parser")
    page_title = soup.title.get_text(strip=True) if soup.title else None
    h1_tag = soup.find("h1")
    product_title = h1_tag.get_text(strip=True) if h1_tag else page_title

    body_text = soup.get_text(" ", strip=True)
    in_stock_heuristic = not bool(OUT_OF_STOCK_PATTERNS.search(body_text))

    if custom_selector:
        el = soup.select_one(custom_selector)
        if el:
            val = parse_number_string(el.get_text(" ", strip=True))
            if val:
                return PriceDetectionResult(
                    detected=True,
                    currency="BRL",
                    amount=round(val, 2),
                    formatted=format_currency(val, "BRL"),
                    in_stock=in_stock_heuristic,
                    source_method=f"selector:{custom_selector}",
                    product_title=product_title,
                )

    ld_res = _extract_from_json_ld(soup)
    if ld_res:
        if not ld_res.product_title:
            ld_res.product_title = product_title
        return ld_res

    meta_res = _extract_from_meta(soup)
    if meta_res:
        meta_res.product_title = product_title
        meta_res.in_stock = in_stock_heuristic
        return meta_res

    brl_matches = BRL_REGEX.findall(body_text)
    if brl_matches:
        parsed_vals = [
            v for v in (parse_number_string(m) for m in brl_matches) if v is not None
        ]
        if parsed_vals:
            primary = parsed_vals[0]
            orig = max(parsed_vals) if len(parsed_vals) > 1 and max(parsed_vals) > primary else None
            disc = (
                round(((orig - primary) / orig) * 100, 1)
                if orig and orig > primary
                else None
            )
            return PriceDetectionResult(
                detected=True,
                currency="BRL",
                amount=round(primary, 2),
                formatted=format_currency(primary, "BRL"),
                original_amount=round(orig, 2) if orig else None,
                discount_pct=disc,
                in_stock=in_stock_heuristic,
                source_method="regex-brl",
                product_title=product_title,
            )

    usd_matches = USD_REGEX.findall(body_text)
    if usd_matches:
        parsed_vals = [
            v for v in (parse_number_string(m) for m in usd_matches) if v is not None
        ]
        if parsed_vals:
            primary = parsed_vals[0]
            return PriceDetectionResult(
                detected=True,
                currency="USD",
                amount=round(primary, 2),
                formatted=format_currency(primary, "USD"),
                in_stock=in_stock_heuristic,
                source_method="regex-usd",
                product_title=product_title,
            )

    return PriceDetectionResult(
        detected=False, in_stock=in_stock_heuristic, product_title=product_title
    )
