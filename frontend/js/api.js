/**
 * api.js — Centralised API layer
 * ─────────────────────────────────────────────────────────────
 * Every HTTP call to the Flask backend goes through this module.
 * No other file ever calls fetch() directly.
 *
 * Design rationale
 * ────────────────
 * • Single source of truth for the base URL — change it in one place
 *   for local dev, staging, and production (API Gateway).
 * • All responses are unwrapped here; callers receive plain JS objects
 *   or throw a typed ApiError they can handle consistently.
 * • When migrating to API Gateway + Lambda, only BASE_URL changes.
 *   No consumer code needs to be touched.
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/**
 * Base URL for all API calls.
 * In production behind API Gateway this becomes the invoke URL, e.g.
 *   https://<id>.execute-api.us-east-1.amazonaws.com/prod
 */
const BASE_URL = 'http://localhost:5001';

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

/**
 * Structured error thrown by every API helper so callers can distinguish
 * network failures from server-side validation errors.
 */
class ApiError extends Error {
  /**
   * @param {string} message   Human-readable description.
   * @param {number} status    HTTP status code (0 = network failure).
   * @param {object} [body]    Parsed response body, if available.
   */
  constructor(message, status = 0, body = null) {
    super(message);
    this.name   = 'ApiError';
    this.status = status;
    this.body   = body;
  }
}

// ---------------------------------------------------------------------------
// Internal fetch wrapper
// ---------------------------------------------------------------------------

/**
 * _request(method, path, body?)
 * Low-level fetch wrapper shared by all public helpers.
 * Parses JSON responses and converts non-2xx status codes into ApiError.
 *
 * @param {string}  method  HTTP method ('GET', 'POST', 'PUT', 'DELETE').
 * @param {string}  path    Path relative to BASE_URL, e.g. '/submit-survey'.
 * @param {object}  [body]  Request payload — serialised to JSON when present.
 * @returns {Promise<object>} Parsed JSON response body.
 * @throws  {ApiError}        On network failure or non-2xx response.
 */
async function _request(method, path, body = null) {
  const options = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };

  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, options);
  } catch (networkError) {
    throw new ApiError(
      'Unable to reach the server. Make sure the backend is running on port 5001.',
      0
    );
  }

  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message =
      (data && (data.error || data.message)) ||
      `Server returned ${response.status}`;
    throw new ApiError(message, response.status, data);
  }

  return data;
}

// ---------------------------------------------------------------------------
// Survey API
// ---------------------------------------------------------------------------

/**
 * Submit a completed OER survey.
 * @param {object} formData  Plain object matching the Submission model fields.
 * @returns {Promise<{success: boolean, submission: object}>}
 */
async function submitSurvey(formData) {
  return _request('POST', '/submit-survey', formData);
}

/**
 * Fetch all submissions (admin).
 * @param {object} [filters]  Optional { status, materialType } query params.
 * @returns {Promise<{count: number, submissions: object[]}>}
 */
async function getSubmissions(filters = {}) {
  const params = new URLSearchParams();
  if (filters.status)       params.set('status',       filters.status);
  if (filters.materialType) params.set('materialType', filters.materialType);
  const qs = params.toString() ? `?${params}` : '';
  return _request('GET', `/submissions${qs}`);
}

/**
 * Fetch summary counts for admin stat cards.
 * @returns {Promise<{total, pending, underReview, approved, needsCorrection, ltc, ztc}>}
 */
async function getSubmissionStats() {
  return _request('GET', '/submissions/stats');
}

/**
 * Fetch a single submission by id.
 * @param {string} id
 * @returns {Promise<object>} Submission object.
 */
async function getSubmission(id) {
  return _request('GET', `/submission/${encodeURIComponent(id)}`);
}

/**
 * Save an admin review (status + notes) for a submission.
 * @param {string} id
 * @param {object} updates  { status?: string, adminNotes?: string }
 * @returns {Promise<{success: boolean, submission: object}>}
 */
async function updateSubmission(id, updates) {
  return _request('PUT', `/submission/${encodeURIComponent(id)}`, updates);
}

/**
 * Delete a single submission (admin).
 * @param {string} id
 * @returns {Promise<{success: boolean, deletedId: string}>}
 */
async function deleteSubmission(id) {
  return _request('DELETE', `/submission/${encodeURIComponent(id)}`);
}

/**
 * Delete all submissions (admin).
 * @returns {Promise<{success: boolean, deletedCount: number}>}
 */
async function deleteAllSubmissions() {
  return _request('DELETE', '/submissions');
}

// ---------------------------------------------------------------------------
// Chatbot / AI API
// ---------------------------------------------------------------------------

/**
 * Get course-based textbook and platform suggestions from the CSV dataset.
 * @param {string} query  Free-text course description, e.g. "Biology 10".
 * @returns {Promise<{type: string, data?: object, message?: string}>}
 */
async function getSuggestions(query) {
  return _request('POST', '/suggestions', { query });
}

/**
 * Send a freeform chat message to the AI (AWS Bedrock / Claude).
 * @param {string}   message  User's message text.
 * @param {object[]} history  Conversation history: [{ role, content }, …]
 * @returns {Promise<{reply: string}>}
 */
async function sendChatMessage(message, history = []) {
  return _request('POST', '/chat', { message, history });
}

/**
 * Perform a web search for textbook / resource information.
 * @param {string} query
 * @returns {Promise<{results: object[]}>}
 */
async function webSearch(query) {
  return _request('POST', '/search', { query });
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------
// Exposed as a plain object so index.html can load this as a plain <script>
// without requiring a bundler or ES module support in older browsers.

const API = {
  // Survey
  submitSurvey,
  getSubmissions,
  getSubmissionStats,
  getSubmission,
  updateSubmission,
  deleteSubmission,
  deleteAllSubmissions,
  // Chatbot / AI
  getSuggestions,
  sendChatMessage,
  webSearch,
  // Error class (so callers can do: catch(e) { if (e instanceof API.ApiError) }
  ApiError,
};
