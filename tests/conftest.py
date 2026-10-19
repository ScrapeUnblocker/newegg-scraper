"""Shared test helpers: real (trimmed) Newegg pages and a fake ScrapeUnblocker client.

The fixtures in ``tests/fixtures/`` are real Newegg responses cut down to the parts
the parsers read: the ``window.__initialState__`` JSON (with fewer products,
filters and reviews) and the matching result cards. Reviewer names are replaced.
No test calls the API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def listing_html(items: list[tuple[str, float]], total: int, sponsored: tuple[str, ...] = ()):
    """A minimal listing page with one product per ``(item number, price)``."""
    products = [
        {
            "ProductNumber": item,
            "SponsoredMsg": {"Position": 1} if item in sponsored else None,
            "ItemCell": {
                "Item": item,
                "UnitCost": price,
                "InstantRebateAmount": 0,
                "ShippingCharge": 0.01,
                "Instock": True,
                "Description": {"Title": f"Product {item}"},
                "Review": {"HumanRating": 0},
                "Seller": {"SellerName": None},
            },
        }
        for item, price in items
    ]
    state = {"Products": products, "TotalItemCount": total, "PageInfo": {"H1TagText": "Test"}}
    return f"<html><script>window.__initialState__ = {json.dumps(state)};</script></html>"


class ScrapeTimeoutError(Exception):
    """Same class name as the SDK's timeout error (matched by name)."""


class TargetNotFoundError(Exception):
    """Same class name as the SDK's error for a target that answers 404."""


class AuthenticationError(Exception):
    pass


class FakeClient:
    """Stands in for ``scrapeunblocker.Client``; ``responder(url, kwargs)`` returns HTML.

    A responder may also return an exception instance, which is raised instead.
    """

    def __init__(self, responder: Callable[[str, dict[str, Any]], Any]):
        self.responder = responder
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_page_source(self, url: str, **kwargs: Any) -> str:
        self.calls.append((url, kwargs))
        result = self.responder(url, kwargs)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture
def make_scraper():
    """Build a :class:`NeweggScraper` around a :class:`FakeClient` (no sleeping)."""
    from newegg_scraper import NeweggScraper

    def build(responder, **kwargs):
        client = FakeClient(responder)
        sleeps: list[float] = []
        scraper = NeweggScraper(client=client, sleep=sleeps.append, **kwargs)
        scraper.sleeps = sleeps  # type: ignore[attr-defined]
        return scraper, client

    return build
