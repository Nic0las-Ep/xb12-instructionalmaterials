"""Shared HTTP response helpers and request parsing for API Gateway proxy Lambdas."""

import decimal
import json

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            # Emit whole numbers as int, otherwise float.
            return int(obj) if obj == obj.to_integral_value() else float(obj)
        return super().default(obj)


def respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": _CORS_HEADERS,
        "body": json.dumps(body, cls=_DecimalEncoder),
    }


def ok(body):
    return respond(200, body)


def bad_request(message, **extra):
    return respond(400, {"error": message, **extra})


def server_error(message="Internal server error", **extra):
    return respond(500, {"error": message, **extra})


def parse_body(event):
    """Parse a JSON body from an API Gateway (REST or HTTP API) proxy event."""
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


def query_params(event):
    return event.get("queryStringParameters") or {}


def http_method(event):
    """Return the HTTP method for either REST (v1) or HTTP API (v2) events."""
    if "httpMethod" in event:
        return event["httpMethod"]
    return (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", "")
    )
