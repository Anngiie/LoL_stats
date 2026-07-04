/**
 * LoL Stats — Settings Page
 * Global preferences for the overlay and app.
 */

async function renderSettingsPage(container) {
    const identity = App.identity.get();

    // Load current strategy to get global prefs
    let prefs = {
        overlay_always_visible: true,
        overlay_auto_show_loading_screen: true,
        overlay_show_duration_seconds: 15,
        overlay_opacity: 0.85,
        overlay_font_size: 14,
        overlay_font_family: 'JetBrains Mono',
        overlay_width: 500,
        overlay_x: 20,
        overlay_y: 60,
    };

    try {
        const strategy = await api.getStrategy();
        if (strategy && strategy.global_preferences) {
            prefs = { ...prefs, ...strategy.global_preferences };
        }
    } catch (_) { /* use defaults */ }

    container.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Settings</h1>
            <p class="page-subtitle">Configure your summoner identity, overlay, and backend.</p>
        </div>

        <div class="settings-grid">
            <div class="card">
                <div class="card-header">Summoner Identity</div>
                <form id="identity-form">
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label" for="id-region">Region</label>
                        <select class="form-select" id="id-region">
                            <option value="euw1" ${identity.region === 'euw1' ? 'selected' : ''}>EUW</option>
                            <option value="eun1" ${identity.region === 'eun1' ? 'selected' : ''}>EUNE</option>
                            <option value="na1"  ${identity.region === 'na1'  ? 'selected' : ''}>NA</option>
                            <option value="kr"   ${identity.region === 'kr'   ? 'selected' : ''}>Korea</option>
                            <option value="br1"  ${identity.region === 'br1'  ? 'selected' : ''}>Brazil</option>
                            <option value="jp1"  ${identity.region === 'jp1'  ? 'selected' : ''}>Japan</option>
                            <option value="oc1"  ${identity.region === 'oc1'  ? 'selected' : ''}>Oceania</option>
                            <option value="tr1"  ${identity.region === 'tr1'  ? 'selected' : ''}>Turkey</option>
                            <option value="ru"   ${identity.region === 'ru'   ? 'selected' : ''}>Russia</option>
                            <option value="la1"  ${identity.region === 'la1'  ? 'selected' : ''}>LAN</option>
                            <option value="la2"  ${identity.region === 'la2'  ? 'selected' : ''}>LAS</option>
                        </select>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label" for="id-name">Game Name</label>
                        <input class="form-input" id="id-name" value="${escapeHtml(identity.game_name)}" autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="id-tag">Tag Line</label>
                        <input class="form-input" id="id-tag" value="${escapeHtml(identity.tag_line)}" autocomplete="off">
                    </div>
                </div>
                <button type="submit" class="btn btn-primary">Save Identity</button>
                <span class="form-hint">This is the summoner the dashboard loads automatically on Home.</span>
            </form>
        </div>

        <div class="card">
            <div class="card-header">Overlay Settings</div>
            <form id="settings-form">
                <div class="form-group">
                    <label class="form-label">
                        <input type="checkbox" id="always-visible" ${prefs.overlay_always_visible !== false ? 'checked' : ''}>
                        Always visible during game (don't fade out)
                    </label>
                </div>

                <div class="form-group">
                    <label class="form-label">
                        <input type="checkbox" id="auto-show" ${prefs.overlay_auto_show_loading_screen ? 'checked' : ''}>
                        Auto-show overlay during loading screen
                    </label>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label" for="show-duration">Show duration (seconds)</label>
                        <input class="form-input" type="number" id="show-duration"
                               value="${prefs.overlay_show_duration_seconds}" min="5" max="120">
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="overlay-opacity">Overlay opacity</label>
                        <input class="form-input" type="number" id="overlay-opacity"
                               value="${prefs.overlay_opacity}" min="0.1" max="1.0" step="0.05">
                    </div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label" for="font-size">Font size</label>
                        <input class="form-input" type="number" id="font-size"
                               value="${prefs.overlay_font_size}" min="8" max="32">
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="font-family">Font family</label>
                        <select class="form-select" id="font-family">
                            <option ${prefs.overlay_font_family === 'JetBrains Mono' ? 'selected' : ''}>JetBrains Mono</option>
                            <option ${prefs.overlay_font_family === 'Martian Mono' ? 'selected' : ''}>Martian Mono</option>
                            <option ${prefs.overlay_font_family === 'Segoe UI' ? 'selected' : ''}>Segoe UI</option>
                            <option ${prefs.overlay_font_family === 'Consolas' ? 'selected' : ''}>Consolas</option>
                            <option ${prefs.overlay_font_family === 'Arial' ? 'selected' : ''}>Arial</option>
                            <option ${prefs.overlay_font_family === 'Georgia' ? 'selected' : ''}>Georgia</option>
                        </select>
                    </div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label" for="overlay-width">Overlay width (px)</label>
                        <input class="form-input" type="number" id="overlay-width"
                               value="${prefs.overlay_width}" min="200" max="1000">
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="overlay-x">Screen X position</label>
                        <input class="form-input" type="number" id="overlay-x"
                               value="${prefs.overlay_x}" min="0" max="3000">
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="overlay-y">Screen Y position</label>
                        <input class="form-input" type="number" id="overlay-y"
                               value="${prefs.overlay_y}" min="0" max="3000">
                    </div>
                </div>

                <button type="submit" class="btn btn-primary">Save Settings</button>
            </form>
        </div>

        <div class="card">
            <div class="card-header">Backend</div>
            <div id="backend-info" style="color:var(--text-secondary);font-size:0.9rem;">
                Checking backend...
            </div>
        </div>
        </div>
    `;

    // Check backend health
    try {
        const health = await api.checkHealth();
        const info = document.getElementById('backend-info');
        if (health && health.status === 'ok') {
            info.innerHTML = `
                <p>Backend online <span style="color:var(--text-muted);">(v${health.version || '0.1.0'})</span></p>
                <p>Riot API key: <span style="color:${health.riot_api_key_configured ? 'var(--win)' : 'var(--loss)'};font-weight:700;">${health.riot_api_key_configured ? 'Configured' : 'Not configured'}</span></p>
                <p>Database: <span style="color:${health.database_ok ? 'var(--win)' : 'var(--loss)'};font-weight:700;">${health.database_ok ? 'OK' : 'Error'}</span></p>
                <p>Strategy file: <span style="color:${health.strategy_file_ok ? 'var(--win)' : 'var(--loss)'};font-weight:700;">${health.strategy_file_ok ? 'Found' : 'Missing'}</span></p>
                <p>Live client: <span style="color:${health.live_client_reachable ? 'var(--win)' : 'var(--loss)'};font-weight:700;">${health.live_client_reachable ? 'Connected' : 'Not reachable'}</span></p>
            `;
        }
    } catch (_) { /* ignore */ }

    // Identity form submit
    const identityForm = document.getElementById('identity-form');
    if (identityForm) {
        identityForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const next = {
                region: document.getElementById('id-region').value,
                game_name: document.getElementById('id-name').value.trim(),
                tag_line: document.getElementById('id-tag').value.trim().replace(/^#/, ''),
            };
            if (!next.game_name || !next.tag_line) {
                App.toast('Game name and tag line are required.', 'error');
                return;
            }
            App.identity.set(next);
            App.state.currentSummoner = null;
            App.toast('Identity saved. Reloading...', 'success');
            setTimeout(() => App.navigate('home'), 600);
        });
    }

    // Overlay settings form submit
    const settingsForm = document.getElementById('settings-form');
    if (settingsForm) {
        settingsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const global_preferences = {
            overlay_always_visible: document.getElementById('always-visible').checked,
            overlay_auto_show_loading_screen: document.getElementById('auto-show').checked,
            overlay_show_duration_seconds: parseInt(document.getElementById('show-duration').value) || 15,
            overlay_opacity: parseFloat(document.getElementById('overlay-opacity').value) || 0.85,
            overlay_font_size: parseInt(document.getElementById('font-size').value) || 14,
            overlay_font_family: document.getElementById('font-family').value,
            overlay_width: parseInt(document.getElementById('overlay-width').value) || 500,
            overlay_x: parseInt(document.getElementById('overlay-x').value) || 20,
            overlay_y: parseInt(document.getElementById('overlay-y').value) || 60,
        };

        try {
            await fetch('/api/v1/strategy/global-preferences', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(global_preferences),
            });
            App.toast('Settings saved! Restart the overlay to apply changes.', 'success');
        } catch (err) {
            App.toast('Failed to save settings: ' + err.message, 'error');
        }
    });
    }
}
