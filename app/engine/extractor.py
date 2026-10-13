import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
from app.engine.price_parser import detect_price

NOISE_TAGS = [
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "canvas",
    "form",
    "footer",
    "nav",
]


def html_to_clean_markdown(html: str, base_url: str = "") -> str:
    """Transforms noisy HTML DOM into structured, readable Markdown."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.find("body") or soup
    lines: List[str] = []

    for element in root.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre"]
    ):
        if not isinstance(element, Tag):
            continue
        text = element.get_text(" ", strip=True)
        if not text:
            continue

        name = element.name.lower()
        if name == "h1":
            lines.append(f"# {text}\n")
        elif name == "h2":
            lines.append(f"## {text}\n")
        elif name == "h3":
            lines.append(f"### {text}\n")
        elif name == "h4":
            lines.append(f"#### {text}\n")
        elif name == "li":
            lines.append(f"- {text}")
        elif name == "blockquote":
            lines.append(f"> {text}\n")
        elif name == "pre":
            lines.append(f"```\n{text}\n```\n")
        elif name == "p":
            lines.append(f"{text}\n")

    if not lines:
        fallback = root.get_text("\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", fallback).strip()

    output = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", output).strip()


def extract_page_payload(
    html: str,
    url: str,
    selectors: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    desc_meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = (
        desc_meta.get("content", "").strip()
        if desc_meta and desc_meta.get("content")
        else None
    )

    og_tags: Dict[str, str] = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "")
        if prop.startswith("og:") and meta.get("content"):
            og_tags[prop] = meta.get("content", "").strip()

    headings = [
        h.get_text(" ", strip=True)
        for h in soup.find_all(["h1", "h2", "h3"])
        if h.get_text(strip=True)
    ][:15]

    links: List[str] = []
    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        full_url = urljoin(url, href)
        if full_url not in seen_links:
            seen_links.add(full_url)
            links.append(full_url)
            if len(links) >= 50:
                break

    custom_extracted: Dict[str, Any] = {}
    if selectors:
        for field_name, css_sel in selectors.items():
            try:
                matches = soup.select(css_sel)
                if not matches:
                    custom_extracted[field_name] = None
                elif len(matches) == 1:
                    custom_extracted[field_name] = matches[0].get_text(" ", strip=True)
                else:
                    custom_extracted[field_name] = [
                        m.get_text(" ", strip=True) for m in matches[:20]
                    ]
            except Exception as exc:
                custom_extracted[field_name] = f"SelectorError: {exc}"

    price_selector = selectors.get("price") if selectors else None
    price_intel = detect_price(html, custom_selector=price_selector)

    markdown = html_to_clean_markdown(html, base_url=url)

    extracted_data: Dict[str, Any] = {
        "headings": headings,
        "opengraph": og_tags,
    }
    if custom_extracted:
        extracted_data["custom_selectors"] = custom_extracted

    return {
        "title": title,
        "description": description,
        "markdown": markdown,
        "extracted_data": extracted_data,
        "price_intel": price_intel.model_dump(),
        "links": links,
    }
