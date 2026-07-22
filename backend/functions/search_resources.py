"""
GET /resources/search
Query params:
  q            free-text query (semantic vector similarity + lexical)
  xb12         filter by XB12 code (A,C,D,E,F,G,Y) - comma-separated allowed
  subject      filter by subject (case-insensitive, partial)
  classNumber  filter by class number (case-insensitive, partial)
  materialType filter by "textbook" | "platform"
  size         max results (default 25)

Primary ranking is semantic similarity: the query text is embedded with the
same model used at index time and matched against each resource's vector via
k-NN on the OpenSearch Serverless VECTORSEARCH collection. Because the vectors
capture meaning, this tolerates partial words ("Bio" -> "Biology"), typos, and
subject synonyms. Lexical prefix/fuzzy clauses are layered in to boost exact
title matches, and a lexical-only fallback is used if embeddings are
unavailable.
"""

import os

from xb12_common import embeddings
from xb12_common.aoss import AossClient, AossError
from xb12_common.responses import ok, server_error, query_params, http_method, respond

AOSS_INDEX = os.environ.get("AOSS_INDEX", "resources")

# Lexical fields used to boost exact/prefix title matches on top of similarity.
_TEXT_FIELDS = ["title^3", "author^2", "publisher", "description"]


def _terms_filter(field, raw):
    """Exact match filter (used for dropdown values like xb12 code / type)."""
    values = [v.strip() for v in raw.split(",") if v.strip()]
    if not values:
        return None
    if len(values) == 1:
        return {"term": {field: values[0]}}
    return {"terms": {field: values}}


def _partial_filter(field, raw):
    """Case-insensitive substring filter for free-text keyword fields."""
    value = raw.strip().lower()
    if not value:
        return None
    return {"wildcard": {field: {"value": f"*{value}*", "case_insensitive": True}}}


def handler(event, context):
    if http_method(event) == "OPTIONS":
        return respond(200, {})

    params = query_params(event)
    q = (params.get("q") or "").strip()
    size = int(params.get("size") or 25)

    # ---- Filters ---------------------------------------------------------
    filters = []
    for field, param in (("xb12Code", "xb12"), ("materialType", "materialType")):
        raw = params.get(param)
        if raw:
            clause = _terms_filter(field, raw)
            if clause:
                filters.append(clause)
    for field, param in (("subject", "subject"), ("classNumber", "classNumber")):
        raw = params.get(param)
        if raw:
            clause = _partial_filter(field, raw)
            if clause:
                filters.append(clause)

    # ---- Query -----------------------------------------------------------
    should = []
    if q:
        vector = embeddings.embed_text(q)
        if vector:
            # Semantic similarity (primary signal).
            should.append(
                {
                    "knn": {
                        "embedding": {
                            "vector": vector,
                            "k": max(size, 25),
                        }
                    }
                }
            )
        # Lexical boosts: prefix ("Bio" -> "Biology") and typo tolerance.
        should.append(
            {"multi_match": {"query": q, "fields": _TEXT_FIELDS, "type": "phrase_prefix"}}
        )
        should.append(
            {
                "multi_match": {
                    "query": q,
                    "fields": _TEXT_FIELDS,
                    "fuzziness": "AUTO",
                    "prefix_length": 1,
                }
            }
        )

    bool_query = {}
    if should:
        bool_query["should"] = should
        bool_query["minimum_should_match"] = 1
    else:
        bool_query["must"] = [{"match_all": {}}]
    if filters:
        bool_query["filter"] = filters

    body = {"size": size, "query": {"bool": bool_query}}

    client = AossClient()
    try:
        result = client.search(AOSS_INDEX, body)
    except AossError as exc:
        if exc.status == 404:
            return ok({"count": 0, "resources": []})
        return server_error("Search failed.", detail=exc.body)
    except Exception as exc:  # noqa: BLE001
        return server_error("Search failed.", detail=str(exc))

    hits = (result.get("hits") or {}).get("hits") or []
    resources = []
    for h in hits:
        src = h.get("_source", {})
        src.pop("embedding", None)  # never return the raw vector
        src["_score"] = h.get("_score")
        resources.append(src)

    return ok({"count": len(resources), "resources": resources})
