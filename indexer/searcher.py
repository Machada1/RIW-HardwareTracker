"""
Hardware Crawler — Motor de Busca BM25 (Fase 2: Representação)

Implementa busca sobre o índice invertido usando o algoritmo BM25
(Best Match 25), o padrão de facto para IR moderna.

Fórmula BM25:
    score(q,d) = Σ_t IDF(t) × (tf(t,d) × (k1+1)) / (tf(t,d) + k1×(1 - b + b×dl/avgdl))

Hiperparâmetros padrão (Robertson et al.):
    k1 = 1.5   — saturação de frequência de termo
    b  = 0.75  — normalização por comprimento de documento
"""

import json
import math
from pathlib import Path
from typing import Optional

from indexer.text_processor import TextProcessor


class Searcher:
    """
    Motor de busca BM25 sobre o índice invertido em disco.

    Uso:
        s = Searcher(index_dir=Path("data/index"))
        results = s.search("placa de video rtx 4070", top_k=10)
        for r in results:
            print(r["score"], r["title"], r["url"])
    """

    BM25_K1 = 1.5
    BM25_B = 0.75

    def __init__(
        self,
        index_dir: Path,
        text_processor: Optional[TextProcessor] = None,
    ):
        self.index_dir = index_dir
        self.tp = text_processor or TextProcessor()

        # Carrega metadados (pequenos, ficam em memória)
        self._meta = self._load_json("meta.json")
        self._vocab: dict[str, dict] = self._load_json("vocab.json")
        self._docs: dict[str, dict] = self._load_json("docs.json")

        # Cache de shards de postings já carregados
        self._postings_cache: dict[int, dict] = {}

    # ------------------------------------------------------------------
    # Busca principal
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        domain_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Executa busca BM25 e retorna até top_k resultados.

        Args:
            query: string de busca em linguagem natural
            top_k: quantidade máxima de resultados
            domain_filter: se fornecido, restringe a um domínio (ex: "kabum.com.br")

        Returns:
            Lista de dicts: {rank, score, doc_id, url, title, domain, is_product, category}
        """
        if not self._meta:
            raise RuntimeError("Índice não encontrado. Execute: python main.py index build")

        query_terms = self.tp.process_query(query)
        if not query_terms:
            return []

        total_docs = self._meta["total_docs"]
        avg_dl = self._meta["avg_dl"]

        # Acumula scores BM25 por documento
        scores: dict[str, float] = {}

        for term in set(query_terms):  # deduplica termos da query
            if term not in self._vocab:
                continue

            term_info = self._vocab[term]
            term_id = term_info["id"]
            df = term_info["df"]

            # IDF (suavizado para evitar log negativo)
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)

            # Postings: [(doc_id, tf), ...]
            postings = self._get_postings(term_id)
            if not postings:
                continue

            for doc_id_raw, tf in postings:
                doc_id = str(doc_id_raw)
                doc = self._docs.get(doc_id)
                if not doc:
                    continue

                # Filtro por domínio
                if domain_filter and domain_filter not in doc.get("domain", ""):
                    continue

                dl = doc.get("dl", avg_dl)
                norm = tf * (self.BM25_K1 + 1) / (
                    tf + self.BM25_K1 * (1 - self.BM25_B + self.BM25_B * dl / avg_dl)
                )
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * norm

        # Ordena por score desc, pega top_k
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]

        results = []
        for rank, (doc_id, score) in enumerate(ranked, 1):
            doc = self._docs.get(doc_id, {})
            results.append({
                "rank": rank,
                "score": round(score, 4),
                "doc_id": int(doc_id),
                "url": doc.get("url", ""),
                "title": doc.get("title", ""),
                "domain": doc.get("domain", ""),
                "is_product": doc.get("is_product", False),
                "category": doc.get("category"),
            })

        return results

    # ------------------------------------------------------------------
    # Estatísticas do índice
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Retorna estatísticas detalhadas do índice."""
        if not self._meta:
            return {}

        # Top termos por DF
        top_terms = sorted(
            self._vocab.items(),
            key=lambda kv: -kv[1]["df"],
        )[:50]

        # Distribuição de DF
        df_values = [v["df"] for v in self._vocab.values()]
        n = len(df_values)
        df_sorted = sorted(df_values)
        p50 = df_sorted[n // 2] if n else 0
        p90 = df_sorted[int(n * 0.9)] if n else 0
        p99 = df_sorted[int(n * 0.99)] if n else 0

        # Termos únicos (df == 1)
        hapax = sum(1 for v in df_values if v == 1)

        return {
            **self._meta,
            "top_terms": [(t, d["df"]) for t, d in top_terms],
            "df_p50": p50,
            "df_p90": p90,
            "df_p99": p99,
            "hapax_legomena": hapax,
            "hapax_pct": round(hapax / max(n, 1) * 100, 1),
        }

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _load_json(self, filename: str) -> dict:
        path = self.index_dir / filename
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _get_postings(self, term_id: int) -> list:
        """Carrega e cacheia o shard de postings para um term_id."""
        shard = term_id % 256
        if shard not in self._postings_cache:
            shard_file = self.index_dir / "postings" / f"{shard:02x}.json"
            if shard_file.exists():
                with open(shard_file, encoding="utf-8") as f:
                    self._postings_cache[shard] = json.load(f)
            else:
                self._postings_cache[shard] = {}
        return self._postings_cache[shard].get(str(term_id), [])

    def is_ready(self) -> bool:
        """Verifica se o índice existe e está pronto para uso."""
        return bool(self._meta) and bool(self._vocab) and bool(self._docs)
