"""Find discounted items in a Newegg category and export them to CSV.

Reads a few result pages of a category (100007709 is "GPUs / Video Graphics
Cards"; run `newegg-scraper filters "<keywords>"` to find others) and keeps
in-stock items with an instant discount of at least --min-savings percent.

    python examples/category_deals.py --category 100007709 --min-savings 10
"""

from __future__ import annotations

import argparse

from newegg_scraper import NeweggScraper, SearchQuery
from newegg_scraper.export import write


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--category", type=int, default=100007709)
    parser.add_argument("--min-savings", type=int, default=10, help="percent")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--output", default="deals.csv")
    args = parser.parse_args()

    newegg = NeweggScraper()  # reads SCRAPEUNBLOCKER_KEY
    query = SearchQuery(category=args.category, in_stock=True, sort="best-selling")
    products = newegg.search(query, max_pages=args.pages, sponsored=False)
    deals = [p for p in products if (p.savings_percent or 0) >= args.min_savings]
    deals.sort(key=lambda p: p.savings_percent or 0, reverse=True)

    write(deals, "csv", args.output)
    print(f"{len(deals)} of {len(products)} items save {args.min_savings}%+ -> {args.output}")
    for deal in deals[:5]:
        print(f"  -{deal.savings_percent}%  ${deal.price:,.2f}  {deal.title[:70]}")


if __name__ == "__main__":
    main()
