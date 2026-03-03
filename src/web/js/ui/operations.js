// FormicOS v0.7.9 — Operations module
// Handles DataClaw export, compute queue, diagnostics, sessions,
// settings, API keys, API inspector, and webhook debug.

import { API_V1, ColonyStatus, MAX_LOG_ENTRIES, STATUS_BADGE_CLASS } from '../Constants.js';
import {
    colonyState,
    _lastQueueHash, set_lastQueueHash,
    _lastDiagnosticsHash, set_lastDiagnosticsHash,
    _lastApiKeysHash, set_lastApiKeysHash,
    _generatedKeyFull, set_generatedKeyFull,
    _lastColonyHash, set_lastColonyHash,
    _lastDecisionHash, set_lastDecisionHash,
    _lastTopoHash, set_lastTopoHash,
    _lastTopologySignature, set_lastTopologySignature,
    _pendingTopologyData, set_pendingTopologyData,
    _pendingTopologyRenderTimer, set_pendingTopologyRenderTimer,
    _topologyLiveMode, set_topologyLiveMode,
    _topoHistoryIdx, set_topoHistoryIdx
} from '../state.js';
import { hashString, escapeHtml, escapeAttr, truncateStr, formatTimestamp, showNotification, trapFocus, releaseFocusTrap } from '../utils.js';
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client.js';

// ── DataClaw Export ──────────────────────────────────────────
export function showDataClawModal() {
    if (!colonyState.colony_id) { showNotification('No colony selected', 'warning'); return; }
    const modal = document.getElementById('dataclaw-modal');
    if (modal) { modal.classList.remove('hidden'); trapFocus(modal); }
}

export function hideDataClawModal() {
    const modal = document.getElementById('dataclaw-modal');
    if (modal) { releaseFocusTrap(modal); modal.classList.add('hidden'); }
}

export function executeDataClawExport() {
    if (!colonyState.colony_id) { showNotification('No colony selected', 'warning'); return; }
    const format = document.getElementById('dataclaw-format').value;
    const scrub = document.getElementById('dataclaw-scrub').checked;
    const cid = encodeURIComponent(colonyState.colony_id);
    const url = API_V1 + '/colonies/' + cid + '/export?format=' + encodeURIComponent(format) + '&scrub=' + scrub;
    const a = document.createElement('a');
    a.href = url;
    a.download = 'dataclaw_' + colonyState.colony_id + '.' + (format === 'raw' ? 'zip' : 'jsonl');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    hideDataClawModal();
    showNotification('DataClaw export started for ' + format.toUpperCase(), 'info');
}

// ── Compute & Queue ──────────────────────────────────────────
export function loadQueueState() {
    apiGet(API_V1 + '/queue').then(function (data) {
        const hash = hashString(JSON.stringify(data));
        if (hash === _lastQueueHash) return;
        set_lastQueueHash(hash);
        renderQueueDashboard(data);
    }).catch(function (err) {
        const locksTbody = document.getElementById('compute-locks-tbody');
        if (locksTbody) locksTbody.innerHTML = '<tr><td colspan="3" class="empty-state">Failed to load: ' + escapeHtml(err.message) + '</td></tr>';
        const queueTbody = document.getElementById('queue-tbody');
        if (queueTbody) queueTbody.innerHTML = '<tr><td colspan="4" class="empty-state">Failed to load: ' + escapeHtml(err.message) + '</td></tr>';
    });
}

