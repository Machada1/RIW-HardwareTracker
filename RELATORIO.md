# Relatório — Fases 1 e 2: Coletor e Representação

**Disciplina:** Recuperação de Informação
**Fases:** 1 — Coletor (8 pts) + 2 — Representação/Indexação (8 pts)

---

## 1. Introdução

Este relatório descreve a implementação de um **coletor web (crawler)** especializado em páginas de hardware de e-commerce brasileiro, seguido de um **motor de busca BM25** sobre os dados coletados. O sistema é composto por dois módulos principais:

- **Fase 1:** coleta assíncrona de páginas, extração de produtos e preços, persistência em SQLite e no filesystem
- **Fase 2:** pipeline NLP para português, índice invertido shardado em JSON, busca BM25 ranqueada

### 1.1 Lojas Alvo

| Loja | Domínio | Status | Observação |
|------|---------|--------|------------|
| Kabum | `kabum.com.br` | Funcional | ~849 páginas no teste de 2k |
| Mercado Livre | `mercadolivre.com.br` | Funcional | ~826 páginas; anti-bot parcial |
| Amazon Brasil | `amazon.com.br` | Funcional | ~325 páginas; rate-limit frequente |
| Magazine Luiza | `magazineluiza.com.br` | Desabilitado | SPA React — HTML sem conteúdo |
| Pichau / Terabyte | — | Inviável | Cloudflare WAF — HTTP 403 imediato |

### 1.2 Meta de Coleta

A meta do trabalho é ≥ 50.000 páginas. A infraestrutura está preparada: ~130 seeds distribuídas, profundidade máxima 20, balanceamento por domínio. Uma coleta de 2.000 páginas foi realizada para validação; a coleta completa requer execução contínua de ~5–6 horas.

---

## 2. Arquitetura do Sistema

### 2.1 Visão Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                       CLI (main.py)                             │
│                   Typer + Rich (terminal UI)                    │
├──────────────────┬──────────────────┬───────────────────────────┤
│    FASE 1        │    EXTRAÇÃO       │       FASE 2              │
│  Spider async    │  ProductDetector  │  IndexBuilder + Searcher  │
│  aiohttp + BFS   │  PriceExtractor   │  BM25 + RSLP stemmer      │
├──────────────────┼──────────────────┼───────────────────────────┤
│  URLFrontier     │  Politeness       │  TextProcessor            │
│  (prioridade +   │  (robots.txt +    │  (stopwords PT-BR +       │
│   balanceamento) │   rate-limit)     │   tokenização regex)      │
├──────────────────┴──────────────────┴───────────────────────────┤
│          Storage: SQLite/WAL (SQLAlchemy async)                  │
│    data/crawler.db  |  data/html_pages/  |  data/index/          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Componentes

| Componente | Arquivo | Responsabilidade |
|------------|---------|-----------------|
| Spider | `crawler/spider.py` | Orquestra coleta async, salva HTML em disco e DB |
| URLFrontier | `crawler/frontier.py` | Fila BFS priorizada, deduplicação SHA-256, balanceamento por domínio |
| Politeness | `crawler/politeness.py` | robots.txt por domínio, rate limiting com asyncio Lock |
| ProductDetector | `extractors/product_detector.py` | JSON-LD, OpenGraph, URL patterns; filtra listagens |
| PriceExtractor | `extractors/price_extractor.py` | JSON-LD → meta tags → CSS selectors → regex R$ |
| Database | `storage/database.py` | SQLAlchemy async, WAL mode, retry em deadlock |
| TextProcessor | `indexer/text_processor.py` | Lowercasing → tokenização → stopwords → RSLP |
| IndexBuilder | `indexer/builder.py` | Índice invertido shardado em 256 arquivos JSON |
| Searcher | `indexer/searcher.py` | BM25 com cache de shards, filtro por domínio |

---

## 3. Fase 1 — Coleta

### 3.1 Estratégia: BFS com Priorização

A coleta usa Busca em Largura com fila de prioridade. Cada URL recebe uma pontuação que determina a ordem de visita:

| Tipo de página | Prioridade | Exemplo |
|----------------|-----------|---------|
| Páginas de produto | 100 | `/produto/12345/rtx-4060` |
| Seeds iniciais | 90 | `kabum.com.br/hardware` |
| Páginas de listagem/categoria | 80 | `/hardware/placa-de-video` |
| Outras | ≤ 50 | qualquer outro link |

