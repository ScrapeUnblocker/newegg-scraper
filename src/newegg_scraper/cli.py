"""``newegg-scraper`` command line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .export import FORMATS, write
from .urls import DEFAULT_PAGE_SIZE, PAGE_SIZES, SITES, SORTS, SearchQuery

EXAMPLES = """\
examples:
  newegg-scraper search "rtx 4070" -f table
  newegg-scraper search "rtx 4070" --sort lowest-price --in-stock --sold-by-newegg -f table
  newegg-scraper search "ssd 2tb" --min-price 80 --max-price 200 --pages 3 -f csv -o ssd.csv
  newegg-scraper search --category 100007709 --filter 50001315 --sort best-selling --max 50
  newegg-scraper search --url "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48"
  newegg-scraper --site ca search "ryzen 7 9800x3d" -f table
  newegg-scraper filters "rtx 4070" -f table
  newegg-scraper product 14-126-761
  newegg-scraper product 9SIB3T1KEH4255 N82E16814126761 -f csv -o gpus.csv
  newegg-scraper reviews 14-126-761 -f table
"""


def n_values(text: str) -> list[int]:
    """``50001315`` or ``50001315,4131``: Newegg filter (N) values."""
    values = []
    for part in text.replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise argparse.ArgumentTypeError(f"filter values are numbers, got {part!r}")
        values.append(int(part))
    if not values:
        raise argparse.ArgumentTypeError("expected one or more filter numbers")
    return values


def bounded(low: int, high: int):
    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return value

    return parse


def money(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a price: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("prices cannot be negative")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="newegg-scraper",
        description=(
            "Scrape Newegg search results, category listings and product pages into "
            "JSON/CSV via the ScrapeUnblocker API."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--site",
        default="us",
        choices=list(SITES),
        help="storefront: us = newegg.com, ca = newegg.ca (default: us)",
    )
    parser.add_argument(
        "--proxy-country",
        default="auto",
        help="route requests through this country (default: auto = the site's country; "
        '"" lets the API choose)',
    )
    parser.add_argument("--retries", type=int, default=3, help="retries per request (default 3)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log retries to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="search results or a category listing")
    _listing_args(search)
    search.add_argument("--sort", choices=list(SORTS), help="default: Newegg's featured order")
    search.add_argument("--min-price", type=money, help="Newegg's price filter, lower end")
    search.add_argument("--max-price", type=money, help="Newegg's price filter, upper end")
    search.add_argument("--in-stock", action="store_true", help="only items in stock")
    search.add_argument(
        "--sold-by-newegg", action="store_true", help="only items Newegg sells itself"
    )
    search.add_argument(
        "--pages", type=bounded(1, 100), default=1, help="result pages to read (default 1)"
    )
    search.add_argument(
        "--max", type=bounded(1, 10000), dest="max_results", help="stop after this many products"
    )
    search.add_argument(
        "--page-size",
        type=int,
        choices=PAGE_SIZES,
        default=DEFAULT_PAGE_SIZE,
        help=f"results per page (default {DEFAULT_PAGE_SIZE})",
    )
    search.add_argument("--no-sponsored", action="store_true", help="drop the sponsored listings")
    search.add_argument(
        "--keep-duplicates", action="store_true", help="keep repeats of the same item"
    )
    _output_args(search)

    product = sub.add_parser("product", help="full details of one or more products")
    product.add_argument(
        "items", nargs="+", metavar="ITEM_OR_URL", help="e.g. 14-126-761, 9SIB3T1KEH4255, a URL"
    )
    _output_args(product)

    reviews = sub.add_parser("reviews", help="the customer reviews on a product page")
    reviews.add_argument("item", metavar="ITEM_OR_URL")
    _output_args(reviews)

    filters = sub.add_parser("filters", help="filter values (N numbers) a listing offers")
    _listing_args(filters)
    _output_args(filters)
    return parser


def _listing_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("keywords", nargs="*", help='search words, e.g. "rtx 4070"')
    parser.add_argument(
        "--category", type=int, metavar="N", help="a category's N value (see `filters`)"
    )
    parser.add_argument(
        "--filter",
        type=n_values,
        action="append",
        default=[],
        metavar="N[,N...]",
        help="filter values from `filters` (brand, condition, ...); repeatable",
    )
    parser.add_argument("--url", help="a Newegg listing URL copied from your browser")


def _output_args(parser: argparse.ArgumentParser, default: str = "json") -> None:
    parser.add_argument("-f", "--format", default=default, choices=FORMATS)
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")


def query_from_args(args: argparse.Namespace) -> SearchQuery:
    return SearchQuery(
        keywords=" ".join(args.keywords),
        category=args.category,
        filters=[n for group in args.filter for n in group],
        sort=getattr(args, "sort", None),
        min_price=getattr(args, "min_price", None),
        max_price=getattr(args, "max_price", None),
        in_stock=getattr(args, "in_stock", False),
        sold_by_newegg=getattr(args, "sold_by_newegg", False),
        site=args.site,
        url=args.url,
    )


def make_scraper(args: argparse.Namespace):
    from .scraper import NeweggScraper

    return NeweggScraper(
        site=args.site, proxy_country=args.proxy_country or None, max_retries=args.retries
    )


def _emit(items: Any, args: argparse.Namespace) -> None:
    write(items, args.format, args.output)


def run(args: argparse.Namespace) -> int:
    scraper = make_scraper(args)
    if args.command == "search":
        products = scraper.search(
            query_from_args(args),
            max_results=args.max_results,
            max_pages=args.pages,
            page_size=args.page_size,
            sponsored=not args.no_sponsored,
            dedupe=not args.keep_duplicates,
        )
        _emit(products, args)
        print(f"{len(products)} products, {scraper.requests} requests", file=sys.stderr)
    elif args.command == "product":
        details = [scraper.product(item) for item in args.items]
        _emit(details[0] if len(details) == 1 and args.format == "json" else details, args)
    elif args.command == "reviews":
        found = scraper.reviews(args.item)
        _emit(found, args)
        print(f"{len(found)} reviews, {scraper.requests} requests", file=sys.stderr)
    elif args.command == "filters":
        _emit(scraper.filters(query_from_args(args)), args)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.basicConfig(format="%(levelname)s %(message)s")
        logging.getLogger("newegg_scraper").setLevel(logging.INFO)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - report any failure as one clean line
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
