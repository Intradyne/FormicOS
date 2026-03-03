// FormicOS v0.7.9 — Main Entry Point
// ES6 module orchestrator: bootstrap, event listeners, window bindings

import { ColonyStatus, SURFACES, POLL_FAST, POLL_SLOW, POLL_IDLE } from './Constants.js';
import {
    colonyState, currentTab, setCurrentTab, pollInterval, setPollInterval,
    cy, appState
} from './state.js';
import { hashString } from './utils.js';

// ── API layer ────────────────────────────────────────────────
import { apiGet, apiPost, apiPut, apiDelete } from './api/client.js';

// ── WebSocket layer ──────────────────────────────────────────
import {
    connectWebSocket, subscribeToColony, scheduleReconnect,
    reconnectWebSocket, updateWsIndicator, updateOperationsWsStatus,
    updateOperationsWsReconnects
} from './websockets/socket_manager.js';

// ── UI: Colony ───────────────────────────────────────────────
import {
    normalizeStatus, isCreateModalOpen, getCreateFormElements,
    setAppState, setColonyViewState, fetchColonyState,
    updateColonyStatusDisplay, getStatusColor
} from './ui/colony.js';

// ── UI: Fleet ────────────────────────────────────────────────
import {
    loadFleet, updateFleetPagination, fleetPrevPage, fleetNextPage,
    renderFleetTable, renderColonyCards, viewColony, reuseColony,
    reuseCurrentColony, showCreateColonyModal, addTeamMember,
    getCastesCached, addTeamMemberRow, hideCreateColonyModal,
    applyTeamPreset, suggestTeam, submitCreateColony,
    startColony, pauseColony, resumeColony, destroyColony,
    fleetBulkPause, fleetBulkResume, fleetBulkDestroy
} from './ui/fleet.js';

// ── UI: Console ──────────────────────────────────────────────
import {
    appendStreamToken, appendToolCall, handleRoundUpdate,
    handleColonyComplete, handleWsError, updatePhaseDisplay,
    autoScrollConsole, clearConsole, registerConsoleAgent,
    filterConsoleByAgent, pruneConsole
} from './ui/console.js';

// ── UI: Modals ───────────────────────────────────────────────
import {
    handleHeadlessApprovalRequested, overrideHeadlessApproval,
    handleColonySpawned, handleEpochAdvanced,
    showApprovalModal, approveAction, dismissApprovalModal
} from './ui/modals.js';

// ── UI: Workspace ────────────────────────────────────────────
import {
    refreshWorkspace, resetWorkspaceState, renderWorkspaceFiles, navigateWorkspace,
    viewWorkspaceFile, closeWorkspaceViewer, uploadWorkspaceFile,
    downloadWorkspaceArchive, openWorkspaceArchiveModal,
    hideWorkspaceArchiveModal, filterWorkspaceArchiveFiles,
    getVisibleWorkspaceArchiveFiles, renderWorkspaceArchiveFiles,
    toggleWorkspaceArchiveFileSelection, setWorkspaceArchiveSelectionVisible,
    downloadSelectedWorkspaceArchive, openWorkspaceFolder
} from './ui/workspace.js';

// ── UI: Topology ─────────────────────────────────────────────
import {
    fetchTopology, transformTkgToCytoscape, queueTopologyRender,
    markGraphInteracting, buildTopologySignature, initCytoscape,
    clampNumber, formatTopologyLabel, updateTopologyGraph,
    toggleGraphView, fitGraph, changeGraphLayout,
    fetchTopoHistory, renderTopoRoundProgress, updateTopoControls,
    updateTopoRoundLabel, topoGoLive, topoHistoryPrev, topoHistoryNext,
    fetchDecisions, exportDecisions, buildDecisionEntryHTML,
    toggleDecisionDetail, renderDecisionLog
} from './ui/topology.js';

// ── UI: Dashboard ────────────────────────────────────────────
import {
    loadMission, loadColonyWorkspace, dashboardRunTask,
    dashboardExtendRounds, dashboardPauseResume, dashboardInjectHint,
    fetchAndShowResults, hideResultsModal
} from './ui/dashboard.js';

