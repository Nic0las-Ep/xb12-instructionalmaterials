"""
GET /resources/search
Query params:
  q            free-text query over title / author / publisher / description
  xb12         filter by XB12 code (A,C,D,E,F,G,Y) - comma-separated allowed
  subject      filter by subject
  classNumber  filter by class number
  materialType filter by "textbook" | "platform"
  size         max results (default 25)

Searches the OpenSearch Serverless "resources" index and returns matches.
"""

import os

from xb12_common.aoss import AossClient, AossError
from xb12_common.responses import ok, server_error, query_params, http_method, respond

AOSS_INDEX = os.environ.get("AOSS_INDEX", "resources")


def _terms_filter(field, raw):
    values = [v.strip() for v in raw.split(",") if v.strip()]
    if not values:
        return None
    if len(values) == 1:
        return {"term": {field: values[0]}}
    return {"terms": {field: values}}


def handler(event, context):
    if http_method(event) == "OPTIONS":
        return respond(200, {})

    params = query_params(event)
    q = (params.get("q") or "").strip()
    size = int(params.get("size") or 25)

    must = []
    if q:
        must.append(
            {
                "multi_match": {
                    "query": q,
                    "fields": ["title^3", "author^2", "publisher", "description", "subject"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        )

    filters = []
    for field, param in (
        ("xb12Code", "xb12"),
        ("subject", "subject"),
        ("classNumber", "classNumber"),
        ("materialType", "materialType"),
    ):
        raw = params.get(param)
        if raw:
            clause = _terms_filter(field, raw)
            if clause:
                filters.append(clause)

    query = {"bool": {}}
    query["bool"]["must"] = must if must else [{"match_all": {}}]
    if filters:
        query["bool"]["filter"] = filters

    body = {"size": size, "query": query, "sort": ["_score"]}

    client = AossClient()
    try:
        result = client.search(AOSS_INDEX, body)
    except AossError as exc:
        if exc.status == 404:
            # Index not created yet -> no resources indexed.
            return ok({"count": 0, "resources": []})
        return server_error("Search failed.", detail=exc.body)
    except Exception as exc:  # noqa: BLE001
        return server_error("Search failed.", detail=str(exc))

    hits = (result.get("hits") or {}).get("hits") or []
    resources = []
    for h in hits:
        src = h.get("_source", {})
        src["_score"] = h.get("_score")
        resources.append(src)

    return ok({"count": len(resources), "resources": resources})
