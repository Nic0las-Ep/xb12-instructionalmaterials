"""
Submissions API used by the admin dashboard.

  GET    /submissions           list all submissions (newest first)
  GET    /submissions/{id}      fetch one submission
  PUT    /submissions/{id}      update review status / admin notes
  DELETE /submissions/{id}      delete a submission

NOTE: These endpoints are currently UNAUTHENTICATED (open) per the project
decision to add access control later. They expose and mutate all faculty
submissions, so an admin auth layer should be added before production use.
"""

import datetime
import os
from decimal import Decimal

import boto3

from xb12_common.responses import (
    ok,
    bad_request,
    server_error,
    respond,
    parse_body,
    http_method,
)
from xb12_common.xb12 import XB12_MEANINGS, zero_low_cost_marking

SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]

_table = boto3.resource("dynamodb").Table(SUBMISSIONS_TABLE)

_ALLOWED_STATUS = {"Pending", "Under Review", "Approved", "Needs Correction"}

# Simple identity/professor fields an admin may correct. The class, section
# number, and CRN are intentionally NOT editable - they identify the section.
_EDITABLE_STR_FIELDS = ("respondentName", "professorFirstName", "professorLastName")


def _decimalize(obj):
    """Recursively convert floats to Decimal so the value is DynamoDB-safe."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, list):
        return [_decimalize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _decimalize(v) for k, v in obj.items()}
    return obj

# Fields an admin may correct on a submission (e.g. a last-minute professor or
# section change). CRN is intentionally excluded: it is the immutable section
# identifier used to match submissions and adoptions, so it cannot be changed.
EDITABLE_FIELDS = ("respondentName", "professorFirstName", "professorLastName", "section")


def _submission_id(event):
    return (event.get("pathParameters") or {}).get("id")


def _list():
    items, kwargs = [], {}
    while True:
        resp = _table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    items.sort(key=lambda s: s.get("submittedAt", ""), reverse=True)
    return ok({"count": len(items), "submissions": items})


def _get(sub_id):
    item = _table.get_item(Key={"id": sub_id}).get("Item")
    if not item:
        return respond(404, {"error": "Submission not found."})
    return ok({"submission": item})


def _update(event, sub_id):
    body = parse_body(event)
    existing = _table.get_item(Key={"id": sub_id}).get("Item")
    if not existing:
        return respond(404, {"error": "Submission not found."})

    expr_parts = ["updatedAt = :u"]
    values = {":u": datetime.datetime.utcnow().isoformat() + "Z"}

    status = body.get("status")
    if status is not None:
        if status not in _ALLOWED_STATUS:
            return bad_request(f"Invalid status. Allowed: {sorted(_ALLOWED_STATUS)}")
        expr_parts.append("#s = :s")
        values[":s"] = status
    # Accept both adminNotes (admin.html) and notes.
    notes = body.get("adminNotes")
    if notes is None:
        notes = body.get("notes")
    if notes is not None:
        expr_parts.append("adminNotes = :n")
        values[":n"] = str(notes)

    names = {}

    # --- Editable corrections -------------------------------------------
    # The professor can change last-minute, and the resources and XB12 codes
    # can change. The class, section number, and CRN stay fixed (not editable).
    for i, field in enumerate(_EDITABLE_STR_FIELDS):
        if body.get(field) is not None:
            alias = f":f{i}"
            expr_parts.append(f"{field} = {alias}")
            values[alias] = str(body[field])

    code = body.get("sectionXb12Code")
    if code is not None:
        code = str(code).strip().upper()
        if code and code not in XB12_MEANINGS:
            return bad_request(f"Invalid XB12 code. Allowed: {sorted(XB12_MEANINGS)}")
        expr_parts.append("sectionXb12Code = :xc")
        values[":xc"] = code
        expr_parts.append("sectionXb12Meaning = :xm")
        values[":xm"] = XB12_MEANINGS.get(code, "")
        expr_parts.append("sectionCostStatus = :xs")
        values[":xs"] = zero_low_cost_marking(code) or ("NONE" if code == "A" else "STANDARD")

    materials = body.get("materials")
    if materials is not None:
        if not isinstance(materials, list):
            return bad_request("materials must be a list.")
        expr_parts.append("materials = :m")
        values[":m"] = _decimalize(materials)

    kwargs = {
        "Key": {"id": sub_id},
        "UpdateExpression": "SET " + ", ".join(expr_parts),
        "ExpressionAttributeValues": values,
        "ReturnValues": "ALL_NEW",
    }
    if status is not None:
        names["#s"] = "status"
    if names:
        kwargs["ExpressionAttributeNames"] = names

    try:
        result = _table.update_item(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to update submission.", detail=str(exc))
    return ok({"success": True, "submission": result.get("Attributes")})


def _delete(sub_id):
    try:
        _table.delete_item(Key={"id": sub_id})
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to delete submission.", detail=str(exc))
    return ok({"success": True, "deleted": sub_id})


def handler(event, context):
    method = http_method(event)
    if method == "OPTIONS":
        return respond(200, {})

    sub_id = _submission_id(event)

    if method == "GET":
        return _get(sub_id) if sub_id else _list()
    if method == "PUT":
        if not sub_id:
            return bad_request("A submission id is required.")
        return _update(event, sub_id)
    if method == "DELETE":
        if not sub_id:
            return bad_request("A submission id is required.")
        return _delete(sub_id)
    return bad_request(f"Unsupported method: {method}")
