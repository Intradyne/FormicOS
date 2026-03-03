// FormicOS v0.7.9 — Objects surface module
// Handles castes, skills, MCP tools, and models management.

import { API_V1 } from '../Constants.js';
import {
    colonyState,
    currentPromptCaste, setCurrentPromptCaste,
    editingSkillId, setEditingSkillId
} from '../state.js';
import { escapeHtml, escapeAttr, truncateStr, showNotification } from '../utils.js';
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client.js';

// ── Local constants ──────────────────────────────────────────
const CORE_BUILTIN_TOOLS = [
    { id: 'file_read', desc: 'Read files from the colony workspace.' },
    { id: 'file_write', desc: 'Create or overwrite files in the workspace.' },
    { id: 'file_delete', desc: 'Delete files from the workspace (approval-gated by default).' },
    { id: 'code_execute', desc: 'Run Python snippets for validation and debugging.' },
    { id: 'fetch', desc: 'Fetch URL content from the web.' },
    { id: 'web_search', desc: 'Search the web and return summarized results.' },
    { id: 'qdrant_search', desc: 'Search the local project knowledge index (RAG).' }
];

// ── Objects Surface ──────────────────────────────────────────
// Consolidates: Colony config, Teams, Castes, Skills, MCP, Models
export function loadObjects() {
    try { loadObjCastes(); }     catch (e) { console.error('obj-castes:', e); }
    try { loadObjSkills(); }     catch (e) { console.error('obj-skills:', e); }
    try { loadMcpTools(); }      catch (e) { console.error('obj-mcp:', e); }
    try { loadModels(); }        catch (e) { console.error('obj-models:', e); }
}

export function switchObjectSection(sectionId) {
    // Update sidebar buttons
    const btns = document.querySelectorAll('.obj-nav-btn');
    for (let i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('active', btns[i].getAttribute('data-section') === sectionId);
    }
    // Update sections
    const sections = document.querySelectorAll('.obj-section');
    for (let i = 0; i < sections.length; i++) {
        sections[i].classList.toggle('active', sections[i].id === sectionId);
    }
}

// -- Objects: Castes (CRUD)
export function loadObjCastes() {
    apiGet(API_V1 + '/castes').then(function (data) {
        renderCastesList(data);
    }).catch(function () {
        const el = document.getElementById('obj-castes-list');
        if (el) el.innerHTML = '<div class="empty-state">Failed to load castes.</div>';
    });
}

export function renderCastesList(castes) {
    const container = document.getElementById('obj-castes-list');
    if (!container) return;
    let html = '';
    const names = Object.keys(castes);
    for (let i = 0; i < names.length; i++) {
        const name = names[i];
        const c = castes[name];
        const toolCount = (c.tools || []).length + (c.mcp_tools || []).length;
        html += '<div class="caste-card" onclick="selectCaste(\'' + escapeAttr(name) + '\')">';
        html += '<div class="caste-card-name">' + escapeHtml(name) + '</div>';
        html += '<div class="caste-card-desc">' + escapeHtml(c.description || '') + '</div>';
        html += '<div class="caste-card-meta">' + toolCount + ' tools</div>';
        html += '</div>';
    }
    container.innerHTML = html;
}

