"""
POST /admin/submissions/{submissionId}/publish

Publish the valid resource URLs from a single APPROVED submission to one or
more mock destination pages (Course Schedule, Bookstore, MIS Reporting).

Design notes:
  * Approval is re-validated in the backend - the disabled frontend button is
    only a convenience, never the authorization.
  * Publishing is idempotent. Each (submissionId, destination) becomes ONE row
    in the PublishedLinks-index table keyed by a deterministic id
    (``submissionId#destination``). Re-publishing the same submission refreshes
    that row in place instead of creating duplicates (counted as
    skippedDuplicateCount).
  * Each row carries a small snapshot the destination pages need: course
    prefix/number, section, CRN, professor name, the section cost code
    (ZTC/LTC/Standard), the XB12 MIS code, the validated resource URLs, and a
    per-material snapshot (title, ISBN, platform URL, price). No admin notes,
    survey answers, or embedding vectors are ever published.

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
from boto3.dynamodb.conditions import Attr
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
# Adoption history table (Textbookhistory-index) - used to enrich material
# prices at publish time when the submission snapshot predates price capture.
HISTORY_TABLE = os.environ.get("HISTORY_TABLE")

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
_history = _ddb.Table(HISTORY_TABLE) if HISTORY_TABLE else None


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


# Section cost code (friendly) derived from the XB12 letter code.
#   E/F/G/C -> ZTC (zero textbook cost)   D -> LTC (low textbook cost)
#   Y -> Standard                         A -> No Material
_COST_CODE_LABEL = {
    "E": "ZTC", "F": "ZTC", "G": "ZTC", "C": "ZTC",
    "D": "LTC",
    "Y": "Standard",
    "A": "No Material",
}


def cost_code_label(xb12_code):
    """Return the friendly ZTC/LTC/Standard/No Material label for an XB12 code."""
    return _COST_CODE_LABEL.get((xb12_code or "").strip().upper(), "")


# FHDA MIS quarterly-report term convention: YYYY + quarter digit
# (1=Summer, 2=Fall, 3=Winter, 4=Spring), e.g. Fall 2025 -> "20252".
_QUARTER_DIGIT = {"summer": "1", "fall": "2", "winter": "3", "spring": "4"}


def mis_term_code(quarter, year):
    """Return the FHDA-style term code (YYYYT) for a quarter/year, or ''."""
    digit = _QUARTER_DIGIT.get((str(quarter or "").strip().lower()), "")
    digits = "".join(ch for ch in str(year or "") if ch.isdigit())
    if not digit or len(digits) != 4:
        return ""
    return f"{digits}{digit}"


def _row_id(submission_id, destination):
    return f"{submission_id}#{destination}"


def _professor_name(submission):
    name = (submission.get("respondentName") or "").strip()
    if name and name.lower() != "unknown":
        return name
    first = (submission.get("professorFirstName") or "").strip()
    last = (submission.get("professorLastName") or "").strip()
    return (first + " " + last).strip()


def build_material_snapshot(submission):
    """
    Build the minimal per-material snapshot the Bookstore page needs:
    title, ISBN (textbooks), platform URL (validated http/https), and price.

    Only materials that carry an ISBN, a valid URL, a price, or a title are
    included. Nothing sensitive (admin notes, survey answers) is copied.
    """
    snapshot = []
    for material in submission.get("materials") or []:
        if not isinstance(material, dict):
            continue
        isbn = material.get("ISBN") or material.get("isbn") or ""
        raw_url = (
            material.get("url")
            or material.get("oerUrl")
            or material.get("resourceUrl")
            or material.get("platformUrl")
            or material.get("link")
            or ""
        )
        normalized = urlutil.normalize_url(raw_url) if raw_url else None
        entry = {
            "title": material.get("title") or "",
            "isbn": str(isbn) if isbn else "",
            "url": normalized or "",
            "materialType": material.get("materialType") or "",
            "costStatus": material.get("costStatus") or "",
        }
        price = material.get("price")
        if price not in (None, ""):
            entry["price"] = price  # Decimal (from DynamoDB) or numeric string
        if entry["isbn"] or entry["url"] or "price" in entry or entry["title"]:
            snapshot.append(entry)
    return snapshot


def _adoption_price_index(submission, history_table):
    """
    Build {isbn -> price} and {normalizedUrl -> price} lookups from the course's
    adoption records (Textbookhistory) so material prices can be filled in even
    when the submission snapshot predates price capture.
    """
    prefix = submission.get("coursePrefix") or submission.get("department") or ""
    number = submission.get("courseNumber") or ""
    crn = submission.get("crn") or submission.get("CRN") or ""
    if not prefix or not number:
        return {}, {}

    expr = Attr("Course-prefix").eq(prefix) & Attr("Course-number").eq(number)
    if crn:
        expr = expr & Attr("CRN").eq(crn)

    items, kwargs = [], {"FilterExpression": expr}
    while True:
        resp = history_table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    by_isbn, by_url = {}, {}
    for adoption in items:
        price = adoption.get("price")
        if price in (None, ""):
            continue
        isbn = str(adoption.get("ISBN") or "").strip()
        if isbn and isbn not in by_isbn:
            by_isbn[isbn] = price
        normalized = urlutil.normalize_url(adoption.get("url") or "")
        if normalized and normalized not in by_url:
            by_url[normalized] = price
    return by_isbn, by_url


def enrich_snapshot_prices(snapshot, submission, history_table):
    """
    Fill in missing material prices from the course's adoption records. Matches
    each material by ISBN first, then by normalized URL. No-op when a price is
    already present or no history table is available. Best-effort.
    """
    if not history_table:
        return snapshot
    try:
        by_isbn, by_url = _adoption_price_index(submission, history_table)
    except Exception:  # noqa: BLE001 - enrichment is best-effort
        return snapshot
    if not by_isbn and not by_url:
        return snapshot
    for material in snapshot:
        if material.get("price") not in (None, ""):
            continue
        price = None
        if material.get("isbn") and material["isbn"] in by_isbn:
            price = by_isbn[material["isbn"]]
        elif material.get("url") and material["url"] in by_url:
            price = by_url[material["url"]]
        if price is not None:
            material["price"] = price
    return snapshot


def publish(submission, destinations, published_by, table, now=None, history_table=None):
    """
    Write ONE idempotent row per (submission, destination) for an approved
    submission and return ``(result_dict, error_message)``.

    On success ``error_message`` is ``None`` and ``result_dict`` contains
    success / publishedCount / skippedDuplicateCount / publishedMaterialCount /
    publishedUrlCount / destinations / publishedAt.

    Idempotency: the row id is deterministic (``submissionId#destination``).
    The first write for a destination uses a conditional put (counts as
    published); if the row already exists the snapshot is refreshed in place
    (counts as a skipped duplicate) so re-publishing never creates duplicates.
    """
    materials = build_material_snapshot(submission)
    materials = enrich_snapshot_prices(materials, submission, history_table)
    url_pairs = extract_publishable_urls(submission)
    urls = [pair["normalizedUrl"] for pair in url_pairs]
    if not materials and not urls:
        return None, "This submission has no materials to publish."

    timestamp = now or (datetime.datetime.utcnow().isoformat() + "Z")
    submission_id = submission.get("id")
    course_prefix = submission.get("coursePrefix") or submission.get("department") or ""
    course_number = submission.get("courseNumber") or ""
    section = submission.get("section") or ""
    crn = submission.get("crn") or submission.get("CRN") or ""
    professor = _professor_name(submission)
    quarter = submission.get("quarter") or ""
    year = submission.get("year") or ""
    term = mis_term_code(quarter, year)
    # Section-level XB12 INSTRUCTIONAL-MATERIAL-COST code + friendly label.
    xb12_code = submission.get("sectionXb12Code") or ""
    xb12_meaning = submission.get("sectionXb12Meaning") or ""
    cost_code = cost_code_label(xb12_code)

    published_count = 0
    skipped_count = 0

    for destination in destinations:
        item = {
            "id": _row_id(submission_id, destination),
            "publicationId": _row_id(submission_id, destination),
            "submissionId": submission_id,
            "destination": destination,
            "coursePrefix": course_prefix,
            "courseNumber": course_number,
            "section": section,
            "crn": crn,
            "professor": professor,
            "quarter": quarter,
            "year": year,
            "term": term,
            "costCode": cost_code,
            "xb12Code": xb12_code,
            "xb12Meaning": xb12_meaning,
            "materials": materials,
            "urls": urls,
            "publishedAt": timestamp,
            "publishedBy": published_by,
        }
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(id)")
            published_count += 1
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                # Row exists - refresh its snapshot in place (no duplicate).
                try:
                    table.put_item(Item=item)
                except ClientError:
                    return None, "Failed to write one or more publication records."
                skipped_count += 1
            else:
                return None, "Failed to write one or more publication records."

    result = {
        "success": True,
        "submissionId": submission_id,
        "publishedCount": published_count,
        "skippedDuplicateCount": skipped_count,
        "publishedMaterialCount": len(materials),
        "publishedUrlCount": len(urls),
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

    result, error = publish(
        submission, destinations, published_by, _published, history_table=_history
    )
    if error:
        # A storage failure is a server condition; anything else (e.g. nothing
        # to publish) is a client condition.
        if error.startswith("Failed to write"):
            return server_error(error)
        return bad_request(error)
    # The admin dashboard classifies entries as "Submitted" from live
    # published-links state, so no flag is stamped on the submission here.
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
