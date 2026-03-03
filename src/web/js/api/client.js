// FormicOS v0.7.9 — API client with timeout and RFC 7807 error handling

import { API_V1 } from '../Constants.js';

/** Default request timeout in milliseconds. */
const API_TIMEOUT_MS = 30000;

/**
 * Handle an API response — parse JSON and throw on non-OK status.
 * Supports RFC 7807 ProblemDetail responses with suggested_fix.
 * @param {Response} resp - Fetch Response object.
 * @returns {Promise<any>}
 */
function _apiHandleResponse(resp) {
    if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (body) {
            // RFC 7807 ProblemDetail support
            let msg = 'HTTP ' + resp.status;
            if (body.detail) msg = body.detail;
            if (body.suggested_fix) msg += ' — Fix: ' + body.suggested_fix;
            throw new Error(msg);
        });
    }
    return resp.json();
}

/**
 * Internal fetch wrapper with AbortController timeout.
 * @param {string} path - URL path to fetch.
 * @param {object} [opts] - Fetch options.
 * @returns {Promise<any>}
 */
function _apiFetch(path, opts) {
    const controller = new AbortController();
    const timeoutId = setTimeout(function () { controller.abort(); }, API_TIMEOUT_MS);
    opts = opts || {};
    opts.signal = controller.signal;
    return fetch(path, opts).then(function (resp) {
        clearTimeout(timeoutId);
        return _apiHandleResponse(resp);
    }).catch(function (err) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') throw new Error('Request timeout (' + (API_TIMEOUT_MS / 1000) + 's)');
        throw err;
    });
}

/**
 * Perform a GET request.
 * @param {string} path
 * @returns {Promise<any>}
 */
export function apiGet(path) {
    return _apiFetch(path);
}

/**
 * Perform a POST request with optional JSON body.
 * @param {string} path
 * @param {object} [body]
 * @returns {Promise<any>}
 */
export function apiPost(path, body) {
    return _apiFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined
    });
}

/**
 * Perform a PUT request with optional JSON body.
 * @param {string} path
 * @param {object} [body]
 * @returns {Promise<any>}
 */
export function apiPut(path, body) {
    return _apiFetch(path, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined
    });
}

/**
 * Perform a DELETE request.
 * @param {string} path
 * @returns {Promise<any>}
 */
export function apiDelete(path) {
    return _apiFetch(path, { method: 'DELETE' });
}
