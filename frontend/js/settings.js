// Settings Management (Dark mode only)

// API_URL is defined in main.js

document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    bindModelSettings();
});

let modelSettingsSnapshot = null;
let modelModels = new Map();
let modelTestResults = new Map();
let settingsReturnFocus = null;

// Dark mode is permanent now; keep this for backwards compatibility.
function applyTheme() {
    // no-op
}

async function loadSettings() {
    if (typeof getAuthToken === 'function' && !getAuthToken()) return;

    try {
        const settings = await apiJson(`${API_URL}/settings`);
        const usernameInput = document.getElementById('setting-username') || document.getElementById('settings-username');
        const themeInput = document.getElementById('setting-theme');
        const tempInput = document.getElementById('settings-temp');
        if (usernameInput && settings?.username != null) usernameInput.value = settings.username;
        if (themeInput && settings?.theme != null) themeInput.value = settings.theme;
        if (tempInput && settings?.ai_temperature != null) tempInput.value = settings.ai_temperature;
        await loadModelSettings();
    } catch (error) {
        showToast(error.message || 'Failed to load settings', 'error');
    }
}

function openSettings() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;
    settingsReturnFocus = document.activeElement;
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    showSettingsTab('models');
    loadModelSettings();
    document.getElementById('settings-title')?.focus();
}

function closeSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
    }
    if (settingsReturnFocus instanceof HTMLElement) settingsReturnFocus.focus();
    settingsReturnFocus = null;
}

