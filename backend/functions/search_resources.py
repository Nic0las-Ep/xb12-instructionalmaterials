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

# Minimum cosine-similarity score for a semantic hit to be considered relevant.
# Calibrated from real query scores: on-topic results sit >= ~0.385 and the
# unrelated "noise floor" sits <= ~0.365, so 0.37 cleanly separates them.
SIMILARITY_MIN_SCORE = float(os.environ.get("SIMILARITY_MIN_SCORE", "0.37"))

# Lexical fields (used only as a fallback when embeddings are unavailable).
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
    # Default: browse (no free-text query) -> match everything, filters apply.
    bool_query = {"must": [{"match_all": {}}]}
    min_score = None

    if q:
        vector = embeddings.embed_text(q)
        if vector:
            # Primary path: pure semantic k-NN, gated by a similarity cutoff so
            # only genuinely relevant resources are returned (not every doc).
            # Filters carry no score, so the top-level min_score applies to the
            # k-NN similarity score directly.
            bool_query = {
                "must": [
                    {"knn": {"embedding": {"vector": vector, "k": max(size, 50)}}}
                ]
            }
            min_score = SIMILARITY_MIN_SCORE
        else:
            # Fallback (embeddings unavailable): lexical prefix + fuzzy match.
            bool_query = {
                "should": [
                    {"multi_match": {"query": q, "fields": _TEXT_FIELDS, "type": "phrase_prefix"}},
                    {"multi_match": {"query": q, "fields": _TEXT_FIELDS, "fuzziness": "AUTO", "prefix_length": 1}},
                ],
                "minimum_should_match": 1,
            }

    if filters:
        bool_query["filter"] = filters

    body = {"size": size, "query": {"bool": bool_query}}
    if min_score is not None:
        body["min_score"] = min_score

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
