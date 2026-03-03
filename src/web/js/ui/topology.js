// FormicOS v0.7.9 — Topology graph and decision log module
// Handles Cytoscape.js graph rendering, topology history navigation, and decision log display.

import { CASTE_COLORS, ColonyStatus, MAX_CYTOSCAPE_NODES, API_V1 } from '../Constants.js';
import {
    cy, setCy,
    cachedTopology, setCachedTopology,
    cachedTkg, setCachedTkg,
    currentGraphView, setCurrentGraphView,
    colonyState,
    currentTab,
    _lastTopoHash, set_lastTopoHash,
    _lastDecisionHash, set_lastDecisionHash,
    _lastTopologySignature, set_lastTopologySignature,
    _lastTopoHistoryFetchTs, set_lastTopoHistoryFetchTs,
    _graphInteractionLock, set_graphInteractionLock,
    _graphInteractionTimer, set_graphInteractionTimer,
    _pendingTopologyData, set_pendingTopologyData,
    _pendingTopologyRenderTimer, set_pendingTopologyRenderTimer,
    _lastTopologyRenderTs, set_lastTopologyRenderTs,
    _topologyRenderIntervalMs,
    _topologyLiveMode, set_topologyLiveMode,
    _topoHistoryIdx, set_topoHistoryIdx,
    _topoHistory, set_topoHistory
} from '../state.js';
import { hashString, escapeHtml, escapeAttr, formatTimestamp } from '../utils.js';
import { apiGet } from '../api/client.js';
import { normalizeStatus, getStatusColor } from './colony.js';

// ── Local module state ───────────────────────────────────────
let _lastDecisionCount = 0;

// ── Topology ─────────────────────────────────────────────────
export function fetchTopology() {
    if (!colonyState.colony_id) return;
    const colonyId = encodeURIComponent(colonyState.colony_id);
    const endpoint = currentGraphView === 'tkg'
        ? API_V1 + '/colonies/' + colonyId + '/tkg'
        : API_V1 + '/colonies/' + colonyId + '/topology';

    apiGet(endpoint).then(function (data) {
        const hash = hashString(JSON.stringify(data));
        if (hash === _lastTopoHash) return;
        set_lastTopoHash(hash);

        if (currentGraphView === 'tkg') {
            setCachedTkg(data);
            const transformed = transformTkgToCytoscape(data);
            if (_graphInteractionLock) { set_pendingTopologyData(transformed); return; }
            queueTopologyRender(transformed, false);
        } else {
            setCachedTopology(data);
            if (_graphInteractionLock) { set_pendingTopologyData(data); return; }
            queueTopologyRender(data, false);
        }

        // Refresh topology history occasionally in background.
        if (currentGraphView !== 'tkg' && Date.now() - _lastTopoHistoryFetchTs > 10000) {
            fetchTopoHistory();
        }
    }).catch(function () {});
}

export function transformTkgToCytoscape(tuples) {
    const arr = Array.isArray(tuples) ? tuples : (tuples.tuples || tuples.data || []);
    const nodeSet = {};
    const edges = [];
    for (let i = 0; i < arr.length; i++) {
        const t = arr[i];
        const s = t.subject || t[0] || '';
        const p = t.predicate || t[1] || '';
        const o = t.object || t.object_ || t[2] || '';
        if (s && !nodeSet[s]) nodeSet[s] = { id: s, label: s, type: 'entity' };
        if (o && !nodeSet[o]) nodeSet[o] = { id: o, label: o, type: 'entity' };
        if (s && o) edges.push({ source: s, target: o, weight: 1, label: p });
    }
    return { nodes: Object.values(nodeSet), edges: edges };
}

export function queueTopologyRender(data, force) {
    if (!cy) return;

    if (force) {
        if (_pendingTopologyRenderTimer) {
            clearTimeout(_pendingTopologyRenderTimer);
            set_pendingTopologyRenderTimer(null);
        }
        set_pendingTopologyData(null);
        set_lastTopologyRenderTs(Date.now());
        updateTopologyGraph(data);
        return;
    }

    const now = Date.now();
    const wait = _topologyRenderIntervalMs - (now - _lastTopologyRenderTs);
    if (wait <= 0) {
        set_lastTopologyRenderTs(now);
        updateTopologyGraph(data);
        return;
    }

    set_pendingTopologyData(data);
    if (_pendingTopologyRenderTimer) return;
    set_pendingTopologyRenderTimer(setTimeout(function () {
        set_pendingTopologyRenderTimer(null);
        if (_graphInteractionLock || !_pendingTopologyData) return;
        const pending = _pendingTopologyData;
        set_pendingTopologyData(null);
        set_lastTopologyRenderTs(Date.now());
        updateTopologyGraph(pending);
    }, wait + 10));
}

