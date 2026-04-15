"""
Hardware Crawler - Detector de Páginas de Produto

Identifica se uma página é de produto usando:
- Padrões de URL
- Metadados estruturados (JSON-LD, OpenGraph)
- Padrões de conteúdo HTML
"""

import re
import json
from typing import Optional
from bs4 import BeautifulSoup

from config import STORES, HARDWARE_CATEGORIES


class ProductDetector:
    """
    Detecta se uma página é de produto e extrai categoria.
    """

    # Padrões de URL que indicam páginas de LISTAGEM/CATEGORIA (não produto individual)
    # Mesmo que tenham JSON-LD de produto, essas URLs são listagens.
    LISTING_URL_PATTERNS = [
        # Kabum — categorias sem ID de produto
        r'kabum\.com\.br/(hardware|computadores|gamer|perifericos|tv|celular|electrodomesticos|esporte|ferramentas)(/[a-z-]+)*/?$',
        # Mercado Livre — páginas de busca/categoria
        r'mercadolivre\.com\.br/(busca|s\?|lista\.|categoria)',
        r'lista\.mercadolivre\.com\.br/',
        # Amazon — páginas de busca (s?k=) ou listagem de categoria (s?node=)
        r'amazon\.com\.br/s\?',
        r'amazon\.com\.br/s/',
        # Genérico — termina em categoria/navegação sem ID numérico de produto
        r'/(colecao|categorias?|departamento|vitrine|busca|search|catalog|c/)(/|$)',
    ]

    # Padrões de JSON-LD para produtos
    PRODUCT_SCHEMA_TYPES = {
        "Product",
        "IndividualProduct", 
        "ProductModel",
        "Offer",
    }
    
    # Indicadores no HTML de página de produto
    PRODUCT_INDICATORS = [
        # Botões de compra
        ('button', {'class': re.compile(r'buy|comprar|adicionar|cart', re.I)}),
        ('button', {'id': re.compile(r'buy|comprar|add-cart', re.I)}),
        ('a', {'class': re.compile(r'buy-button|add-to-cart|comprar', re.I)}),
        
        # Elementos de preço
        ('span', {'class': re.compile(r'price|preco|valor', re.I)}),
        ('div', {'class': re.compile(r'product-price|price-box', re.I)}),
        
        # Elementos de produto
        ('div', {'class': re.compile(r'product-info|product-detail', re.I)}),
        ('section', {'class': re.compile(r'product', re.I)}),
    ]
    
    def _is_listing_url(self, url: str) -> bool:
        """Retorna True se a URL é de uma página de listagem/categoria."""
        for pattern in self.LISTING_URL_PATTERNS:
            if re.search(pattern, url, re.I):
                return True
        return False

    def is_product_page(self, html: str, url: str) -> bool:
        """
        Verifica se página é de produto.

        Usa múltiplas heurísticas:
        1. Padrão de URL (negativo: listagem; positivo: produto)
        2. JSON-LD schema
        3. Meta tags OpenGraph
        4. Indicadores HTML
        """
        # 0. Se URL é de listagem, rejeitar imediatamente
        if self._is_listing_url(url):
            return False

        # 1. Verifica URL
        if self._check_url_pattern(url):
            # URL pattern é forte indicador
            return True
        
        soup = BeautifulSoup(html, 'lxml')
        
        # 2. Verifica JSON-LD
        if self._has_product_schema(soup):
            return True
        
        # 3. Verifica OpenGraph
        if self._has_product_og(soup):
            return True
        
        # 4. Verifica indicadores HTML
        indicators_found = self._count_product_indicators(soup)
        
        # Se tem múltiplos indicadores, provavelmente é produto
        return indicators_found >= 3
    
    def _check_url_pattern(self, url: str) -> bool:
        """Verifica padrões de URL de produto."""
        # Padrões genéricos
        generic_patterns = [
            r'/produto/\d+',
            r'/p/[a-z0-9]+',
            r'/product/',
            r'/item/',
            r'MLB-?\d{8,}',  # Mercado Livre
            r'/\d+/p/?$',    # Magazine Luiza
        ]
        
        for pattern in generic_patterns:
            if re.search(pattern, url, re.I):
                return True
        
        # Padrões específicos das lojas
        from crawler.frontier import get_store_for_url
        store = get_store_for_url(url)
        if store:
            for pattern in store.product_patterns:
                if re.search(pattern, url, re.I):
                    return True
        
        return False
    
    def _has_product_schema(self, soup: BeautifulSoup) -> bool:
        """Verifica se há schema.org Product em JSON-LD."""
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string or '{}')
                
                # Pode ser objeto ou lista
                if isinstance(data, list):
                    for item in data:
                        if self._is_product_schema(item):
                            return True
                elif self._is_product_schema(data):
                    return True
                    
            except (json.JSONDecodeError, TypeError):
                continue
        
        return False
    
    def _is_product_schema(self, data: dict) -> bool:
        """Verifica se objeto JSON-LD é de produto."""
        schema_type = data.get('@type', '')
        
        if isinstance(schema_type, list):
            return any(t in self.PRODUCT_SCHEMA_TYPES for t in schema_type)
        
        return schema_type in self.PRODUCT_SCHEMA_TYPES
    
    def _has_product_og(self, soup: BeautifulSoup) -> bool:
        """Verifica meta tags OpenGraph de produto."""
        og_type = soup.find('meta', property='og:type')
        
        if og_type:
            content = og_type.get('content', '').lower()
            if 'product' in content:
                return True
        
        # Verifica se tem og:price
        og_price = soup.find('meta', property='product:price:amount')
        if og_price:
            return True
        
        return False
    
    def _count_product_indicators(self, soup: BeautifulSoup) -> int:
        """Conta indicadores de página de produto."""
        count = 0
        
        for tag_name, attrs in self.PRODUCT_INDICATORS:
            if soup.find(tag_name, attrs):
                count += 1
        
        return count
    
    def detect_category(self, name: str, html: str = "") -> Optional[str]:
        """
        Detecta categoria do produto pelo nome.
        
        Usa as keywords definidas em config.HARDWARE_CATEGORIES.
        """
        name_lower = name.lower()
        
        # Pontuação por categoria
        scores = {}
        
        for category, keywords in HARDWARE_CATEGORIES.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in name_lower:
                    score += 1
            if score > 0:
                scores[category] = score
        
        if not scores:
            return None
        
        # Retorna categoria com maior score
        return max(scores, key=scores.get)
    
    def extract_product_info(self, html: str, url: str) -> Optional[dict]:
        """
        Extrai informações do produto da página.
        
        Tenta extrair de JSON-LD primeiro, depois de meta tags,
        e por último do HTML.
        """
        soup = BeautifulSoup(html, 'lxml')
        
        # Tenta JSON-LD
        info = self._extract_from_jsonld(soup)
        if info and info.get('name'):
            return info
        
        # Tenta meta tags
        info = self._extract_from_meta(soup)
        if info and info.get('name'):
            return info
        
        # Tenta HTML direto
        return self._extract_from_html(soup, url)
    
    def _extract_from_jsonld(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extrai info de JSON-LD."""
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string or '{}')
                
                if isinstance(data, list):
                    for item in data:
                        if self._is_product_schema(item):
                            data = item
                            break
                
                if not self._is_product_schema(data):
                    continue
                
                # Extrai dados
                name = data.get('name', '')
                sku = data.get('sku', '')
                brand = data.get('brand', {})
                if isinstance(brand, dict):
                    brand = brand.get('name', '')
                
                # Preço pode estar em offers
                price = None
                offers = data.get('offers', {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                if isinstance(offers, dict):
                    price = offers.get('price')
                
                return {
                    'name': name,
                    'sku': sku,
                    'brand': brand,
                    'price': float(price) if price else None,
                }
                
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        
        return None
    
    def _extract_from_meta(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extrai info de meta tags."""
        name = None
        price = None
        brand = None
        
        # Nome
        og_title = soup.find('meta', property='og:title')
        if og_title:
            name = og_title.get('content', '')
        
        # Preço
        og_price = soup.find('meta', property='product:price:amount')
        if og_price:
            try:
                price = float(og_price.get('content', 0))
            except ValueError:
                pass
        
        # Marca
        og_brand = soup.find('meta', property='product:brand')
        if og_brand:
            brand = og_brand.get('content', '')
        
        if name:
            return {
                'name': name,
                'price': price,
                'brand': brand,
                'sku': None,
            }
        
        return None
    
    def _extract_from_html(self, soup: BeautifulSoup, url: str) -> Optional[dict]:
        """Extrai info do HTML diretamente."""
        # Nome - tenta h1 ou título do produto
        name = None
        
        # Tenta seletores comuns
        for selector in [
            'h1.product-name',
            'h1.product-title',
            'h1[data-testid="product-title"]',
            '.product-name h1',
            '.product-title',
            'h1',
        ]:
            elem = soup.select_one(selector)
            if elem:
                name = elem.get_text(strip=True)
                if name and len(name) > 5:
                    break
        
        if not name:
            title = soup.find('title')
            if title:
                name = title.get_text(strip=True).split('|')[0].split('-')[0].strip()
        
        return {
            'name': name,
            'price': None,
            'brand': None,
            'sku': None,
        } if name else None
    
    def is_hardware_product(self, name: str) -> tuple[bool, str]:
        """
        Verifica se o produto é relacionado a hardware/informática.
        
        Returns:
            tuple: (is_hardware, reason)
            - is_hardware: True se é hardware válido
            - reason: "hardware", "non_hardware", ou "unknown"
        """
        if not name:
            return False, "unknown"
        
        name_lower = name.lower()
        
        # Palavras-chave de hardware (forte indicador positivo)
        hardware_keywords = [
            # Placas de vídeo
            'placa de vídeo', 'placa de video', 'placa gráfica', 'gpu', 
            'rtx', 'gtx', 'radeon', 'geforce', 'vga', 'nvidia', 'amd rx',
            
            # Processadores
            'processador', 'cpu', 'ryzen', 'intel core', 'core i3', 'core i5', 
            'core i7', 'core i9', 'threadripper', 'xeon',
            
            # Memória
            'memória ram', 'memoria ram', 'ram ddr', 'ddr4', 'ddr5', 'dimm',
            
            # Armazenamento
            'ssd', 'hd interno', 'hd externo', 'nvme', 'm.2', 'disco rígido', 
            'disco rigido', 'hdd', 'sata iii', 'seagate', 'western digital',
            'pen drive', 'pendrive', 'cartão de memória', 'cartao de memoria',
            
            # Placa-mãe
            'placa-mãe', 'placa mãe', 'placa-mae', 'placa mae', 'motherboard',
            'mainboard', 'socket am', 'lga 1',
            
            # Fonte e gabinete
            'fonte de alimentação', 'fonte atx', 'psu', 'w bronze', 'w gold',
            'gabinete gamer', 'gabinete pc', 'case pc', 'torre gamer',
            
            # Refrigeração
            'cooler para', 'water cooler', 'air cooler', 'cooler master',
            'fan rgb', 'ventoinha', 'refrigeração', 'coolers fan', 'deepcool',
            
            # Periféricos gamer/informática
            'teclado mecânico', 'teclado mecanico', 'teclado gamer', 'keyboard',
            'mouse gamer', 'mouse sem fio', 'mousepad', 'mouse pad',
            'monitor gamer', 'monitor 144hz', 'monitor 240hz', 'monitor curvo',
            'headset gamer', 'headset 7.1', 'fone de ouvido gamer',
            'cadeira gamer', 'cadeira-gamer', 'mesa gamer',
            
            # Computadores e notebooks
            'pc gamer', 'notebook gamer', 'desktop gamer', 'computador gamer',
            'workstation', 'notebook', 'laptop', 'ideapad', 'thinkpad',
            'vivobook', 'zenbook', 'macbook', 'chromebook',
            
            # Monitores e headsets genéricos
            'monitor ', 'monitor-', 'headset ', 'headset-',
            'fone gamer', 'fone-gamer',
            
            # Consoles e games
            'playstation', 'xbox', 'nintendo', 'ps5', 'ps4', 'switch',
            'console', 'controle gamer',
            
            # TVs (para gaming)
            'smart tv', 'smart-tv', 'tv 4k', 'tv-4k', 'oled', 'qled',
            'tv led', 'tv-led',
            
            # Rede
            'roteador', 'router', 'switch de rede', 'placa de rede', 'wifi 6',
            
            # Outros hardware
            'webcam', 'nobreak', 'ups', 'estabilizador', 'hub usb',
            'leitor', 'intelbras', 'câmera de segurança', 'camera de seguranca',
        ]
        
        # Palavras-chave que indicam NÃO-hardware
        non_hardware_keywords = [
            # Veículos
            'carro', 'veículo', 'veiculo', 'automóvel', 'automovel',
            'moto', 'motocicleta', 'caminhão', 'caminhao', 'combustível',
            'gasolina', 'diesel', 'pneu', 'automotivo',
            
            # Vestuário
            'roupa', 'camiseta', 'calça', 'sapato', 'tênis', 'tenis',
            'vestido', 'blusa', 'jaqueta', 'moda',
            
            # Móveis/Casa
            'móveis', 'moveis', 'sofá', 'sofa', 'cama', 'colchão', 'colchao',
            'mesa de jantar', 'cadeira de jantar', 'guarda-roupa',
            
            # Eletrodomésticos
            'geladeira', 'fogão', 'fogao', 'microondas', 'lavadora',
            'máquina de lavar', 'maquina de lavar', 'ar condicionado',
            'ventilador de teto', 'liquidificador', 'batedeira',
            
            # Celulares (não PC)
            'iphone', 'samsung galaxy', 'smartphone', 'celular', 'capa de celular',
            'película', 'pelicula', 'capinha',
            
            # Brinquedos
            'brinquedo', 'boneca', 'boneco', 'lego', 'carrinho',
            
            # Beleza/Saúde
            'perfume', 'maquiagem', 'cosmético', 'cosmetico', 'shampoo',
            'hidratante', 'protetor solar',
            
            # Alimentos/Pets
            'comida', 'alimento', 'bebida', 'ração', 'racao', 'pet', 
            'cachorro', 'gato', 'casinha', 'comedouro',
            
            # Cozinha/Casa
            'pote', 'tigela', 'bowl', 'panela', 'frigideira', 'assadeira',
            'fritadeira', 'air fryer', 'airfryer', 'forno', 'cafeteira',
            'purificador', 'filtro de água', 'filtro de agua',
            'aspirador', 'cooktop', 'lava louça', 'lava louca', 'lava-louça',
            'multiprocessador', 'processador de alimentos', 'mixer',
            
            # Outros não-relacionados
            'livro', 'kindle', 'bicicleta', 'patinete', 'skate',
            'instrumento musical', 'violão', 'violao', 'guitarra',
            'bolsa térmica', 'bolsa termica', 'garrafa térmica',
            'tapete higiênico', 'tapete higienico', 'hipótese', 'hipotese',
            'principe', 'arado', 'torto', 'creatina', 'oximetro',
        ]
        
        # Verificar se tem keyword de hardware
        is_hardware = any(kw in name_lower for kw in hardware_keywords)
        
        # Verificar se tem keyword de não-hardware
        is_non_hardware = any(kw in name_lower for kw in non_hardware_keywords)
        
        # Lógica de decisão
        if is_hardware and not is_non_hardware:
            return True, "hardware"
        elif is_non_hardware:
            return False, "non_hardware"
        else:
            # Não classificado - REJEITAR (ser restritivo, só aceitar hardware explícito)
            return False, "unknown"
