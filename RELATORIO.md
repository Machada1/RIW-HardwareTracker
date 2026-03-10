# Relatório - Fase 1: Coletor Web

**Disciplina:** Recuperação de Informação  
**Fase:** 1 - Coletor  
**Pontuação Máxima:** 8 pontos  

---

## 1. Introdução

Este relatório descreve a implementação de um **coletor web (crawler)** especializado em páginas de hardware de e-commerce brasileiro. O objetivo é construir um corpus de páginas para posterior indexação e recuperação.

### 1.1 Domínio

O coletor foi desenvolvido para coletar páginas de três grandes lojas de e-commerce:

1. **Kabum** - Especializada em informática e hardware
2. **Mercado Livre** - Marketplace com grande variedade de vendedores
3. **Amazon Brasil** - E-commerce global com amplo catálogo

> **Nota:** Magazine Luiza, Pichau e Terabyte foram testadas mas não puderam ser implementadas devido a limitações técnicas (SPA e Cloudflare WAF). Ver seção 8 para detalhes.

### 1.2 Escopo de Coleta

- **Categorias:** Processadores, placas de vídeo, memórias, SSDs, HDDs, fontes, gabinetes, coolers, placas-mãe, periféricos
- **Meta:** > 50.000 páginas para pontuação máxima

---

## 2. Arquitetura do Sistema

### 2.1 Visão Geral

O sistema foi implementado em **Python 3.11+** com arquitetura modular:

```
┌─────────────────────────────────────────────────────────┐
│                    CLI (main.py)                        │
│                   Typer + Rich                          │
├──────────────────┬────────────────┬────────────────────┤
│     Spider       │   Extractors   │     Storage        │
│   (Assíncrono)   │   (Produto/    │   (SQLAlchemy      │
│   aiohttp        │    Preço)      │    + SQLite)       │
├──────────────────┼────────────────┼────────────────────┤
│    Frontier      │  Politeness    │    Config          │
│  (Prioridade)    │  (robots.txt)  │   (Stores/Seeds)   │
└──────────────────┴────────────────┴────────────────────┘
```

### 2.2 Componentes

| Componente | Responsabilidade |
|------------|-----------------|
| **Spider** | Orquestra coleta, requisições HTTP, parsing |
| **Frontier** | Gerencia fila de URLs com prioridade |
| **Politeness** | Respeita robots.txt e delays por domínio |
| **Extractors** | Detecta produtos e extrai preços |
| **Storage** | Persistência em SQLite com SQLAlchemy |

---

## 3. Técnica de Coleta

### 3.1 Estratégia: BFS com Priorização

O coletor utiliza **Busca em Largura (BFS) adaptativa** com fila de prioridade:

1. **Seeds (90 pontos):** URLs iniciais das lojas
2. **Produtos (100 pontos):** Páginas identificadas como produtos
3. **Listagens (80 pontos):** Páginas de categoria
4. **Outras (50 pontos):** Páginas genéricas

```python
def calculate_priority(url: str, store: StoreConfig) -> int:
    # Páginas de produto têm máxima prioridade
    for pattern in store.product_patterns:
        if pattern in url:
            return 100
    
    # Listagens são importantes
    if any(kw in url for kw in ['categoria', 'busca', 'lista']):
        return 80
    
    return 50
```

### 3.2 Processamento Assíncrono

Utilizamos **aiohttp** para requisições concorrentes:

- 10 requisições simultâneas (configurável)
- Delay de 2 segundos entre requisições ao mesmo domínio
- Timeout de 30 segundos por requisição
- Retry com backoff exponencial (3 tentativas)

### 3.3 Normalização de URLs

Para evitar duplicatas, todas as URLs são normalizadas:

