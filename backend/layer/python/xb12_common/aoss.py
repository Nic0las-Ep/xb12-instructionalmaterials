"""
Minimal Amazon OpenSearch Serverless (AOSS) client.

Signs requests with SigV4 for the ``aoss`` service using botocore (already
present in the Lambda runtime) and sends them with urllib from the standard
library, so the Lambda needs no bundled third-party dependencies.
"""

import json
import os
import urllib.request
import urllib.error

import botocore.session
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth

_SERVICE = "aoss"


class AossError(Exception):
    """Raised when OpenSearch Serverless returns a non-2xx response."""

    def __init__(self, status, body):
        super().__init__(f"AOSS request failed ({status}): {body}")
        self.status = status
        self.body = body


class AossClient:
    def __init__(self, endpoint=None, region=None):
        self.endpoint = (endpoint or os.environ["AOSS_ENDPOINT"]).rstrip("/")
        self.region = region or os.environ.get("AWS_REGION", "us-west-2")
        self._session = botocore.session.Session()

    # -- low level ---------------------------------------------------------
    def _signed_headers(self, method, url, body):
        creds = self._session.get_credentials().get_frozen_credentials()
        request = AWSRequest(method=method, url=url, data=body)
        # AOSS requires the payload hash header to be UNSIGNED-PAYLOAD.
        request.headers.add_header("X-Amz-Content-SHA256", "UNSIGNED-PAYLOAD")
        SigV4Auth(creds, _SERVICE, self.region).add_auth(request)
        return dict(request.headers)

    def request(self, method, path, body=None):
        url = f"{self.endpoint}/{path.lstrip('/')}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        headers = self._signed_headers(method, url, data)
        headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise AossError(exc.code, raw)

    # -- helpers -----------------------------------------------------------
    def index_exists(self, index):
        try:
            self.request("HEAD", f"/{index}")
            return True
        except AossError as exc:
            if exc.status == 404:
                return False
            raise

    def ensure_index(self, index, mapping=None):
        """Create the index (idempotent) with a keyword/text friendly mapping."""
        if self.index_exists(index):
            return
        default_mapping = {
            "settings": {"index.knn": False},
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "author": {"type": "text"},
                    "publisher": {"type": "text"},
                    "ISBN": {"type": "keyword"},
                    "url": {"type": "keyword"},
                    "subject": {"type": "keyword"},
                    "classNumber": {"type": "keyword"},
                    "materialType": {"type": "keyword"},
                    "costType": {"type": "keyword"},
                    "xb12Code": {"type": "keyword"},
                    "ztcLtc": {"type": "keyword"},
                    "price": {"type": "float"},
                    "description": {"type": "text"},
                    "createdAt": {"type": "date"},
                }
            },
        }
        try:
            self.request("PUT", f"/{index}", mapping or default_mapping)
        except AossError as exc:
            # Tolerate a race where another invocation created it first.
            if exc.status == 400 and "resource_already_exists" in exc.body:
                return
            raise

    def index_document(self, index, doc_id, document):
        # OpenSearch Serverless does not support caller-supplied document IDs
        # ("Document ID is not supported in create/index operation request").
        # We let the service generate the _id and keep our own id as a field
        # inside the document (already present) for correlation and search.
        return self.request("POST", f"/{index}/_doc", document)

    def search(self, index, query_body):
        return self.request("POST", f"/{index}/_search", query_body)
