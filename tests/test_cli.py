from __future__ import annotations

import argparse
import csv
import io
import json

import pytest
from conftest import FakeClient, TargetNotFoundError, fixture_html

from newegg_scraper import NeweggScraper, cli


def parse(*argv: str) -> argparse.Namespace:
    return cli.build_parser().parse_args(list(argv))


def test_search_arguments_build_a_query():
    args = parse(
        "--site", "ca", "search", "rtx", "4070", "--category", "100007709",
        "--filter", "50001315,50001314", "--filter", "4814", "--sort", "lowest-price",
        "--min-price", "500", "--max-price", "799.99", "--in-stock", "--sold-by-newegg",
        "--pages", "3", "--max", "120", "--page-size", "60", "--no-sponsored",
    )  # fmt: skip
    query = cli.query_from_args(args)
    assert query.keywords == "rtx 4070" and query.site == "ca"
    assert query.category == 100007709
    assert query.filters == [50001315, 50001314, 4814]
    assert query.sort == "lowest-price"
    assert (query.min_price, query.max_price) == (500.0, 799.99)
    assert query.in_stock and query.sold_by_newegg
    assert (args.pages, args.max_results, args.page_size) == (3, 120, 60)
    assert args.no_sponsored and not args.keep_duplicates


def test_defaults():
    args = parse("search", "ssd")
    assert args.site == "us" and args.proxy_country == "auto" and args.retries == 3
    assert args.pages == 1 and args.max_results is None and args.page_size == 96
    assert args.format == "json" and args.sort is None
    filters = cli.query_from_args(parse("filters", "--url", "https://www.newegg.com/p/pl?N=4131"))
    assert filters.url and filters.sort is None and not filters.in_stock


@pytest.mark.parametrize(
    "argv",
    [
        ("search", "ssd", "--sort", "cheapest"),
        ("search", "ssd", "--filter", "brand-asus"),
        ("search", "ssd", "--filter", ","),
        ("search", "ssd", "--pages", "0"),
        ("search", "ssd", "--pages", "101"),
        ("search", "ssd", "--page-size", "50"),
        ("search", "ssd", "--min-price", "-5"),
        ("search", "ssd", "--max-price", "cheap"),
        ("--site", "uk", "search", "ssd"),
        ("product",),
    ],
)
def test_bad_arguments_exit(argv):
    with pytest.raises(SystemExit):
        parse(*argv)


@pytest.fixture
def fake_scraper(monkeypatch):
    """Route the CLI to a scraper whose client answers from fixtures."""

    def responder(url, kw):
        if "/p/pl" in url:
            return fixture_html("search_rtx_4070.html")
        if "14-999-999" in url or "N82E16814999999" in url:
            return TargetNotFoundError("404")
        return fixture_html("product_9SIB3T1KEH4255.html")

    client = FakeClient(responder)

    def make(args):
        return NeweggScraper(client=client, site=args.site, sleep=lambda s: None)

    monkeypatch.setattr(cli, "make_scraper", make)
    return client


def test_main_search_writes_json(fake_scraper, capsys):
    assert cli.main(["search", "rtx 4070", "--in-stock"]) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert len(data) == 6 and data[0]["item_number"] == "14-126-761"
    assert data[1]["was_price"] == 999.0
    assert "6 products, 1 requests" in err
    assert "N=4131" in fake_scraper.calls[-1][0]


def test_main_search_table_and_csv(fake_scraper, capsys, tmp_path):
    assert cli.main(["search", "rtx 4070", "--no-sponsored", "-f", "table"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["#", "item", "price", "was", "stock", "rating", "reviews",
                                "seller", "title"]  # fmt: skip
    assert "$869.99" in lines[1] and "Newegg" in lines[1]
    assert "[ad]" not in "\n".join(lines)
    out = tmp_path / "gpus.csv"
    assert cli.main(["search", "rtx 4070", "-f", "csv", "-o", str(out)]) == 0
    rows = list(csv.DictReader(io.StringIO(out.read_text(encoding="utf-8"))))
    assert len(rows) == 6 and rows[0]["price"] == "869.99"
    assert json.loads(rows[0]["highlights"])["Brand"] == "ASUS"


def test_main_product_and_reviews(fake_scraper, capsys):
    assert cli.main(["product", "9SIB3T1KEH4255"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["seller"] == "Techjunkie" and data["specifications"]["Memory"]["Memory Size"]
    assert cli.main(["product", "9SIB3T1KEH4255", "14-932-683", "-f", "table"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 3
    assert cli.main(["reviews", "9SIB3T1KEH4255", "-f", "table"]) == 0
    out, err = capsys.readouterr()
    assert "Great Card with Caveats" in out and "3 reviews, 1 requests" in err


def test_main_filters_table(fake_scraper, capsys):
    assert cli.main(["filters", "rtx 4070", "-f", "table"]) == 0
    out = capsys.readouterr().out
    assert "Availability" in out and "4131" in out and "In Stock" in out


def test_main_ca_site(fake_scraper, capsys):
    assert cli.main(["--site", "ca", "search", "rtx 4070", "--max", "1"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["currency"] == "CAD"
    assert fake_scraper.calls[-1][0].startswith("https://www.newegg.ca/")


def test_main_reports_errors(fake_scraper, capsys):
    assert cli.main(["product", "14-999-999"]) == 1
    assert "Newegg has no page at" in capsys.readouterr().err
    assert cli.main(["search"]) == 1
    assert "give keywords" in capsys.readouterr().err
    assert cli.main(["-v", "search", "ssd", "--min-price", "9", "--max-price", "1"]) == 1
    assert "above max price" in capsys.readouterr().err
