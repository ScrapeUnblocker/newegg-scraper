from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import (
    AuthenticationError,
    ScrapeTimeoutError,
    TargetNotFoundError,
    fixture_html,
    listing_html,
)

from newegg_scraper import NotFoundError, ParseError, SearchQuery

SEARCH = fixture_html("search_rtx_4070.html")
PRODUCT = fixture_html("product_9SIB3T1KEH4255.html")


def page_of(url: str) -> int:
    return int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])


def test_retries_transient_errors_with_backoff(make_scraper):
    answers = [ScrapeTimeoutError("slow"), ScrapeTimeoutError("slow"), PRODUCT]
    scraper, client = make_scraper(lambda url, kw: answers.pop(0), backoff=1.5)
    assert scraper.product("9SIB3T1KEH4255").price == 970.0
    assert len(client.calls) == 3
    assert scraper.sleeps == [1.5, 3.0]
    assert scraper.requests == 3


def test_retries_pages_without_data(make_scraper):
    answers = ["<html><title>Are you a human?</title></html>", SEARCH]
    scraper, client = make_scraper(lambda url, kw: answers.pop(0))
    assert len(scraper.search("rtx 4070")) == 6
    assert len(client.calls) == 2


def test_gives_up_after_max_retries(make_scraper):
    scraper, client = make_scraper(lambda url, kw: ScrapeTimeoutError("slow"), max_retries=2)
    with pytest.raises(ScrapeTimeoutError):
        scraper.product("14-126-761")
    assert len(client.calls) == 3
    scraper, client = make_scraper(lambda url, kw: "<html></html>", max_retries=1)
    with pytest.raises(ParseError):
        scraper.search("rtx 4070")
    assert len(client.calls) == 2


def test_does_not_retry_other_errors(make_scraper):
    scraper, client = make_scraper(lambda url, kw: AuthenticationError("bad key"))
    with pytest.raises(AuthenticationError):
        scraper.product("14-126-761")
    assert len(client.calls) == 1


def test_missing_product_is_not_found(make_scraper):
    scraper, client = make_scraper(lambda url, kw: TargetNotFoundError("404"))
    with pytest.raises(NotFoundError):
        scraper.product("14-999-999")
    assert len(client.calls) == 1


def test_proxy_country_follows_the_site(make_scraper):
    scraper, client = make_scraper(lambda url, kw: PRODUCT)
    scraper.product("14-126-761")
    scraper.product("https://www.newegg.ca/p/N82E16814126761")
    assert client.calls[0] == ("https://www.newegg.com/p/N82E16814126761", {"proxy_country": "us"})
    assert client.calls[1] == ("https://www.newegg.ca/p/N82E16814126761", {"proxy_country": "ca"})
    scraper, client = make_scraper(lambda url, kw: PRODUCT, proxy_country=None)
    scraper.product("14-126-761")
    assert client.calls[0][1] == {}
    scraper, client = make_scraper(lambda url, kw: PRODUCT, proxy_country="de")
    scraper.product("14-126-761")
    assert client.calls[0][1] == {"proxy_country": "de"}


def test_ca_site_sets_urls_and_currency(make_scraper):
    scraper, client = make_scraper(lambda url, kw: SEARCH if "/p/pl" in url else PRODUCT, site="ca")
    products = scraper.search("rtx 4070")
    assert client.calls[0][0] == "https://www.newegg.ca/p/pl?d=rtx+4070&PageSize=96"
    assert {p.currency for p in products} == {"CAD"}
    assert scraper.product("14-126-761").currency == "CAD"


def test_search_dedupes_and_numbers_results(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: SEARCH)
    products = scraper.search("rtx 4070")
    numbers = [p.item_number for p in products]
    assert len(numbers) == len(set(numbers)) == 6
    assert [p.position for p in products] == [1, 2, 3, 4, 5, 6]
    everything = scraper.search("rtx 4070", dedupe=False)
    assert len(everything) == 7


def test_search_without_sponsored(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: SEARCH)
    products = scraper.search("rtx 4070", sponsored=False)
    assert not any(p.sponsored for p in products)
    # The organic copy of an item that was also advertised is kept.
    assert "9SIAZBDKFV9493" in [p.item_number for p in products]
    assert len(products) == 5


def test_search_walks_pages_until_the_end(make_scraper):
    pages = {
        1: listing_html([("9SIA01", 1.0), ("9SIA02", 2.0), ("9SIAD1", 9.0)], 80, ("9SIAD1",)),
        2: listing_html([("9SIA03", 3.0), ("9SIA02", 2.0), ("9SIA04", 4.0)], 80),
        3: listing_html([("9SIA05", 5.0)], 80),
    }
    scraper, client = make_scraper(lambda url, kw: pages[page_of(url)])
    query = SearchQuery("ssd", sort="lowest-price")
    products = scraper.search(query, max_pages=10, page_size=36)
    numbers = [p.item_number for p in products]
    assert numbers == ["9SIA01", "9SIA02", "9SIAD1", "9SIA03", "9SIA04", "9SIA05"]
    assert [page_of(url) for url, _ in client.calls] == [1, 2, 3]
    assert all("PageSize=36" in url and "Order=1" in url for url, _ in client.calls)


def test_search_stops_at_max_results_and_max_pages(make_scraper):
    big = listing_html([(f"9SIB{i:03d}", float(i)) for i in range(36)], 1000)
    scraper, client = make_scraper(lambda url, kw: big)
    assert len(scraper.search("ssd", max_results=10, max_pages=5)) == 10
    assert len(client.calls) == 1
    scraper, client = make_scraper(lambda url, kw: big)
    scraper.search("ssd", max_pages=2, page_size=36, dedupe=False)
    assert len(client.calls) == 2


def test_search_stops_on_an_empty_page(make_scraper):
    scraper, client = make_scraper(lambda url, kw: fixture_html("search_no_results.html"))
    assert scraper.search("zzqqxx", max_pages=5) == []
    assert len(client.calls) == 1


def test_search_argument_checks(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: SEARCH)
    with pytest.raises(ValueError):
        scraper.search("ssd", max_pages=0)
    with pytest.raises(ValueError):
        scraper.search("ssd", max_results=0)
    with pytest.raises(ValueError):
        scraper.search("ssd", page_size=50)


def test_filters_reads_a_small_first_page(make_scraper):
    scraper, client = make_scraper(lambda url, kw: SEARCH)
    values = scraper.filters("rtx 4070")
    assert client.calls[0][0] == "https://www.newegg.com/p/pl?d=rtx+4070&PageSize=36"
    assert any(v.n_value == 4131 for v in values)


def test_reviews(make_scraper):
    scraper, client = make_scraper(lambda url, kw: PRODUCT)
    reviews = scraper.reviews("9SIB3T1KEH4255")
    assert client.calls[0][0] == "https://www.newegg.com/p/9SIB3T1KEH4255"
    assert len(reviews) == 3
    assert reviews[0].title == "Great Card with Caveats"