async function saveSettings() {
    // Support both old and new IDs
    const usernameInput = document.getElementById('setting-username') || document.getElementById('settings-username');
    const themeInput = document.getElementById('setting-theme');
    const tempInput = document.getElementById('settings-temp');

    if (!usernameInput || !tempInput) {
        if (typeof showToast === 'function') {
            showToast("Settings form elements not found", "error");
        }
        return;
    }

    const username = usernameInput.value.trim();
    const theme = themeInput?.value;
    const temp = parseFloat(tempInput.value);

    if (!username) {
        if (typeof showToast === 'function') {
            showToast("Username is required", "error");
        }
        return;
    }

    try {
        const settings = await apiJson(`${API_URL}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                ...(theme ? { theme } : {}),
                ai_temperature: temp
            })
        });

        const usernameValue = settings?.username ?? username;
        if (usernameInput) usernameInput.value = usernameValue;
        if (tempInput && settings?.ai_temperature != null) tempInput.value = settings.ai_temperature;
        showToast("Settings saved!");
        closeSettings();
    } catch (error) {
        console.error("Error saving settings:", error);
        if (typeof showToast === 'function') {
            showToast("Error saving settings", "error");
        }
    }
}

function showSettingsTab(tab) {
    const modelsSelected = tab === 'models';
    document.getElementById('models-panel').hidden = !modelsSelected;
    document.getElementById('general-panel').hidden = modelsSelected;
    document.getElementById('models-tab').classList.toggle('active', modelsSelected);
    document.getElementById('general-tab').classList.toggle('active', !modelsSelected);
    document.getElementById('models-tab').setAttribute('aria-selected', String(modelsSelected));
    document.getElementById('general-tab').setAttribute('aria-selected', String(!modelsSelected));
}

async function loadModelSettings() {
    if (typeof getAuthToken === 'function' && !getAuthToken()) return;
    try {
        modelSettingsSnapshot = await apiJson(`${API_URL}/settings/models`);
        const localOnly = Boolean(modelSettingsSnapshot.local_only);
        const toggle = document.getElementById('local-only-toggle');
        const state = document.getElementById('local-only-state');
        if (toggle) toggle.checked = localOnly;
        if (state) state.textContent = localOnly
            ? 'On · cloud requests are blocked'
            : 'Off · messages may leave this device';
        renderConnectionList();
        renderRoleSummary();
        populateRoleForm();
        updateChatSelectionIndicator();
    } catch (_error) {
        const list = document.getElementById('connection-list');
        if (list) {
            AuraSafe.clear(list).appendChild(
                AuraSafe.element('p', 'error-state', 'Model settings could not be loaded. Check your connection and try again.')
            );
        }
    }
}

function updateChatSelectionIndicator() {
    const target = document.getElementById('chat-model-indicator');
    if (!target || !modelSettingsSnapshot) return;
    const selected = modelSettingsSnapshot.resolved_roles?.chat;
    if (!selected) {
        target.textContent = 'No Chat model selected';
    } else if (!selected.available) {
        target.textContent = `Chat model unavailable · ${selected.connection_name} · ${selected.model_id}`;
    } else {
        target.textContent = `${selected.connection_name} · ${selected.model_id}`;
    }
}

function renderConnectionList() {
    const list = document.getElementById('connection-list');
    if (!list || !modelSettingsSnapshot) return;
    const connections = modelSettingsSnapshot.connections || [];
    document.getElementById('connection-count').textContent = String(connections.length);
    AuraSafe.clear(list);
    if (!connections.length) {
        const empty = AuraSafe.element('div', 'connections-empty');
        empty.append(
            AuraSafe.element('p', 'empty-state-title', 'No connections yet'),
            AuraSafe.element('p', 'empty-state', 'Add Ollama for a local model or an OpenAI-compatible endpoint. AURA will not choose a model for you.')
        );
        list.appendChild(empty);
        return;
    }

    connections.forEach((connection) => {
        const row = AuraSafe.element('article', 'connection-row');
        row.dataset.connectionId = connection.id;
        const details = AuraSafe.element('div', 'connection-details');
        details.append(
            AuraSafe.element('h5', 'connection-name', connection.name),
            AuraSafe.element('span', 'connection-provider', connection.provider_type === 'ollama' ? 'Ollama' : 'OpenAI-compatible'),
            AuraSafe.element('code', 'connection-endpoint', connection.base_url)
        );
        const stateText = modelTestResults.get(connection.id)
            || (connection.has_api_key ? 'Key configured · not tested' : 'Configured · not tested');
        const state = AuraSafe.element('span', `connection-state${stateText.startsWith('Connected') ? ' is-connected' : stateText.startsWith('Blocked') || stateText.startsWith('Unavailable') ? ' is-warning' : ''}`, stateText);
        const actions = AuraSafe.element('div', 'connection-actions');
        actions.append(
            connectionAction('Test', 'test-connection', connection.id),
            connectionAction('Discover models', 'discover-models', connection.id),
            connectionAction('Edit', 'edit-connection', connection.id),
            connectionAction('Remove', 'remove-connection', connection.id, 'quiet-danger')
        );
        if (connection.provider_type === 'openai_compatible') {
            actions.appendChild(connectionAction(
                connection.has_api_key ? 'Remove key' : 'Key not set',
                'remove-credential',
                connection.id,
                connection.has_api_key ? 'quiet-danger' : 'is-disabled'
            ));
            actions.lastElementChild.disabled = !connection.has_api_key;
        }
        row.append(details, state, actions);
        list.appendChild(row);
    });
}

function connectionAction(label, action, connectionId, extraClass = '') {
    const button = AuraSafe.element('button', `connection-action ${extraClass}`, label);
    button.type = 'button';
    button.dataset.action = action;
    button.dataset.connectionId = connectionId;
    return button;
}

function renderRoleSummary() {
    const summary = document.getElementById('role-summary');
    if (!summary || !modelSettingsSnapshot) return;
    AuraSafe.clear(summary);
    ['chat', 'router', 'embedding'].forEach((role) => {
        const item = modelSettingsSnapshot.roles?.[role];
        const row = AuraSafe.element('div', `role-summary-row${item && !item.available ? ' unavailable' : ''}`);
        row.appendChild(AuraSafe.element('span', 'role-label', role[0].toUpperCase() + role.slice(1)));
        row.appendChild(AuraSafe.element(
            'span',
            'role-value',
            item ? `${item.connection_name} · ${item.model_id}${item.available ? '' : ' · Unavailable'}` : 'Not selected'
        ));
        summary.appendChild(row);
    });
}

function populateRoleForm() {
    const connectionSelect = document.getElementById('role-connection');
    const modelSelect = document.getElementById('role-model');
    if (!connectionSelect || !modelSelect || !modelSettingsSnapshot) return;
    const currentRole = document.getElementById('role-name').value;
    const selected = modelSettingsSnapshot.roles?.[currentRole];
    const availableConnections = modelSettingsSnapshot.connections || [];
    AuraSafe.clear(connectionSelect);
    const placeholder = AuraSafe.element('option', null, 'Choose a named connection');
    placeholder.value = '';
    connectionSelect.appendChild(placeholder);
    availableConnections.forEach((connection) => {
        const option = AuraSafe.element('option', null, `${connection.name} · ${connection.provider_type === 'ollama' ? 'Ollama' : 'OpenAI-compatible'}`);
        option.value = connection.id;
        option.selected = selected?.connection_id === connection.id;
        connectionSelect.appendChild(option);
    });
    if (selected?.connection_id && !selected.available) {
        const option = AuraSafe.element('option', null, `${selected.connection_name} · unavailable`);
        option.value = selected.connection_id;
        option.selected = true;
        option.disabled = true;
        connectionSelect.appendChild(option);
    }
    const models = modelModels.get(connectionSelect.value) || [];
    renderRoleModelOptions(models, selected);
    document.getElementById('role-model-manual').value = '';
}

function renderRoleModelOptions(models, selected = null) {
    const select = document.getElementById('role-model');
    AuraSafe.clear(select);
    const placeholder = AuraSafe.element('option', null, models.length ? 'Choose a discovered model' : 'Discover models or enter an ID below');
    placeholder.value = '';
    select.appendChild(placeholder);
    models.forEach((model) => {
        const option = AuraSafe.element('option', null, model.display_name && model.display_name !== model.id
            ? `${model.display_name} · ${model.id}`
            : model.id);
        option.value = model.id;
        option.selected = selected?.model_id === model.id;
        select.appendChild(option);
    });
}

function bindModelSettings() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;
    modal.addEventListener('click', async (event) => {
        const origin = event.target;
        const target = origin instanceof Element ? origin.closest('[data-settings-tab], [data-action]') : null;
        if (!target) return;
        if (target.dataset.settingsTab) {
            showSettingsTab(target.dataset.settingsTab);
            return;
        }
        const id = target.dataset.connectionId;
        if (target.dataset.action === 'add-connection') openConnectionEditor();
        if (target.dataset.action === 'cancel-connection') closeConnectionEditor();
        if (target.dataset.action === 'test-connection') await testModelConnection(id);
        if (target.dataset.action === 'discover-models') await discoverModels(id);
        if (target.dataset.action === 'edit-connection') openConnectionEditor(id);
        if (target.dataset.action === 'remove-connection') await removeConnection(id);
        if (target.dataset.action === 'remove-credential') await removeCredential(id);
    });
    modal.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        const controls = [...modal.querySelectorAll('button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')]
            .filter((element) => !element.hidden && element.getClientRects().length > 0);
        if (!controls.length) return;
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });
    document.getElementById('connection-form').addEventListener('submit', saveConnection);
    document.getElementById('role-form').addEventListener('submit', saveModelRole);
    document.getElementById('role-name').addEventListener('change', populateRoleForm);
    document.getElementById('role-connection').addEventListener('change', () => renderRoleModelOptions(modelModels.get(document.getElementById('role-connection').value) || []));
    document.getElementById('clear-role').addEventListener('click', clearModelRole);
    document.getElementById('check-capabilities').addEventListener('click', checkModelCapabilities);
    document.getElementById('local-only-toggle').addEventListener('change', changeLocalOnly);
    document.getElementById('connection-provider').addEventListener('change', updateConnectionEditorFields);
}

function openConnectionEditor(connectionId = '') {
    const form = document.getElementById('connection-form');
    const connection = modelSettingsSnapshot?.connections?.find((item) => item.id === connectionId);
    form.reset();
    document.getElementById('connection-id').value = connection?.id || '';
    document.getElementById('connection-form-title').textContent = connection ? 'Edit connection' : 'Add a connection';
    document.getElementById('connection-provider').disabled = Boolean(connection);
    document.getElementById('connection-provider').value = connection?.provider_type || 'ollama';
    document.getElementById('connection-name').value = connection?.name || '';
    document.getElementById('connection-url').value = connection?.base_url || (connection ? '' : 'http://127.0.0.1:11434');
    document.getElementById('token-parameter').value = connection?.token_limit_parameter || 'max_tokens';
    document.getElementById('credential-state').textContent = connection?.has_api_key ? '(a key is stored; value hidden)' : '(optional)';
    updateConnectionEditorFields();
    form.hidden = false;
    document.getElementById('connection-name').focus();
}

function closeConnectionEditor() {
    const form = document.getElementById('connection-form');
    form.reset();
    form.hidden = true;
    document.getElementById('connection-provider').disabled = false;
}

function updateConnectionEditorFields() {
    const provider = document.getElementById('connection-provider').value;
    document.getElementById('token-parameter-wrap').hidden = provider !== 'openai_compatible';
    document.getElementById('credential-field').hidden = provider !== 'openai_compatible';
    const url = document.getElementById('connection-url');
    if (provider === 'ollama' && !url.value) url.value = 'http://127.0.0.1:11434';
    if (provider === 'openai_compatible' && url.value === 'http://127.0.0.1:11434') url.value = '';
}

async function saveConnection(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const id = document.getElementById('connection-id').value;
    const provider = document.getElementById('connection-provider').value;
    const keyInput = document.getElementById('connection-key');
    const apiKey = keyInput.value;
    const payload = {
        name: document.getElementById('connection-name').value.trim(),
        base_url: document.getElementById('connection-url').value.trim(),
    };
    if (!id) {
        payload.provider_type = provider;
        payload.token_limit_parameter = document.getElementById('token-parameter').value;
    } else if (provider === 'openai_compatible') {
        payload.token_limit_parameter = document.getElementById('token-parameter').value;
    }
    try {
        const connection = await apiJson(id
            ? `${API_URL}/settings/models/connections/${encodeURIComponent(id)}`
            : `${API_URL}/settings/models/connections`, {
                method: id ? 'PATCH' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        if (apiKey) {
            await apiJson(`${API_URL}/settings/models/connections/${encodeURIComponent(connection.id)}/credential`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: apiKey }),
            });
        }
        showToast('Connection saved');
        closeConnectionEditor();
        await loadModelSettings();
    } catch (error) {
        showToast(error.message || 'Connection could not be saved', 'error');
    } finally {
        keyInput.value = '';
    }
}

async function testModelConnection(connectionId) {
    try {
        const result = await apiJson(`${API_URL}/settings/models/connections/${encodeURIComponent(connectionId)}/test`, { method: 'POST' });
        const latency = Number.isFinite(result.latency_ms) ? ` · ${result.latency_ms} ms` : '';
        const label = result.status === 'connected' ? `Connected${latency}` : modelTestLabel(result);
        modelTestResults.set(connectionId, label);
        renderConnectionList();
        const focus = document.querySelector(`[data-connection-id="${CSS.escape(connectionId)}"][data-action="test-connection"]`);
        if (focus) focus.focus();
    } catch (error) {
        modelTestResults.set(connectionId, modelTestLabel({ message: error.message }));
        renderConnectionList();
    }
}

function modelTestLabel(result) {
    const message = String(result.message || 'Connection unavailable');
    if (result.status === 'blocked_by_local_only' || result.error_code === 'local_only_blocked' || /local only|cloud model requests are disabled/i.test(message)) {
        return 'Blocked by Local only · turn it off to allow remote requests';
    }
    if (result.status === 'authentication_failed' || result.error_code === 'authentication_failed') return 'Authentication failed · check the saved key';
    if (result.status === 'needs_credential_reentry') return 'Needs credential re-entry';
    return message;
}

async function discoverModels(connectionId) {
    try {
        const result = await apiJson(`${API_URL}/settings/models/connections/${encodeURIComponent(connectionId)}/models`);
        modelModels.set(connectionId, result.models || []);
        renderRoleModelOptions(modelModels.get(connectionId), modelSettingsSnapshot?.roles?.[document.getElementById('role-name').value]);
        showToast(`${result.models?.length || 0} models discovered`);
    } catch (error) {
        const isLocalOnly = /local only|cloud model requests are disabled/i.test(error.message);
        modelTestResults.set(connectionId, isLocalOnly
            ? 'Blocked by Local only · turn it off to allow remote requests'
            : modelTestLabel({ message: error.message }));
        renderConnectionList();
    }
}

async function saveModelRole(event) {
    event.preventDefault();
    const role = document.getElementById('role-name').value;
    const connectionId = document.getElementById('role-connection').value;
    const modelId = document.getElementById('role-model-manual').value.trim()
        || document.getElementById('role-model').value;
    if (!connectionId || !modelId) {
        showToast('Choose a connection and an exact model ID', 'error');
        return;
    }
    try {
        await apiJson(`${API_URL}/settings/models/roles/${role}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ connection_id: connectionId, model_id: modelId }),
        });
        await loadModelSettings();
        showToast(`${role[0].toUpperCase() + role.slice(1)} model saved`);
    } catch (error) {
        showToast(error.message || 'Model role could not be saved', 'error');
    }
}