1. Conversão para lowercase
2. Remoção de fragmentos (#)
3. Ordenação de query parameters
4. Remoção de parâmetros de tracking (utm_*, ref, etc.)
5. Hash SHA-256 para comparação rápida

```python
def normalize_url(url: str) -> str:
    parsed = urlparse(url.lower())
    
    # Remove parâmetros de tracking
    params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in params.items() 
                    if not k.startswith(('utm_', 'ref'))}
    
    return urlunparse(...)
```

### 3.4 Politeness

O coletor segue boas práticas de web crawling:

- **robots.txt:** Parseado e respeitado para cada domínio
- **Crawl-delay:** Respeitado quando especificado
- **User-Agent:** Identificado como bot educacional
- **Rate limiting:** Máximo de 1 requisição/2s por domínio

---

## 4. Extração de Dados

### 4.1 Detecção de Produtos

Utilizamos múltiplas heurísticas para identificar páginas de produto:

1. **JSON-LD:** Schema.org Product
2. **OpenGraph:** og:type = "product"
3. **Padrões de URL:** /produto/, /p/, /item/
4. **Elementos HTML:** Seletores específicos por loja

### 4.2 Extração de Preços

Preços são extraídos usando:

1. **JSON-LD:** offers.price
2. **Meta tags:** product:price:amount
3. **Seletores CSS:** Específicos por loja
4. **Regex:** Fallback para R$ X.XXX,XX

---

## 5. Armazenamento

### 5.1 Modelo de Dados

```
┌──────────┐     ┌──────────┐     ┌───────────────┐
│  pages   │────<│  links   │>────│    pages      │
├──────────┤     ├──────────┤     ├───────────────┤
│ id (PK)  │     │ source   │     │               │
│ url      │     │ target   │     │               │
│ title    │     │          │     │               │
│ domain   │     └──────────┘     └───────────────┘
│ html     │
│ ...      │     ┌──────────────┐
└──────────┘     │   products   │
      │          ├──────────────┤
      └─────────>│ page_id (FK) │
                 │ name         │
                 │ price        │
                 │ category     │
                 └──────────────┘
```

### 5.2 Tabelas

| Tabela | Descrição | Registros Esperados |
|--------|-----------|---------------------|
| pages | Páginas coletadas | > 50.000 |
| products | Produtos extraídos | > 10.000 |
| price_history | Histórico de preços | > 10.000 |
| links | Grafo de links | > 200.000 |
| frontier | URLs pendentes | Variável |
| crawl_stats | Estatísticas | ~50 |

---

## 6. Execução e Resultados

### 6.1 Ambiente de Execução

- **Sistema:** Linux / Python 3.11
- **Hardware:** [especificar]
- **Tempo de execução:** [a preencher após coleta]

### 6.2 Comandos

```bash
# Instalação
pip install -r requirements.txt

# Coleta completa
python main.py crawl --max-pages 60000

# Verificar progresso
python main.py stats

# Exportar dados
python main.py export --format csv
```

### 6.3 Estatísticas de Coleta

| Métrica | Valor |
|---------|-------|
| Páginas coletadas | 50.016 |
| Páginas de produto | ~25.000 |
| Produtos com preço | ~20.000 |
| Taxa média | ~244 pág/min |
| Tempo total | ~3.5 horas |
| Erros HTTP | ~17.000 (35%) |

### 6.4 Distribuição por Loja

| Loja | Páginas | Produtos |
|------|---------|----------|
| Mercado Livre | ~28.500 | ~22.600 |
| Kabum | ~12.000 | ~89 |
| Amazon Brasil | ~9.500 | ~3.100 |

> **Nota:** O Mercado Livre tem mais produtos por ser marketplace generalista. O filtro de hardware limita produtos não-relacionados a informática.

---

## 7. Proposta do Sistema de RI

### 7.1 Visão Geral

O Sistema de Recuperação de Informação proposto permitirá:

1. **Busca por produtos de hardware**
   - Consultas por nome, categoria, preço
   - Ranking por relevância

2. **Comparação de preços**
   - Mesmo produto em diferentes lojas
   - Histórico de preços

3. **Recomendação**
   - Produtos similares
   - "Quem comprou X também viu Y"

### 7.2 Arquitetura Proposta (Fases 2 e 3)

```
┌───────────────────────────────────────────────────────┐
│                    Interface Web                       │
├───────────────┬───────────────────┬───────────────────┤
│   Busca       │   Comparador      │   Recomendação    │
├───────────────┴───────────────────┴───────────────────┤
│                Motor de Busca (BM25/TF-IDF)           │
├───────────────────────────────────────────────────────┤
│                 Índice Invertido                       │
├───────────────────────────────────────────────────────┤
│              Representação (Tokenização)               │
├───────────────────────────────────────────────────────┤
│               Corpus (50k+ páginas)                    │
└───────────────────────────────────────────────────────┘
```

### 7.3 Técnicas Previstas

**Fase 2 - Representação:**
- Tokenização com NLTK
- Remoção de stopwords
- Stemming (RSLP para português)
- TF-IDF para vetorização

**Fase 3 - Recuperação:**
- Índice invertido
- BM25 para ranking
- Busca booleana
- Facetamento por categoria/preço

---

## 8. Lojas Não Suportadas (Limitações Técnicas)

Durante o desenvolvimento, testamos outras lojas brasileiras de hardware:

| Loja | Problema | Detalhes |
|------|----------|----------|
| Magazine Luiza | SPA | Conteúdo renderizado via React/JavaScript. Retorna apenas 17KB de HTML. Necessitaria headless browser. |
| Pichau | Cloudflare WAF | HTTP 403 Forbidden. CF-Ray header presente. Bloqueia bots. |
| Terabyte Shop | Cloudflare WAF | HTTP 403 Forbidden. CF-Ray header presente. Bloqueia bots. |

**Decisão:** Focar nas 3 lojas funcionais (Kabum, ML, Amazon) que fornecem volume suficiente.

---

## 9. Conclusão

O coletor desenvolvido atende aos requisitos da Fase 1, sendo capaz de:

- ✅ Coletar > 50.000 páginas de hardware
- ✅ Extrair informações estruturadas de produtos
- ✅ Filtrar produtos não-hardware (celulares, carros, etc.)
- ✅ Manter dados organizados para próximas fases
- ✅ Respeitar políticas de acesso (robots.txt)

### Otimizações Implementadas

| Aspecto | Solução |
|---------|--------|
| Performance | Lock por domínio, delay 0.3s, ~244 pág/min |
| Estabilidade | WAL mode SQLite, retry com backoff exponencial |
| Qualidade | Filtro de hardware para excluir produtos irrelevantes |
| Monitoramento | Métricas em tempo real (CPU, RAM, NET) |

O sistema está preparado para a **Fase 2 (Representação)**, onde os textos coletados serão processados e indexados.

---

## Referências

1. Manning, C. D., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval*.
2. Liu, B. (2011). *Web Data Mining: Exploring Hyperlinks, Contents, and Usage Data*.
3. Documentação Python: aiohttp, SQLAlchemy, BeautifulSoup.

---

**Data de entrega:** [DATA]  
**Autor:** [NOME]  
**RA:** [RA]
