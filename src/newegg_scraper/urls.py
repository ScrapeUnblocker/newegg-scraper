"""Newegg URLs: storefronts, sort orders, filter values, listing and product pages.

Newegg filters a listing with numeric ``N`` values joined by spaces
(``/p/pl?d=rtx+4070&N=50001314 4131``). Brands, categories, condition, stock and
the rest all work this way; ``newegg-scraper filters`` lists the values a search
offers. Prices are filtered with ``LeftPriceRange=<min> <max>``, the sort order is
``Order=<0-5>`` and a page holds 36, 60 or 96 results (``PageSize``), plus any
sponsored listings Newegg mixes in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

#: Storefronts this scraper reads: site code -> (base URL, currency).
SITES: dict[str, tuple[str, str]] = {
    "us": ("https://www.newegg.com", "USD"),
    "ca": ("https://www.newegg.ca", "CAD"),
}

#: Sort orders, as Newegg's ``Order`` parameter.
SORTS: dict[str, int] = {
    "featured": 0,
    "lowest-price": 1,
    "highest-price": 2,
    "best-selling": 3,
    "best-rating": 4,
    "most-reviews": 5,
}

#: Results per page Newegg accepts (sponsored listings come on top).
PAGE_SIZES = (36, 60, 96)
DEFAULT_PAGE_SIZE = 96

#: ``N`` filter values shared by every listing on both storefronts.
IN_STOCK = 4131
SOLD_BY_NEWEGG = 8000

#: Paging parameters, replaced on every page of a copied URL.
_PAGING = ("page", "PageSize")
_ITEM_NUMBER = re.compile(r"^(\d{2})-(\d{3})-(\d{3})([A-Z]?)$")
_WEB_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{4,40}$")


def site_base(site: str) -> str:
    try:
        return SITES[site][0]
    except KeyError:
        raise ValueError(f"unknown site {site!r}; choose from: {', '.join(SITES)}") from None


def site_currency(site: str) -> str:
    site_base(site)
    return SITES[site][1]


def site_of(url: str) -> str:
    """The site code of a Newegg URL (``us`` unless it is on newegg.ca)."""
    host = urlsplit(url).netloc.lower()
    return "ca" if host.endswith("newegg.ca") else "us"


def web_code(item_number: str) -> str:
    """The code Newegg puts in product URLs for an item number.

    Newegg's own items are numbered ``14-126-761`` (refurbished ones end in ``T``)
    and live at ``/p/N82E16814126761``; marketplace items (``9SIB3T1KEH4255``) and
    product groups (``1FT-0004-008P2``) use their number as is.
    """
    item_number = item_number.strip()
    match = _ITEM_NUMBER.match(item_number)
    if match:
        return "N82E168" + "".join(match.groups())
    return item_number


def product_url(ref: str, site: str = "us") -> str:
    """The product page for an item number, a URL code or a full Newegg URL."""
    ref = ref.strip()
    if ref.startswith(("http://", "https://")):
        parts = urlsplit(ref)
        if not parts.netloc.lower().endswith(("newegg.com", "newegg.ca")):
            raise ValueError(f"not a Newegg URL: {ref}")
        return urlunsplit(parts._replace(fragment=""))
    code = web_code(ref)
    if not _WEB_CODE.match(code):
        raise ValueError(f"not a Newegg item number or URL: {ref!r}")
    return f"{site_base(site)}/p/{code}"


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


def price_range(min_price: float | None, max_price: float | None) -> str | None:
    """Newegg's ``LeftPriceRange`` value; an open end becomes 0 or 999999."""
    if min_price is None and max_price is None:
        return None
    low = 0.0 if min_price is None else float(min_price)
    high = 999999.0 if max_price is None else float(max_price)
    if low < 0 or high < 0:
        raise ValueError("prices cannot be negative")
    if low > high:
        raise ValueError(f"min price {low:g} is above max price {high:g}")
    return f"{_number(low)} {_number(high)}"


@dataclass
class SearchQuery:
    """What to list: keywords, a category, filters, a price range and a sort order.

    Args:
        keywords: Search words (``"rtx 4070"``). Optional when ``category`` or
            ``url`` is given.
        category: The ``N`` value of a category, e.g. ``100007709`` for
            "GPUs / Video Graphics Cards" (``filters`` lists them).
        filters: More ``N`` values: brands, condition, ratings, promotions, ...
        sort: One of :data:`SORTS`.
        min_price, max_price: Newegg's price filter.
        in_stock: Only items in stock.
        sold_by_newegg: Only items Newegg sells itself (no marketplace sellers).
        site: ``us`` (newegg.com) or ``ca`` (newegg.ca).
        url: A listing URL copied from your browser (a search, a category page,
            a brand store); its own filters are kept and the options above are
            added on top. The site is taken from the URL.
    """

    keywords: str = ""
    category: int | None = None
    filters: list[int] = field(default_factory=list)
    sort: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    in_stock: bool = False
    sold_by_newegg: bool = False
    site: str = "us"
    url: str | None = None

    def __post_init__(self) -> None:
        self.keywords = " ".join(self.keywords.split())
        if self.url:
            self.site = site_of(self.url)
        site_base(self.site)
        if self.sort is not None and self.sort not in SORTS:
            raise ValueError(f"unknown sort {self.sort!r}; choose from: {', '.join(SORTS)}")
        self.filters = [int(n) for n in self.filters]
        price_range(self.min_price, self.max_price)
        if not (self.keywords or self.category or self.url or self.filters):
            raise ValueError("give keywords, a category, filters or a listing URL")

    @property
    def currency(self) -> str:
        return site_currency(self.site)

    def n_values(self) -> list[int]:
        """Every ``N`` value of the query, each once, in order."""
        values = ([self.category] if self.category else []) + list(self.filters)
        if self.in_stock:
            values.append(IN_STOCK)
        if self.sold_by_newegg:
            values.append(SOLD_BY_NEWEGG)
        seen: list[int] = []
        for value in values:
            if value not in seen:
                seen.append(value)
        return seen

    def page_url(self, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> str:
        """The URL of one result page."""
        if page < 1:
            raise ValueError("page must be at least 1")
        if page_size not in PAGE_SIZES:
            raise ValueError(f"page_size must be one of {', '.join(map(str, PAGE_SIZES))}")
        if self.url:
            parts = urlsplit(self.url)
            params = [(k, v) for k, v in parse_qsl(parts.query) if k not in _PAGING]
            if self.keywords:
                params = [(k, v) for k, v in params if k != "d"] + [("d", self.keywords)]
            base = urlunsplit(parts._replace(query="", fragment=""))
        else:
            params = [("d", self.keywords)] if self.keywords else []
            base = f"{site_base(self.site)}/p/pl"
        extra = self.n_values()
        if extra:
            given = next((v for k, v in params if k == "N"), "")
            merged = given.split() + [str(n) for n in extra if str(n) not in given.split()]
            params = [(k, v) for k, v in params if k != "N"] + [("N", " ".join(merged))]
        price = price_range(self.min_price, self.max_price)
        if price:
            params = [(k, v) for k, v in params if k != "LeftPriceRange"]
            params.append(("LeftPriceRange", price))
        if self.sort is not None:
            params = [(k, v) for k, v in params if k != "Order"]
            params.append(("Order", str(SORTS[self.sort])))
        if page > 1:
            params.append(("page", str(page)))
        params.append(("PageSize", str(page_size)))
        return f"{base}?{urlencode(params, quote_via=quote_plus)}"
