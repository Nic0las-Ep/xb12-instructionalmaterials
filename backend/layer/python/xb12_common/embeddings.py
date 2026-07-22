"""
Text embeddings via Amazon Bedrock (Titan Text Embeddings v2).

Used to power semantic / vector-similarity search on the OpenSearch Serverless
VECTORSEARCH collection. Embeddings are normalized so that an L2/inner-product
nearest-neighbour search ranks results by cosine similarity - which tolerates
partial words ("Bio" -> "Biology"), typos, and subject synonyms.
"""

import json
import os

import boto3

EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))

_client = None


def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime")
    return _client


def embed_text(text):
    """
    Return a normalized embedding vector (list[float]) for the given text,
    or None if the text is empty or the embedding call fails (callers then
    fall back to lexical search).
    """
    text = (text or "").strip()
    if not text:
        return None
    body = json.dumps(
        {"inputText": text[:8000], "dimensions": EMBED_DIM, "normalize": True}
    )
    try:
        resp = _bedrock().invoke_model(
            modelId=EMBED_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        payload = json.loads(resp["body"].read())
        vector = payload.get("embedding")
        if isinstance(vector, list) and vector:
            return vector
    except Exception:  # noqa: BLE001 - degrade gracefully to lexical search
        return None
    return None


def resource_text(resource):
    """Build the text used to embed a catalog resource for semantic search."""
    parts = [
        resource.get("title"),
        resource.get("author"),
        resource.get("publisher"),
        resource.get("subject"),
        resource.get("classNumber"),
        resource.get("materialType"),
        resource.get("description"),
    ]
    return " ".join(str(p) for p in parts if p)
