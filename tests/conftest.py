"""
Fixtures compartilhadas entre os módulos de teste.
"""
import pytest
import tempfile
import json
from pathlib import Path


# ── Diretório temporário por sessão ─────────────────────────────────────────

@pytest.fixture(scope="session")
def tmp_data(tmp_path_factory):
    """Diretório temporário reutilizado em toda a sessão de testes."""
    return tmp_path_factory.mktemp("crawler_tests")


# ── HTML mínimos para testes ─────────────────────────────────────────────────

PRODUCT_HTML_JSONLD = """
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "RTX 4070 Ti Super",
  "offers": {
    "@type": "Offer",
    "price": "4599.90",
    "priceCurrency": "BRL"
  }
}
</script>
<meta property="og:type" content="product">
</head>
<body><h1>RTX 4070 Ti Super</h1></body>
</html>
"""

LISTING_HTML = """
<html>
<head><title>Placas de Vídeo - KaBuM!</title></head>
<body><ul><li>RTX 4060</li><li>RX 7600</li></ul></body>
</html>
"""

PRODUCT_HTML_META = """
<html>
<head>
<meta property="og:type" content="product">
<meta property="product:price:amount" content="999.90">
</head>
<body>Processador Ryzen 5 5600X</body>
</html>
"""


@pytest.fixture
def product_html_jsonld():
    return PRODUCT_HTML_JSONLD

@pytest.fixture
def listing_html():
    return LISTING_HTML

@pytest.fixture
def product_html_meta():
    return PRODUCT_HTML_META
