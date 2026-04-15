"""
Testes de configuração (config.py).
Verifica que as constantes e classes de configuração estão corretas.
"""
import pytest
from config import HARDWARE_CATEGORIES, STORES, CRAWLER_CONFIG, get_enabled_stores_dict


# ── HARDWARE_CATEGORIES ───────────────────────────────────────────────────────

class TestHardwareCategories:
    EXPECTED_CATEGORIES = {
        "gpu", "cpu", "ram", "ssd", "hdd",
        "motherboard", "psu", "cooler", "case",
        "monitor", "keyboard", "mouse", "headset",
    }

    def test_all_expected_categories_present(self):
        assert self.EXPECTED_CATEGORIES.issubset(set(HARDWARE_CATEGORIES.keys()))

    def test_each_category_has_keywords(self):
        for cat, keywords in HARDWARE_CATEGORIES.items():
            assert len(keywords) >= 1, f"Categoria '{cat}' sem keywords"

    def test_hdd_has_no_bare_hd_space(self):
        """Bug corrigido: 'hd ' com espaço casava 'Full HD'."""
        hdd_kws = HARDWARE_CATEGORIES.get("hdd", [])
        assert "hd " not in hdd_kws, "'hd ' (com espaço) ainda está em HARDWARE_CATEGORIES['hdd']"

    def test_hdd_has_specific_terms(self):
        hdd_kws = HARDWARE_CATEGORIES.get("hdd", [])
        specific = {"hd sata", "hd interno", "hd externo", "hdd"}
        found = set(hdd_kws) & specific
        assert found, f"Nenhum termo específico de HDD encontrado: {hdd_kws}"

    def test_gpu_contains_rtx(self):
        assert any("rtx" in k.lower() for k in HARDWARE_CATEGORIES.get("gpu", []))

    def test_cpu_contains_ryzen(self):
        assert any("ryzen" in k.lower() for k in HARDWARE_CATEGORIES.get("cpu", []))


# ── STORES ────────────────────────────────────────────────────────────────────

class TestStores:
    def test_three_enabled_stores(self):
        enabled = get_enabled_stores_dict()
        assert len(enabled) == 3, f"Esperado 3 lojas ativas, got {len(enabled)}: {list(enabled.keys())}"

    def test_enabled_stores_are_correct(self):
        enabled = get_enabled_stores_dict()
        domains = {cfg.domain for cfg in enabled.values()}
        assert "kabum.com.br" in domains
        assert "mercadolivre.com.br" in domains
        assert "amazon.com.br" in domains

    def test_magazineluiza_disabled(self):
        ml = STORES.get("magazineluiza")
        if ml:
            assert not ml.enabled, "Magazine Luiza deveria estar desabilitada"

    def test_each_store_has_seeds(self):
        for name, store in STORES.items():
            if store.enabled:
                assert len(store.seed_urls) > 0, f"Loja {name} sem seeds"

    def test_each_store_has_product_patterns(self):
        for name, store in STORES.items():
            if store.enabled:
                assert len(store.product_patterns) > 0, f"Loja {name} sem product_patterns"


# ── CRAWLERCONFIG ─────────────────────────────────────────────────────────────

class TestCrawlerConfig:
    def test_max_pages_reasonable(self):
        assert 1000 <= CRAWLER_CONFIG.max_pages <= 1_000_000

    def test_max_depth_reasonable(self):
        assert 5 <= CRAWLER_CONFIG.max_depth <= 50

    def test_delay_is_small(self):
        """Delay deve ser pequeno (< 5s) para não tornar o crawl lento."""
        assert 0 < CRAWLER_CONFIG.default_delay < 5.0

    def test_delay_is_not_2_seconds(self):
        """Bug documentado: delay era erroneamente mostrado como 2s no RELATORIO."""
        assert CRAWLER_CONFIG.default_delay < 1.0, (
            f"Delay = {CRAWLER_CONFIG.default_delay}s parece alto. "
            "Verifique se foi alterado acidentalmente."
        )

    def test_concurrency_positive(self):
        assert CRAWLER_CONFIG.max_concurrent_requests > 0

    def test_request_timeout_reasonable(self):
        assert 5 <= CRAWLER_CONFIG.request_timeout <= 120