async function clearModelRole() {
    const role = document.getElementById('role-name').value;
    try {
        await apiJson(`${API_URL}/settings/models/roles/${role}`, { method: 'DELETE' });
        await loadModelSettings();
        showToast(`${role[0].toUpperCase() + role.slice(1)} role cleared`);
    } catch (error) {
        showToast(error.message || 'Model role could not be cleared', 'error');
    }
}

async function checkModelCapabilities() {
    const connectionId = document.getElementById('role-connection').value;
    const modelId = document.getElementById('role-model-manual').value.trim()
        || document.getElementById('role-model').value;
    const panel = document.getElementById('capability-panel');
    if (!connectionId || !modelId) {
        panel.textContent = 'Choose a connection and model before checking capabilities.';
        return;
    }
    panel.textContent = 'Checking capabilities…';
    try {
        const data = await apiJson(`${API_URL}/settings/models/connections/${encodeURIComponent(connectionId)}/models/${encodeURIComponent(modelId)}/capabilities`);
        AuraSafe.clear(panel);
        ['tools', 'json_mode', 'vision', 'streaming', 'embeddings'].forEach((name) => {
            const capability = data[name] || { state: 'unknown', source: 'unknown' };
            const row = AuraSafe.element('p', 'capability-row');
            row.append(
                AuraSafe.element('span', 'capability-name', name.replace('_', ' ')),
                AuraSafe.element('span', `capability-state state-${capability.state}`, capability.state),
                AuraSafe.element('span', 'capability-source', capability.source === 'controlled_probe' ? 'controlled probe' : capability.source === 'provider_metadata' ? 'provider metadata' : 'unknown')
            );
            panel.appendChild(row);
        });
    } catch (error) {
        panel.textContent = modelTestLabel({ message: error.message });
    }
}

