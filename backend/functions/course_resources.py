"""
Course adoptions (which resources are used by a given course/section).

POST /course-resources
  Adopt a resource (existing catalog entry or a freshly-created one) into a
  course. Multiple resources may be adopted per course - each call adds one row
  to the Textbookhistory-index table.
  Body:
    coursePrefix, courseNumber           (required)
    quarter, year                        (term)
    professorFirstName, professorLastName
    resourceId, ISBN, url, title, xb12Code, materialType   (resource reference)

GET /course-resources?coursePrefix=ENGL&courseNumber=1A[&quarter=Fall&year=2025]
  List all resources adopted for a course.
"""

import datetime
import os
import uuid
from decimal import Decimal, InvalidOperation

import boto3
from boto3.dynamodb.conditions import Attr

from xb12_common.responses import (
    ok,
    bad_request,
    server_error,
    parse_body,
    query_params,
    http_method,
    respond,
)

HISTORY_TABLE = os.environ["HISTORY_TABLE"]

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(HISTORY_TABLE)


def _create(event):
    body = parse_body(event)

    course_prefix = (body.get("coursePrefix") or body.get("Course-prefix") or "").strip()
    course_number = (body.get("courseNumber") or body.get("Course-number") or "").strip()
    if not course_prefix or not course_number:
        return bad_request("'coursePrefix' and 'courseNumber' are required.")

    isbn = (body.get("ISBN") or body.get("isbn") or "").strip()
    url = (body.get("url") or "").strip()
    if not isbn and not url and not body.get("resourceId"):
        return bad_request("Provide a resource reference (resourceId, ISBN, or url).")

    item = {
        "id": str(uuid.uuid4()),
        "Course-prefix": course_prefix,
        "Course-number": course_number,
        "adoptedAt": datetime.datetime.utcnow().isoformat() + "Z",
    }

    # Optional term / professor / resource fields.
    quarter = (body.get("quarter") or body.get("Quarter") or "").strip()
    if quarter:
        item["Quarter"] = quarter
    year = body.get("year") or body.get("Year")
    if year not in (None, ""):
        try:
            item["Year"] = int(year)
        except (ValueError, TypeError):
            return bad_request("'year' must be a number.")

    for src_key, dst_key in (
        ("crn", "CRN"),
        ("section", "section"),
        ("professorFirstName", "professorFirstName"),
        ("professorLastName", "professorLastName"),
        ("resourceId", "resourceId"),
        ("title", "title"),
        ("xb12Code", "xb12Code"),
        ("costStatus", "costStatus"),
        ("costType", "costType"),
        ("materialType", "materialType"),
    ):
        val = body.get(src_key)
        if val:
            item[dst_key] = str(val).strip()

    # Numeric price (kept for the section-level XB12 computation at submit time).
    price = body.get("price")
    if price not in (None, ""):
        try:
            item["price"] = Decimal(str(price))
        except (InvalidOperation, ValueError, TypeError):
            pass

    if isbn:
        item["ISBN"] = isbn
    if url:
        item["url"] = url

    try:
        _table.put_item(Item=item)
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to record course adoption.", detail=str(exc))

    return ok({"success": True, "adoption": item})


def _list(event):
    params = query_params(event)
    course_prefix = (params.get("coursePrefix") or "").strip()
    course_number = (params.get("courseNumber") or "").strip()
    if not course_prefix or not course_number:
        return bad_request("'coursePrefix' and 'courseNumber' query params are required.")

    filter_expr = Attr("Course-prefix").eq(course_prefix) & Attr("Course-number").eq(
        course_number
    )
    quarter = (params.get("quarter") or "").strip()
    if quarter:
        filter_expr = filter_expr & Attr("Quarter").eq(quarter)
    year = params.get("year")
    if year:
        try:
            filter_expr = filter_expr & Attr("Year").eq(int(year))
        except (ValueError, TypeError):
            return bad_request("'year' must be a number.")

    try:
        items = []
        kwargs = {"FilterExpression": filter_expr}
        while True:
            resp = _table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to list course adoptions.", detail=str(exc))

    return ok({"count": len(items), "adoptions": items})


def handler(event, context):
    method = http_method(event)
    if method == "OPTIONS":
        return respond(200, {})
    if method == "GET":
        return _list(event)
    if method == "POST":
        return _create(event)
    return bad_request(f"Unsupported method: {method}")
