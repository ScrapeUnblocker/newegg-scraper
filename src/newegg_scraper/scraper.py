"""Scrape Newegg through the ScrapeUnblocker ``getPageSource`` API.

:class:`NeweggScraper` builds Newegg URLs, fetches the pages through
ScrapeUnblocker and parses them into the dataclasses in :mod:`models`.

* Listing pages (search, categories, brand stores) and product pages are
  server-rendered with their data embedded as JSON, so every page is one plain
  ``getPageSource`` request; no browser rendering is needed.
* :meth:`NeweggScraper.search` walks result pages (up to 96 results each) until
  it has what you asked for, and drops repeats (Newegg shows some items twice,
  once as a sponsored listing).
* Timeouts, transient API errors and pages that come back without their data are
  retried with doubling backoff. A product page that does not exist raises
  :class:`NotFoundError`.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from .errors import NotFoundError, ParseError
from .models import FilterValue, Product, ProductDetail, Review, SearchPage
from .parsing import has_listing, has_product, parse_filters, parse_listing, parse_product
from .urls import (
    DEFAULT_PAGE_SIZE,
    PAGE_SIZES,
    SearchQuery,
    product_url,
    site_base,
    site_currency,
    site_of,
)

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BlockedError",
    "ServerError",
    "ConnectionError",
)
_NOT_FOUND_NAMES = ("TargetNotFoundError", "NotFoundError")

#: Proxy country per storefront, used when ``proxy_country="auto"``.
SITE_COUNTRY = {"us": "us", "ca": "ca"}

log = logging.getLogger(__name__)


def _is_named(error: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(error).__mro__)


def _query(query: SearchQuery | str, site: str) -> SearchQuery:
    if isinstance(query, SearchQuery):
        return query
    return SearchQuery(keywords=query, site=site)


class NeweggScraper:
    """Read Newegg search results, category listings and product pages.

    Args:
        api_key: Your ScrapeUnblocker API key. Defaults to the
            ``SCRAPEUNBLOCKER_KEY`` environment variable (read by the SDK).
        client: A ready ``scrapeunblocker.Client`` (or anything with a compatible
            ``get_page_source``); handy for tests.
        site: Default storefront, ``us`` (newegg.com) or ``ca`` (newegg.ca).
        proxy_country: Country to route requests through. ``"auto"`` (default)
            matches the storefront (``us`` or ``ca``) so prices, stock and
            shipping are the ones local shoppers see. ``None`` lets the API choose.
        max_retries: Extra attempts for a request that fails transiently.
        backoff: Seconds before the first retry; doubles on each retry.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any = None,
        site: str = "us",
        proxy_country: str | None = "auto",
        max_retries: int = 3,
        backoff: float = 2.0,
        timeout: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        site_base(site)
        if client is None:
            from scrapeunblocker import Client

            client = Client(api_key=api_key, timeout=timeout)
        self.client = client
        self.site = site
        self.proxy_country = proxy_country or None
        self.max_retries = max_retries
        self.backoff = backoff
        self.sleep = sleep
        #: Number of API requests made so far (each page fetch is one request).
        self.requests = 0

    # -- fetching -------------------------------------------------------------

    def _country(self, url: str) -> str | None:
        if self.proxy_country == "auto":
            return SITE_COUNTRY[site_of(url)]
        return self.proxy_country

    def fetch(self, url: str, *, check: Callable[[str], bool] | None = None) -> str:
        """The HTML of ``url``, retried on transient failures.

        ``check`` tells a complete page from an empty or challenge page (which is
        retried like a transient error).
        """
        kwargs: dict[str, Any] = {}
        country = self._country(url)
        if country:
            kwargs["proxy_country"] = country
        attempt = 0
        while True:
            self.requests += 1
            try:
                html = self.client.get_page_source(url, **kwargs)
                if not isinstance(html, str) or (check is not None and not check(html)):
                    raise ParseError(f"the page came back without its data: {url}")
                return html
            except Exception as exc:
                if _is_named(exc, *_NOT_FOUND_NAMES):
                    raise NotFoundError(f"Newegg has no page at {url}") from exc
                retryable = isinstance(exc, ParseError) or _is_named(exc, *_TRANSIENT_NAMES)
                if not retryable or attempt >= self.max_retries:
                    raise
                log.info("retrying %s after %s", url, type(exc).__name__)
                self.sleep(self.backoff * (2**attempt))
                attempt += 1

    # -- listings -------------------------------------------------------------

    def search_page(
        self,
        query: SearchQuery | str,
        page: int = 1,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> SearchPage:
        """One result page of a search, category or copied listing URL."""
        query = _query(query, self.site)
        url = query.page_url(page, page_size)
        html = self.fetch(url, check=has_listing)
        return parse_listing(html, url, page=page, page_size=page_size, currency=query.currency)

    def search(
        self,
        query: SearchQuery | str,
        *,
        max_results: int | None = None,
        max_pages: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        sponsored: bool = True,
        dedupe: bool = True,
    ) -> list[Product]:
        """Products of a search or listing, in Newegg's order, numbered from 1.

        Args:
            query: Keywords (``"rtx 4070"``) or a :class:`SearchQuery` with a
                category, filters, price range, sort order or a copied URL.
            max_results: Stop once this many products are collected.
            max_pages: Read at most this many result pages (one request each).
            page_size: 36, 60 or 96 results per page.
            sponsored: Keep the sponsored listings Newegg mixes into results.
            dedupe: Keep each item number once (an item can show up as an ad and
                as a regular result).
        """
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if max_results is not None and max_results < 1:
            raise ValueError("max_results must be at least 1")
        if page_size not in PAGE_SIZES:
            raise ValueError(f"page_size must be one of {', '.join(map(str, PAGE_SIZES))}")
        query = _query(query, self.site)
        products: list[Product] = []
        seen: set[str] = set()
        for page_number in range(1, max_pages + 1):
            page = self.search_page(query, page_number, page_size=page_size)
            for product in page.products:
                if not sponsored and product.sponsored:
                    continue
                if dedupe and product.item_number in seen:
                    continue
                seen.add(product.item_number)
                products.append(product)
            if max_results is not None and len(products) >= max_results:
                break
            if not page.has_more:
                break
        products = products[:max_results] if max_results is not None else products
        for position, product in enumerate(products, 1):
            product.position = position
        return products

    def filters(self, query: SearchQuery | str) -> list[FilterValue]:
        """The filter values (categories, brands, condition, price bands, ...) a
        listing offers, with the ``N`` value to pass as ``SearchQuery.filters``."""
        query = _query(query, self.site)
        url = query.page_url(1, PAGE_SIZES[0])
        return parse_filters(self.fetch(url, check=has_listing), url)

    # -- product pages --------------------------------------------------------

    def product(self, ref: str, *, site: str | None = None) -> ProductDetail:
        """A product page: price, seller, specifications, warranty, reviews and Q&A.

        ``ref`` is an item number (``14-126-761``, ``9SIB3T1KEH4255``), the code
        from a product URL (``N82E16814126761``) or a full newegg.com / newegg.ca
        product URL.
        """
        url = product_url(ref, site or self.site)
        html = self.fetch(url, check=has_product)
        return parse_product(html, url, currency=site_currency(site_of(url)))

    def reviews(self, ref: str, *, site: str | None = None) -> list[Review]:
        """The customer reviews a product page shows, in Newegg's default order."""
        return self.product(ref, site=site).reviews
