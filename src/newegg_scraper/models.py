"""Dataclasses for what the scraper returns. Every one has ``to_dict()``."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar


def _money(value: float | None, currency: str = "") -> str:
    if value is None:
        return "-"
    symbol = "$" if currency in ("USD", "CAD", "") else ""
    return f"{symbol}{value:,.2f}"


def _short(text: str | None, width: int = 60) -> str:
    text = text or ""
    return text if len(text) <= width else text[: width - 3] + "..."


@dataclass
class Product:
    """One result of a Newegg search or category listing.

    ``price`` is what the listing shows today. ``was_price`` and ``savings`` are
    set when an instant discount applies. ``shipping`` is ``0.0`` for free
    shipping. ``all_offers_min`` / ``all_offers_max`` span every seller and
    condition of the same product ("More options from ...").
    """

    position: int
    item_number: str
    title: str
    url: str
    brand: str | None = None
    model: str | None = None
    price: float | None = None
    was_price: float | None = None
    savings: float | None = None
    savings_percent: int | None = None
    currency: str = "USD"
    lowest_price_30_days: float | None = None
    shipping: float | None = None
    free_shipping: bool = False
    in_stock: bool = False
    condition: str = "New"
    rating: float | None = None
    review_count: int = 0
    seller: str = "Newegg"
    sold_by_newegg: bool = True
    ship_from: str | None = None
    sponsored: bool = False
    category: str | None = None
    all_offers_min: float | None = None
    all_offers_max: float | None = None
    release_date: str | None = None
    highlights: dict[str, str] = field(default_factory=dict)
    image: str | None = None

    TABLE_HEADER: ClassVar[tuple[str, ...]] = (
        "#",
        "item",
        "price",
        "was",
        "stock",
        "rating",
        "reviews",
        "seller",
        "title",
    )

    def table_row(self) -> tuple[Any, ...]:
        return (
            self.position,
            self.item_number,
            _money(self.price, self.currency),
            _money(self.was_price, self.currency) if self.was_price else "",
            "in stock" if self.in_stock else "out",
            f"{self.rating:.1f}" if self.rating is not None else "-",
            self.review_count,
            _short(self.seller, 22),
            ("[ad] " if self.sponsored else "") + _short(self.title),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchPage:
    """One page of a listing, as Newegg returned it (sponsored listings included)."""

    url: str
    page: int
    page_size: int
    total_results: int
    products: list[Product] = field(default_factory=list)
    title: str | None = None

    @property
    def has_more(self) -> bool:
        organic = sum(1 for p in self.products if not p.sponsored)
        return organic > 0 and self.page * self.page_size < self.total_results

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["has_more"] = self.has_more
        return data


@dataclass
class FilterValue:
    """One filter value of a listing; pass ``n_value`` as ``--filter``/``filters=``."""

    group: str
    name: str
    n_value: int

    TABLE_HEADER: ClassVar[tuple[str, ...]] = ("group", "N", "value")

    def table_row(self) -> tuple[Any, ...]:
        return (self.group, self.n_value, self.name)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Review:
    """A customer review from a product page."""

    item_number: str
    title: str | None
    rating: int | None
    date: str | None
    author: str | None
    pros: str | None = None
    cons: str | None = None
    comments: str | None = None
    purchased: bool = False
    helpful_votes: int = 0
    total_votes: int = 0
    images: int = 0

    TABLE_HEADER: ClassVar[tuple[str, ...]] = ("rating", "date", "helpful", "purchased", "title")

    def table_row(self) -> tuple[Any, ...]:
        return (
            self.rating if self.rating is not None else "-",
            (self.date or "")[:10],
            f"{self.helpful_votes}/{self.total_votes}",
            "yes" if self.purchased else "no",
            _short(self.title, 70),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Question:
    """A shopper question from a product page, with its best answer."""

    question: str
    date: str | None
    answer_count: int = 0
    upvotes: int = 0
    best_answer: str | None = None
    best_answer_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductDetail:
    """Everything a Newegg product page says about one item (one seller's offer)."""

    item_number: str
    title: str
    url: str
    parent_item: str | None = None
    brand: str | None = None
    model: str | None = None
    upc: str | None = None
    price: float | None = None
    was_price: float | None = None
    savings: float | None = None
    savings_percent: int | None = None
    currency: str = "USD"
    lowest_price_30_days: float | None = None
    shipping: float | None = None
    free_shipping: bool = False
    in_stock: bool = False
    condition: str = "New"
    all_offers_min: float | None = None
    all_offers_max: float | None = None
    rating: float | None = None
    review_count: int = 0
    rating_histogram: dict[str, int] = field(default_factory=dict)
    seller: str = "Newegg"
    sold_by_newegg: bool = True
    seller_rating: float | None = None
    seller_review_count: int | None = None
    seller_top_rated: bool = False
    ship_from: str | None = None
    category: str | None = None
    breadcrumbs: list[str] = field(default_factory=list)
    bullet_points: list[str] = field(default_factory=list)
    specifications: dict[str, dict[str, str]] = field(default_factory=dict)
    variant_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    return_policy: str | None = None
    refund_days: int | None = None
    replacement_days: int | None = None
    warranty_parts_days: int | None = None
    warranty_labor_days: int | None = None
    manufacturer_support_url: str | None = None
    images: list[str] = field(default_factory=list)
    reviews_with_text: int | None = None
    reviews: list[Review] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)

    TABLE_HEADER: ClassVar[tuple[str, ...]] = (
        "item",
        "price",
        "stock",
        "rating",
        "reviews",
        "seller",
        "title",
    )

    def table_row(self) -> tuple[Any, ...]:
        return (
            self.item_number,
            _money(self.price, self.currency),
            "in stock" if self.in_stock else "out",
            f"{self.rating:.1f}" if self.rating is not None else "-",
            self.review_count,
            _short(self.seller, 22),
            _short(self.title),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
