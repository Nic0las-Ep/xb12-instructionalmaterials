"""
Look up textbook metadata from reliable public book registries by ISBN.

Sources (queried in order, results merged):
  1. ISBNdb API         - title, authors, publisher, and list price (MSRP).
                          Requires ISBNDB_API_KEY; this is the only source that
                          reliably carries textbook pricing.
  2. Google Books API   - title, authors, publisher, date, description, price
                          (retail price is often absent for textbooks).
  3. Open Library API   - title, authors, publisher, date  (fallback / fill-in)

Uses only the Python standard library (urllib) so no bundled deps are needed.
"""

import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error

# Fields the application expects for a complete textbook record.
REQUIRED_FIELDS = ("title", "author", "publisher", "price")

# Optional paid price source (ISBNdb). When no key is configured the lookup
# simply falls back to the free sources and the UI prompts for the price.
ISBNDB_API_KEY = os.environ.get("ISBNDB_API_KEY", "")
ISBNDB_BASE = os.environ.get("ISBNDB_BASE", "https://api2.isbndb.com")


def _normalize_isbn(isbn):
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def _get_json(url, timeout=8, headers=None):
    base = {"User-Agent": "xb12-registry/1.0"}
    if headers:
        base.update(headers)
    req = urllib.request.Request(url, headers=base)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None


def _parse_price(value):
    """Extract a numeric price from an ISBNdb msrp value (number or string)."""
    if value in (None, "", 0, "0", "0.00"):
        return None
    try:
        amount = float(str(value).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    return amount if amount > 0 else None


def _from_isbndb(isbn):
    """Query ISBNdb for metadata + list price. Requires ISBNDB_API_KEY."""
    if not ISBNDB_API_KEY:
        return {}
    url = f"{ISBNDB_BASE.rstrip('/')}/book/{urllib.parse.quote(isbn)}"
    data = _get_json(url, headers={"Authorization": ISBNDB_API_KEY})
    book = (data or {}).get("book") or {}
    if not book:
        return {}
    result = {
        "title": book.get("title") or book.get("title_long"),
        "author": ", ".join(book.get("authors", []) or []) or None,
        "publisher": book.get("publisher"),
        "publishedDate": book.get("date_published"),
        "description": book.get("synopsis"),
        "source": "isbndb",
    }
    price = _parse_price(book.get("msrp"))
    if price is not None:
        result["price"] = price
        result["currency"] = "USD"
        result["priceSource"] = "isbndb (MSRP)"
    return {k: v for k, v in result.items() if v is not None}


def _from_google_books(isbn):
    url = "https://www.googleapis.com/books/v1/volumes?q=" + urllib.parse.quote(
        f"isbn:{isbn}"
    )
    data = _get_json(url)
    if not data or not data.get("items"):
        return {}
    item = data["items"][0]
    info = item.get("volumeInfo", {}) or {}
    sale = item.get("saleInfo", {}) or {}

    result = {
        "title": info.get("title"),
        "author": ", ".join(info.get("authors", []) or []) or None,
        "publisher": info.get("publisher"),
        "publishedDate": info.get("publishedDate"),
        "description": info.get("description"),
        "pageCount": info.get("pageCount"),
        "categories": info.get("categories"),
        "source": "googleBooks",
    }

    list_price = (sale.get("listPrice") or {})
    retail_price = (sale.get("retailPrice") or {})
    price = retail_price.get("amount") or list_price.get("amount")
    if price is not None:
        result["price"] = price
        result["currency"] = retail_price.get("currencyCode") or list_price.get(
            "currencyCode"
        )
    return {k: v for k, v in result.items() if v is not None}


def _from_open_library(isbn):
    url = (
        "https://openlibrary.org/api/books?bibkeys=ISBN:"
        + urllib.parse.quote(isbn)
        + "&format=json&jscmd=data"
    )
    data = _get_json(url)
    key = f"ISBN:{isbn}"
    if not data or key not in data:
        return {}
    rec = data[key]
    result = {
        "title": rec.get("title"),
        "author": ", ".join(a.get("name", "") for a in rec.get("authors", []) or [])
        or None,
        "publisher": ", ".join(
            p.get("name", "") for p in rec.get("publishers", []) or []
        )
        or None,
        "publishedDate": rec.get("publish_date"),
        "url": rec.get("url"),
        "source": "openLibrary",
    }
    return {k: v for k, v in result.items() if v}


def lookup_isbn(isbn):
    """
    Return {"found": bool, "isbn": str, "metadata": {...}, "missingFields": [...],
            "sources": [...]}.
    """
    clean = _normalize_isbn(isbn)
    if not clean or len(clean) not in (10, 13):
        return {
            "found": False,
            "isbn": clean,
            "metadata": {},
            "missingFields": list(REQUIRED_FIELDS),
            "sources": [],
            "error": "Invalid ISBN. Provide a 10- or 13-digit ISBN.",
        }

    merged = {}
    sources = []

    # 1) ISBNdb first - it is the reliable source for list price (MSRP).
    isbndb = _from_isbndb(clean)
    if isbndb:
        sources.append("isbndb")
        merged.update(isbndb)

    # 2) Google Books - fills any gaps; only sets price if not already known.
    google = _from_google_books(clean)
    if google:
        sources.append("googleBooks")
        for k, v in google.items():
            merged.setdefault(k, v)

    # 3) Open Library - final fallback for bibliographic fields.
    openlib = _from_open_library(clean)
    if openlib:
        sources.append("openLibrary")
        for k, v in openlib.items():
            merged.setdefault(k, v)

    merged.pop("source", None)
    merged["ISBN"] = clean

    missing = [f for f in REQUIRED_FIELDS if not merged.get(f)]

    return {
        "found": bool(sources),
        "isbn": clean,
        "metadata": merged,
        "missingFields": missing,
        "sources": sources,
    }
