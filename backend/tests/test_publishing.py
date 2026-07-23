"""
Unit tests for the publishing workflow.

Run from the repo root:

    PYTHONPATH=backend/layer/python:backend/functions \
        python3 -m unittest backend.tests.test_publishing -v

or simply:

    cd backend && PYTHONPATH=layer/python:functions python3 -m unittest \
        tests.test_publishing -v

These tests exercise the AWS-free core: URL extraction/validation, destination
validation, idempotent publish (via a FakeTable), and the read grouping. No AWS
resources or network access are required.
"""

import os
import sys
import unittest

# Make the shared layer and function modules importable without AWS.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_BACKEND, "layer", "python"))
sys.path.insert(0, os.path.join(_BACKEND, "functions"))

# publish_submission / published_links read env vars at import time.
os.environ.setdefault("SUBMISSIONS_TABLE", "Xb12-submissions")
os.environ.setdefault("PUBLISHED_LINKS_TABLE", "PublishedLinks-index")
# The function modules create boto3 clients at import time, which requires a
# region. Set one so the tests are hermetic and don't depend on ambient AWS
# config. No AWS calls are actually made (the tests use a fake table).
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")

from botocore.exceptions import ClientError  # noqa: E402

from xb12_common import urls as urlutil  # noqa: E402


class FakeTable:
    """Minimal DynamoDB Table stand-in supporting conditional put_item."""

    def __init__(self, fail_after=None):
        self.items = {}
        self.put_calls = 0
        self.fail_after = fail_after  # raise a generic ClientError after N puts

    def put_item(self, Item=None, ConditionExpression=None):
        self.put_calls += 1
        if self.fail_after is not None and self.put_calls > self.fail_after:
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException"}},
                "PutItem",
            )
        key = Item["id"]
        if ConditionExpression == "attribute_not_exists(id)" and key in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
            )
        self.items[key] = dict(Item)
        return {}


def _submission(materials, status="Approved", **extra):
    base = {
        "id": "sub-1",
        "status": status,
        "coursePrefix": "ENGL",
        "courseNumber": "1A",
        "crn": "12345",
        "materials": materials,
    }
    base.update(extra)
    return base


# Import after helpers so env is set.
import publish_submission as ps  # noqa: E402
import published_links as pl  # noqa: E402


class UrlHelperTests(unittest.TestCase):
    def test_single_valid_url(self):
        pairs = urlutil.collect_urls(["https://example.edu/resource"])
        self.assertEqual([p["normalizedUrl"] for p in pairs], ["https://example.edu/resource"])

    def test_duplicate_urls_removed(self):
        pairs = urlutil.collect_urls(
            ["https://example.edu/x", "https://example.edu/x/", "HTTPS://Example.edu/x"]
        )
        self.assertEqual(len(pairs), 1)

    def test_unsafe_protocols_rejected(self):
        pairs = urlutil.collect_urls(
            ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd"]
        )
        self.assertEqual(pairs, [])

    def test_non_url_values_ignored(self):
        # ISBN, course number, CRN, title, professor name
        pairs = urlutil.collect_urls(
            ["9781947172517", "1A", "12345", "Intro to Biology", "Jane Doe"]
        )
        self.assertEqual(pairs, [])

    def test_multiple_urls_in_text(self):
        text = "See https://a.edu/one and also https://b.edu/two for details."
        pairs = urlutil.collect_urls([text])
        self.assertEqual(
            sorted(p["normalizedUrl"] for p in pairs),
            ["https://a.edu/one", "https://b.edu/two"],
        )

    def test_normalize_strips_fragment_and_default_port(self):
        self.assertEqual(
            urlutil.normalize_url("https://Example.edu:443/path/#section"),
            "https://example.edu/path",
        )


class DestinationValidationTests(unittest.TestCase):
    def test_no_destination_rejected(self):
        valid, err = ps.validate_destinations([])
        self.assertEqual(valid, [])
        self.assertIsNotNone(err)

    def test_unknown_destination_rejected(self):
        valid, err = ps.validate_destinations(["course-schedule", "moon"])
        self.assertEqual(valid, [])
        self.assertIn("Unknown destination", err)

    def test_valid_destinations_deduped(self):
        valid, err = ps.validate_destinations(
            ["course-schedule", "course-schedule", "bookstore"]
        )
        self.assertIsNone(err)
        self.assertEqual(valid, ["course-schedule", "bookstore"])