Essa estratégia garante que páginas de produto (com dados úteis) sejam visitadas antes de páginas de navegação.

### 3.2 Processamento Assíncrono

- **aiohttp** com até 25 requisições concorrentes totais e máximo 6 por domínio
- Delay mínimo de **0,2 segundos** entre requisições ao mesmo domínio (asyncio Lock por domínio)
- Timeout de 30s por requisição; retry com backoff exponencial (3 tentativas)

**Por que aiohttp e não requests?** Crawling é I/O bound — enquanto a conexão aguarda a resposta, a CPU fica ociosa com `requests` síncrono. Com `aiohttp` async, 25 requisições concorrem no mesmo thread sem overhead de threads/processos, resultando em ~10–25× mais throughput para o mesmo hardware.

### 3.3 Balanceamento de Domínio

O método `pop_batch` distribui o batch entre domínios proporcionalmente:
cada domínio contribui `min(disponível, tamanho_batch // num_dominios)` itens. Sem isso, o Mercado Livre (com ~130 seeds) dominaria 100% dos primeiros batches, deixando Kabum e Amazon sem coleta inicial.

### 3.4 Normalização e Deduplicação de URLs

1. Lowercase do scheme e host; remoção de fragmento (`#`)
2. Remoção de parâmetros de tracking: `utm_*`, `fbclid`, `gclid`, `ref`, `src`
3. **Amazon:** remoção de segmentos `/ref=...` do path (não são query params normais)
4. Ordenação dos query params restantes (para que `?a=1&b=2` e `?b=2&a=1` sejam iguais)
5. Hash SHA-256 do URL normalizado → verificado em set em memória

**Por que SHA-256?** O set de hashes ocupa ~64 bytes por URL independentemente do comprimento. Um set de 50.000 URLs ocupa ~3 MB; as strings originais seriam ~5–10 MB.

### 3.5 Politeness

- robots.txt parseado e cacheado por domínio
- User-Agent identificado como bot acadêmico
- Rate limiting: asyncio Lock por domínio garante o delay mínimo entre requisições ao mesmo site

### 3.6 Persistência Dual

Cada página é salva em dois lugares durante o crawl:
1. **SQLite** (`data/crawler.db`): HTML + texto extraído + metadados → usado pelo indexador
2. **Arquivo HTML** (`data/html_pages/{domain}/{id:06d}.html`): cópia raw para processamento offline

**Por que SQLite com WAL?** Zero configuração. O modo WAL permite leituras concorrentes enquanto o crawler escreve — sem WAL, o comando `stats` durante uma coleta retornaria erro de lock.

### 3.7 Extração de Produtos e Preços

**Detecção de produto** em cascata de confiança:
1. URL bate com `product_patterns` da loja (`/produto/\d+`, `/dp/[A-Z0-9]+`)
2. JSON-LD `@type: Product` (Schema.org)
3. OpenGraph `og:type = "product"`

**Filtro de listagem** aplicado antes da análise HTML: se a URL bate com `LISTING_URL_PATTERNS` (ex: `/busca/`, `/s?k=`, `/categoria/`), a página é rejeitada — evita extrair como produto o primeiro item de uma página de resultados.

**Extração de preço** em cascata:
1. JSON-LD `offers.price`
2. Meta tag `product:price:amount`
3. Seletores CSS por loja (`h4.finalPrice` no Kabum, `.andes-money-amount__fraction` no ML)
4. Regex fallback: apenas padrões com prefixo `R$` obrigatório; mínimo R$50

---

## 4. Fase 2 — Representação e Indexação

### 4.1 Pipeline de Processamento de Texto

Implementado em `indexer/text_processor.py`:

```
texto bruto (campo text_content do SQLite)
    ↓ lowercasing
    ↓ tokenização regex (\b\w+\b)
    ↓ filtro de comprimento: descarta tokens < 2 ou > 40 caracteres
    ↓ tokens numéricos com > 8 dígitos descartados (SKUs, timestamps)
    ↓ normalização Unicode (NFD → strip diacríticos)
    ↓ remoção de stopwords PT-BR (~120 termos)
    ↓ stemming RSLP ou suffix-stripping (fallback automático)
    → lista de stems indexáveis
```

