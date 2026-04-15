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


@app.command(name="export-html")
def export_html(
    output: str = typer.Option(
        str(DATA_DIR / "html_pages"),
        "--output", "-o",
        help="Diretório de saída para os arquivos HTML"
    ),
    limit: int = typer.Option(
        0,
        "--limit", "-n",
        help="Limite de páginas a exportar (0 = todas)"
    ),
    db_path: str = typer.Option(
        str(DATA_DIR / "crawler.db"),
        "--db",
        help="Caminho do banco de dados"
    ),
):
    """
    Exporta HTMLs coletados do banco para arquivos .html no filesystem.

    Estrutura de saída:
        {output}/{domain}/{page_id:06d}.html
        {output}/index.jsonl  (metadados de cada página)

    Exemplos:
        python main.py export-html
        python main.py export-html --output html_pages/ --limit 1000
    """
    asyncio.run(_export_html(output, limit, db_path))


async def _export_html(output: str, limit: int, db_path: str):
    """Exporta páginas do DB como arquivos HTML."""
    import json as _json

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    db = Database(db_path)
    await db.initialize()

    index_path = output_dir / "index.jsonl"
    total_exported = 0
    batch_size = 500
    offset = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Exportando HTMLs...", total=None)

        with open(index_path, "w", encoding="utf-8") as index_file:
            while True:
                pages = await db.get_pages_batch(offset=offset, limit=batch_size)
                if not pages:
                    break

                for page in pages:
                    if not page.html_content:
                        continue

                    # Cria subpasta por domínio
                    domain_dir = output_dir / page.domain
                    domain_dir.mkdir(parents=True, exist_ok=True)

                    # Salva arquivo HTML
                    file_name = f"{page.id:06d}.html"
                    file_path = domain_dir / file_name
                    file_path.write_text(page.html_content, encoding="utf-8", errors="replace")

                    # Escreve linha no index.jsonl
                    rel_path = f"{page.domain}/{file_name}"
                    entry = {
                        "id": page.id,
                        "url": page.url,
                        "title": page.title,
                        "domain": page.domain,
                        "is_product": page.is_product_page,
                        "category": page.category,
                        "crawled_at": str(page.crawled_at),
                        "file": rel_path,
                    }
                    index_file.write(_json.dumps(entry, ensure_ascii=False) + "\n")

                    total_exported += 1
                    if limit and total_exported >= limit:
                        break

                progress.update(task, description=f"Exportando HTMLs... {total_exported:,} páginas")
                offset += batch_size

                if limit and total_exported >= limit:
                    break

    console.print(f"\n[bold green]✓[/] {total_exported:,} HTMLs exportados para: {output_dir.absolute()}")
    console.print(f"[green]✓[/] Índice: {index_path}")


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
def clean(
    db: bool = typer.Option(False, "--db", help="Limpa banco de dados"),
    html: bool = typer.Option(False, "--html", help="Limpa arquivos HTML exportados"),
    index: bool = typer.Option(False, "--index", help="Limpa índice invertido"),
    all_data: bool = typer.Option(False, "--all", help="Limpa tudo (equivale a --db --html --index)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirma sem perguntar"),
):
    """
    Remove dados gerados (banco, HTMLs, índice).

    Exemplos:
        python main.py clean              # interativo, pergunta o que limpar
        python main.py clean --db         # só banco de dados
        python main.py clean --html       # só arquivos HTML
        python main.py clean --index      # só índice invertido
        python main.py clean --all --yes  # tudo, sem confirmação
    """
    import shutil

    # Se nenhum flag específico, limpa tudo
    if not any([db, html, index, all_data]):
        all_data = True

    if all_data:
        db = html = index = True

    # Resolve caminhos
    db_file = DATA_DIR / "crawler.db"
    html_dir = DATA_DIR / "html_pages"
    index_dir = DATA_DIR / "index"

    # Calcula o que será removido
    targets = []
    if db and db_file.exists():
        size = db_file.stat().st_size
        targets.append((db_file, f"Banco de dados ({size / 1024 / 1024:.0f} MB)", "file"))
    if html and html_dir.exists():
        count = sum(1 for _ in html_dir.rglob("*.html"))
        size = sum(f.stat().st_size for f in html_dir.rglob("*") if f.is_file())
        targets.append((html_dir, f"Arquivos HTML ({count:,} arquivos, {size / 1024 / 1024:.0f} MB)", "dir"))
    if index and index_dir.exists():
        count = sum(1 for _ in index_dir.rglob("*.json"))
        size = sum(f.stat().st_size for f in index_dir.rglob("*") if f.is_file())
        targets.append((index_dir, f"Índice invertido ({count} arquivos, {size / 1024 / 1024:.1f} MB)", "dir"))

    if not targets:
        console.print("[yellow]Nada a remover (dados não existem).[/]")
        return

    console.print("\n[bold yellow]O seguinte será removido:[/]")
    for path, desc, _ in targets:
        console.print(f"  [red]✗[/] {desc}")
        console.print(f"    [dim]{path}[/dim]")

    if not yes:
        confirmed = typer.confirm("\nConfirmar remoção?")
        if not confirmed:
            console.print("[yellow]Operação cancelada.[/]")
            raise typer.Exit()

    console.print()
    for path, desc, kind in targets:
        try:
            if kind == "file":
                path.unlink()
            else:
                shutil.rmtree(path)
            console.print(f"[green]✓[/] Removido: {desc}")
        except Exception as e:
            console.print(f"[red]✗[/] Erro ao remover {path}: {e}")

    console.print("\n[green]Limpeza concluída.[/]")


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
    (Legado) Remove apenas o banco de dados. Prefira usar 'clean'.
    """
    if not confirm:
        confirm = typer.confirm(
            "Isso vai apagar o banco de dados. Continuar?"
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

    if total == 0:
        console.print("[yellow]Nenhum produto encontrado no banco.[/]")
        conn.close()
        return

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


# ---------------------------------------------------------------------------
# Sub-aplicação: index
# ---------------------------------------------------------------------------

index_app = typer.Typer(help="Gerencia o índice invertido BM25")
app.add_typer(index_app, name="index")


@index_app.command("build")
def index_build(
    db_path: str = typer.Option(
        str(DATA_DIR / "crawler.db"),
        "--db",
        help="Banco de dados fonte",
    ),
    index_dir: str = typer.Option(
        str(DATA_DIR / "index"),
        "--index-dir",
        help="Diretório de saída do índice",
    ),
    no_stem: bool = typer.Option(False, "--no-stem", help="Desativa stemming"),
    no_stopwords: bool = typer.Option(False, "--no-stopwords", help="Desativa remoção de stopwords"),
):
    """
    Constrói o índice invertido BM25 a partir do banco de dados.

    Exemplos:
        python main.py index build
        python main.py index build --index-dir data/index_custom/
    """
    from indexer import IndexBuilder, TextProcessor
    from rich.progress import BarColumn, MofNCompleteColumn, TimeElapsedColumn

    db_file = Path(db_path)
    if not db_file.exists():
        console.print("[red]Banco de dados não encontrado.[/] Execute: python main.py crawl")
        raise typer.Exit(1)

    tp = TextProcessor(use_stemming=not no_stem, use_stopwords=not no_stopwords)
    builder = IndexBuilder(index_dir=Path(index_dir), text_processor=tp)

    console.print(Panel.fit(
        f"[bold blue]Construindo Índice Invertido[/]\n"
        f"Fonte: {db_file}\n"
        f"Saída: {index_dir}\n"
        f"Stemmer: {tp.stemmer_name} | Stopwords: {'sim' if not no_stopwords else 'não'}",
        title="🔨 Index Build",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Indexando documentos...", total=None)

        def _cb(processed: int, total: int):
            progress.update(task, total=total, completed=processed,
                            description=f"Indexando documentos... {processed:,}/{total:,}")

        meta = builder.build_from_db(db_file, progress_cb=_cb)

    # Exibe estatísticas do índice construído
    table = Table(title="Índice Construído", show_header=True)
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="green", justify="right")
    table.add_row("Documentos indexados", f"{meta['total_docs']:,}")
    table.add_row("Termos únicos (vocabuário)", f"{meta['total_terms']:,}")
    table.add_row("Total de postings", f"{meta['total_postings']:,}")
    table.add_row("Comprimento médio (tokens)", f"{meta['avg_dl']:.1f}")
    table.add_row("Stemmer", meta["stemmer"])
    table.add_row("Stopwords ativas", "sim" if meta["use_stopwords"] else "não")
    table.add_row("Tempo de construção", f"{meta['build_time_s']:.1f} s")
    console.print(table)
    console.print(f"\n[bold green]✓[/] Índice salvo em: {Path(index_dir).absolute()}")


@index_app.command("stats")
def index_stats(
    index_dir: str = typer.Option(
        str(DATA_DIR / "index"),
        "--index-dir",
        help="Diretório do índice",
    ),
    top_n: int = typer.Option(20, "--top", "-n", help="Top N termos por frequência"),
):
    """
    Exibe estatísticas detalhadas do índice invertido.

    Exemplos:
        python main.py index stats
        python main.py index stats --top 50
    """
    from indexer import Searcher

    s = Searcher(index_dir=Path(index_dir))
    if not s.is_ready():
        console.print("[red]Índice não encontrado.[/] Execute: python main.py index build")
        raise typer.Exit(1)

    info = s.stats()

    # Métricas gerais
    overview = Table(title="Visão Geral do Índice", show_header=True)
    overview.add_column("Métrica", style="cyan")
    overview.add_column("Valor", style="green", justify="right")
    overview.add_row("Documentos", f"{info['total_docs']:,}")
    overview.add_row("Termos no vocabulário", f"{info['total_terms']:,}")
    overview.add_row("Total de postings", f"{info['total_postings']:,}")
    overview.add_row("Comprimento médio (tokens)", f"{info['avg_dl']:.1f}")
    overview.add_row("Stemmer", info["stemmer"])
    overview.add_row("Hapax legomena (df=1)", f"{info['hapax_legomena']:,} ({info['hapax_pct']}%)")
    overview.add_row("DF p50", str(info["df_p50"]))
    overview.add_row("DF p90", str(info["df_p90"]))
    overview.add_row("DF p99", str(info["df_p99"]))
    console.print(overview)

    # Top termos
    terms_table = Table(title=f"Top {top_n} Termos por Document Frequency", show_header=True)
    terms_table.add_column("Rank", style="dim", width=5)
    terms_table.add_column("Termo (stem)", style="cyan")
    terms_table.add_column("DF", style="green", justify="right")
    for rank, (term, df) in enumerate(info["top_terms"][:top_n], 1):
        terms_table.add_row(str(rank), term, f"{df:,}")
    console.print(terms_table)


@index_app.command("search")
def index_search(
    query: str = typer.Argument(..., help="Texto da busca"),
    top_k: int = typer.Option(10, "--top", "-k", help="Número de resultados"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filtrar por domínio (ex: kabum.com.br)"),
    index_dir: str = typer.Option(
        str(DATA_DIR / "index"),
        "--index-dir",
        help="Diretório do índice",
    ),
):
    """
    Busca no índice invertido usando BM25.

    Exemplos:
        python main.py index search "placa de video rtx 4070"
        python main.py index search "processador ryzen" --top 20
        python main.py index search "ssd nvme" --domain kabum.com.br
    """
    from indexer import Searcher

    s = Searcher(index_dir=Path(index_dir))
    if not s.is_ready():
        console.print("[red]Índice não encontrado.[/] Execute: python main.py index build")
        raise typer.Exit(1)

    results = s.search(query, top_k=top_k, domain_filter=domain)

    if not results:
        console.print(f"[yellow]Nenhum resultado para:[/] {query}")
        raise typer.Exit()

    title = f"Resultados BM25 para: \"{query}\""
    if domain:
        title += f" (domínio: {domain})"

    table = Table(title=title, show_header=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", style="yellow", justify="right", width=7)
    table.add_column("Título", style="cyan", max_width=55, overflow="ellipsis")
    table.add_column("Domínio", style="blue", width=22)
    table.add_column("Produto?", style="green", width=8)
    table.add_column("Categoria", style="magenta", width=12)

    for r in results:
        table.add_row(
            str(r["rank"]),
            f"{r['score']:.4f}",
            r["title"] or r["url"][:55],
            r["domain"],
            "✓" if r["is_product"] else "",
            r["category"] or "",
        )

    console.print(table)

    # Mostra URL do top resultado
    if results:
        console.print(f"\n[dim]Top resultado:[/] {results[0]['url']}")


@app.command()
def version():
    """
    Mostra a versão do crawler.
    """
    console.print("[bold blue]Hardware Crawler[/] v1.0.0")
    console.print("Sistema de RI - Fase 1: Coletor + Fase 2: Representação")
    console.print("Autor: Aluno")


if __name__ == "__main__":
    app()
