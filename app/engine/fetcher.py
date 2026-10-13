import time
from typing import Any, Dict, Optional
import httpx
from app.config import settings
from app.engine.extractor import extract_page_payload
from app.engine.fingerprint import fingerprint_rotator
from app.engine.proxy_manager import proxy_pool
from app.engine.rate_limiter import rate_limiter

SYNTHETIC_DEMO_PAGES: Dict[str, str] = {
    "kabum.com.br/produto/rtx-4070-super-12gb": """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <title>Placa de Vídeo RTX 4070 Super 12GB GDDR6X | KaBuM!</title>
        <meta name="description" content="GeForce RTX 4070 Super 12GB GDDR6X 192-bit DLSS 3 Ray Tracing em promoção." />
        <meta property="og:title" content="Placa de Vídeo RTX 4070 Super 12GB GDDR6X" />
        <meta property="og:site_name" content="KaBuM!" />
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Placa de Vídeo RTX 4070 Super 12GB GDDR6X",
            "sku": "KB-4070S-12G",
            "offers": {
                "@type": "Offer",
                "priceCurrency": "BRL",
                "price": "3849.90",
                "availability": "https://schema.org/InStock"
            }
        }
        </script>
    </head>
    <body>
        <main>
            <h1>Placa de Vídeo RTX 4070 Super 12GB GDDR6X</h1>
            <p class="old-price">De: R$ 4.399,90</p>
            <p class="price-tag">Por: R$ 3.849,90 à vista no PIX (12% OFF)</p>
            <h2>Especificações Técnicas</h2>
            <ul>
                <li>Arquitetura: NVIDIA Ada Lovelace</li>
                <li>Memória de Vídeo: 12GB GDDR6X (21 Gbps)</li>
                <li>CUDA Cores: 7168 unidades</li>
                <li>Consumo (TGP): 220W</li>
            </ul>
            <a href="https://kabum.com.br/hardware/placas-de-video">Ver mais placas de vídeo</a>
            <a href="https://kabum.com.br/promocoes">Ofertas do Dia</a>
        </main>
    </body>
    </html>
    """,
    "dell.com/pt-br/shop/alienware-27-aw2724dm": """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <title>Monitor Gamer Alienware 27 AW2724DM | Dell Brasil</title>
        <meta name="description" content="Monitor QHD Fast IPS de 27 polegadas com taxa de atualização de 180Hz e G-SYNC." />
        <meta property="product:price:amount" content="2699.90" />
        <meta property="product:price:currency" content="BRL" />
    </head>
    <body>
        <main>
            <h1>Monitor Gamer Alienware 27 - AW2724DM</h1>
            <p>Preço Especial: R$ 2.699,90 em até 12x sem juros</p>
            <h2>Destaques do Produto</h2>
            <ul>
                <li>Resolução nativa QHD (2560 x 1440) até 180 Hz</li>
                <li>Painel Fast IPS com cobertura de 95% DCI-P3</li>
                <li>Certificação VESA DisplayHDR 600</li>
            </ul>
            <a href="https://dell.com/pt-br/shop/monitors">Monitores Dell</a>
        </main>
    </body>
    </html>
    """,
}


async def fetch_and_extract(
    url: str,
    selectors: Optional[Dict[str, str]] = None,
    use_stealth_headers: bool = True,
    raw_html_override: Optional[str] = None,
) -> Dict[str, Any]:
    domain = rate_limiter.extract_domain(url)
    await rate_limiter.acquire(domain)

    headers, fp_label = fingerprint_rotator.build_headers(
        randomize=use_stealth_headers
    )
    proxy_node = proxy_pool.select_proxy()
    proxy_label = (
        f"{proxy_node.id} ({proxy_node.endpoint})" if proxy_node else "direct-egress"
    )

    t0 = time.perf_counter()
    http_status = 200
    html_content = raw_html_override

    if html_content is None:
        for key, template_html in SYNTHETIC_DEMO_PAGES.items():
            if key in url:
                html_content = template_html
                break

    if html_content is None:
        async with httpx.AsyncClient(
            timeout=settings.REQUEST_TIMEOUT_SEC,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = await client.get(url)
            http_status = resp.status_code
            html_content = resp.text

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    if proxy_node:
        if 200 <= http_status < 400:
            proxy_node.record_success(max(elapsed_ms, 12.0))
        else:
            proxy_node.record_failure()

    payload = extract_page_payload(html_content, url=url, selectors=selectors)
    payload.update(
        {
            "domain": domain,
            "http_status": http_status,
            "fingerprint_used": fp_label,
            "proxy_used": proxy_label,
            "elapsed_ms": elapsed_ms,
        }
    )
    return payload
