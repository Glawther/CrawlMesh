from app.engine.extractor import extract_page_payload, html_to_clean_markdown

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Distributed Systems Guide</title>
    <meta name="description" content="Practical guide to resilient web crawlers." />
    <meta property="og:title" content="Distributed Systems Guide OG" />
    <script>console.log("tracking noise");</script>
    <style>body { color: red; }</style>
</head>
<body>
    <nav><a href="/home">Nav Ignore</a></nav>
    <main>
        <h1>High-Throughput Crawling Architecture</h1>
        <p>Token bucket rate limiting prevents target server saturation.</p>
        <h2>Core Components</h2>
        <ul>
            <li>Async HTTPX Worker Pool</li>
            <li>Circuit Breaker Proxy Mesh</li>
        </ul>
        <a href="/docs/architecture">Read Architecture Spec</a>
        <a href="https://example.org/external">External Reference</a>
    </main>
    <footer>Footer Copyright 2026</footer>
</body>
</html>
"""


def test_html_to_clean_markdown_strips_noise():
    md = html_to_clean_markdown(SAMPLE_HTML)
    assert "# High-Throughput Crawling Architecture" in md
    assert "## Core Components" in md
    assert "- Async HTTPX Worker Pool" in md
    assert "console.log" not in md
    assert "Footer Copyright" not in md


def test_extract_page_payload_metadata_and_selectors():
    payload = extract_page_payload(
        SAMPLE_HTML,
        url="https://crawlmesh.dev/guide",
        selectors={"main_heading": "h1", "items": "ul li"},
    )
    assert payload["title"] == "Distributed Systems Guide"
    assert payload["description"] == "Practical guide to resilient web crawlers."
    assert payload["extracted_data"]["opengraph"]["og:title"] == "Distributed Systems Guide OG"
    assert payload["extracted_data"]["custom_selectors"]["main_heading"] == "High-Throughput Crawling Architecture"
    assert len(payload["extracted_data"]["custom_selectors"]["items"]) == 2
    assert "https://crawlmesh.dev/docs/architecture" in payload["links"]
    assert "https://example.org/external" in payload["links"]
