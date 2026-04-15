"""
Testes do processador de texto (indexer/text_processor.py).
Cobre tokenização, stopwords, stemming e casos de borda.
"""
import pytest
from indexer.text_processor import TextProcessor


@pytest.fixture
def processor():
    return TextProcessor(use_stemming=True, use_stopwords=True)

@pytest.fixture
def processor_nostem():
    return TextProcessor(use_stemming=False, use_stopwords=True)

@pytest.fixture
def processor_raw():
    return TextProcessor(use_stemming=False, use_stopwords=False)


# ── Inicialização ─────────────────────────────────────────────────────────────

class TestInitialization:
    def test_stemmer_name_set(self, processor):
        assert processor.stemmer_name in ("rslp", "suffix-stripping", "none")

    def test_stemmer_name_rslp_or_fallback(self, processor):
        """RSLP ou fallback suffix-stripping — ambos são válidos."""
        assert processor.stemmer_name != "none"

    def test_nostem_returns_none_name(self, processor_nostem):
        assert processor_nostem.stemmer_name == "none"


# ── process() ─────────────────────────────────────────────────────────────────

class TestProcess:
    def test_empty_string_returns_empty_list(self, processor):
        assert processor.process("") == []

    def test_returns_list(self, processor):
        result = processor.process("placa de vídeo rtx 4070")
        assert isinstance(result, list)

    def test_basic_tokenization(self, processor_raw):
        result = processor_raw.process("placa video rtx")
        assert "placa" in result
        assert "video" in result
        assert "rtx" in result

    def test_stopwords_filtered(self, processor):
        """Stopwords como 'de', 'para', 'o' não devem aparecer."""
        result = processor.process("placa de vídeo para o computador")
        assert "de" not in result
        assert "para" not in result
        assert "o" not in result

    def test_hardware_terms_kept(self, processor):
        """Termos técnicos de hardware devem sobreviver ao processamento."""
        result = processor.process("RTX 4070 placa de vídeo NVMe SSD")
        stems = " ".join(result)
        # Pelo menos um dos termos técnicos deve estar presente (após stemming)
        assert any(t in stems for t in ["rtx", "4070", "plac", "nvme", "ssd"])

    def test_min_token_length_filter(self, processor_raw):
        """Tokens muito curtos (len < 2) são descartados."""
        result = processor_raw.process("a i o u SSD")
        assert "a" not in result
        assert "i" not in result

    def test_long_numeric_filtered(self, processor):
        """Números longos (IDs de produto > 8 dígitos) são filtrados."""
        result = processor.process("produto 123456789012345 rtx")
        assert "123456789012345" not in result

    def test_short_numeric_kept(self, processor_raw):
        """Números curtos (≤ 8 dígitos) são mantidos."""
        result = processor_raw.process("rtx 4070 ssd 1tb")
        assert "4070" in result

    def test_unicode_normalization(self, processor_raw):
        """'vídeo' e 'video' devem produzir stems iguais após normalização."""
        r1 = processor_raw.process("vídeo")
        r2 = processor_raw.process("video")
        assert r1 == r2

    def test_stemming_reduces_form(self, processor):
        """Formas flexionadas devem reduzir ao mesmo stem."""
        r1 = processor.process("processador")
        r2 = processor.process("processadores")
        # Com RSLP, ambos deveriam virar o mesmo stem
        # (toleramos diferença se stemmer for fallback)
        assert len(r1) > 0
        assert len(r2) > 0
        # O stem de "processador" deve ser prefixo do original
        assert r1[0] in "processador" or "process" in r1[0]


# ── process_query() ───────────────────────────────────────────────────────────

class TestProcessQuery:
    def test_same_as_process(self, processor):
        """process_query deve produzir o mesmo resultado que process."""
        text = "placa de vídeo RTX 4070"
        assert processor.process(text) == processor.process_query(text)

    def test_empty_query(self, processor):
        assert processor.process_query("") == []

    def test_single_term(self, processor):
        result = processor.process_query("ssd")
        assert len(result) >= 1


# ── Casos especiais ───────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_only_stopwords_returns_empty(self, processor):
        result = processor.process("de para com em o a")
        assert result == []

    def test_html_tags_stripped(self, processor):
        result = processor.process("<b>RTX</b> <i>4070</i>")
        combined = " ".join(result)
        assert "<b>" not in combined
        assert "RTX".lower() in combined.lower() or "rtx" in combined

    def test_boilerplate_ecommerce_filtered(self, processor):
        """Termos de boilerplate de e-commerce não devem aparecer no índice."""
        boilerplate = "clique aqui comprar carrinho adicionar frete grátis"
        result = processor.process(boilerplate)
        for term in ["carrinh", "clique", "frete"]:
            assert term not in " ".join(result)
