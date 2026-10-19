from __future__ import annotations

import pytest
from conftest import fixture_html, listing_html

from newegg_scraper import ParseError
from newegg_scraper.parsing import (
    clean,
    clean_url,
    extract_state,
    has_listing,
    has_product,
    highlights,
    offer_fields,
    offer_url,
    parse_filters,
    parse_listing,
    parse_product,
)

SEARCH = fixture_html("search_rtx_4070.html")
EMPTY = fixture_html("search_no_results.html")
PRODUCT = fixture_html("product_9SIB3T1KEH4255.html")
SEARCH_URL = "https://www.newegg.com/p/pl?d=rtx+4070&PageSize=96"
PRODUCT_URL = "https://www.newegg.com/p/9SIB3T1KEH4255"


def test_extract_state():
    assert extract_state("<html>nothing here</html>") is None
    assert extract_state("<script>window.__initialState__ = {broken</script>") is None
    html = '<script>window.__initialState__ = {"a": [1, "</b>"]};var x = 1;</script>'
    assert extract_state(html) == {"a": [1, "</b>"]}


def test_page_checks():
    assert has_listing(SEARCH) and has_listing(EMPTY)
    assert not has_listing(PRODUCT)
    assert has_product(PRODUCT)
    assert not has_product(SEARCH)
    assert not has_listing("<html><title>Are you a human?</title></html>")


def test_listing_page():
    page = parse_listing(SEARCH, SEARCH_URL)
    assert page.total_results == 1546
    assert page.title == "GeForce RTX 4070 GPUs / Video Graphics Cards"
    assert [p.position for p in page.products] == [1, 2, 3, 4, 5, 6, 7]
    assert page.has_more


def test_newegg_sold_product():
    first = parse_listing(SEARCH, SEARCH_URL).products[0]
    assert first.item_number == "14-126-761"
    assert first.title.startswith("ASUS PRIME GeForce RTX 5070 12GB")
    assert first.brand == "ASUS"
    assert first.model == "PRIME-RTX5070-12G"
    assert first.url == (
        "https://www.newegg.com/asus-prime-rtx5070-12g-geforce-rtx-5070-12gb-graphics-card"
        "-triple-fans/p/N82E16814126761"
    )
    assert first.price == 869.99
    assert first.was_price is None and first.savings is None
    assert first.currency == "USD"
    assert first.lowest_price_30_days == 849.99
    assert first.shipping == 0.0 and first.free_shipping
    assert first.in_stock
    assert first.condition == "New"
    assert first.rating == 4.5 and first.review_count == 176
    assert first.seller == "Newegg" and first.sold_by_newegg
    assert first.ship_from == "United States"
    assert not first.sponsored
    assert first.category == "GPUs / Video Graphics Cards"
    assert (first.all_offers_min, first.all_offers_max) == (869.99, 1499.99)
    assert first.release_date == "2025-02-24"
    assert first.highlights["Max Resolution"] == "7680 x 4320"
    assert first.highlights["Brand"] == "ASUS"
    assert first.image == "https://c1.neweggimages.com/productimage/nb640/14-126-761-01.png"


def test_marketplace_offer_with_instant_discount():
    offer = parse_listing(SEARCH, SEARCH_URL).products[1]
    assert offer.item_number == "9SIB3T1KEH4255"
    assert offer.price == 970.0
    assert offer.was_price == 999.0
    assert offer.savings == 29.0
    assert offer.savings_percent == 2
    assert offer.seller == "Techjunkie" and not offer.sold_by_newegg
    # The card links to the product group; Item= selects this seller's offer.
    assert offer.url.endswith("/p/N82E16814932683?Item=9SIB3T1KEH4255")


def test_sponsored_listing():
    ad = parse_listing(SEARCH, SEARCH_URL).products[2]
    assert ad.sponsored
    assert ad.price == 1554.0 and ad.was_price == 1849.0 and ad.savings_percent == 15
    assert "cm_sp" not in ad.url
    assert ad.url.endswith("/p/3D5-002D-000E7?Item=9SIAZBDK9U1163")


def test_used_and_refurbished_items():
    products = parse_listing(SEARCH, SEARCH_URL).products
    used, refurbished = products[5], products[6]
    assert used.condition == "Used - Like New"
    assert used.shipping == 29.99 and not used.free_shipping
    assert used.price == 699.99
    assert refurbished.item_number == "14-137-773T"
    assert refurbished.condition == "Refurbished"
    assert not refurbished.in_stock
    assert refurbished.price == 599.99
    assert refurbished.rating is None and refurbished.review_count == 0
    assert refurbished.lowest_price_30_days is None
    assert refurbished.url.endswith("/p/N82E16814137773T")


def test_listing_without_cards_builds_urls():
    page = parse_listing(listing_html([("14-126-761", 10.0)], 1), "https://www.newegg.ca/p/pl?d=x")
    assert page.products[0].url == "https://www.newegg.ca/p/N82E16814126761"
    assert not page.has_more


def test_empty_listing():
    page = parse_listing(EMPTY, "https://www.newegg.com/p/pl?d=zzqqxx")
    assert page.products == [] and page.total_results == 0
    assert not page.has_more


def test_listing_without_data_raises():
    with pytest.raises(ParseError):
        parse_listing("<html></html>", SEARCH_URL)


def test_filters():
    values = parse_filters(SEARCH)
    groups = {v.group for v in values}
    assert {"Category", "Sold by", "Brands", "Availability", "Condition"} <= groups
    by_name = {(v.group, v.name): v.n_value for v in values}
    assert by_name[("Category", "GPUs / Video Graphics Cards")] == 100007709
    assert by_name[("Sold by", "Newegg")] == 8000
    assert by_name[("Availability", "In Stock")] == 4131
    assert by_name[("Brands", "ASUS")] == 50001315
    assert ("Category", "Any Category") not in by_name


