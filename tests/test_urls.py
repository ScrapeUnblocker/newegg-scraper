from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from newegg_scraper import IN_STOCK, SOLD_BY_NEWEGG, SearchQuery, product_url, web_code
from newegg_scraper.urls import price_range, site_currency, site_of


def params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


@pytest.mark.parametrize(
    "item, code",
    [
        ("14-126-761", "N82E16814126761"),
        ("83-360-977", "N82E16883360977"),
        ("14-137-773T", "N82E16814137773T"),
        ("9SIB3T1KEH4255", "9SIB3T1KEH4255"),
        ("1FT-0004-008P2", "1FT-0004-008P2"),
        (" N82E16814126761 ", "N82E16814126761"),
    ],
)
def test_web_code(item, code):
    assert web_code(item) == code


def test_product_url():
    assert product_url("14-126-761") == "https://www.newegg.com/p/N82E16814126761"
    assert product_url("9SIB3T1KEH4255", "ca") == "https://www.newegg.ca/p/9SIB3T1KEH4255"
    url = "https://www.newegg.com/some-gpu/p/N82E16814932683?Item=9SIB3T1KEH4255#reviews"
    assert (
        product_url(url) == "https://www.newegg.com/some-gpu/p/N82E16814932683?Item=9SIB3T1KEH4255"
    )


@pytest.mark.parametrize("ref", ["https://example.com/p/N82E16814126761", "rtx 4070!", "ab"])
def test_product_url_rejects_other_input(ref):
    with pytest.raises(ValueError):
        product_url(ref)


def test_sites():
    assert site_currency("us") == "USD"
    assert site_currency("ca") == "CAD"
    assert site_of("https://www.newegg.ca/p/pl?d=ssd") == "ca"
    assert site_of("https://www.newegg.com/p/pl?d=ssd") == "us"
    with pytest.raises(ValueError):
        site_currency("uk")


def test_price_range():
    assert price_range(None, None) is None
    assert price_range(500, 700) == "500 700"
    assert price_range(None, 700) == "0 700"
    assert price_range(99.5, None) == "99.50 999999"
    with pytest.raises(ValueError):
        price_range(700, 500)
    with pytest.raises(ValueError):
        price_range(-1, 5)


def test_keyword_search_url():
    url = SearchQuery("  rtx   4070 ").page_url()
    assert url == "https://www.newegg.com/p/pl?d=rtx+4070&PageSize=96"


def test_full_search_url():
    query = SearchQuery(
        "rtx 4070",
        category=100007709,
        filters=[50001315, 100007709],
        sort="lowest-price",
        min_price=500,
        max_price=700,
        in_stock=True,
        sold_by_newegg=True,
    )
    assert query.n_values() == [100007709, 50001315, IN_STOCK, SOLD_BY_NEWEGG]
    got = params(query.page_url(3, 36))
    assert got == {
        "d": ["rtx 4070"],
        "N": ["100007709 50001315 4131 8000"],
        "LeftPriceRange": ["500 700"],
        "Order": ["1"],
        "page": ["3"],
        "PageSize": ["36"],
    }


def test_category_only_url():
    url = SearchQuery(category=100007709, sort="best-selling").page_url(2)
    assert url.startswith("https://www.newegg.com/p/pl?N=100007709")
    assert params(url) == {"N": ["100007709"], "Order": ["3"], "page": ["2"], "PageSize": ["96"]}


def test_copied_url_keeps_its_filters_and_replaces_paging():
    copied = "https://www.newegg.ca/p/pl?d=ssd&N=4131&Order=2&page=5&PageSize=36#top"
    query = SearchQuery(url=copied, filters=[50001315], sort="lowest-price")
    assert query.site == "ca"
    assert query.currency == "CAD"
    url = query.page_url(2, 60)
    assert url.startswith("https://www.newegg.ca/p/pl?")
    assert params(url) == {
        "d": ["ssd"],
        "N": ["4131 50001315"],
        "Order": ["1"],
        "page": ["2"],
        "PageSize": ["60"],
    }


def test_copied_category_url():
    copied = "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48"
    url = SearchQuery(url=copied).page_url()
    assert url == f"{copied}?PageSize=96"


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"keywords": "ssd", "sort": "cheapest"},
        {"keywords": "ssd", "site": "uk"},
        {"keywords": "ssd", "min_price": 10, "max_price": 5},
    ],
)
def test_bad_queries(kwargs):
    with pytest.raises(ValueError):
        SearchQuery(**kwargs)


def test_bad_paging():
    query = SearchQuery("ssd")
    with pytest.raises(ValueError):
        query.page_url(0)
    with pytest.raises(ValueError):
        query.page_url(1, 50)
