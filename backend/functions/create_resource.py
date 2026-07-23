"""
POST /resources
Register a new textbook (with ISBN) or learning platform (with URL) in the
catalog. Computes the XB12 code, persists to the Resource-index DynamoDB table,
and indexes the document in OpenSearch so it is searchable in the future.

Body (JSON):
  title        (required)
  materialType : "textbook" | "platform"   (inferred from isbn/url when absent)
  ISBN         : required for textbooks
  url          : required for platforms
  author, publisher, description, subject, classNumber
  costType     : "oer" | "free_non_oer" | "subsidized" | "priced"
  price        : number (for priced / subsidized materials)
"""

import datetime
import os
import uuid
from decimal import Decimal

import boto3

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

RESOURCE_TABLE = os.environ["RESOURCE_TABLE"]
AOSS_INDEX = os.environ.get("AOSS_INDEX", "resources")
LOW_COST_THRESHOLD = os.environ.get("LOW_COST_THRESHOLD", "50")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(RESOURCE_TABLE)


def _to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def handler(event, context):
    if http_method(event) == "OPTIONS":
        return respond(200, {})

    body = parse_body(event)

    title = (body.get("title") or "").strip()
    isbn = (body.get("ISBN") or body.get("isbn") or "").strip()
    url = (body.get("url") or "").strip()

    material_type = (body.get("materialType") or "").strip().lower()
    if not material_type:
        material_type = "platform" if url and not isbn else "textbook"

    if not title:
        return bad_request("A 'title' is required.")
    if material_type == "textbook" and not isbn:
        return bad_request("Textbooks require an 'ISBN'.")
    if material_type == "platform" and not url:
        return bad_request("Learning platforms require a 'url'.")

    price = _to_decimal(body.get("price"))
    cost_type = (body.get("costType") or "").strip().lower()

    # Detect OER sources (OpenStax, LibreTexts, Pressbooks, ...). These are
    # no-cost OER, so they classify as XB12 code E regardless of any mistaken
    # cost marking on the way in.
    oer_source = xb12.is_oer_source(
        title, body.get("author"), body.get("publisher"), url
    )
    if oer_source:
        cost_type = "oer"

    # Classify this resource on its own (per-resource XB12 code for the catalog).
    material = {
        "costType": cost_type,
        "price": price,
        "isOER": bool(body.get("isOER")) or cost_type == "oer" or oer_source,
        "url": url,
        "isbn": isbn,
    }
    code, explanation = xb12.classify([material], LOW_COST_THRESHOLD)
    ztc_ltc = xb12.zero_low_cost_marking(code)
    # Friendly cost-status label kept alongside the official XB12 letter code.
    if oer_source:
        cost_status = "ZTC-OER"
    else:
        cost_status = ztc_ltc or ("NONE" if code == "A" else "STANDARD")

    resource_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat() + "Z"

    item = {
        "id": resource_id,
        "title": title,
        "materialType": material_type,
        "xb12Code": code,
        "ztcLtc": ztc_ltc,
        "costStatus": cost_status,
        "createdAt": now,
    }
    # Only set indexed string attributes when non-empty (DynamoDB GSI keys
    # cannot be empty strings).
    if isbn:
        item["ISBN"] = isbn
    if url:
        item["url"] = url
    for key in ("author", "publisher", "description", "subject", "classNumber", "currency"):
        val = body.get(key)
        if val:
            item[key] = str(val).strip()
    if cost_type:
        item["costType"] = cost_type
    if price is not None:
        item["price"] = price

    # ---- Persist to DynamoDB (catalog / source of truth) -----------------
    try:
        _table.put_item(Item=item)
    except Exception as exc:  # noqa: BLE001
        return server_error("Failed to save resource to DynamoDB.", detail=str(exc))

    # ---- Index in OpenSearch (searchable) --------------------------------
    search_doc = dict(item)
    if isinstance(search_doc.get("price"), Decimal):
        search_doc["price"] = float(search_doc["price"])

    # Semantic embedding for vector-similarity search (tolerates partial words
    # and typos). Falls back to lexical-only indexing if embedding is
    # unavailable.
    vector = embeddings.embed_text(embeddings.resource_text(search_doc))
    if vector:
        search_doc["embedding"] = vector

    index_warning = None
    try:
        client = AossClient()
        client.ensure_index(AOSS_INDEX, embed_dim=EMBED_DIM)
        client.index_document(AOSS_INDEX, resource_id, search_doc)
    except Exception as exc:  # noqa: BLE001
        # The catalog write succeeded; report search indexing as a soft failure.
        index_warning = f"Resource saved but search indexing failed: {exc}"

    # Do not echo the (large) embedding vector back to the client.
    search_doc.pop("embedding", None)

    response = {
        "success": True,
        "resource": search_doc,
        "xb12": {"code": code, "meaning": xb12.XB12_MEANINGS[code], "explanation": explanation, "ztcLtc": ztc_ltc},
    }
    if index_warning:
        response["warning"] = index_warning
    return ok(response)
