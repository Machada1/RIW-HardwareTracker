# 🕷️ Hardware Crawler

Coletor de páginas web para Sistema de Recuperação de Informação (RI).

**Fase 1: Coletor** - Coleta páginas de lojas de hardware brasileiras para indexação e busca.

## 🎯 Objetivo

Coletar **mais de 50.000 páginas** de produtos de hardware de e-commerces brasileiros:
- **Kabum** - Principal loja de hardware do Brasil
- **Mercado Livre** - Marketplace com milhares de vendedores
- **Amazon Brasil** - E-commerce global com amplo catálogo

---

## ⚠️ Lojas Não Suportadas (Limitações Técnicas)

Durante o desenvolvimento, foram testadas outras lojas brasileiras de hardware que **não puderam ser implementadas** devido a limitações técnicas:

| Loja | Problema | Detalhes Técnicos |
|------|----------|-------------------|
| **Magazine Luiza** | SPA (Single Page Application) | Retorna apenas 17KB de HTML e 6 links. Todo o conteúdo é renderizado via JavaScript/React. Seria necessário um headless browser (Playwright/Selenium) para funcionar. |
| **Pichau** | Cloudflare WAF | Retorna HTTP 403. Proteção Cloudflare ativa (CF-Ray header presente). Bloqueia requisições automatizadas. |
| **Terabyte Shop** | Cloudflare WAF | Retorna HTTP 403. Proteção Cloudflare ativa (CF-Ray header presente). Bloqueia requisições automatizadas. |

### Por que não usar Headless Browser?

1. **Complexidade**: Adiciona dependências pesadas (Chromium ~300MB)
2. **Performance**: 10-50x mais lento que HTTP puro
3. **Recursos**: Consome muito mais RAM e CPU
4. **Scope**: Fora do escopo para Fase 1 (foco em coleta eficiente)

### Por que não bypassar Cloudflare?

1. **Ético**: Contornar proteções anti-bot viola boas práticas
2. **Legal**: Pode violar ToS dos sites
3. **Instável**: Soluções de bypass quebram frequentemente

**Decisão**: Focar nas 3 lojas que funcionam bem (Kabum, ML, Amazon) que juntas oferecem catálogo suficiente para >50k páginas.

---

## 📦 Instalação

```bash
# 1. Clonar/entrar no diretório
cd Python-WebCrawler

# 2. Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# 3. Instalar dependências
pip install -r requirements.txt
```

---

## 🚀 Tutorial de Uso Completo

### Passo 1: Verificar Seeds Configuradas

Antes de iniciar, veja quais URLs estão configuradas:

```bash
python main.py seeds
```

**Resultado esperado:** Tabela com ~36 URLs seed das 3 lojas.

### Passo 2: Teste Rápido (Recomendado)

Faça um teste com poucas páginas para validar:

```bash
python main.py crawl --max-pages 20 --no-resume
```

**Resultado esperado:**
```
🕷️ Iniciando Coleta
Coletando de: kabum, mercadolivre, amazon
Meta: 20 páginas | Profundidade: 15

✓ 74 URLs seed adicionadas
Coletando páginas... ━━━━━━━━━━ 100% • 20/20 0:00:10

═══════════════════════════════════════════
            RESUMO DO CRAWL                
═══════════════════════════════════════════
  Tempo total                00:00:10  
  Páginas coletadas                20  
  Produtos detectados               5  
  Links descobertos               200  
```

### Passo 3: Coleta Completa (50k+ Páginas)

Para obter a pontuação máxima (8 pontos):

```bash
python main.py crawl --max-pages 60000
```

**Tempo estimado:** ~6-8 horas (otimizado para ~130-150 páginas/min).

---

## ⚡ Otimização de Performance

### Histórico de Otimização

Durante o desenvolvimento, o crawler passou por várias otimizações:

| Versão | Velocidade | Tempo p/ 50k | Mudança |
|--------|------------|--------------|---------|
| v1 (inicial) | ~40 pág/min | ~21 horas | Lock global, delay 2.0s |
| v2 | ~84 pág/min | ~10 horas | Lock por domínio, delay 0.5s |
| v3 | ~130 pág/min | ~6 horas | Delay 0.3s, concorrência 20 |
| v4 (atual) | ~186 pág/min | ~4.5 horas | Write locks serializados (fix SQLite) |

**Ganho total: 4.6x mais rápido!**

### Teste Real: 10.000 Páginas

Resultado do teste de validação:

```
═══════════════════════════════════════════
            RESUMO DO CRAWL                
═══════════════════════════════════════════
  Tempo total                 00:53:41  
  Páginas coletadas             10,009  
  Páginas com erro                 491  
  Produtos detectados            9,809  
  Links descobertos             16,610  
  Dados baixados             2636.8 MB  
  Velocidade             186.4 pág/min  
```