export function selectCaste(name) {
    setCurrentPromptCaste(name);
    apiGet(API_V1 + '/castes').then(function (castes) {
        const c = castes[name];
        if (!c) return;
        document.getElementById('caste-editor-title').textContent = 'Edit: ' + name;
        document.getElementById('caste-prompt-editor').value = c.system_prompt || '';
        document.getElementById('caste-desc').value = c.description || '';

        // Populate model override dropdown
        const modelSel = document.getElementById('caste-model-override');
        if (modelSel) {
            apiGet(API_V1 + '/models').then(function (modelData) {
                let models = modelData.models || modelData || [];
                let html = '<option value="">Default (global inference)</option>';
                if (Array.isArray(models)) {
                    for (let i = 0; i < models.length; i++) {
                        const mid = models[i].model_id || models[i].id || '';
                        const sel = (c.model_override === mid) ? ' selected' : '';
                        html += '<option value="' + escapeAttr(mid) + '"' + sel + '>' + escapeHtml(mid) + '</option>';
                    }
                } else if (models && typeof models === 'object') {
                    const keys = Object.keys(models);
                    for (let i = 0; i < keys.length; i++) {
                        const mid = keys[i];
                        const sel = (c.model_override === mid) ? ' selected' : '';
                        html += '<option value="' + escapeAttr(mid) + '"' + sel + '>' + escapeHtml(mid) + '</option>';
                    }
                }
                modelSel.innerHTML = html;
            }).catch(function(){});
        }

        // Populate builtin tools
        const builtinDiv = document.getElementById('caste-builtin-tools');
        if (builtinDiv) {
            const allBuiltin = ['file_read', 'file_write', 'file_delete', 'code_execute', 'fetch', 'web_search', 'qdrant_search'];
            const selectedBuiltin = c.tools || [];
            let bHtml = '';
            for (let i = 0; i < allBuiltin.length; i++) {
                const checked = selectedBuiltin.indexOf(allBuiltin[i]) >= 0 ? ' checked' : '';
                bHtml += '<label class="tool-check"><input type="checkbox" value="' + allBuiltin[i] + '"' + checked + '> ' + allBuiltin[i] + '</label>';
            }
            builtinDiv.innerHTML = bHtml;
        }

        // Populate MCP tools
        populateMcpToolChecklist(c.mcp_tools || []);

        // Populate subcaste overrides
        populateSubcasteOverrides(c.subcaste_overrides || {});

        document.getElementById('caste-editor').classList.remove('hidden');
    });
}

export function populateMcpToolChecklist(selectedTools) {
    apiGet(API_V1 + '/tools').then(function (tools) {
        tools = tools || [];
        const container = document.getElementById('caste-mcp-tools');
        if (!container) return;
        const showAllEl = document.getElementById('mcp-show-all');
        const showAll = !!(showAllEl && showAllEl.checked);
        let html = '';
        if (tools.length === 0) {
            html = '<span class="text-muted">No MCP tools available</span>';
        }
        for (let i = 0; i < tools.length; i++) {
            const t = tools[i];
            if (!showAll && !isDockerToolkitManagementTool(t.id, t.server || '')) continue;
            const checked = selectedTools.indexOf(t.id) >= 0 ? ' checked' : '';
            html += '<label class="tool-check"><input type="checkbox" value="' + escapeAttr(t.id) + '"' + checked + '> ' + escapeHtml(t.id) + '</label>';
        }
        if (!html) {
            html = '<span class="text-muted">No tools in current filtered set. Enable "Show all discovered MCP tools" in Tools view to edit full policy.</span>';
        }
        container.innerHTML = html;
    }).catch(function () {
        const el = document.getElementById('caste-mcp-tools');
        if (el) el.innerHTML = '<span class="text-muted">MCP not connected</span>';
    });
}

export function populateSubcasteOverrides(overrides) {
    const container = document.getElementById('caste-subcaste-overrides');
    if (!container) return;
    const tiers = ['heavy', 'balanced', 'light'];
    let html = '';
    for (let i = 0; i < tiers.length; i++) {
        const tier = tiers[i];
        const current = overrides[tier] ? (overrides[tier].primary || '') : '';
        html += '<div class="subcaste-override-row">';
        html += '<span class="subcaste-tier-label">' + tier + '</span>';
        html += '<input type="text" class="form-input subcaste-model-input" data-tier="' + tier + '" value="' + escapeAttr(current) + '" placeholder="model registry ID (empty = global default)">';
        html += '</div>';
    }
    container.innerHTML = html;
}

