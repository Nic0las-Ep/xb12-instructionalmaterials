"""
GET /published-links?destination=course-schedule

Return the links that have been published to a given mock destination. Rows in
PublishedLinks-index are stored one-per-URL for idempotency; this endpoint
groups them by source submission so each course/section appears once with its
list of URLs, newest first.

Only the minimal, non-private publication fields are returned. Professor PII,
admin notes, survey answers, and embeddings are never stored here and so can
never be exposed.
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


def group_rows(rows):
    """
    Group per-URL rows into one publication per submission (within a
    destination). Returns publications newest-first. Each publication:
      { publicationId, submissionId, coursePrefix, courseNumber, crn,
        destination, urls: [...], publishedAt }
    """
    groups = {}
    order = []
    for row in rows:
        sub_id = row.get("submissionId")
        if sub_id not in groups:
            groups[sub_id] = {
                "publicationId": sub_id,
                "submissionId": sub_id,
                "coursePrefix": row.get("coursePrefix", ""),
                "courseNumber": row.get("courseNumber", ""),
                "crn": row.get("crn", ""),
                "xb12Code": row.get("xb12Code", ""),
                "xb12Meaning": row.get("xb12Meaning", ""),
                "destination": row.get("destination", ""),
                "urls": [],
                "_seen": set(),
                "publishedAt": row.get("publishedAt", ""),
            }
            order.append(sub_id)
        group = groups[sub_id]
        url = row.get("normalizedUrl")
        if url and url not in group["_seen"]:
            group["_seen"].add(url)
            group["urls"].append(url)
        # Keep the most recent timestamp for the group.
        if row.get("publishedAt", "") > group["publishedAt"]:
            group["publishedAt"] = row["publishedAt"]

    publications = []
    for sub_id in order:
        group = groups[sub_id]
        group.pop("_seen", None)
        publications.append(group)
    # Rows arrive newest-first, but a group's chosen publishedAt may be newer;
    # sort defensively so the response is strictly newest-first.
    publications.sort(key=lambda p: p.get("publishedAt", ""), reverse=True)
    return publications


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

    publications = group_rows(rows)
    return ok(
        {
            "count": len(publications),
            "destination": destination,
            "publications": publications,
        }
    )