export function markGraphInteracting() {
    set_graphInteractionLock(true);
    if (_graphInteractionTimer) {
        clearTimeout(_graphInteractionTimer);
    }
    set_graphInteractionTimer(setTimeout(function () {
        set_graphInteractionLock(false);
        if (_pendingTopologyData) {
            const pending = _pendingTopologyData;
            set_pendingTopologyData(null);
            queueTopologyRender(pending, false);
        }
    }, 700));
}

export function buildTopologySignature(nodes, edges) {
    const nodeIds = [];
    for (let i = 0; i < nodes.length; i++) {
        const nid = nodes[i].id || nodes[i].agent_id || ('node-' + i);
        nodeIds.push(String(nid));
    }
    nodeIds.sort();

    const edgeKeys = [];
    for (let j = 0; j < edges.length; j++) {
        const e = edges[j] || {};
        edgeKeys.push(String(e.source || e.from || e.sender || '') + '->' + String(e.target || e.to || e.receiver || ''));
    }
    edgeKeys.sort();
    return nodeIds.join('|') + '||' + edgeKeys.join('|');
}

export function initCytoscape() {
    if (typeof cytoscape === 'undefined') {
        console.warn('Cytoscape.js not loaded');
        return;
    }

    setCy(cytoscape({
        container: document.getElementById('cy-container'),
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'background-color': 'data(color)',
                    'color': '#ffffff',
                    'text-outline-color': '#333333',
                    'text-outline-width': 1,
                    'font-size': 11,
                    'text-wrap': 'ellipsis',
                    'text-max-width': 140,
                    'min-zoomed-font-size': 8,
                    'text-valign': 'bottom',
                    'text-margin-y': 6,
                    'width': 'data(size)',
                    'height': 'data(size)',
                    'border-width': 2,
                    'border-color': '#444444'
                }
            },
            {
                selector: 'node:selected',
                style: {
                    'border-color': '#ffffff',
                    'border-width': 3
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 'data(weight)',
                    'line-color': '#555555',
                    'target-arrow-color': '#555555',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'opacity': 0.7
                }
            },
            {
                selector: 'edge:selected',
                style: {
                    'line-color': '#4CAF50',
                    'target-arrow-color': '#4CAF50',
                    'opacity': 1
                }
            }
        ],
        layout: {
            name: 'breadthfirst',
            animate: false,
            fit: true,
            padding: 30,
            spacingFactor: 1.2,
            directed: true
        },
        minZoom: 0.3,
        maxZoom: 3,
        wheelSensitivity: 0.3
    }));

    // Defer topology redraw while the operator is actively interacting
    // with the graph to avoid UI freezes/jank from relayout churn.
    const graphContainer = document.getElementById('cy-container');
    if (graphContainer) {
        graphContainer.addEventListener('pointerdown', markGraphInteracting);
        graphContainer.addEventListener('wheel', markGraphInteracting, { passive: true });
        graphContainer.addEventListener('touchstart', markGraphInteracting, { passive: true });
    }
}

