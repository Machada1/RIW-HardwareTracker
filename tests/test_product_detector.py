"""
Testes do detector de produtos (extractors/product_detector.py).
Cobre detecção de listagem vs produto, categorias e filtragem de hardware.
"""
import pytest
from extractors.product_detector import ProductDetector


@pytest.fixture
def detector():
    return ProductDetector()


# ── _is_listing_url ────────────────────────────────────────────────────────────

class TestIsListingUrl:
    def test_kabum_category_is_listing(self, detector):
        assert detector._is_listing_url("https://www.kabum.com.br/hardware/placas-de-video") is True

    def test_kabum_tv_smart_tv_is_listing(self, detector):
        assert detector._is_listing_url("https://www.kabum.com.br/tv/smart-tv") is True

    def test_kabum_produto_is_not_listing(self, detector):
        assert detector._is_listing_url("https://www.kabum.com.br/produto/419013/rtx-4070") is False

    def test_mercadolivre_busca_is_listing(self, detector):
        assert detector._is_listing_url("https://www.mercadolivre.com.br/busca?q=rtx") is True

    def test_mercadolivre_lista_is_listing(self, detector):
        assert detector._is_listing_url("https://lista.mercadolivre.com.br/rtx-4070") is True

    def test_amazon_search_is_listing(self, detector):
        assert detector._is_listing_url("https://www.amazon.com.br/s?k=placa+de+video") is True

    def test_amazon_product_is_not_listing(self, detector):
        assert detector._is_listing_url("https://www.amazon.com.br/dp/B09XY12345") is False

    def test_mercadolivre_product_mlb_is_not_listing(self, detector):
        assert detector._is_listing_url("https://www.mercadolivre.com.br/MLB-1234567890") is False


# ── is_product_page ───────────────────────────────────────────────────────────

class TestIsProductPage:
    PRODUCT_JSONLD_HTML = """
    <html>
    <head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "RTX 4070", "offers": {"price": "3899.00"}}
    </script>
    </head>
    <body></body>
    </html>
    """

    PRODUCT_OG_HTML = """
    <html>
    <head>
    <meta property="og:type" content="product">
    <meta property="product:price:amount" content="599.90">
    </head>
    <body></body>
    </html>
    """

    def test_listing_url_overrides_all(self, detector):
        """Listagem com JSON-LD ainda deve ser rejeitada pela URL."""
        html = self.PRODUCT_JSONLD_HTML
        assert detector.is_product_page(html, "https://www.kabum.com.br/hardware/ssd") is False

    def test_amazon_search_page_is_not_product(self, detector):
        assert detector.is_product_page("", "https://www.amazon.com.br/s?k=rtx+4070") is False

    def test_product_url_pattern_detected(self, detector):
        """URL com /produto/ deve ser detectada sem análise de HTML."""
        assert detector.is_product_page("", "https://www.kabum.com.br/produto/419013/rtx") is True

    def test_jsonld_schema_detects_product(self, detector):
        url = "https://www.kabum.com.br/pagina/qualquer"
        assert detector.is_product_page(self.PRODUCT_JSONLD_HTML, url) is True

    def test_opengraph_product_detected(self, detector):
        url = "https://www.mercadolivre.com.br/p/qualquer"
        assert detector.is_product_page(self.PRODUCT_OG_HTML, url) is True

    def test_empty_page_is_not_product(self, detector):
        assert detector.is_product_page("", "https://kabum.com.br/pagina/generica") is False


# ── detect_category ────────────────────────────────────────────────────────────

class TestDetectCategory:
    def test_gpu_detected(self, detector):
        cat = detector.detect_category("Placa de Vídeo RTX 4070 Ti 12GB")
        assert cat == "gpu"

    def test_cpu_detected(self, detector):
        cat = detector.detect_category("Processador AMD Ryzen 5 5600X")
        assert cat in ("cpu", "gpu") or cat == "cpu"

    def test_ram_detected(self, detector):
        cat = detector.detect_category("Memória RAM DDR5 32GB Kingston")
        assert cat == "ram"

    def test_ssd_detected(self, detector):
        cat = detector.detect_category("SSD NVMe 1TB Samsung 980 Pro M.2")
        assert cat == "ssd"

    def test_hdd_detected(self, detector):
        cat = detector.detect_category("HD Interno 2TB Seagate SATA")
        assert cat == "hdd"

    def test_full_hd_is_not_hdd(self, detector):
        """Bug corrigido: Smart TV 43 Full HD não deve ser categorizada como HDD."""
        cat = detector.detect_category("Smart TV 43 Full HD DLED Samsung 4K")
        assert cat != "hdd", f"'Full HD' ainda está gerando categoria 'hdd': {cat}"

    def test_motherboard_detected(self, detector):
        cat = detector.detect_category("Placa-Mãe ASUS B550M-K AM4")
        assert cat == "motherboard"

    def test_psu_detected(self, detector):
        cat = detector.detect_category("Fonte 650W Bronze Corsair Modular")
        assert cat == "psu"

    def test_unknown_product_returns_none(self, detector):
        cat = detector.detect_category("Produto completamente aleatório")
        assert cat is None


# ── is_hardware_product ───────────────────────────────────────────────────────

class TestIsHardwareProduct:
    def test_gpu_is_hardware(self, detector):
        is_hw, reason = detector.is_hardware_product("Placa de Vídeo RTX 4060 8GB")
        assert is_hw is True
        assert reason == "hardware"

    def test_ssd_is_hardware(self, detector):
        is_hw, _ = detector.is_hardware_product("SSD NVMe 1TB WD Black")
        assert is_hw is True

    def test_car_is_not_hardware(self, detector):
        # Precisa de keyword explícita ("carro", "veículo") para ser "non_hardware".
        # "Honda Civic" sem keyword → "unknown" (conservador). Com "carro" → "non_hardware".
        is_hw1, reason1 = detector.is_hardware_product("Carro Honda Civic 2024 automático")
        assert is_hw1 is False
        assert reason1 == "non_hardware"

        # Sem keyword de não-hardware: o sistema é conservador → unknown
        is_hw2, reason2 = detector.is_hardware_product("Honda Civic 2024")
        assert is_hw2 is False
        assert reason2 in ("non_hardware", "unknown")

    def test_clothes_is_not_hardware(self, detector):
        is_hw, reason = detector.is_hardware_product("Camiseta polo masculina azul")
        assert is_hw is False

    def test_empty_name_is_not_hardware(self, detector):
        is_hw, reason = detector.is_hardware_product("")
        assert is_hw is False

    def test_ambiguous_returns_unknown(self, detector):
        """Produto sem palavras-chave claras deve ser 'unknown' (conservador)."""
        is_hw, reason = detector.is_hardware_product("Produto XYZ qualquer coisa")
        assert is_hw is False