export function saveCaste() {
    if (!currentPromptCaste) return;
    // Handle new caste creation
    if (window._creatingNewCaste) {
        window._creatingNewCaste = false;
        const prompt = document.getElementById('caste-prompt-editor').value;
        const desc = document.getElementById('caste-desc').value;
        const modelOverride = document.getElementById('caste-model-override').value;
        const builtinChecks = document.querySelectorAll('#caste-builtin-tools input[type=checkbox]:checked');
        const tools = [];
        for (let i = 0; i < builtinChecks.length; i++) tools.push(builtinChecks[i].value);
        const mcpChecks = document.querySelectorAll('#caste-mcp-tools input[type=checkbox]:checked');
        const mcpTools = [];
        for (let i = 0; i < mcpChecks.length; i++) mcpTools.push(mcpChecks[i].value);
        const subOverrides = {};
        const subInputs = document.querySelectorAll('.subcaste-model-input');
        for (let i = 0; i < subInputs.length; i++) {
            const tier = subInputs[i].getAttribute('data-tier');
            const val = subInputs[i].value.trim();
            if (val) subOverrides[tier] = { primary: val };
        }
        apiPost(API_V1 + '/castes', {
            name: currentPromptCaste,
            system_prompt: prompt,
            tools: tools,
            mcp_tools: mcpTools,
            model_override: modelOverride,
            subcaste_overrides: subOverrides,
            description: desc
        }).then(function () {
            showNotification('Caste created: ' + currentPromptCaste, 'success');
            closeCasteEditor();
            loadObjCastes();
        }).catch(function (err) {
            showNotification('Create failed: ' + err.message, 'error');
        });
        return;
    }
    const prompt = document.getElementById('caste-prompt-editor').value;
    const desc = document.getElementById('caste-desc').value;
    const modelOverride = document.getElementById('caste-model-override').value;

    // Collect builtin tools
    const builtinChecks = document.querySelectorAll('#caste-builtin-tools input[type=checkbox]:checked');
    const tools = [];
    for (let i = 0; i < builtinChecks.length; i++) tools.push(builtinChecks[i].value);

    // Collect MCP tools
    const mcpChecks = document.querySelectorAll('#caste-mcp-tools input[type=checkbox]:checked');
    const mcpTools = [];
    for (let i = 0; i < mcpChecks.length; i++) mcpTools.push(mcpChecks[i].value);

    // Collect subcaste overrides
    const subOverrides = {};
    const subInputs = document.querySelectorAll('.subcaste-model-input');
    for (let i = 0; i < subInputs.length; i++) {
        const tier = subInputs[i].getAttribute('data-tier');
        const val = subInputs[i].value.trim();
        if (val) subOverrides[tier] = { primary: val };
    }

    apiPut(API_V1 + '/castes/' + encodeURIComponent(currentPromptCaste), {
        system_prompt: prompt,
        tools: tools,
        mcp_tools: mcpTools,
        model_override: modelOverride,
        subcaste_overrides: subOverrides,
        description: desc
    }).then(function () {
        showNotification('Caste saved: ' + currentPromptCaste, 'success');
        loadObjCastes();
    }).catch(function (err) {
        showNotification('Save failed: ' + err.message, 'error');
    });
}

export function deleteCaste() {
    if (!currentPromptCaste) return;
    if (!confirm('Delete caste "' + currentPromptCaste + '"? This cannot be undone.')) return;
    apiDelete(API_V1 + '/castes/' + encodeURIComponent(currentPromptCaste)).then(function () {
        showNotification('Caste deleted: ' + currentPromptCaste, 'success');
        closeCasteEditor();
        loadObjCastes();
    }).catch(function (err) {
        showNotification('Delete failed: ' + err.message, 'error');
    });
}

export function closeCasteEditor() {
    document.getElementById('caste-editor').classList.add('hidden');
    setCurrentPromptCaste(null);
}

export function showCreateCasteForm() {
    setCurrentPromptCaste(null);
    document.getElementById('caste-editor-title').textContent = 'Create New Caste';
    document.getElementById('caste-prompt-editor').value = '';
    document.getElementById('caste-desc').value = '';
    const builtinDiv = document.getElementById('caste-builtin-tools');
    if (builtinDiv) {
        const allBuiltin = ['file_read', 'file_write', 'file_delete', 'code_execute', 'fetch', 'web_search', 'qdrant_search'];
        let bHtml = '';
        for (let i = 0; i < allBuiltin.length; i++) {
            bHtml += '<label class="tool-check"><input type="checkbox" value="' + allBuiltin[i] + '"> ' + allBuiltin[i] + '</label>';
        }
        builtinDiv.innerHTML = bHtml;
    }
    populateMcpToolChecklist([]);
    populateSubcasteOverrides({});

    // Override save to call create
    const namePrompt = prompt('Enter caste name:');
    if (!namePrompt || !namePrompt.trim()) return;
    setCurrentPromptCaste(namePrompt.trim().toLowerCase());
    document.getElementById('caste-editor-title').textContent = 'Create: ' + currentPromptCaste;
    document.getElementById('caste-editor').classList.remove('hidden');

    // Temporarily replace saveCaste behavior for creation
    const origSave = window._origSaveCaste;
    if (!origSave) window._origSaveCaste = saveCaste;

    // Use a flag to track if this is a new caste
    window._creatingNewCaste = true;
}

