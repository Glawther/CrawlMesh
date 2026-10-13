from app.engine.price_parser import detect_price, parse_number_string


def test_parse_number_string_formats():
    assert parse_number_string("R$ 3.849,90") == 3849.90
    assert parse_number_string("1,499.50") == 1499.50
    assert parse_number_string("89,90") == 89.90
    assert parse_number_string("invalid") is None


def test_detect_price_from_json_ld():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Processador Ryzen 7 7800X3D",
            "offers": {
                "@type": "Offer",
                "priceCurrency": "BRL",
                "price": "2799.90",
                "availability": "https://schema.org/InStock"
            }
        }
        </script>
    </head>
    <body><h1>Processador Ryzen 7 7800X3D</h1></body>
    </html>
    """
    res = detect_price(html)
    assert res.detected is True
    assert res.amount == 2799.90
    assert res.currency == "BRL"
    assert res.in_stock is True
    assert res.source_method == "json-ld"


def test_detect_price_brl_regex_and_out_of_stock():
    html = """
    <html>
    <body>
        <h1>Placa Mãe B650M Aorus Elite</h1>
        <span class="price">R$ 1.299,00</span>
        <span class="old">R$ 1.599,00</span>
        <div>Produto indisponível no momento</div>
    </body>
    </html>
    """
    res = detect_price(html)
    assert res.detected is True
    assert res.amount == 1299.00
    assert res.original_amount == 1599.00
    assert res.in_stock is False
    assert res.source_method == "regex-brl"
