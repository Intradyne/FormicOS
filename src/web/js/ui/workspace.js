// FormicOS v0.7.9 — Workspace browser module
// Handles file browsing, viewing, uploading, and archive downloads for colony workspaces.

import { API_V1 } from '../Constants.js';
import {
    colonyState,
    workspaceCurrentPath, setWorkspaceCurrentPath,
    lastResultsColonyId,
    workspaceArchiveState
} from '../state.js';
import { escapeHtml, escapeAttr, showNotification, trapFocus, releaseFocusTrap } from '../utils.js';
import { apiGet, apiPost } from '../api/client.js';

// ── Archive filter debounce timer ────────────────────────────
let _archiveFilterTimer = null;

// ── Workspace Browser ────────────────────────────────────────
let _lastWorkspaceHash = '';

/**
 * Reset workspace module state when switching colonies.
 * Clears the cached hash so the next refreshWorkspace() always rebuilds the DOM,
 * and resets the browsing path back to the workspace root.
 */
export function resetWorkspaceState() {
    _lastWorkspaceHash = '';
    setWorkspaceCurrentPath('');
}

export function refreshWorkspace() {
    const colonyId = colonyState.colony_id;
    if (!colonyId) {
        const el = document.getElementById('workspace-file-list');
        if (el) el.innerHTML = '<div class="empty-state">No colony active</div>';
        _lastWorkspaceHash = '';
        return;
    }
    let url = API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/workspace/files';
    if (workspaceCurrentPath) url += '?path=' + encodeURIComponent(workspaceCurrentPath);
    apiGet(url).then(function (files) {
        const hash = JSON.stringify(files);
        if (hash === _lastWorkspaceHash) return;  // No change — skip DOM rebuild
        _lastWorkspaceHash = hash;
        renderWorkspaceFiles(files);
    }).catch(function () {
        const el = document.getElementById('workspace-file-list');
        if (el) el.innerHTML = '<div class="empty-state">Failed to load workspace</div>';
    });
}

export function renderWorkspaceFiles(files) {
    const container = document.getElementById('workspace-file-list');
    const pathBar = document.getElementById('workspace-path-bar');
    if (!container) return;
    if (pathBar) pathBar.textContent = '/' + (workspaceCurrentPath || '');

    if (!files || files.length === 0) {
        container.innerHTML = '<div class="empty-state">Empty directory</div>';
        return;
    }

    let html = '';
    if (workspaceCurrentPath) {
        html += '<div class="workspace-file-row workspace-dir" onclick="navigateWorkspace(\'\')">';
        html += '<span class="file-icon">&#x2190;</span> <span class="file-name">..</span>';
        html += '</div>';
    }
    for (let i = 0; i < files.length; i++) {
        const f = files[i];
        if (f.is_dir) {
            html += '<div class="workspace-file-row workspace-dir" onclick="navigateWorkspace(\'' + escapeAttr(f.path) + '\')">';
            html += '<span class="file-icon">&#x1F4C1;</span> <span class="file-name">' + escapeHtml(f.name) + '</span>';
            html += '</div>';
        } else {
            const sizeStr = f.size > 1024 ? (f.size / 1024).toFixed(1) + ' KB' : f.size + ' B';
            html += '<div class="workspace-file-row" onclick="viewWorkspaceFile(\'' + escapeAttr(f.path) + '\')">';
            html += '<span class="file-icon">&#x1F4C4;</span> <span class="file-name">' + escapeHtml(f.name) + '</span>';
            html += '<span class="file-size">' + sizeStr + '</span>';
            html += '</div>';
        }
    }
    container.innerHTML = html;
}

export function navigateWorkspace(path) {
    setWorkspaceCurrentPath(path);
    refreshWorkspace();
}

/**
 * Unified viewWorkspaceFile — works from both the workspace browser (single arg)
 * and the results modal (two args: colonyId, path).
 */