// ── UI: Operations ───────────────────────────────────────────
import {
    showDataClawModal, hideDataClawModal,
    executeDataClawExport, loadQueueState, renderQueueDashboard,
    dropQueuedColony, loadSystemDiagnostics, renderDiagnostics,
    loadOperations, loadMetrics, loadSessions, renderSessionTable,
    resumeSession, deleteSession, loadSettings, loadApiKeys,
    renderApiKeysTable, showGenerateApiKeyModal, hideGenerateApiKeyModal,
    submitGenerateApiKey, copyApiKeyToClipboard, revokeApiKey,
    sendApiRequest, showWebhookDebugModal, hideWebhookDebugModal,
    loadWebhookLogs, toggleWebhookPayload
} from './ui/operations.js';

// ── UI: Objects ──────────────────────────────────────────────
import {
    loadObjects, switchObjectSection, loadObjCastes, renderCastesList,
    selectCaste, populateMcpToolChecklist, populateSubcasteOverrides,
    saveCaste, deleteCaste, closeCasteEditor, showCreateCasteForm,
    savePrompt, loadObjSubcastes, loadObjSkills, renderSkillsList,
    showCreateSkillForm, editSkill, submitSkillForm, cancelSkillForm,
    deleteSkill, isDockerToolkitManagementTool, renderBuiltinToolsPanel,
    getMcpToolCategory, loadMcpTools, toggleServerTools,
    toggleServerCategoryTools, toggleVisibleMcpTools,
    syncMcpSelectionFromSelectedCaste, applyMcpSelectionToCaste,
    reconnectMcp, loadModels, renderModelTable
} from './ui/objects.js';

// ═══════════════════════════════════════════════════════════════
// Tab Navigation
// ═══════════════════════════════════════════════════════════════

function initTabs() {
    const btns = document.querySelectorAll('.tab-btn');
    btns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            switchTab(btn.getAttribute('data-tab'));
        });
    });
}

function switchTab(tab) {
    if (!SURFACES.includes(tab)) return;
    setCurrentTab(tab);

    document.querySelectorAll('.tab-btn').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
    });
    document.querySelectorAll('.tab-content').forEach(function (s) {
        s.classList.toggle('active', s.id === 'tab-' + tab);
    });

    loadSurface(tab);
}

function loadSurface(tab) {
    try {
        switch (tab) {
            case 'fleet':             loadFleet();            break;
            case 'mission':           loadMission();          break;
            case 'colony-workspace':  loadColonyWorkspace();  break;
            case 'objects':           loadObjects();          break;
            case 'operations':        loadOperations();       break;
        }
    } catch (err) {
        console.error('Surface load error [' + tab + ']:', err);
    }
}

function handleHashRoute() {
    const hash = window.location.hash.replace('#', '');
    if (!hash) return;

    // Handle #colony/{colonyId} — navigate to that colony's workspace
    if (hash.startsWith('colony/')) {
        const colonyId = decodeURIComponent(hash.slice('colony/'.length));
        if (colonyId) {
            colonyState.colony_id = colonyId;

            // Purge stale UI from the previous colony
            clearConsole();
            resetWorkspaceState();

            // Subscribe WS to the new colony (server-side unsubs old automatically)
            subscribeToColony(colonyId);

            // Switch to colony-workspace tab (calls loadColonyWorkspace -> fetchColonyState)
            switchTab('colony-workspace');

            // Immediate full hydration — do not wait for the next poll cycle
            fetchColonyState();
            fetchTopology();
            fetchDecisions();
            refreshWorkspace();
            return;
        }
    }

    if (SURFACES.includes(hash)) {
        switchTab(hash);
    }
}

// ═══════════════════════════════════════════════════════════════
// Adaptive Polling
// ═══════════════════════════════════════════════════════════════

function getAdaptivePollInterval() {
    const status = normalizeStatus(colonyState.status);
    if (status === ColonyStatus.RUNNING) return POLL_FAST;
    if (status === ColonyStatus.PAUSED) return POLL_SLOW;
    return POLL_IDLE;
}

let _pollTimer = null;

function scheduleNextPoll() {
    if (_pollTimer) clearTimeout(_pollTimer);
    const interval = getAdaptivePollInterval();
    _pollTimer = setTimeout(function () {
        if (!document.hidden) {
            fetchAll();
        }
        scheduleNextPoll();
    }, interval);
}

function startPolling() {
    scheduleNextPoll();
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) {
            fetchAll();
            scheduleNextPoll();
        }
    });
}

