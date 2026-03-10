"""
Hardware Crawler - Spider Exploratório Principal

Crawler BFS com:
- Requisições HTTP assíncronas
- Extração de links
- Detecção de páginas de produto
- Checkpoints para retomada
- Estatísticas em tempo real
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, Callable, Any

import aiohttp
import psutil
from aiohttp_retry import RetryClient, ExponentialRetry
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from config import CRAWLER_CONFIG, get_all_seed_urls, get_enabled_stores
from crawler.frontier import (
    URLFrontier, URLItem, hash_url, normalize_url, 
    extract_links_from_html, is_product_url, extract_domain, calculate_priority
)
from crawler.politeness import PolitenessController
from storage import Database


console = Console()


@dataclass
class CrawlResult:
    """Resultado de uma requisição."""
    url: str
    url_hash: str
    status_code: int
    html: str
    text: str
    title: Optional[str]
    crawl_time_ms: int
    links: list[tuple[str, Optional[str]]]  # (url, anchor)
    is_product: bool
    error: Optional[str] = None


@dataclass
class CrawlStats:
    """Estatísticas do crawl em tempo real."""
    start_time: float = field(default_factory=time.time)
    pages_crawled: int = 0
    pages_failed: int = 0
    products_found: int = 0
    links_discovered: int = 0
    bytes_downloaded: int = 0
    
    # Por domínio
    by_domain: dict[str, int] = field(default_factory=dict)
    
    def pages_per_minute(self) -> float:
        """Calcula páginas por minuto."""
        elapsed = (time.time() - self.start_time) / 60
        return self.pages_crawled / elapsed if elapsed > 0 else 0
    
    def elapsed_time(self) -> str:
        """Retorna tempo decorrido formatado."""
        elapsed = int(time.time() - self.start_time)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class Spider:
    """
    Spider exploratório para coleta de páginas web.
    
    Características:
    - Crawl BFS com priorização
    - Requisições assíncronas
    - Respeita politeness
    - Detecta páginas de produto
    - Extrai links para continuar crawling
    """
    
    def __init__(
        self,
        db: Database,
        max_pages: int = CRAWLER_CONFIG.max_pages,
        max_concurrent: int = CRAWLER_CONFIG.max_concurrent_requests,
    ):
        self.db = db
        self.max_pages = max_pages
        self.max_concurrent = max_concurrent
        
        self.frontier = URLFrontier()
        self.politeness = PolitenessController()
        self.stats = CrawlStats()
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._semaphore: Optional[asyncio.Semaphore] = None
    
    async def initialize(self):
        """Inicializa recursos."""
        # Configura cliente HTTP com retry
        retry_options = ExponentialRetry(
            attempts=CRAWLER_CONFIG.max_retries,
            start_timeout=1,
            max_timeout=30,
            statuses={500, 502, 503, 504, 408, 429},
        )
        
        timeout = aiohttp.ClientTimeout(total=CRAWLER_CONFIG.request_timeout)
        
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            limit_per_host=CRAWLER_CONFIG.max_concurrent_per_domain,
        )
        
        self._session = RetryClient(
            raise_for_status=False,
            retry_options=retry_options,
            timeout=timeout,
            connector=connector,
            headers={
                "User-Agent": CRAWLER_CONFIG.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
    
    async def close(self):
        """Fecha recursos."""
        if self._session:
            await self._session.close()
    
    async def seed(self, urls: Optional[list[str]] = None):
        """
        Adiciona URLs iniciais (seeds).
        
        Se não fornecidas, usa as URLs padrão das lojas.
        """
        if urls is None:
            urls = get_all_seed_urls()
        
        for url in urls:
            self.frontier.add(url, depth=0, priority=90)
        
        console.print(f"[green]✓[/green] {len(urls)} URLs seed adicionadas")
    
    async def _fetch_page(self, url: str) -> CrawlResult:
        """
        Faz requisição HTTP e processa resposta.
        """
        url_hash = hash_url(normalize_url(url))
        start_time = time.time()
        
        try:
            # Aguarda permissão de politeness
            if not await self.politeness.wait_for_permission(url, self._session._client):
                return CrawlResult(
                    url=url,
                    url_hash=url_hash,
                    status_code=0,
                    html="",
                    text="",
                    title=None,
                    crawl_time_ms=0,
                    links=[],
                    is_product=False,
                    error="Blocked by robots.txt",
                )
            
            async with self._session.get(url) as response:
                status = response.status
                
                # Verifica content-type
                content_type = response.headers.get("Content-Type", "")
                if not any(ct in content_type for ct in CRAWLER_CONFIG.allowed_content_types):
                    return CrawlResult(
                        url=url,
                        url_hash=url_hash,
                        status_code=status,
                        html="",
                        text="",
                        title=None,
                        crawl_time_ms=int((time.time() - start_time) * 1000),
                        links=[],
                        is_product=False,
                        error=f"Invalid content-type: {content_type}",
                    )
                
                # Lê HTML
                html = await response.text(errors='replace')
                
                crawl_time = int((time.time() - start_time) * 1000)
                
                # Parse HTML
                soup = BeautifulSoup(html, 'lxml')
                
                # Extrai título
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True)[:512] if title_tag else None
                
                # Extrai texto (para indexação futura)
                # Remove scripts e estilos
                for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                    tag.decompose()
                text = soup.get_text(separator=' ', strip=True)[:50000]  # Limita tamanho
                
                # Extrai links
                links = extract_links_from_html(html, url)
                
                # Detecta página de produto
                is_product = is_product_url(url)
                
                return CrawlResult(
                    url=url,
                    url_hash=url_hash,
                    status_code=status,
                    html=html,
                    text=text,
                    title=title,
                    crawl_time_ms=crawl_time,
                    links=links,
                    is_product=is_product,
                )
                
        except asyncio.TimeoutError:
            return CrawlResult(
                url=url,
                url_hash=url_hash,
                status_code=0,
                html="",
                text="",
                title=None,
                crawl_time_ms=int((time.time() - start_time) * 1000),
                links=[],
                is_product=False,
                error="Timeout",
            )
        except Exception as e:
            return CrawlResult(
                url=url,
                url_hash=url_hash,
                status_code=0,
                html="",
                text="",
                title=None,
                crawl_time_ms=int((time.time() - start_time) * 1000),
                links=[],
                is_product=False,
                error=str(e)[:200],
            )
    
    async def _process_url(self, item: URLItem) -> bool:
        """
        Processa uma URL: fetch, parse, salva.
        
        Retorna True se sucesso.
        """
        async with self._semaphore:
            # Verifica se já alcançou limite
            if self.stats.pages_crawled >= self.max_pages:
                return False
            
            # Verifica se já existe no banco
            if await self.db.page_exists(item.url_hash):
                self.frontier.mark_seen(item.url_hash)
                return False
            
            # Fetch
            result = await self._fetch_page(item.url)
            
            if result.error:
                self.stats.pages_failed += 1
                await self.db.mark_url_failed(item.url_hash)
                return False
            
            if result.status_code != 200:
                self.stats.pages_failed += 1
                await self.db.mark_url_failed(item.url_hash)
                return False
            
            # Salva página
            domain = extract_domain(item.url)
            
            page = await self.db.save_page(
                url=item.url,
                url_hash=item.url_hash,
                domain=domain,
                status_code=result.status_code,
                title=result.title,
                html_content=result.html,
                text_content=result.text,
                depth=item.depth,
                crawl_time_ms=result.crawl_time_ms,
                is_product_page=result.is_product,
            )
            
            # Se é página de produto, extrai e salva informações
            if result.is_product and page:
                await self._extract_and_save_product(page, result.html, item.url, domain)
            
            # Atualiza estatísticas
            self.stats.pages_crawled += 1
            self.stats.bytes_downloaded += len(result.html)
            self.stats.by_domain[domain] = self.stats.by_domain.get(domain, 0) + 1
            
            if result.is_product:
                self.stats.products_found += 1
            
            # Adiciona links à frontier
            new_depth = item.depth + 1
            for link_url, anchor in result.links:
                if self.frontier.add(link_url, depth=new_depth):
                    self.stats.links_discovered += 1
            
            # Marca como processada
            await self.db.mark_url_done(item.url_hash)
            
            return True
    
    async def crawl(
        self, 
        progress_callback: Optional[Callable[[CrawlStats], None]] = None
    ):
        """
        Executa o crawl.
        
        Processa URLs da frontier até atingir limite ou esvaziar.
        """
        self._running = True
        
        console.print(f"\n[bold blue]🕷️ Iniciando crawl...[/bold blue]")
        console.print(f"   Meta: {self.max_pages:,} páginas")
        console.print(f"   Concorrência: {self.max_concurrent} requisições")
        console.print()
        
        # Inicializa contadores de rede
        net_start = psutil.net_io_counters()
        
        def get_system_stats() -> str:
            """Retorna string com métricas do sistema."""
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            net = psutil.net_io_counters()
            net_mb = (net.bytes_recv - net_start.bytes_recv) / (1024*1024)
            return f"CPU:{cpu:>4.0f}% | RAM:{mem:>4.0f}% | NET:{net_mb:>6.1f}MB"
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("{task.completed:,}/{task.total:,}"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TextColumn("[dim]{task.fields[sys_stats]}[/]"),
            console=console,
            refresh_per_second=2,
        ) as progress:
            
            task = progress.add_task(
                "[cyan]Coletando páginas...",
                total=self.max_pages,
                sys_stats=get_system_stats()
            )
            
            last_checkpoint = 0
            
            while self._running and self.stats.pages_crawled < self.max_pages:
                # Pega batch de URLs
                batch = self.frontier.pop_batch(self.max_concurrent)
                
                if not batch:
                    # Tenta carregar mais do banco
                    pending = await self.db.get_pending_count()
                    if pending == 0:
                        console.print("[yellow]⚠️ Frontier vazia, encerrando.[/yellow]")
                        break
                    
                    # Recarrega do banco
                    db_items = await self.db.get_next_urls(limit=100)
                    for item in db_items:
                        self.frontier.add(item.url, depth=item.depth, priority=item.priority)
                    continue
                
                # Processa batch em paralelo
                tasks = [self._process_url(item) for item in batch]
                await asyncio.gather(*tasks)
                
                # Atualiza progresso com métricas do sistema
                progress.update(
                    task, 
                    completed=self.stats.pages_crawled,
                    sys_stats=get_system_stats()
                )
                
                # Callback de progresso
                if progress_callback:
                    progress_callback(self.stats)
                
                # Checkpoint
                if self.stats.pages_crawled - last_checkpoint >= CRAWLER_CONFIG.checkpoint_interval:
                    await self._save_checkpoint()
                    last_checkpoint = self.stats.pages_crawled
            
            # Salva checkpoint final
            await self._save_checkpoint()
        
        self._running = False
        
        # Mostra resumo
        self._print_summary()
        
        return self.stats
    
    async def _save_checkpoint(self):
        """Salva estado atual para retomada."""
        # Salva URLs pendentes no banco
        pending_items = [
            (item.url, item.url_hash, item.domain, item.priority, item.depth)
            for item in self.frontier.pending
        ]
        
        if pending_items:
            await self.db.add_many_to_frontier(pending_items)
    
    async def _extract_and_save_product(self, page, html: str, url: str, domain: str):
        """
        Extrai informações do produto e salva no banco.
        
        Filtro de hardware: só salva produtos relacionados a informática.
        """
        from extractors import ProductDetector, PriceExtractor
        
        detector = ProductDetector()
        price_extractor = PriceExtractor()
        
        try:
            # Verificar se página está bloqueada (captcha/verificação)
            blocked_indicators = ['suspicious_traffic', 'captcha', 'challenge', 'blocked']
            html_lower = html.lower()
            is_blocked = any(ind in html_lower for ind in blocked_indicators)
            
            # Extrai info do produto
            info = detector.extract_product_info(html, url)
            
            if not info or not info.get('name'):
                # Usa título da página como fallback
                info = {'name': page.title or url}
            
            product_name = info.get('name', '')
            
            # Se o nome é uma URL, extrai do slug
            if product_name.startswith('http://') or product_name.startswith('https://'):
                product_name = self._extract_name_from_url(product_name) or product_name
            
            # Se ainda é URL após extração, página provavelmente bloqueada
            if product_name.startswith('http'):
                return
            
            # Filtrar páginas genéricas (não são produtos reais)
            generic_titles = [
                'kabum!', 'amazon.com.br', 'mercado livre', 'maior e-commerce',
                'prime ninja', 'programas grátis', 'programas gratuitos',
                'até 15% off', 'até 15 off', 'com desconto', 'benefícios',
            ]
            name_lower = product_name.lower()
            if any(gt in name_lower for gt in generic_titles):
                return
            
            # Filtro de hardware: verificar se é produto de informática
            is_hardware, classification = detector.is_hardware_product(product_name)
            
            if not is_hardware:
                # Produto não é hardware, não salvar
                return
            
            # Extrai preço
            price, price_raw = price_extractor.extract_price(html, url)
            
            # Se página bloqueada e sem preço, não salvar (dados incompletos)
            if is_blocked and not price:
                return
            
            # Detecta categoria
            category = detector.detect_category(product_name, html)
            
            # Determina loja pelo domínio
            store = domain.replace('.com.br', '').replace('www.', '')
            
            # Salva produto
            await self.db.save_product(
                page_id=page.id,
                name=product_name[:512],
                store=store,
                price=price,
                price_raw=price_raw,
                sku=info.get('sku'),
                brand=info.get('brand'),
                category=category,
            )
            
        except Exception as e:
            # Log do erro mas não falha
            console.print(f"[dim]Erro ao extrair produto de {url[:50]}: {e}[/dim]")
    
    def _extract_name_from_url(self, url: str) -> str:
        """
        Extrai nome do produto do slug da URL.
        
        Ex: https://www.mercadolivre.com.br/notebook-lenovo-ideapad/p/MLB123
            -> 'Notebook Lenovo Ideapad'
        """
        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip('/')
            
            # Para Mercado Livre: pega o segmento antes de /p/MLB
            if '/p/MLB' in path:
                path = path.split('/p/MLB')[0]
            
            path = path.rstrip('/')
            
            # Pega o último segmento do path
            if '/' in path:
                slug = path.split('/')[-1]
            else:
                slug = path
            
            # Remove IDs numéricos
            slug = re.sub(r'MLB\d+', '', slug)
            slug = re.sub(r'\d{5,}', '', slug)  # IDs longos
            
            # Converte hífens para espaços e formata
            name = slug.replace('-', ' ').replace('_', ' ')
            name = ' '.join(name.split())  # Remove múltiplos espaços
            
            if name:
                name = name.title()
            
            # Mínimo 5 caracteres para ser válido
            if name and len(name) >= 5:
                return name
                
        except Exception:
            pass
        
        return ''
    
    def stop(self):
        """Para o crawl graciosamente."""
        console.print("[yellow]🛑 Parando crawl...[/yellow]")
        self._running = False
    
    def _print_summary(self):
        """Imprime resumo do crawl."""
        console.print()
        console.print("[bold green]═══════════════════════════════════════════[/bold green]")
        console.print("[bold green]            RESUMO DO CRAWL                [/bold green]")
        console.print("[bold green]═══════════════════════════════════════════[/bold green]")
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green", justify="right")
        
        table.add_row("Tempo total", self.stats.elapsed_time())
        table.add_row("Páginas coletadas", f"{self.stats.pages_crawled:,}")
        table.add_row("Páginas com erro", f"{self.stats.pages_failed:,}")
        table.add_row("Produtos detectados", f"{self.stats.products_found:,}")
        table.add_row("Links descobertos", f"{self.stats.links_discovered:,}")
        table.add_row("Dados baixados", f"{self.stats.bytes_downloaded / 1024 / 1024:.1f} MB")
        table.add_row("Velocidade", f"{self.stats.pages_per_minute():.1f} pág/min")
        
        console.print(table)
        
        # Por domínio
        if self.stats.by_domain:
            console.print()
            console.print("[bold]Por domínio:[/bold]")
            domain_table = Table(show_header=True, box=None)
            domain_table.add_column("Domínio", style="blue")
            domain_table.add_column("Páginas", justify="right")
            
            for domain, count in sorted(
                self.stats.by_domain.items(), 
                key=lambda x: -x[1]
            ):
                domain_table.add_row(domain, f"{count:,}")
            
            console.print(domain_table)
        
        console.print()
