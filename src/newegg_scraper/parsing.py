"""Turn Newegg pages into the dataclasses in :mod:`models`.

Newegg server-renders every listing and product page and embeds the data behind
it as one JSON object, ``window.__initialState__``:

* listing pages (search, category, brand store) carry ``Products`` (one
  ``ItemCell`` per result, in the page's sort order), ``TotalItemCount``, and the
  filter menus in ``NavigationList`` / ``PropertyList``;
* product pages carry ``ItemDetail`` (price, seller, specifications, warranty,
  images), ``SyncLoadReviews`` (rating histogram and the first customer reviews)
  and ``QaQuestions``.

The price a listing shows is ``UnitCost`` minus any ``InstantRebateAmount``, with
``UnitCost`` shown struck through as the "was" price. ``ShippingCharge`` is
``0.01`` when shipping is free. The product link and the condition label
("Refurbished", "Open Box") come from the rendered result cards.
"""

from __future__ import annotations

import html as htmllib
import json
import math
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import ParseError
from .models import FilterValue, Product, ProductDetail, Question, Review, SearchPage
from .urls import product_url, site_base, site_of, web_code

STATE_MARK = "window.__initialState__ = "
IMAGE_URL = "https://c1.neweggimages.com/productimage/nb640/{name}"

_CARD = re.compile(r'<div[^>]*\bclass="goods-container"[^>]*>')
_ITEM_ATTR = re.compile(r'data-itemnumber="([^"]+)"')
_TITLE_LINK = re.compile(r'<a[^>]*\bclass="goods-title"[^>]*>', re.S)
_HREF = re.compile(r'\bhref="([^"]+)"')
_LABEL = re.compile(r'<span class="item-open-box-italic">(.*?)</span>', re.S)
_IMG = re.compile(r'<a[^>]*\bclass="goods-img"[^>]*>\s*<img[^>]*\bsrc="([^"]+)"', re.S)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_HIGHLIGHT = re.compile(r"<b>(.*?)</b>(.*?)(?=<b>|$)", re.S)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
#: Tracking parameters Newegg adds to links; dropped from returned URLs.
_TRACKING = ("cm_sp", "cm_re", "icid")
NBSP = chr(160)


# -- small helpers -------------------------------------------------------------


def clean(text: Any) -> str | None:
    """Plain text: HTML tags and entities removed, whitespace collapsed."""
    if text is None:
        return None
    text = htmllib.unescape(_TAG.sub(" ", str(text))).replace(NBSP, " ")
    text = _SPACE.sub(" ", text).strip()
    return text or None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _price(value: Any) -> float | None:
    number = _number(value)
    return round(number, 2) if number is not None and number > 0 else None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def clean_url(url: str) -> str:
    """An absolute product link without Newegg's tracking parameters."""
    url = htmllib.unescape(url.strip())
    if url.startswith("//"):
        url = "https:" + url
    parts = urlsplit(url)
    params = [(k, v) for k, v in parse_qsl(parts.query) if k not in _TRACKING]
    return urlunsplit(parts._replace(query=urlencode(params), fragment=""))


def offer_url(url: str, item_number: str) -> str:
    """Point a product-group link at one seller's offer (``?Item=<item number>``).

    A marketplace offer's card links to the product it belongs to, which opens on
    whichever offer Newegg features; ``Item`` selects this one.
    """
    parts = urlsplit(url)
    code = parts.path.rstrip("/").rsplit("/", 1)[-1].upper()
    # Newegg sometimes repeats the page's own code as ?Item=; that one adds nothing.
    params = [(k, v) for k, v in parse_qsl(parts.query) if not (k == "Item" and v.upper() == code)]
    if code != web_code(item_number).upper() and not any(k == "Item" for k, _ in params):
        params.append(("Item", item_number))
    return urlunsplit(parts._replace(query=urlencode(params)))


def image_urls(cell: dict[str, Any]) -> list[str]:
    """Full-size image URLs of an item (``Image.Normal.ImageNameList``)."""
    image = _dict(cell.get("Image"))
    normal = _dict(image.get("Normal")) or _dict(cell.get("NewImage"))
    names = str(normal.get("ImageNameList") or normal.get("ImageName") or "")
    urls = [IMAGE_URL.format(name=n.strip()) for n in names.split(",") if n.strip()]
    if not urls and image.get("ItemCellImageName"):
        urls.append(IMAGE_URL.format(name=image["ItemCellImageName"]))
    return urls


