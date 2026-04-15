"""
Testes da frontier de URLs (crawler/frontier.py).
Cobre normalização, hash, extração de domínio, balanceamento de batch.
"""
import pytest
from collections import Counter
from crawler.frontier import normalize_url, hash_url, extract_domain, URLFrontier, is_allowed_url, get_store_for_url


# ── normalize_url ─────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_lowercase_scheme_and_host(self):
        url = "HTTPS://WWW.KABUM.COM.BR/Produto/123"
        n = normalize_url(url)
        assert n.startswith("https://www.kabum.com.br/")

    def test_removes_fragment(self):
        url = "https://kabum.com.br/produto/123#reviews"
        assert "#" not in normalize_url(url)

    def test_removes_utm_params(self):
        url = "https://kabum.com.br/p?id=1&utm_source=google&utm_campaign=bf"
        n = normalize_url(url)
        assert "utm_source" not in n
        assert "utm_campaign" not in n
        assert "id=1" in n

    def test_removes_fbclid(self):
        url = "https://kabum.com.br/p?x=1&fbclid=IwAR123"
        n = normalize_url(url)
        assert "fbclid" not in n

    def test_removes_amazon_ref_from_path(self):
        """Bug corrigido: Amazon usa /ref= no path, não como query param."""
        url = "https://www.amazon.com.br/produto-x/ref=psd_bb_logo/dp/B09XY"
        n = normalize_url(url)
        assert "/ref=" not in n
        assert "B09XY" in n

    def test_amazon_ref_makes_duplicates_equal(self):
        url1 = "https://www.amazon.com.br/produto-x/ref=psd_abc/dp/B09XY"
        url2 = "https://www.amazon.com.br/produto-x/dp/B09XY"
        assert normalize_url(url1) == normalize_url(url2)

    def test_sorts_query_params(self):
        url1 = "https://kabum.com.br/p?b=2&a=1"
        url2 = "https://kabum.com.br/p?a=1&b=2"
        assert normalize_url(url1) == normalize_url(url2)

    def test_empty_query_no_question_mark(self):
        url = "https://kabum.com.br/produto/123?utm_source=x"
        n = normalize_url(url)
        assert "?" not in n


# ── hash_url ─────────────────────────────────────────────────────────────────

class TestHashUrl:
    def test_returns_64_char_hex(self):
        h = hash_url("https://kabum.com.br/produto/123")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        url = "https://kabum.com.br/produto/123"
        assert hash_url(url) == hash_url(url)

    def test_different_urls_different_hashes(self):
        h1 = hash_url("https://kabum.com.br/produto/123")
        h2 = hash_url("https://kabum.com.br/produto/456")
        assert h1 != h2


# ── extract_domain ────────────────────────────────────────────────────────────

class TestExtractDomain:
    def test_kabum(self):
        assert extract_domain("https://www.kabum.com.br/produto/1") == "kabum.com.br"

    def test_mercadolivre(self):
        assert extract_domain("https://www.mercadolivre.com.br/p/1") == "mercadolivre.com.br"

    def test_amazon(self):
        assert extract_domain("https://www.amazon.com.br/dp/B09") == "amazon.com.br"

    def test_subdomain_stripped(self):
        """Subdomínio www ou lista não deve aparecer no resultado."""
        d = extract_domain("https://lista.mercadolivre.com.br/rtx-4070")
        assert d == "mercadolivre.com.br"


# ── URLFrontier ───────────────────────────────────────────────────────────────

class TestURLFrontierAdd:
    def setup_method(self):
        self.frontier = URLFrontier()

    def test_add_new_url_returns_true(self):
        assert self.frontier.add("https://kabum.com.br/produto/1") is True

    def test_add_duplicate_returns_false(self):
        url = "https://kabum.com.br/produto/2"
        self.frontier.add(url)
        assert self.frontier.add(url) is False

    def test_add_normalized_duplicate_returns_false(self):
        """URLs que normalizam para o mesmo valor não devem ser adicionadas duas vezes."""
        url1 = "https://www.amazon.com.br/produto/ref=abc/dp/B09"
        url2 = "https://www.amazon.com.br/produto/dp/B09"
        self.frontier.add(url1)
        assert self.frontier.add(url2) is False

    def test_add_increments_pending(self):
        size_before = len(self.frontier.pending)
        self.frontier.add("https://kabum.com.br/produto/99")
        assert len(self.frontier.pending) == size_before + 1

    def test_add_invalid_url_returns_false(self):
        assert self.frontier.add("nao-eh-uma-url") is False

    def test_add_javascript_url_returns_false(self):
        assert self.frontier.add("javascript:void(0)") is False