export function renderQueueDashboard(data) {
    const activeLocks = data.active_compute_locks || [];
    const queued = data.queued || [];
    const totalQueued = data.total_queued != null ? data.total_queued : queued.length;
    const activeWorkers = data.active_workers != null ? data.active_workers : activeLocks.length;

    const vramEl = document.getElementById('compute-vram-active');
    const depthEl = document.getElementById('compute-queue-depth');
    const workersEl = document.getElementById('compute-active-workers');
    const waitEl = document.getElementById('compute-avg-wait');

    let totalVram = 0;
    for (let i = 0; i < activeLocks.length; i++) {
        totalVram += (activeLocks[i].vram_est_gb || 0);
    }
    if (vramEl) vramEl.textContent = totalVram > 0 ? totalVram.toFixed(1) + ' GB' : '--';
    if (depthEl) depthEl.textContent = String(totalQueued);
    if (workersEl) workersEl.textContent = String(activeWorkers);

    if (waitEl) {
        const avgSec = data.estimated_wait_time_avg_seconds;
        if (avgSec != null && avgSec > 0) {
            if (avgSec >= 3600) waitEl.textContent = '~' + Math.round(avgSec / 3600) + 'h';
            else if (avgSec >= 60) waitEl.textContent = '~' + Math.round(avgSec / 60) + 'm';
            else waitEl.textContent = '~' + Math.round(avgSec) + 's';
        } else {
            waitEl.textContent = '--';
        }
    }

    // Stall detection banner
    const banner = document.getElementById('queue-stall-banner');
    if (banner) {
        if (activeWorkers === 0 && totalQueued > 0) {
            banner.classList.remove('hidden');
        } else {
            banner.classList.add('hidden');
        }
    }

    // Active compute locks table — DocumentFragment for memory hardening
    const locksTbody = document.getElementById('compute-locks-tbody');
    if (locksTbody) {
        if (!activeLocks.length) {
            locksTbody.innerHTML = '<tr><td colspan="3" class="empty-state">No active compute locks.</td></tr>';
        } else {
            const locksFrag = document.createDocumentFragment();
            for (let j = 0; j < activeLocks.length; j++) {
                const lock = activeLocks[j];
                const tr = document.createElement('tr');
                const tdColony = document.createElement('td');
                tdColony.className = 'font-mono';
                tdColony.textContent = lock.colony_id || '--';
                tr.appendChild(tdColony);
                const tdClient = document.createElement('td');
                tdClient.textContent = lock.client_id || '--';
                tr.appendChild(tdClient);
                const tdVram = document.createElement('td');
                tdVram.textContent = lock.vram_est_gb != null ? lock.vram_est_gb.toFixed(1) + ' GB' : '--';
                tr.appendChild(tdVram);
                locksFrag.appendChild(tr);
            }
            locksTbody.textContent = '';
            locksTbody.appendChild(locksFrag);
        }
    }

    // Queued colonies table — DocumentFragment for memory hardening
    const queueTbody = document.getElementById('queue-tbody');
    if (queueTbody) {
        if (!queued.length) {
            queueTbody.innerHTML = '<tr><td colspan="4" class="empty-state">No colonies in queue.</td></tr>';
        } else {
            const queueFrag = document.createDocumentFragment();
            for (let k = 0; k < queued.length; k++) {
                const q = queued[k];
                const tr = document.createElement('tr');
                const tdColony = document.createElement('td');
                tdColony.className = 'font-mono';
                tdColony.textContent = q.colony_id || '--';
                tr.appendChild(tdColony);
                const tdClient = document.createElement('td');
                tdClient.textContent = q.client_id || '--';
                tr.appendChild(tdClient);
                const tdPriority = document.createElement('td');
                tdPriority.textContent = q.priority != null ? String(q.priority) : '--';
                tr.appendChild(tdPriority);
                const tdAction = document.createElement('td');
                const dropBtn = document.createElement('button');
                dropBtn.className = 'btn btn-danger btn-sm';
                dropBtn.textContent = 'Drop';
                dropBtn.setAttribute('onclick', "dropQueuedColony('" + escapeAttr(q.colony_id || '') + "')");
                tdAction.appendChild(dropBtn);
                tr.appendChild(tdAction);
                queueFrag.appendChild(tr);
            }
            queueTbody.textContent = '';
            queueTbody.appendChild(queueFrag);
        }
    }
}

export function dropQueuedColony(colonyId) {
    if (!colonyId) return;
    if (!confirm('Drop colony ' + colonyId + ' from the queue? This cannot be undone.')) return;
    apiDelete(API_V1 + '/queue/' + encodeURIComponent(colonyId)).then(function () {
        showNotification('Colony ' + colonyId + ' dropped from queue', 'info');
        set_lastQueueHash('');
        loadQueueState();
    }).catch(function (err) {
        showNotification('Drop failed: ' + err.message, 'error');
    });
}

