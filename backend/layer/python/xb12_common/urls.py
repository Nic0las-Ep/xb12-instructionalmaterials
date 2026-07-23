"""
URL extraction, validation, and normalization helpers.

Used by the publishing workflow to pull ONLY genuine resource links out of a
submission, drop anything unsafe, normalize them, and de-duplicate. Kept free
of AWS dependencies so it can be unit-tested in isolation.

Rules enforced here:
  * Only ``http`` and ``https`` URLs are accepted. Unsafe schemes such as
    ``javascript:``, ``data:``, and ``file:`` never match and are rejected.
  * Values that are not URLs (ISBNs, course numbers, CRNs, titles, names)
    never match the extraction regex, so they are naturally excluded.
  * Text fields that may contain one or more URLs are scanned for every
    ``http(s)://`` occurrence.
"""

from urllib.parse import urlsplit, urlunsplit
import re

# Matches http/https URLs embedded anywhere in a string. Stops at whitespace
# and characters that commonly terminate a URL in prose (quotes, brackets,
# angle brackets, closing parens).
_URL_RE = re.compile(r"""https?://[^\s<>"'`)\]}]+""", re.IGNORECASE)

_ALLOWED_SCHEMES = ("http", "https")

# Trailing characters that are almost always sentence punctuation rather than
# part of the URL when a link is embedded in free text.
_TRAILING_JUNK = ".,;:!?)]}>\"'"

# Fields on a material/resource that may legitimately hold a URL.
URL_FIELDS = ("url", "oerUrl", "resourceUrl", "platformUrl", "link")

# Fields that may contain free text with one or more embedded URLs.
TEXT_FIELDS = ("description", "notes", "resourceDescription", "noCostDescription")


def normalize_url(raw):
    """
    Validate and normalize a single URL string.

    Returns the normalized URL (str) if it is a well-formed http/https URL,
    otherwise ``None``. Normalization:
      * lowercases the scheme and host
      * drops the fragment (``#...``)
      * removes a default port (80 for http, 443 for https)
      * strips a trailing slash from a non-root path
      * drops any userinfo (``user:pass@``) for safety
    """
    if raw is None:
        return None
    candidate = str(raw).strip().strip(_TRAILING_JUNK)
    if not candidate:
        return None
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None

    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return None

    host = (parts.hostname or "").lower()
    if not host:
        return None

    netloc = host
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"

    path = parts.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def find_urls_in_text(text):
    """Return every raw http(s) URL substring found in a piece of text."""
    if not text:
        return []
    return _URL_RE.findall(str(text))


def collect_urls(candidates):
    """
    Extract, validate, normalize, and de-duplicate URLs from a list of values.

    ``candidates`` is an iterable of arbitrary values (direct URL strings or
    free text that may embed URLs). Non-string values are coerced to str.

    Returns a list of ``{"normalizedUrl": ..., "originalUrl": ...}`` dicts in
    first-seen order, with duplicates (by normalized form) removed.
    """
    seen = set()
    result = []
    for value in candidates:
        if value is None:
            continue
        for raw in find_urls_in_text(str(value)):
            normalized = normalize_url(raw)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(
                {"normalizedUrl": normalized, "originalUrl": raw.strip().strip(_TRAILING_JUNK)}
            )
    return result