function fetchAll() {
    fetchColonyState();
    updateGpuHeaderStat();

    switch (currentTab) {
        case 'colony-workspace':
            fetchTopology();
            fetchDecisions();
            refreshWorkspace();
            break;
        case 'fleet':
            break;
    }
}

// ═══════════════════════════════════════════════════════════════
// GPU Header Stat
// ═══════════════════════════════════════════════════════════════

let _gpuPollCounter = 0;

function updateGpuHeaderStat(force) {
    // Poll every ~30s (called from fetchAll which runs every 3-10s)
    if (!force) {
        _gpuPollCounter++;
        if (_gpuPollCounter % 10 !== 1) return;  // first call + every 10th
    }

    apiGet('/api/v1/system').then(function (data) {
        const el = document.getElementById('gpu-header-stat');
        if (!el || !data) return;
        const gpu = data.gpu || {};
        const budget = data.vram_budget || {};

        if (gpu.used_gb > 0 && gpu.total_gb > 0) {
            // Live nvidia-smi data available
            el.textContent = 'GPU: ' + gpu.used_gb.toFixed(1) + ' / ' + gpu.total_gb.toFixed(0) + ' GB';
            el.title = (gpu.name || 'GPU') + ' — ' + gpu.used_gb.toFixed(1) + ' / ' + gpu.total_gb.toFixed(0) + ' GB VRAM';
        } else if (budget.total_vram > 0) {
            // Fallback to VRAM budget from model registry
            const allocated = budget.allocated || 0;
            el.textContent = 'GPU: ' + allocated.toFixed(1) + ' / ' + budget.total_vram.toFixed(0) + ' GB';
            el.title = 'VRAM Budget — ' + allocated.toFixed(1) + ' allocated / ' + budget.total_vram.toFixed(0) + ' GB total';
        }
    }).catch(function () {
        // Silently fail — server may not be ready
    });
}

// ═══════════════════════════════════════════════════════════════
// Window Bindings — expose functions for HTML onclick handlers
// ═══════════════════════════════════════════════════════════════

// Fleet & Colony
window.loadFleet = loadFleet;
window.showCreateColonyModal = showCreateColonyModal;
window.hideCreateColonyModal = hideCreateColonyModal;
window.addTeamMember = addTeamMember;
window.applyTeamPreset = applyTeamPreset;
window.suggestTeam = suggestTeam;
window.submitCreateColony = submitCreateColony;
window.fleetPrevPage = fleetPrevPage;
window.fleetNextPage = fleetNextPage;
window.fleetBulkPause = fleetBulkPause;
window.fleetBulkResume = fleetBulkResume;
window.fleetBulkDestroy = fleetBulkDestroy;
window.viewColony = viewColony;
window.reuseColony = reuseColony;
window.reuseCurrentColony = reuseCurrentColony;
window.startColony = startColony;
window.pauseColony = pauseColony;
window.resumeColony = resumeColony;
window.destroyColony = destroyColony;

// Dashboard
window.dashboardRunTask = dashboardRunTask;
window.dashboardPauseResume = dashboardPauseResume;
window.dashboardExtendRounds = dashboardExtendRounds;
window.dashboardInjectHint = dashboardInjectHint;
window.hideResultsModal = hideResultsModal;
window.downloadWorkspaceArchive = downloadWorkspaceArchive;

// Topology & Graph
window.toggleGraphView = toggleGraphView;
window.fitGraph = fitGraph;
window.changeGraphLayout = changeGraphLayout;
window.topoGoLive = topoGoLive;
window.topoHistoryPrev = topoHistoryPrev;
window.topoHistoryNext = topoHistoryNext;

// Console
window.clearConsole = clearConsole;
window.filterConsoleByAgent = filterConsoleByAgent;

// Decisions
window.exportDecisions = exportDecisions;
window.toggleDecisionDetail = toggleDecisionDetail;

