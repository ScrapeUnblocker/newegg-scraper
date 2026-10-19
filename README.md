# Newegg Scraper

[![CI](https://github.com/ScrapeUnblocker/newegg-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/newegg-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-orange.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

Scrape **Newegg** into clean JSON or CSV: search results and category listings with prices, "was" prices, stock, ratings and sellers, plus full product pages with specifications, warranty, the rating histogram, customer reviews and Q&A. Built for GPU and PC-part price tracking, deal hunting and catalog research. It ships as a CLI and a Python library and reads both newegg.com (USD) and newegg.ca (CAD).

**Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos).** Every page is fetched through the ScrapeUnblocker `getPageSource` API, so you don't deal with blocks, CAPTCHAs or proxies yourself.

```bash
newegg-scraper search "rtx 5070" --category 100007709 --in-stock -f table
newegg-scraper search "ssd 2tb" --min-price 150 --sold-by-newegg --pages 3 -f csv -o ssd.csv
newegg-scraper product 14-126-761
newegg-scraper filters "rtx 5070" -f table
newegg-scraper --site ca search "ryzen 7 9800x3d" -f table
```

## Features

- **Search and category listings** (`search`): any keywords, any category or brand store, or any listing URL pasted from your browser. Each result has the item number, title, brand, model, **current price**, **was price, savings and savings percent** when an instant discount applies, Newegg's **lowest price in the last 30 days** (when it shows one), shipping cost / free shipping, **in-stock** flag, condition (New, Refurbished, Open Box, Used - Like New, ...), star rating and rating count, **seller** (Newegg or the marketplace seller) and ship-from country, sponsored flag, category, the price range across every seller of the same product, release date, key specs ("Max Resolution", "HDMI", "Chipset Manufacturer", ...), image and product URL.
- **Filters and sorting**: the six Newegg sort orders (featured, lowest/highest price, best selling, best rating, most reviews), Newegg's price filter, **in stock only**, **sold by Newegg only**, and every other filter a listing offers (brand, category, condition, ratings, promotions, ...) by its Newegg `N` value. `filters` lists those values for any search.
- **Paging**: up to 96 results per request, as many pages as you ask for. Repeats are dropped (Newegg shows some items twice, once as an ad), and sponsored listings can be left out.
- **Product pages** (`product`): everything above for one seller's offer, plus UPC, parent item, every **specification** group (Memory, Chipset, Ports, Dimensions, ...), bullet points, variant options (series, edition, capacity, ...), the **1-5 star rating histogram**, seller rating and review count, return policy with refund / replacement days, manufacturer warranty (parts and labor days), support URL, all product images, the first customer reviews (title, rating, date, pros, cons, comments, helpful votes, purchased flag) and shopper Q&A with the best answer.
- **newegg.com and newegg.ca**: `--site ca` reads the Canadian store, with prices in CAD and requests routed through Canada.
- **Robust**: retries with backoff on timeouts, transient errors and pages that come back without their data; a product that doesn't exist raises `NotFoundError`.
- Output as **JSON, JSON Lines, CSV or a terminal table**; typed dataclasses in Python.

## How it works

Newegg renders listing and product pages on the server and embeds the data behind them as one JSON object (`window.__initialState__`). The scraper reads that object instead of CSS classes: listings carry one record per result (in the page's sort order) plus the filter menus, and product pages carry the item, its seller, specifications, warranty, reviews and Q&A. Product links and condition labels come from the result cards. Each page is one request to ScrapeUnblocker's [`getPageSource`](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) endpoint; no browser rendering is needed.

Prices follow what Newegg displays: the current price is the list price minus any instant discount, and the list price becomes `was_price`. Requests go through the storefront's own country (US for newegg.com, Canada for newegg.ca), so prices, stock and shipping are the ones local shoppers see.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/newegg-scraper.git
cd newegg-scraper
python -m pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) and expose it as `SCRAPEUNBLOCKER_KEY` (see `.env.example`):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here
```

Requires Python 3.9+. The only runtime dependency is the official [`scrapeunblocker`](https://docs.scrapeunblocker.com/sdks/python?utm_source=github&utm_medium=integration&utm_campaign=example-repos) SDK.

## CLI usage

```text
newegg-scraper [--site us|ca] [--proxy-country auto] [--retries 3] [-v] COMMAND ...

  search   [KEYWORDS] [--category N] [--filter N[,N...]] [--url URL]
           [--sort featured|lowest-price|highest-price|best-selling|best-rating|most-reviews]
           [--min-price X] [--max-price Y] [--in-stock] [--sold-by-newegg]
           [--pages 1] [--max N] [--page-size 36|60|96] [--no-sponsored] [--keep-duplicates]
  product  ITEM_OR_URL [ITEM_OR_URL ...]
  reviews  ITEM_OR_URL
  filters  [KEYWORDS] [--category N] [--filter N] [--url URL]

every command: -f json|jsonl|csv|table  -o FILE
```

**Search** with keywords, a category, filters or a pasted URL:

```bash
# cheapest in-stock RTX 5070 cards that Newegg sells itself
newegg-scraper search "rtx 5070" --category 100007709 --sort lowest-price --in-stock --sold-by-newegg -f table

# 2 TB SSDs from $150, three pages of 96, to CSV
newegg-scraper search "ssd 2tb" --min-price 150 --pages 3 --no-sponsored -f csv -o ssd.csv

# best-selling ASUS graphics cards (category and brand by N value)
newegg-scraper search --category 100007709 --filter 50001315 --sort best-selling --max 50

# any listing URL from your browser (its filters are kept)
newegg-scraper search --url "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48" --pages 2
```

**Find filter values.** Newegg identifies every filter (category, brand, condition, ...) by a number. `filters` lists the ones a search offers:

```console
$ newegg-scraper filters "rtx 5070" -f table
group              N          value
Category           100007709  GPUs / Video Graphics Cards
Category           100897449  Gaming Desktop PC
Category           100167748  Gaming Laptops
Sold by            8000       Newegg
Brands             50001314   GIGABYTE
Brands             50001315   ASUS
Brands             50001312   MSI
...
```

**Products and reviews** take an item number (`14-126-761`, `9SIB3T1KEH4255`), the code from a product URL (`N82E16814126761`) or a full URL:

```bash
newegg-scraper product 14-126-761
newegg-scraper product 14-126-761 20-147-923 -f csv -o products.csv
newegg-scraper reviews 14-126-761 -f table
newegg-scraper --site ca product 19-113-877
```

## Library usage

```python
from newegg_scraper import NeweggScraper, SearchQuery

newegg = NeweggScraper()  # reads SCRAPEUNBLOCKER_KEY; NeweggScraper(site="ca") for newegg.ca

# Keywords only...
cards = newegg.search("rtx 5070")

# ...or a full query: category, filters, price range, sort, stock, seller.
query = SearchQuery(
    "rtx 5070",
    category=100007709,  # GPUs / Video Graphics Cards
    sort="lowest-price",
    in_stock=True,
    sold_by_newegg=True,
    max_price=1000,
)
for card in newegg.search(query, max_pages=2, sponsored=False):
    print(card.price, card.was_price, card.seller, card.title)

# Filter values for a search: [FilterValue(group="Brands", name="ASUS", n_value=50001315), ...]
brands = [f for f in newegg.filters("rtx 5070") if f.group == "Brands"]

# One product page
gpu = newegg.product("14-126-761")
gpu.price, gpu.in_stock, gpu.rating, gpu.rating_histogram
gpu.specifications["Chipset"]["GPU"]  # 'GeForce RTX 5070'
gpu.warranty_parts_days, gpu.return_policy
for review in gpu.reviews:
    print(review.rating, review.title, review.helpful_votes)
```

`NeweggScraper` options: `site` (`us` or `ca`), `proxy_country` (`"auto"` matches the site, `None` lets the API choose), `max_retries`, `backoff`, `timeout`, or a ready `client`. `scraper.requests` counts the API requests made.

## Example output

`newegg-scraper search "rtx 5070" --category 100007709 --in-stock --max 1` (one product, key specs trimmed):

```json
[
  {
    "position": 1,
    "item_number": "14-126-813",
    "title": "ASUS PRIME GeForce RTX 5070 DLSS 4.0 Graphics Card PRIME-RTX5070-O12G-WHITE",
    "url": "https://www.newegg.com/asus-prime-rtx5070-o12g-white-geforce-rtx-5070-12gb-graphics-card-triple-fans/p/N82E16814126813",
    "brand": "ASUS",
    "model": "PRIME-RTX5070-O12G-WHITE",
    "price": 919.99,
    "was_price": null,
    "savings": null,
    "savings_percent": null,
    "currency": "USD",
    "lowest_price_30_days": null,
    "shipping": 0.0,
    "free_shipping": true,
    "in_stock": true,
    "condition": "New",
    "rating": 4.5,
    "review_count": 176,
    "seller": "Newegg",
    "sold_by_newegg": true,
    "ship_from": "United States",
    "sponsored": false,
    "category": "GPUs / Video Graphics Cards",
    "all_offers_min": 919.99,
    "all_offers_max": 1159.99,
    "release_date": null,
    "highlights": {
      "Core Clock": "OC mode: 2587MHz Default mode: 2557MHz (Boost Clock)",
      "Max Resolution": "7680 x 4320",
      "DisplayPort": "3 x DisplayPort 2.1b",
      "HDMI": "1 x HDMI 2.1b",
      "Slot Width": "2.5 Slots"
    },
    "image": "https://c1.neweggimages.com/productimage/nb640/14-126-813-02.png"
  }
]
```

`newegg-scraper --site ca search "ryzen 7 9800x3d" --max 3 -f table` (prices in CAD):

```text
#  item            price      was      stock     rating  reviews  seller            title
1  19-113-877      $619.99    $799.99  in stock  4.8     731      Newegg            AMD Ryzen 7 9800X3D - Ryzen 7 9000 Series Zen 5 8-Core 5....
2  9SIADDZKJV7483  $828.56             in stock  5.0     1        Corn Electronics  AMD Ryzen 7 9800X3D - Ryzen 7 9000 Series 8-Core Socket A...
3  9SIADDZKJV7488  $928.56             in stock  5.0     1        Corn Electronics  AMD Ryzen 7 9800X3D - Ryzen 7 9000 Series Zen 5 8-Core 5....
```

A product page (`newegg-scraper product 20-147-923`, abridged):

```json
{
  "item_number": "20-147-923",
  "title": "Samsung Internal SSD 990 2TB, Read/Write Speeds Up to 7,250/6,450 MB/s NVMe Internal Solid State Drive ...",
  "brand": "SAMSUNG",
  "model": "MZ-V9V2T0B/AM",
  "upc": "198957280801",
  "price": 329.99,
  "was_price": 529.99,
  "savings": 200.0,
  "savings_percent": 37,
  "lowest_price_30_days": 329.99,
  "in_stock": true,
  "rating": 4.8,
  "review_count": 24,
  "rating_histogram": {"5": 20, "4": 4, "3": 0, "2": 0, "1": 0},
  "seller": "Newegg",
  "breadcrumbs": ["Components & Storage", "SSD", "Internal SSDs"],
  "specifications": {"Model": {"Brand": "SAMSUNG", "...": "..."}, "Performance": {"...": "..."}},
  "reviews": [{"title": "Great product", "rating": 5, "date": "2026-10-07T11:58:32", "...": "..."}],
  "questions": [{"question": "...", "best_answer": "...", "...": "..."}]
}
```

## Examples

```bash
python examples/price_tracker.py "rtx 5070" --category 100007709   # append today's prices to a CSV history
python examples/product_report.py 14-126-761                        # one-page product report + full JSON
python examples/category_deals.py --category 100007709 --min-savings 10   # discounted items -> deals.csv
```

## Notes and limits

- **Requests:** every listing page and every product page is one API request. A search reads `--pages` pages of up to 96 results (plus any sponsored listings Newegg adds), and stops early when the results run out.
- **Relevance:** keyword search is Newegg's own. A sort like `lowest-price` on a broad search can surface accessories (cables, brackets); add `--category` to keep a search on target.
- **Prices:** `price` is what the listing shows today; for out-of-stock items it is Newegg's last price. `lowest_price_30_days` is only set when Newegg provides it. `shipping` is `0.0` for free shipping and `null` when Newegg does not say.
- **Offers:** a product can be sold by Newegg and by marketplace sellers. Each listing result is one offer, and its `url` opens that offer. `all_offers_min` / `all_offers_max` span all of them.
- **Reviews:** a product page carries its first page of customer reviews (usually 8) plus the full rating histogram and counts; `reviews_with_text` is the total number of written reviews.
- **Filter values** (`N` numbers) such as `4131` (in stock) and `8000` (sold by Newegg) work on both storefronts; brand values are `50000000 + brand ID`. Use `filters` to look up the rest.
- Scrape responsibly: collect public data at a reasonable rate and follow Newegg's terms and the laws that apply to you.

## Project layout

```text
newegg-scraper/
├── src/newegg_scraper/
│   ├── __init__.py      # public API + __version__
│   ├── scraper.py       # NeweggScraper: fetch + retry, paging, dedupe
│   ├── parsing.py       # window.__initialState__ + result cards -> Product / ProductDetail
│   ├── urls.py          # SearchQuery -> listing URL, item numbers -> product URLs
│   ├── models.py        # dataclasses
│   ├── errors.py        # exceptions
│   ├── export.py        # JSON / JSONL / CSV / table writers
│   └── cli.py           # `newegg-scraper` command
├── examples/            # runnable scripts
├── tests/               # offline tests (mocked client + trimmed real pages)
├── pyproject.toml
├── requirements.txt
├── Makefile
└── .env.example
```

## Development

```bash
make install   # pip install -e ".[dev]"
make lint      # ruff check . && ruff format --check .
make format    # ruff format .
make test      # pytest -q
```

The tests run fully offline. They use a fake client and trimmed snapshots of real Newegg pages (reviewer names replaced), so they cost no API credits. CI runs lint and tests on Python 3.9 and 3.12.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos): web scraping API that handles blocks, CAPTCHAs and rendering
- [Documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
- [Python SDK](https://docs.scrapeunblocker.com/sdks/python?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

## License

[MIT](LICENSE). Copyright (c) 2026 ScrapeUnblocker.