class ExtractionTests(unittest.TestCase):
    def test_extract_from_material_url(self):
        sub = _submission([{"title": "A", "url": "https://example.edu/a"}])
        pairs = ps.extract_publishable_urls(sub)
        self.assertEqual([p["normalizedUrl"] for p in pairs], ["https://example.edu/a"])

    def test_extract_ignores_isbn_and_notes(self):
        sub = _submission(
            [{"title": "A", "ISBN": "9781947172517", "url": ""}],
            adminNotes="See https://secret.internal/should-not-publish",
        )
        pairs = ps.extract_publishable_urls(sub)
        self.assertEqual(pairs, [])


class PublishTests(unittest.TestCase):
    def test_publish_single_url_multiple_destinations(self):
        sub = _submission([{"url": "https://example.edu/a"}])
        table = FakeTable()
        result, err = ps.publish(sub, ["course-schedule", "bookstore"], "admin", table)
        self.assertIsNone(err)
        self.assertEqual(result["publishedCount"], 2)
        self.assertEqual(result["skippedDuplicateCount"], 0)

    def test_publish_multiple_urls(self):
        sub = _submission(
            [{"url": "https://example.edu/a"}, {"url": "https://example.edu/b"}]
        )
        table = FakeTable()
        result, err = ps.publish(sub, ["course-schedule"], "admin", table)
        self.assertIsNone(err)
        self.assertEqual(result["publishedCount"], 2)

    def test_publish_twice_is_idempotent(self):
        sub = _submission([{"url": "https://example.edu/a"}])
        table = FakeTable()
        ps.publish(sub, ["course-schedule"], "admin", table)
        result, err = ps.publish(sub, ["course-schedule"], "admin", table)
        self.assertIsNone(err)
        self.assertEqual(result["publishedCount"], 0)
        self.assertEqual(result["skippedDuplicateCount"], 1)

    def test_publish_no_urls(self):
        sub = _submission([{"title": "A", "ISBN": "123", "url": ""}])
        table = FakeTable()
        result, err = ps.publish(sub, ["course-schedule"], "admin", table)
        self.assertIsNone(result)
        self.assertIn("no valid URLs", err)

    def test_storage_failure_surfaced(self):
        sub = _submission(
            [{"url": "https://example.edu/a"}, {"url": "https://example.edu/b"}]
        )
        table = FakeTable(fail_after=1)  # first put ok, second raises
        result, err = ps.publish(sub, ["course-schedule"], "admin", table)
        self.assertIsNone(result)
        self.assertIn("Failed to write", err)


class ReadGroupingTests(unittest.TestCase):
    def test_group_rows_by_submission(self):
        rows = [
            {
                "submissionId": "s1",
                "destination": "course-schedule",
                "normalizedUrl": "https://a.edu/1",
                "coursePrefix": "ENGL",
                "courseNumber": "1A",
                "crn": "111",
                "publishedAt": "2026-01-01T00:00:00Z",
            },
            {
                "submissionId": "s1",
                "destination": "course-schedule",
                "normalizedUrl": "https://a.edu/2",
                "coursePrefix": "ENGL",
                "courseNumber": "1A",
                "crn": "111",
                "publishedAt": "2026-01-01T00:00:00Z",
            },
            {
                "submissionId": "s2",
                "destination": "course-schedule",
                "normalizedUrl": "https://b.edu/1",
                "coursePrefix": "BIOL",
                "courseNumber": "10",
                "crn": "222",
                "publishedAt": "2026-02-01T00:00:00Z",
            },
        ]
        pubs = pl.group_rows(rows)
        self.assertEqual(len(pubs), 2)
        # Newest first -> s2 (Feb) before s1 (Jan)
        self.assertEqual(pubs[0]["submissionId"], "s2")
        s1 = next(p for p in pubs if p["submissionId"] == "s1")
        self.assertEqual(sorted(s1["urls"]), ["https://a.edu/1", "https://a.edu/2"])

    def test_group_rows_empty(self):
        self.assertEqual(pl.group_rows([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