**Stopwords customizadas para e-commerce:** além das stopwords NLTK português, foram adicionadas palavras de boilerplate de lojas online: `carrinho`, `frete`, `parcelamento`, `pix`, `boleto`, `cadastro`, `login`, `adicionar`, `comparar`, etc.

**Por que RSLP e não Porter?** Porter foi desenvolvido para inglês. O RSLP (Orengo & Huyck, 2001) é o stemmer de referência para português. O sistema usa fallback automático para suffix-stripping heurístico quando os dados NLTK não estão disponíveis.

**Boost de título:** o título é concatenado 3× antes do corpo antes do processamento, aumentando o peso dos termos do título no TF sem modificar a fórmula BM25.

### 4.2 Índice Invertido

Implementado em `indexer/builder.py`. Estrutura em disco, sem banco de dados:

```
data/index/
  meta.json     → {total_docs, total_terms, avg_dl, stemmer, build_time, ...}
  vocab.json    → {stem: {id: int, df: int, raw: str}}
  docs.json     → {doc_id: {url, title, domain, dl, is_product, category}}
  postings/
    00.json     → {term_id: [[doc_id, tf], ...]} para term_id % 256 == 0
    ...
    ff.json     → idem para term_id % 256 == 255
```

**Por que JSON shardado e não SQLite para o índice?** O acesso ao índice é direto: dada uma query, carregue os shards dos termos e some os scores. Não há joins, filtragens ou transações. SQLite adicionaria overhead de ACID e B-tree para um padrão de acesso que é essencialmente "leia esta lista do arquivo". Os 256 shards mantêm cada arquivo em dezenas de KB, carregados sob demanda com cache LRU.

### 4.3 BM25

Fórmula implementada em `indexer/searcher.py`:

```
score(q,d) = Σ_t  IDF(t) × tf(t,d)×(k1+1) / (tf(t,d) + k1×(1 − b + b×dl/avgdl))

IDF(t) = log((N − df + 0.5) / (df + 0.5) + 1)   [IDF suavizado]

Hiperparâmetros: k1 = 1.5,  b = 0.75
```

**Por que BM25 e não TF-IDF?** TF-IDF não normaliza pelo comprimento do documento. Um documento de 10.000 tokens sobre RTX pontua mais que um de 500 tokens com a mesma densidade de termos, mesmo sendo o segundo mais focado. O BM25 corrige isso com `dl/avgdl`. O `b=0.75` é o valor padrão de Robertson et al. (TREC-3, 1994), validado empiricamente em centenas de coleções.

---

## 5. Bugs Encontrados e Corrigidos

### Bug 1 — Falso positivo de preço via `rgba()`

**Sintoma:** Produtos com preço `R$ 65,13` extraídos de páginas sem preço real.
**Causa:** Regex capturava `rgba(65,137,230,.15)` (cor CSS) como preço.
**Correção:** Prefixo `R\$` obrigatório em todos os padrões; remoção de `rgba?(...)` antes da busca. **Arquivo:** `extractors/price_extractor.py`

---

### Bug 2 — `R$ 200.000,00` capturado como `R$ 200`

**Sintoma:** Teste `test_above_maximum_rejected` falhava — valor acima de R$100k retornava R$200.
**Causa:** O Padrão 1 rejeitava `200.000,00` corretamente (> R$100k), mas o Padrão 2 capturava os dígitos `200` antes do ponto de milhar.
**Correção:** Lookahead negativo `(?![0-9,.])` em ambos os padrões. **Arquivo:** `extractors/price_extractor.py:32-35`

---

### Bug 3 — Smart TV categorizada como `hdd`

**Sintoma:** "Smart TV 43 Full HD" era classificada como disco rígido.
**Causa:** Keyword `"hd "` (com espaço) batia em "Full HD".
**Correção:** Substituído por `"hd sata"`, `"hd interno"`, `"hd externo"`. **Arquivo:** `extractors/product_detector.py`

---

### Bug 4 — Produto extraído de página de listagem

**Sintoma:** Kabum retornava produtos com nome do primeiro item de páginas de categoria.
**Causa:** JSON-LD de listagens inclui objetos `Product` aninhados.
**Correção:** `LISTING_URL_PATTERNS` verificados antes de qualquer análise HTML. **Arquivo:** `extractors/product_detector.py`

---

### Bug 5 — Amazon: duplicatas por `/ref=` no path

