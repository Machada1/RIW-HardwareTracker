"""
Hardware Crawler - Extrator de Preços

Extrai preços de páginas de e-commerce usando múltiplas estratégias:
- JSON-LD estruturado
- Meta tags
- Padrões CSS/HTML específicos por loja
- Regex em texto
"""

import re
import json
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from decimal import Decimal, InvalidOperation


class PriceExtractor:
    """
    Extrai preços de páginas HTML.
    
    Suporta diferentes formatos de moeda brasileira:
    - R$ 1.234,56
    - 1234.56
    - 1.234
    """
    
    # Regex para encontrar preços em BRL
    PRICE_PATTERNS = [
        # R$ 1.234,56
        r'R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
        # R$ 1234,56
        r'R\$\s*(\d+(?:,\d{2})?)',
        # Só números com vírgula
        r'(\d{1,3}(?:\.\d{3})*,\d{2})',
    ]
    
    # Seletores CSS por loja
    STORE_SELECTORS = {
        'kabum.com.br': [
            'h4.finalPrice',
            '.finalPrice',
            '[data-price]',
            '.priceCard',
        ],
        'mercadolivre.com.br': [
            '.andes-money-amount__fraction',
            '.price-tag-fraction',
            '[itemprop="price"]',
            '.poly-price__current .andes-money-amount__fraction',
        ],
        'magazineluiza.com.br': [
            '[data-testid="price-value"]',
            '.price-template__text',
            '.price-template-price-block',
        ],
    }
    
    def extract_price(self, html: str, url: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Extrai preço da página.
        
        Returns:
            Tuple de (preço_float, preço_texto_original)
        """
        soup = BeautifulSoup(html, 'lxml')
        
        # 1. Tenta JSON-LD
        price, raw = self._extract_from_jsonld(soup)
        if price:
            return price, raw
        
        # 2. Tenta meta tags
        price, raw = self._extract_from_meta(soup)
        if price:
            return price, raw
        
        # 3. Tenta seletores específicos da loja
        domain = self._extract_domain(url)
        price, raw = self._extract_from_selectors(soup, domain)
        if price:
            return price, raw
        
        # 4. Fallback: procura no HTML inteiro
        return self._extract_from_text(str(soup))
    
    def _extract_domain(self, url: str) -> str:
        """Extrai domínio da URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.replace('www.', '').replace('lista.', '')
    
    def _extract_from_jsonld(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[str]]:
        """Extrai preço de JSON-LD."""
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string or '{}')
                
                if isinstance(data, list):
                    data = data[0] if data else {}
                
                # Procura offers
                offers = data.get('offers', {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                
                price = offers.get('price') or data.get('price')
                
                if price:
                    price_float = self._parse_price(str(price))
                    if price_float:
                        return price_float, str(price)
                        
            except (json.JSONDecodeError, TypeError):
                continue
        
        return None, None
    
    def _extract_from_meta(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[str]]:
        """Extrai preço de meta tags."""
        # OpenGraph
        og_price = soup.find('meta', property='product:price:amount')
        if og_price:
            content = og_price.get('content', '')
            price = self._parse_price(content)
            if price:
                return price, content
        
        # Itemprop
        price_elem = soup.find(attrs={'itemprop': 'price'})
        if price_elem:
            content = price_elem.get('content') or price_elem.get_text(strip=True)
            price = self._parse_price(content)
            if price:
                return price, content
        
        return None, None
    
    def _extract_from_selectors(
        self, 
        soup: BeautifulSoup, 
        domain: str
    ) -> Tuple[Optional[float], Optional[str]]:
        """Extrai preço usando seletores CSS específicos."""
        selectors = []
        
        # Adiciona seletores da loja
        for store_domain, store_selectors in self.STORE_SELECTORS.items():
            if store_domain in domain:
                selectors.extend(store_selectors)
        
        # Seletores genéricos
        selectors.extend([
            '.price',
            '.product-price',
            '[data-price]',
            '.current-price',
            '.sale-price',
        ])
        
        for selector in selectors:
            try:
                elem = soup.select_one(selector)
                if elem:
                    # Tenta data-price primeiro
                    price_attr = elem.get('data-price') or elem.get('content')
                    if price_attr:
                        price = self._parse_price(str(price_attr))
                        if price:
                            return price, str(price_attr)
                    
                    # Tenta texto
                    text = elem.get_text(strip=True)
                    price = self._parse_price(text)
                    if price:
                        return price, text
                        
            except Exception:
                continue
        
        return None, None
    
    def _extract_from_text(self, html: str) -> Tuple[Optional[float], Optional[str]]:
        """Fallback: procura preço no HTML com regex."""
        # Primeiro, remove blocos de CSS e JavaScript para evitar falsos positivos
        # (ex: rgba(65,137,230,.15) sendo interpretado como R$ 65,13)
        clean_html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'<script[^>]*>.*?</script>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'style="[^"]*"', '', clean_html)
        clean_html = re.sub(r"style='[^']*'", '', clean_html)
        
        for pattern in self.PRICE_PATTERNS:
            matches = re.findall(pattern, clean_html)
            if matches:
                # Filtra valores plausíveis (R$ 10 a R$ 100.000)
                valid_prices = []
                for match in matches:
                    price = self._parse_price(match)
                    if price and 10 <= price <= 100000:
                        valid_prices.append((price, match))
                
                if valid_prices:
                    # Retorna o preço mais frequente ou o primeiro
                    prices_count = {}
                    for p, raw in valid_prices:
                        prices_count[p] = prices_count.get(p, 0) + 1
                    
                    most_common = max(prices_count, key=prices_count.get)
                    raw = next(raw for p, raw in valid_prices if p == most_common)
                    return most_common, raw
        
        return None, None
    
    def _parse_price(self, text: str) -> Optional[float]:
        """
        Converte texto de preço para float.
        
        Lida com formatos brasileiros:
        - 1.234,56 -> 1234.56
        - 1234,56 -> 1234.56
        - 1234.56 -> 1234.56
        """
        if not text:
            return None
        
        # Remove R$, espaços e caracteres especiais
        text = re.sub(r'[R$\s]', '', text)
        text = text.strip()
        
        if not text:
            return None
        
        try:
            # Formato brasileiro: 1.234,56
            if ',' in text and '.' in text:
                # Remove pontos de milhar, troca vírgula por ponto
                text = text.replace('.', '').replace(',', '.')
            elif ',' in text:
                # Vírgula como separador decimal
                text = text.replace(',', '.')
            
            price = float(text)
            
            # Validação básica
            if price <= 0 or price > 1000000:
                return None
            
            return round(price, 2)
            
        except (ValueError, InvalidOperation):
            return None
    
    def extract_original_and_discount(
        self, 
        html: str, 
        url: str
    ) -> dict:
        """
        Extrai preço original, preço com desconto e porcentagem.
        
        Returns:
            {
                'price': float,
                'original_price': float or None,
                'discount_percent': int or None,
            }
        """
        soup = BeautifulSoup(html, 'lxml')
        
        result = {
            'price': None,
            'original_price': None,
            'discount_percent': None,
        }
        
        # Preço atual
        result['price'], _ = self.extract_price(html, url)
        
        # Tenta encontrar preço original
        original_selectors = [
            '.original-price',
            '.old-price',
            '.price-old',
            '.list-price',
            'del',  # Preço riscado
            's',    # Preço riscado
        ]
        
        for selector in original_selectors:
            try:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    orig_price = self._parse_price(text)
                    if orig_price and result['price'] and orig_price > result['price']:
                        result['original_price'] = orig_price
                        break
            except Exception:
                continue
        
        # Calcula desconto
        if result['price'] and result['original_price']:
            discount = (1 - result['price'] / result['original_price']) * 100
            result['discount_percent'] = int(discount)
        
        return result
