"""
Hardware Crawler - Módulo de Extração

Extratores especializados para detectar produtos e preços.
"""

from .product_detector import ProductDetector
from .price_extractor import PriceExtractor

__all__ = [
    'ProductDetector',
    'PriceExtractor',
]
