/**
 * api.js — Centralised API layer for the XB12 Instructional-Materials Registry
 * ─────────────────────────────────────────────────────────────
 * Every HTTP call to the backend (API Gateway + Lambda) goes through this
 * module. No other file calls fetch() directly.
 *
 * The API base URL is resolved at runtime from /config.json (written by the
 * CDK deployment) so the same built assets work in any environment. When that
 * file is absent (e.g. local dev) it falls back to a localhost default.
 */

// ---------------------------------------------------------------------------
// Configuration (resolved at runtime)
// ---------------------------------------------------------------------------

let BASE_URL = 'http://localhost:5001';

/**
 * Load runtime configuration (API base URL). Safe to call multiple times.
 * @returns {Promise<string>} the resolved base URL.
 */
async function initConfig() {
  try {
    const res = await fetch('config.json', { cache: 'no-store' });
    if (res.ok) {
      const cfg = await res.json();
      if (cfg && cfg.apiBaseUrl) {
        BASE_URL = String(cfg.apiBaseUrl).replace(/\/+$/, '');
      }
    }
  } catch (_) {
    /* keep the default BASE_URL */
  }
  return BASE_URL;
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(message, status = 0, body = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// Internal fetch wrapper
// ---------------------------------------------------------------------------

async function _request(method, path, { body = null, query = null } = {}) {
  let url = `${BASE_URL}${path}`;
  if (query) {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') params.set(k, v);
    });
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const options = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== null) options.body = JSON.stringify(body);

  let response;
  try {
    response = await fetch(url, options);
  } catch (networkError) {
    throw new ApiError('Unable to reach the server. Please try again.', 0);
  }

  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message =
      (data && (data.error || data.message)) || `Server returned ${response.status}`;
    throw new ApiError(message, response.status, data);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Registry API
// ---------------------------------------------------------------------------

/**
 * Look up textbook metadata by ISBN from public registries.
 * @param {string} isbn
 * @returns {Promise<{found:boolean, isbn:string, metadata:object, missingFields:string[], sources:string[]}>}
 */
async function isbnLookup(isbn) {
  return _request('POST', '/isbn-lookup', { body: { isbn } });
}

/**
 * Search the resource catalog (OpenSearch) with optional filters.
 * @param {object} filters { q, xb12, subject, classNumber, materialType, size }
 * @returns {Promise<{count:number, resources:object[]}>}
 */
async function searchResources(filters = {}) {
  return _request('GET', '/resources/search', { query: filters });
}

/**
 * Create a new catalog resource (textbook or platform). Computes XB12,
 * writes to DynamoDB, and indexes it in OpenSearch.
 * @param {object} payload
 * @returns {Promise<{success:boolean, resource:object, xb12:object}>}
 */
async function createResource(payload) {
  return _request('POST', '/resources', { body: payload });
}

/**
 * Adopt a resource into a course (adds a row to the history table).
 * @param {object} payload
 * @returns {Promise<{success:boolean, adoption:object}>}
 */
async function addCourseResource(payload) {
  return _request('POST', '/course-resources', { body: payload });
}

/**
 * List resources adopted for a course.
 * @param {object} q { coursePrefix, courseNumber, quarter, year }
 * @returns {Promise<{count:number, adoptions:object[]}>}
 */
async function listCourseResources(q) {
  return _request('GET', '/course-resources', { query: q });
}

/**
 * Remove a single adopted material from a course (by its adoption id).
 * @param {string} id
 * @returns {Promise<{success:boolean, deleted:string}>}
 */
async function deleteCourseResource(id) {
  return _request('DELETE', `/course-resources/${encodeURIComponent(id)}`);
}

/**
 * Finalize a class submission: computes the section-level XB12 code, records
 * the submission, and writes usage back to the catalog.
 * @param {object} course { coursePrefix, courseNumber, crn, section, quarter, year, professorFirstName, professorLastName }
 * @returns {Promise<{success:boolean, submission:object, section:object}>}
 */
async function submitClass(course) {
  return _request('POST', '/submit-class', { body: course });
}

/** List all class submissions (admin dashboard). */
async function listSubmissions() {
  return _request('GET', '/submissions');
}

/** Update a submission's review status / notes (admin dashboard). */
async function updateSubmission(id, patch) {
  return _request('PUT', `/submissions/${encodeURIComponent(id)}`, { body: patch });
}

/** Delete a submission (admin dashboard). */
async function deleteSubmission(id) {
  return _request('DELETE', `/submissions/${encodeURIComponent(id)}`);
}

// ---------------------------------------------------------------------------
// Publishing API (admin publish + mock destination pages)
// ---------------------------------------------------------------------------

/**
 * Publish the valid URLs of an APPROVED submission to one or more mock
 * destinations. The backend re-validates approval and de-duplicates.
 * @param {string} submissionId
 * @param {string[]} destinations e.g. ['course-schedule','bookstore','mis-reporting']
 * @returns {Promise<{success:boolean, publishedCount:number, skippedDuplicateCount:number, destinations:string[], publishedAt:string}>}
 */
async function publishSubmission(submissionId, destinations) {
  return _request('POST', `/admin/submissions/${encodeURIComponent(submissionId)}/publish`, {
    body: { destinations },
  });
}

/**
 * Read the links published to a mock destination.
 * @param {string} destination one of 'course-schedule' | 'bookstore' | 'mis-reporting'
 * @returns {Promise<{count:number, destination:string, publications:object[]}>}
 */
async function getPublishedLinks(destination) {
  return _request('GET', '/published-links', { query: { destination } });
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

const API = {
  initConfig,
  isbnLookup,
  searchResources,
  createResource,
  addCourseResource,
  listCourseResources,
  deleteCourseResource,
  submitClass,
  listSubmissions,
  updateSubmission,
  deleteSubmission,
  publishSubmission,
  getPublishedLinks,
  ApiError,
  get baseUrl() {
    return BASE_URL;
  },
};