export function clampNumber(value, min, max, fallback) {
    const n = Number(value);
    if (!isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
}

export function formatTopologyLabel(rawLabel, fallbackId) {
    let label = String(rawLabel || fallbackId || '')
        .replace(/^[\s"'`[\](){}]+|[\s"'`[\](){}]+$/g, '')
        .trim();
    if (!label) return 'agent';
    const shortMatch = label.match(/^([a-zA-Z]+)[_:-]([a-f0-9]{4,})$/i);
    if (shortMatch) return shortMatch[1] + '_' + shortMatch[2].slice(-4);
    if (label.length > 22) return label.slice(0, 19) + '...';
    return label;
}

export function updateTopologyGraph(data, skipLayoutCheck) {
    if (!cy) return;

    // Handle different data shapes
    const nodes = data.nodes || data.agents || [];
    const edges = data.edges || data.routes || data.links || [];
    const signature = buildTopologySignature(nodes, edges);

    if (_lastTopologySignature === signature && cy.nodes().length > 0) {
        cy.batch(function () {
            for (let ni = 0; ni < nodes.length; ni++) {
                const nn = nodes[ni];
                const nid = nn.id || nn.agent_id || ('node-' + ni);
                const ncaste = nn.caste || nn.type || 'coder';
                const ncolor = CASTE_COLORS[ncaste] || '#2196f3';
                const nodeEl = cy.getElementById(nid);
                if (!nodeEl || !nodeEl.length) continue;
                nodeEl.data('label', formatTopologyLabel(nn.label || nn.name || nid, nid));
                nodeEl.data('color', ncolor);
                nodeEl.data('size', clampNumber(nn.size, 22, 48, 30));
                nodeEl.data('caste', ncaste);
            }
            for (let ei = 0; ei < edges.length; ei++) {
                const ee = edges[ei] || {};
                const edgeId = ee.id || ('edge-' + ei);
                const edgeEl = cy.getElementById(edgeId);
                if (!edgeEl || !edgeEl.length) continue;
                edgeEl.data('weight', Math.max(1, Math.min(6, (ee.weight || ee.similarity || 1) * 3)));
            }
        });
        return;
    }

    set_lastTopologySignature(signature);
    const elements = [];

    for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const nodeId = n.id || n.agent_id || ('node-' + i);
        const caste = n.caste || n.type || 'coder';
        const nodeColor = CASTE_COLORS[caste] || '#2196f3';
        elements.push({
            group: 'nodes',
            data: {
                id: nodeId,
                label: formatTopologyLabel(n.label || n.name || nodeId, nodeId),
                color: nodeColor,
                size: clampNumber(n.size, 22, 48, 30),
                caste: caste
            }
        });
    }

    for (let j = 0; j < edges.length; j++) {
        const e = edges[j];
        const sourceId = e.source || e.from || e.sender;
        const targetId = e.target || e.to || e.receiver;
        if (!sourceId || !targetId) continue;
        elements.push({
            group: 'edges',
            data: {
                id: e.id || ('edge-' + j),
                source: sourceId,
                target: targetId,
                weight: Math.max(1, Math.min(6, (e.weight || e.similarity || 1) * 3))
            }
        });
    }

    cy.elements().remove();
    if (elements.length > 0) {
        cy.add(elements);

        // Memory hardening: cap maximum Cytoscape nodes
        if (cy.elements().length > MAX_CYTOSCAPE_NODES) {
            const excess = cy.elements().length - MAX_CYTOSCAPE_NODES;
            // Remove the oldest nodes (first added) to stay under the cap
            const toRemove = cy.nodes().slice(0, excess);
            toRemove.remove();
        }

        const layoutName = edges.length > 0 ? 'breadthfirst' : 'circle';
        cy.layout({
            name: layoutName,
            animate: false,
            fit: true,
            padding: 30,
            spacingFactor: 1.2,
            directed: true
        }).run();
    }
}

export function toggleGraphView(view) {
    setCurrentGraphView(view);
    set_lastTopoHash(''); // Force refresh
    set_lastTopologySignature('');
    set_pendingTopologyData(null);
    if (_pendingTopologyRenderTimer) { clearTimeout(_pendingTopologyRenderTimer); set_pendingTopologyRenderTimer(null); }

    // Restore from cache if available
    if (view === 'topology' && cachedTopology) {
        updateTopologyGraph(cachedTopology);
    } else if (view === 'tkg' && cachedTkg) {
        updateTopologyGraph(cachedTkg);
    }

    // Always fetch fresh data too
    fetchTopology();

    // Update button styling
    const buttons = document.querySelector('.panel-graph .panel-controls');
    if (buttons) {
        const btns = buttons.querySelectorAll('.btn-icon');
        for (let i = 0; i < btns.length; i++) {
            btns[i].style.color = '';
            btns[i].style.borderColor = '';
            btns[i].classList.remove('btn-icon-active');
        }
        let activeBtn = null;
        if (view === 'tkg') {
            activeBtn = buttons.querySelector('button[title="TKG view"]');
        } else {
            activeBtn = buttons.querySelector('button[title="Topology view"]');
        }
        if (activeBtn) {
            activeBtn.classList.add('btn-icon-active');
        }
    }
    updateTopoControls();
}

export function fitGraph() {
    if (cy) cy.fit(undefined, 30);
}

export function changeGraphLayout(layoutName) {
    if (!cy || cy.nodes().length === 0) return;
    cy.layout({ name: layoutName, animate: true, fit: true, padding: 30 }).run();
}

// ── Topology History Navigation ──────────────────────────────
export function fetchTopoHistory() {
    if (!colonyState.colony_id) return;
    set_lastTopoHistoryFetchTs(Date.now());
    const colonyId = encodeURIComponent(colonyState.colony_id);
    apiGet(API_V1 + '/colonies/' + colonyId + '/topology/history').then(function (data) {
        if (!Array.isArray(data)) return;
        set_topoHistory(data);
        renderTopoRoundProgress();
    }).catch(function () {});
}

export function renderTopoRoundProgress() {
    const container = document.getElementById('topo-round-progress');
    const summary = document.getElementById('topo-progress-summary');
    if (!container) return;
    const wasNearEnd = (container.scrollWidth - container.clientWidth - container.scrollLeft) < 40;

    const history = Array.isArray(_topoHistory) ? _topoHistory : [];
    const roundLookup = {};
    let maxHistoryRound = -1;
    for (let i = 0; i < history.length; i++) {
        const snap = history[i] || {};
        let round = parseInt(snap.round, 10);
        if (!isFinite(round) || round < 0) round = i;
        roundLookup[round] = snap;
        if (round > maxHistoryRound) maxHistoryRound = round;
    }

    const status = normalizeStatus(colonyState.status || ColonyStatus.IDLE);
    let currentRound = parseInt(colonyState.round, 10);
    if (!isFinite(currentRound) || currentRound < 0) currentRound = 0;
    let maxRounds = parseInt(colonyState.max_rounds, 10);
    if (!isFinite(maxRounds) || maxRounds < 1) maxRounds = history.length;
    const totalRounds = Math.max(maxRounds, maxHistoryRound + 1, currentRound + 1, 1);

    if (summary) {
        summary.textContent = 'Round ' + currentRound + ' / ' + Math.max(totalRounds - 1, 0) + ' • ' + status;
    }

    let html = '';
    for (let r = 0; r < totalRounds; r++) {
        const snapR = roundLookup[r] || null;
        let stateClass = 'pending';

        if (snapR) stateClass = 'done';
        if ((status === ColonyStatus.RUNNING || status === ColonyStatus.PAUSED) && r === currentRound) stateClass = 'active';
        if (status === ColonyStatus.FAILED && r === currentRound) stateClass = 'failed';
        if ((status === ColonyStatus.COMPLETED || status === ColonyStatus.FAILED) && r > currentRound) stateClass = 'future';

        const edgeCount = snapR && Array.isArray(snapR.edges) ? snapR.edges.length : 0;
        const orderCount = snapR && Array.isArray(snapR.execution_order) ? snapR.execution_order.length : 0;
        const density = snapR && snapR.density !== undefined ? Number(snapR.density) : null;
        let title = 'R' + r;
        if (snapR) {
            title += ' | edges: ' + edgeCount + ', order: ' + orderCount;
            if (density !== null && isFinite(density)) {
                title += ', density: ' + density.toFixed(3);
            }
        } else {
            title += ' | no topology snapshot';
        }

        html += '<div class="topo-round-chip topo-round-' + stateClass + '" title="' + escapeAttr(title) + '">';
        html += '<span class="topo-round-dot"></span>';
        html += '<span class="topo-round-chip-label">R' + r + '</span>';
        html += '</div>';
    }

    container.innerHTML = html;
    if (wasNearEnd) {
        container.scrollLeft = container.scrollWidth;
    }
}

export function updateTopoControls() {
    renderTopoRoundProgress();
}

export function updateTopoRoundLabel() {
    renderTopoRoundProgress();
}

export function topoGoLive() {
    set_topologyLiveMode(true);
    set_topoHistoryIdx(-1);
    updateTopoRoundLabel();
    fetchTopology();
}

export function topoHistoryPrev() {
    if (_topoHistory.length === 0) { fetchTopoHistory(); return; }
    set_topologyLiveMode(false);
    if (_topoHistoryIdx < 0) {
        // Currently live -- go to the last recorded round
        set_topoHistoryIdx(_topoHistory.length - 1);
    } else if (_topoHistoryIdx > 0) {
        set_topoHistoryIdx(_topoHistoryIdx - 1);
    }
    queueTopologyRender(_topoHistory[_topoHistoryIdx], true);
    updateTopoRoundLabel();
}

export function topoHistoryNext() {
    if (_topoHistory.length === 0) { fetchTopoHistory(); return; }
    if (_topologyLiveMode || _topoHistoryIdx < 0) return; // Already live
    if (_topoHistoryIdx < _topoHistory.length - 1) {
        set_topoHistoryIdx(_topoHistoryIdx + 1);
        queueTopologyRender(_topoHistory[_topoHistoryIdx], true);
    } else {
        topoGoLive();
        return;
    }
    updateTopoRoundLabel();
}

// ── Decisions ────────────────────────────────────────────────
export function fetchDecisions() {
    if (!colonyState.colony_id) return;
    const colonyId = encodeURIComponent(colonyState.colony_id);
    apiGet(API_V1 + '/colonies/' + colonyId + '/decisions').then(function (data) {
        const decisions = data.decisions || data || [];
        const hash = hashString(JSON.stringify(decisions));
        if (hash === _lastDecisionHash) return;
        set_lastDecisionHash(hash);

        renderDecisionLog(decisions);
    }).catch(function () {});
}

export function exportDecisions() {
    if (!colonyState.colony_id) { showNotification('No colony selected', 'warning'); return; }
    const colonyId = encodeURIComponent(colonyState.colony_id);
    apiGet(API_V1 + '/colonies/' + colonyId + '/decisions').then(function (data) {
        const decisions = data.decisions || data || [];
        const blob = new Blob([JSON.stringify(decisions, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = colonyState.colony_id + '-decisions.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }).catch(function (err) {
        showNotification('Export failed: ' + err.message, 'error');
    });
}

export function buildDecisionEntryHTML(d, idx) {
    let round = d.round_num;
    if (round === undefined || round === null) round = d.round;
    if (round === undefined || round === null) round = '?';
    const phase = d.phase || d.decision_type || '';
    let text = d.detail || d.text || d.decision || d.summary || '';
    if (!text) text = JSON.stringify(d);
    const fullJson = escapeHtml(JSON.stringify(d, null, 2));
    let html = '<div class="decision-entry" onclick="toggleDecisionDetail(this)">';
    html += '<span class="decision-round">R' + round + '</span>';
    if (phase) html += '<span class="decision-phase">' + escapeHtml(phase) + '</span>';
    html += '<div class="decision-text">' + escapeHtml(text) + '</div>';
    html += '<pre class="decision-detail hidden">' + fullJson + '</pre>';
    html += '</div>';
    return html;
}

export function toggleDecisionDetail(el) {
    const detail = el.querySelector('.decision-detail');
    if (detail) detail.classList.toggle('hidden');
}

export function renderDecisionLog(decisions) {
    const container = document.getElementById('decision-log');
    if (!container) return;

    const countEl = document.getElementById('decision-count');
    if (countEl) countEl.textContent = String(decisions.length);

    if (decisions.length === 0) {
        container.innerHTML = '<div class="empty-state">No decisions recorded yet.</div>';
        _lastDecisionCount = 0;
        return;
    }

    // Smart scroll: remember if user was at top (newest first)
    const wasAtTop = container.scrollTop < 30;

    // Incremental: only prepend new decisions if list grew monotonically
    const newCount = decisions.length - _lastDecisionCount;
    if (newCount > 0 && _lastDecisionCount > 0 && newCount < decisions.length) {
        let frag = '';
        for (let i = decisions.length - 1; i >= decisions.length - newCount; i--) {
            frag += buildDecisionEntryHTML(decisions[i]);
        }
        container.insertAdjacentHTML('afterbegin', frag);
    } else {
        // Full rebuild
        let html = '';
        for (let i = decisions.length - 1; i >= 0; i--) {
            html += buildDecisionEntryHTML(decisions[i]);
        }
        container.innerHTML = html;
    }
    _lastDecisionCount = decisions.length;

    if (wasAtTop) {
        container.scrollTop = 0;
    }
}