def highlights(view_description: Any) -> dict[str, str]:
    """``<b>Brand:</b> ASUS<br/>...`` as ``{"Brand": "ASUS", ...}``."""
    result: dict[str, str] = {}
    for key, value in _HIGHLIGHT.findall(str(view_description or "")):
        key_text = (clean(key) or "").rstrip(":").strip()
        value_text = clean(value)
        if key_text and value_text:
            result[key_text] = value_text
    return result


def _date(value: Any) -> str | None:
    text = str(value or "")
    if not _DATE.match(text) or text.startswith("1970-"):
        return None
    return text[:10]


# -- the embedded state --------------------------------------------------------


def extract_state(html: str) -> dict[str, Any] | None:
    """The ``window.__initialState__`` object of a Newegg page, or ``None``."""
    start = html.find(STATE_MARK)
    if start < 0:
        return None
    try:
        state, _ = json.JSONDecoder().raw_decode(html, start + len(STATE_MARK))
    except ValueError:
        return None
    return state if isinstance(state, dict) else None


def has_listing(html: str) -> bool:
    """True for a listing page (even one with no results)."""
    state = extract_state(html)
    return state is not None and isinstance(state.get("Products", None), list)


def has_product(html: str) -> bool:
    state = extract_state(html)
    return state is not None and bool(_dict(state.get("ItemDetail")).get("Item"))


def _state(html: str, check, what: str, url: str) -> dict[str, Any]:
    if not check(html):
        raise ParseError(f"no Newegg {what} data in the page: {url}")
    state = extract_state(html)
    assert state is not None
    return state


# -- prices, offers and sellers ------------------------------------------------


def offer_fields(cell: dict[str, Any]) -> dict[str, Any]:
    """Price, shipping, stock, rating and seller fields shared by listings and pages."""
    unit = _price(cell.get("UnitCost"))
    rebate = _number(cell.get("InstantRebateAmount")) or 0.0
    price = round(unit - rebate, 2) if unit is not None else None
    discounted = unit is not None and rebate > 0 and price is not None and price > 0
    shipping = _number(cell.get("ShippingCharge"))
    free = shipping is not None and shipping <= 0.01
    offers = _dict(cell.get("ItemPriceRange"))
    low, high = _price(offers.get("PriceRangeMin")), _price(offers.get("PriceRangeMax"))
    review = _dict(cell.get("Review"))
    count = _int(review.get("HumanRating")) or 0
    seller = _dict(cell.get("Seller"))
    seller_name = clean(seller.get("SellerName"))
    return {
        "price": price if price is None or price > 0 else None,
        "was_price": unit if discounted else None,
        "savings": round(rebate, 2) if discounted else None,
        "savings_percent": math.floor(rebate * 100 / unit + 1e-9) if discounted else None,
        "lowest_price_30_days": _price(cell.get("LowestPrice30Days")),
        "shipping": 0.0 if free else (round(shipping, 2) if shipping is not None else None),
        "free_shipping": free,
        "in_stock": bool(cell.get("Instock")),
        "rating": _number(review.get("RatingOneDecimal")) if count else None,
        "review_count": count,
        "seller": seller_name or "Newegg",
        "sold_by_newegg": not seller_name,
        "ship_from": clean(cell.get("ShipFromCountryName")),
        "all_offers_min": low if low and high else None,
        "all_offers_max": high if low and high else None,
    }


def condition(cell: dict[str, Any], label: str | None = None) -> str:
    if label:
        return label
    feature = _dict(cell.get("Feature"))
    if feature.get("IsRefurbished"):
        return "Refurbished"
    if feature.get("IsOpenBoxed"):
        return "Open Box"
    return "New"


# -- listing pages -------------------------------------------------------------


def parse_cards(html: str) -> dict[str, dict[str, str | None]]:
    """Link, condition label and thumbnail of every rendered result card."""
    cards: dict[str, dict[str, str | None]] = {}
    starts = list(_CARD.finditer(html))
    for index, match in enumerate(starts):
        item = _ITEM_ATTR.search(match.group(0))
        if not item:
            continue
        end = starts[index + 1].start() if index + 1 < len(starts) else len(html)
        chunk = html[match.end() : end]
        link = _TITLE_LINK.search(chunk)
        href = _HREF.search(link.group(0)) if link else None
        label = _LABEL.search(chunk)
        image = _IMG.search(chunk)
        cards.setdefault(
            item.group(1),
            {
                "url": clean_url(href.group(1)) if href else None,
                "condition": clean(label.group(1)) if label else None,
                "image": image.group(1) if image else None,
            },
        )
    return cards


