"""
Testes de CLI (main.py) usando o CliRunner do Typer.
Valida que todos os comandos existem, retornam código 0 e exibem saída esperada.

Atenção: estes testes usam o banco real (data/crawler.db) e índice (data/index/)
que existem no repositório. Não modificam esses dados.
"""
import pytest
from typer.testing import CliRunner
from main import app

runner = CliRunner()


# ── Help de cada comando ──────────────────────────────────────────────────────

class TestHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "crawl" in result.output
        assert "stats" in result.output
        assert "clean" in result.output
        assert "index" in result.output

    def test_crawl_help(self):
        result = runner.invoke(app, ["crawl", "--help"])
        assert result.exit_code == 0
        assert "--max-pages" in result.output
        assert "--max-depth" in result.output
        assert "--stores" in result.output
        assert "--resume" in result.output

    def test_index_help(self):
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0
        assert "build" in result.output
        assert "stats" in result.output
        assert "search" in result.output

    def test_index_build_help(self):
        result = runner.invoke(app, ["index", "build", "--help"])
        assert result.exit_code == 0
        assert "--db" in result.output
        assert "--index-dir" in result.output
        assert "--no-stem" in result.output
        assert "--no-stopwords" in result.output

    def test_index_search_help(self):
        result = runner.invoke(app, ["index", "search", "--help"])
        assert result.exit_code == 0
        assert "--top" in result.output
        assert "--domain" in result.output

    def test_clean_help(self):
        result = runner.invoke(app, ["clean", "--help"])
        assert result.exit_code == 0
        assert "--db" in result.output
        assert "--html" in result.output
        assert "--index" in result.output
        assert "--all" in result.output
        assert "--yes" in result.output

    def test_browse_help(self):
        result = runner.invoke(app, ["browse", "--help"])
        assert result.exit_code == 0
        assert "--search" in result.output
        assert "--domain" in result.output
        assert "--limit" in result.output
        assert "--offset" in result.output
        assert "--url" in result.output

    def test_export_html_help(self):
        result = runner.invoke(app, ["export-html", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--limit" in result.output

    def test_seeds_help(self):
        result = runner.invoke(app, ["seeds", "--help"])
        assert result.exit_code == 0

    def test_categories_help(self):
        result = runner.invoke(app, ["categories", "--help"])
        assert result.exit_code == 0

    def test_version_help(self):
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == 0


# ── Comandos informativos (não modificam dados) ───────────────────────────────

class TestReadOnlyCommands:
    def test_stats_runs(self):
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0

    def test_stats_shows_domain_data(self):
        result = runner.invoke(app, ["stats"])
        # Com dados existentes deve mostrar pelo menos um domínio
        assert result.exit_code == 0
        # Verifica se a saída contém informação útil
        assert any(d in result.output for d in ["kabum", "mercado", "amazon", "Nenhuma"])

    def test_categories_runs(self):
        result = runner.invoke(app, ["categories"])
        assert result.exit_code == 0
        assert "gpu" in result.output.lower() or "GPU" in result.output

    def test_seeds_runs(self):
        result = runner.invoke(app, ["seeds"])
        assert result.exit_code == 0
        assert "kabum" in result.output.lower() or "http" in result.output

    def test_version_runs(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Hardware Crawler" in result.output

    def test_inspect_runs(self):
        result = runner.invoke(app, ["inspect"])
        assert result.exit_code == 0

    def test_browse_runs(self):
        result = runner.invoke(app, ["browse", "--limit", "5"])
        assert result.exit_code == 0

    def test_browse_search_runs(self):
        result = runner.invoke(app, ["browse", "--search", "rtx", "--limit", "3"])
        assert result.exit_code == 0

    def test_browse_pages_mode(self):
        result = runner.invoke(app, ["browse", "--pages", "--limit", "5"])
        assert result.exit_code == 0

    def test_analyze_products_runs(self):
        result = runner.invoke(app, ["analyze-products"])
        assert result.exit_code == 0


# ── Index commands ────────────────────────────────────────────────────────────

class TestIndexCommands:
    def test_index_stats_runs(self):
        """Requer índice construído em data/index/."""
        result = runner.invoke(app, ["index", "stats"])
        # Aceita exit 0 (índice presente) ou 1 (índice ausente)
        if result.exit_code != 0:
            assert "Índice não encontrado" in result.output or result.exit_code == 1
        else:
            assert "Documentos" in result.output or "total_docs" in result.output.lower()

    def test_index_search_rtx(self):
        result = runner.invoke(app, ["index", "search", "placa de video rtx"])
        if result.exit_code == 0:
            assert "Score" in result.output or "Nenhum resultado" in result.output
        else:
            # Índice não construído — ok
            assert "Índice não encontrado" in result.output

    def test_index_search_with_domain_filter(self):
        result = runner.invoke(app, ["index", "search", "ssd", "--domain", "kabum.com.br"])
        assert result.exit_code in (0, 1)

    def test_index_search_empty_query(self):
        """Query vazia deve retornar 'Nenhum resultado' ou erro gracioso."""
        result = runner.invoke(app, ["index", "search", "xyzzy_termo_inexistente_123"])
        assert result.exit_code in (0, 1)
        if result.exit_code == 0:
            assert "Nenhum resultado" in result.output or "Score" in result.output


# ── clean — seguro (só verifica o prompt, não executa) ───────────────────────

class TestCleanCommand:
    def test_clean_help_shows_correct_flags(self):
        result = runner.invoke(app, ["clean", "--help"])
        assert "--all" in result.output
        assert "--yes" in result.output
        # Garante que --all e --yes são flags separadas
        assert "--all / --yes" not in result.output, (
            "README bug: '--all / --yes' não deveriam ser mostrados como alternativas"
        )

    def test_clean_nothing_exists_graceful(self):
        """Se não há dados para limpar, deve sair sem erro."""
        # Roda clean sem confirmar (sem --yes, interativo → cancelado)
        result = runner.invoke(app, ["clean", "--index"], input="n\n")
        # Deve sair normalmente (cancelado pelo usuário ou sem dados)
        assert result.exit_code in (0, 1)
