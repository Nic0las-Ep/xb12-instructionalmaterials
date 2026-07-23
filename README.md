# XB12 Instructional Materials Registry

A cloud application for collecting course instructional-material adoptions,
classifying them with the XB12 cost code, and publishing approved resource
links to downstream destinations.

The frontend is static (served by CloudFront from a private S3 bucket) and talks
to a REST API (API Gateway + Python Lambdas). Data lives in DynamoDB; semantic
search uses OpenSearch Serverless with Amazon Bedrock (Titan) embeddings. All
infrastructure is defined with the AWS CDK in `infra/`.

> The Course Schedule, Bookstore, and MIS Reporting pages are **demonstration
> mockups** and are **not** integrations with real external systems.

---

## Architecture

```
Browser (CloudFront + S3)
   │  config.json -> apiBaseUrl
   ▼
API Gateway (REST, CORS)
   ▼
Lambda functions (Python 3.12, shared xb12_common layer)
   ├── isbn_lookup          POST /isbn-lookup
   ├── search_resources     GET  /resources/search
   ├── create_resource      POST /resources
   ├── course_resources     GET/POST /course-resources, DELETE /course-resources/{id}
   ├── submit_class         POST /submit-class
   ├── submissions          GET/PUT/DELETE /submissions[/{id}]
   ├── publish_submission   POST /admin/submissions/{submissionId}/publish   (NEW)
   └── published_links      GET  /published-links?destination=...            (NEW)
   ▼
DynamoDB: Resource-index, Textbookhistory-index, Xb12-submissions,
          PublishedLinks-index (NEW)
OpenSearch Serverless (resource search) · Amazon Bedrock (embeddings)
```

---

## End-to-end flow

1. **Professor submission.** A professor adds materials for a course section on
   the form (`index.html`) and submits. `POST /submit-class` computes the
   section-level XB12 code, writes usage back to the resource catalog, and
   records a submission in `Xb12-submissions` with status `Pending`.
2. **Admin review.** A reviewer opens `admin.html`, inspects the submission, and
   sets a status (`Pending`, `Under Review`, `Approved`, `Needs Correction`)
   plus optional internal notes via `PUT /submissions/{id}`.
3. **Publishing.** Once a submission is **Approved**, the reviewer clicks
   **Publish Approved Links**, confirms the extracted URLs, picks destinations,
   and publishes. `POST /admin/submissions/{submissionId}/publish` re-validates
   approval, extracts/validates/de-duplicates the URLs, and writes idempotent
   records to `PublishedLinks-index`.
4. **Destinations.** The three mock pages load their links via
   `GET /published-links?destination=...` and render clickable resource links.

---

## Mock destinations

| Page | Destination id | Purpose |
| --- | --- | --- |
| `course-schedule.html` | `course-schedule` | Section table: class, section, professor, CRN, and cost code (ZTC/LTC/Standard). |
| `bookstore.html` | `bookstore` | Per-material table: class, professor, CRN, section, textbook ISBN, learning-platform URL, and price (with Class/CRN filters). |
| `mis-reporting.html` | `mis-reporting` | Compliance report table (Course, CRN, XB12 data-entry code, URL, date, submission id) with Course/CRN filters. |

Each page escapes all backend text, opens links with
`target="_blank" rel="noopener noreferrer"`, and has loading / empty / error
states.

---

## API routes (publishing)

### `POST /admin/submissions/{submissionId}/publish`

Request body:

```json
{ "destinations": ["course-schedule", "bookstore", "mis-reporting"] }
```

Response:

```json
{
  "success": true,
  "submissionId": "…",
  "publishedCount": 3,
  "skippedDuplicateCount": 0,
  "publishedMaterialCount": 2,
  "publishedUrlCount": 1,
  "publishedAt": "2026-07-22T00:00:00Z",
  "destinations": ["course-schedule", "bookstore", "mis-reporting"]
}
```

`publishedCount` is the number of new (submission, destination) rows written;
re-publishing refreshes existing rows in place and counts them under
`skippedDuplicateCount`. The backend rejects the request (400) when the
submission is not `Approved` ("Approve this submission before publishing."),
when no valid destination is selected, or when the submission has no materials
to publish. Unknown submission → 404.

### `GET /published-links?destination=course-schedule`

`destination` must be one of `course-schedule`, `bookstore`, `mis-reporting`.

```json
{
  "count": 1,
  "destination": "course-schedule",
  "publications": [
    {
      "publicationId": "…",
      "submissionId": "…",
      "coursePrefix": "ENGL",
      "courseNumber": "1A",
      "section": "01",
      "crn": "12345",
      "professor": "Prof. Ada Lovelace",
      "costCode": "ZTC",
      "xb12Code": "E",
      "xb12Meaning": "…",
      "destination": "course-schedule",
      "materials": [
        { "title": "…", "isbn": "9781947172517", "url": "", "price": 0, "materialType": "textbook", "costStatus": "ZTC" },
        { "title": "…", "isbn": "", "url": "https://platform.edu/course", "materialType": "platform", "costStatus": "STANDARD" }
      ],
      "urls": ["https://platform.edu/course"],
      "publishedAt": "…"
    }
  ]
}
```

Only these display fields are returned — never admin notes, survey answers, or
embeddings. (Professor name is included because the destination pages display
it.)

---

## DynamoDB: `PublishedLinks-index`

One row per **(submission, destination)** — a small snapshot of what each
destination page renders.

