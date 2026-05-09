# Diretório de Dados

Todos os arquivos aqui são gerados automaticamente — ignorados pelo `.gitignore`.

## Estrutura

```
data/
├── crawler.db          # Banco SQLite de coleta (tabelas: pages, products, frontier, ...)
├── html_pages/         # HTMLs exportados por domínio
│   ├── kabum.com.br/
│   │   ├── 000001.html
│   │   └── ...
│   ├── amazon.com.br/
│   ├── mercadolivre.com.br/
│   └── index.jsonl     # Metadados de cada página (uma linha JSON por arquivo)
└── index/              # Índice invertido (arquivos JSON)
    ├── meta.json       # Total de docs, avg_dl, data de construção
    ├── vocab.json      # Vocabulário: {stem: {id, df, raw_term}}
    ├── docs.json       # Documentos: {doc_id: {url, title, domain, dl, ...}}
    └── postings/       # Listas de postings shardadas por term_id % 256
        ├── 00.json
        └── ...

```

## Comandos de Manutenção

```bash
# Ver o que existe
python main.py stats

# Exportar HTMLs do banco para arquivos
python main.py export-html --output data/html_pages/

# Construir índice invertido
python main.py index build

# Limpar tudo (com confirmação)
python main.py clean

# Limpar tudo sem confirmação
python main.py clean --all --yes

# Limpar só o banco
python main.py clean --db

# Limpar só os HTMLs
python main.py clean --html

# Limpar só o índice
python main.py clean --index
```