export function viewWorkspaceFile(colonyIdOrPath, maybePath) {
    let colonyId, path;
    if (maybePath !== undefined) {
        // Called with (colonyId, path) from results modal
        colonyId = colonyIdOrPath;
        path = maybePath;
    } else {
        // Called with (path) from workspace browser
        colonyId = colonyState.colony_id;
        path = colonyIdOrPath;
    }
    if (!colonyId) return;

    const url = API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/workspace/files/' + encodeURIComponent(path);
    apiGet(url).then(function (data) {
        // If called from results modal, render inside results body
        if (maybePath !== undefined) {
            const body = document.getElementById('results-body');
            if (!body) return;
            const html = '<div style="margin-bottom:8px;">' +
                '<a href="#" onclick="fetchAndShowResults(\'' + escapeAttr(colonyId) + '\'); return false;">&larr; Back to results</a>' +
                '</div>' +
                '<h4>' + escapeHtml(path) + '</h4>' +
                '<pre class="file-preview"><code>' + escapeHtml(data.content || '') + '</code></pre>';
            body.innerHTML = html;
        } else {
            // Workspace browser view
            document.getElementById('workspace-viewer-name').textContent = path;
            document.getElementById('workspace-viewer-content').textContent = data.content || '';
            document.getElementById('workspace-file-viewer').classList.remove('hidden');
            document.getElementById('workspace-file-list').classList.add('hidden');
        }
    }).catch(function (err) {
        showNotification('Failed to read file: ' + (err.message || 'unknown'), 'error');
    });
}

export function closeWorkspaceViewer() {
    document.getElementById('workspace-file-viewer').classList.add('hidden');
    document.getElementById('workspace-file-list').classList.remove('hidden');
}

export function uploadWorkspaceFile() {
    const input = document.getElementById('workspace-upload');
    if (!input || !input.files || !input.files[0]) return;
    if (!colonyState.colony_id) {
        showNotification('No colony active', 'warning');
        return;
    }

    const file = input.files[0];
    const colonyId = colonyState.colony_id;
    const reader = new FileReader();
    reader.onload = function () {
        fetch(API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/workspace/upload', {
            method: 'POST',
            headers: { 'X-Filename': file.name },
            body: reader.result
        }).then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        }).then(function () {
            showNotification('File uploaded: ' + file.name, 'success');
            refreshWorkspace();
        }).catch(function (err) {
            showNotification('Upload failed: ' + err.message, 'error');
        });
    };
    reader.readAsArrayBuffer(file);
    input.value = '';
}

export function downloadWorkspaceArchive(colonyId) {
    openWorkspaceArchiveModal(colonyId);
}

export function openWorkspaceArchiveModal(colonyId) {
    const cid = colonyId || colonyState.colony_id || lastResultsColonyId;
    if (!cid) {
        showNotification('No colony selected', 'warning');
        return;
    }

    workspaceArchiveState.colonyId = cid;
    workspaceArchiveState.files = [];
    workspaceArchiveState.selected = {};
    workspaceArchiveState.filter = '';

    const filterInput = document.getElementById('workspace-archive-filter');
    if (filterInput) filterInput.value = '';

    const modal = document.getElementById('workspace-archive-modal');
    if (modal) { modal.classList.remove('hidden'); trapFocus(modal); }

    const listEl = document.getElementById('workspace-archive-list');
    if (listEl) listEl.innerHTML = '<div class="empty-state">Loading files...</div>';

    apiGet(API_V1 + '/colonies/' + encodeURIComponent(cid) + '/results/files').then(function (files) {
        workspaceArchiveState.files = Array.isArray(files) ? files.slice().sort() : [];
        workspaceArchiveState.selected = {};
        for (let i = 0; i < workspaceArchiveState.files.length; i++) {
            workspaceArchiveState.selected[workspaceArchiveState.files[i]] = true;
        }
        renderWorkspaceArchiveFiles();
    }).catch(function (err) {
        showNotification('Failed to load workspace files: ' + err.message, 'error');
        const el = document.getElementById('workspace-archive-list');
        if (el) el.innerHTML = '<div class="empty-state">Failed to load files</div>';
    });
}

export function hideWorkspaceArchiveModal() {
    const modal = document.getElementById('workspace-archive-modal');
    releaseFocusTrap(modal);
    if (modal) modal.classList.add('hidden');
}

export function filterWorkspaceArchiveFiles(value) {
    workspaceArchiveState.filter = String(value || '').trim().toLowerCase();
    if (_archiveFilterTimer) clearTimeout(_archiveFilterTimer);
    _archiveFilterTimer = setTimeout(function () {
        renderWorkspaceArchiveFiles();
    }, 200);
}

export function getVisibleWorkspaceArchiveFiles() {
    const files = workspaceArchiveState.files || [];
    const filter = workspaceArchiveState.filter || '';
    if (!filter) return files.slice();
    const visible = [];
    for (let i = 0; i < files.length; i++) {
        if (files[i].toLowerCase().indexOf(filter) !== -1) visible.push(files[i]);
    }
    return visible;
}

