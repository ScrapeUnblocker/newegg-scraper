"""Print a one-page report on a Newegg product and save the full details as JSON.

python examples/product_report.py 14-126-761
python examples/product_report.py "https://www.newegg.com/p/N82E16820147923"
"""

from __future__ import annotations

import json
import sys

from newegg_scraper import NeweggScraper


def main() -> None:
    ref = sys.argv[1] if len(sys.argv) > 1 else "14-126-761"
    product = NeweggScraper().product(ref)

    price = f"${product.price:,.2f}" if product.price else "n/a"
    if product.was_price:
        price += f" (was ${product.was_price:,.2f}, save {product.savings_percent}%)"
    print(product.title)
    print(f"  {product.url}")
    stock = "in stock" if product.in_stock else "out of stock"
    print(f"  price     {price} {product.currency}, {stock}")
    print(f"  seller    {product.seller} (ships from {product.ship_from or 'n/a'})")
    print(f"  rating    {product.rating or '-'} from {product.review_count} ratings")
    for stars, count in product.rating_histogram.items():
        bar = "#" * round(40 * count / max(product.review_count, 1))
        print(f"    {stars} stars {count:>5}  {bar}")
    print(f"  returns   {product.return_policy or 'n/a'}")
    for group, rows in list(product.specifications.items())[:4]:
        print(f"  [{group}]")
        for key, value in rows.items():
            print(f"    {key}: {value}")
    if product.reviews:
        top = product.reviews[0]
        print(f'  review    {top.rating}/5 "{top.title}" ({top.helpful_votes} found it helpful)')

    path = f"newegg_{product.item_number}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(product.to_dict(), handle, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    main()
