# 🕷️ Hardware Crawler

Coletor de páginas web (web crawler) especializado em e-commerces brasileiros de hardware e informática. Desenvolvido para a disciplina de Recuperação de Informação.

## Índice

1. [Visão Geral](#-visão-geral)
2. [Instalação](#-instalação)
3. [Guia Rápido](#-guia-rápido)
4. [Comandos CLI](#-comandos-cli)
5. [Como Usar](#-como-usar)
6. [Configuração](#-configuração)
7. [Arquitetura](#-arquitetura)
8. [Como Funciona](#-como-funciona)
9. [Banco de Dados](#-banco-de-dados)
10. [Performance](#-performance)
11. [Limitações Técnicas](#-limitações-técnicas)
12. [Troubleshooting](#-troubleshooting)

---

## 📋 Visão Geral

### O Que Faz

O Hardware Crawler coleta automaticamente páginas de lojas de hardware brasileiras, extraindo:

- **Páginas HTML completas** para indexação
- **Informações de produtos** (nome, preço, categoria)
- **Links entre páginas** (grafo de navegação)
- **Metadados** (timestamps, domínios, status HTTP)

### Lojas Suportadas

| Loja | Domínio | Status |
|------|---------|--------|
| **Kabum** | kabum.com.br | ✅ Totalmente suportado |
| **Amazon Brasil** | amazon.com.br | ✅ Totalmente suportado |
| **Mercado Livre** | mercadolivre.com.br | ⚠️ Parcial (proteção anti-bot) |

> **Nota**: O Mercado Livre retorna páginas de verificação para alguns acessos. O crawler detecta e filtra essas páginas automaticamente.

### Características

- ✅ **Assíncrono**: Requisições paralelas com aiohttp
- ✅ **Respeitoso**: Segue robots.txt e delays por domínio
- ✅ **Persistente**: Salva em SQLite, permite retomada
- ✅ **Filtro de Hardware**: Identifica produtos de informática
- ✅ **Monitoramento**: Métricas em tempo real (CPU, RAM, NET)

---

## 📦 Instalação

### Requisitos

- Python 3.11 ou superior
- ~2GB de espaço em disco (para banco de dados)

### Passos

```bash
# 1. Clonar o repositório
git clone <url-do-repo>
cd Python-WebCrawler

# 2. Criar ambiente virtual
python -m venv venv

# 3. Ativar ambiente virtual
source venv/bin/activate      # Linux/Mac
# ou
venv\Scripts\activate         # Windows

# 4. Instalar dependências
pip install -r requirements.txt
```

### Verificar Instalação

```bash
python main.py --help
```

---

## 🚀 Guia Rápido

### Teste Rápido (20 páginas)

```bash
python main.py crawl --max-pages 20 --no-resume
```

### Coleta Completa (50k+ páginas)

```bash
python main.py crawl --max-pages 60000
```

### Ver Estatísticas

```bash
python main.py stats
```

### Explorar Dados

```bash
python main.py browse --search "rtx 4090"
```

---

## 🖥️ Comandos CLI

O crawler é controlado via linha de comando. Todos os comandos usam `python main.py <comando>`.

### Tabela de Comandos

| Comando | Descrição |
|---------|-----------|
| `crawl` | Inicia ou retoma coleta de páginas |
| `stats` | Mostra estatísticas resumidas |
| `inspect` | Inspeciona banco de dados em detalhes |
| `browse` | Navega e busca produtos no banco |
| `analyze-products` | Analisa qualidade dos produtos coletados |
| `export` | Exporta dados para CSV ou JSON |
| `seeds` | Lista URLs seed configuradas |
| `categories` | Lista categorias de hardware monitoradas |
| `clear` | Remove todos os dados coletados |
| `version` | Mostra versão do crawler |

### Opções do Comando `crawl`

```bash
python main.py crawl [OPTIONS]

Opções:
  --max-pages, -n     Número máximo de páginas (padrão: 60000)
  --max-depth, -d     Profundidade máxima de links (padrão: 15)
  --concurrency, -c   Requisições simultâneas (padrão: 25)
  --delay             Delay entre requisições em segundos (padrão: 0.2)
  --stores, -s        Lojas específicas (ex: "kabum,amazon")
  --resume/--no-resume Retomar coleta anterior (padrão: resume)
```

### Opções do Comando `browse`

```bash
python main.py browse [OPTIONS]

Opções:
  --limit, -l         Quantidade de itens (padrão: 20)
  --offset, -o        Pular N itens para paginação
  --search, -s        Buscar por nome do produto
  --domain, -d        Filtrar por domínio
  --min-price         Preço mínimo
  --max-price         Preço máximo
  --url, -u           Mostrar URLs completas
  --products/--pages  Mostrar produtos ou páginas
```

---

## 📖 Como Usar

### 1. Verificar Configuração

Antes de iniciar, verifique as URLs seed configuradas:

```bash
python main.py seeds
```

Resultado: Tabela com ~74 URLs das 3 lojas.

### 2. Fazer Teste Inicial

Valide que tudo funciona com um teste pequeno:

```bash
python main.py crawl --max-pages 100 --no-resume
```

Observe:
- Barra de progresso com métricas (CPU, RAM, NET)
- Resumo final com páginas coletadas e erros
- Tempo total e velocidade

### 3. Executar Coleta Completa

Para coleta grande:

```bash
python main.py crawl --max-pages 60000
```

**Notas:**
- Tempo estimado: ~4 horas para 50k páginas
- Use `Ctrl+C` para interromper a qualquer momento
- A coleta pode ser retomada com `--resume` (padrão)

### 4. Monitorar Progresso

Durante a coleta, você verá:

```
⠹ Coletando páginas... ━━━━━━━━━━━╸━━━━  39% • 19,685/50,000 1:18:36 • CPU: 10% | RAM: 50% | NET: 1366.9MB
```

A qualquer momento, abra outro terminal e use:

```bash
python main.py stats
```

### 5. Inspecionar Resultados

Após a coleta, analise os dados:

```bash
# Visão geral detalhada
python main.py inspect --limit 20

# Buscar produtos específicos
python main.py browse --search "placa de video"

# Filtrar por loja
python main.py browse --domain kabum --limit 50

# Filtrar por preço
python main.py browse --min-price 1000 --max-price 5000

# Ver páginas (não produtos)
python main.py browse --pages
```

### 6. Analisar Qualidade

O Mercado Livre é um marketplace generalista, então alguns produtos não são de hardware. Para ver a distribuição:

```bash
python main.py analyze-products
```

Resultado:
```
         Classificação de Produtos         
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┓
┃ Categoria          ┃ Quantidade ┃     % ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━┩
│ ✓ Hardware válido  │      3,029 │ 24.1% │
│ ✗ Não-hardware     │          0 │  0.0% │
│ ? Não classificado │     10,681 │ 75.9% │
└────────────────────┴────────────┴───────┘
```

> O crawler possui filtro de hardware que impede produtos claramente não-relacionados (celulares, carros, roupas) de serem salvos.

### 7. Exportar Dados

Para usar os dados em outras ferramentas:

```bash
# Exportar para CSV
python main.py export --format csv --output ./dados

# Exportar para JSON
python main.py export --format json --output ./dados
```

Arquivos gerados:
- `dados/pages.csv` - Todas as páginas coletadas
- `dados/products.csv` - Produtos com preços extraídos

### 8. Retomar Coleta Interrompida

Se a coleta foi interrompida:

```bash
# Retoma de onde parou (padrão)
python main.py crawl --max-pages 60000

# Ou explicitamente
python main.py crawl --max-pages 60000 --resume
```

### 9. Limpar e Recomeçar

Para uma coleta do zero:

```bash
# Remove banco de dados
python main.py clear --yes

# Inicia nova coleta
python main.py crawl --max-pages 60000 --no-resume
```

---

## ⚙️ Configuração

Toda a configuração está no arquivo `config.py`.

### Parâmetros Principais

```python
@dataclass
class CrawlerConfig:
    max_pages: int = 60000              # Meta de páginas
    max_depth: int = 15                 # Profundidade máxima de links
    max_concurrent_requests: int = 25   # Requisições simultâneas
    max_concurrent_per_domain: int = 6  # Por domínio
    default_delay: float = 0.2          # Delay entre requisições (s)
    request_timeout: int = 30           # Timeout por requisição (s)
    respect_robots_txt: bool = True     # Seguir robots.txt
```

### Configurar uma Loja

Cada loja é configurada com `StoreConfig`:

```python
STORES = {
    "kabum": StoreConfig(
        name="Kabum",
        domain="kabum.com.br",
        enabled=True,
        seed_urls=[
            "https://www.kabum.com.br/hardware",
            "https://www.kabum.com.br/hardware/placa-de-video-vga",
            # ... mais URLs
        ],
        request_delay=0.2,
        product_patterns=[
            r"/produto/\d+",        # Regex para URLs de produto
        ],
        ignore_patterns=[
            r"/carrinho",           # URLs a ignorar
            r"/login",
        ],
    ),
}
```

### Adicionar Nova Loja

1. Abra `config.py`
2. Adicione uma nova entrada no dicionário `STORES`:

```python
"nova_loja": StoreConfig(
    name="Nova Loja",
    domain="novaloja.com.br",
    enabled=True,
    seed_urls=[
        "https://www.novaloja.com.br/hardware",
    ],
    request_delay=0.5,  # Ajuste conforme necessário
    product_patterns=[
        r"/produto/[a-z0-9-]+",
    ],
    ignore_patterns=[
        r"/login",
        r"/carrinho",
    ],
),
```

3. Teste com poucas páginas:

```bash
python main.py crawl --stores nova_loja --max-pages 50
```

### Desabilitar uma Loja

```python
"kabum": StoreConfig(
    ...
    enabled=False,  # Não será coletada
),
```

### Categorias de Hardware

As categorias são usadas para classificar produtos. Edite `HARDWARE_CATEGORIES` em `config.py`:

```python
HARDWARE_CATEGORIES = {
    "gpu": ["placa de vídeo", "rtx", "gtx", "radeon", "geforce"],
    "cpu": ["processador", "ryzen", "intel core", "amd"],
    "ram": ["memória ram", "ddr4", "ddr5"],
    # ...
}
```

---

## 🏗️ Arquitetura

### Estrutura de Diretórios

```
Python-WebCrawler/
├── main.py                 # CLI principal (Typer)
├── config.py               # Configurações e seeds
├── requirements.txt        # Dependências Python
├── README.md               # Esta documentação
├── RELATORIO.md            # Relatório técnico
│
├── crawler/                # Módulo de coleta
│   ├── __init__.py
│   ├── spider.py          # Spider principal (orquestra tudo)
│   ├── frontier.py        # Fila de URLs com prioridade
│   └── politeness.py      # Respeito a robots.txt e delays
│
├── storage/                # Módulo de persistência
│   ├── __init__.py
│   ├── models.py          # Modelos SQLAlchemy (ORM)
│   └── database.py        # Operações de banco de dados
│
├── extractors/             # Módulo de extração
│   ├── __init__.py
│   ├── product_detector.py # Detecta páginas de produto
│   └── price_extractor.py  # Extrai preços do HTML
│
└── data/                   # Dados gerados
    └── crawler.db         # Banco SQLite
```

### Componentes Principais

| Componente | Arquivo | Responsabilidade |
|------------|---------|-----------------|
| **Spider** | `crawler/spider.py` | Orquestra coleta, faz requisições HTTP, gerencia concorrência |
| **Frontier** | `crawler/frontier.py` | Fila de URLs com priorização, deduplicação |
| **Politeness** | `crawler/politeness.py` | Respeita robots.txt, gerencia delays por domínio |
| **ProductDetector** | `extractors/product_detector.py` | Identifica páginas de produto, extrai info, filtra hardware |
| **PriceExtractor** | `extractors/price_extractor.py` | Extrai preços de HTML (JSON-LD, meta tags, regex) |
| **Database** | `storage/database.py` | CRUD assíncrono com SQLite, retry automático |
| **Models** | `storage/models.py` | Definição de tabelas (SQLAlchemy ORM) |

### Fluxo de Execução

```
1. CLI (main.py)
   └── Inicializa Spider com configurações

2. Spider
   ├── Carrega seeds da config
   ├── Adiciona seeds à Frontier
   └── Loop principal:
       ├── Pega próximas URLs da Frontier
       ├── Verifica Politeness (robots.txt, delay)
       ├── Faz requisição HTTP (aiohttp)
       ├── Salva página no Database
       ├── Detecta se é produto (ProductDetector)
       ├── Extrai preço se for produto (PriceExtractor)
       ├── Extrai links da página
       ├── Adiciona novos links à Frontier
       └── Atualiza progresso

3. Ao finalizar ou Ctrl+C:
   └── Salva estatísticas finais
```

---

## 🔧 Como Funciona

### Estratégia de Coleta: BFS com Priorização

O crawler usa **Busca em Largura (BFS)** modificada com fila de prioridade:

| Tipo de URL | Prioridade | Descrição |
|-------------|------------|-----------|
| Produtos | 100 | URLs que casam com `product_patterns` |
| Seeds | 90 | URLs iniciais configuradas |
| Listagens | 80 | Páginas de categoria, busca |
| Outras | 50 | Qualquer outra URL do domínio |

### Deduplicação de URLs

Para evitar visitar a mesma página duas vezes:

1. **Normalização**: URL convertida para lowercase, fragmentos removidos
2. **Hash**: SHA-256 da URL normalizada
3. **Verificação**: Hash comparado com banco antes de adicionar à fila

### Politeness (Boas Práticas)

O crawler respeita as regras de cada site:

- **robots.txt**: Parseado e respeitado para cada domínio
- **Crawl-delay**: Respeitado quando especificado (nenhuma loja atual define)
- **Delay por domínio**: 0.2s entre requisições ao mesmo domínio
- **User-Agent**: Identificado como bot educacional
- **Concorrência por domínio**: Máximo 6 conexões simultâneas por domínio

### Detecção de Produtos

O `ProductDetector` usa múltiplas heurísticas:

1. **JSON-LD**: Busca schema.org `@type: "Product"`
2. **OpenGraph**: Verifica `og:type` = "product"
3. **Padrões de URL**: Regex configurados em `product_patterns`
4. **Elementos HTML**: Botões de compra, elementos de preço

### Filtro de Hardware

Produtos são filtrados para incluir apenas itens de informática:

**Incluídos** (exemplos de keywords):
- Placa de vídeo, RTX, GTX, Radeon
- Processador, Ryzen, Intel Core
- Memória RAM, DDR4, DDR5
- SSD, NVMe, HD
- Monitor gamer, teclado mecânico

**Excluídos** (exemplos de keywords):
- Celular, iPhone, smartphone
- Carro, moto, veículo
- Roupa, sapato, maquiagem
- Eletrodomésticos

### Extração de Preços

O `PriceExtractor` tenta extrair preços em ordem:

1. **JSON-LD**: `offers.price`
2. **Meta tags**: `product:price:amount`
3. **Seletores CSS**: Específicos por loja
4. **Regex**: `R\$ ?[\d.,]+`

### Retry com Backoff

Para evitar erros de "database is locked":

- Operações de escrita têm retry automático
- 5 tentativas com backoff exponencial
- Delay base: 0.2s, máximo: 5s

---

## 🗃️ Banco de Dados

### Localização

O banco SQLite fica em `data/crawler.db`.

### Tabelas

| Tabela | Descrição |
|--------|-----------|
| `pages` | Todas as páginas coletadas (URL, HTML, título, domínio) |
| `products` | Produtos extraídos (nome, preço, categoria, SKU) |
| `price_history` | Histórico de preços por produto |
| `links` | Grafo de links entre páginas |
| `frontier` | URLs pendentes para coleta |
| `crawl_stats` | Estatísticas de execução |

### Consultar Diretamente

```bash
sqlite3 data/crawler.db
```

### Consultas Úteis

```sql
-- Total de páginas por domínio
SELECT domain, COUNT(*) as total 
FROM pages 
GROUP BY domain 
ORDER BY total DESC;

-- Produtos com preço
SELECT name, price, store 
FROM products 
WHERE price IS NOT NULL 
ORDER BY price DESC 
LIMIT 20;

-- Distribuição de categorias
SELECT category, COUNT(*) as total 
FROM products 
WHERE category IS NOT NULL 
GROUP BY category 
ORDER BY total DESC;

-- Páginas com erro
SELECT url, status_code 
FROM pages 
WHERE status_code != 200 
LIMIT 50;
```

### Otimizações SQLite

O banco usa:

- **WAL mode**: Permite leituras e escritas simultâneas
- **busy_timeout=60000**: Espera até 60s em caso de lock
- **cache_size=-64000**: 64MB de cache em memória

---

## ⚡ Performance

### Métricas Atuais

| Métrica | Valor |
|---------|-------|
| Velocidade | ~244 páginas/min |
| Delay por domínio | 0.2s |
| Concorrência total | 25 requisições |
| Concorrência por domínio | 6 requisições |
| Retry de banco | 5 tentativas |

### Tempo Estimado

| Meta | Tempo Estimado |
|------|---------------|
| 1.000 páginas | ~4 min |
| 10.000 páginas | ~40 min |
| 50.000 páginas | ~3.5 horas |

### Histórico de Otimização

| Versão | Velocidade | Mudança |
|--------|------------|---------|
| v1 | ~40 pág/min | Lock global, delay 2.0s |
| v2 | ~84 pág/min | Lock por domínio |
| v3 | ~130 pág/min | Delay 0.3s, concorrência 20 |
| v4 | ~244 pág/min | Delay 0.2s, retry com backoff |

### Ajustar Performance

Para aumentar velocidade (com mais risco):

```python
# Em config.py
max_concurrent_requests: int = 40   # Mais conexões
max_concurrent_per_domain: int = 10
default_delay: float = 0.1          # Menos delay
```

Para diminuir velocidade (mais seguro):

```python
# Em config.py
max_concurrent_requests: int = 10
max_concurrent_per_domain: int = 3
default_delay: float = 0.5
```

---

## ⚠️ Limitações Técnicas

### Lojas com Problemas

| Loja | Problema | Detalhes |
|------|----------|----------|
| **Mercado Livre** | Anti-bot | Retorna páginas de "suspicious_traffic" (verificação de segurança) em vez do conteúdo real. Páginas coletadas são detectadas e filtradas automaticamente. |
| **Magazine Luiza** | SPA | Site renderizado via React. HTML retornado tem apenas 17KB e 6 links. Necessitaria headless browser (Playwright/Selenium). |
| **Pichau** | Cloudflare | HTTP 403 Forbidden. Proteção Cloudflare ativa. Bloqueia requisições automatizadas. |
| **Terabyte Shop** | Cloudflare | HTTP 403 Forbidden. Proteção Cloudflare ativa. Bloqueia requisições automatizadas. |

> **Nota**: O crawler detecta automaticamente páginas de bloqueio/verificação e não as processa como produtos válidos.

### Por que não usar Headless Browser?

1. **Performance**: 10-50x mais lento que HTTP puro
2. **Recursos**: Chromium consome ~300MB de RAM
3. **Complexidade**: Dependências pesadas
4. **Escopo**: Fora do escopo para esta fase do trabalho

### Por que não bypassar Cloudflare?

1. **Ético**: Contornar proteções viola boas práticas
2. **Legal**: Pode violar Termos de Serviço
3. **Instável**: Soluções de bypass quebram frequentemente

---

## 🔧 Troubleshooting

### Erros Comuns

#### "python: command not found"

Use o caminho completo do venv:

```bash
./venv/bin/python main.py crawl
```

Ou ative o ambiente virtual:

```bash
source venv/bin/activate
python main.py crawl
```

#### "database is locked"

O banco SQLite tem limite de escritas concorrentes. O crawler tem retry automático, mas se persistir:

1. Reduza concorrência: `--concurrency 15`
2. Feche outras conexões ao banco
3. Limpe e recomece: `python main.py clear --yes`

#### Muitos erros 403

Seu IP pode estar sendo bloqueado. Opções:

1. Aumente o delay: `--delay 1.0`
2. Espere algumas horas
3. Reinicie o roteador (trocar IP)

#### Coleta muito lenta

Verifique:

1. Conexão de internet
2. Se CPU/RAM estão saturados
3. Se alguma loja está throttling

Aumente concorrência: `--concurrency 40`

### Verificar Status do Banco

```bash
# Ver se banco existe
ls -la data/

# Verificar integridade
sqlite3 data/crawler.db "PRAGMA integrity_check;"
```

### Logs de Debug

Para ver mais detalhes durante a coleta, você pode ver os warnings no console. O crawler imprime erros de extração em tempo real.

---

## 📝 Arquivos de Saída

### CSV Exportado

**pages.csv:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | int | ID único |
| url | str | URL completa |
| title | str | Título da página |
| domain | str | Domínio (ex: kabum.com.br) |
| status_code | int | Código HTTP |
| is_product | bool | Se é página de produto |
| crawled_at | datetime | Data/hora da coleta |

**products.csv:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | int | ID único |
| name | str | Nome do produto |
| price | float | Preço em R$ |
| category | str | Categoria (gpu, cpu, ram, etc) |
| store | str | Loja de origem |
| brand | str | Marca (se detectada) |
| url | str | URL da página |

---

## 👤 Informações do Projeto

**Disciplina:** Recuperação de Informação  
**Fase:** 1 - Coletor  
**Linguagem:** Python 3.11+  
**Licença:** MIT - Uso educacional

### Dependências Principais

- `aiohttp` - Cliente HTTP assíncrono
- `beautifulsoup4` - Parser HTML
- `sqlalchemy` - ORM para banco de dados
- `typer` - CLI moderna
- `rich` - Interface bonita no terminal
- `psutil` - Monitoramento de sistema
