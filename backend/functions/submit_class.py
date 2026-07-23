"""
POST /submit-class
Finalize a class submission: gather every material adopted for the course
section, compute the SECTION-LEVEL XB12 code (across all materials), record a
submission for the admin dashboard, and write usage back to the Resource-index
catalog so each material reflects which sections previously used it.

Body:
  coursePrefix, courseNumber            (required)
  crn, section, quarter, year           (identify the section)
  professorFirstName, professorLastName
"""

import datetime
import decimal
import os
import uuid

import boto3
from boto3.dynamodb.conditions import Attr, Key

from xb12_common import xb12
from xb12_common import embeddings
from xb12_common.aoss import AossClient
from xb12_common.responses import (
    ok,
    bad_request,
    server_error,
    parse_body,
    http_method,
    respond,
)

HISTORY_TABLE = os.environ["HISTORY_TABLE"]
RESOURCE_TABLE = os.environ["RESOURCE_TABLE"]
SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]
AOSS_INDEX = os.environ.get("AOSS_INDEX", "resources")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
LOW_COST_THRESHOLD = os.environ.get("LOW_COST_THRESHOLD", "50")

_ddb = boto3.resource("dynamodb")
_history = _ddb.Table(HISTORY_TABLE)
_resources = _ddb.Table(RESOURCE_TABLE)
_submissions = _ddb.Table(SUBMISSIONS_TABLE)

# Fallback cost profile when an adoption predates cost tracking: derive an
# approximate profile from the material's own XB12 code.
_THRESH = float(LOW_COST_THRESHOLD or "50")
_CODE_TO_MATERIAL = {
    "E": {"costType": "oer"},
    "F": {"costType": "free_non_oer"},
    "C": {"costType": "subsidized", "price": 1},
    "G": {"costType": "oer"},
    "D": {"costType": "priced", "price": _THRESH},
    "Y": {"costType": "priced", "price": _THRESH * 3},
    "A": {},
}


def _material_from_adoption(a):
    cost_type = (a.get("costType") or "").strip().lower()
    if cost_type:
        return {
            "costType": cost_type,
            "price": a.get("price"),
            "isOER": cost_type == "oer",
            "url": a.get("url"),
            "isbn": a.get("ISBN"),
        }
    m = dict(_CODE_TO_MATERIAL.get((a.get("xb12Code") or "").strip().upper(), {}))
    m["url"] = a.get("url")
    m["isbn"] = a.get("ISBN")
    return m


def _material_type_label(code):
    if code in ("E", "F", "G", "C"):
        return "Zero-Cost Material (ZTC)"
    if code == "D":
        return "Low-Cost Material (LTC)"
    if code == "A":
        return "No Material"
    return "Standard Material"


def _query_adoptions(prefix, number, section, crn, quarter, year):
    expr = Attr("Course-prefix").eq(prefix) & Attr("Course-number").eq(number)
    if section:
        expr = expr & Attr("section").eq(section)
    if crn:
        expr = expr & Attr("CRN").eq(crn)
    if quarter:
        expr = expr & Attr("Quarter").eq(quarter)
    if year not in (None, ""):
        try:
            expr = expr & Attr("Year").eq(int(year))
        except (ValueError, TypeError):
            pass
    items, kwargs = [], {"FilterExpression": expr}
    while True:
        resp = _history.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def _find_resource(resource_id, isbn, url):
    if resource_id:
        got = _resources.get_item(Key={"id": resource_id}).get("Item")
        if got:
            return got
    if isbn:
        r = _resources.query(
            IndexName="ISBN-index", KeyConditionExpression=Key("ISBN").eq(isbn)
        ).get("Items")
        if r:
            return r[0]
    if url:
        r = _resources.query(
            IndexName="url-index", KeyConditionExpression=Key("url").eq(url)
        ).get("Items")
        if r:
            return r[0]
    return None


def _clean(v):
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _record_usage(resource, course_ref, course_key, professor=None):
    """Append this section (and professor) to a catalog resource's usage history."""
    used = list(resource.get("usedInCourses") or [])
    if course_key not in used:
        used.append(course_key)
    professors = list(resource.get("usedByProfessors") or [])
    if professor and professor not in ("", "Unknown") and professor not in professors:
        professors.append(professor)
    history = list(resource.get("courseHistory") or [])
    key_tuple = (
        course_ref["coursePrefix"],
        course_ref["courseNumber"],
        course_ref.get("section", ""),
        course_ref.get("quarter", ""),
        str(course_ref.get("year", "")),
    )
    exists = any(
        (
            h.get("coursePrefix"),
            h.get("courseNumber"),
            h.get("section", ""),
            h.get("quarter", ""),
            str(h.get("year", "")),
        )
        == key_tuple
        for h in history
    )
    if not exists:
        history.append(course_ref)

    expr = "SET usedInCourses = :u, courseHistory = :h, usedByProfessors = :p"
    values = {":u": used, ":h": history, ":p": professors}
    if not resource.get("classNumber"):
        expr += ", classNumber = :c"
        values[":c"] = course_key
    _resources.update_item(
        Key={"id": resource["id"]},
        UpdateExpression=expr,
        ExpressionAttributeValues=values,
    )
    resource["usedInCourses"] = used
    resource["courseHistory"] = history
    resource["usedByProfessors"] = professors
    return resource