def test_product_page():
    detail = parse_product(PRODUCT, PRODUCT_URL)
    assert detail.item_number == "9SIB3T1KEH4255"
    assert detail.parent_item == "14-932-683"
    assert detail.title.endswith("GV-N407SWF3OC-12GD Video Card")
    assert "  " not in detail.title
    assert detail.brand == "GIGABYTE" and detail.model == "GV-N407SWF3OC-12GD"
    assert detail.upc == "889523041321"
    assert (detail.price, detail.was_price, detail.savings) == (970.0, 999.0, 29.0)
    assert detail.in_stock and detail.free_shipping
    assert (detail.all_offers_min, detail.all_offers_max) == (843.0, 1380.0)
    assert detail.rating == 4.5 and detail.review_count == 142
    assert detail.rating_histogram == {"5": 112, "4": 14, "3": 1, "2": 4, "1": 11}
    assert detail.seller == "Techjunkie" and detail.seller_rating == 4.3
    assert detail.seller_review_count == 477 and detail.seller_top_rated
    assert detail.breadcrumbs[-1] == "GPUs / Video Graphics Cards"
    assert detail.bullet_points[0] == "Powered by GeForce RTX 4070 SUPER"
    assert detail.specifications["Memory"]["Memory Size"] == "12GB"
    assert detail.specifications["Chipset"]["GPU"] == "GeForce RTX 4070 SUPER"
    assert detail.variant_options["Option"]["selected"] == "WindForce"
    assert "AORUS" in detail.variant_options["Option"]["choices"]
    assert detail.return_policy == "RamDeals Return Policy"
    assert (detail.refund_days, detail.replacement_days) == (90, 90)
    assert (detail.warranty_parts_days, detail.warranty_labor_days) == (1095, 1095)
    assert detail.manufacturer_support_url == "https://www.gigabyte.com/Support"
    assert len(detail.images) == 8
    assert detail.images[0] == "https://c1.neweggimages.com/productimage/nb640/14-932-683-11.jpg"
    assert detail.reviews_with_text == 68


def test_product_reviews_and_questions():
    detail = parse_product(PRODUCT, PRODUCT_URL)
    review = detail.reviews[0]
    assert review.item_number == "9SIB3T1KEH4255"
    assert review.title == "Great Card with Caveats"
    assert review.rating == 4
    assert review.date == "2024-02-05T19:44:35"
    assert review.author == "Reviewer 1"
    assert review.pros.startswith("The card has great performance")
    assert review.cons and review.comments
    assert review.purchased
    assert (review.helpful_votes, review.total_votes) == (19, 19)
    question = detail.questions[0]
    assert question.question.startswith("What cooling system")
    assert question.date == "2026-07-07"
    assert question.answer_count == 1
    assert question.best_answer.startswith("It uses the WINDFORCE cooling system")


def test_product_without_data_raises():
    with pytest.raises(ParseError):
        parse_product(SEARCH, PRODUCT_URL)


def test_ca_currency_is_passed_through():
    detail = parse_product(PRODUCT, "https://www.newegg.ca/p/9SIB3T1KEH4255", currency="CAD")
    assert detail.currency == "CAD"


def test_offer_fields_edge_cases():
    assert offer_fields({}) == {
        "price": None,
        "was_price": None,
        "savings": None,
        "savings_percent": None,
        "lowest_price_30_days": None,
        "shipping": None,
        "free_shipping": False,
        "in_stock": False,
        "rating": None,
        "review_count": 0,
        "seller": "Newegg",
        "sold_by_newegg": True,
        "ship_from": None,
        "all_offers_min": None,
        "all_offers_max": None,
    }
    fields = offer_fields({"UnitCost": "20", "InstantRebateAmount": 5, "ShippingCharge": 0})
    assert fields["price"] == 15.0 and fields["was_price"] == 20.0
    assert fields["savings_percent"] == 25
    assert fields["free_shipping"] and fields["shipping"] == 0.0


def test_helpers():
    assert clean("  Card&nbsp;12GB" + chr(160) + " <b>OC</b> ") == "Card 12GB OC"
    assert clean("   ") is None and clean(None) is None
    assert highlights("<b>Brand:</b> ASUS<br/><b>HDMI:</b> 1 x HDMI 2.1b<br/>") == {
        "Brand": "ASUS",
        "HDMI": "1 x HDMI 2.1b",
    }
    assert clean_url("//www.newegg.com/p/X?Item=Y&amp;cm_sp=SP-_-1#a") == (
        "https://www.newegg.com/p/X?Item=Y"
    )
    assert offer_url("https://www.newegg.com/a/p/N82E16814126761", "14-126-761").endswith(
        "/p/N82E16814126761"
    )
    assert offer_url("https://www.newegg.com/a/p/1FT-0004-008P2", "9SIC6E1M4Z3358").endswith(
        "?Item=9SIC6E1M4Z3358"
    )
    assert offer_url(
        "https://www.newegg.com/a/p/N82E16814126813?Item=N82E16814126813", "14-126-813"
    ) == ("https://www.newegg.com/a/p/N82E16814126813")
    assert offer_url("https://www.newegg.com/a/p/3D5-002D-000E7?Item=9SIAZBDK9U1163", "X") == (
        "https://www.newegg.com/a/p/3D5-002D-000E7?Item=9SIAZBDK9U1163"
    )
