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

import boto3

from xb12_common.responses import (
    ok,
    bad_request,
    server_error,
    respond,
    parse_body,
    http_method,
)

SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]

_table = boto3.resource("dynamodb").Table(SUBMISSIONS_TABLE)

_ALLOWED_STATUS = {"Pending", "Under Review", "Approved", "Needs Correction"}


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

    kwargs = {
        "Key": {"id": sub_id},
        "UpdateExpression": "SET " + ", ".join(expr_parts),
        "ExpressionAttributeValues": values,
        "ReturnValues": "ALL_NEW",
    }
    if status is not None:
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}

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