async function removeConnection(connectionId) {
    if (!window.confirm('Remove this connection? Existing model roles will stay visible as unavailable.')) return;
    try {
        await apiJson(`${API_URL}/settings/models/connections/${encodeURIComponent(connectionId)}`, { method: 'DELETE' });
        await loadModelSettings();
        showToast('Connection removed. Existing roles remain unavailable.');
    } catch (error) {
        showToast(error.message || 'Connection could not be removed', 'error');
    }
}

async function removeCredential(connectionId) {
    if (!window.confirm('Remove the stored API key for this connection?')) return;
    try {
        await apiJson(`${API_URL}/settings/models/connections/${encodeURIComponent(connectionId)}/credential`, { method: 'DELETE' });
        await loadModelSettings();
        showToast('Stored key removed');
    } catch (error) {
        showToast(error.message || 'Stored key could not be removed', 'error');
    }
}

async function changeLocalOnly(event) {
    const toggle = event.currentTarget;
    const enabled = toggle.checked;
    if (!enabled && !window.confirm('Cloud requests can send the current message to a remote provider. Chat history, tasks, files and profile details are not sent. Continue?')) {
        toggle.checked = true;
        return;
    }
    try {
        await apiJson(`${API_URL}/settings/models/local-only`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        if (modelSettingsSnapshot) modelSettingsSnapshot.local_only = enabled;
        document.getElementById('local-only-state').textContent = enabled
            ? 'On · cloud requests are blocked'
            : 'Off · messages may leave this device';
    } catch (error) {
        toggle.checked = !enabled;
        showToast(error.message || 'Privacy setting could not be saved', 'error');
    }
}
