"""
Hardware Crawler - URL Frontier

Gerencia a fila de URLs a serem visitadas com:
- Priorização (páginas de produto > listagens > outras)
- Deduplicação via hash
- Controle de profundidade
- Balanceamento entre domínios
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urljoin, urldefrag, parse_qs

import tldextract

from config import STORES, StoreConfig, CRAWLER_CONFIG


@dataclass
class URLItem:
    """Item da frontier com metadados."""
    url: str
    url_hash: str
    domain: str
    priority: int
    depth: int
    
    @classmethod
    def create(cls, url: str, depth: int = 0, priority: int = 0) -> "URLItem":
        """Cria um item a partir de uma URL."""
        normalized = normalize_url(url)
        return cls(
            url=normalized,
            url_hash=hash_url(normalized),
            domain=extract_domain(normalized),
            priority=priority,
            depth=depth,
        )


def hash_url(url: str) -> str:
    """Gera hash SHA-256 da URL para deduplicação."""
    return hashlib.sha256(url.encode()).hexdigest()


def normalize_url(url: str) -> str:
    """
    Normaliza URL para deduplicação.
    
    - Remove fragmentos (#)
    - Remove parâmetros de tracking comuns
    - Converte para lowercase (scheme + host)
    - Remove trailing slash
    """
    # Remove fragmento
    url, _ = urldefrag(url)
    
    parsed = urlparse(url)
    
    # Parâmetros de tracking a remover
    tracking_params = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
        'fbclid', 'gclid', 'ref', 'src', 'source',
        '_gl', '_ga', 'mc_cid', 'mc_eid',
    }
    
    # Parse e filtra query params
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k.lower() not in tracking_params}
        
        if filtered:
            # Reconstrói query string ordenada
            query = '&'.join(
                f"{k}={v[0]}" 
                for k, v in sorted(filtered.items())
            )
        else:
            query = ''
    else:
        query = ''
    
    # Reconstrói URL normalizada
    path = parsed.path.rstrip('/') or '/'
    
    normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
    if query:
        normalized += f"?{query}"
    
    return normalized


def extract_domain(url: str) -> str:
    """Extrai domínio registrado da URL."""
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}"


def get_store_for_url(url: str) -> Optional[StoreConfig]:
    """Retorna configuração da loja para uma URL."""
    domain = extract_domain(url)
    for store in STORES.values():
        if store.domain in domain or domain in store.domain:
            return store
    return None


def is_allowed_url(url: str) -> bool:
    """
    Verifica se URL deve ser coletada.
    
    Filtra URLs indesejadas (login, carrinho, etc).
    """
    store = get_store_for_url(url)
    if not store or not store.enabled:
        return False
    
    # Verifica padrões de ignorar
    for pattern in store.ignore_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return False
    
    # Deve ser HTTP(S)
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Ignora extensões de arquivo
    ignore_extensions = {
        '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
        '.css', '.js', '.ico', '.woff', '.woff2', '.ttf',
        '.mp4', '.mp3', '.avi', '.mov', '.zip', '.rar',
    }
    for ext in ignore_extensions:
        if url.lower().endswith(ext):
            return False
    
    return True


def calculate_priority(url: str, depth: int) -> int:
    """
    Calcula prioridade da URL.
    
    Maior prioridade = será visitada primeiro.
    
    Prioridades:
    - Páginas de produto: 100
    - Páginas de listagem/categoria: 80
    - Seeds: 90
    - Outras: 50 - depth (mais profundo = menor prioridade)
    """
    store = get_store_for_url(url)
    if not store:
        return 0
    
    # Verifica se é página de produto
    for pattern in store.product_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return 100
    
    # Verifica se é seed URL
    if url in store.seed_urls:
        return 90
    
    # Listagens/categorias (heurística)
    listing_indicators = [
        '/categoria/', '/c/', '/list', '/busca', '/search',
        '/hardware', '/informatica', '/s/',
    ]
    for indicator in listing_indicators:
        if indicator in url.lower():
            return 80
    
    # Default: diminui com profundidade
    return max(10, 50 - depth * 2)


def is_product_url(url: str) -> bool:
    """Verifica se URL parece ser de página de produto."""
    store = get_store_for_url(url)
    if not store:
        return False
    
    for pattern in store.product_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    
    return False


def extract_links_from_html(html: str, base_url: str) -> list[tuple[str, Optional[str]]]:
    """
    Extrai links de HTML.
    
    Retorna lista de (url, anchor_text).
    """
    from bs4 import BeautifulSoup
    
    links = []
    soup = BeautifulSoup(html, 'lxml')
    
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        if not href:
            continue
        
        # Resolve URL relativa
        full_url = urljoin(base_url, href)
        
        # Normaliza
        normalized = normalize_url(full_url)
        
        # Filtra
        if not is_allowed_url(normalized):
            continue
        
        # Anchor text
        anchor = a.get_text(strip=True)[:512] if a.get_text(strip=True) else None
        
        links.append((normalized, anchor))
    
    return links


class URLFrontier:
    """
    Gerenciador de URL Frontier em memória.
    
    Usado para operações rápidas antes de persistir no banco.
    """
    
    def __init__(self):
        self.seen_hashes: set[str] = set()
        self.pending: list[URLItem] = []
    
    def add(self, url: str, depth: int = 0, priority: Optional[int] = None) -> bool:
        """
        Adiciona URL à frontier.
        
        Retorna True se adicionada, False se já vista.
        """
        normalized = normalize_url(url)
        url_hash = hash_url(normalized)
        
        if url_hash in self.seen_hashes:
            return False
        
        if not is_allowed_url(normalized):
            return False
        
        # Verifica profundidade máxima
        if depth > CRAWLER_CONFIG.max_depth:
            return False
        
        self.seen_hashes.add(url_hash)
        
        # Calcula prioridade se não fornecida
        if priority is None:
            priority = calculate_priority(normalized, depth)
        
        item = URLItem(
            url=normalized,
            url_hash=url_hash,
            domain=extract_domain(normalized),
            priority=priority,
            depth=depth,
        )
        
        self.pending.append(item)
        return True
    
    def add_many(self, urls: list[str], depth: int = 0) -> int:
        """Adiciona múltiplas URLs."""
        added = 0
        for url in urls:
            if self.add(url, depth):
                added += 1
        return added
    
    def pop_batch(self, n: int = 10) -> list[URLItem]:
        """
        Remove e retorna N URLs de maior prioridade.
        """
        # Ordena por prioridade (desc)
        self.pending.sort(key=lambda x: -x.priority)
        
        batch = self.pending[:n]
        self.pending = self.pending[n:]
        
        return batch
    
    def mark_seen(self, url_hash: str):
        """Marca hash como visto."""
        self.seen_hashes.add(url_hash)
    
    def is_seen(self, url: str) -> bool:
        """Verifica se URL já foi vista."""
        return hash_url(normalize_url(url)) in self.seen_hashes
    
    def pending_count(self) -> int:
        """Retorna quantidade de URLs pendentes."""
        return len(self.pending)
    
    def seen_count(self) -> int:
        """Retorna quantidade de URLs vistas."""
        return len(self.seen_hashes)