export function loadSystemDiagnostics() {
    apiGet(API_V1 + '/admin/diagnostics').then(function (data) {
        const hash = hashString(JSON.stringify(data));
        if (hash === _lastDiagnosticsHash) return;
        set_lastDiagnosticsHash(hash);
        renderDiagnostics(data);
    }).catch(function (err) {
        const el = document.getElementById('diag-stack-traces');
        if (el) el.textContent = 'Failed to load: ' + (err.message || 'Unknown error');
    });
}

export function renderDiagnostics(data) {
    // Pane 1: Stack Traces — Memory hardening: slice to MAX_LOG_ENTRIES
    const stackEl = document.getElementById('diag-stack-traces');
    if (stackEl) {
        let exceptions = data.recent_exceptions_tail || [];
        exceptions = exceptions.slice(-MAX_LOG_ENTRIES);
        if (!exceptions.length) {
            stackEl.textContent = 'No exceptions recorded.';
        } else {
            let txt = '';
            for (let i = 0; i < exceptions.length; i++) {
                const ex = exceptions[i];
                txt += '── ' + (ex.timestamp || 'Unknown time') + ' [' + (ex.module || '?') + '] ──\n';
                txt += (ex.traceback || 'No traceback') + '\n\n';
            }
            stackEl.textContent = txt.trim();
        }
    }

    // Pane 2: DataClaw Diffs — Memory hardening: slice to MAX_LOG_ENTRIES
    const diffEl = document.getElementById('diag-dataclaw-diffs');
    if (diffEl) {
        let diffs = data.dataclaw_diff_tail || [];
        diffs = diffs.slice(-MAX_LOG_ENTRIES);
        if (!diffs.length) {
            diffEl.textContent = 'No failed diffs.';
        } else {
            let dTxt = '';
            for (let j = 0; j < diffs.length; j++) {
                const d = diffs[j];
                dTxt += '── Colony: ' + (d.colony_id || '?') + ' ──\n';
                dTxt += (d.failed_state_diff || 'No diff data') + '\n\n';
            }
            diffEl.textContent = dTxt.trim();
        }
    }

    // Pane 3: WebSocket Faults — Memory hardening: slice to MAX_LOG_ENTRIES
    const wsEl = document.getElementById('diag-ws-faults');
    if (wsEl) {
        let faults = data.websocket_faults || [];
        faults = faults.slice(-MAX_LOG_ENTRIES);
        if (!faults.length) {
            wsEl.textContent = 'No WS faults.';
        } else {
            let wTxt = '';
            for (let k = 0; k < faults.length; k++) {
                const f = faults[k];
                wTxt += 'Client: ' + (f.client_id || '?') + '  Code: ' + (f.error_code || '?') + '  ' + (f.message || '') + '\n';
            }
            wsEl.textContent = wTxt.trim();
        }
    }
}

// ── Operations Surface (Sessions + Settings folded in) ───────
export function loadOperations() {
    try { loadSessions(); }    catch (e) { console.error('ops-sessions:', e); }
    try { loadApiKeys(); }     catch (e) { console.error('ops-apikeys:', e); }
    try { loadQueueState(); }  catch (e) { console.error('ops-queue:', e); }
    try { loadSettings(); }    catch (e) { console.error('ops-settings:', e); }
    try { loadMetrics(); }     catch (e) { console.error('ops-metrics:', e); }
    try { loadSystemDiagnostics(); } catch (e) { console.error('ops-diagnostics:', e); }
}

export function loadMetrics() {
    apiGet(API_V1 + '/system/metrics').then(function (data) {
        const grid = document.getElementById('slo-metrics-grid');
        if (!grid) return;
        const keys = Object.keys(data || {});
        if (!keys.length) { grid.innerHTML = '<div class="empty-state">No metrics collected yet.</div>'; return; }
        let html = '';
        for (let i = 0; i < keys.length; i++) {
            const name = keys[i];
            const m = data[name] || {};
            html += '<div class="slo-metric-card">';
            html += '<div class="slo-metric-name">' + escapeHtml(name) + '</div>';
            html += '<div class="slo-metric-values">';
            html += '<span>p50: ' + (m.p50 != null ? Math.round(m.p50) + 'ms' : '--') + '</span>';
            html += '<span>p95: ' + (m.p95 != null ? Math.round(m.p95) + 'ms' : '--') + '</span>';
            html += '<span>p99: ' + (m.p99 != null ? Math.round(m.p99) + 'ms' : '--') + '</span>';
            html += '<span class="text-muted">n=' + (m.count || 0) + '</span>';
            html += '</div></div>';
        }
        grid.innerHTML = html;
    }).catch(function () {});
}

