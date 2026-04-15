"""
Testes de storage (storage/database.py).
Usa banco SQLite em memória para isolar os testes.
"""
import pytest
import asyncio
from pathlib import Path
from storage.database import Database


@pytest.fixture
def event_loop():
    """Event loop dedicado para os testes async."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db(tmp_path):
    """Banco de dados temporário inicializado."""
    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    await database.initialize()
    return database


# ── Inicialização ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_initializes(tmp_path):
    db_path = tmp_path / "init_test.db"
    db = Database(str(db_path))
    result = await db.initialize()
    assert result is db  # retorna self para chaining


# ── get_stats ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stats_empty_db(tmp_path):
    db = Database(str(tmp_path / "empty.db"))
    await db.initialize()
    stats = await db.get_stats()
    assert isinstance(stats, dict)
    assert stats.get("total_pages", 0) == 0
    assert stats.get("total_products", 0) == 0


@pytest.mark.asyncio
async def test_get_stats_after_save(tmp_path):
    db = Database(str(tmp_path / "withdata.db"))
    await db.initialize()

    # Salva uma página
    await db.save_page(
        url="https://kabum.com.br/produto/1",
        url_hash="abc123",
        domain="kabum.com.br",
        status_code=200,
        title="RTX 4070",
        html_content="<html></html>",
        text_content="RTX 4070 placa de vídeo",
        depth=1,
        crawl_time_ms=100,
        is_product_page=True,
        category="gpu",
    )

    stats = await db.get_stats()
    assert stats["total_pages"] == 1
    assert stats.get("product_pages", 0) == 1
    assert "by_domain" in stats
    assert stats["by_domain"].get("kabum.com.br", 0) == 1


# ── page_exists ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_page_exists_false_before_save(tmp_path):
    db = Database(str(tmp_path / "exists.db"))
    await db.initialize()
    assert await db.page_exists("hash_que_nao_existe") is False


@pytest.mark.asyncio
async def test_page_exists_true_after_save(tmp_path):
    db = Database(str(tmp_path / "exists2.db"))
    await db.initialize()

    url_hash = "myhash001"
    await db.save_page(
        url="https://kabum.com.br/produto/2",
        url_hash=url_hash,
        domain="kabum.com.br",
        status_code=200,
        title="SSD",
        html_content="<html></html>",
        text_content="SSD NVMe",
        depth=1,
        crawl_time_ms=50,
    )

    assert await db.page_exists(url_hash) is True


# ── get_pages_batch ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pages_batch_empty(tmp_path):
    db = Database(str(tmp_path / "batch_empty.db"))
    await db.initialize()
    pages = await db.get_pages_batch(offset=0, limit=10)
    assert pages == []


@pytest.mark.asyncio
async def test_get_pages_batch_pagination(tmp_path):
    db = Database(str(tmp_path / "batch_pages.db"))
    await db.initialize()

    # Salva 5 páginas
    for i in range(5):
        await db.save_page(
            url=f"https://kabum.com.br/produto/{i}",
            url_hash=f"hash{i:03d}",
            domain="kabum.com.br",
            status_code=200,
            title=f"Produto {i}",
            html_content="<html></html>",
            text_content=f"texto do produto {i}",
            depth=1,
            crawl_time_ms=100,
        )

    batch1 = await db.get_pages_batch(offset=0, limit=3)
    batch2 = await db.get_pages_batch(offset=3, limit=3)

    assert len(batch1) == 3
    assert len(batch2) == 2

    # IDs não devem se sobrepor
    ids1 = {p.id for p in batch1}
    ids2 = {p.id for p in batch2}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_get_pages_batch_ordered_by_id(tmp_path):
    db = Database(str(tmp_path / "batch_order.db"))
    await db.initialize()

    for i in range(3):
        await db.save_page(
            url=f"https://kabum.com.br/item/{i}",
            url_hash=f"orderhash{i}",
            domain="kabum.com.br",
            status_code=200,
            title=f"Item {i}",
            html_content="<html></html>",
            text_content=f"item {i}",
            depth=1,
            crawl_time_ms=50,
        )

    pages = await db.get_pages_batch(offset=0, limit=10)
    ids = [p.id for p in pages]
    assert ids == sorted(ids), "get_pages_batch deve retornar em ordem crescente de ID"


# ── get_page_count ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_page_count_increments(tmp_path):
    db = Database(str(tmp_path / "count.db"))
    await db.initialize()

    assert await db.get_page_count() == 0

    await db.save_page(
        url="https://kabum.com.br/produto/99",
        url_hash="counthash001",
        domain="kabum.com.br",
        status_code=200,
        title="GPU",
        html_content="<html></html>",
        text_content="gpu rtx",
        depth=1,
        crawl_time_ms=100,
    )

    assert await db.get_page_count() == 1
