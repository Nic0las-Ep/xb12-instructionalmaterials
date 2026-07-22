"""
POST /isbn-lookup
Body: { "isbn": "9781234567897" }

Queries reliable public book registries (Google Books, Open Library) and
returns merged metadata plus a list of fields the user still needs to supply.
"""

from xb12_common.registries import lookup_isbn
from xb12_common.responses import ok, bad_request, server_error, parse_body, http_method, respond


def handler(event, context):
    if http_method(event) == "OPTIONS":
        return respond(200, {})

    body = parse_body(event)
    isbn = (body.get("isbn") or "").strip()
    if not isbn:
        return bad_request("An 'isbn' is required.")

    try:
        result = lookup_isbn(isbn)
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
        return server_error("ISBN lookup failed.", detail=str(exc))

    return ok(result)