export function renderWorkspaceArchiveFiles(files) {
    const listEl = document.getElementById('workspace-archive-list');
    const summaryEl = document.getElementById('workspace-archive-summary');
    if (!listEl) return;
    const priorScroll = listEl.scrollTop;

    const allFiles = workspaceArchiveState.files || [];
    const visible = getVisibleWorkspaceArchiveFiles();
    let selectedCount = 0;
    for (let i = 0; i < allFiles.length; i++) {
        if (workspaceArchiveState.selected[allFiles[i]]) selectedCount++;
    }
    if (summaryEl) {
        summaryEl.textContent = selectedCount + ' of ' + allFiles.length + ' files selected';
    }

    if (allFiles.length === 0) {
        listEl.innerHTML = '<div class="empty-state">No files available for this colony.</div>';
        return;
    }
    if (visible.length === 0) {
        listEl.innerHTML = '<div class="empty-state">No files match this filter.</div>';
        return;
    }

    let html = '';
    for (let j = 0; j < visible.length; j++) {
        const path = visible[j];
        const checked = workspaceArchiveState.selected[path] ? ' checked' : '';
        html += '<label class="archive-file-item">';
        html += '<input type="checkbox"' + checked + ' onchange="toggleWorkspaceArchiveFileSelection(\'' + escapeAttr(path) + '\', this.checked)">';
        html += '<span class="archive-file-path">' + escapeHtml(path) + '</span>';
        html += '</label>';
    }
    listEl.innerHTML = html;
    listEl.scrollTop = priorScroll;
}

export function toggleWorkspaceArchiveFileSelection(path, enabled) {
    workspaceArchiveState.selected[path] = !!enabled;
    renderWorkspaceArchiveFiles();
}

export function setWorkspaceArchiveSelectionVisible(enabled) {
    const visible = getVisibleWorkspaceArchiveFiles();
    for (let i = 0; i < visible.length; i++) {
        workspaceArchiveState.selected[visible[i]] = !!enabled;
    }
    renderWorkspaceArchiveFiles();
}

export function downloadSelectedWorkspaceArchive() {
    const cid = workspaceArchiveState.colonyId || colonyState.colony_id || lastResultsColonyId;
    if (!cid) {
        showNotification('No colony selected', 'warning');
        return;
    }

    const files = workspaceArchiveState.files || [];
    const selectedPaths = [];
    for (let i = 0; i < files.length; i++) {
        if (workspaceArchiveState.selected[files[i]]) selectedPaths.push(files[i]);
    }
    if (selectedPaths.length === 0) {
        showNotification('Select at least one file for ZIP download', 'warning');
        return;
    }

    let url = API_V1 + '/colonies/' + encodeURIComponent(cid) + '/workspace/archive';
    if (selectedPaths.length < files.length) {
        const params = [];
        for (let j = 0; j < selectedPaths.length; j++) {
            params.push('paths=' + encodeURIComponent(selectedPaths[j]));
        }
        if (params.length > 0) {
            url += '?' + params.join('&');
        }
    }

    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    hideWorkspaceArchiveModal();
    showNotification('Downloading ZIP (' + selectedPaths.length + ' files)', 'success');
}

export function openWorkspaceFolder(colonyId) {
    const cid = colonyId || colonyState.colony_id || lastResultsColonyId;
    if (!cid) {
        showNotification('No colony selected', 'warning');
        return;
    }
    apiPost(API_V1 + '/colonies/' + encodeURIComponent(cid) + '/workspace/open', {}).then(function (data) {
        if (data && data.opened) {
            showNotification('Opened workspace: ' + (data.path || cid), 'success');
            return;
        }
        const reason = data && data.reason ? (' (' + data.reason + ')') : '';
        const hostHint = data && data.host_path_hint ? data.host_path_hint : '';
        const pathLabel = hostHint || (data && data.path) || cid;
        const prefix = hostHint ? 'Host path hint: ' : 'Path: ';
        showNotification('Open folder unavailable in this runtime' + reason + '. ' + prefix + pathLabel + '. Use Download ZIP if needed.', 'info');
    }).catch(function (err) {
        showNotification('Open folder failed: ' + err.message, 'error');
    });
}
