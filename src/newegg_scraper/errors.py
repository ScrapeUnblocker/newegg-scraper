"""Errors raised by the scraper."""

from __future__ import annotations


class NeweggError(Exception):
    """Base class for scraper errors."""


class ParseError(NeweggError):
    """The page came back without the data Newegg normally puts in it."""


class NotFoundError(NeweggError, LookupError):
    """Newegg has no page at that address (HTTP 404), e.g. an unknown item number."""
