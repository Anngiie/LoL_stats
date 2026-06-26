/**
 * LoL Stats — Strategy Editor
 * 3-context champion notes: vs enemy support / with your jungler / with your ADC.
 * Imported from the Coach K Excel guide; fully editable; feeds the live overlay.
 */

const CONTEXTS = {
    vs_support: {
        label: 'vs Enemy Support',
        icon: '⚔️',
        fields: [
            { key: 'early_strength', type: 'select', options: ['', 'Weak', 'Average', 'Strong', 'Depends'], label: 'Early Strength' },
            { key: 'strengths',      type: 'list',   label: 'Strengths (be careful)' },
            { key: 'weaknesses',     type: 'list',   label: 'Weaknesses (play around)' },
            { key: 'counters',       type: 'list',   label: 'Support Counters' },
            { key: 'how_to_play',    type: 'list',   label: 'How to Play vs Them' },
            { key: 'more_info',      type: 'text',   label: 'More Info' },
        ],
    },
    with_jungler: {
        label: 'With Jungler',
        icon: '🌲',
        fields: [
            { key: 'early',          type: 'select', options: ['', 'Weak', 'Average', 'Strong'], label: 'Early' },
            { key: 'pathing',        type: 'text', label: 'Pathing' },
            { key: 'synergy',        type: 'text', label: 'Synergy' },
            { key: 'best_supports',  type: 'list', label: 'Best Supports' },
            { key: 'vision_level1',  type: 'text', label: 'Vision / Cover L1' },
            { key: 'gameplan',       type: 'text', label: 'Gameplan' },
            { key: 'important_info', type: 'text', label: 'Important Info' },
        ],
    },
    with_adc: {
        label: 'With ADC',
        icon: '🏹',
        fields: [
            { key: 'strength',       type: 'select', options: ['', 'Weak', 'Strong', 'Depends'], label: 'Strength' },
            { key: 'synergy',        type: 'text', label: 'Synergy' },
            { key: 'best_supports',  type: 'list', label: 'Best Supports' },
            { key: 'gameplan',       type: 'text', label: 'Gameplan' },
            { key: 'how_to_trade',   type: 'text', label: 'How to Trade' },
            { key: 'when_to_roam',   type: 'text', label: 'When to Roam' },
        ],
    },
};
const CONTEXT_ORDER = ['vs_support', 'with_jungler', 'with_adc'];

const strategyState = {
    data: null,
    activeContext: 'vs_support',
    selectedChampion: null,
    search: '',
};

