"""Scrape Newegg through the ScrapeUnblocker API.

>>> from newegg_scraper import NeweggScraper, SearchQuery
>>> newegg = NeweggScraper()  # reads SCRAPEUNBLOCKER_KEY
>>> cards = newegg.search(SearchQuery("rtx 4070", sort="lowest-price", in_stock=True))
>>> cards[0].price, cards[0].seller
>>> gpu = newegg.product("14-126-761")
>>> gpu.specifications["Memory"], gpu.rating_histogram

See https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import NeweggError, NotFoundError, ParseError
from .models import FilterValue, Product, ProductDetail, Question, Review, SearchPage
from .scraper import NeweggScraper
from .urls import (
    IN_STOCK,
    PAGE_SIZES,
    SITES,
    SOLD_BY_NEWEGG,
    SORTS,
    SearchQuery,
    product_url,
    web_code,
)

__all__ = [
    "FilterValue",
    "IN_STOCK",
    "NeweggError",
    "NeweggScraper",
    "NotFoundError",
    "PAGE_SIZES",
    "ParseError",
    "Product",
    "ProductDetail",
    "Question",
    "Review",
    "SITES",
    "SOLD_BY_NEWEGG",
    "SORTS",
    "SearchPage",
    "SearchQuery",
    "__version__",
    "product_url",
    "web_code",
]
