/**
 * LoL Stats — Application Router & Shell
 * Hash-based SPA router with global state management.
 */

const App = {
    // ── Global State ──────────────────────────────────────
    state: {
        currentSummoner: null,  // { puuid, game_name, tag_line, region, ... }
        matchList: [],          // Cached match summaries
        matchPage: 1,
        hasMoreMatches: false,
        strategyData: null,     // Full strategy.json data
        champions: [],          // Champion name list for autocomplete
    },

    // ── Identity (the configured summoner — this is a personal dashboard) ──
    identity: {
        STORAGE_KEY: 'lol_stats_identity',
        defaults: {
            region: 'eun1',
            game_name: 'Aegiron',
            tag_line: '1309',
        },
        get() {
            try {
                const saved = JSON.parse(localStorage.getItem(this.STORAGE_KEY) || 'null');
                return { ...this.defaults, ...(saved || {}) };
            } catch (_) {
                return { ...this.defaults };
            }
        },
        set(identity) {
            const merged = { ...this.defaults, ...identity };
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(merged));
            return merged;
        },
    },

    // ── Router ────────────────────────────────────────────
    routes: {
        'home':     { render: renderHomePage,     title: 'Overview' },
        'match':    { render: renderMatchDetail,  title: 'Match Detail' },
        'strategy': { render: renderStrategyPage, title: 'Strategy' },
        'settings': { render: renderSettingsPage, title: 'Settings' },
    },

    navigate(hash) {
        const page = hash.replace(/^#\//, '') || 'home';
        window.location.hash = `#/${page}`;
    },

    async route() {
        const hash = window.location.hash || '#/home';
        const [path, ...args] = hash.replace(/^#\//, '').split('/');
        const page = path || 'home';
        const main = document.getElementById('main-content');
        const loader = document.getElementById('loading-block');

        // Toggle per-page layout mode on the main container.
        main.classList.remove('strategy-view');

        // Update sidebar nav active state
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === page || item.dataset.page === path);
        });

        // Show loading
        if (loader) loader.style.display = 'flex';

        try {
            const route = this.routes[page];
            if (route) {
                document.title = `LoL Stats — ${route.title}`;
                if (page === 'strategy') main.classList.add('strategy-view');
                await route.render(main, args);
            } else if (page === 'match') {
                document.title = 'LoL Stats — Match Detail';
                await renderMatchDetail(main, args);
            } else {
                main.innerHTML = `<div class="empty-block">
                    <div class="empty-label">Page not found</div>
                    <div class="empty-action">The page you're looking for doesn't exist.</div>
                </div>`;
            }
        } catch (err) {
            console.error('Route error:', err);
            main.innerHTML = `<div class="empty-block">
                <div class="empty-label">Something went wrong</div>
                <div class="empty-action">${escapeHtml(err.message)}</div>
            </div>`;
        } finally {
            if (loader) loader.style.display = 'none';
        }
    },

    // ── Toast Notifications ───────────────────────────────
    toast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    // ── Health Check ──────────────────────────────────────
    async checkHealth() {
        const dot = document.getElementById('status-dot');
        const label = document.getElementById('status-label');
        try {
            const health = await api.checkHealth();
            if (health && health.status === 'ok') {
                dot.className = 'status-dot online';
                dot.title = 'Backend online';
                if (label) label.textContent = 'Connected';
                return true;
            }
        } catch (_) { /* offline */ }
        dot.className = 'status-dot offline';
        dot.title = 'Backend offline — start the server';
        if (label) label.textContent = 'Offline';
        return false;
    },

    // ── Preload Summoner ──────────────────────────────────
    async preloadSummoner() {
        if (App.state.currentSummoner) return App.state.currentSummoner;
        const id = App.identity.get();
        if (!id.game_name || !id.tag_line) return null;
        try {
            const summoner = await api.lookupSummoner(id.region, id.game_name, id.tag_line);
            App.state.currentSummoner = summoner;
            return summoner;
        } catch (_) {
            return null; // pages handle the missing-summoner state gracefully
        }
    },

    // ── Init ──────────────────────────────────────────────
    async init() {
        // Redirect legacy hashes → #/home
        const legacy = (window.location.hash || '').replace(/^#\//, '');
        if (legacy === 'search' || legacy === 'matches') {
            window.location.hash = '#/home';
        }

        // Listen for hash changes
        window.addEventListener('hashchange', () => this.route());

        // Sidebar nav click handler — updates hash
        document.getElementById('sidebar-nav').addEventListener('click', (e) => {
            const item = e.target.closest('.nav-item');
            if (item) {
                const page = item.dataset.page;
                if (page) this.navigate(page);
            }
        });

        // Health check every 30s
        this.checkHealth();
        setInterval(() => this.checkHealth(), 30000);

        // Warm the summoner into state so other pages have it immediately
        this.preloadSummoner();

        // Initial route
        await this.route();
    },
};


// ── Utility Functions ─────────────────────────────────────

/**
 * Format seconds into MM:SS or HH:MM:SS.
 */
function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '0:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * Format epoch ms into relative time string.
 */
function timeAgo(epochMs) {
    if (!epochMs) return '';
    const diff = Date.now() - epochMs;
    const mins = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (mins > 0) return `${mins}m ago`;
    return 'just now';
}

/**
 * Format epoch ms into a date string.
 */
function formatDate(epochMs) {
    if (!epochMs) return '';
    return new Date(epochMs).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
    });
}

/**
 * Calculate KDA ratio.
 */
function kdaRatio(k, d, a) {
    if (d === 0) return (k + a).toFixed(1);
    return ((k + a) / d).toFixed(2);
}

/**
 * HTML-escape a string.
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Get queue name from queue ID.
 */
function queueName(queueId) {
    const names = {
        400: 'Normal Draft', 420: 'Ranked Solo', 430: 'Normal Blind',
        440: 'Ranked Flex', 450: 'ARAM', 700: 'Clash',
        1700: 'Arena', 1900: 'URF',
    };
    return names[queueId] || `Queue ${queueId}`;
}


// ── Bootstrap ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => App.init());
