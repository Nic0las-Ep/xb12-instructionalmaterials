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

import json
import os

from xb12_common import embeddings
from xb12_common.aoss import AossClient, AossError
from xb12_common.responses import ok, server_error, query_params, http_method, respond

AOSS_INDEX = os.environ.get("AOSS_INDEX", "resources")

# Minimum cosine-similarity score for a semantic hit to be considered relevant.
# Calibrated from real query scores: on-topic results sit >= ~0.385 and the
# unrelated "noise floor" sits <= ~0.365, so 0.37 cleanly separates them.
SIMILARITY_MIN_SCORE = float(os.environ.get("SIMILARITY_MIN_SCORE", "0.37"))

# Lexical fields for the primary title/author search. Kept narrow (title,
# author) so results stay specific to what the user typed rather than matching
# on descriptions or topical text.
_TEXT_FIELDS = ["title^3", "author^2"]


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


def _class_filter(raw):
    """
    Match resources used in a given class (e.g. "ACCT 1A"). Class names are
    stable across semesters (only CRN/section change), so this checks both the
    resource's primary classNumber and its usedInCourses history (populated when
    classes are submitted).
    """
    value = raw.strip()
    if not value:
        return None
    lower = value.lower()
    return {
        "bool": {
            "should": [
                {"wildcard": {"classNumber": {"value": f"*{lower}*", "case_insensitive": True}}},
                {"term": {"usedInCourses.keyword": value}},
                {"match_phrase": {"usedInCourses": value}},
            ],
            "minimum_should_match": 1,
        }
    }


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
    subject_raw = params.get("subject")
    if subject_raw:
        clause = _partial_filter("subject", subject_raw)
        if clause:
            filters.append(clause)
    # Class-name filter (e.g. "ACCT 1A") matches classNumber + usage history.
    class_raw = params.get("classNumber") or params.get("className")
    if class_raw:
        clause = _class_filter(class_raw)
        if clause:
            filters.append(clause)

    client = AossClient()

    # ---- Query -----------------------------------------------------------
    # No free-text query -> browse everything (filters still apply).
    if not q:
        body = {"size": size, "query": {"bool": _with_filters({"must": [{"match_all": {}}]}, filters)}}
        return _run(client, body)

    # Primary path: LEXICAL match on title/author. Prefix matching handles
    # partial words ("Bio" -> "Biology") and fuzzy matching handles typos, while
    # keeping results specific to what the user typed - so topically-adjacent
    # titles that don't contain the term (e.g. "Anatomy & Physiology" for "Bio")
    # are NOT returned.
    lexical = {
        "should": [
            {"multi_match": {"query": q, "fields": _TEXT_FIELDS, "type": "phrase_prefix"}},
            {"multi_match": {"query": q, "fields": _TEXT_FIELDS, "fuzziness": "AUTO", "prefix_length": 1}},
        ],
        "minimum_should_match": 1,
    }
    body = {"size": size, "query": {"bool": _with_filters(lexical, filters)}}
    response = _run(client, body)
    lexical_hits = _extract(response)
    if lexical_hits is None:  # error already packaged as an HTTP response
        return response
    if lexical_hits:
        return ok({"count": len(lexical_hits), "resources": lexical_hits})

    # Fallback: no lexical match at all -> semantic k-NN similarity, gated by a
    # relevance cutoff, so unusual/synonym queries still return something useful.
    vector = embeddings.embed_text(q)
    if not vector:
        return ok({"count": 0, "resources": []})
    knn = {"must": [{"knn": {"embedding": {"vector": vector, "k": max(size, 50)}}}]}
    body = {
        "size": size,
        "min_score": SIMILARITY_MIN_SCORE,
        "query": {"bool": _with_filters(knn, filters)},
    }
    return _run(client, body)


def _with_filters(bool_query, filters):
    if filters:
        bool_query = dict(bool_query)
        bool_query["filter"] = filters
    return bool_query


def _extract(response):
    """Return the resource list from a successful _run response, or None on error."""
    if response.get("statusCode") != 200:
        return None
    return json.loads(response["body"]).get("resources", [])


def _run(client, body):
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