class TestURLFrontierPopBatch:
    def setup_method(self):
        self.frontier = URLFrontier()

    def _add_many(self, domain, count, path_prefix="item"):
        for i in range(count):
            self.frontier.add(f"https://www.{domain}/{path_prefix}{i}")

    def test_pop_returns_correct_size(self):
        self._add_many("kabum.com.br", 10)
        batch = self.frontier.pop_batch(5)
        assert len(batch) == 5

    def test_pop_removes_from_pending(self):
        self._add_many("kabum.com.br", 10)
        before = len(self.frontier.pending)
        self.frontier.pop_batch(5)
        assert len(self.frontier.pending) == before - 5

    def test_pop_empty_frontier(self):
        assert self.frontier.pop_batch(10) == []

    def test_domain_balance_equal_distribution(self):
        """Com 20 ML + 5 Kabum + 5 Amazon, batch de 15 deve ser 5 de cada."""
        self._add_many("mercadolivre.com.br", 20)
        self._add_many("kabum.com.br", 5)
        self._add_many("amazon.com.br", 5)

        batch = self.frontier.pop_batch(15)
        counts = Counter(item.domain for item in batch)

        assert counts["mercadolivre.com.br"] <= 7, (
            f"ML dominou o batch: {counts['mercadolivre.com.br']}/15 items"
        )
        assert counts["kabum.com.br"] >= 3
        assert counts["amazon.com.br"] >= 3

    def test_domain_balance_single_domain(self):
        """Com apenas 1 domínio, todo o batch vem dele."""
        self._add_many("kabum.com.br", 20)
        batch = self.frontier.pop_batch(10)
        assert all(item.domain == "kabum.com.br" for item in batch)

    def test_pop_respects_batch_limit_when_less_available(self):
        self._add_many("kabum.com.br", 3)
        batch = self.frontier.pop_batch(10)
        assert len(batch) == 3


# ── is_allowed_url / get_store_for_url ────────────────────────────────────────

class TestDomainFiltering:
    """
    Testa filtragem de domínios.

    Bug corrigido: get_store_for_url usava correspondência bidirecional de substring
    ("amazon.com" in "amazon.com.br" → True), permitindo que amazon.com (EUA)
    e mercadolivre.com (global) fossem coletados junto com as lojas BR alvo.
    """

    def test_amazon_br_allowed(self):
        assert is_allowed_url("https://www.amazon.com.br/s?k=ssd") is True

    def test_amazon_com_rejected(self):
        """amazon.com (EUA) não deve ser coletado."""
        assert is_allowed_url("https://www.amazon.com/dp/B09XY12345") is False

    def test_aboutamazon_br_rejected(self):
        """aboutamazon.com.br (blog corporativo) não é loja e deve ser rejeitado."""
        assert is_allowed_url("https://www.aboutamazon.com.br/noticias/x") is False

    def test_mercadolivre_br_allowed(self):
        assert is_allowed_url("https://www.mercadolivre.com.br/p/MLB123") is True

    def test_lista_mercadolivre_br_allowed(self):
        assert is_allowed_url("https://lista.mercadolivre.com.br/informatica") is True

    def test_mercadolivre_com_rejected(self):
        """mercadolivre.com (global) não deve ser coletado."""
        assert is_allowed_url("https://www.mercadolivre.com/p/MLB123") is False

    def test_kabum_allowed(self):
        assert is_allowed_url("https://www.kabum.com.br/hardware/ssd") is True

    def test_get_store_exact_match_amazon(self):
        store = get_store_for_url("https://www.amazon.com.br/s?k=gpu")
        assert store is not None
        assert "amazon" in store.domain

    def test_get_store_returns_none_for_amazon_us(self):
        assert get_store_for_url("https://www.amazon.com/dp/B09") is None

    def test_get_store_returns_none_for_unknown_domain(self):
        assert get_store_for_url("https://www.terabyteshop.com.br/produto/123") is None
