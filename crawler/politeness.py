"""
Hardware Crawler - Politeness Control

Gerencia:
- Respeito ao robots.txt
- Delays entre requisições por domínio
- Rate limiting
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urljoin

import aiohttp
from robotexclusionrulesparser import RobotExclusionRulesParser

from config import CRAWLER_CONFIG, STORES, get_store_for_url


@dataclass
class DomainState:
    """Estado de um domínio."""
    last_request_time: float = 0.0
    request_count: int = 0
    robots_parser: Optional[RobotExclusionRulesParser] = None
    robots_fetched: bool = False
    delay: float = 2.0


class PolitenessController:
    """
    Controlador de politeness para crawling ético.
    
    Garante:
    - Delays entre requisições ao mesmo domínio
    - Respeito ao robots.txt
    - Rate limiting global
    """
    
    def __init__(self, user_agent: str = CRAWLER_CONFIG.user_agent):
        self.user_agent = user_agent
        self.domain_states: dict[str, DomainState] = {}
        self._global_lock = asyncio.Lock()  # Para criar novos domínios
        self._domain_locks: dict[str, asyncio.Lock] = {}  # Lock por domínio
    
    def _get_domain(self, url: str) -> str:
        """Extrai domínio de URL."""
        parsed = urlparse(url)
        return parsed.netloc
    
    def _get_robots_url(self, url: str) -> str:
        """Gera URL do robots.txt."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    
    async def _fetch_robots(self, url: str, session: aiohttp.ClientSession) -> Optional[RobotExclusionRulesParser]:
        """Busca e parseia robots.txt."""
        robots_url = self._get_robots_url(url)
        
        try:
            async with session.get(
                robots_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": self.user_agent}
            ) as response:
                if response.status == 200:
                    content = await response.text()
                    parser = RobotExclusionRulesParser()
                    parser.parse(content)
                    return parser
        except Exception:
            pass
        
        return None
    
    async def get_domain_state(
        self, 
        url: str, 
        session: Optional[aiohttp.ClientSession] = None
    ) -> DomainState:
        """Obtém ou cria estado do domínio."""
        domain = self._get_domain(url)
        
        # Cria domínio se não existir (lock global, rápido)
        if domain not in self.domain_states:
            async with self._global_lock:
                if domain not in self.domain_states:
                    # Determina delay baseado na loja
                    from crawler.frontier import get_store_for_url
                    store = get_store_for_url(url)
                    delay = store.request_delay if store else CRAWLER_CONFIG.default_delay
                    
                    self.domain_states[domain] = DomainState(delay=delay)
                    self._domain_locks[domain] = asyncio.Lock()
        
        state = self.domain_states[domain]
        
        # Busca robots.txt se ainda não foi feito (lock do domínio)
        if CRAWLER_CONFIG.respect_robots_txt and not state.robots_fetched and session:
            async with self._domain_locks[domain]:
                if not state.robots_fetched:
                    state.robots_parser = await self._fetch_robots(url, session)
                    state.robots_fetched = True
        
        return state
    
    async def can_fetch(
        self, 
        url: str, 
        session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """
        Verifica se pode fazer requisição à URL.
        
        Considera robots.txt e estado do domínio.
        """
        state = await self.get_domain_state(url, session)
        
        # Verifica robots.txt
        if state.robots_parser:
            parsed = urlparse(url)
            path = parsed.path or "/"
            if not state.robots_parser.is_allowed(self.user_agent, path):
                return False
        
        return True
    
    async def wait_for_permission(
        self, 
        url: str, 
        session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """
        Aguarda até poder fazer requisição.
        
        Implementa delay entre requisições por domínio (paralelo entre domínios).
        Retorna True se permitido, False se bloqueado.
        """
        # Verifica permissão
        if not await self.can_fetch(url, session):
            return False
        
        domain = self._get_domain(url)
        
        # Garante que o domínio existe
        if domain not in self._domain_locks:
            async with self._global_lock:
                if domain not in self._domain_locks:
                    self._domain_locks[domain] = asyncio.Lock()
        
        # Lock apenas para este domínio (outros domínios podem prosseguir)
        async with self._domain_locks[domain]:
            state = self.domain_states.get(domain)
            if not state:
                return True
            
            # Calcula tempo de espera
            now = time.time()
            elapsed = now - state.last_request_time
            
            if elapsed < state.delay:
                wait_time = state.delay - elapsed
                await asyncio.sleep(wait_time)
            
            # Atualiza estado
            state.last_request_time = time.time()
            state.request_count += 1
        
        return True
    
    def get_delay(self, url: str) -> float:
        """Retorna delay configurado para URL."""
        domain = self._get_domain(url)
        state = self.domain_states.get(domain)
        return state.delay if state else CRAWLER_CONFIG.default_delay
    
    def get_stats(self) -> dict:
        """Retorna estatísticas de politeness."""
        return {
            "domains": len(self.domain_states),
            "by_domain": {
                domain: {
                    "requests": state.request_count,
                    "delay": state.delay,
                    "robots_fetched": state.robots_fetched,
                }
                for domain, state in self.domain_states.items()
            }
        }
