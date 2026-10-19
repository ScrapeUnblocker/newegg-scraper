from __future__ import annotations

import csv
import io
import json

import pytest
from conftest import fixture_html

from newegg_scraper.export import render, to_csv, to_table, write
from newegg_scraper.models import Question
from newegg_scraper.parsing import parse_filters, parse_listing, parse_product

SEARCH = fixture_html("search_rtx_4070.html")


@pytest.fixture(scope="module")
def products():
    return parse_listing(SEARCH, "u").products


@pytest.fixture(scope="module")
def detail():
    return parse_product(fixture_html("product_9SIB3T1KEH4255.html"), "u")


def test_json_and_jsonl(products):
    data = json.loads(render(products, "json"))
    assert data[0]["item_number"] == "14-126-761"
    lines = render(products, "jsonl").splitlines()
    assert len(lines) == len(products)
    assert json.loads(lines[1])["seller"] == "Techjunkie"


def test_csv_flattens_lists_and_dicts(products, detail):
    rows = list(csv.DictReader(io.StringIO(to_csv(products))))
    assert len(rows) == len(products) and rows[1]["savings"] == "29.0"
    assert rows[0]["was_price"] == "" and rows[0]["sponsored"] == "False"
    row = next(csv.DictReader(io.StringIO(to_csv([detail]))))
    assert row["bullet_points"].startswith("Powered by GeForce RTX 4070 SUPER | ")
    assert json.loads(row["specifications"])["Memory"]["Memory Type"] == "GDDR6X"
    assert json.loads(row["reviews"])[0]["rating"] == 4
    assert to_csv([]) == ""


def test_tables(products, detail):
    lines = to_table(products).splitlines()
    assert "$970.00" in lines[2] and "$999.00" in lines[2] and "Techjunkie" in lines[2]
    assert "[ad]" in lines[3]
    assert "out" in lines[7] and "-" in lines[7].split()
    assert "Techjunkie" in to_table([detail]).splitlines()[1]
    filters = to_table(parse_filters(SEARCH)).splitlines()
    assert filters[0].split() == ["group", "N", "value"]
    assert to_table([]) == "(no results)\n"
    with pytest.raises(ValueError):
        to_table([Question("q?", None)])


def test_single_object_and_errors(products, detail, tmp_path):
    assert json.loads(render(detail, "json"))["upc"] == "889523041321"
    with pytest.raises(ValueError):
        render(products, "xml")
    path = tmp_path / "gpus.csv"
    write(products, "csv", str(path))
    text = path.read_text(encoding="utf-8")
    assert "ASUS PRIME GeForce RTX 5070" in text and "\r\n" not in text
    stream = io.StringIO()
    write(products[:1], "jsonl", stream=stream)
    assert json.loads(stream.getvalue())["price"] == 869.99
