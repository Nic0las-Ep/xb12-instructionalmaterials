"""
POST /admin/submissions/{submissionId}/publish

Publish the valid resource URLs from a single APPROVED submission to one or
more mock destination pages (Course Schedule, Bookstore, MIS Reporting).

Design notes:
  * Approval is re-validated in the backend - the disabled frontend button is
    only a convenience, never the authorization.
  * Publishing is idempotent. Each (submissionId, destination, normalizedUrl)
    becomes one row in the PublishedLinks-index table keyed by a deterministic
    id. Re-publishing the same submission skips rows that already exist
    (counted as skippedDuplicateCount) instead of creating duplicates.
  * Only minimal, non-private data is stored per row (course prefix/number,
    CRN, the URLs, timestamps). No admin notes, professor PII, survey answers,
    or embeddings are ever published.

The core (`publish`, `extract_publishable_urls`, `validate_destinations`) is
kept free of module-level AWS state so it can be unit-tested with a fake table.

NOTE: This route is currently UNAUTHENTICATED per the project decision to add
access control later. It is structured so a Cognito (or other) admin authorizer
can be attached to the API Gateway method without changing this handler.
"""

import datetime
import os
import uuid

import boto3
from botocore.exceptions import ClientError

from xb12_common import urls as urlutil
from xb12_common.responses import (
    ok,
    bad_request,
    server_error,
    respond,
    parse_body,
    http_method,
)

SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]
PUBLISHED_LINKS_TABLE = os.environ["PUBLISHED_LINKS_TABLE"]

# Canonical destination ids and their human labels.
DESTINATIONS = {
    "course-schedule": "Course Schedule",
    "bookstore": "Bookstore",
    "mis-reporting": "State Compliance / MIS Reporting",
}

APPROVED_STATUS = "Approved"

_ddb = boto3.resource("dynamodb")
_submissions = _ddb.Table(SUBMISSIONS_TABLE)
_published = _ddb.Table(PUBLISHED_LINKS_TABLE)


def _submission_id(event):
    return (event.get("pathParameters") or {}).get("submissionId") or (
        event.get("pathParameters") or {}
    ).get("id")


def extract_publishable_urls(submission):
    """
    Return the de-duplicated, validated, normalized URLs belonging to a
    submission as a list of ``{"normalizedUrl", "originalUrl"}`` dicts.

    URLs are pulled ONLY from resource-bearing fields: each material's url /
    oerUrl / resourceUrl / platformUrl / link fields plus any free-text
    description fields. Admin notes, titles, ISBNs, CRNs, course numbers, and
    names are never inspected, so they can never leak in as "URLs".
    """
    candidates = []
    for material in submission.get("materials") or []:
        if not isinstance(material, dict):
            continue
        for field in urlutil.URL_FIELDS:
            if material.get(field):
                candidates.append(material[field])
        for field in urlutil.TEXT_FIELDS:
            if material.get(field):
                candidates.append(material[field])
    # Defensively check submission-level URL fields too (models vary).
    for field in urlutil.URL_FIELDS:
        if submission.get(field):
            candidates.append(submission[field])
    return urlutil.collect_urls(candidates)


def validate_destinations(raw):
    """
    Validate a requested destination list.

    Returns ``(valid_list, error_message)``. ``valid_list`` is the de-duplicated
    list of known destination ids (order preserved). ``error_message`` is
    ``None`` when valid, otherwise a human-readable reason.
    """
    if not isinstance(raw, list) or not raw:
        return [], "Select at least one destination to publish to."
    seen = set()
    valid = []
    for dest in raw:
        key = str(dest).strip()
        if key not in DESTINATIONS:
            return [], f"Unknown destination: {dest}"
        if key not in seen:
            seen.add(key)
            valid.append(key)
    return valid, None


def _row_id(submission_id, destination, normalized_url):
    return f"{submission_id}#{destination}#{normalized_url}"


def publish(submission, destinations, published_by, table, now=None):
    """
    Write one idempotent row per (destination, URL) for an approved submission.

    Returns ``(result_dict, error_message)``. On success ``error_message`` is
    ``None`` and ``result_dict`` contains success / publishedCount /
    skippedDuplicateCount / destinations / publishedAt / publishedUrlCount.

    Idempotency: each row uses a deterministic id and a conditional put that
    fails (ConditionalCheckFailed) when the row already exists; such rows are
    counted as skipped duplicates rather than re-created.
    """
    url_pairs = extract_publishable_urls(submission)
    if not url_pairs:
        return None, "This submission contains no valid URLs to publish."

    timestamp = now or (datetime.datetime.utcnow().isoformat() + "Z")
    submission_id = submission.get("id")
    course_prefix = submission.get("coursePrefix") or submission.get("department") or ""
    course_number = submission.get("courseNumber") or ""
    crn = submission.get("crn") or submission.get("CRN") or ""
    # Section-level XB12 INSTRUCTIONAL-MATERIAL-COST code (the value reported to
    # MIS). Included so the MIS destination can render it as a data element.
    xb12_code = submission.get("sectionXb12Code") or ""
    xb12_meaning = submission.get("sectionXb12Meaning") or ""

    published_count = 0
    skipped_count = 0

    for destination in destinations:
        for pair in url_pairs:
            normalized = pair["normalizedUrl"]
            item = {
                "id": _row_id(submission_id, destination, normalized),
                "publicationId": str(uuid.uuid4()),
                "submissionId": submission_id,
                "destination": destination,
                "normalizedUrl": normalized,
                "originalUrl": pair["originalUrl"],
                "coursePrefix": course_prefix,
                "courseNumber": course_number,
                "crn": crn,
                "xb12Code": xb12_code,
                "xb12Meaning": xb12_meaning,
                "publishedAt": timestamp,
                "publishedBy": published_by,
            }
            try:
                table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(id)",
                )
                published_count += 1
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    skipped_count += 1
                else:
                    # Storage failure - surface it without leaking internals.
                    return None, "Failed to write one or more publication records."

    result = {
        "success": True,
        "submissionId": submission_id,
        "publishedCount": published_count,
        "skippedDuplicateCount": skipped_count,
        "publishedUrlCount": len(url_pairs),
        "publishedAt": timestamp,
        "destinations": list(destinations),
    }
    return result, None


def handler(event, context):
    if http_method(event) == "OPTIONS":
        return respond(200, {})

    sub_id = _submission_id(event)
    if not sub_id:
        return bad_request("A submission id is required.")

    body = parse_body(event)
    destinations, dest_error = validate_destinations(body.get("destinations"))
    if dest_error:
        return bad_request(dest_error)

    try:
        submission = _submissions.get_item(Key={"id": sub_id}).get("Item")
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to load submission.", detail=str(exc))
    if not submission:
        return respond(404, {"error": "Submission not found."})

    if submission.get("status") != APPROVED_STATUS:
        return bad_request("Approve this submission before publishing.")

    published_by = _resolve_publisher(event)

    result, error = publish(submission, destinations, published_by, _published)
    if error:
        # No URLs / storage failure. "No valid URLs" is a client-side condition;
        # a storage failure is a server condition.
        if "no valid URLs" in error.lower():
            return bad_request(error)
        return server_error(error)
    return ok(result)


def _resolve_publisher(event):
    """
    Best-effort identity of the publishing admin. When a Cognito authorizer is
    later attached, the authenticated username/sub is used automatically.
    Falls back to "admin" while the route is unauthenticated.
    """
    try:
        claims = (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("claims", {})
        )
        return claims.get("cognito:username") or claims.get("sub") or "admin"
    except Exception:  # noqa: BLE001
        return "admin"
