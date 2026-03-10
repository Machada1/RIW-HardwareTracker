"""Storage module - Database and models."""

from storage.models import Page, Product, PriceHistory, Link, Frontier, CrawlStats
from storage.database import Database

__all__ = [
    "Database",
    "Page",
    "Product", 
    "PriceHistory",
    "Link",
    "Frontier",
    "CrawlStats",
]