// -- Operations: Sessions
export function loadSessions() {
    try {
        apiGet(API_V1 + '/sessions').then(function (data) {
            const sessions = data.sessions || data || [];
            renderSessionTable(sessions);
        }).catch(function (err) {
            const tbody = document.getElementById('sessions-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Failed to load: ' + escapeHtml(err.message) + '</td></tr>';
        });
    } catch (err) {
        console.error('Sessions load error:', err);
    }
}

export function renderSessionTable(sessions) {
    const tbody = document.getElementById('sessions-tbody');
    if (!tbody) return;

    if (!sessions || sessions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No sessions found.</td></tr>';
        return;
    }

    // DocumentFragment for memory hardening
    const frag = document.createDocumentFragment();
    for (let i = 0; i < sessions.length; i++) {
        const s = sessions[i];
        const sessionId = s.session_id || s.id || '--';
        const task = s.task || '--';
        const status = s.status || 'unknown';
        const created = s.created || s.created_at || s.timestamp || '--';
        const statusUpper = String(status).toUpperCase();
        const badgeClass = STATUS_BADGE_CLASS[statusUpper] || 'badge-neutral';

        const tr = document.createElement('tr');

        const tdId = document.createElement('td');
        tdId.className = 'font-mono font-sm';
        tdId.textContent = truncateStr(sessionId, 24);
        tr.appendChild(tdId);

        const tdTask = document.createElement('td');
        tdTask.className = 'truncate';
        tdTask.style.maxWidth = '250px';
        tdTask.textContent = truncateStr(task, 80);
        tr.appendChild(tdTask);

        const tdStatus = document.createElement('td');
        const badge = document.createElement('span');
        badge.className = 'badge ' + badgeClass;
        badge.textContent = statusUpper;
        tdStatus.appendChild(badge);
        tr.appendChild(tdStatus);

        const tdCreated = document.createElement('td');
        tdCreated.className = 'font-sm';
        tdCreated.textContent = formatTimestamp(created);
        tr.appendChild(tdCreated);

        const tdActions = document.createElement('td');
        const loadBtn = document.createElement('button');
        loadBtn.className = 'btn btn-secondary';
        loadBtn.textContent = 'Load';
        loadBtn.setAttribute('onclick', "resumeSession('" + escapeAttr(sessionId) + "')");
        tdActions.appendChild(loadBtn);
        tdActions.appendChild(document.createTextNode(' '));
        const delBtn = document.createElement('button');
        delBtn.className = 'btn btn-danger';
        delBtn.textContent = 'Delete';
        delBtn.setAttribute('onclick', "deleteSession('" + escapeAttr(sessionId) + "')");
        tdActions.appendChild(delBtn);
        tr.appendChild(tdActions);

        frag.appendChild(tr);
    }
    tbody.textContent = '';
    tbody.appendChild(frag);
}

export function resumeSession(sessionId) {
    apiPost(API_V1 + '/sessions/' + encodeURIComponent(sessionId) + '/recover', {}).then(function (data) {
        showNotification('Session resumed: ' + sessionId, 'success');
        const colonyId = data.colony_id || sessionId;
        colonyState.colony_id = colonyId;
        set_lastColonyHash('');
        set_lastDecisionHash('');
        set_lastTopoHash('');
        set_lastTopologySignature('');
        set_pendingTopologyData(null);
        if (_pendingTopologyRenderTimer) { clearTimeout(_pendingTopologyRenderTimer); set_pendingTopologyRenderTimer(null); }
        set_topologyLiveMode(true);
        set_topoHistoryIdx(-1);
        // Navigate to colony workspace
        window.location.hash = '#colony/' + encodeURIComponent(colonyId);
    }).catch(function (err) {
        showNotification('Resume failed: ' + err.message, 'error');
    });
}

export function deleteSession(sessionId) {
    if (!confirm('Delete session "' + truncateStr(sessionId, 30) + '"?')) return;

    apiDelete(API_V1 + '/sessions/' + encodeURIComponent(sessionId)).then(function () {
        showNotification('Session deleted', 'success');
        loadSessions();
    }).catch(function (err) {
        showNotification('Delete failed: ' + err.message, 'error');
    });
}

// -- Operations: Settings
export function loadSettings() {
    try {
        // System stats are fetched by the polling loop

        apiGet(API_V1 + '/system').then(function (data) {
            const configContainer = document.getElementById('settings-config');
            if (!configContainer) return;

            // Show all non-gpu fields as config
            const config = data.config || data;
            const keys = Object.keys(config);
            if (keys.length === 0) {
                configContainer.innerHTML = '<div class="empty-state">No configuration data available.</div>';
                return;
            }

            let html = '';
            for (let i = 0; i < keys.length; i++) {
                const key = keys[i];
                if (key === 'gpu') continue; // Shown separately
                const val = config[key];
                const displayVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
                html += '<div class="config-row">';
                html += '<span class="config-key">' + escapeHtml(key) + '</span>';
                html += '<span class="config-val">' + escapeHtml(truncateStr(displayVal, 100)) + '</span>';
                html += '</div>';
            }

            configContainer.innerHTML = html || '<div class="empty-state">Configuration loaded from formicos.yaml</div>';
        }).catch(function () {});
    } catch (err) {
        console.error('Settings load error:', err);
    }
}

// ── API Key Management ───────────────────────────────────────

export function loadApiKeys() {
    apiGet(API_V1 + '/auth/keys').then(function (data) {
        const keys = Array.isArray(data) ? data : (data && data.keys ? data.keys : []);
        const hash = hashString(JSON.stringify(keys));
        if (hash === _lastApiKeysHash) return;
        set_lastApiKeysHash(hash);
        renderApiKeysTable(keys);
    }).catch(function (err) {
        const tbody = document.getElementById('apikeys-tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Failed to load: ' + escapeHtml(err.message) + '</td></tr>';
    });
}

export function renderApiKeysTable(keys) {
    const tbody = document.getElementById('apikeys-tbody');
    if (!tbody) return;

    if (!keys || keys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No API keys generated yet.</td></tr>';
        return;
    }

    // DocumentFragment for memory hardening
    const frag = document.createDocumentFragment();
    for (let i = 0; i < keys.length; i++) {
        const k = keys[i];
        const keyId = k.id || '';
        const name = k.name || 'Unnamed';
        const prefix = k.prefix || 'sk-...';
        const created = k.created_at || k.created || '--';
        let tokens = (k.total_tokens_used != null ? k.total_tokens_used : (k.total_tokens != null ? k.total_tokens : 0));
        tokens = Number(tokens).toLocaleString();

        const tr = document.createElement('tr');

        const tdName = document.createElement('td');
        tdName.textContent = name;
        tr.appendChild(tdName);

        const tdPrefix = document.createElement('td');
        tdPrefix.className = 'font-mono font-sm';
        tdPrefix.textContent = prefix;
        tr.appendChild(tdPrefix);

        const tdCreated = document.createElement('td');
        tdCreated.className = 'font-sm';
        tdCreated.textContent = formatTimestamp(created);
        tr.appendChild(tdCreated);

        const tdTokens = document.createElement('td');
        tdTokens.className = 'font-mono';
        tdTokens.textContent = tokens;
        tr.appendChild(tdTokens);

        const tdActions = document.createElement('td');
        const revokeBtn = document.createElement('button');
        revokeBtn.className = 'btn btn-danger btn-sm';
        revokeBtn.textContent = 'Revoke';
        revokeBtn.setAttribute('onclick', "revokeApiKey('" + escapeAttr(keyId) + "', '" + escapeAttr(name) + "')");
        tdActions.appendChild(revokeBtn);
        tr.appendChild(tdActions);

        frag.appendChild(tr);
    }
    tbody.textContent = '';
    tbody.appendChild(frag);
}

export function showGenerateApiKeyModal() {
    set_generatedKeyFull(null);

    // Reset to form phase
    const formPhase = document.getElementById('apikey-form-phase');
    const revealPhase = document.getElementById('apikey-reveal-phase');
    const nameInput = document.getElementById('apikey-name-input');
    const submitBtn = document.getElementById('apikey-submit-btn');
    const doneBtn = document.getElementById('apikey-done-btn');
    const cancelBtn = document.getElementById('apikey-cancel-btn');

    if (formPhase) formPhase.classList.remove('hidden');
    if (revealPhase) revealPhase.classList.add('hidden');
    if (nameInput) nameInput.value = '';
    if (submitBtn) { submitBtn.style.display = ''; submitBtn.disabled = false; submitBtn.textContent = 'Generate'; }
    if (doneBtn) doneBtn.classList.add('hidden');
    if (cancelBtn) cancelBtn.style.display = '';

    const modal = document.getElementById('generate-apikey-modal');
    if (modal) {
        modal.classList.remove('hidden');
        trapFocus(modal);
    }
    if (nameInput) nameInput.focus();
}

export function hideGenerateApiKeyModal() {
    set_generatedKeyFull(null);
    const modal = document.getElementById('generate-apikey-modal');
    if (modal) {
        releaseFocusTrap(modal);
        modal.classList.add('hidden');
    }
}

export function submitGenerateApiKey() {
    const nameInput = document.getElementById('apikey-name-input');
    const name = nameInput ? nameInput.value.trim() : '';
    if (!name) {
        showNotification('Key name is required', 'warning');
        if (nameInput) nameInput.focus();
        return;
    }

    const submitBtn = document.getElementById('apikey-submit-btn');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Generating...'; }

    apiPost(API_V1 + '/auth/keys', { name: name }).then(function (data) {
        set_generatedKeyFull(data.full_key || data.key || '');

        // Switch to reveal phase
        const formPhase = document.getElementById('apikey-form-phase');
        const revealPhase = document.getElementById('apikey-reveal-phase');
        const secretDisplay = document.getElementById('apikey-secret-display');
        const doneBtn = document.getElementById('apikey-done-btn');
        const cancelBtn = document.getElementById('apikey-cancel-btn');
        const copyBtn = document.getElementById('apikey-copy-btn');

        if (formPhase) formPhase.classList.add('hidden');
        if (revealPhase) revealPhase.classList.remove('hidden');
        if (secretDisplay) secretDisplay.textContent = _generatedKeyFull;
        if (submitBtn) submitBtn.style.display = 'none';
        if (doneBtn) doneBtn.classList.remove('hidden');
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (copyBtn) copyBtn.textContent = 'Copy';

        // Refresh the keys table in background
        set_lastApiKeysHash('');
        loadApiKeys();

        showNotification('API key generated successfully', 'success');
    }).catch(function (err) {
        showNotification('Failed to generate key: ' + err.message, 'error');
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Generate'; }
    });
}

export function copyApiKeyToClipboard() {
    if (!_generatedKeyFull) return;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(_generatedKeyFull).then(function () {
            showNotification('API key copied to clipboard', 'success');
            const copyBtn = document.getElementById('apikey-copy-btn');
            if (copyBtn) copyBtn.textContent = 'Copied!';
        }).catch(function () {
            showNotification('Failed to copy -- please select and copy manually', 'warning');
        });
    } else {
        // Fallback: select the text for manual copy
        const secretDisplay = document.getElementById('apikey-secret-display');
        if (secretDisplay) {
            const range = document.createRange();
            range.selectNodeContents(secretDisplay);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }
        showNotification('Press Ctrl+C to copy the selected key', 'info');
    }
}

export function revokeApiKey(keyId, keyName) {
    if (!confirm('Revoke API key "' + keyName + '"?\n\nThis action is permanent. Any external agents using this key will immediately lose access.')) return;

    apiDelete(API_V1 + '/auth/keys/' + encodeURIComponent(keyId)).then(function () {
        showNotification('API key "' + keyName + '" revoked', 'success');
        set_lastApiKeysHash('');
        loadApiKeys();
    }).catch(function (err) {
        showNotification('Revoke failed: ' + err.message, 'error');
    });
}

// ── API Inspector ────────────────────────────────────────────
export function sendApiRequest() {
    const method = document.getElementById('api-method').value;
    const endpoint = document.getElementById('api-endpoint').value.trim();
    const bodyText = document.getElementById('api-request-body').value.trim();
    const responseEl = document.getElementById('api-response');
    if (!endpoint) { showNotification('Enter an endpoint', 'warning'); return; }
    const opts = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (method !== 'GET' && method !== 'DELETE' && bodyText) {
        try { JSON.parse(bodyText); opts.body = bodyText; }
        catch (e) { responseEl.textContent = 'Invalid JSON body: ' + e.message; return; }
    }
    responseEl.textContent = 'Loading...';
    fetch(endpoint, opts)
        .then(function (r) { return r.text().then(function (t) { return { status: r.status, statusText: r.statusText, body: t }; }); })
        .then(function (res) {
            const header = res.status + ' ' + res.statusText + '\n\n';
            try { responseEl.textContent = header + JSON.stringify(JSON.parse(res.body), null, 2); }
            catch (e) { responseEl.textContent = header + res.body; }
        })
        .catch(function (err) { responseEl.textContent = 'ERROR: ' + err.message; });
}

// ── Webhook Debug Modal ──────────────────────────────────────
export function showWebhookDebugModal() {
    const modal = document.getElementById('webhook-debug-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    trapFocus(modal);
    loadWebhookLogs();
}

export function hideWebhookDebugModal() {
    const modal = document.getElementById('webhook-debug-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    releaseFocusTrap(modal);
}

export function loadWebhookLogs() {
    const tbody = document.getElementById('webhook-logs-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Loading...</td></tr>';

    apiGet(API_V1 + '/webhooks/logs').then(function (data) {
        const logs = Array.isArray(data) ? data : (data && data.logs ? data.logs : []);
        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No webhook deliveries recorded.</td></tr>';
            return;
        }
        let html = '';
        for (let i = 0; i < logs.length; i++) {
            const log = logs[i];
            let ts = log.timestamp || log.created_at || '--';
            if (ts !== '--') {
                try { ts = new Date(ts).toLocaleString(); } catch (e) { /* keep raw */ }
            }
            const url = log.url || log.target_url || '--';
            const status = log.status_code || log.http_status || log.status || '--';
            const colonyId = log.colony_id || '--';
            let statusClass = 'wh-status-unknown';
            const statusNum = parseInt(status, 10);
            if (statusNum >= 200 && statusNum < 300) statusClass = 'wh-status-ok';
            else if (statusNum >= 400 || status === 'timeout' || status === 'error') statusClass = 'wh-status-error';

            const rowId = 'wh-payload-' + i;
            const payload = log.payload || log.body || log.response_body || null;

            html += '<tr>';
            html += '<td class="font-mono font-sm">' + escapeHtml(String(ts)) + '</td>';
            html += '<td class="font-mono font-sm truncate" style="max-width:200px" title="' + escapeHtml(String(url)) + '">' + escapeHtml(String(url)) + '</td>';
            html += '<td><span class="wh-status ' + statusClass + '">' + escapeHtml(String(status)) + '</span></td>';
            html += '<td class="font-mono font-sm">' + escapeHtml(String(colonyId)) + '</td>';
            html += '<td>';
            if (payload) {
                html += '<button class="btn btn-secondary btn-xs" onclick="toggleWebhookPayload(\'' + rowId + '\')">View Payload</button>';
            }
            html += '</td>';
            html += '</tr>';
            if (payload) {
                let payloadStr;
                try { payloadStr = typeof payload === 'string' ? JSON.stringify(JSON.parse(payload), null, 2) : JSON.stringify(payload, null, 2); }
                catch (e) { payloadStr = String(payload); }
                html += '<tr id="' + rowId + '" class="wh-payload-row hidden">';
                html += '<td colspan="5"><pre class="code-block wh-payload-pre">' + escapeHtml(payloadStr) + '</pre></td>';
                html += '</tr>';
            }
        }
        tbody.innerHTML = html;
    }).catch(function (err) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Failed to load: ' + escapeHtml(err.message) + '</td></tr>';
    });
}

export function toggleWebhookPayload(rowId) {
    const row = document.getElementById(rowId);
    if (row) row.classList.toggle('hidden');
}
