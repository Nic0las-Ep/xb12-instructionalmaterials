"""
Look up textbook metadata from reliable public book registries by ISBN.

Sources (queried in order, results merged):
  1. Google Books API   - title, authors, publisher, date, description, price
  2. Open Library API   - title, authors, publisher, date  (fallback / fill-in)

Uses only the Python standard library (urllib) so no bundled deps are needed.
"""

import json
import re
import urllib.request
import urllib.parse
import urllib.error

# Fields the application expects for a complete textbook record.
REQUIRED_FIELDS = ("title", "author", "publisher", "price")


def _normalize_isbn(isbn):
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def _get_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "xb12-registry/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None


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

    google = _from_google_books(clean)
    if google:
        sources.append("googleBooks")
        merged.update(google)

    openlib = _from_open_library(clean)
    if openlib:
        sources.append("openLibrary")
        # Only fill in fields Google Books did not already provide.
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
