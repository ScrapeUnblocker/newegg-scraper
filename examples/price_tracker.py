"""Track Newegg prices over time: append today's prices to a CSV history file.

Run it once a day (cron, Task Scheduler, a GitHub Action) and the CSV grows into
a price history you can chart or alert on. Results come in Newegg's relevance
order; --category keeps accessories out (100007709 is "GPUs / Video Graphics
Cards", `newegg-scraper filters "<keywords>"` lists the others).

    python examples/price_tracker.py "rtx 5070" --category 100007709 --history rtx5070.csv
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone

from newegg_scraper import NeweggScraper, SearchQuery

COLUMNS = ["checked_at", "item_number", "title", "price", "was_price", "in_stock", "seller", "url"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("keywords")
    parser.add_argument("--category", type=int, help="a category N value")
    parser.add_argument("--history", default="price_history.csv")
    parser.add_argument("--max", type=int, default=30, help="products to track")
    args = parser.parse_args()

    newegg = NeweggScraper()  # reads SCRAPEUNBLOCKER_KEY
    query = SearchQuery(args.keywords, category=args.category, in_stock=True)
    products = newegg.search(query, max_results=args.max, sponsored=False)

    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_file = not os.path.exists(args.history)
    with open(args.history, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        for product in products:
            writer.writerow({**product.to_dict(), "checked_at": checked_at})

    cheapest = min((p for p in products if p.price), key=lambda p: p.price, default=None)
    print(f"appended {len(products)} prices to {args.history}")
    if cheapest:
        print(f"cheapest: ${cheapest.price:,.2f}  {cheapest.title[:70]}")
        print(f"          {cheapest.url}")


if __name__ == "__main__":
    main()
