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
        "section": "01",
        "crn": "12345",
        "quarter": "Fall",
        "year": 2025,
        "respondentName": "Prof. Ada Lovelace",
        "sectionXb12Code": "Y",
        "sectionXb12Meaning": "Section does not meet no-cost or low-cost criteria",
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


class CostCodeTests(unittest.TestCase):
    def test_cost_code_labels(self):
        self.assertEqual(ps.cost_code_label("E"), "ZTC")
        self.assertEqual(ps.cost_code_label("C"), "ZTC")
        self.assertEqual(ps.cost_code_label("D"), "LTC")
        self.assertEqual(ps.cost_code_label("Y"), "Standard")
        self.assertEqual(ps.cost_code_label("A"), "No Material")
        self.assertEqual(ps.cost_code_label(""), "")


class TermCodeTests(unittest.TestCase):
    def test_term_codes(self):
        self.assertEqual(ps.mis_term_code("Fall", 2025), "20252")
        self.assertEqual(ps.mis_term_code("Summer", "2026"), "20261")
        self.assertEqual(ps.mis_term_code("Winter", 2026), "20263")
        self.assertEqual(ps.mis_term_code("Spring", 2026), "20264")

    def test_term_code_missing_parts(self):
        self.assertEqual(ps.mis_term_code("", 2025), "")
        self.assertEqual(ps.mis_term_code("Fall", ""), "")
        self.assertEqual(ps.mis_term_code("Fall", "26"), "")  # not 4-digit


class MaterialSnapshotTests(unittest.TestCase):
    def test_snapshot_captures_isbn_url_price(self):
        sub = _submission(
            [
                {"title": "Textbook", "ISBN": "9781947172517", "price": 120},
                {"title": "Platform", "url": "https://platform.edu/course"},
            ]
        )
        snap = ps.build_material_snapshot(sub)
        self.assertEqual(len(snap), 2)
        book = next(m for m in snap if m["isbn"])
        self.assertEqual(book["isbn"], "9781947172517")
        self.assertEqual(book["price"], 120)
        platform = next(m for m in snap if m["url"])
        self.assertEqual(platform["url"], "https://platform.edu/course")

    def test_snapshot_normalizes_material_url(self):
        sub = _submission([{"title": "P", "url": "HTTPS://Platform.edu/x/#top"}])
        snap = ps.build_material_snapshot(sub)
        self.assertEqual(snap[0]["url"], "https://platform.edu/x")


class PublishTests(unittest.TestCase):
    def test_publish_one_row_per_destination(self):
        sub = _submission([{"url": "https://example.edu/a"}])
        table = FakeTable()
        result, err = ps.publish(sub, ["course-schedule", "bookstore"], "admin", table)
        self.assertIsNone(err)
        self.assertEqual(result["publishedCount"], 2)
        self.assertEqual(result["skippedDuplicateCount"], 0)
        self.assertEqual(len(table.items), 2)

    def test_published_row_carries_section_fields(self):
        sub = _submission(
            [{"title": "T", "ISBN": "123", "price": 50, "url": "https://x.edu/a"}]
        )
        table = FakeTable()
        ps.publish(sub, ["bookstore"], "admin", table)
        row = table.items["sub-1#bookstore"]
        self.assertEqual(row["section"], "01")
        self.assertEqual(row["professor"], "Prof. Ada Lovelace")
        self.assertEqual(row["costCode"], "Standard")
        self.assertEqual(row["term"], "20252")  # Fall 2025
        self.assertEqual(row["urls"], ["https://x.edu/a"])
        self.assertEqual(row["materials"][0]["isbn"], "123")
        self.assertEqual(row["materials"][0]["price"], 50)

    def test_publish_twice_refreshes_no_duplicate(self):
        sub = _submission([{"url": "https://example.edu/a"}])
        table = FakeTable()
        ps.publish(sub, ["course-schedule"], "admin", table)
        result, err = ps.publish(sub, ["course-schedule"], "admin", table)
        self.assertIsNone(err)
        self.assertEqual(result["publishedCount"], 0)
        self.assertEqual(result["skippedDuplicateCount"], 1)
        self.assertEqual(len(table.items), 1)  # still one row, refreshed in place

    def test_publish_textbook_without_url(self):
        # A textbook with only an ISBN is still publishable (for the bookstore).
        sub = _submission([{"title": "A", "ISBN": "9781947172517", "url": ""}])
        table = FakeTable()
        result, err = ps.publish(sub, ["bookstore"], "admin", table)
        self.assertIsNone(err)
        self.assertEqual(result["publishedCount"], 1)
        self.assertEqual(result["publishedMaterialCount"], 1)
        self.assertEqual(result["publishedUrlCount"], 0)

    def test_publish_nothing_to_publish(self):
        sub = _submission([])
        table = FakeTable()
        result, err = ps.publish(sub, ["course-schedule"], "admin", table)
        self.assertIsNone(result)
        self.assertIn("no materials", err.lower())

    def test_storage_failure_surfaced(self):
        sub = _submission([{"url": "https://example.edu/a"}])
        table = FakeTable(fail_after=0)  # first put raises
        result, err = ps.publish(sub, ["course-schedule"], "admin", table)
        self.assertIsNone(result)
        self.assertIn("Failed to write", err)


class ReadTests(unittest.TestCase):
    def test_to_publication_maps_fields(self):
        row = {
            "publicationId": "s1#course-schedule",
            "submissionId": "s1",
            "coursePrefix": "ENGL",
            "courseNumber": "1A",
            "section": "02",
            "crn": "111",
            "professor": "Prof. X",
            "costCode": "ZTC",
            "xb12Code": "E",
            "destination": "course-schedule",
            "materials": [{"isbn": "123", "url": "", "price": 0}],
            "urls": ["https://a.edu/1"],
            "publishedAt": "2026-01-01T00:00:00Z",
        }
        pub = pl.to_publication(row)
        self.assertEqual(pub["section"], "02")
        self.assertEqual(pub["professor"], "Prof. X")
        self.assertEqual(pub["costCode"], "ZTC")
        self.assertEqual(pub["materials"][0]["isbn"], "123")
        self.assertEqual(pub["urls"], ["https://a.edu/1"])

    def test_to_publication_legacy_normalized_url(self):
        # Older rows stored a single normalizedUrl; surface it as urls[].
        row = {"submissionId": "s1", "normalizedUrl": "https://a.edu/1", "publishedAt": "z"}
        pub = pl.to_publication(row)
        self.assertEqual(pub["urls"], ["https://a.edu/1"])

    def test_to_publications_newest_first(self):
        rows = [
            {"submissionId": "s1", "publishedAt": "2026-01-01T00:00:00Z"},
            {"submissionId": "s2", "publishedAt": "2026-02-01T00:00:00Z"},
        ]
        pubs = pl.to_publications(rows)
        self.assertEqual(pubs[0]["submissionId"], "s2")

    def test_to_publications_empty(self):
        self.assertEqual(pl.to_publications([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