export function savePrompt() {
    // Legacy compat -- redirect to saveCaste
    saveCaste();
}

export function loadObjSubcastes() {
    // Subcastes are now merged into the caste editor
}

// -- Objects: Skills (CRUD)
export function loadObjSkills() {
    apiGet(API_V1 + '/skills').then(function (data) {
        const skills = data.skills || data || [];
        renderSkillsList(skills);
    }).catch(function () {
        const el = document.getElementById('obj-skills-list');
        if (el) el.innerHTML = '<div class="empty-state">Failed to load skills.</div>';
    });
}

export function renderSkillsList(skills) {
    const container = document.getElementById('obj-skills-list');
    if (!container) return;

    if (!skills || skills.length === 0) {
        container.innerHTML = '<div class="empty-state">No skills in the bank.</div>';
        return;
    }

    let html = '';
    for (let i = 0; i < skills.length; i++) {
        const s = skills[i];
        const skillId = s.id || s.skill_id || i;
        const name = s.name || 'Unnamed';
        const category = s.category || 'General';
        const desc = s.description || '';

        const isApiSkill = s.author_client_id && s.author_client_id !== 'system';
        html += '<div class="skill-card' + (isApiSkill ? ' skill-card-api' : '') + '">';
        html += '<div class="skill-card-header">';
        html += '<span class="skill-card-name">' + escapeHtml(name) + '</span>';
        if (isApiSkill) {
            html += '<span class="badge-api-client">\uD83E\uDD16 ' + escapeHtml(s.author_client_id) + '</span>';
        }
        html += '</div>';
        html += '<div class="skill-card-desc">' + escapeHtml(truncateStr(desc, 200)) + '</div>';
        html += '<div class="skill-card-meta"><span class="badge badge-neutral">' + escapeHtml(category) + '</span></div>';
        html += '<div class="skill-card-actions">';
        if (isApiSkill) {
            html += '<button class="btn-icon" onclick="editSkill(' + JSON.stringify(skillId).replace(/"/g, '&quot;') + ')" title="Review &amp; Edit">Review</button>';
        } else {
            html += '<button class="btn-icon" onclick="editSkill(' + JSON.stringify(skillId).replace(/"/g, '&quot;') + ')">Edit</button>';
        }
        html += '<button class="btn-icon" style="color:#F44336" onclick="deleteSkill(' + JSON.stringify(skillId).replace(/"/g, '&quot;') + ')">Del</button>';
        html += '</div></div>';
    }

    container.innerHTML = html;
}

export function showCreateSkillForm() {
    setEditingSkillId(null);
    document.getElementById('skill-form-title').textContent = 'Create Skill';
    document.getElementById('skill-form-id').value = '';
    document.getElementById('skill-form-name').value = '';
    document.getElementById('skill-form-category').value = 'General';
    document.getElementById('skill-form-desc').value = '';
    document.getElementById('skill-form-content').value = '';
    document.getElementById('skill-form-area').classList.remove('hidden');
}

export function editSkill(skillId) {
    apiGet(API_V1 + '/skills').then(function (data) {
        const skills = data.skills || data || [];
        let skill = null;
        for (let i = 0; i < skills.length; i++) {
            if ((skills[i].id || skills[i].skill_id) === skillId) {
                skill = skills[i];
                break;
            }
        }
        if (!skill) {
            showNotification('Skill not found', 'error');
            return;
        }

        setEditingSkillId(skillId);
        document.getElementById('skill-form-title').textContent = 'Edit Skill';
        document.getElementById('skill-form-id').value = skillId;
        document.getElementById('skill-form-name').value = skill.name || '';
        document.getElementById('skill-form-category').value = skill.category || 'General';
        document.getElementById('skill-form-desc').value = skill.description || '';
        document.getElementById('skill-form-content').value = skill.content || '';
        document.getElementById('skill-form-area').classList.remove('hidden');
    }).catch(function (err) {
        showNotification('Load failed: ' + err.message, 'error');
    });
}

export function submitSkillForm() {
    const name = document.getElementById('skill-form-name').value.trim();
    const category = document.getElementById('skill-form-category').value;
    const desc = document.getElementById('skill-form-desc').value.trim();
    const content = document.getElementById('skill-form-content').value.trim();

    if (!name) {
        showNotification('Skill name required', 'warning');
        return;
    }

    const payload = { name: name, category: category, description: desc, content: content };

    if (editingSkillId) {
        apiPut(API_V1 + '/skills/' + encodeURIComponent(editingSkillId), payload).then(function () {
            showNotification('Skill updated', 'success');
            cancelSkillForm();
            loadObjSkills();
        }).catch(function (err) {
            showNotification('Update failed: ' + err.message, 'error');
        });
    } else {
        apiPost(API_V1 + '/skills', payload).then(function () {
            showNotification('Skill created', 'success');
            cancelSkillForm();
            loadObjSkills();
        }).catch(function (err) {
            showNotification('Create failed: ' + err.message, 'error');
        });
    }
}

export function cancelSkillForm() {
    setEditingSkillId(null);
    document.getElementById('skill-form-area').classList.add('hidden');
}

export function deleteSkill(skillId) {
    if (!confirm('Delete this skill?')) return;

    apiDelete(API_V1 + '/skills/' + encodeURIComponent(skillId)).then(function () {
        showNotification('Skill deleted', 'success');
        loadObjSkills();
    }).catch(function (err) {
        showNotification('Delete failed: ' + err.message, 'error');
    });
}

// -- Objects: MCP Tools
export function isDockerToolkitManagementTool(toolId, serverName) {
    const id = String(toolId || '').toLowerCase();
    const server = String(serverName || '').toLowerCase();
    if (id.indexOf('mcp-add') === 0 || id.indexOf('mcp_add') === 0) return true;
    if (id.indexOf('mcp-remove') === 0 || id.indexOf('mcp_remove') === 0) return true;
    if (id.indexOf('mcp-find') === 0 || id.indexOf('mcp_find') === 0) return true;
    if (id.indexOf('mcp-list') === 0 || id.indexOf('mcp_list') === 0) return true;
    if (id.indexOf('mcp-config-set') === 0 || id.indexOf('mcp_config_set') === 0) return true;
    if (id.indexOf('mcp-exec') === 0 || id.indexOf('mcp_exec') === 0) return true;
    // Local docker toolkit utility server is typically the management plane
    if (server === 'local' && id.indexOf('mcp-') === 0) return true;
    return false;
}

export function renderBuiltinToolsPanel() {
    const container = document.getElementById('obj-builtin-tools');
    if (!container) return;
    let html = '';
    for (let i = 0; i < CORE_BUILTIN_TOOLS.length; i++) {
        const t = CORE_BUILTIN_TOOLS[i];
        html += '<div class="mcp-tool-row">';
        html += '<span class="mcp-tool-id">' + escapeHtml(t.id) + '</span>';
        html += '<span class="mcp-tool-desc">' + escapeHtml(t.desc) + '</span>';
        html += '</div>';
    }
    container.innerHTML = html;
}

export function getMcpToolCategory(toolId) {
    const id = String(toolId || '').toLowerCase();
    if (!id) return 'misc';
    if (id.indexOf('mcp-') === 0 || id.indexOf('mcp_') === 0) return 'gateway';
    if (id.indexOf('manage_') === 0 || id.indexOf('manage-') === 0) return 'manage';
    if (id.indexOf('control_') === 0 || id.indexOf('control-') === 0) return 'control';
    if (id.indexOf('build_') === 0 || id.indexOf('build-') === 0) return 'build';
    if (id.indexOf('code-mode') === 0 || id.indexOf('code_mode') === 0) return 'code-mode';
    const split = id.split(/[_:-]/);
    return split[0] || 'misc';
}

export function loadMcpTools() {
    Promise.all([
        apiGet(API_V1 + '/tools/catalog'),
        apiGet(API_V1 + '/castes')
    ]).then(function (res) {
        const catalog = res[0] || {};
        const castes = res[1] || {};
        window._mcpCasteCache = castes;

        const statusEl = document.getElementById('mcp-gateway-status');
        if (statusEl) {
            const connected = !!catalog.connected;
            statusEl.textContent = connected ? 'Connected' : 'Disconnected';
            statusEl.className = 'badge ' + (connected ? 'badge-running' : 'badge-failed');
        }

        const casteSel = document.getElementById('mcp-policy-caste');
        if (casteSel) {
            const names = Object.keys(castes).sort();
            const selected = casteSel.value;
            let opts = '';
            for (let i = 0; i < names.length; i++) {
                const sel = names[i] === selected ? ' selected' : '';
                opts += '<option value="' + escapeAttr(names[i]) + '"' + sel + '>' + escapeHtml(names[i]) + '</option>';
            }
            casteSel.innerHTML = opts || '<option value="">No castes</option>';
        }

        renderBuiltinToolsPanel();

        const showAllEl = document.getElementById('mcp-show-all');
        const selectedOnlyEl = document.getElementById('mcp-selected-only');
        const searchEl = document.getElementById('mcp-tool-search');
        const showAll = !!(showAllEl && showAllEl.checked);
        const selectedOnly = !!(selectedOnlyEl && selectedOnlyEl.checked);
        const search = (searchEl ? searchEl.value : '').trim().toLowerCase();
        const selectedCaste = casteSel ? casteSel.value : '';
        const selectedTools = (castes[selectedCaste] && castes[selectedCaste].mcp_tools) ? castes[selectedCaste].mcp_tools : [];
        const selectedSet = {};
        for (let si = 0; si < selectedTools.length; si++) selectedSet[selectedTools[si]] = true;

        const container = document.getElementById('obj-mcp-tools');
        if (!container) return;
        const servers = catalog.servers || {};
        const serverNames = Object.keys(servers).sort();
        if (!serverNames.length) {
            container.innerHTML = '<div class="empty-state">No MCP tools available. Check gateway connection.</div>';
            return;
        }

        let html = '';
        let totalVisible = 0;
        let totalSelectedVisible = 0;
        for (let s = 0; s < serverNames.length; s++) {
            const sName = serverNames[s];
            const allTools = servers[sName] || [];
            const categories = {};
            let serverVisible = 0;
            let serverSelectedVisible = 0;
            for (let k = 0; k < allTools.length; k++) {
                const tk = allTools[k] || {};
                const tkId = tk.id || tk.name || String(tk);
                const tkDesc = String(tk.description || '').toLowerCase();
                if (!showAll && !isDockerToolkitManagementTool(tkId, sName)) continue;
                if (search && String(tkId).toLowerCase().indexOf(search) < 0 && tkDesc.indexOf(search) < 0) continue;
                if (selectedOnly && !selectedSet[tkId]) continue;

                const category = getMcpToolCategory(tkId);
                if (!categories[category]) categories[category] = [];
                categories[category].push(tk);
                serverVisible++;
                if (selectedSet[tkId]) serverSelectedVisible++;
            }
            if (!serverVisible) continue;
            totalVisible += serverVisible;
            totalSelectedVisible += serverSelectedVisible;

            const serverArg = JSON.stringify(sName).replace(/"/g, '&quot;');
            html += '<div class="mcp-server-group">';
            html += '<div class="mcp-server-name">';
            html += '<span>' + escapeHtml(sName) + ' (' + serverSelectedVisible + '/' + serverVisible + ' selected)</span>';
            html += '<div class="mcp-server-actions">';
            html += '<button class="btn-icon" onclick="toggleServerTools(' + serverArg + ', true)">All</button>';
            html += '<button class="btn-icon" onclick="toggleServerTools(' + serverArg + ', false)">None</button>';
            html += '</div></div>';

            const categoryNames = Object.keys(categories).sort();
            for (let ci = 0; ci < categoryNames.length; ci++) {
                const catName = categoryNames[ci];
                const catTools = categories[catName] || [];
                if (!catTools.length) continue;
                const catArg = JSON.stringify(catName).replace(/"/g, '&quot;');
                html += '<div class="mcp-category-group">';
                html += '<div class="mcp-category-header">';
                html += '<span class="mcp-category-name">' + escapeHtml(catName) + ' (' + catTools.length + ')</span>';
                html += '<div class="mcp-category-actions">';
                html += '<button class="btn-icon" onclick="toggleServerCategoryTools(' + serverArg + ', ' + catArg + ', true)">All</button>';
                html += '<button class="btn-icon" onclick="toggleServerCategoryTools(' + serverArg + ', ' + catArg + ', false)">None</button>';
                html += '</div></div>';

                for (let t = 0; t < catTools.length; t++) {
                    const tool = catTools[t] || {};
                    const toolId = tool.id || tool.name || String(tool);
                    const desc = tool.description || '';
                    html += '<label class="mcp-tool-row">';
                    html += '<input type="checkbox" class="mcp-tool-check" data-server="' + escapeAttr(sName) + '" data-category="' + escapeAttr(catName) + '" data-tool-id="' + escapeAttr(toolId) + '">';
                    html += '<span class="mcp-tool-id">' + escapeHtml(toolId) + '</span>';
                    if (desc) {
                        html += '<span class="mcp-tool-desc">' + escapeHtml(truncateStr(desc, 120)) + '</span>';
                    }
                    html += '</label>';
                }
                html += '</div>';
            }
            html += '</div>';
        }
        if (!html) {
            html = '<div class="empty-state">No MCP tools match current filters.' +
                (showAll ? '' : ' Enable "Show all discovered MCP tools" to inspect all servers.') + '</div>';
        } else {
            html = '<div class="text-muted" style="margin-bottom:8px;">Visible tools: ' + totalVisible +
                ' | Selected in current caste: ' + totalSelectedVisible + '</div>' + html;
        }
        container.innerHTML = html;
        syncMcpSelectionFromSelectedCaste();
    }).catch(function () {
        const el = document.getElementById('obj-mcp-tools');
        if (el) el.innerHTML = '<div class="empty-state">Failed to load MCP tools.</div>';
    });
}

export function toggleServerTools(serverName, enabled) {
    const checks = document.querySelectorAll('.mcp-tool-check');
    for (let i = 0; i < checks.length; i++) {
        if (checks[i].getAttribute('data-server') === serverName) {
            checks[i].checked = !!enabled;
        }
    }
}

export function toggleServerCategoryTools(serverName, category, enabled) {
    const checks = document.querySelectorAll('.mcp-tool-check');
    for (let i = 0; i < checks.length; i++) {
        if (checks[i].getAttribute('data-server') === serverName &&
            checks[i].getAttribute('data-category') === category) {
            checks[i].checked = !!enabled;
        }
    }
}

export function toggleVisibleMcpTools(enabled) {
    const checks = document.querySelectorAll('.mcp-tool-check');
    for (let i = 0; i < checks.length; i++) {
        checks[i].checked = !!enabled;
    }
}

export function syncMcpSelectionFromSelectedCaste() {
    const casteSel = document.getElementById('mcp-policy-caste');
    if (!casteSel) return;
    const casteName = casteSel.value;
    const castes = window._mcpCasteCache || {};
    const caste = castes[casteName] || {};
    const allowed = caste.mcp_tools || [];
    const allowedSet = {};
    for (let i = 0; i < allowed.length; i++) allowedSet[allowed[i]] = true;

    const checks = document.querySelectorAll('.mcp-tool-check');
    for (let c = 0; c < checks.length; c++) {
        checks[c].checked = !!allowedSet[checks[c].getAttribute('data-tool-id')];
    }
}

export function applyMcpSelectionToCaste() {
    const casteSel = document.getElementById('mcp-policy-caste');
    if (!casteSel || !casteSel.value) {
        showNotification('Select a caste first', 'warning');
        return;
    }
    const selected = [];
    const checks = document.querySelectorAll('.mcp-tool-check:checked');
    for (let i = 0; i < checks.length; i++) {
        selected.push(checks[i].getAttribute('data-tool-id'));
    }
    apiPut(API_V1 + '/castes/' + encodeURIComponent(casteSel.value), { mcp_tools: selected }).then(function () {
        showNotification('MCP tool policy saved for caste: ' + casteSel.value, 'success');
        if (window._mcpCasteCache && window._mcpCasteCache[casteSel.value]) {
            window._mcpCasteCache[casteSel.value].mcp_tools = selected;
        }
    }).catch(function (err) {
        showNotification('Failed to save MCP policy: ' + err.message, 'error');
    });
}

export function reconnectMcp() {
    apiPost('/api/mcp/reconnect', {}).then(function () {
        showNotification('MCP reconnect initiated', 'info');
        setTimeout(loadMcpTools, 2000);
    }).catch(function (err) {
        showNotification('MCP reconnect failed: ' + err.message, 'error');
    });
}

// -- Objects: Models (folded into Objects from old Models tab)
export function loadModels() {
    try {
        apiGet(API_V1 + '/models').then(function (data) {
            // API returns {model_id: {backend, endpoint, ...}, ...} dict -- convert to array
            let models;
            if (Array.isArray(data)) {
                models = data;
            } else if (data && typeof data === 'object') {
                models = Object.keys(data).map(function (key) {
                    const entry = data[key];
                    entry.model_id = entry.model_id || key;
                    return entry;
                });
            } else {
                models = [];
            }
            renderModelTable(models);
        }).catch(function (err) {
            const tbody = document.getElementById('models-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Failed to load: ' + escapeHtml(err.message) + '</td></tr>';
        });
    } catch (err) {
        console.error('Models load error:', err);
    }
}

export function renderModelTable(models) {
    const tbody = document.getElementById('models-tbody');
    if (!tbody) return;

    if (!models || models.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No models registered.</td></tr>';
        return;
    }

    let html = '';
    for (let i = 0; i < models.length; i++) {
        const m = models[i];
        const modelId = m.model_id || m.id || m.name || '--';
        const backend = m.backend || m.type || '--';
        const endpoint = m.endpoint || m.url || '--';
        const status = m.status || 'unknown';
        const vram = m.vram_gb || m.vram || m.vram_mb || '--';
        const circuitState = m.circuit_state || null;

        let statusColor = '#666';
        const statusLower = String(status).toLowerCase();
        if (statusLower === 'ready' || statusLower === 'loaded' || statusLower === 'healthy') statusColor = '#4CAF50';
        else if (statusLower === 'loading' || statusLower === 'warming') statusColor = '#FFC107';
        else if (statusLower === 'error' || statusLower === 'failed') statusColor = '#F44336';

        // Circuit breaker indicator
        let circuitHtml = '<span class="circuit-indicator circuit-unknown" title="Unknown">--</span>';
        if (circuitState) {
            const cs = String(circuitState).toUpperCase();
            if (cs === 'CLOSED') circuitHtml = '<span class="circuit-indicator circuit-closed" title="Circuit Closed">Healthy</span>';
            else if (cs === 'HALF_OPEN' || cs === 'HALF-OPEN') circuitHtml = '<span class="circuit-indicator circuit-half-open" title="Circuit Half-Open">Probing</span>';
            else if (cs === 'OPEN') circuitHtml = '<span class="circuit-indicator circuit-open" title="Circuit Open">Unavailable</span>';
        }

        html += '<tr>';
        html += '<td class="font-mono">' + escapeHtml(modelId) + '</td>';
        html += '<td>' + escapeHtml(backend) + '</td>';
        html += '<td class="font-mono font-sm truncate" style="max-width:200px">' + escapeHtml(endpoint) + '</td>';
        html += '<td>' + circuitHtml + '</td>';
        html += '<td><span style="color:' + statusColor + '">' + escapeHtml(status) + '</span></td>';
        html += '<td>' + (typeof vram === 'number' ? vram + ' GB' : escapeHtml(String(vram))) + '</td>';
        html += '</tr>';
    }

    tbody.innerHTML = html;
}
