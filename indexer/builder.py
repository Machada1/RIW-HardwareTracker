"""
Hardware Crawler — Construtor de Índice Invertido (Fase 2: Representação)

Constrói e persiste um índice invertido a partir dos textos coletados.
O índice é armazenado em arquivos JSON — sem banco de dados.

Estrutura em disco:
    data/index/
        meta.json       → metadados do índice (total_docs, avg_dl, ...)
        vocab.json      → vocabulário: {stem: {id, df, raw_term}}
        docs.json       → documentos: {doc_id: {url, title, domain, dl, ...}}
        postings/
            00.json     → postings para termos com term_id % 256 == 0
            ...
            ff.json     → postings para termos com term_id % 256 == 255

Formato das postings (por arquivo de shard):
    {
      "term_id": [[doc_id, tf], ...]   ← lista ordenada por doc_id
    }
"""

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from indexer.text_processor import TextProcessor


class IndexBuilder:
    """
    Constrói o índice invertido a partir do banco de dados de coleta.

    O builder lê o campo `text_content` de cada página na tabela `pages`
    do SQLite, processa o texto com TextProcessor, e salva o índice em
    `data/index/`.
    """

    SHARD_BITS = 8          # 256 shards (00..ff)
    BATCH_DB = 500          # páginas por batch de leitura do DB

    def __init__(
        self,
        index_dir: Path,
        text_processor: Optional[TextProcessor] = None,
    ):
        self.index_dir = index_dir
        self.tp = text_processor or TextProcessor()

        # Estruturas em memória durante a construção
        self._vocab: dict[str, dict] = {}     # stem → {id, df, raw_term}
        self._docs: dict[int, dict] = {}      # doc_id → {url, title, domain, dl, ...}
        self._postings: dict[int, list] = defaultdict(list)  # term_id → [(doc_id, tf)]
        self._next_term_id = 0
        self._total_dl = 0                    # soma de doc lengths (para avg_dl)

    def build_from_db(self, db_path: Path, progress_cb=None) -> dict:
        """
        Constrói o índice a partir do banco SQLite de coleta.

        Args:
            db_path: caminho para crawler.db
            progress_cb: callback(processed, total) para progress bar

        Returns:
            dict com estatísticas do índice construído
        """
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM pages WHERE text_content IS NOT NULL AND LENGTH(text_content) > 50")
        total = c.fetchone()[0]

        processed = 0
        offset = 0

        t0 = time.time()

        while True:
            c.execute(
                """
                SELECT id, url, title, domain, text_content, is_product_page, category
                FROM pages
                WHERE text_content IS NOT NULL AND LENGTH(text_content) > 50
                ORDER BY id
                LIMIT ? OFFSET ?
                """,
                (self.BATCH_DB, offset),
            )
            rows = c.fetchall()
            if not rows:
                break

            for row in rows:
                self._index_document(
                    doc_id=row["id"],
                    url=row["url"],
                    title=row["title"] or "",
                    domain=row["domain"],
                    text=row["text_content"],
                    is_product=bool(row["is_product_page"]),
                    category=row["category"],
                )
                processed += 1

            offset += self.BATCH_DB
            if progress_cb:
                progress_cb(processed, total)

        conn.close()

        build_time = time.time() - t0
        return self._save(build_time, total)

    def _index_document(
        self,
        doc_id: int,
        url: str,
        title: str,
        domain: str,
        text: str,
        is_product: bool,
        category: Optional[str],
    ):
        """Indexa um documento: tokeniza e acumula TF por termo."""
        # Título recebe peso 3× (boost para relevância)
        full_text = (title + " ") * 3 + text

        tokens = self.tp.process(full_text)
        if not tokens:
            return

        dl = len(tokens)
        self._total_dl += dl

        # Conta TF por termo neste documento
        tf_map: dict[str, int] = defaultdict(int)
        for token in tokens:
            tf_map[token] += 1

        # Registra documento
        self._docs[doc_id] = {
            "url": url,
            "title": title[:200],
            "domain": domain,
            "dl": dl,
            "is_product": is_product,
            "category": category,
        }

        # Atualiza vocabulário e postings
        for stem, tf in tf_map.items():
            if stem not in self._vocab:
                self._vocab[stem] = {
                    "id": self._next_term_id,
                    "df": 0,
                    "raw": stem,  # stem já normalizado
                }
                self._next_term_id += 1
            self._vocab[stem]["df"] += 1
            term_id = self._vocab[stem]["id"]
            self._postings[term_id].append((doc_id, tf))

    def _save(self, build_time: float, total_docs: int) -> dict:
        """Persiste o índice em disco e retorna estatísticas."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        postings_dir = self.index_dir / "postings"
        postings_dir.mkdir(exist_ok=True)

        avg_dl = self._total_dl / max(len(self._docs), 1)

        # --- meta.json ---
        meta = {
            "total_docs": len(self._docs),
            "total_terms": len(self._vocab),
            "total_postings": sum(len(v) for v in self._postings.values()),
            "avg_dl": round(avg_dl, 2),
            "build_time_s": round(build_time, 2),
            "stemmer": self.tp.stemmer_name,
            "use_stopwords": self.tp.use_stopwords,
        }
        _write_json(self.index_dir / "meta.json", meta)

        # --- docs.json ---
        _write_json(self.index_dir / "docs.json", self._docs)

        # --- vocab.json ---
        _write_json(self.index_dir / "vocab.json", self._vocab)

        # --- postings shardados ---
        # Agrupa por term_id % 256
        shards: dict[int, dict] = defaultdict(dict)
        for term_id, posting_list in self._postings.items():
            shard = term_id % (2 ** self.SHARD_BITS)
            shards[shard][str(term_id)] = posting_list

        for shard_id, shard_data in shards.items():
            shard_file = postings_dir / f"{shard_id:02x}.json"
            _write_json(shard_file, shard_data)

        # Shards vazios ficam ausentes — sem problema (searcher trata)

        return meta


def _write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
