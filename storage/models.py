"""
Hardware Crawler - Modelos do Banco de Dados

Define as tabelas para armazenar:
- Páginas coletadas
- Produtos detectados
- Histórico de preços
- URLs da frontier
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, 
    Boolean, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Page(Base):
    """
    Página web coletada.
    
    Armazena o conteúdo HTML e metadados de cada página visitada.
    Esta é a tabela principal para contagem de páginas coletadas.
    """
    __tablename__ = "pages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # === Identificação ===
    url = Column(String(2048), nullable=False, unique=True, index=True)
    url_hash = Column(String(64), nullable=False, unique=True, index=True)
    
    # === Metadados HTTP ===
    domain = Column(String(255), nullable=False, index=True)
    status_code = Column(Integer)
    content_type = Column(String(128))
    content_length = Column(Integer)
    
    # === Conteúdo ===
    title = Column(String(512))
    html_content = Column(Text)  # HTML completo
    text_content = Column(Text)  # Texto extraído (para indexação futura)
    
    # === Crawl info ===
    depth = Column(Integer, default=0)
    crawled_at = Column(DateTime, default=datetime.utcnow, index=True)
    crawl_time_ms = Column(Integer)  # Tempo de download
    
    # === Classificação ===
    is_product_page = Column(Boolean, default=False, index=True)
    category = Column(String(64))
    
    # === Relacionamentos ===
    product = relationship("Product", back_populates="page", uselist=False)
    links_found = relationship("Link", back_populates="source_page")
    
    __table_args__ = (
        Index("idx_pages_domain_crawled", "domain", "crawled_at"),
    )
    
    def __repr__(self):
        return f"<Page(id={self.id}, url={self.url[:50]}...)>"


class Product(Base):
    """
    Produto detectado em uma página.
    
    Quando uma página é identificada como página de produto,
    os dados são extraídos e armazenados aqui.
    """
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    page_id = Column(Integer, ForeignKey("pages.id"), nullable=False, unique=True)
    
    # === Identificação ===
    name = Column(String(512), nullable=False)
    sku = Column(String(128), index=True)
    brand = Column(String(128))
    
    # === Preço atual ===
    price = Column(Float)
    price_raw = Column(String(64))  # Texto original do preço
    currency = Column(String(8), default="BRL")
    
    # === Categorização ===
    category = Column(String(64), index=True)
    store = Column(String(64), nullable=False, index=True)
    
    # === Timestamps ===
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # === Relacionamentos ===
    page = relationship("Page", back_populates="product")
    price_history = relationship("PriceHistory", back_populates="product", order_by="PriceHistory.recorded_at")
    
    __table_args__ = (
        Index("idx_products_store_category", "store", "category"),
    )
    
    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name[:30]}..., price={self.price})>"


class PriceHistory(Base):
    """
    Histórico de preços de produtos.
    
    Registra as variações de preço ao longo do tempo.
    """
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    product = relationship("Product", back_populates="price_history")
    
    def __repr__(self):
        return f"<PriceHistory(product_id={self.product_id}, price={self.price}, at={self.recorded_at})>"


class Link(Base):
    """
    Links encontrados nas páginas.
    
    Usado para construir o grafo de links e rastrear
    a descoberta de novas URLs.
    """
    __tablename__ = "links"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    source_page_id = Column(Integer, ForeignKey("pages.id"), nullable=False, index=True)
    target_url = Column(String(2048), nullable=False)
    target_url_hash = Column(String(64), nullable=False, index=True)
    
    anchor_text = Column(String(512))
    discovered_at = Column(DateTime, default=datetime.utcnow)
    
    source_page = relationship("Page", back_populates="links_found")
    
    __table_args__ = (
        Index("idx_links_source_target", "source_page_id", "target_url_hash"),
    )


class Frontier(Base):
    """
    URL Frontier - fila de URLs a serem visitadas.
    
    Implementa a fila de prioridade para o crawler.
    """
    __tablename__ = "frontier"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    url = Column(String(2048), nullable=False)
    url_hash = Column(String(64), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=False, index=True)
    
    # === Prioridade ===
    priority = Column(Integer, default=0, index=True)  # Maior = mais prioritário
    depth = Column(Integer, default=0)
    
    # === Status ===
    status = Column(String(16), default="pending", index=True)  # pending, processing, done, failed
    retries = Column(Integer, default=0)
    
    # === Timestamps ===
    added_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    
    __table_args__ = (
        Index("idx_frontier_priority_status", "priority", "status"),
        Index("idx_frontier_domain_status", "domain", "status"),
    )
    
    def __repr__(self):
        return f"<Frontier(url={self.url[:50]}..., priority={self.priority}, status={self.status})>"


class CrawlStats(Base):
    """
    Estatísticas de crawl.
    
    Armazena métricas agregadas para monitoramento.
    """
    __tablename__ = "crawl_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # === Contadores ===
    pages_crawled = Column(Integer, default=0)
    pages_failed = Column(Integer, default=0)
    products_found = Column(Integer, default=0)
    links_discovered = Column(Integer, default=0)
    
    # === Por domínio ===
    domain = Column(String(255))
    domain_pages = Column(Integer, default=0)
    
    # === Performance ===
    avg_response_time_ms = Column(Float)
    pages_per_minute = Column(Float)
    
    def __repr__(self):
        return f"<CrawlStats(pages={self.pages_crawled}, products={self.products_found})>"
