#!/usr/bin/env python3
"""
Hardware Crawler - CLI Principal

Interface de linha de comando para controlar o coletor.

Uso:
    python main.py crawl                    # Inicia coleta com defaults
    python main.py crawl --max-pages 1000   # Limita a 1000 páginas
    python main.py stats                    # Mostra estatísticas
    python main.py export                   # Exporta dados
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import STORES, CRAWLER_CONFIG, HARDWARE_CATEGORIES, DATA_DIR, get_enabled_stores_dict
from storage import Database
from crawler import Spider


# CLI App
app = typer.Typer(
    name="hardware-crawler",
    help="Coletor de páginas de hardware para Sistema de RI",
    add_completion=False,
)

console = Console()


@app.command()
def crawl(
    max_pages: int = typer.Option(
        CRAWLER_CONFIG.max_pages, 
        "--max-pages", "-n",
        help="Número máximo de páginas a coletar"
    ),
    max_depth: int = typer.Option(
        CRAWLER_CONFIG.max_depth,
        "--max-depth", "-d",
        help="Profundidade máxima de crawling"
    ),
    concurrency: int = typer.Option(
        CRAWLER_CONFIG.max_concurrent_requests,
        "--concurrency", "-c",
        help="Requisições concorrentes"
    ),
    delay: float = typer.Option(
        CRAWLER_CONFIG.default_delay,
        "--delay",
        help="Delay entre requisições (segundos)"
    ),
    stores: Optional[str] = typer.Option(
        None,
        "--stores", "-s",
        help="Lojas a coletar (separadas por vírgula)"
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="Retomar coleta anterior"
    ),
    db_path: str = typer.Option(
        str(DATA_DIR / "crawler.db"),
        "--db",
        help="Caminho do banco de dados"
    ),
):
    """
    Inicia ou retoma a coleta de páginas.
    
    Exemplos:
        python main.py crawl
        python main.py crawl --max-pages 1000
        python main.py crawl --stores kabum,magazineluiza
    """
    # Filtra lojas se especificado
    selected_stores = get_enabled_stores_dict()  # Usa apenas lojas habilitadas
    if stores:
        store_names = [s.strip().lower() for s in stores.split(',')]
        selected_stores = {
            name: config 
            for name, config in selected_stores.items() 
            if any(s in name.lower() for s in store_names)
        }
        
        if not selected_stores:
            console.print("[red]Erro:[/] Nenhuma loja válida encontrada.")
            console.print(f"Lojas disponíveis: {', '.join(STORES.keys())}")
            raise typer.Exit(1)
    
    # Banner
    console.print(Panel.fit(
        "[bold blue]Hardware Crawler[/]\n"
        f"Coletando de: {', '.join(selected_stores.keys())}\n"
        f"Meta: {max_pages:,} páginas | Profundidade: {max_depth}",
        title="🕷️ Iniciando Coleta",
    ))
    
    # Executa crawler
    try:
        asyncio.run(_run_crawler(
            stores=selected_stores,
            max_pages=max_pages,
            max_depth=max_depth,
            concurrency=concurrency,
            delay=delay,
            resume=resume,
            db_path=db_path,
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Coleta interrompida pelo usuário.[/]")
        console.print("Use [cyan]--resume[/] para continuar depois.")


async def _run_crawler(
    stores: dict,
    max_pages: int,
    max_depth: int,
    concurrency: int,
    delay: float,
    resume: bool,
    db_path: str,
):
    """Executa o crawler de forma assíncrona."""
    db = Database(db_path)
    await db.initialize()
    
    spider = Spider(
        db=db,
        max_pages=max_pages,
        max_concurrent=concurrency,
    )
    
    # Inicializa spider
    await spider.initialize()
    
    # Adicionar seeds das lojas selecionadas (se não for resume)
    if not resume:
        seed_urls = []
        for store in stores.values():
            seed_urls.extend(store.seed_urls)
        await spider.seed(seed_urls)
    
    start_time = datetime.now()
    
    try:
        stats = await spider.crawl()
        
        elapsed = datetime.now() - start_time
        
        # Mostra resumo
        console.print()
        console.print(Panel(
            f"[green]✓[/] Páginas coletadas: [bold]{stats.pages_crawled:,}[/]\n"
            f"[green]✓[/] Produtos encontrados: [bold]{stats.products_found:,}[/]\n"
            f"[red]✗[/] Erros: [bold]{stats.pages_failed:,}[/]\n"
            f"[blue]⏱[/] Tempo: [bold]{elapsed}[/]",
            title="📊 Resumo da Coleta",
        ))
        
    finally:
        await spider.close()


@app.command()
def stats(
    db_path: str = typer.Option(
        str(DATA_DIR / "crawler.db"),
        "--db",
        help="Caminho do banco de dados"
    ),
):
    """
    Mostra estatísticas da coleta.
    """
    asyncio.run(_show_stats(db_path))


async def _show_stats(db_path: str):
    """Mostra estatísticas do banco."""
    db = Database(db_path)
    await db.initialize()
    
    try:
        stats = await db.get_stats()
        
        if not stats or stats.get('total_pages', 0) == 0:
            console.print("[yellow]Nenhuma coleta realizada ainda.[/]")
            return
        
        # Tabela de páginas
        table = Table(title="Estatísticas de Coleta")
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green", justify="right")
        
        table.add_row("Total de Páginas", f"{stats.get('total_pages', 0):,}")
        table.add_row("Páginas de Produto", f"{stats.get('product_pages', 0):,}")
        table.add_row("Total de Produtos", f"{stats.get('total_products', 0):,}")
        
        console.print(table)
        
        # Por domínio
        if 'by_domain' in stats and stats['by_domain']:
            domain_table = Table(title="Por Domínio")
            domain_table.add_column("Domínio", style="cyan")
            domain_table.add_column("Páginas", justify="right")
            
            for domain, count in stats['by_domain'].items():
                domain_table.add_row(domain, f"{count:,}")
            
            console.print(domain_table)
            
    finally:
        pass  # db cleanup


@app.command(name="export")
def export_data(
    output: str = typer.Option(
        "export",
        "--output", "-o",
        help="Diretório de saída"
    ),
    format: str = typer.Option(
        "csv",
        "--format", "-f",
        help="Formato: csv, json"
    ),
    db_path: str = typer.Option(
        str(DATA_DIR / "crawler.db"),
        "--db",
        help="Caminho do banco de dados"
    ),
):
    """
    Exporta dados coletados.
    """
    asyncio.run(_export_data(output, format, db_path))


async def _export_data(output: str, format: str, db_path: str):
    """Exporta dados para arquivo."""
    import csv
    import json
    from sqlalchemy import select
    
    output_dir = Path(output)
    output_dir.mkdir(exist_ok=True)
    
    db = Database(db_path)
    await db.initialize()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        
        # Exporta páginas
        task = progress.add_task("Exportando páginas...", total=None)
        
        async with db.session() as session:
            from storage.models import Page, Product
            
            # Páginas
            result = await session.execute(select(Page))
            pages = result.scalars().all()
            
            if format == 'csv':
                pages_file = output_dir / "pages.csv"
                with open(pages_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['id', 'url', 'title', 'domain', 'is_product', 'crawled_at'])
                    for page in pages:
                        writer.writerow([
                            page.id, page.url, page.title, 
                            page.domain, page.is_product_page, page.crawled_at
                        ])
                console.print(f"[green]✓[/] Páginas exportadas: {pages_file}")
            
            elif format == 'json':
                pages_file = output_dir / "pages.json"
                data = [{
                    'id': p.id,
                    'url': p.url,
                    'title': p.title,
                    'domain': p.domain,
                    'is_product': p.is_product_page,
                    'crawled_at': str(p.crawled_at),
                } for p in pages]
                
                with open(pages_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                console.print(f"[green]✓[/] Páginas exportadas: {pages_file}")
            
            progress.update(task, description="Exportando produtos...")
            
            # Produtos (com eager loading da página)
            from sqlalchemy.orm import joinedload
            result = await session.execute(
                select(Product).options(joinedload(Product.page))
            )
            products = result.scalars().all()
            
            if format == 'csv':
                products_file = output_dir / "products.csv"
                with open(products_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'id', 'name', 'price', 'category', 
                        'store', 'url', 'last_updated'
                    ])
                    for prod in products:
                        url = prod.page.url if prod.page else ''
                        writer.writerow([
                            prod.id, prod.name, prod.price, 
                            prod.category, prod.store, url, prod.last_updated
                        ])
                console.print(f"[green]✓[/] Produtos exportados: {products_file}")
                
            elif format == 'json':
                products_file = output_dir / "products.json"
                data = [{
                    'id': p.id,
                    'name': p.name,
                    'price': float(p.price) if p.price else None,
                    'category': p.category,
                    'store': p.store,
                    'url': p.page.url if p.page else None,
                    'last_updated': str(p.last_updated),
                } for p in products]
                
                with open(products_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                console.print(f"[green]✓[/] Produtos exportados: {products_file}")
    
    console.print(f"\n[bold green]Exportação concluída![/] Arquivos em: {output_dir.absolute()}")


@app.command()
def seeds(
    store: Optional[str] = typer.Option(
        None,
        "--store", "-s",
        help="Filtrar por loja"
    ),
):
    """
    Lista as URLs seed configuradas.
    """
    table = Table(title="URLs Seed")
    table.add_column("Loja", style="cyan")
    table.add_column("URL", style="blue")
    
    for name, config in STORES.items():
        if store and store.lower() not in name.lower():
            continue
        
        for url in config.seed_urls:
            table.add_row(name, url)
    
    console.print(table)


@app.command()
def categories():
    """
    Lista as categorias de hardware monitoradas.
    """
    table = Table(title="Categorias de Hardware")
    table.add_column("Categoria", style="cyan")
    table.add_column("Palavras-chave", style="green")
    
    for cat, keywords in HARDWARE_CATEGORIES.items():
        table.add_row(cat, ", ".join(keywords[:5]) + "...")
    
    console.print(table)


@app.command()
def clear(
    db_path: str = typer.Option(
        str(DATA_DIR / "crawler.db"),
        "--db",
        help="Caminho do banco de dados"
    ),
    confirm: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Confirma limpeza sem perguntar"
    ),
):
    """
    Limpa todos os dados coletados.
    """
    if not confirm:
        confirm = typer.confirm(
            "⚠️  Isso vai apagar TODOS os dados coletados. Continuar?"
        )
    
    if not confirm:
        console.print("[yellow]Operação cancelada.[/]")
        raise typer.Exit()
    
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()
        console.print(f"[green]✓[/] Banco de dados removido: {db_path}")
    else:
        console.print("[yellow]Banco de dados não existe.[/]")


@app.command()
def inspect(
    limit: int = typer.Option(10, "--limit", "-l", help="Limite de itens para mostrar"),
):
    """
    Inspeciona o banco de dados e mostra o que está salvo.
    
    Mostra estatísticas detalhadas, amostras de produtos e distribuição.
    """
    import sqlite3
    import os
    
    db_file = DATA_DIR / "crawler.db"
    
    if not db_file.exists():
        console.print("[red]Banco de dados não existe.[/]")
        console.print("Execute primeiro: python main.py crawl")
        raise typer.Exit(1)
    
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    # === ESTATÍSTICAS GERAIS ===
    console.print(Panel.fit("[bold blue]📊 Inspeção do Banco de Dados[/]"))
    
    # Tamanho do arquivo
    db_size = os.path.getsize(db_file) / (1024*1024)
    console.print(f"\n[bold]Arquivo:[/] {db_file}")
    console.print(f"[bold]Tamanho:[/] {db_size:.1f} MB")
    
    # Contagens
    c.execute("SELECT COUNT(*) FROM pages")
    total_pages = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM products")
    total_products = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM products WHERE price IS NOT NULL AND price > 0")
    products_with_price = c.fetchone()[0]
    
    stats_table = Table(title="Estatísticas Gerais", show_header=True)
    stats_table.add_column("Métrica", style="cyan")
    stats_table.add_column("Valor", style="green", justify="right")
    stats_table.add_row("Total de Páginas", f"{total_pages:,}")
    stats_table.add_row("Total de Produtos", f"{total_products:,}")
    stats_table.add_row("Produtos com Preço", f"{products_with_price:,}")
    if total_products > 0:
        stats_table.add_row("Taxa de Preço", f"{products_with_price/total_products*100:.1f}%")
    console.print(stats_table)
    
    # === POR DOMÍNIO ===
    c.execute("SELECT domain, COUNT(*) FROM pages GROUP BY domain ORDER BY COUNT(*) DESC")
    domain_rows = c.fetchall()
    
    domain_table = Table(title="Páginas por Domínio", show_header=True)
    domain_table.add_column("Domínio", style="cyan")
    domain_table.add_column("Páginas", style="green", justify="right")
    domain_table.add_column("%", style="yellow", justify="right")
    for row in domain_rows:
        pct = (row[1] / total_pages * 100) if total_pages > 0 else 0
        domain_table.add_row(row[0], f"{row[1]:,}", f"{pct:.1f}%")
    console.print(domain_table)
    
    # === CATEGORIAS ===
    c.execute("""
        SELECT category, COUNT(*) 
        FROM products 
        GROUP BY category 
        ORDER BY COUNT(*) DESC 
        LIMIT ?
    """, (limit,))
    cat_rows = c.fetchall()
    
    cat_table = Table(title=f"Top {limit} Categorias de Produtos", show_header=True)
    cat_table.add_column("Categoria", style="cyan")
    cat_table.add_column("Quantidade", style="green", justify="right")
    for row in cat_rows:
        cat = row[0] if row[0] else "sem categoria"
        cat_table.add_row(cat, f"{row[1]:,}")
    console.print(cat_table)
    
    # === DISTRIBUIÇÃO DE PREÇOS ===
    c.execute("""
        SELECT 
            CASE 
                WHEN price < 100 THEN 'Até R$100'
                WHEN price < 500 THEN 'R$100-500'
                WHEN price < 1000 THEN 'R$500-1000'
                WHEN price < 5000 THEN 'R$1000-5000'
                ELSE 'Acima R$5000'
            END as faixa,
            COUNT(*)
        FROM products 
        WHERE price IS NOT NULL AND price > 0
        GROUP BY faixa
        ORDER BY MIN(price)
    """)
    price_rows = c.fetchall()
    
    price_table = Table(title="Distribuição de Preços", show_header=True)
    price_table.add_column("Faixa", style="cyan")
    price_table.add_column("Produtos", style="green", justify="right")
    for row in price_rows:
        price_table.add_row(row[0], f"{row[1]:,}")
    console.print(price_table)
    
    # === TOP PRODUTOS MAIS CAROS ===
    c.execute("""
        SELECT p.name, p.price, p.store, pg.domain
        FROM products p 
        JOIN pages pg ON p.page_id = pg.id 
        WHERE p.price IS NOT NULL 
        ORDER BY p.price DESC 
        LIMIT ?
    """, (limit,))
    top_rows = c.fetchall()
    
    console.print(f"\n[bold]🏆 Top {limit} Produtos Mais Caros:[/]")
    for i, row in enumerate(top_rows, 1):
        nome = row[0][:55] + "..." if row[0] and len(row[0]) > 55 else row[0]
        console.print(f"  {i}. [green]R$ {row[1]:,.2f}[/] - {nome}")
        console.print(f"     [dim]{row[2]} ({row[3]})[/]")
    
    # === AMOSTRA DE URLS ===
    console.print(f"\n[bold]🔗 Amostra de URLs Coletadas:[/]")
    for domain in [r[0] for r in domain_rows[:3]]:
        c.execute("SELECT url FROM pages WHERE domain = ? LIMIT 3", (domain,))
        urls = c.fetchall()
        console.print(f"  [cyan]{domain}:[/]")
        for url in urls:
            console.print(f"    {url[0][:80]}...")
    
    conn.close()
    
    console.print(f"\n[bold green]✓[/] Inspeção concluída!")


@app.command()
def browse(
    limit: int = typer.Option(20, "--limit", "-l", help="Quantidade de itens"),
    offset: int = typer.Option(0, "--offset", "-o", help="Pular N itens"),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Buscar por nome"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filtrar por domínio"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Preço mínimo"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Preço máximo"),
    show_url: bool = typer.Option(False, "--url", "-u", help="Mostrar URLs"),
    products_only: bool = typer.Option(True, "--products/--pages", help="Mostrar produtos ou páginas"),
):
    """
    Navega e busca dados no banco de dados.
    
    Exemplos:
        python main.py browse --search "placa de video"
        python main.py browse --domain kabum.com.br --limit 50
        python main.py browse --min-price 1000 --max-price 5000
        python main.py browse --pages  # Ver páginas em vez de produtos
    """
    import sqlite3
    
    db_file = DATA_DIR / "crawler.db"
    
    if not db_file.exists():
        console.print("[red]Banco de dados não existe.[/]")
        raise typer.Exit(1)
    
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    if products_only:
        # Buscar produtos
        query = """
            SELECT p.id, p.name, p.price, p.store, p.category, pg.url, pg.domain
            FROM products p 
            JOIN pages pg ON p.page_id = pg.id 
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND LOWER(p.name) LIKE ?"
            params.append(f"%{search.lower()}%")
        
        if domain:
            query += " AND pg.domain LIKE ?"
            params.append(f"%{domain}%")
        
        if min_price is not None:
            query += " AND p.price >= ?"
            params.append(min_price)
        
        if max_price is not None:
            query += " AND p.price <= ?"
            params.append(max_price)
        
        query += " ORDER BY p.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        c.execute(query, params)
        rows = c.fetchall()
        
        # Conta total
        count_query = query.replace("SELECT p.id, p.name, p.price, p.store, p.category, pg.url, pg.domain", "SELECT COUNT(*)")
        count_query = count_query.split("ORDER BY")[0]
        c.execute(count_query, params[:-2])
        total = c.fetchone()[0]
        
        # Tabela de resultados
        title = f"Produtos ({offset+1}-{offset+len(rows)} de {total:,})"
        if search:
            title += f" | Busca: '{search}'"
        
        table = Table(title=title, show_header=True)
        table.add_column("ID", style="dim", width=6)
        table.add_column("Nome", style="cyan", max_width=50, overflow="ellipsis")
        table.add_column("Preço", style="green", justify="right", width=12)
        table.add_column("Loja", style="yellow", width=15)
        table.add_column("Domínio", style="blue", width=20)
        
        for row in rows:
            price_str = f"R$ {row[2]:,.2f}" if row[2] else "-"
            table.add_row(
                str(row[0]),
                row[1][:50] if row[1] else "-",
                price_str,
                row[3] or "-",
                row[6] or "-",
            )
        
        console.print(table)
        
        if show_url and rows:
            console.print("\n[bold]URLs:[/]")
            for row in rows:
                console.print(f"  [dim]{row[0]}:[/] {row[5]}")
    
    else:
        # Buscar páginas
        query = """
            SELECT id, url, domain, title, status_code, is_product_page
            FROM pages 
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND (LOWER(title) LIKE ? OR LOWER(url) LIKE ?)"
            params.extend([f"%{search.lower()}%", f"%{search.lower()}%"])
        
        if domain:
            query += " AND domain LIKE ?"
            params.append(f"%{domain}%")
        
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        c.execute(query, params)
        rows = c.fetchall()
        
        table = Table(title=f"Páginas (offset {offset})", show_header=True)
        table.add_column("ID", style="dim", width=6)
        table.add_column("Título", style="cyan", max_width=40, overflow="ellipsis")
        table.add_column("Domínio", style="yellow", width=20)
        table.add_column("Status", style="green", width=6)
        table.add_column("Produto?", style="blue", width=8)
        
        for row in rows:
            table.add_row(
                str(row[0]),
                (row[3] or row[1])[:40],
                row[2],
                str(row[4]),
                "✓" if row[5] else "",
            )
        
        console.print(table)
        
        if show_url:
            console.print("\n[bold]URLs:[/]")
            for row in rows:
                console.print(f"  [dim]{row[0]}:[/] {row[1][:100]}")
    
    conn.close()
    
    # Dicas
    console.print(f"\n[dim]Próxima página: --offset {offset + limit}[/]")


@app.command()
def analyze_products():
    """
    Analisa produtos encontrados e detecta possíveis erros (não-hardware).
    """
    import sqlite3
    
    db_file = DATA_DIR / "crawler.db"
    
    if not db_file.exists():
        console.print("[red]Banco de dados não existe.[/]")
        raise typer.Exit(1)
    
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    # Palavras-chave de hardware
    hardware_keywords = [
        'placa de vídeo', 'placa de video', 'gpu', 'rtx', 'gtx', 'radeon', 'geforce', 'vga',
        'processador', 'cpu', 'ryzen', 'intel', 'core i', 'amd',
        'memoria', 'memória', 'ram', 'ddr4', 'ddr5',
        'ssd', 'hd', 'nvme', 'disco', 'armazenamento', 'm.2',
        'placa-mãe', 'placa mãe', 'motherboard', 'placa mae',
        'fonte', 'psu', 'w bronze', 'w gold', 'watt',
        'gabinete', 'case', 'torre',
        'cooler', 'water cooler', 'air cooler', 'ventilador',
        'teclado', 'keyboard', 'mecânico', 'mecanico',
        'mouse', 'mousepad',
        'monitor', 'polegadas', '"', 'hz',
        'headset', 'fone', 'microfone',
        'notebook', 'laptop', 'pc gamer',
        'roteador', 'wifi', 'rede',
    ]
    
    # Palavras que indicam NÃO-hardware
    non_hardware_keywords = [
        'carro', 'veículo', 'veiculo', 'automóvel', 'automovel',
        'moto', 'motocicleta', 'caminhão', 'caminhao',
        'roupa', 'camiseta', 'calça', 'sapato', 'tênis', 'tenis',
        'móveis', 'moveis', 'sofá', 'sofa', 'cama', 'colchão',
        'geladeira', 'fogão', 'fogao', 'microondas', 'lavadora',
        'celular', 'iphone', 'samsung galaxy', 'smartphone',
        'brinquedo', 'boneca', 'lego',
        'perfume', 'maquiagem', 'cosmético',
        'livro', 'kindle',
        'comida', 'alimento', 'bebida',
    ]
    
    console.print(Panel.fit("[bold blue]🔍 Análise de Produtos[/]"))
    
    # Conta total
    c.execute("SELECT COUNT(*) FROM products")
    total = c.fetchone()[0]
    
    # Conta hardware válido
    hardware_count = 0
    non_hardware_count = 0
    unknown_count = 0
    
    c.execute("SELECT id, name FROM products")
    all_products = c.fetchall()
    
    non_hardware_samples = []
    
    for prod_id, name in all_products:
        if not name:
            unknown_count += 1
            continue
            
        name_lower = name.lower()
        
        is_hardware = any(kw in name_lower for kw in hardware_keywords)
        is_non_hardware = any(kw in name_lower for kw in non_hardware_keywords)
        
        if is_non_hardware and not is_hardware:
            non_hardware_count += 1
            if len(non_hardware_samples) < 20:
                non_hardware_samples.append((prod_id, name))
        elif is_hardware:
            hardware_count += 1
        else:
            unknown_count += 1
    
    # Tabela de resumo
    table = Table(title="Classificação de Produtos", show_header=True)
    table.add_column("Categoria", style="cyan")
    table.add_column("Quantidade", style="green", justify="right")
    table.add_column("%", style="yellow", justify="right")
    
    table.add_row("✓ Hardware válido", f"{hardware_count:,}", f"{hardware_count/total*100:.1f}%")
    table.add_row("✗ Não-hardware", f"{non_hardware_count:,}", f"{non_hardware_count/total*100:.1f}%")
    table.add_row("? Não classificado", f"{unknown_count:,}", f"{unknown_count/total*100:.1f}%")
    table.add_row("[bold]Total[/]", f"[bold]{total:,}[/]", "[bold]100%[/]")
    
    console.print(table)
    
    # Amostras de não-hardware
    if non_hardware_samples:
        console.print(f"\n[bold red]⚠️ Amostras de Não-Hardware Detectados:[/]")
        for prod_id, name in non_hardware_samples[:15]:
            console.print(f"  [dim]{prod_id}:[/] {name[:70]}")
    
    # Por domínio
    console.print(f"\n[bold]Distribuição por Domínio:[/]")
    c.execute("""
        SELECT pg.domain, COUNT(*) 
        FROM products p 
        JOIN pages pg ON p.page_id = pg.id 
        GROUP BY pg.domain 
        ORDER BY COUNT(*) DESC
    """)
    for domain, count in c.fetchall():
        pct = count / total * 100
        console.print(f"  {domain}: {count:,} ({pct:.1f}%)")
    
    conn.close()
    
    console.print(f"\n[bold yellow]💡 Dica:[/] Use 'browse --search \"placa de video\"' para ver só hardware válido")


@app.command()
def version():
    """
    Mostra a versão do crawler.
    """
    console.print("[bold blue]Hardware Crawler[/] v1.0.0")
    console.print("Sistema de RI - Fase 1: Coletor")
    console.print("Autor: Aluno")


if __name__ == "__main__":
    app()