// Workspace
window.refreshWorkspace = refreshWorkspace;
window.navigateWorkspace = navigateWorkspace;
window.viewWorkspaceFile = viewWorkspaceFile;
window.closeWorkspaceViewer = closeWorkspaceViewer;
window.uploadWorkspaceFile = uploadWorkspaceFile;
window.openWorkspaceArchiveModal = openWorkspaceArchiveModal;
window.hideWorkspaceArchiveModal = hideWorkspaceArchiveModal;
window.filterWorkspaceArchiveFiles = filterWorkspaceArchiveFiles;
window.toggleWorkspaceArchiveFileSelection = toggleWorkspaceArchiveFileSelection;
window.setWorkspaceArchiveSelectionVisible = setWorkspaceArchiveSelectionVisible;
window.downloadSelectedWorkspaceArchive = downloadSelectedWorkspaceArchive;
window.openWorkspaceFolder = openWorkspaceFolder;

// Operations
window.showDataClawModal = showDataClawModal;
window.hideDataClawModal = hideDataClawModal;
window.executeDataClawExport = executeDataClawExport;
window.loadQueueState = loadQueueState;
window.dropQueuedColony = dropQueuedColony;
window.loadSystemDiagnostics = loadSystemDiagnostics;
window.loadOperations = loadOperations;
window.loadSessions = loadSessions;
window.resumeSession = resumeSession;
window.deleteSession = deleteSession;
window.loadApiKeys = loadApiKeys;
window.showGenerateApiKeyModal = showGenerateApiKeyModal;
window.hideGenerateApiKeyModal = hideGenerateApiKeyModal;
window.submitGenerateApiKey = submitGenerateApiKey;
window.copyApiKeyToClipboard = copyApiKeyToClipboard;
window.revokeApiKey = revokeApiKey;
window.sendApiRequest = sendApiRequest;
window.showWebhookDebugModal = showWebhookDebugModal;
window.hideWebhookDebugModal = hideWebhookDebugModal;
window.loadWebhookLogs = loadWebhookLogs;
window.toggleWebhookPayload = toggleWebhookPayload;

// Objects
window.loadObjects = loadObjects;
window.switchObjectSection = switchObjectSection;
window.showCreateCasteForm = showCreateCasteForm;
window.saveCaste = saveCaste;
window.deleteCaste = deleteCaste;
window.closeCasteEditor = closeCasteEditor;
window.savePrompt = savePrompt;
window.selectCaste = selectCaste;
window.applyMcpSelectionToCaste = applyMcpSelectionToCaste;
window.reconnectMcp = reconnectMcp;
window.loadMcpTools = loadMcpTools;
window.toggleServerTools = toggleServerTools;
window.toggleServerCategoryTools = toggleServerCategoryTools;
window.toggleVisibleMcpTools = toggleVisibleMcpTools;
window.syncMcpSelectionFromSelectedCaste = syncMcpSelectionFromSelectedCaste;
window.showCreateSkillForm = showCreateSkillForm;
window.editSkill = editSkill;
window.submitSkillForm = submitSkillForm;
window.cancelSkillForm = cancelSkillForm;
window.deleteSkill = deleteSkill;
window.loadModels = loadModels;

// Modals & Approvals
window.dismissApprovalModal = dismissApprovalModal;
window.approveAction = approveAction;
window.overrideHeadlessApproval = overrideHeadlessApproval;

// WebSocket
window.reconnectWebSocket = reconnectWebSocket;

// State access for inline references (e.g., results modal download button)
window.lastResultsColonyId = null;

// ═══════════════════════════════════════════════════════════════
// Bootstrap
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initCytoscape();
    renderTopoRoundProgress();
    connectWebSocket();
    startPolling();
    handleHashRoute();
    if (!window.location.hash || window.location.hash === '#') {
        switchTab('fleet');
    }
    updateGpuHeaderStat(true);
    setAppState('ready');
});

window.addEventListener('resize', function () {
    if (currentTab === 'colony-workspace' && cy) {
        cy.resize();
        cy.fit(undefined, 30);
    }
});

window.addEventListener('hashchange', function () {
    handleHashRoute();
});

// ── Keyboard Shortcuts ───────────────────────────────────────
document.addEventListener('keydown', function (e) {
    if (e.ctrlKey && e.key === 'Enter') {
        const active = document.activeElement;
        if (active && active.id === 'task-input') {
            e.preventDefault();
            dashboardRunTask();
        }
    }

    if (e.key === 'Escape') {
        dismissApprovalModal();
        hideCreateColonyModal();
        hideResultsModal();
        hideWorkspaceArchiveModal();
        hideWebhookDebugModal();
        hideGenerateApiKeyModal();
        hideDataClawModal();
        closeWorkspaceViewer();
    }
});