**Sintoma:** Mesmos produtos indexados duas vezes com URLs diferentes.
**Causa:** Amazon usa `/ref=...` no path, não como query param — a remoção padrão não funcionava.
**Correção:** `re.sub(r'/ref=[^/]*', '', path)` no normalize_url. **Arquivo:** `crawler/frontier.py`

---

### Bug 6 — ML dominando os batches

**Sintoma:** Kabum e Amazon sem coleta nas primeiras centenas de páginas.
**Causa:** `pop_batch` sem balanceamento por domínio.
**Correção:** Distribuição proporcional: cada domínio contribui `n // num_dominios` itens. **Arquivo:** `crawler/frontier.py`

---

### Bug 7 — Domain filtering: domínios fora do escopo (crítico)

**Sintoma:** Após coleta de 2.000 páginas, `stats` mostrava `amazon.com` (EUA), `mercadolivre.com` (global) e `aboutamazon.com.br`.

**Causa:** `get_store_for_url` usava correspondência bidirecional:
```python
if store.domain in domain or domain in store.domain:  # BUG
```
- `"amazon.com" in "amazon.com.br"` → True (EUA passava como Brasil)
- `"mercadolivre.com" in "mercadolivre.com.br"` → True
- `"amazon.com.br" in "aboutamazon.com.br"` → True (blog corporativo)

**Correção:** Igualdade exata após `tldextract`:
```python
if domain == store.domain:  # CORRETO
```
**Impacto:** 525 MB de dados contaminados descartados; coleta reiniciada. **Arquivo:** `crawler/frontier.py:107`

---

### Bug 8 — `ZeroDivisionError` em `analyze-products`

**Sintoma:** Crash com banco vazio.
**Causa:** `hardware_count / total * 100` sem guard para `total == 0`.
**Correção:** Early return quando `total == 0`. **Arquivo:** `main.py:976`

---

### Bug 9 — Near-duplicatas por `?facet_filters=` e `/sspa/click`

**Sintoma:** Mesma página de categoria do Kabum aparecia 7–8 vezes na busca. 71 URLs `sspa/click` da Amazon no banco.
**Causa:** Kabum usa `?facet_filters=<base64>` para filtros (mesmo conteúdo, URL diferente). Amazon usa `/sspa/click` para rastrear anúncios — não são produtos.
**Correção:** Adicionados aos `ignore_patterns`: `r'[?&]facet_filters='` (Kabum), `r'/sspa/click'` (Amazon), `r'/ofertas\?'` (ML). **Arquivo:** `config.py`

---

## 6. Decisões de Implementação

| Decisão | Alternativa avaliada | Motivo da escolha |
|---------|---------------------|-------------------|
| `aiohttp` async | `requests` síncrono | Crawling é I/O bound — 25 conexões sem overhead de threads |
| SQLite com WAL | PostgreSQL | Zero configuração; WAL permite leituras durante o crawl |
| JSON shardado (256 shards) | SQLite para postings | Acesso direto sem ORM; sem overhead de ACID |
| BM25 (k1=1.5, b=0.75) | TF-IDF puro | Normaliza pelo comprimento do documento |
| RSLP stemmer | Porter stemmer | RSLP desenvolvido especificamente para português |
| Typer + Rich | argparse | Tabelas e progress bars prontos; menos boilerplate |
| SHA-256 para dedup | Comparação de string | 64 bytes/URL fixo; 50k hashes = ~3 MB |

---

## 7. Suite de Testes

O projeto possui **188 testes automatizados** em 8 arquivos, cobrindo todos os módulos:

| Arquivo | Testes | O que cobre |
|---------|--------|-------------|
| `test_config.py` | 12 | Categorias de hardware, lojas, parâmetros defaults |
| `test_frontier.py` | 37 | Normalização URL, SHA-256, balanceamento, domain filtering (regressão bugs 5, 6, 7) |
| `test_price_extractor.py` | 23 | Falso positivo RGB, lookahead negativo, JSON-LD, meta tags, limites R$50–R$100k |
| `test_product_detector.py` | 24 | Listagem vs. produto, categorias, regressão Smart TV/HDD |
| `test_text_processor.py` | 15 | Tokenização, stopwords, RSLP, unicode |
| `test_indexer.py` | 16 | Build, BM25 ranking, filtro de domínio (índice sintético) |
| `test_database.py` | 9 | CRUD assíncrono, paginação, `page_exists` |
| `test_cli.py` | 52 | Todos os subcomandos e flags via `CliRunner` |