async function renderStrategyPage(container) {
    container.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <h1 class="page-title">📝 Strategy Editor</h1>
                <p class="page-subtitle">Champion notes per context — these feed your in-game overlay.</p>
            </div>
            <div style="display:flex;gap:8px;">
                <button class="btn btn-sm" id="add-champion-btn">➕ Add Champion</button>
            </div>
        </div>

        <div id="strategy-content">
            <div class="loading-block"><div class="spinner"></div><span>Loading strategy data...</span></div>
        </div>
    `;

    await reloadStrategy();
    renderStrategyContent();

    document.getElementById('add-champion-btn').addEventListener('click', addChampion);
}

async function reloadStrategy() {
    try {
        strategyState.data = await api.getStrategy();
        App.state.strategyData = strategyState.data;
    } catch (err) {
        console.error('Failed to load strategy:', err);
        App.toast('Failed to load strategy data.', 'error');
    }
}

function renderStrategyContent() {
    const content = document.getElementById('strategy-content');
    if (!content) return;

    const data = strategyState.data;
    if (!data || !data.champions) {
        content.innerHTML = `<div class="empty-block">
            <div class="empty-label">No strategy data found</div>
            <div class="empty-action">Click "Add Champion" to create your first note.</div>
        </div>`;
        return;
    }

    // Context tab bar with counts
    const tabs = CONTEXT_ORDER.map(ctx => {
        const count = countChampsForContext(ctx);
        const active = ctx === strategyState.activeContext ? 'active' : '';
        return `<button class="tab-btn ${active}" data-context="${ctx}">
            ${CONTEXTS[ctx].icon} ${CONTEXTS[ctx].label} <span class="faint">(${count})</span>
        </button>`;
    }).join('');

    content.innerHTML = `
        <div class="tab-bar" id="context-tabs">${tabs}</div>
        <div class="strategy-layout">
            <div class="champion-sidebar" id="champion-sidebar"></div>
            <div class="champion-editor" id="champion-editor"></div>
        </div>
    `;

    document.getElementById('context-tabs').addEventListener('click', (e) => {
        const btn = e.target.closest('.tab-btn');
        if (!btn) return;
        strategyState.activeContext = btn.dataset.context;
        renderStrategyContent();
    });

    renderChampionSidebar();
    renderChampionEditor();
}

function countChampsForContext(ctx) {
    const champs = strategyState.data?.champions || {};
    return Object.values(champs).filter(c => hasContextData(c, ctx)).length;
}

function hasContextData(champ, ctx) {
    const block = champ?.[ctx] || {};
    return Object.keys(block).length > 0;
}

function renderChampionSidebar() {
    const sidebar = document.getElementById('champion-sidebar');
    if (!sidebar) return;

    const ctx = strategyState.activeContext;
    const champs = strategyState.data?.champions || {};
    const search = (strategyState.search || '').toLowerCase();

    let names = Object.keys(champs).filter(name => {
        // Show champs with data in this context, OR the currently selected champ.
        return hasContextData(champs[name], ctx) || name === strategyState.selectedChampion;
    });
    if (search) names = names.filter(n => n.toLowerCase().includes(search));
    names.sort((a, b) => a.localeCompare(b));

    // Auto-select first if none or selection invalid for this context.
    if (names.length && (!strategyState.selectedChampion || !names.includes(strategyState.selectedChampion))) {
        strategyState.selectedChampion = names[0];
    }

    sidebar.innerHTML = `
        <div class="champion-sidebar-header">${CONTEXTS[ctx].label}</div>
        <input class="champion-search-input" id="champ-search"
               placeholder="Search..." value="${escapeHtml(strategyState.search)}">
        <div id="champ-list">
            ${names.length ? names.map(name => {
                const isHigh = champs[name]?.overlay_priority === 'high';
                const active = name === strategyState.selectedChampion ? 'active' : '';
                return `<div class="champ-item ${active}" data-champion="${escapeHtml(name)}">
                    <span>${escapeHtml(name)}</span>
                    ${isHigh ? '<span class="priority-star">⭐</span>' : ''}
                </div>`;
            }).join('') : '<div style="padding:12px 16px;color:var(--faint);font-size:0.82rem;">No champions yet.</div>'}
        </div>
    `;

    document.getElementById('champ-search').addEventListener('input', (e) => {
        strategyState.search = e.target.value;
        renderChampionSidebar();
        document.getElementById('champ-search').focus();
    });

    sidebar.querySelectorAll('.champ-item').forEach(el => {
        el.addEventListener('click', () => {
            strategyState.selectedChampion = el.dataset.champion;
            renderChampionSidebar();
            renderChampionEditor();
        });
    });
}

function renderChampionEditor() {
    const editor = document.getElementById('champion-editor');
    if (!editor) return;

    const name = strategyState.selectedChampion;
    const champ = name && (strategyState.data?.champions?.[name]);
    if (!name || !champ) {
        editor.innerHTML = `<p class="muted" style="padding:20px;">Select a champion on the left, or add a new one.</p>`;
        return;
    }

    const ctx = strategyState.activeContext;
    const ctxDef = CONTEXTS[ctx];
    const block = champ[ctx] || {};

    editor.innerHTML = `
        <div class="editor-title">
            <h2>${ctxDef.icon} ${escapeHtml(name)}</h2>
            <span class="faint" style="font-size:0.8rem;">${ctxDef.label}</span>
            <button class="btn btn-sm btn-danger" id="delete-champ-btn" style="margin-left:auto;">🗑 Delete</button>
        </div>

        <div class="form-row" style="margin-bottom:16px;">
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label" for="priority-select">Overlay Priority</label>
                <select class="form-select" id="priority-select" style="width:auto;">
                    <option value="high"   ${champ.overlay_priority === 'high' ? 'selected' : ''}>⭐ High — always show</option>
                    <option value="normal" ${champ.overlay_priority === 'normal' ? 'selected' : ''}>Normal</option>
                    <option value="low"    ${champ.overlay_priority === 'low' ? 'selected' : ''}>Low — only if room</option>
                </select>
            </div>
        </div>

        <div id="context-fields"></div>

        <div class="card" style="margin-top:16px;background:var(--bg-deep);">
            <div class="card-header">🗒️ Personal Notes (shared across contexts)</div>
            <textarea class="form-textarea" id="personal-notes" placeholder="Your own notes for ${escapeHtml(name)}..."
                      style="min-height:90px;">${escapeHtml(champ.personal_notes || '')}</textarea>
            <p class="form-hint" id="notes-save">Auto-saved</p>
        </div>
    `;

    // Render context fields
    const fieldsHost = document.getElementById('context-fields');
    fieldsHost.innerHTML = ctxDef.fields.map(f => renderField(f, block[f.key])).join('');
    attachFieldHandlers(fieldsHost, name, ctx, ctxDef, block);

    // Priority
    document.getElementById('priority-select').addEventListener('change', async (e) => {
        try {
            await api.updateChampionStrategy(name, { overlay_priority: e.target.value });
            champ.overlay_priority = e.target.value;
            App.toast('Priority updated.', 'success');
            renderChampionSidebar();
        } catch (err) { App.toast('Save failed: ' + err.message, 'error'); }
    });

    // Delete
    document.getElementById('delete-champ-btn').addEventListener('click', async () => {
        if (!confirm(`Delete all strategy notes for ${name}?`)) return;
        try {
            await api.deleteChampionStrategy(name);
            App.toast(`Deleted ${name}.`, 'success');
            strategyState.selectedChampion = null;
            await reloadStrategy();
            renderStrategyContent();
        } catch (err) { App.toast('Delete failed: ' + err.message, 'error'); }
    });

    // Personal notes — debounced autosave
    let notesTimer = null;
    document.getElementById('personal-notes').addEventListener('input', (e) => {
        const indicator = document.getElementById('notes-save');
        indicator.textContent = 'Unsaved changes...';
        if (notesTimer) clearTimeout(notesTimer);
        notesTimer = setTimeout(async () => {
            try {
                await api.updateChampionStrategy(name, { personal_notes: e.target.value });
                champ.personal_notes = e.target.value;
                indicator.textContent = 'Auto-saved ✓';
            } catch (err) { indicator.textContent = 'Save failed'; }
        }, 700);
    });
}

// ── Field rendering ───────────────────────────────────────────
function renderField(field, value) {
    const lbl = `<label class="form-label">${escapeHtml(field.label)}</label>`;
    if (field.type === 'select') {
        const opts = field.options.map(o =>
            `<option value="${escapeHtml(o)}" ${value === o ? 'selected' : ''}>${o || '—'}</option>`
        ).join('');
        return `<div class="form-group">
            ${lbl}
            <select class="form-select" data-field="${field.key}" data-type="select" style="max-width:220px;">${opts}</select>
        </div>`;
    }
    if (field.type === 'text') {
        return `<div class="form-group">
            ${lbl}
            <textarea class="form-textarea" data-field="${field.key}" data-type="text"
                      placeholder="${escapeHtml(field.label)}..."
                      style="min-height:64px;">${escapeHtml(value || '')}</textarea>
        </div>`;
    }
    // list
    const items = Array.isArray(value) ? value : [];
    return `<div class="form-group">
        ${lbl}
        <div class="tip-input-row">
            <input class="form-input list-add-input" placeholder="Add ${escapeHtml(field.label)}..." data-field="${field.key}">
            <button class="btn btn-primary btn-sm list-add-btn" data-field="${field.key}">+ Add</button>
        </div>
        <ul class="tip-list" data-list="${field.key}">
            ${items.length ? items.map((it, i) => `
                <li class="tip-row">
                    <span class="tip-index">${i + 1}.</span>
                    <span class="tip-text">${escapeHtml(it)}</span>
                    <button class="tip-remove" data-field="${field.key}" data-index="${i}" title="Remove">✕</button>
                </li>`).join('') : '<li class="faint" style="padding:6px 0;font-size:0.82rem;">No entries yet.</li>'}
        </ul>
    </div>`;
}

function attachFieldHandlers(host, name, ctx, ctxDef, block) {
    // Ensure the block object exists on the champ entry locally.
    const champ = strategyState.data.champions[name];
    champ[ctx] = champ[ctx] || {};

    // Save the whole context block after any change.
    async function saveContext() {
        try {
            await api.updateChampionStrategy(name, { [ctx]: champ[ctx] });
        } catch (err) {
            App.toast('Save failed: ' + err.message, 'error');
        }
    }

    // selects + textareas (debounced for text)
    host.querySelectorAll('[data-type="select"]').forEach(el => {
        el.addEventListener('change', async () => {
            champ[ctx][el.dataset.field] = el.value;
            await saveContext();
        });
    });

    host.querySelectorAll('[data-type="text"]').forEach(el => {
        let t = null;
        el.addEventListener('input', () => {
            champ[ctx][el.dataset.field] = el.value;
            if (t) clearTimeout(t);
            t = setTimeout(saveContext, 700);
        });
    });

    // list add
    host.querySelectorAll('.list-add-btn').forEach(btn => {
        const field = btn.dataset.field;
        const input = host.querySelector(`.list-add-input[data-field="${field}"]`);
        const add = async () => {
            const v = input.value.trim();
            if (!v) return;
            champ[ctx][field] = [...(champ[ctx][field] || []), v];
            input.value = '';
            await saveContext();
            refreshList(host, field, champ[ctx][field]);
        };
        btn.addEventListener('click', add);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } });
    });

    // list remove
    host.querySelectorAll('.tip-remove').forEach(btn => {
        btn.addEventListener('click', async () => {
            const field = btn.dataset.field;
            const idx = parseInt(btn.dataset.index, 10);
            const arr = [...(champ[ctx][field] || [])];
            arr.splice(idx, 1);
            champ[ctx][field] = arr;
            await saveContext();
            refreshList(host, field, arr);
        });
    });
}

function refreshList(host, field, items) {
    const ul = host.querySelector(`.tip-list[data-list="${field}"]`);
    if (!ul) return;
    if (!items || !items.length) {
        ul.innerHTML = '<li class="faint" style="padding:6px 0;font-size:0.82rem;">No entries yet.</li>';
        return;
    }
    ul.innerHTML = items.map((it, i) => `
        <li class="tip-row">
            <span class="tip-index">${i + 1}.</span>
            <span class="tip-text">${escapeHtml(it)}</span>
            <button class="tip-remove" data-field="${field}" data-index="${i}" title="Remove">✕</button>
        </li>`).join('');
    // Rebind remove buttons for this list.
    ul.querySelectorAll('.tip-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            const name = strategyState.selectedChampion;
            const ctx = strategyState.activeContext;
            const champ = strategyState.data.champions[name];
            const arr = [...(champ[ctx][field] || [])];
            arr.splice(parseInt(btn.dataset.index, 10), 1);
            champ[ctx][field] = arr;
            api.updateChampionStrategy(name, { [ctx]: champ[ctx] })
                .then(() => refreshList(host, field, arr))
                .catch(err => App.toast('Save failed: ' + err.message, 'error'));
        });
    });
}

// ── Toolbar actions ───────────────────────────────────────────
async function addChampion() {
    const raw = prompt('Enter champion name (e.g. "Thresh"):');
    if (!raw || !raw.trim()) return;
    const name = raw.trim()[0].toUpperCase() + raw.trim().slice(1);
    try {
        await api.updateChampionStrategy(name, {});
        App.toast(`Added ${name}.`, 'success');
        strategyState.selectedChampion = name;
        await reloadStrategy();
        renderStrategyContent();
    } catch (err) {
        App.toast('Failed to add champion: ' + err.message, 'error');
    }
}
