/**
 * LoL Stats — API Client
 * Fetch wrapper for all backend REST endpoints.
 */

const API_BASE = window.location.origin + '/api/v1';

const api = {
    /**
     * Base fetch wrapper with error handling.
     * @param {string} path - URL path relative to API_BASE
     * @param {object} options - Fetch options
     * @returns {Promise<any>} Parsed JSON response
     */
    async _fetch(path, options = {}) {
        const url = `${API_BASE}${path}`;
        const defaults = {
            headers: { 'Content-Type': 'application/json' },
        };
        const merged = { ...defaults, ...options };
        if (merged.headers) {
            merged.headers = { ...defaults.headers, ...merged.headers };
        }

        const response = await fetch(url, merged);

        if (!response.ok) {
            let detail = response.statusText;
            try {
                const errorBody = await response.json();
                detail = errorBody.detail || detail;
            } catch (_) { /* not JSON */ }
            throw new Error(detail);
        }

        return response.json();
    },

    // ── Summoner ──────────────────────────────────────────
    async lookupSummoner(region, gameName, tagLine) {
        return this._fetch(`/summoner/${region}/${encodeURIComponent(gameName)}/${encodeURIComponent(tagLine)}`);
    },

    async getSummoner(puuid) {
        return this._fetch(`/summoner/${puuid}`);
    },

    async deleteSummoner(puuid) {
        return this._fetch(`/summoner/${puuid}`, { method: 'DELETE' });
    },

    // ── Matches ───────────────────────────────────────────
    async getMatches(puuid, page = 1, perPage = 20, queue = null) {
        let url = `/matches/${puuid}?page=${page}&per_page=${perPage}`;
        if (queue) url += `&queue=${queue}`;
        return this._fetch(url);
    },

    async refreshMatches(puuid, count = 20, queue = null) {
        let url = `/matches/${puuid}/refresh?count=${count}`;
        if (queue) url += `&queue=${queue}`;
        return this._fetch(url, { method: 'POST' });
    },

    async getMatchDetail(puuid, matchId) {
        return this._fetch(`/matches/${puuid}/detail/${matchId}`);
    },

    // ── Analysis ──────────────────────────────────────────
    async getMatchAnalysis(matchId) {
        return this._fetch(`/analysis/${matchId}`);
    },

    async getTrends(puuid) {
        return this._fetch(`/analysis/${puuid}/trends`);
    },

    // ── Analytics ─────────────────────────────────────────
    async getAnalytics(puuid, limit = 20, queue = null) {
        let url = `/analytics/${puuid}/overview?limit=${limit}`;
        if (queue) url += `&queue=${queue}`;
        return this._fetch(url);
    },

    // ── Strategy ──────────────────────────────────────────
    async getStrategy() {
        return this._fetch(`/strategy`);
    },

    async getChampionStrategy(championName) {
        return this._fetch(`/strategy/${encodeURIComponent(championName)}`);
    },

    async updateChampionStrategy(championName, data) {
        return this._fetch(`/strategy/${encodeURIComponent(championName)}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    async deleteChampionStrategy(championName) {
        return this._fetch(`/strategy/${encodeURIComponent(championName)}`, {
            method: 'DELETE',
        });
    },

    async importExcel() {
        return this._fetch(`/strategy/import/excel`, { method: 'POST' });
    },

    // ── Champions ─────────────────────────────────────────
    async getChampions() {
        return this._fetch(`/champions`);
    },

    async getChampionVersion() {
        return this._fetch(`/champions/version`);
    },

    // ── Health ────────────────────────────────────────────
    async checkHealth() {
        try {
            const response = await fetch(`${API_BASE}/health`);
            return response.json();
        } catch (_) {
            return { status: 'offline' };
        }
    },
};