def _fallback_url(item: str, site: str) -> str:
    try:
        return product_url(item, site)
    except ValueError:
        return f"{site_base(site)}/p/{web_code(item)}"


def product_from_cell(
    entry: dict[str, Any],
    position: int,
    currency: str,
    site: str,
    card: dict[str, str | None] | None = None,
) -> Product | None:
    cell = _dict(entry.get("ItemCell"))
    item = str(entry.get("ProductNumber") or cell.get("Item") or "").strip()
    description = _dict(cell.get("Description"))
    title = clean(description.get("Title")) or clean(description.get("ProductName"))
    if not item or not title:
        return None
    card = card or {}
    images = image_urls(cell)
    return Product(
        position=position,
        item_number=item,
        title=title,
        url=offer_url(card["url"], item) if card.get("url") else _fallback_url(item, site),
        brand=clean(_dict(cell.get("ItemManufactory")).get("Manufactory")),
        model=clean(cell.get("Model")),
        currency=currency,
        condition=condition(cell, card.get("condition")),
        sponsored=bool(entry.get("SponsoredMsg")),
        category=clean(_dict(cell.get("Subcategory")).get("SubcategoryDescription")),
        release_date=_date(cell.get("LaunchDate")),
        highlights=highlights(cell.get("ViewDescription")),
        image=images[0] if images else card.get("image"),
        **offer_fields(cell),
    )


def parse_listing(
    html: str,
    url: str,
    *,
    page: int = 1,
    page_size: int = 96,
    currency: str = "USD",
) -> SearchPage:
    """A search, category or brand-store result page."""
    state = _state(html, has_listing, "listing", url)
    site = site_of(url)
    cards = parse_cards(html)
    products: list[Product] = []
    for entry in _list(state.get("Products")):
        if not isinstance(entry, dict):
            continue
        item = str(entry.get("ProductNumber") or "")
        product = product_from_cell(entry, len(products) + 1, currency, site, cards.get(item))
        if product is not None:
            products.append(product)
    info = _dict(state.get("PageInfo"))
    return SearchPage(
        url=url,
        page=page,
        page_size=page_size,
        total_results=_int(state.get("TotalItemCount")) or 0,
        products=products,
        title=clean(info.get("H1TagText")) or clean(info.get("PageTitle")),
    )


def parse_filters(html: str, url: str = "") -> list[FilterValue]:
    """Every filter value a listing offers (categories, brands, condition, ...)."""
    state = _state(html, has_listing, "listing", url)
    values: list[FilterValue] = []
    seen: set[int] = set()
    groups = _list(state.get("NavigationList")) + _list(state.get("PropertyList"))
    for group in groups:
        group = _dict(group)
        name = clean(group.get("Name")) or "Filter"
        if name == "Department":
            name = "Category"
        for child in _list(group.get("Children")):
            child = _dict(child)
            n_value = _int(child.get("NValue"))
            label = clean(child.get("Name"))
            if not n_value or not label or n_value == 100 or n_value in seen:
                continue
            seen.add(n_value)
            values.append(FilterValue(group=name, name=label, n_value=n_value))
    return values


# -- product pages -------------------------------------------------------------


def _specifications(detail: dict[str, Any]) -> dict[str, dict[str, str]]:
    specs: dict[str, dict[str, str]] = {}
    for group in _list(_dict(detail.get("DetailSpecificationObject")).get("Groups")):
        group = _dict(group)
        name = clean(group.get("GroupName")) or "General"
        rows = specs.setdefault(name, {})
        for prop in _list(group.get("Properties")):
            prop = _dict(prop)
            key, value = clean(prop.get("Key")), clean(prop.get("Value"))
            if key and value:
                rows[key] = value
        if not rows:
            del specs[name]
    return specs


