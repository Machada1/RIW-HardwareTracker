"""Crawler module - Spider and frontier."""

from crawler.spider import Spider, CrawlStats, CrawlResult
from crawler.frontier import URLFrontier, URLItem, normalize_url, hash_url
from crawler.politeness import PolitenessController

__all__ = [
    "Spider",
    "CrawlStats",
    "CrawlResult",
    "URLFrontier",
    "URLItem",
    "PolitenessController",
    "normalize_url",
    "hash_url",
]
