"""
Testes do índice invertido BM25 (indexer/builder.py + indexer/searcher.py).
Usa documentos sintéticos para testar a lógica sem depender do DB real.
"""
import pytest
import json
import math
import tempfile
from pathlib import Path
from indexer.text_processor import TextProcessor
from indexer.builder import IndexBuilder
from indexer.searcher import Searcher


# ── Fixture: índice sintético ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def index_dir(tmp_path_factory):
    """Constrói um mini-índice com documentos sintéticos."""
    tmp = tmp_path_factory.mktemp("index")

    tp = TextProcessor(use_stemming=True, use_stopwords=True)
    builder = IndexBuilder(index_dir=tmp, text_processor=tp)

    # Documentos sintéticos
    docs = [
        {
            "id": 1,
            "url": "https://kabum.com.br/produto/1",
            "title": "RTX 4070 Ti Placa de Vídeo 12GB",
            "domain": "kabum.com.br",
            "text_content": "RTX 4070 Ti placa de vídeo 12GB GDDR6x NVMe alta performance",
            "is_product_page": True,
            "category": "gpu",
        },
        {
            "id": 2,
            "url": "https://kabum.com.br/produto/2",
            "title": "RTX 4060 Placa de Vídeo 8GB",
            "domain": "kabum.com.br",
            "text_content": "RTX 4060 placa de vídeo 8GB GDDR6 mid-range jogos",
            "is_product_page": True,
            "category": "gpu",
        },
        {
            "id": 3,
            "url": "https://mercadolivre.com.br/produto/3",
            "title": "SSD NVMe 1TB Samsung 980 Pro",
            "domain": "mercadolivre.com.br",
            "text_content": "SSD NVMe 1TB Samsung 980 Pro M.2 PCIe leitura 7000 MB/s",
            "is_product_page": True,
            "category": "ssd",
        },
        {
            "id": 4,
            "url": "https://amazon.com.br/produto/4",
            "title": "Processador Ryzen 5 5600X",
            "domain": "amazon.com.br",
            "text_content": "Processador AMD Ryzen 5 5600X 6 cores 12 threads AM4 socket",
            "is_product_page": True,
            "category": "cpu",
        },
        {
            "id": 5,
            "url": "https://kabum.com.br/produto/5",
            "title": "Memória RAM DDR5 32GB Kingston",
            "domain": "kabum.com.br",
            "text_content": "Memória RAM DDR5 32GB 6000MHz Kingston Fury Beast",
            "is_product_page": True,
            "category": "ram",
        },
    ]

    # Injeta diretamente no builder para simular build_from_db
    builder._docs = {}
    builder._vocab = {}
    builder._postings = {}

    for doc in docs:
        doc_id = doc["id"]
        text = doc["title"] * 3 + " " + doc["text_content"]  # title boost 3x
        tokens = tp.process(text)
        dl = len(tokens)

        tf_map = {}
        for token in tokens:
            tf_map[token] = tf_map.get(token, 0) + 1

        builder._docs[str(doc_id)] = {
            "url": doc["url"],
            "title": doc["title"],
            "domain": doc["domain"],
            "dl": dl,
            "is_product": doc["is_product_page"],
            "category": doc["category"],
        }

        for term, tf in tf_map.items():
            if term not in builder._vocab:
                term_id = len(builder._vocab)
                builder._vocab[term] = {"id": term_id, "df": 0, "raw": term}
            builder._vocab[term]["df"] += 1
            term_id = builder._vocab[term]["id"]
            shard = term_id % 256
            if shard not in builder._postings:
                builder._postings[shard] = {}
            shard_data = builder._postings[shard]
            if term_id not in shard_data:
                shard_data[term_id] = []
            shard_data[term_id].append([doc_id, tf])

    # Calcula avg_dl
    total_dl = sum(d["dl"] for d in builder._docs.values())
    avg_dl = total_dl / len(builder._docs) if builder._docs else 0

    # Salva os arquivos
    (tmp / "postings").mkdir(exist_ok=True)
    meta = {
        "total_docs": len(docs),
        "total_terms": len(builder._vocab),
        "total_postings": sum(len(v) for v in builder._postings.values()),
        "avg_dl": avg_dl,
        "build_time_s": 0.1,
        "stemmer": tp.stemmer_name,
        "use_stopwords": True,
    }
    (tmp / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (tmp / "vocab.json").write_text(json.dumps(builder._vocab), encoding="utf-8")
    (tmp / "docs.json").write_text(json.dumps(builder._docs), encoding="utf-8")
    for shard_id, shard_data in builder._postings.items():
        shard_path = tmp / "postings" / f"{shard_id:02x}.json"
        shard_path.write_text(json.dumps(shard_data), encoding="utf-8")

    return tmp


@pytest.fixture(scope="module")
def searcher(index_dir):
    s = Searcher(index_dir=index_dir)
    assert s.is_ready()
    return s


# ── Searcher.is_ready ─────────────────────────────────────────────────────────

class TestSearcherIsReady:
    def test_ready_after_build(self, searcher):
        assert searcher.is_ready() is True

    def test_not_ready_without_index(self, tmp_path):
        s = Searcher(index_dir=tmp_path / "nonexistent")
        assert s.is_ready() is False


# ── Searcher.stats ────────────────────────────────────────────────────────────

class TestSearcherStats:
    def test_returns_dict(self, searcher):
        assert isinstance(searcher.stats(), dict)

    def test_has_required_keys(self, searcher):
        s = searcher.stats()
        for key in ("total_docs", "total_terms", "avg_dl", "top_terms", "hapax_legomena"):
            assert key in s, f"Chave ausente nas stats: '{key}'"

    def test_total_docs_correct(self, searcher):
        assert searcher.stats()["total_docs"] == 5

    def test_top_terms_is_list(self, searcher):
        top = searcher.stats()["top_terms"]
        assert isinstance(top, list)
        assert len(top) > 0

    def test_hapax_is_non_negative(self, searcher):
        assert searcher.stats()["hapax_legomena"] >= 0


# ── Searcher.search ───────────────────────────────────────────────────────────

class TestSearcherSearch:
    def test_returns_list(self, searcher):
        results = searcher.search("rtx placa video")
        assert isinstance(results, list)

    def test_empty_query_returns_empty(self, searcher):
        assert searcher.search("") == []

    def test_unknown_query_returns_empty(self, searcher):
        assert searcher.search("xyzzy abracadabra foobarbaz") == []

    def test_gpu_query_returns_gpu_docs(self, searcher):
        results = searcher.search("rtx placa video")
        assert len(results) > 0
        # Os documentos mais relevantes devem ser GPUs
        top_domains = [r["domain"] for r in results[:2]]
        assert "kabum.com.br" in top_domains

    def test_ssd_query_returns_ssd_doc(self, searcher):
        results = searcher.search("ssd nvme samsung")
        assert len(results) > 0
        top = results[0]
        assert "ssd" in top["title"].lower() or top["category"] == "ssd"

    def test_results_have_required_fields(self, searcher):
        results = searcher.search("processador ryzen")
        assert len(results) > 0
        r = results[0]
        for field in ("rank", "score", "url", "title", "domain", "is_product"):
            assert field in r, f"Campo '{field}' ausente no resultado de busca"

    def test_results_ranked_by_score(self, searcher):
        results = searcher.search("rtx placa video")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), "Resultados não estão ordenados por score"

    def test_top_k_respected(self, searcher):
        results = searcher.search("rtx placa video ssd processador", top_k=2)
        assert len(results) <= 2

    def test_domain_filter(self, searcher):
        results = searcher.search("placa video rtx ssd", domain_filter="kabum.com.br")
        assert all("kabum.com.br" in r["domain"] for r in results)

    def test_domain_filter_excludes_other_domains(self, searcher):
        results = searcher.search("rtx ssd processador", domain_filter="amazon.com.br")
        for r in results:
            assert "amazon.com.br" in r["domain"]

    def test_bm25_more_relevant_scores_higher(self, searcher):
        """Doc sobre RTX deve pontuar mais que doc sobre SSD em busca por 'rtx'."""
        results = searcher.search("rtx 4070 placa video")
        if len(results) >= 2:
            # O primeiro resultado deve ter score maior
            assert results[0]["score"] >= results[1]["score"]
            # O primeiro deve ser sobre GPU, não SSD
            assert results[0].get("category") == "gpu" or "rtx" in results[0]["title"].lower()

    def test_rank_starts_at_1(self, searcher):
        results = searcher.search("rtx")
        if results:
            assert results[0]["rank"] == 1

    def test_score_is_positive(self, searcher):
        results = searcher.search("rtx")
        for r in results:
            assert r["score"] > 0