**Métricas:**
- Taxa de detecção de produtos: **98%**
- Taxa de extração de preços: **98%**
- Taxa de erro: **5%** (normal para sites grandes)
- Banco gerado: **2.6 GB**

### O Que Foi Otimizado

1. **Lock por domínio ao invés de global**
   - Antes: Um lock global serializava TODAS as requisições
   - Depois: Cada domínio tem seu próprio lock, permitindo paralelismo entre lojas

2. **Delay reduzido para 0.3s**
   - Verificamos os robots.txt de todas as lojas
   - Nenhuma define `Crawl-delay`, então usamos delay mínimo seguro
   - Delay seguro típico: 0.3-0.5s por domínio

3. **Concorrência otimizada para 25**
   - Balanceado entre velocidade e estabilidade do SQLite
   - 25 requisições simultâneas com retry automático

4. **SQLite WAL Mode + Retry com Backoff**
   - Habilitado WAL (Write-Ahead Logging) para melhor concorrência
   - Operações de escrita com retry automático (5 tentativas, backoff exponencial)
   - Evita erro "database is locked" em alta concorrência

### Velocidade Máxima Teórica

```
Domínios: 3 (Kabum, ML, Amazon)
Delay: 0.3s por domínio
Conexões/domínio: 5

Velocidade = 3 domínios × (1/0.3s) req/s = ~10 req/s = 600 pág/min (teórico)
Velocidade real: ~130 pág/min (latência de rede, parsing, etc)
```

---

## 🔥 Tutorial: Como Acelerar Ainda Mais (Avançado)

> ⚠️ **ATENÇÃO: RISCOS DE REQUISIÇÕES AGRESSIVAS**
> 
> Acelerar além do recomendado pode causar:
> - **Rate limiting**: Site retorna HTTP 429 (Too Many Requests)
> - **Bloqueio de IP**: Seu IP é banido temporária ou permanentemente
> - **Degradação de serviço**: Você pode prejudicar a performance do site
> - **Ação legal**: Em casos extremos, pode violar ToS e leis
> 
> **Use com responsabilidade e apenas para fins educacionais!**

### Opção 1: Reduzir Delay (Moderado)

Edite `config.py`:

```python
# ANTES (seguro)
request_delay=0.3

# DEPOIS (mais rápido, mais risco)
request_delay=0.1
```

**Risco:** Médio. Pode causar rate limiting após alguns minutos.

### Opção 2: Aumentar Concorrência (Moderado)

Edite `config.py`:

```python
# ANTES
max_concurrent_requests: int = 20
max_concurrent_per_domain: int = 5

# DEPOIS (mais rápido)
max_concurrent_requests: int = 50
max_concurrent_per_domain: int = 10
```

**Risco:** Médio-Alto. Mais conexões simultâneas = mais chance de detecção.

### Opção 3: Via CLI (Temporário)

```bash
# Dobrar velocidade para teste específico
python main.py crawl --concurrency 40 --delay 0.15 --max-pages 1000
```

**Vantagem:** Não altera configuração permanente.

### Opção 4: Desabilitar robots.txt (NÃO RECOMENDADO)

```python
# Em config.py
respect_robots_txt: bool = False
```

**Risco:** MUITO ALTO. Viola boas práticas de web crawling.

### Sinais de Que Você Está Muito Agressivo

1. **Muitos erros 429** (Too Many Requests)
   ```
   Páginas com erro: 150
   ```

2. **Erros de conexão aumentando**
   ```
   Connection refused / Connection reset
   ```

3. **Velocidade caindo repentinamente**
   - Site começou a throttle suas requisições

4. **Captchas aparecendo**
   - Cloudflare ou similar detectou bot

### Como Verificar se Foi Bloqueado

```bash
# Testar se o site ainda responde
curl -I "https://www.kabum.com.br/"
```

Se retornar 403 ou 429, seu IP foi bloqueado.

### Recuperação de Bloqueio

1. **Esperar**: Maioria dos bloqueios expira em 1-24 horas
2. **Trocar IP**: Reiniciar roteador (se IP dinâmico)
3. **VPN**: Usar VPN para trocar IP (não recomendado para scraping)
4. **Reduzir velocidade**: Voltar para configuração segura

### Configuração Recomendada por Nível de Risco

| Nível | Delay | Concorrência | Velocidade | Risco |
|-------|-------|--------------|------------|-------|
| **Seguro** | 0.5s | 10 | ~60 pág/min | Baixo |
| **Balanceado** | 0.3s | 20 | ~130 pág/min | Baixo-Médio |
| **Agressivo** | 0.15s | 40 | ~250 pág/min | Médio-Alto |
| **Perigoso** | 0.05s | 100 | ~500 pág/min | Muito Alto |

