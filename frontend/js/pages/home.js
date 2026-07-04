/**
 * LoL Stats — Home Page
 * Personal overview: profile card + full match history ("Recent Skirmishes").
 * Also hosts match-detail rendering.
 */

const HOME_PAGE_SIZE = 20;

async function renderHomePage(container) {
    const identity = App.identity.get();

    container.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Command Overview</h1>
            <p class="page-subtitle">
                ${escapeHtml(identity.game_name)}#${escapeHtml(identity.tag_line)}
                • ${identity.region.toUpperCase()}
            </p>
        </div>

        <div id="home-body">
            <div class="loading-block">
                <div class="spinner"></div>
                <span>Loading your profile...</span>
            </div>
        </div>
    `;

    await loadProfile();
}

// ── Profile card + stats ──────────────────────────────────────
async function loadProfile() {
    const identity = App.identity.get();
    const body = document.getElementById('home-body');
    if (!body) return;

    try {
        const summoner = await api.lookupSummoner(
            identity.region, identity.game_name, identity.tag_line
        );
        App.state.currentSummoner = summoner;

        body.innerHTML = `
            <div class="card" style="margin-bottom:16px;">
                <div class="flex-between">
                    <div style="display:flex;align-items:center;gap:16px;">
                        <div class="grade-seal" title="Summoner">
                            ${escapeHtml((summoner.game_name || '?')[0].toUpperCase())}
                        </div>
                        <div>
                            <div style="font-size:1.15rem;font-weight:700;color:var(--text);">
                                ${escapeHtml(summoner.game_name)}<span class="faint">#${escapeHtml(summoner.tag_line)}</span>
                            </div>
                            <div style="color:var(--muted);font-size:0.88rem;">
                                Level ${summoner.summoner_level ?? '—'}
                                • ${summoner.region.toUpperCase()}
                                • ${summoner.match_count ?? 0} matches on record
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn btn-sm" id="home-refresh" title="Fetch new matches from Riot">Refresh</button>
                    </div>
                </div>
            </div>

            <div id="home-stats" class="detail-grid" style="margin-bottom:24px;grid-template-columns:repeat(3,1fr);"></div>

            <div id="home-analytics"></div>

            <div id="recent-skirmishes"></div>
        `;

        document.getElementById('home-refresh').addEventListener('click', () =>
            refreshHomeMatches(summoner.puuid)
        );

        await renderAnalytics(summoner.puuid);
        await renderRecentSkirmishes();
    } catch (err) {
        body.innerHTML = `
            <div class="card">
                <div class="card-header">Couldn't load your profile</div>
                <p class="muted mb-12">${escapeHtml(err.message || 'Summoner not found.')}</p>
                <p class="muted">
                    Check your identity in
                    <a href="#/settings" class="gold">Settings</a>,
                    and make sure the backend is running.
                </p>
            </div>`;
    }
}

// ── Recent Skirmishes (full match history) ────────────────────
async function renderRecentSkirmishes() {
    const host = document.getElementById('recent-skirmishes');
    if (!host) return;
    const summoner = App.state.currentSummoner;
    if (!summoner) return;

    host.innerHTML = `
        <div class="flex-between mb-12">
            <div class="card-header" style="margin-bottom:0;">Recent Skirmishes</div>
            <div class="form-group" style="margin:0;">
                <select class="form-select" id="queue-filter" style="width:auto;min-width:150px;">
                    <option value="">All Queues</option>
                    <option value="420">Ranked Solo/Duo</option>
                    <option value="440">Ranked Flex</option>
                    <option value="400">Normal Draft</option>
                    <option value="450">ARAM</option>
                </select>
            </div>
        </div>
        <div id="match-list"></div>
        <div id="pagination" style="text-align:center;margin-top:16px;"></div>
    `;

    document.getElementById('queue-filter').addEventListener('change', () => {
        App.state.matchPage = 1;
        loadMatchList();
    });

    App.state.matchPage = 1;
    await loadMatchList();
}

async function loadMatchList() {
    const summoner = App.state.currentSummoner;
    if (!summoner) return;

    const list = document.getElementById('match-list');
    const pagination = document.getElementById('pagination');
    const stats = document.getElementById('home-stats');
    if (!list) return;

    list.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Loading matches...</p></div>';
    pagination.innerHTML = '';

    const queue = document.getElementById('queue-filter')?.value || null;
    const queueNum = queue ? parseInt(queue) : null;

    try {
        const result = await api.getMatches(summoner.puuid, App.state.matchPage, HOME_PAGE_SIZE);
        App.state.matchList = result.matches;
        App.state.hasMoreMatches = result.has_more;

        // Stat boxes
        if (stats) {
            const wins = result.matches.filter(m => m.win).length;
            const losses = result.matches.length - wins;
            stats.innerHTML = `
                <div class="stat-box">
                    <div class="stat-value">${result.total}</div>
                    <div class="stat-label">Matches on Record</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${result.matches.length}</div>
                    <div class="stat-label">On This Page</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">
                        <span style="color:var(--win);">${wins}</span>
                        <span class="faint">/</span>
                        <span style="color:var(--loss);">${losses}</span>
                    </div>
                    <div class="stat-label">Page Record</div>
                </div>`;
        }

        if (result.matches.length === 0) {
            list.innerHTML = `
                <div class="empty-block">
                    <div class="empty-label">No matches found</div>
                    <div class="empty-action">Click "Refresh" to fetch matches from Riot.</div>
                </div>`;
            return;
        }

        list.innerHTML = result.matches.map(m => renderMatchCard(m)).join('');

        pagination.innerHTML = `
            <div style="display:flex;gap:12px;justify-content:center;align-items:center;">
                <button class="btn btn-sm" id="prev-page" ${App.state.matchPage <= 1 ? 'disabled' : ''}>
                    ← Previous
                </button>
                <span style="color:var(--text-secondary);font-size:0.9rem;">
                    Page ${App.state.matchPage} (${result.total} total)
                </span>
                <button class="btn btn-sm" id="next-page" ${!result.has_more ? 'disabled' : ''}>
                    Next →
                </button>
            </div>`;

        document.getElementById('prev-page')?.addEventListener('click', () => {
            if (App.state.matchPage > 1) {
                App.state.matchPage--;
                loadMatchList();
                window.scrollTo(0, 0);
            }
        });
        document.getElementById('next-page')?.addEventListener('click', () => {
            if (App.state.hasMoreMatches) {
                App.state.matchPage++;
                loadMatchList();
                window.scrollTo(0, 0);
            }
        });
    } catch (err) {
        list.innerHTML = `<div class="empty-block">
            <div class="empty-label">Failed to load matches</div>
            <div class="empty-action">${escapeHtml(err.message)}</div>
        </div>`;
    }
}

async function refreshHomeMatches(puuid) {
    const btn = document.getElementById('home-refresh');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'Fetching...';
    try {
        const result = await api.refreshMatches(puuid, 20, null);
        App.toast(result.message || 'Matches refreshed.', 'success');
        App.state.matchPage = 1;
        await loadMatchList();
    } catch (err) {
        App.toast(err.message || 'Refresh failed.', 'error');
    } finally {
        const restored = document.getElementById('home-refresh');
        if (restored) { restored.disabled = false; restored.textContent = 'Refresh'; }
    }
}

// ── Analytics Section ─────────────────────────────────────────
let analyticsChart = null;
const analyticsState = { metric: 'kda', rankBenchmarks: {}, selectedRank: 'GOLD' };

const METRIC_LABELS = {
    kda: 'KDA Ratio',
    vision_per_min: 'Vision / min',
    cs_per_min: 'CS / min',
    gold_per_min: 'Gold / min',
    dmg_per_min: 'Damage / min',
};

async function renderAnalytics(puuid) {
    const host = document.getElementById('home-analytics');
    if (!host) return;

    let data;
    try {
        data = await api.getAnalytics(puuid, 20);
    } catch (_) {
        host.innerHTML = '';
        return;
    }

    const s = data.summary;
    analyticsState.rankBenchmarks = data.rank_benchmarks || {};

    // ── Coaching items ──
    const coachingHtml = data.coaching.map(c => {
        const sev = c.severity === 'poor' ? 'poor' : c.severity === 'warning' ? 'warn' : 'ok';
        const icon = sev === 'poor' ? '🔴' : sev === 'warn' ? '⚠' : '✅';
        return `<div class="coaching-item ${sev}">
            <div class="coaching-item-head">
                <span class="coaching-item-icon">${icon}</span>
                <span class="coaching-item-area">${escapeHtml(c.area)}</span>
                <span class="coaching-item-metric mono">${escapeHtml(c.metric)}${c.target ? ' → ' + escapeHtml(c.target) : ''}</span>
            </div>
            <p class="coaching-item-msg">${escapeHtml(c.message)}</p>
        </div>`;
    }).join('');

    // ── Recent form blocks ──
    const formHtml = data.recent_form.map(r =>
        `<span class="form-block ${r === 'W' ? 'win' : 'loss'}" title="${r === 'W' ? 'Win' : 'Loss'}">${r}</span>`
    ).join('');

    // ── Champion pool ──
    const champHtml = data.champion_stats.slice(0, 5).map(c => `
        <div class="champ-pool-row">
            <span class="champ-pool-name">${escapeHtml(c.champion)}</span>
            <div class="champ-pool-bar">
                <div class="champ-pool-fill" style="width:${c.win_rate}%;"></div>
            </div>
            <span class="champ-pool-record mono">${c.wins}W ${c.losses}L</span>
            <span class="champ-pool-wr mono ${c.win_rate >= 50 ? 'positive' : 'negative'}">${c.win_rate}%</span>
        </div>
    `).join('');

    // ── Summary mini-stats for chart card header ──
    const trendColor = s.trend_direction === 'improving' ? 'var(--win)' : s.trend_direction === 'declining' ? 'var(--loss)' : 'var(--muted)';

    host.innerHTML = `
        <div class="analytics-section">
            <div class="analytics-grid">
                <div class="analytics-chart-card">
                    <div class="analytics-card-head">
                        <div>
                            <span class="analytics-card-title">Performance Trends</span>
                            <span class="analytics-card-sub mono">
                                ${s.win_rate}% WR (${s.wins}W ${s.losses}L)
                                • ${s.avg_kda} avg KDA
                                • <span style="color:${trendColor};font-weight:700;">${s.trend_direction.charAt(0).toUpperCase() + s.trend_direction.slice(1)}</span>
                            </span>
                        </div>
                    </div>
                    <div class="metric-toggles" id="metric-toggles">
                        <button class="metric-btn active" data-metric="kda">KDA</button>
                        <button class="metric-btn" data-metric="vision_per_min">Vision</button>
                        <button class="metric-btn" data-metric="cs_per_min">CS</button>
                        <button class="metric-btn" data-metric="gold_per_min">Gold</button>
                        <button class="metric-btn" data-metric="dmg_per_min">Damage</button>
                    </div>
                    <div class="chart-wrap"><canvas id="trend-chart"></canvas></div>
                </div>

                <div class="coaching-card">
                    <div class="analytics-card-head">
                        <span class="analytics-card-title">Coaching Focus</span>
                    </div>
                    <div class="coaching-list">${coachingHtml}</div>
                </div>
            </div>

            <div id="rank-comparison-host"></div>

            <div class="analytics-bottom">
                <div class="analytics-mini-card">
                    <div class="card-header" style="margin-bottom:10px;">Recent Form (last ${data.recent_form.length})</div>
                    <div class="form-bar">${formHtml}</div>
                </div>
                <div class="analytics-mini-card">
                    <div class="card-header" style="margin-bottom:10px;">Champion Pool</div>
                    <div class="champ-pool-list">${champHtml}</div>
                </div>
            </div>
        </div>
    `;

    initTrendChart(data.time_series, analyticsState.metric);

    document.getElementById('metric-toggles').addEventListener('click', (e) => {
        const btn = e.target.closest('.metric-btn');
        if (!btn) return;
        host.querySelectorAll('.metric-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        analyticsState.metric = btn.dataset.metric;
        updateTrendChart(data.time_series, analyticsState.metric);
    });

    // Rank comparison dropdown
    renderRankComparison(s);
}

function _extractMetric(timeSeries, metric) {
    return {
        label: METRIC_LABELS[metric] || metric,
        labels: timeSeries.map((_, i) => i + 1),
        values: timeSeries.map(g => g[metric]),
        colors: timeSeries.map(g => g.win ? '#4A9E7C' : '#D44B5A'),
    };
}

function buildChartConfig(timeSeries, metric) {
    const m = _extractMetric(timeSeries, metric);
    return {
        type: 'line',
        data: {
            labels: m.labels,
            datasets: [{
                label: m.label,
                data: m.values,
                borderColor: '#C8A75A',
                backgroundColor: 'rgba(200, 167, 90, 0.08)',
                borderWidth: 2,
                pointBackgroundColor: m.colors,
                pointBorderColor: m.colors,
                pointRadius: 4,
                pointHoverRadius: 7,
                tension: 0.3,
                fill: true,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0d0f12',
                    borderColor: '#232830',
                    borderWidth: 1,
                    titleColor: '#cca74f',
                    bodyColor: '#e8eaed',
                    padding: 10,
                    cornerRadius: 0,
                    displayColors: false,
                    titleFont: { family: 'JetBrains Mono', size: 12, weight: '700' },
                    bodyFont: { family: 'JetBrains Mono', size: 11 },
                    callbacks: {
                        title: (ctx) => {
                            const g = timeSeries[ctx[0].dataIndex];
                            return g.champion + ' — ' + (g.win ? 'Win' : 'Loss');
                        },
                        label: (ctx) => m.label + ': ' + ctx.parsed.y,
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(46, 50, 64, 0.3)', drawBorder: false },
                    ticks: { color: '#5B6170', font: { size: 10 } },
                },
                y: {
                    grid: { color: 'rgba(46, 50, 64, 0.3)', drawBorder: false },
                    ticks: { color: '#5B6170', font: { size: 10 } },
                    beginAtZero: true,
                },
            },
        },
    };
}

function initTrendChart(timeSeries, metric) {
    if (analyticsChart) { analyticsChart.destroy(); analyticsChart = null; }
    const canvas = document.getElementById('trend-chart');
    if (!canvas || typeof Chart === 'undefined') return;
    analyticsChart = new Chart(canvas, buildChartConfig(timeSeries, metric));
}

function updateTrendChart(timeSeries, metric) {
    if (!analyticsChart) { initTrendChart(timeSeries, metric); return; }
    const m = _extractMetric(timeSeries, metric);
    analyticsChart.data.datasets[0].label = m.label;
    analyticsChart.data.datasets[0].data = m.values;
    analyticsChart.data.datasets[0].pointBackgroundColor = m.colors;
    analyticsChart.data.datasets[0].pointBorderColor = m.colors;
    analyticsChart.update();
}

// ── Rank Comparison ───────────────────────────────────────────
const RANK_ORDER = ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'EMERALD', 'DIAMOND', 'MASTER'];
const COMPARE_METRICS = [
    { key: 'kda',            label: 'KDA',           summary_key: 'avg_kda' },
    { key: 'vision_per_min', label: 'Vision / min',  summary_key: 'avg_vision_per_min' },
    { key: 'gold_per_min',   label: 'Gold / min',    summary_key: 'avg_gold_per_min' },
    { key: 'dmg_per_min',    label: 'Damage / min',  summary_key: 'avg_dmg_per_min' },
];

function renderRankComparison(summary) {
    const host = document.getElementById('rank-comparison-host');
    if (!host) return;
    const benches = analyticsState.rankBenchmarks;
    const rank = analyticsState.selectedRank;
    const rankData = benches[rank] || {};

    const options = RANK_ORDER.map(r =>
        '<option value="' + r + '"' + (r === rank ? ' selected' : '') + '>' +
        r.charAt(0) + r.slice(1).toLowerCase() + '</option>'
    ).join('');

    const rows = COMPARE_METRICS.map(m => {
        const myVal = summary[m.summary_key] || 0;
        const rankVal = rankData[m.key];
        if (rankVal == null) return '';
        const diff = myVal - rankVal;
        const pct = rankVal > 0 ? Math.round((diff / rankVal) * 100) : 0;
        const positive = diff >= 0;
        const arrow = positive ? '▲' : '▼';
        const diffStr = (diff >= 0 ? '+' : '') + (Number.isInteger(diff) ? diff : diff.toFixed(2));

        return '<div class="rank-comp-row">' +
            '<span class="rank-comp-metric">' + m.label + '</span>' +
            '<span class="rank-comp-you mono">' + myVal + '</span>' +
            '<span class="rank-comp-sep">vs</span>' +
            '<span class="rank-comp-them mono">' + rankVal + '</span>' +
            '<span class="rank-comp-diff ' + (positive ? 'positive' : 'negative') + '">' +
                diffStr + ' ' + arrow + ' (' + (positive ? '+' : '') + pct + '%)' +
            '</span>' +
        '</div>';
    }).join('');

    host.innerHTML = `
        <div class="rank-comparison-card">
            <div class="rank-comp-head">
                <span class="analytics-card-title">Rank Comparison</span>
                <div class="rank-comp-select">
                    <span class="rank-comp-select-label">Compare with</span>
                    <select class="form-select" id="rank-select">${options}</select>
                </div>
            </div>
            <div class="rank-comp-table">
                <div class="rank-comp-header-row">
                    <span>Metric</span>
                    <span>Your Avg</span>
                    <span></span>
                    <span>${rank.charAt(0) + rank.slice(1).toLowerCase()} Avg</span>
                    <span>Difference</span>
                </div>
                ${rows}
            </div>
        </div>
    `;

    document.getElementById('rank-select')?.addEventListener('change', (e) => {
        analyticsState.selectedRank = e.target.value;
        renderRankComparison(summary);
    });
}

function renderMatchCard(m) {
    const ratio = kdaRatio(m.kills, m.deaths, m.assists);
    const gold = (m.gold_earned / 1000).toFixed(1);
    return `
    <div class="match-strip ${m.win ? 'win' : 'loss'}"
         onclick="App.navigate('match/${encodeURIComponent(m.match_id)}')"
         tabindex="0" role="button" aria-label="${m.win ? 'Win' : 'Loss'} as ${m.champion_name}">
        <span class="match-result-label ${m.win ? 'win' : 'loss'}">${m.win ? 'Win' : 'Loss'}</span>
        <span class="match-champ">${escapeHtml(m.champion_name)}</span>
        <span class="match-kda">
            <span class="k">${m.kills}</span><span class="sep">/</span>
            <span class="d">${m.deaths}</span><span class="sep">/</span>
            <span class="a">${m.assists}</span>
            <span class="ratio">${ratio}</span>
        </span>
        <span class="match-stats-row">
            <span>${m.total_minions_killed} CS</span>
            <span>VS ${m.vision_score}</span>
            <span>${gold}k</span>
        </span>
        <span class="match-meta">
            <span>${formatDuration(m.game_duration)}</span>
            <span> • ${timeAgo(m.game_creation)}</span>
            ${m.has_analysis ? ' •' : ''}
        </span>
    </div>`;
}

// ── Match Detail ──────────────────────────────────────────────
async function renderMatchDetail(container, args) {
    const summoner = App.state.currentSummoner;
    const matchId = decodeURIComponent(args[0] || '');

    if (!summoner || !matchId) {
        container.innerHTML = `<div class="empty-block"><div class="empty-label">No match selected.</div></div>`;
        return;
    }

    container.innerHTML = '<div class="loading-block"><div class="spinner"></div><span>Loading match...</span></div>';

    try {
        const match = await api.getMatchDetail(summoner.puuid, matchId);
        const ratio = kdaRatio(match.kills, match.deaths, match.assists);
        const csPerMin = match.game_duration > 0
            ? (match.total_minions_killed / (match.game_duration / 60)).toFixed(1)
            : '0';
        const goldK = (match.gold_earned / 1000).toFixed(1);

        let analysisHtml = '';
        if (match.analysis_data) {
            analysisHtml = renderAnalysisBlock(match.analysis_data);
        } else {
            try {
                const analysis = await api.getMatchAnalysis(matchId);
                analysisHtml = renderAnalysisBlock(analysis);
            } catch (_) {
                analysisHtml = `<div class="card">
                    <div class="card-header">Analysis</div>
                    <p class="muted">Analysis not yet computed. Refresh matches to generate it.</p>
                </div>`;
            }
        }

        container.innerHTML = `
            <a href="#/home" class="back-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
                Back to Overview
            </a>

            <div class="match-hero ${match.win ? 'win' : 'loss'}">
                <div class="match-hero-banner">${match.win ? 'VICTORY' : 'DEFEAT'}</div>
                <div class="match-hero-body">
                    <div>
                        <div class="match-hero-champ">${escapeHtml(match.champion_name)}</div>
                        ${match.individual_position ? `<div class="match-hero-pos">${escapeHtml(match.individual_position)}</div>` : ''}
                    </div>
                    <div class="match-hero-player">
                        ${escapeHtml(summoner.game_name)}<span class="faint">#${escapeHtml(summoner.tag_line)}</span>
                    </div>
                </div>
                <div class="match-hero-meta">
                    ${queueName(match.queue_id)} • ${formatDuration(match.game_duration)} • ${formatDate(match.game_creation)}
                </div>
            </div>

            <div class="detail-grid">
                <div class="stat-box">
                    <div class="stat-value">
                        <span style="color:var(--win);">${match.kills}</span>
                        <span class="faint">/</span>
                        <span style="color:var(--loss);">${match.deaths}</span>
                        <span class="faint">/</span>
                        <span class="muted">${match.assists}</span>
                    </div>
                    <div class="stat-label">KDA <span class="gold">${ratio}</span></div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${match.total_minions_killed}</div>
                    <div class="stat-label">CS <span class="muted">${csPerMin}/min</span></div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${match.vision_score}</div>
                    <div class="stat-label">Vision <span class="muted">${match.control_wards_placed} ctrl wards</span></div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${goldK}k</div>
                    <div class="stat-label">Gold <span class="muted">${(match.total_damage_dealt_to_champions / 1000).toFixed(1)}k dmg</span></div>
                </div>
            </div>

            ${analysisHtml}
        `;
    } catch (err) {
        container.innerHTML = `<div class="empty-block">
            <div class="empty-label">Failed to load match</div>
            <div class="empty-action">${escapeHtml(err.message)}</div>
        </div>`;
    }
}

function renderAnalysisBlock(analysis) {
    if (!analysis) return '';
    const a = analysis;
    const grade = a.overall_grade || '?';
    const gradeClass = grade === '?' ? 'grade-seal' : `grade-seal ${grade}`;

    let html = `
    <div class="tactical-assessment">
        <div class="ta-header">
            <span class="ta-title">Tactical Assessment</span>
            <div class="${gradeClass}" title="Overall Grade">${grade}</div>
        </div>
        ${a.summary ? `<p class="ta-summary">${escapeHtml(a.summary)}</p>` : ''}
        ${a.focus_areas && a.focus_areas.length ? `
            <div class="priority-callout">
                <div class="priority-callout-header">⚠ Priority Improvements</div>
                <div class="priority-list">
                    ${a.focus_areas.map(f => `
                        <div class="priority-item">
                            <span class="priority-marker"></span>
                            <span>${escapeHtml(f)}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        ` : ''}
    </div>`;

    const sections = [
        { key: 'cs', label: 'CS Analysis' },
        { key: 'kill_participation', label: 'Kill Participation' },
        { key: 'vision', label: 'Vision Control' },
        { key: 'deaths', label: 'Death Review' },
        { key: 'itemization', label: 'Itemization' },
    ];

    for (const s of sections) {
        const sec = a[s.key];
        if (!sec) continue;

        const status = sec.status === 'poor' ? 'poor' : sec.status === 'warning' ? 'warn' : 'ok';
        const score = sec.score != null ? `${sec.score}` : '—';

        html += `<div class="analysis-block">
            <div class="analysis-block-header">
                <span class="indicator ${status}"></span>
                <span>${s.label}</span>
                <span class="analysis-score">${score}/100</span>
            </div>`;

        if (sec.details && sec.details.length) {
            html += `<ul class="analysis-detail">
                ${sec.details.map(d => `<li>${escapeHtml(d)}</li>`).join('')}
            </ul>`;
        }
        html += `</div>`;
    }

    return html;
}
