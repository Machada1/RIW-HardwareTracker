# Hardware Crawler — Sistema de Recuperação de Informação

Coletor web especializado em e-commerces brasileiros de hardware, com motor de busca BM25 sobre os dados coletados.
Desenvolvido para a disciplina de Recuperação de Informação — Fases 1 (Coletor) e 2 (Representação/Indexação).

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Testes](https://img.shields.io/badge/Testes-188%20passando-brightgreen)
![Status](https://img.shields.io/badge/Status-Funcional-brightgreen)

---

## Funcionalidades

**Fase 1 — Coletor**
- Crawl assíncrono BFS com priorização por tipo de URL e balanceamento entre domínios
- Deduplicação via SHA-256; normalização de URL (UTM, `/ref=` Amazon, fragmentos)
- Extração de produtos via JSON-LD (schema.org) e OpenGraph; extração de preços em R$
- Politeness: robots.txt respeitado, rate limiting por domínio (0,2 s padrão)
- Persistência dual: banco SQLite + arquivos HTML em disco

**Fase 2 — Índice BM25**
- Pipeline NLP para português: tokenização → stopwords (~120 termos) → stemmer RSLP
- Índice invertido shardado em 256 arquivos JSON (sem banco externo)
- Busca BM25 ranqueada com facetamento por domínio
- 188 testes automatizados cobrindo todos os módulos

---

## Stack Tecnológica

| Camada | Tecnologia | Uso |
|--------|-----------|-----|
| Coleta | `aiohttp` + `aiohttp-retry` | Requisições HTTP async com retry exponencial |
| Parsing | `beautifulsoup4` + `lxml` | Extração de HTML, JSON-LD, links |
| Banco | `sqlalchemy` + `aiosqlite` | ORM async sobre SQLite com WAL |
| NLP | `nltk` (RSLP + stopwords) | Stemmer português e lista de paradas |
| CLI | `typer` + `rich` | Interface de terminal com tabelas e progress bars |
| Domínios | `tldextract` | Extração correta de domínio registrado (com/sem www, lista/...) |
| Testes | `pytest` + `pytest-asyncio` | Suite completa; modo asyncio automático |

---

## Lojas Suportadas

| Loja | Domínio | Status |
|------|---------|--------|
| Kabum | `kabum.com.br` | Funcional |
| Mercado Livre | `mercadolivre.com.br` | Funcional (anti-bot parcial) |
| Amazon Brasil | `amazon.com.br` | Funcional (rate-limit frequente) |
| Magazine Luiza | `magazineluiza.com.br` | Desabilitado — SPA/React |
| Pichau / Terabyte | — | Inviável — Cloudflare WAF (HTTP 403) |

---

## Instalação

**Requisitos:** Python 3.11+, ~5 GB livres em disco (para 50k páginas).

```bash
# 1. Ambiente virtual
python -m venv venv
source venv/bin/activate      # Linux/macOS
# venv\Scripts\activate       # Windows

# 2. Dependências
pip install -r requirements.txt

# 3. Dados NLTK (stemmer + stopwords — necessário uma vez só)
python -c "import nltk; nltk.download('rslp'); nltk.download('stopwords')"

# 4. Verificar
python main.py --help
```

---

## Uso Rápido

```bash
# 1. Coletar páginas
python main.py crawl --max-pages 200 --no-resume

# 2. Ver o que foi coletado
python main.py stats
python main.py browse --limit 20

# 3. Construir índice invertido
python main.py index build

# 4. Buscar
python main.py index search "placa de video rtx 4070"

# 5. Limpar tudo para recomeçar
python main.py clean --all --yes
```

---

## Estrutura do Repositório

```
Python-WebCrawler/
├── main.py                  # CLI principal (Typer + Rich) — todos os comandos
├── config.py                # Configurações: lojas, seeds, parâmetros do crawler
├── requirements.txt         # Dependências Python
├── pytest.ini               # Configuração do pytest (asyncio_mode = auto)
│
├── crawler/                 # Módulo de coleta
│   ├── spider.py            # Spider BFS assíncrono — loop principal
│   ├── frontier.py          # Fila de URLs: prioridade, deduplicação, balanceamento
│   └── politeness.py        # robots.txt e rate limiting por domínio
│
├── extractors/              # Módulo de extração de dados
│   ├── product_detector.py  # Detecta produto vs. listagem (JSON-LD, OG, URL)
│   └── price_extractor.py   # Extrai preços: JSON-LD → meta tags → CSS → regex R$
│
├── storage/                 # Módulo de persistência
│   ├── models.py            # Tabelas SQLAlchemy (pages, products, frontier, …)
│   └── database.py          # CRUD assíncrono com retry e WAL
│
├── indexer/                 # Módulo de indexação — Fase 2
│   ├── text_processor.py    # Tokenização, stopwords PT-BR, stemmer RSLP
│   ├── builder.py           # Constrói índice invertido shardado
│   └── searcher.py          # Busca BM25 com cache de shards
│
├── tests/                   # Suite de testes (188 testes, 8 arquivos)
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_frontier.py
│   ├── test_price_extractor.py
│   ├── test_product_detector.py
│   ├── test_text_processor.py
│   ├── test_indexer.py
│   ├── test_database.py
│   └── test_cli.py
│
└── data/                    # Gerado em runtime (não commitado)
    ├── crawler.db           # Banco SQLite
    ├── html_pages/          # HTMLs por domínio: {domain}/{id:06d}.html
    │   └── index.jsonl      # Metadados de cada página exportada
    └── index/               # Índice invertido
        ├── meta.json        # Estatísticas do índice
        ├── vocab.json       # Vocabulário e frequências
        ├── docs.json        # Metadados dos documentos
        └── postings/        # 256 shards de postings (00.json … ff.json)
```

---

## Referência de Comandos CLI

Todos os comandos: `python main.py <comando> [opções]`.

### Coleta

```
crawl          Inicia ou retoma coleta de páginas
  --max-pages N      Limite de páginas (padrão: 60000)
  --max-depth N      Profundidade máxima de links (padrão: 20)
  --concurrency N    Requisições paralelas (padrão: 25)
  --delay F          Delay entre req. ao mesmo domínio em segundos (padrão: 0.2)
  --stores S         Lojas separadas por vírgula: "kabum,amazon,mercadolivre"
  --resume / --no-resume  Retomar coleta anterior (padrão: --resume)
```

### Inspeção e Navegação

```
stats          Estatísticas resumidas: total de páginas, produtos, por domínio
inspect        Análise detalhada: distribuição de preços, categorias, top produtos
browse         Navega produtos com filtros
  --search S         Filtro por texto no nome do produto
  --domain D         Filtro por domínio
  --min-price F      Preço mínimo (R$)
  --max-price F      Preço máximo (R$)
  --limit N          Itens por página (padrão: 20)
  --offset N         Pular N itens para paginação (padrão: 0)
  --url              Mostrar URLs completas
  --products / --pages   Modo produto ou página (padrão: produtos)
analyze-products   Classifica produtos em hardware / não-hardware / desconhecido
```

### Índice Invertido

```
index build    Constrói índice a partir do campo text_content do banco
  --db PATH          Banco de dados fonte (padrão: data/crawler.db)
  --index-dir DIR    Diretório de saída (padrão: data/index/)
  --no-stem          Desabilita stemming
  --no-stopwords     Desabilita remoção de stopwords

index stats    Estatísticas do vocabulário e do índice
  --top N            Mostra top N termos mais frequentes (padrão: 20)

index search   Busca BM25 no índice
  QUERY              Consulta de busca (ex: "placa de video rtx 4070")
  --top N            Quantidade de resultados (padrão: 10)
  --domain D         Filtro por domínio
```

### Exportação e Manutenção

```
export-html    Re-exporta HTMLs do banco para data/html_pages/ e gera index.jsonl
  --output DIR       Diretório de saída (padrão: data/html_pages/)
  --limit N          Limitar quantidade (0 = todos)

export         Exporta CSV/JSON das tabelas do banco
  --format csv|json
  --output DIR

seeds          Lista URLs seed configuradas por loja
categories     Lista categorias de hardware e suas keywords

clean          Remove dados coletados
  --db               Limpa apenas o banco (data/crawler.db)
  --html             Limpa apenas os HTMLs (data/html_pages/)
  --index            Limpa apenas o índice (data/index/)
  --all              Limpa tudo (equivalente a --db --html --index)
  --yes, -y          Confirma sem prompt interativo
  (sem flags)        Limpa tudo (equivalente a --all)
```

---

## Configuração

Toda a configuração está em `config.py`.

### Parâmetros do Crawler

```python
@dataclass
class CrawlerConfig:
    max_pages: int = 60000              # Meta de páginas
    max_depth: int = 20                 # Profundidade máxima de links
    max_concurrent_requests: int = 25   # Requisições paralelas totais
    max_concurrent_per_domain: int = 6  # Por domínio
    default_delay: float = 0.2          # Delay entre req. ao mesmo domínio (s)
    request_timeout: int = 30           # Timeout por requisição (s)
    max_retries: int = 3                # Tentativas por URL
    checkpoint_interval: int = 500      # Salvar frontier a cada N páginas
    respect_robots_txt: bool = True
```

### Ajustar Performance

```python
# Mais rápido (maior risco de bloqueio)
max_concurrent_requests = 40
default_delay = 0.1

# Mais conservador
max_concurrent_requests = 10
default_delay = 0.5
```

### Adicionar Nova Loja

```python
# Em config.py, no dicionário STORES:
"nova_loja": StoreConfig(
    name="Nova Loja",
    domain="novaloja.com.br",
    enabled=True,
    seed_urls=["https://www.novaloja.com.br/hardware"],
    request_delay=0.5,
    product_patterns=[r"/produto/[a-z0-9-]+"],
    ignore_patterns=[r"/login", r"/carrinho"],
),
```

---

## Estrutura de Dados

### Banco SQLite (`data/crawler.db`)

| Tabela | Descrição |
|--------|-----------|
| `pages` | Páginas coletadas: URL, HTML completo, texto extraído, domínio, profundidade |
| `products` | Produtos detectados: nome, preço, categoria, SKU, loja |
| `price_history` | Variação de preço ao longo do tempo |
| `frontier` | URLs pendentes: prioridade, profundidade, status |
| `crawl_stats` | Métricas de execução por sessão (checkpoints) |

### Arquivo `index.jsonl`

Uma linha JSON por página exportada:

```json
{
  "id": 1,
  "url": "https://www.kabum.com.br/produto/419013/rtx-4060",
  "title": "RTX 4060 8GB GDDR6 Zotac",
  "domain": "kabum.com.br",
  "is_product": true,
  "category": "gpu",
  "crawled_at": "2026-04-14 11:28:00",
  "file": "kabum.com.br/000001.html"
}
```

### Índice Invertido (`data/index/`)

- **`meta.json`** — estatísticas globais: total_docs, avg_dl, stemmer, tempo de build
- **`vocab.json`** — `{stem: {id, df, raw}}` para todos os termos
- **`docs.json`** — `{doc_id: {url, title, domain, dl, is_product, category}}`
- **`postings/XX.json`** — `{term_id: [[doc_id, tf], ...]}` (256 shards por `term_id % 256`)

---

## Performance

### Métricas Observadas

| Cenário | Velocidade | Notas |
|---------|-----------|-------|
| Kabum isolado | ~200 pág/min | Estável |
| Mix 3 lojas | ~150 pág/min | Limitado por rate-limit da Amazon |
| Coleta 50k | ~5–6 horas | Estimativa com delays padrão |

### Espaço em Disco (50k páginas)

| Dado | Estimativa |
|------|-----------|
| `crawler.db` | ~15 GB |
| `data/html_pages/` | ~8 GB |
| `data/index/` | ~200 MB |

---

## Troubleshooting

**"database is locked"**
```bash
python main.py crawl --concurrency 10   # reduzir concorrência
```

**Muitos erros 403 / 429 (bloqueio de IP)**
```bash
python main.py crawl --delay 1.0
# ou crawlar só uma loja com menos proteção:
python main.py crawl --stores kabum --max-pages 5000
```

**Índice não encontrado ao buscar**
```bash
python main.py index build
```

**Verificar integridade do banco**
```bash
sqlite3 data/crawler.db "PRAGMA integrity_check;"
```

**Recomeçar do zero**
```bash
python main.py clean --all --yes
python main.py crawl --max-pages 60000 --no-resume
```

---

## Roteiro de Validação

Este roteiro permite a qualquer integrante do grupo reproduzir e validar o sistema do zero — desde a instalação até a busca BM25. Siga os passos em ordem.

---

### Passo 0 — Pré-requisitos

- Python 3.11+ (`python --version`)
- Conexão com a internet
- ~10 GB livres em disco

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
python -c "import nltk; nltk.download('rslp'); nltk.download('stopwords')"

python main.py --help
```
> ✅ Lista de comandos exibida sem erros.

---

### Passo 1 — Estado limpo inicial

```bash
python main.py clean --all --yes
ls data/
```
> ✅ Apenas `README.md` em `data/`.

---

### Passo 2 — Coleta de teste (~200 páginas)

```bash
python main.py crawl --max-pages 200 --no-resume
python main.py stats
```
> ✅ Esperado:
> - ~200 páginas coletadas
> - Exatamente 3 domínios: `kabum.com.br`, `mercadolivre.com.br`, `amazon.com.br`
> - **Não** deve aparecer `amazon.com`, `mercadolivre.com` ou `aboutamazon.com.br`

---

### Passo 3 — Verificar qualidade dos dados

```bash
# Produtos detectados
python main.py browse --limit 20

# Deve retornar vazio (nenhum preço < R$50 — seriam falsos positivos)
python main.py browse --min-price 1 --max-price 49 --limit 20

# Busca por produto
python main.py browse --search "rtx" --limit 10
python main.py browse --search "ssd" --limit 10

# Smart TVs não devem aparecer como categoria "hdd"
python main.py browse --search "smart tv" --limit 10

# Análise de qualidade geral
python main.py analyze-products
```
> ✅ Produtos de hardware com preços em R$. Nenhum preço < R$50. Smart TVs sem categoria "hdd".

---

### Passo 4 — HTMLs no disco

```bash
ls data/html_pages/
# → kabum.com.br/  mercadolivre.com.br/  amazon.com.br/

ls data/html_pages/kabum.com.br/ | head -5
# → 000001.html  000002.html  ...

wc -l data/html_pages/kabum.com.br/000001.html
# → número > 0

# Gerar/atualizar metadados (opcional)
python main.py export-html
head -3 data/html_pages/index.jsonl
```
> ✅ Subpastas por domínio, HTMLs não vazios, index.jsonl com campos `id, url, title, domain, is_product, category, file`.

---

### Passo 5 — Construir índice invertido

```bash
python main.py index build
python main.py index stats
```
> ✅ Para ~200 documentos:
> - Documentos indexados: ~200
> - Termos únicos: > 1.000
> - Stemmer: `rslp`

---

### Passo 6 — Validar busca BM25

```bash
# Buscas por categoria
python main.py index search "placa de video rtx 4070"
python main.py index search "ssd nvme 1tb"
python main.py index search "processador ryzen 5"

# Filtro por loja
python main.py index search "placa de video" --domain kabum.com.br --top 5

# Termo inexistente (não deve crashar)
python main.py index search "xyzzy_termo_que_nao_existe"
```
> ✅ Resultados relevantes ranqueados por score decrescente. Scores sempre positivos. "Nenhum resultado" para termo inexistente — sem crash.

---

### Passo 7 — Suite de testes automatizados

```bash
python -m pytest tests/ -v
```
> ✅ `188 passed, 0 failed` em menos de 10 segundos.

| Arquivo | Testes | O que cobre |
|---------|--------|-------------|
| `test_config.py` | 12 | Categorias de hardware, lojas, parâmetros defaults |
| `test_frontier.py` | 37 | Normalização URL, SHA-256, balanceamento, filtragem de domínio |
| `test_price_extractor.py` | 23 | Falso positivo RGB, validação R$50–R$100k, JSON-LD, meta tags |
| `test_product_detector.py` | 24 | Produto vs. listagem, categorias, filtro hardware |
| `test_text_processor.py` | 15 | Tokenização, stopwords, RSLP, unicode |
| `test_indexer.py` | 16 | Build, ranking BM25, filtro de domínio |
| `test_database.py` | 9 | CRUD assíncrono, paginação, page_exists |
| `test_cli.py` | 52 | Todos os subcomandos e flags |

---

### Passo 8 — Coleta completa (50k+ páginas)

```bash
# Inicia coleta (leva ~5–6 horas)
python main.py crawl --max-pages 60000

# Em outra sessão, monitorar progresso:
python main.py stats
python main.py inspect

# Ao terminar:
python main.py index build
python main.py index stats
```

> ✅ Critérios de aceite para entrega:
> - Total de páginas ≥ 50.000
> - Exatamente 3 domínios: `kabum.com.br`, `mercadolivre.com.br`, `amazon.com.br`
> - Nenhum domínio com > 55% das páginas
> - Termos únicos no índice ≥ 50.000
> - `python -m pytest tests/ -v` → 188 passed

---

### Referência rápida

| Comando | Quando usar |
|---------|-------------|
| `python main.py clean --all --yes` | Começar do zero |
| `python main.py crawl --max-pages N` | Iniciar/retomar coleta |
| `python main.py stats` | Ver progresso |
| `python main.py inspect` | Análise detalhada do banco |
| `python main.py browse --search "rtx"` | Buscar produtos |
| `python main.py index build` | Construir índice BM25 |
| `python main.py index search "query"` | Buscar no índice |
| `python main.py export-html` | Gerar/atualizar index.jsonl |
| `python -m pytest tests/ -v` | Rodar suite de testes |

---

## Informações do Projeto

**Disciplina:** Recuperação de Informação
**Fases:** 1 — Coletor | 2 — Representação/Indexação
**Linguagem:** Python 3.11+
