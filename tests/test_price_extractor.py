"""
Testes do extrator de preços (extractors/price_extractor.py).
Cobre cada estratégia de extração e casos de borda críticos.
"""
import pytest
from extractors.price_extractor import PriceExtractor


@pytest.fixture
def extractor():
    return PriceExtractor()


# ── _parse_price ──────────────────────────────────────────────────────────────

class TestParsePrice:
    def test_br_format_with_milhar(self, extractor):
        assert extractor._parse_price("1.234,56") == 1234.56

    def test_br_format_without_milhar(self, extractor):
        assert extractor._parse_price("1234,56") == 1234.56

    def test_br_format_large(self, extractor):
        assert extractor._parse_price("12.345,99") == 12345.99

    def test_en_format(self, extractor):
        assert extractor._parse_price("1234.56") == 1234.56

    def test_strips_r_prefix(self, extractor):
        assert extractor._parse_price("R$ 999,90") == 999.90

    def test_invalid_text_returns_none(self, extractor):
        assert extractor._parse_price("não é preço") is None

    def test_zero_returns_none(self, extractor):
        assert extractor._parse_price("0,00") is None

    def test_negative_returns_none(self, extractor):
        assert extractor._parse_price("-100,00") is None

    def test_too_large_returns_none(self, extractor):
        assert extractor._parse_price("2.000.000,00") is None


# ── _extract_from_text ────────────────────────────────────────────────────────

class TestExtractFromText:
    def test_basic_price_with_comma(self, extractor):
        price, raw = extractor._extract_from_text("R$ 999,90")
        assert price == 999.90

    def test_price_with_milhar_separator(self, extractor):
        price, raw = extractor._extract_from_text("R$ 1.234,56")
        assert price == 1234.56

    def test_price_without_milhar_no_decimal(self, extractor):
        price, raw = extractor._extract_from_text("R$ 1234,56")
        assert price == 1234.56

    def test_price_5_digits(self, extractor):
        price, raw = extractor._extract_from_text("R$ 12.345,99")
        assert price == 12345.99

    def test_rgba_false_positive_blocked(self, extractor):
        """Bug corrigido: rgba(65,137,230,.15) não deve gerar preço R$65,13."""
        price, raw = extractor._extract_from_text("background: rgba(65,137,230,.15)")
        assert price is None

    def test_rgba_with_valid_price_returns_price(self, extractor):
        price, raw = extractor._extract_from_text("rgba(65,137,230,.15) R$ 1.299,00")
        assert price == 1299.00

    def test_below_minimum_rejected(self, extractor):
        """Preços abaixo de R$50 são filtrados como falsos positivos."""
        price, _ = extractor._extract_from_text("R$ 49,90")
        assert price is None

    def test_at_minimum_accepted(self, extractor):
        price, _ = extractor._extract_from_text("R$ 50,00")
        assert price == 50.00

    def test_above_maximum_rejected(self, extractor):
        price, _ = extractor._extract_from_text("R$ 200.000,00")
        assert price is None

    def test_no_prefix_r_rejected(self, extractor):
        """Apenas valores com prefixo R$ são aceitos."""
        price, _ = extractor._extract_from_text("1234,56")
        assert price is None


# ── _extract_from_jsonld ──────────────────────────────────────────────────────

class TestExtractFromJsonLd:
    def _make_soup(self, html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_standard_product_schema(self, extractor):
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "SSD", "offers": {"price": "499.90"}}
        </script>
        """
        price, _ = extractor._extract_from_jsonld(self._make_soup(html))
        assert price == 499.90

    def test_nested_offers_list(self, extractor):
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "offers": [{"price": "1299,00"}]}
        </script>
        """
        price, _ = extractor._extract_from_jsonld(self._make_soup(html))
        assert price == 1299.00

    def test_malformed_json_returns_none(self, extractor):
        html = '<script type="application/ld+json">{invalid json</script>'
        price, _ = extractor._extract_from_jsonld(self._make_soup(html))
        assert price is None

    def test_no_jsonld_returns_none(self, extractor):
        html = "<html><body>sem schema</body></html>"
        price, _ = extractor._extract_from_jsonld(self._make_soup(html))
        assert price is None

    def test_jsonld_without_price_returns_none(self, extractor):
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "SSD sem preço"}
        </script>
        """
        price, _ = extractor._extract_from_jsonld(self._make_soup(html))
        assert price is None


# ── _extract_from_meta ────────────────────────────────────────────────────────

class TestExtractFromMeta:
    def _make_soup(self, html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_product_price_amount(self, extractor):
        html = '<meta property="product:price:amount" content="799.90">'
        price, _ = extractor._extract_from_meta(self._make_soup(html))
        assert price == 799.90

    def test_itemprop_price_content(self, extractor):
        html = '<span itemprop="price" content="1499.99">R$ 1.499,99</span>'
        price, _ = extractor._extract_from_meta(self._make_soup(html))
        assert price == 1499.99

    def test_no_meta_returns_none(self, extractor):
        html = "<html><body>sem meta</body></html>"
        price, _ = extractor._extract_from_meta(self._make_soup(html))
        assert price is None


# ── extract_price (integração) ────────────────────────────────────────────────

class TestExtractPriceIntegration:
    PRODUCT_HTML = """
    <html>
    <head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "RTX 4070", "offers": {"price": "3899.00"}}
    </script>
    </head>
    <body>RTX 4070 - R$ 3.899,00</body>
    </html>
    """

    META_HTML = """
    <html>
    <head>
    <meta property="product:price:amount" content="599.90">
    <meta property="og:type" content="product">
    </head>
    <body>SSD 1TB</body>
    </html>
    """

    def test_jsonld_takes_priority(self, extractor):
        price, _ = extractor.extract_price(self.PRODUCT_HTML, "https://kabum.com.br/produto/1")
        assert price == 3899.00

    def test_meta_fallback(self, extractor):
        price, _ = extractor.extract_price(self.META_HTML, "https://kabum.com.br/produto/2")
        assert price == 599.90

    def test_no_price_returns_none(self, extractor):
        html = "<html><body>página sem preço</body></html>"
        price, _ = extractor.extract_price(html, "https://kabum.com.br/produto/3")
        assert price is None
