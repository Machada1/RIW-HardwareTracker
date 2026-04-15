"""
Hardware Crawler - Configurações Centrais

Sistema de RI para coleta de páginas de e-commerce de hardware.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# =============================================================================
# DIRETÓRIOS
# =============================================================================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "crawler.db"
HTML_OUTPUT_DIR = DATA_DIR / "html_pages"

# =============================================================================
# CONFIGURAÇÃO DAS LOJAS (SEEDS)
# =============================================================================

@dataclass
class StoreConfig:
    """Configuração de uma loja."""
    name: str
    domain: str
    seed_urls: list[str]
    enabled: bool = True
    # Delays customizados por loja (segundos)
    request_delay: float = 2.0
    # Padrões de URL que indicam páginas de produto
    product_patterns: list[str] = field(default_factory=list)
    # Padrões de URL para ignorar
    ignore_patterns: list[str] = field(default_factory=list)


STORES: dict[str, StoreConfig] = {
    "kabum": StoreConfig(
        name="Kabum",
        domain="kabum.com.br",
        seed_urls=[
            # Hardware principal
            "https://www.kabum.com.br/hardware",
            "https://www.kabum.com.br/hardware/placa-de-video-vga",
            "https://www.kabum.com.br/hardware/processadores",
            "https://www.kabum.com.br/hardware/memoria-ram",
            "https://www.kabum.com.br/hardware/ssd-2-5",
            "https://www.kabum.com.br/hardware/placa-mae",
            "https://www.kabum.com.br/hardware/fontes",
            "https://www.kabum.com.br/hardware/coolers",
            "https://www.kabum.com.br/hardware/hds",
            "https://www.kabum.com.br/hardware/water-cooler",
            "https://www.kabum.com.br/hardware/nvme-ssd",
            "https://www.kabum.com.br/hardware/placa-de-som",
            "https://www.kabum.com.br/hardware/placa-de-rede",
            "https://www.kabum.com.br/hardware/pen-drive",
            "https://www.kabum.com.br/hardware/hd-externo",
            # Páginas 2-5 de placa de vídeo
            "https://www.kabum.com.br/hardware/placa-de-video-vga?page_number=2",
            "https://www.kabum.com.br/hardware/placa-de-video-vga?page_number=3",
            "https://www.kabum.com.br/hardware/placa-de-video-vga?page_number=4",
            "https://www.kabum.com.br/hardware/placa-de-video-vga?page_number=5",
            # Páginas 2-5 de processadores
            "https://www.kabum.com.br/hardware/processadores?page_number=2",
            "https://www.kabum.com.br/hardware/processadores?page_number=3",
            # Páginas 2-3 de memórias
            "https://www.kabum.com.br/hardware/memoria-ram?page_number=2",
            "https://www.kabum.com.br/hardware/memoria-ram?page_number=3",
            # Páginas de SSD e HD
            "https://www.kabum.com.br/hardware/ssd-2-5?page_number=2",
            "https://www.kabum.com.br/hardware/ssd-2-5?page_number=3",
            "https://www.kabum.com.br/hardware/hds?page_number=2",
            "https://www.kabum.com.br/hardware/nvme-ssd?page_number=2",
            "https://www.kabum.com.br/hardware/nvme-ssd?page_number=3",
            # Computadores
            "https://www.kabum.com.br/computadores/gabinetes",
            "https://www.kabum.com.br/computadores/pcs-gamer",
            "https://www.kabum.com.br/computadores/notebooks",
            "https://www.kabum.com.br/computadores/pcs-gamer?page_number=2",
            "https://www.kabum.com.br/computadores/pcs-gamer?page_number=3",
            "https://www.kabum.com.br/computadores/notebooks?page_number=2",
            "https://www.kabum.com.br/computadores/notebooks?page_number=3",
            "https://www.kabum.com.br/computadores/notebooks?page_number=4",
            "https://www.kabum.com.br/computadores/notebooks?page_number=5",
            # Periféricos gamer
            "https://www.kabum.com.br/gamer",
            "https://www.kabum.com.br/gamer/teclados-gamer",
            "https://www.kabum.com.br/gamer/mouses-gamer",
            "https://www.kabum.com.br/gamer/headsets-gamer",
            "https://www.kabum.com.br/gamer/mousepad-gamer",
            "https://www.kabum.com.br/gamer/cadeiras-gamer",
            "https://www.kabum.com.br/gamer/teclados-gamer?page_number=2",
            "https://www.kabum.com.br/gamer/mouses-gamer?page_number=2",
            "https://www.kabum.com.br/gamer/mouses-gamer?page_number=3",
            "https://www.kabum.com.br/gamer/headsets-gamer?page_number=2",
            # Periféricos gerais
            "https://www.kabum.com.br/perifericos/teclados",
            "https://www.kabum.com.br/perifericos/mouses",
            "https://www.kabum.com.br/perifericos/headsets",
            "https://www.kabum.com.br/perifericos/webcam",
            "https://www.kabum.com.br/perifericos/teclados?page_number=2",
            "https://www.kabum.com.br/perifericos/mouses?page_number=2",
            # Monitores
            "https://www.kabum.com.br/tv/monitores",
            "https://www.kabum.com.br/tv/monitores?page_number=2",
            "https://www.kabum.com.br/tv/monitores?page_number=3",
            "https://www.kabum.com.br/tv/monitores?page_number=4",
            "https://www.kabum.com.br/tv/monitores?page_number=5",
            # Smart TV (páginas de listagem — não extrairemos produto daqui, mas seguimos links)
            "https://www.kabum.com.br/tv/smart-tv",
        ],
        request_delay=0.2,  # Otimizado: Kabum não define Crawl-delay
        product_patterns=[
            r"/produto/\d+",
            r"/\d+-[a-z0-9-]+$",
        ],
        ignore_patterns=[
            r"/carrinho",
            r"/login",
            r"/cadastro",
            r"/minha-conta",
            r"[?&]facet_filters=",   # Páginas de filtro Kabum — mesmo conteúdo, URL diferente
            r"\.pdf$",
            r"\.jpg$",
            r"\.png$",
        ],
    ),

    "mercadolivre": StoreConfig(
        name="Mercado Livre",
        domain="mercadolivre.com.br",
        seed_urls=[
            # Componentes PC - Hardware
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/placas-video",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/processadores",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/memorias-ram",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/discos-acessorios/discos-rigidos-ssds",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/placas-mae",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/fontes-alimentacao",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/coolers-ventiladores",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/gabinetes",
            # Paginação de componentes
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/placas-video_Desde_49",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/placas-video_Desde_97",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/placas-video_Desde_145",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/processadores_Desde_49",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/processadores_Desde_97",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/memorias-ram_Desde_49",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/memorias-ram_Desde_97",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/discos-acessorios/discos-rigidos-ssds_Desde_49",
            "https://lista.mercadolivre.com.br/informatica/componentes-pc/discos-acessorios/discos-rigidos-ssds_Desde_97",
            # Notebooks e PCs
            "https://lista.mercadolivre.com.br/informatica/pc",
            "https://lista.mercadolivre.com.br/informatica/notebooks",
            "https://lista.mercadolivre.com.br/informatica/pc-gamer",
            "https://lista.mercadolivre.com.br/notebook-gamer",
            "https://lista.mercadolivre.com.br/informatica/notebooks_Desde_49",
            "https://lista.mercadolivre.com.br/informatica/notebooks_Desde_97",
            "https://lista.mercadolivre.com.br/informatica/notebooks_Desde_145",
            # Periféricos gamer
            "https://lista.mercadolivre.com.br/teclado-gamer",
            "https://lista.mercadolivre.com.br/mouse-gamer",
            "https://lista.mercadolivre.com.br/headset-gamer",
            "https://lista.mercadolivre.com.br/mousepad-gamer",
            "https://lista.mercadolivre.com.br/cadeira-gamer",
            "https://lista.mercadolivre.com.br/teclado-gamer_Desde_49",
            "https://lista.mercadolivre.com.br/mouse-gamer_Desde_49",
            "https://lista.mercadolivre.com.br/headset-gamer_Desde_49",
            # Periféricos gerais
            "https://lista.mercadolivre.com.br/informatica/teclados",
            "https://lista.mercadolivre.com.br/informatica/mouses",
            "https://lista.mercadolivre.com.br/informatica/webcam",
            # Monitores
            "https://lista.mercadolivre.com.br/monitor-gamer",
            "https://lista.mercadolivre.com.br/informatica/monitores",
            "https://lista.mercadolivre.com.br/monitor-gamer_Desde_49",
            "https://lista.mercadolivre.com.br/monitor-gamer_Desde_97",
            # Termos específicos de hardware
            "https://lista.mercadolivre.com.br/placa-rtx",
            "https://lista.mercadolivre.com.br/placa-rx",
            "https://lista.mercadolivre.com.br/ryzen",
            "https://lista.mercadolivre.com.br/intel-core",
            "https://lista.mercadolivre.com.br/ssd-nvme",
            "https://lista.mercadolivre.com.br/memoria-ddr5",
            # Termos adicionais
            "https://lista.mercadolivre.com.br/rtx-4070",
            "https://lista.mercadolivre.com.br/rtx-4080",
            "https://lista.mercadolivre.com.br/rtx-4090",
            "https://lista.mercadolivre.com.br/core-i9",
            "https://lista.mercadolivre.com.br/core-i7",
            "https://lista.mercadolivre.com.br/ddr5-32gb",
            "https://lista.mercadolivre.com.br/nvme-1tb",
            "https://lista.mercadolivre.com.br/water-cooler-pc",
        ],
        request_delay=0.2,  # Otimizado: ML não define Crawl-delay
        product_patterns=[
            r"MLB-?\d+",
            r"/p/MLB\d+",
        ],
        ignore_patterns=[
            r"/carrinho",
            r"/login",
            r"/registration",
            r"click1\.mercadolivre",
            r"/ofertas\?",            # Paginação da página de ofertas ML
        ],
    ),
    
    "amazon": StoreConfig(
        name="Amazon Brasil",
        domain="amazon.com.br",
        seed_urls=[
            # Hardware - Componentes
            "https://www.amazon.com.br/s?k=placa+de+video",
            "https://www.amazon.com.br/s?k=processador",
            "https://www.amazon.com.br/s?k=memoria+ram",
            "https://www.amazon.com.br/s?k=ssd+nvme",
            "https://www.amazon.com.br/s?k=placa+mae",
            "https://www.amazon.com.br/s?k=fonte+pc",
            "https://www.amazon.com.br/s?k=cooler+processador",
            "https://www.amazon.com.br/s?k=gabinete+gamer",
            # Paginação das buscas
            "https://www.amazon.com.br/s?k=placa+de+video&page=2",
            "https://www.amazon.com.br/s?k=placa+de+video&page=3",
            "https://www.amazon.com.br/s?k=processador&page=2",
            "https://www.amazon.com.br/s?k=processador&page=3",
            "https://www.amazon.com.br/s?k=ssd+nvme&page=2",
            "https://www.amazon.com.br/s?k=ssd+nvme&page=3",
            "https://www.amazon.com.br/s?k=memoria+ram&page=2",
            # Hardware - Específicos
            "https://www.amazon.com.br/s?k=rtx+4090",
            "https://www.amazon.com.br/s?k=rtx+4080",
            "https://www.amazon.com.br/s?k=rtx+4070",
            "https://www.amazon.com.br/s?k=rtx+4060",
            "https://www.amazon.com.br/s?k=ryzen+7",
            "https://www.amazon.com.br/s?k=ryzen+9",
            "https://www.amazon.com.br/s?k=intel+i7",
            "https://www.amazon.com.br/s?k=intel+i9",
            "https://www.amazon.com.br/s?k=ddr5",
            "https://www.amazon.com.br/s?k=nvme+m2",
            "https://www.amazon.com.br/s?k=water+cooler+pc",
            # Periféricos gamer
            "https://www.amazon.com.br/s?k=teclado+gamer",
            "https://www.amazon.com.br/s?k=mouse+gamer",
            "https://www.amazon.com.br/s?k=headset+gamer",
            "https://www.amazon.com.br/s?k=mousepad+gamer",
            "https://www.amazon.com.br/s?k=monitor+gamer",
            "https://www.amazon.com.br/s?k=teclado+mecanico",
            "https://www.amazon.com.br/s?k=teclado+gamer&page=2",
            "https://www.amazon.com.br/s?k=mouse+gamer&page=2",
            "https://www.amazon.com.br/s?k=headset+gamer&page=2",
            "https://www.amazon.com.br/s?k=monitor+gamer&page=2",
            # Notebooks e PCs
            "https://www.amazon.com.br/s?k=notebook+gamer",
            "https://www.amazon.com.br/s?k=pc+gamer",
            "https://www.amazon.com.br/s?k=notebook+gamer&page=2",
            "https://www.amazon.com.br/s?k=notebook+gamer&page=3",
        ],
        request_delay=0.2,  # Otimizado: sem Crawl-delay
        product_patterns=[
            r"/dp/[A-Z0-9]+",
            r"/gp/product/[A-Z0-9]+",
        ],
        ignore_patterns=[
            r"/ap/signin",
            r"/gp/cart",
            r"/wishlist",
            r"/review",
            r"#customerReviews",
            r"/sspa/click",           # Links de anúncios patrocinados Amazon — não são produtos reais
        ],
    ),
    
    "magazineluiza": StoreConfig(
        name="Magazine Luiza",
        domain="magazineluiza.com.br",
        enabled=False,  # DESABILITADO: SPA requer headless browser
        seed_urls=[
            "https://www.magazineluiza.com.br/placa-de-video/informatica/s/in/pvid/",
            "https://www.magazineluiza.com.br/processador/informatica/s/in/prcs/",
            "https://www.magazineluiza.com.br/memoria-ram/informatica/s/in/mrpc/",
            "https://www.magazineluiza.com.br/hd-ssd/informatica/s/in/hdip/",
            "https://www.magazineluiza.com.br/placa-mae/informatica/s/in/pmae/",
            "https://www.magazineluiza.com.br/fonte/informatica/s/in/ftpc/",
            "https://www.magazineluiza.com.br/gabinete/informatica/s/in/gabi/",
            "https://www.magazineluiza.com.br/teclado/informatica/s/in/tecl/",
            "https://www.magazineluiza.com.br/mouse/informatica/s/in/mous/",
            "https://www.magazineluiza.com.br/headset/informatica/s/in/hdst/",
            "https://www.magazineluiza.com.br/monitor/informatica/s/in/moni/",
        ],
        request_delay=2.5,
        product_patterns=[
            r"/p/[a-z0-9]+/",
            r"/\d{6,}/p/",
        ],
        ignore_patterns=[
            r"/sacola",
            r"/login",
            r"/cadastro",
            r"/quem-somos",
        ],
    ),
}

# =============================================================================
# CONFIGURAÇÃO DO CRAWLER
# =============================================================================

@dataclass
class CrawlerConfig:
    """Configuração principal do crawler."""
    
    # === Limites ===
    max_pages: int = 60000              # Meta: >50k páginas
    max_pages_per_domain: int = 25000   # Limite por domínio
    max_depth: int = 20                 # Profundidade máxima de links
    max_retries: int = 3                # Retentativas por URL
    
    # === Timeouts ===
    request_timeout: int = 30           # Timeout de requisição (segundos)
    
    # === Politeness ===
    default_delay: float = 0.2          # Delay entre requisições (segundos) - Otimizado
    respect_robots_txt: bool = True     # Respeitar robots.txt
    
    # === Concorrência ===
    max_concurrent_requests: int = 25   # Requisições simultâneas (reduzido para evitar DB locks)
    max_concurrent_per_domain: int = 6   # Por domínio
    
    # === User Agent ===
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    # === Checkpoints ===
    checkpoint_interval: int = 500      # Salvar estado a cada N páginas
    
    # === Filtros ===
    allowed_content_types: tuple = (
        "text/html",
        "application/xhtml+xml",
    )


# Instância global de configuração
CRAWLER_CONFIG = CrawlerConfig()


# =============================================================================
# CATEGORIAS DE HARDWARE
# =============================================================================

HARDWARE_CATEGORIES = {
    "gpu": ["placa de video", "placa de vídeo", "geforce", "radeon", "rtx", "gtx", "rx 5", "rx 6", "rx 7"],
    "cpu": ["processador", "ryzen", "intel core", "i3", "i5", "i7", "i9", "amd ryzen"],
    "ram": ["memoria ram", "memória ram", "ddr4", "ddr5", "dimm"],
    "ssd": ["ssd", "nvme", "m.2", "disco sólido"],
    "hdd": ["hd sata", "hd interno", "hd externo", "disco hd", "hdd", "disco rígido", "hard disk", "hard drive"],
    "motherboard": ["placa mae", "placa mãe", "motherboard", "placa-mãe"],
    "psu": ["fonte", "power supply", "psu", "fonte de alimentação"],
    "cooler": ["cooler", "water cooler", "air cooler", "ventilador"],
    "case": ["gabinete", "case", "torre"],
    "monitor": ["monitor", "tela", "display"],
    "keyboard": ["teclado", "keyboard", "mecânico"],
    "mouse": ["mouse", "rato", "gamer mouse"],
    "headset": ["headset", "fone", "headphone", "auricular"],
}


def get_enabled_stores() -> list[StoreConfig]:
    """Retorna lista de lojas habilitadas."""
    return [s for s in STORES.values() if s.enabled]


def get_enabled_stores_dict() -> dict[str, StoreConfig]:
    """Retorna dict de lojas habilitadas."""
    return {name: s for name, s in STORES.items() if s.enabled}


def get_all_seed_urls() -> list[str]:
    """Retorna todas as URLs seed das lojas habilitadas."""
    urls = []
    for store in get_enabled_stores():
        urls.extend(store.seed_urls)
    return urls


def get_store_for_url(url: str) -> Optional[StoreConfig]:
    """
    Retorna a configuração da loja correspondente à URL.
    
    Args:
        url: URL para verificar
        
    Returns:
        StoreConfig se a URL pertence a uma loja conhecida, None caso contrário
    """
    url_lower = url.lower()
    for store in STORES.values():
        if store.domain in url_lower:
            return store
    return None