**Recomendação:** Use "Balanceado" para coletas longas (>10k páginas).

---

### Performance Otimizada

O crawler foi otimizado para máxima velocidade respeitando boas práticas:

| Métrica | Valor |
|---------|-------|
| Velocidade | ~244 páginas/min |
| Delay por domínio | 0.2s (sem Crawl-delay nos robots.txt) |
| Concorrência | 25 requisições simultâneas |
| Lock | Por domínio (paralelo entre lojas) |
| Retry DB | 5 tentativas com backoff exponencial |

**Nota:** A velocidade pode variar dependendo da conexão de internet.

**Dica:** Use `Ctrl+C` para interromper. A coleta pode ser retomada com:

```bash
python main.py crawl --resume
```

### Passo 4: Verificar Estatísticas

```bash
python main.py stats
```

**Resultado esperado:**
```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Métrica            ┃ Valor  ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Total de Páginas   │ 50.234 │
│ Páginas de Produto │  8.543 │
│ Total de Produtos  │  8.543 │
└────────────────────┴────────┘
       Por Domínio        
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Domínio              ┃ Páginas ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ kabum.com.br         │  18.432 │
│ mercadolivre.com.br  │  20.102 │
│ magazineluiza.com.br │  11.700 │
└──────────────────────┴─────────┘
```

### Passo 5: Inspecionar o Banco de Dados

```bash
python main.py inspect --limit 15
```

**O que mostra:**
- Estatísticas gerais (páginas, produtos, preços)
- Distribuição por domínio
- Top categorias de produtos
- Faixas de preço
- Top N produtos mais caros
- Amostra de URLs coletadas

### Passo 6: Explorar e Buscar Dados

O comando `browse` permite navegar e buscar no banco:

```bash
# Ver últimos 20 produtos
python main.py browse

# Buscar por nome
python main.py browse --search "placa de video"
python main.py browse --search "rtx 4090"

# Filtrar por domínio
python main.py browse --domain kabum
python main.py browse --domain amazon --limit 50

# Filtrar por faixa de preço
python main.py browse --min-price 1000 --max-price 5000

# Combinar filtros
python main.py browse --search "ryzen" --min-price 500 --max-price 2000

# Ver URLs dos produtos
python main.py browse --search "monitor" --url

# Navegar páginas (paginação)
python main.py browse --offset 20 --limit 20   # Página 2
python main.py browse --offset 40 --limit 20   # Página 3

# Ver páginas coletadas (não produtos)
python main.py browse --pages --limit 30
python main.py browse --pages --domain kabum
```

### Passo 7: Analisar Qualidade dos Produtos

Como o Mercado Livre é um marketplace genérico, alguns produtos não relacionados a hardware podem ser coletados. Use:

```bash
python main.py analyze-products
```

**O que mostra:**
- Classificação: Hardware válido vs Não-hardware vs Não classificado
- Amostras de produtos não-hardware detectados
- Distribuição por domínio

> **Nota:** O crawler coleta TODAS as páginas para maximizar cobertura. A classificação é pós-processamento. Para o trabalho de RI, o volume de páginas (50k+) é o que importa.

### Passo 8: Exportar Dados

```bash
# Para CSV (mais comum)
python main.py export --format csv --output ./dados

# Para JSON
python main.py export --format json --output ./dados
```

**Arquivos gerados:**
- `dados/pages.csv` - Todas as páginas coletadas
- `dados/products.csv` - Produtos com preços

---

## 📊 Interpretação dos Resultados

### Banco de Dados (data/crawler.db)

O SQLite contém 6 tabelas que você pode consultar:

```bash
# Abrir banco com SQLite
sqlite3 data/crawler.db
```

**Consultas úteis:**

```sql
-- Total de páginas por domínio
SELECT domain, COUNT(*) as total 
FROM pages 
GROUP BY domain;

-- Produtos com preço detectado
SELECT name, price, store, category 
FROM products 
WHERE price IS NOT NULL 
LIMIT 20;

-- Histórico de preços de um produto
SELECT p.name, ph.price, ph.recorded_at 
FROM products p 
JOIN price_history ph ON p.id = ph.product_id 
ORDER BY ph.recorded_at;

-- Categorias mais encontradas
SELECT category, COUNT(*) as total 
FROM products 
WHERE category IS NOT NULL 
GROUP BY category 
ORDER BY total DESC;
```

### Arquivos CSV Exportados