def _variants(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    variants: dict[str, dict[str, Any]] = {}
    for group in _list(_dict(state.get("PropertyCollection")).get("PropertyGroups")):
        group = _dict(group)
        name = clean(group.get("GroupDescription"))
        choices = [clean(_dict(p).get("Description")) for p in _list(group.get("Properties"))]
        choices = [c for c in choices if c]
        if name and choices:
            selected = clean(_dict(group.get("SelectedProperty")).get("Description"))
            variants[name] = {"selected": selected, "choices": choices}
    return variants


def _histogram(bar: dict[str, Any]) -> dict[str, int]:
    histogram = {}
    for stars in range(5, 0, -1):
        count = _int(bar.get(f"Rating{stars}Count"))
        if count is not None:
            histogram[str(stars)] = count
    return histogram if any(histogram.values()) else {}


def parse_review(raw: dict[str, Any], item_number: str) -> Review:
    media = len(_list(raw.get("ReviewMediaList"))) + len(_list(raw.get("ReviewImageList")))
    return Review(
        item_number=item_number,
        title=clean(raw.get("Title")),
        rating=_int(raw.get("Rating")),
        date=str(raw.get("InDate"))[:19] if raw.get("InDate") else None,
        author=clean(raw.get("DisplayName")) or clean(raw.get("NickName")),
        pros=clean(raw.get("Pros")),
        cons=clean(raw.get("Cons")),
        comments=clean(raw.get("Comments")),
        purchased=bool(raw.get("HasPurchased")) or str(raw.get("PurchaseMark")) == "1",
        helpful_votes=_int(raw.get("TotalConsented")) or 0,
        total_votes=_int(raw.get("TotalVoting")) or 0,
        images=media,
    )


def parse_question(raw: dict[str, Any]) -> Question | None:
    text = clean(raw.get("Question"))
    if not text:
        return None
    answers = [_dict(a) for a in _list(raw.get("Answers"))]
    best = next((a for a in answers if a.get("IsBestAnswer")), answers[0] if answers else {})
    return Question(
        question=text,
        date=str(raw.get("Indate"))[:10] if raw.get("Indate") else None,
        answer_count=_int(raw.get("AnswerCount")) or len(answers),
        upvotes=_int(raw.get("UpVotes")) or 0,
        best_answer=clean(best.get("Answer")),
        best_answer_by=clean(best.get("NickName")),
    )


def parse_product(html: str, url: str, *, currency: str = "USD") -> ProductDetail:
    """A product page: one seller's offer of one item."""
    state = _state(html, has_product, "product", url)
    detail = _dict(state.get("ItemDetail"))
    item = str(detail.get("Item")).strip()
    description = _dict(detail.get("Description"))
    warranty = _dict(detail.get("Warranty"))
    seller = _dict(detail.get("Seller"))
    reviews_block = _dict(_dict(state.get("SyncLoadReviews")).get("SearchResult"))
    review_filter = _dict(reviews_block.get("ReivewFilter") or reviews_block.get("ReviewFilter"))
    bullets = str(description.get("BulletDescription") or "").splitlines()
    questions = [parse_question(_dict(q)) for q in _list(state.get("QaQuestions"))]
    offer = offer_fields(detail)
    names = (clean(_dict(b).get("Name")) for b in _list(state.get("Breadcrumbs")))
    crumbs = [name for name in names if name]
    return ProductDetail(
        item_number=item,
        title=clean(description.get("Title")) or clean(description.get("ProductName")) or item,
        url=url,
        parent_item=clean(detail.get("ParentItem")),
        brand=clean(_dict(detail.get("ItemManufactory")).get("Manufactory")),
        model=clean(detail.get("ManufacturerPartsNumber")) or clean(detail.get("Model")),
        upc=clean(detail.get("UPCCode")),
        currency=currency,
        condition=condition(detail),
        rating_histogram=_histogram(_dict(review_filter.get("OverAllReviewBarInfo"))),
        seller_rating=_number(seller.get("SellerRatingOneDecimal")) if seller else None,
        seller_review_count=_int(seller.get("SellerReviewCount")) if seller else None,
        seller_top_rated=bool(seller.get("TopRated")),
        category=clean(_dict(detail.get("Subcategory")).get("SubcategoryDescription")),
        breadcrumbs=crumbs,
        bullet_points=[b for b in (clean(line) for line in bullets) if b],
        specifications=_specifications(detail),
        variant_options=_variants(state),
        return_policy=clean(warranty.get("WarrantyName")),
        refund_days=_int(warranty.get("RMARefundDay")) or None,
        replacement_days=_int(warranty.get("RMAReplacementDay")) or None,
        warranty_parts_days=_int(warranty.get("WarrantyDayParts")) or None,
        warranty_labor_days=_int(warranty.get("WarrantyDayLabor")) or None,
        manufacturer_support_url=clean(warranty.get("SupportURL"))
        or clean(detail.get("SupportURLOnItem")),
        images=image_urls(detail),
        reviews_with_text=_int(reviews_block.get("TotalRecordCount")),
        reviews=[
            parse_review(_dict(r), item) for r in _list(reviews_block.get("CustomerReviewList"))
        ],
        questions=[q for q in questions if q is not None],
        **offer,
    )
