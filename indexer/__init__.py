"""
Módulo de indexação para Recuperação de Informação.

Pipeline: texto bruto → tokenização → stopwords → stemming → índice invertido BM25
"""
from indexer.text_processor import TextProcessor
from indexer.builder import IndexBuilder
from indexer.searcher import Searcher

__all__ = ["TextProcessor", "IndexBuilder", "Searcher"]