def _reindex_resource(client, resource):
    """Best-effort: refresh the resource's OpenSearch doc with usage fields."""
    try:
        doc = _clean({k: v for k, v in resource.items() if k != "embedding"})
        parts = [
            doc.get(k)
            for k in ("title", "author", "publisher", "subject", "materialType", "description")
        ]
        parts.extend(doc.get("usedInCourses") or [])
        parts.extend(doc.get("usedByProfessors") or [])
        doc["embedding"] = embeddings.embed_text(" ".join(str(p) for p in parts if p))
        # Remove any existing docs for this id, then index the fresh one.
        found = client.search(
            AOSS_INDEX, {"size": 10, "_source": False, "query": {"term": {"id": resource["id"]}}}
        )
        for hit in (found.get("hits", {}).get("hits") or []):
            client.request("DELETE", f"/{AOSS_INDEX}/_doc/{hit['_id']}")
        client.index_document(AOSS_INDEX, resource["id"], doc)
    except Exception:  # noqa: BLE001 - search refresh is best-effort
        pass


def _find_existing_submission(prefix, number, crn, section, quarter, year):
    """
    A CRN uniquely identifies a section, so a resubmission for the same CRN
    should update the existing submission rather than create a duplicate.
    Returns the most recent matching submission, or None. Requires a CRN (or,
    absent a CRN, a section) to identify the section - otherwise returns None
    so we don't accidentally merge distinct sections.
    """
    expr = Attr("coursePrefix").eq(prefix) & Attr("courseNumber").eq(number)
    if crn:
        expr = expr & Attr("crn").eq(crn)
    elif section:
        expr = expr & Attr("section").eq(section)
    else:
        return None
    if quarter:
        expr = expr & Attr("quarter").eq(quarter)
    if str(year).strip() not in ("", "None"):
        expr = expr & Attr("year").eq(int(year) if str(year).isdigit() else year)

    items, kwargs = [], {"FilterExpression": expr}
    while True:
        resp = _submissions.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    items.sort(key=lambda s: s.get("submittedAt", ""), reverse=True)
    return items[0] if items else None


def handler(event, context):
    if http_method(event) == "OPTIONS":
        return respond(200, {})

    body = parse_body(event)
    prefix = (body.get("coursePrefix") or "").strip()
    number = (body.get("courseNumber") or "").strip()
    if not prefix or not number:
        return bad_request("'coursePrefix' and 'courseNumber' are required.")

    section = (body.get("section") or "").strip()
    crn = (body.get("crn") or body.get("CRN") or "").strip()
    quarter = (body.get("quarter") or "").strip()
    year = body.get("year")
    first = (body.get("professorFirstName") or "").strip()
    last = (body.get("professorLastName") or "").strip()

    adoptions = _query_adoptions(prefix, number, section, crn, quarter, year)
    if not adoptions:
        return bad_request(
            "No materials have been added for this section yet. Add materials before submitting."
        )

    materials = [_material_from_adoption(a) for a in adoptions]
    code, explanation = xb12.classify(materials, LOW_COST_THRESHOLD)
    ztc_ltc = xb12.zero_low_cost_marking(code)
    material_type_label = _material_type_label(code)

    course_ref = {
        "coursePrefix": prefix,
        "courseNumber": number,
        "section": section,
        "quarter": quarter,
        "year": int(year) if str(year).isdigit() else year,
    }
    course_key = f"{prefix} {number}"
    respondent = (first + " " + last).strip() or "Unknown"

    # Resource-index usage write-back (+ best-effort OpenSearch refresh).
    client = None
    try:
        client = AossClient()
    except Exception:  # noqa: BLE001
        client = None
    updated_resources = []
    material_summaries = []
    for a in adoptions:
        material_summaries.append(
            {
                "title": a.get("title"),
                "ISBN": a.get("ISBN"),
                "url": a.get("url"),
                "xb12Code": a.get("xb12Code"),
                "costStatus": a.get("costStatus"),
                "materialType": a.get("materialType"),
            }
        )
        res = _find_resource(a.get("resourceId"), a.get("ISBN"), a.get("url"))
        if res:
            try:
                res = _record_usage(res, course_ref, course_key, respondent)
                updated_resources.append(res["id"])
                if client:
                    _reindex_resource(client, res)
            except Exception:  # noqa: BLE001 - one bad resource shouldn't fail submit
                pass

    respondent = (first + " " + last).strip() or "Unknown"
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # If this section (by CRN) was already submitted, update that record in
    # place instead of creating a duplicate. A genuinely new/unique CRN creates
    # a new submission. The admin's notes are preserved; status resets to
    # Pending since the materials may have changed and need re-review.
    existing = _find_existing_submission(prefix, number, crn, section, quarter, year)
    resubmitted = bool(existing)

    submission = {
        "id": existing["id"] if existing else str(uuid.uuid4()),
        "respondentName": respondent,
        "professorFirstName": first,
        "professorLastName": last,
        "department": prefix,
        "courseNumber": number,
        "coursePrefix": prefix,
        "courseCode": f"{prefix} {number}",
        "crn": crn,
        "section": section,
        "quarter": quarter,
        "year": int(year) if str(year).isdigit() else (year or ""),
        "materials": material_summaries,
        "materialCount": len(material_summaries),
        "sectionXb12Code": code,
        "sectionXb12Meaning": xb12.XB12_MEANINGS[code],
        "sectionCostStatus": ("ZTC-OER" if code == "E" else (ztc_ltc or ("NONE" if code == "A" else "STANDARD"))),
        "materialType": material_type_label,
        "status": "Pending",
        "adminNotes": (existing.get("adminNotes") if existing else "") or "",
        "createdAt": (existing.get("createdAt") or existing.get("submittedAt")) if existing else now,
        "submittedAt": now,
    }

    try:
        _submissions.put_item(Item=submission)
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to record submission.", detail=str(exc))

    return ok(
        {
            "success": True,
            "resubmitted": resubmitted,
            "submission": submission,
            "section": {
                "code": code,
                "meaning": xb12.XB12_MEANINGS[code],
                "explanation": explanation,
                "ztcLtc": ztc_ltc,
            },
            "updatedResources": updated_resources,
        }
    )