| Field | Notes |
| --- | --- |
| `id` (PK) | Deterministic key: `submissionId#destination`. |
| `publicationId` | Same as `id`. |
| `submissionId` | Source submission id. |
| `destination` | `course-schedule` \| `bookstore` \| `mis-reporting`. |
| `coursePrefix` / `courseNumber` / `section` / `crn` | Section identity. |
| `professor` | Respondent name (shown on the destination pages). |
| `costCode` | `ZTC` \| `LTC` \| `Standard` \| `No Material` (from the XB12 code). |
| `xb12Code` / `xb12Meaning` | XB12 INSTRUCTIONAL-MATERIAL-COST (for MIS). |
| `materials` | Per-material snapshot: `{ title, isbn, url, price, materialType, costStatus }`. |
| `urls` | Validated, de-duplicated resource URLs (used by MIS). |
| `publishedAt` | ISO-8601 timestamp. |
| `publishedBy` | `admin` (or the authenticated admin identity, when Cognito is added). |

**GSI `destination-index`** — PK `destination`, SK `publishedAt` — lets the read
endpoint fetch a destination's publications newest-first. Each row is already
one publication, so no grouping is needed.

### What each page shows

- **Course Schedule** — class, section, professor, CRN, and the cost code.
- **Bookstore** — one row per material: class, professor, CRN, section, the
  textbook **ISBN** and the learning-platform **URL** in separate columns, and
  the **price**.
- **MIS Reporting** — Course, CRN, XB12 code (data-entry column), published URL,
  date, and source submission id.

> Price is captured on submission going forward; submissions created before this
> was added show no price until they are re-submitted through the form.

---

## URL extraction & validation

Extraction (`xb12_common/urls.py`) pulls URLs **only** from resource-bearing
fields — each material's `url` / `oerUrl` / `resourceUrl` / `platformUrl` /
`link`, plus free-text description fields — never from admin notes, titles,
ISBNs, CRNs, course numbers, or professor names.

Each candidate is:

- matched with `https?://…` (so `javascript:`, `data:`, `file:`, ISBNs, and
  course numbers never qualify),
- validated (scheme must be `http`/`https`, host required),
- normalized (lowercase scheme+host, drop fragment, drop default port, strip a
  trailing slash), and
- de-duplicated by normalized form.

## Duplicate prevention (idempotency)

Each `(submissionId, destination)` maps to a deterministic `id`. The first write
for a destination uses a conditional put (`attribute_not_exists(id)`) and counts
as published; if the row already exists it is refreshed in place and counted as
a skipped duplicate. Re-publishing the same submission is therefore safe, never
produces duplicates, and picks up any edits to the submission.

---

## Admin Publish button

Located in the submission detail modal in `admin.html`, next to the review
controls:

- Labeled **Publish Approved Links**; disabled unless the submission status is
  `Approved` (otherwise it shows "Approve this submission before publishing.").
- Clicking it opens a confirmation panel that previews the materials found in
  the submission (textbook ISBNs and learning-platform URLs) and destination
  checkboxes (all three selected by default).
- On confirm it disables the button (preventing double-submit), calls the
  publish route, and reports success with the count, destinations, and
  timestamp.
- A **Published to:** status area shows which destinations already contain the
  submission. Changing an already-published submission back to
  `Needs Correction` shows a warning but never auto-unpublishes.

Authorization is re-validated in the backend; the disabled button is only a
convenience. The route is namespaced under `/admin/...` so a Cognito (or other)
admin authorizer can be attached later without code changes.

---

## Deploy (AWS CDK)

Prerequisites: Node.js + AWS CDK, Python 3.12, and AWS credentials for the
target account/region (us-west-2).

```bash
cd infra
source .venv/bin/activate          # or create one: python3 -m venv .venv && pip install -r requirements.txt
export CDK_DEFAULT_ACCOUNT=<account-id>
export CDK_DEFAULT_REGION=us-west-2
cdk deploy --app "python app.py" --require-approval never
```

The deployment creates/updates the Lambdas, the `PublishedLinks-index` table
and its `destination-index` GSI, the API routes, and redeploys the frontend
(including the three mock pages) to S3/CloudFront with a generated `config.json`.

Stack outputs include `ApiUrl`, `SiteUrl`, `SiteBucketName`, and
`DistributionId`.

---

## Testing

Backend unit tests (no AWS/network required) cover URL extraction/validation,
destination validation, idempotent publishing (via a fake table), storage
failure, and the read grouping:

```bash
cd backend
PYTHONPATH=layer/python:functions python3 -m unittest tests.test_publishing -v
```

### Manual demo test

1. Submit a form (`index.html`) that includes a valid resource URL.
2. Open `admin.html`, open the submission, set status **Approved**, save.
3. **Publish Approved Links** becomes enabled — click it, keep all three
   destinations, and publish.
4. Open `course-schedule.html`, `bookstore.html`, and `mis-reporting.html` and
   confirm the link appears and is clickable on each.
5. Publish the same submission again and confirm no duplicate rows are created
   (the response reports `skippedDuplicateCount`).

---

## Project layout

```
backend/
  functions/
    publish_submission.py     # POST /admin/submissions/{id}/publish
    published_links.py        # GET  /published-links
    …                         # existing functions
  layer/python/xb12_common/
    urls.py                   # URL extraction / validation / normalization
    responses.py, xb12.py, …  # existing shared helpers
  tests/
    test_publishing.py        # publishing unit tests
frontend/
  admin.html                  # + Publish Approved Links UI
  course-schedule.html        # mock destination
  bookstore.html              # mock destination
  mis-reporting.html          # mock destination
  js/api.js                   # + publishSubmission / getPublishedLinks
infra/
  xb12_stack/xb12_stack.py    # + PublishedLinks-index table, Lambdas, routes
```

## Remaining TODOs

- Add a Cognito (or other) authorizer on `/admin/...` and `/submissions` — these
  routes are currently open.
- Optionally surface `publishedBy` (admin identity) once auth is in place.