```bash
python -m pytest tests/ -v
# 188 passed, 0 failed em ~3s
```

---

## 8. Resultados da Coleta de Validação (2.000 páginas)

Coleta realizada após correção de todos os bugs:

### 8.1 Coleta

| Métrica | Valor |
|---------|-------|
| Páginas coletadas | 2.000 |
| Páginas de produto detectadas | 1.158 (57,9%) |
| Produtos extraídos | 81 |
| Produtos com preço | 80 (98,8%) |
| Distribuição | 849 Kabum (42,4%) / 826 ML (41,3%) / 325 Amazon (16,2%) |
| Tamanho do banco | 520 MB |

> Amazon representa 16,2% por maior agressividade no rate-limiting (HTTP 429). O crawler continua após rejeições.

### 8.2 Qualidade dos Produtos

| Categoria | Quantidade | % |
|-----------|-----------|---|
| Hardware válido | 74 | 91,4% |
| Não-hardware | 0 | 0,0% |
| Não classificado | 7 | 8,6% |

### 8.3 Índice Invertido

| Métrica | Valor |
|---------|-------|
| Documentos | 2.000 |
| Termos únicos | 14.147 |
| Total de postings | 275.084 |
| Comprimento médio (tokens) | 366,2 |
| Hapax legomena (df = 1) | 7.250 (51,2%) |
| Stemmer | RSLP |
| Tempo de build | 22,2 s |

### 8.4 Exemplos de Busca BM25

```
$ python main.py index search "placa de video rtx"
#1  12.59  Placa de Vídeo NVIDIA RTX 5090, RTX 5080 no KaBuM!  kabum.com.br

$ python main.py index search "ssd nvme 1tb"
#1  16.81  SSD NVME 1tb com até 15% OFF no PIX | KaBuM!         kabum.com.br

$ python main.py index search "processador ryzen" --domain kabum.com.br
#1   8.48  Processador AMD Ryzen: Ofertas de Black Friday no KaBuM!
```

---

## 9. Armazenamento

| Tabela | Descrição |
|--------|-----------|
| `pages` | URL, HTML completo, texto extraído, domínio, profundidade, tempo de crawl |
| `products` | Nome, preço, categoria, SKU, loja, referência à página |
| `price_history` | Histórico de variação de preço por produto |
| `frontier` | URLs pendentes: prioridade, profundidade, status |
| `crawl_stats` | Métricas de execução por sessão |

Estimativas para 50.000 páginas: banco ~13–15 GB, HTMLs ~8 GB, índice ~80 MB.

---

## 10. Lojas Não Suportadas

| Loja | Problema | Detalhe |
|------|----------|---------|
| Magazine Luiza | SPA React | HTML retorna shell vazio; conteúdo via JavaScript. Requereria Playwright. |
| Pichau | Cloudflare WAF | HTTP 403 imediato. Cabeçalho `CF-Ray` presente. Requereria proxy residencial. |
| Terabyte Shop | Cloudflare WAF | Mesmo comportamento do Pichau. |

---

## 11. Conclusão

### Fase 1

- Coleta assíncrona multi-loja funcionando (aiohttp + BFS + balanceamento)
- Deduplicação por SHA-256 após normalização de URL
- Extração de produtos com 91,4% de precisão e 0% de falsos não-hardware
- Taxa de preço de 98,8%; 0% de falsos positivos (RGB, etc.)
- Persistência dual: SQLite + arquivos HTML
- 9 bugs identificados e corrigidos durante o desenvolvimento e nos testes

### Fase 2

- Pipeline NLP para português: tokenização → ~120 stopwords → RSLP
- Índice invertido shardado em JSON, sem banco externo
- BM25 implementado do zero, resultados relevantes confirmados manualmente
- 188 testes automatizados cobrindo 100% dos módulos

---

## Referências

1. Manning, C. D., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press.
2. Robertson, S. E., et al. (1994). *Okapi at TREC-3*. NIST Special Publication 500-225.
3. Orengo, V. M., & Huyck, C. (2001). *A Stemming Algorithm for the Portuguese Language*. SPIRE 2001.
4. Documentação: aiohttp, SQLAlchemy, BeautifulSoup4, NLTK, Typer, Rich.

---

**Autor:** [NOME] — **RA:** [RA]
