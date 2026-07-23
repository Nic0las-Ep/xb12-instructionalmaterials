"""
GET /published-links?destination=course-schedule

Return the publications for a given mock destination, newest first. Each row in
PublishedLinks-index is one publication (one submission per destination) and
carries the small snapshot the destination pages render: course prefix/number,
section, CRN, professor, section cost code (ZTC/LTC/Standard), XB12 code, the
resource URLs, and a per-material snapshot (title, ISBN, platform URL, price).

Only these display fields are returned. Admin notes, survey answers, and
embedding vectors are never stored here and so can never be exposed.
"""

import os

import boto3
from boto3.dynamodb.conditions import Key

from xb12_common.responses import (
    ok,
    bad_request,
    respond,
    server_error,
    query_params,
    http_method,
)

PUBLISHED_LINKS_TABLE = os.environ["PUBLISHED_LINKS_TABLE"]
DESTINATION_INDEX = "destination-index"

VALID_DESTINATIONS = ("course-schedule", "bookstore", "mis-reporting")

_published = boto3.resource("dynamodb").Table(PUBLISHED_LINKS_TABLE)


def _query_rows(destination):
    """Return all rows for a destination, newest first (by publishedAt)."""
    items, kwargs = [], {
        "IndexName": DESTINATION_INDEX,
        "KeyConditionExpression": Key("destination").eq(destination),
        "ScanIndexForward": False,  # newest publishedAt first
    }
    while True:
        resp = _published.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def to_publication(row):
    """Map a stored row to the public publication shape (display fields only)."""
    urls = row.get("urls") or []
    # Back-compat: older rows stored a single normalizedUrl instead of a list.
    if not urls and row.get("normalizedUrl"):
        urls = [row["normalizedUrl"]]
    return {
        "publicationId": row.get("publicationId") or row.get("submissionId", ""),
        "submissionId": row.get("submissionId", ""),
        "coursePrefix": row.get("coursePrefix", ""),
        "courseNumber": row.get("courseNumber", ""),
        "section": row.get("section", ""),
        "crn": row.get("crn", ""),
        "professor": row.get("professor", ""),
        "quarter": row.get("quarter", ""),
        "year": row.get("year", ""),
        "term": row.get("term", ""),
        "costCode": row.get("costCode", ""),
        "xb12Code": row.get("xb12Code", ""),
        "xb12Meaning": row.get("xb12Meaning", ""),
        "destination": row.get("destination", ""),
        "materials": row.get("materials") or [],
        "urls": urls,
        "publishedAt": row.get("publishedAt", ""),
    }


def to_publications(rows):
    """Map rows to publications, newest first."""
    pubs = [to_publication(r) for r in rows]
    pubs.sort(key=lambda p: p.get("publishedAt", ""), reverse=True)
    return pubs


def handler(event, context):
    if http_method(event) == "OPTIONS":
        return respond(200, {})

    params = query_params(event)
    destination = (params.get("destination") or "").strip()
    if destination not in VALID_DESTINATIONS:
        return bad_request(
            f"Invalid or missing 'destination'. Allowed: {list(VALID_DESTINATIONS)}"
        )

    try:
        rows = _query_rows(destination)
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to load published links.", detail=str(exc))

    publications = to_publications(rows)
    return ok(
        {
            "count": len(publications),
            "destination": destination,
            "publications": publications,
        }
    )
