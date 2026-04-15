"""
Hardware Crawler - Gerenciamento do Banco de Dados

Funções para inicializar e interagir com o banco SQLite.
"""

import asyncio
import random
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Optional, AsyncGenerator, TypeVar, Callable

from sqlalchemy import create_engine, func, select, update, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from storage.models import Base, Page, Product, PriceHistory, Link, Frontier, CrawlStats
from config import DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)

# Decorator para retry com backoff exponencial
T = TypeVar('T')

def with_retry(
    max_retries: int = 5,
    base_delay: float = 0.1,
    max_delay: float = 5.0,
    exceptions: tuple = (OperationalError,)
):
    """Decorator que adiciona retry com backoff exponencial."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if "database is locked" in str(e):
                        # Backoff exponencial com jitter
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
                        logger.warning(f"DB locked, retry {attempt+1}/{max_retries} em {delay:.2f}s")
                        await asyncio.sleep(delay)
                    else:
                        raise
            raise last_exception
        return wrapper
    return decorator


class Database:
    """
    Gerenciador de banco de dados assíncrono.
    
    Encapsula todas as operações de persistência.
    Usa WAL mode + busy_timeout para concorrência.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._engine = None
        self._session_factory = None
    
    async def initialize(self):
        """Inicializa o banco de dados e cria as tabelas."""
        # Garante que o diretório existe
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Cria engine assíncrona com configurações para alta concorrência
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        self._engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            # Pool de conexões otimizado para concorrência
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=3600,
            # SQLite específico: timeout para locks
            connect_args={"timeout": 30},
        )
        
        # Cria tabelas e habilita WAL mode
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # WAL mode permite múltiplas leituras/escritas concorrentes
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            # Timeout maior para evitar locks em alta concorrência
            await conn.execute(text("PRAGMA busy_timeout=60000"))
            # Cache maior para menos I/O
            await conn.execute(text("PRAGMA cache_size=-64000"))
        
        # Session factory
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        return self
    
    async def close(self):
        """Fecha conexões."""
        if self._engine:
            await self._engine.dispose()
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager para sessões."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    @asynccontextmanager
    async def write_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager para escritas (usa WAL mode)."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    # =========================================================================
    # PÁGINAS
    # =========================================================================
    
    @with_retry(max_retries=5, base_delay=0.2, max_delay=5.0)
    async def save_page(
        self,
        url: str,
        url_hash: str,
        domain: str,
        status_code: int,
        title: Optional[str],
        html_content: str,
        text_content: str,
        depth: int,
        crawl_time_ms: int,
        content_type: Optional[str] = None,
        is_product_page: bool = False,
        category: Optional[str] = None,
    ) -> Page:
        """Salva uma página coletada (com retry automático)."""
        async with self.write_session() as session:
            page = Page(
                url=url,
                url_hash=url_hash,
                domain=domain,
                status_code=status_code,
                content_type=content_type,
                content_length=len(html_content) if html_content else 0,
                title=title,
                html_content=html_content,
                text_content=text_content,
                depth=depth,
                crawl_time_ms=crawl_time_ms,
                is_product_page=is_product_page,
                category=category,
            )
            session.add(page)
            await session.flush()
            return page
    
    async def page_exists(self, url_hash: str) -> bool:
        """Verifica se a página já foi coletada."""
        async with self.session() as session:
            result = await session.execute(
                select(Page.id).where(Page.url_hash == url_hash).limit(1)
            )
            return result.scalar() is not None
    
    async def get_page_count(self) -> int:
        """Retorna total de páginas coletadas."""
        async with self.session() as session:
            result = await session.execute(select(func.count(Page.id)))
            return result.scalar() or 0
    
    async def get_page_count_by_domain(self, domain: str) -> int:
        """Retorna total de páginas por domínio."""
        async with self.session() as session:
            result = await session.execute(
                select(func.count(Page.id)).where(Page.domain == domain)
            )
            return result.scalar() or 0
    
    # =========================================================================
    # PRODUTOS
    # =========================================================================
    
    @with_retry(max_retries=5, base_delay=0.2, max_delay=5.0)
    async def save_product(
        self,
        page_id: int,
        name: str,
        store: str,
        price: Optional[float] = None,
        price_raw: Optional[str] = None,
        sku: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Product:
        """Salva um produto detectado (com retry automático)."""
        async with self.write_session() as session:
            product = Product(
                page_id=page_id,
                name=name,
                store=store,
                price=price,
                price_raw=price_raw,
                sku=sku,
                brand=brand,
                category=category,
            )
            session.add(product)
            await session.flush()
            
            # Salva histórico de preço se disponível
            if price:
                history = PriceHistory(
                    product_id=product.id,
                    price=price,
                )
                session.add(history)
            
            return product
    
    async def get_pages_batch(self, offset: int = 0, limit: int = 500) -> list[Page]:
        """Retorna um lote de páginas para export (sem carregar tudo na memória)."""
        async with self.session() as session:
            result = await session.execute(
                select(Page)
                .order_by(Page.id.asc())
                .offset(offset)
                .limit(limit)
            )
            return result.scalars().all()

    async def get_product_count(self) -> int:
        """Retorna total de produtos."""
        async with self.session() as session:
            result = await session.execute(select(func.count(Product.id)))
            return result.scalar() or 0
    
    # =========================================================================
    # FRONTIER (URL Queue)
    # =========================================================================
    
    @with_retry(max_retries=5, base_delay=0.2, max_delay=5.0)
    async def add_to_frontier(
        self,
        url: str,
        url_hash: str,
        domain: str,
        priority: int = 0,
        depth: int = 0,
    ) -> bool:
        """
        Adiciona URL à frontier (com retry automático).
        
        Retorna True se adicionada, False se já existia.
        """
        async with self.write_session() as session:
            # Verifica se já existe
            result = await session.execute(
                select(Frontier.id).where(Frontier.url_hash == url_hash).limit(1)
            )
            if result.scalar() is not None:
                return False
            
            frontier = Frontier(
                url=url,
                url_hash=url_hash,
                domain=domain,
                priority=priority,
                depth=depth,
            )
            session.add(frontier)
            return True
    
    @with_retry(max_retries=5, base_delay=0.2, max_delay=5.0)
    async def add_many_to_frontier(
        self, 
        urls: list[tuple[str, str, str, int, int]]  # (url, hash, domain, priority, depth)
    ) -> int:
        """
        Adiciona múltiplas URLs à frontier (com retry automático).
        
        Retorna quantidade adicionada.
        """
        added = 0
        async with self.write_session() as session:
            for url, url_hash, domain, priority, depth in urls:
                result = await session.execute(
                    select(Frontier.id).where(Frontier.url_hash == url_hash).limit(1)
                )
                if result.scalar() is None:
                    frontier = Frontier(
                        url=url,
                        url_hash=url_hash,
                        domain=domain,
                        priority=priority,
                        depth=depth,
                    )
                    session.add(frontier)
                    added += 1
        return added
    
    async def get_next_urls(self, limit: int = 10, domain: Optional[str] = None) -> list[Frontier]:
        """
        Retorna próximas URLs a processar.
        
        Ordena por prioridade (desc) e seleciona pendentes.
        """
        async with self.session() as session:
            query = (
                select(Frontier)
                .where(Frontier.status == "pending")
                .order_by(Frontier.priority.desc(), Frontier.added_at.asc())
                .limit(limit)
            )
            if domain:
                query = query.where(Frontier.domain == domain)
            
            result = await session.execute(query)
            items = result.scalars().all()
            
            # Marca como processing
            for item in items:
                await session.execute(
                    update(Frontier)
                    .where(Frontier.id == item.id)
                    .values(status="processing")
                )
            
            return items
    
    async def mark_url_done(self, url_hash: str):
        """Marca URL como processada."""
        async with self.write_session() as session:
            await session.execute(
                update(Frontier)
                .where(Frontier.url_hash == url_hash)
                .values(status="done", processed_at=datetime.utcnow())
            )
    
    async def mark_url_failed(self, url_hash: str):
        """Marca URL como falha."""
        async with self.write_session() as session:
            await session.execute(
                update(Frontier)
                .where(Frontier.url_hash == url_hash)
                .values(status="failed", retries=Frontier.retries + 1)
            )
    
    async def get_frontier_stats(self) -> dict:
        """Retorna estatísticas da frontier."""
        async with self.session() as session:
            result = await session.execute(
                select(
                    Frontier.status,
                    func.count(Frontier.id)
                ).group_by(Frontier.status)
            )
            stats = {row[0]: row[1] for row in result.all()}
            return stats
    
    async def get_pending_count(self) -> int:
        """Retorna URLs pendentes."""
        async with self.session() as session:
            result = await session.execute(
                select(func.count(Frontier.id)).where(Frontier.status == "pending")
            )
            return result.scalar() or 0
    
    # =========================================================================
    # LINKS
    # =========================================================================
    
    @with_retry(max_retries=5, base_delay=0.2, max_delay=5.0)
    async def save_links(
        self, 
        source_page_id: int, 
        links: list[tuple[str, str, Optional[str]]]  # (url, hash, anchor)
    ):
        """Salva links encontrados em uma página (com retry automático)."""
        async with self.session() as session:
            for url, url_hash, anchor in links:
                link = Link(
                    source_page_id=source_page_id,
                    target_url=url,
                    target_url_hash=url_hash,
                    anchor_text=anchor[:512] if anchor else None,
                )
                session.add(link)
    
    # =========================================================================
    # ESTATÍSTICAS
    # =========================================================================
    
    async def get_stats(self) -> dict:
        """Retorna estatísticas gerais do crawler."""
        async with self.session() as session:
            pages = await session.execute(select(func.count(Page.id)))
            products = await session.execute(select(func.count(Product.id)))
            product_pages = await session.execute(
                select(func.count(Page.id)).where(Page.is_product_page == True)
            )
            
            # Por domínio
            domains = await session.execute(
                select(
                    Page.domain,
                    func.count(Page.id)
                ).group_by(Page.domain)
            )
            
            return {
                "total_pages": pages.scalar() or 0,
                "total_products": products.scalar() or 0,
                "product_pages": product_pages.scalar() or 0,
                "by_domain": {row[0]: row[1] for row in domains.all()},
            }