**pages.csv:**
| Campo | Descrição |
|-------|-----------|
| id | ID único da página |
| url | URL completa |
| title | Título da página |
| domain | Domínio (ex: kabum.com.br) |
| is_product | True se é página de produto |
| crawled_at | Data/hora da coleta |

**products.csv:**
| Campo | Descrição |
|-------|-----------|
| id | ID único do produto |
| name | Nome do produto |
| price | Preço em R$ (float) |
| category | Categoria detectada (gpu, cpu, ram, etc) |
| store | Loja de origem |
| url | URL da página do produto |
| last_updated | Última atualização |

### Métricas de Sucesso

| Métrica | Meta | Significado |
|---------|------|-------------|
| Total de Páginas | > 50.000 | 8 pontos (máximo) |
| Páginas de Produto | > 10% | Boa detecção de produtos |
| Produtos com Preço | > 80% | Extração de preços funcionando |
| Erros HTTP | < 10% | Coleta estável |

---

## 🔧 Opções Avançadas

### Coletar Apenas Uma Loja

```bash
python main.py crawl --stores kabum --max-pages 5000
```

### Aumentar Velocidade (Cuidado!)

```bash
python main.py crawl --concurrency 15 --delay 1.5
```

⚠️ **Aviso:** Valores muito agressivos podem causar bloqueio.

### Limpar e Recomeçar

```bash
python main.py clear --yes
python main.py crawl --no-resume
```

## 🏗️ Arquitetura

```
Python-WebCrawler/
├── main.py                 # CLI principal
├── config.py               # Configurações e seeds
├── requirements.txt        # Dependências
├── crawler/
│   ├── __init__.py
│   ├── spider.py          # Spider principal (async)
│   ├── frontier.py        # Gerenciador de URLs
│   └── politeness.py      # robots.txt e delays
├── storage/
│   ├── __init__.py
│   ├── models.py          # Modelos SQLAlchemy
│   └── database.py        # Operações de banco
├── extractors/
│   ├── __init__.py
│   ├── product_detector.py # Detecta páginas de produto
│   └── price_extractor.py  # Extrai preços
└── data/
    └── crawler.db         # Banco SQLite
```

## 🔧 Configuração

Edite `config.py` para ajustar:

```python
class CrawlerConfig:
    MAX_PAGES = 60000           # Páginas a coletar
    MAX_DEPTH = 15              # Profundidade máxima
    CONCURRENT_REQUESTS = 25    # Requisições paralelas
    REQUEST_DELAY = 0.2         # Delay entre requisições (s)
```

### Adicionar Nova Loja

```python
STORES = {
    'nova_loja': StoreConfig(
        name='Nova Loja',
        domain='novaloja.com.br',
        seed_urls=[
            'https://novaloja.com.br/categoria/hardware',
        ],
        product_patterns=['/produto/', '/p/'],
        ignore_patterns=['/login', '/carrinho'],
    ),
}
```

## 📊 Estratégia de Coleta

### Priorização (BFS com pesos)

| Tipo de Página | Prioridade |
|----------------|------------|
| Páginas de Produto | 100 |
| Seeds | 90 |
| Listagens/Categorias | 80 |
| Outras | 50 |

### Politeness

- Respeita `robots.txt` de cada domínio
- Delay mínimo de 2s entre requisições ao mesmo domínio
- User-Agent identificado
- Sem crawling paralelo no mesmo domínio

### Deduplicação

- Normalização de URLs (lowercase, remove query params desnecessários)
- Hash SHA-256 para identificação única
- Filtro bloom-like na fronteira

## 📈 Métricas

O crawler rastreia em tempo real:
- Páginas coletadas
- Produtos encontrados
- Erros HTTP
- Taxa de coleta (páginas/segundo)

### Checkpoint

A cada 1000 páginas, o estado é salvo. Use `--resume` para continuar de onde parou.

## 🗃️ Banco de Dados

SQLite com as seguintes tabelas:

- **pages**: Todas as páginas coletadas
- **products**: Produtos extraídos com preços
- **price_history**: Histórico de preços
- **links**: Grafo de links entre páginas
- **frontier**: URLs pendentes
- **crawl_stats**: Estatísticas de execução

## 📝 Requisitos do Trabalho

### Fase 1 - Coletor (8 pontos)

| Meta | Pontos |
|------|--------|
| > 50.000 páginas | 8 |
| > 25.000 páginas | 6 |
| > 10.000 páginas | 4 |
| < 10.000 páginas | 2 |

### Entregas

1. ✅ Código fonte do coletor
2. ✅ Relatório com descrição da técnica
3. ⏳ Proposta do sistema de RI

## 👤 Autor

Trabalho desenvolvido para a disciplina de Recuperação de Informação.

## 📄 Licença

MIT License - uso educacional.
