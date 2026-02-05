/**
 * TherapyRAG Analytics Dashboard
 * Consumes the /api/v1/analytics and /api/v1/experiments endpoints.
 */

const Dashboard = (() => {
  let apiUrl = '';
  let apiKey = '';
  let charts = {};
  let eventCursor = null;

  // ── API Client ──────────────────────────────────────────────────────

  async function api(path, params = {}) {
    const url = new URL(`${apiUrl}${path}`);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v);
    });

    const res = await fetch(url.toString(), {
      headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    });

    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  // ── Connection ──────────────────────────────────────────────────────

  async function connect() {
    apiUrl = document.getElementById('api-url').value.replace(/\/$/, '');
    apiKey = document.getElementById('api-key').value;

    const badge = document.getElementById('connection-status');
    try {
      await fetch(`${apiUrl}/health`);
      badge.textContent = 'Connected';
      badge.className = 'status-badge connected';
      loadAll();
    } catch {
      badge.textContent = 'Failed';
      badge.className = 'status-badge disconnected';
    }
  }

  // ── Tab Navigation ──────────────────────────────────────────────────

  function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`tab-${tab}`).classList.add('active');
  }

  // ── Data Loading ────────────────────────────────────────────────────

  async function loadAll() {
    await Promise.allSettled([
      loadOverview(),
      loadSessions(),
      loadSafety(),
      loadExperiments(),
      loadEvents(),
    ]);
  }

  async function loadOverview() {
    try {
      const [engagement, utilization] = await Promise.all([
        api('/api/v1/analytics/patient-engagement'),
        api('/api/v1/analytics/therapist-utilization'),
      ]);

      // Summary metrics
      if (engagement.length > 0) {
        const latest = engagement[engagement.length - 1];
        setText('metric-active-patients', latest.active_patients);
        setText('metric-sessions-week', latest.total_sessions);
      }

      // Utilization chart
      renderUtilizationChart(utilization);
      renderEngagementChart(engagement);
    } catch (e) {
      console.error('Overview load failed:', e);
    }
  }

  async function loadSessions() {
    try {
      const outcomes = await api('/api/v1/analytics/session-outcomes');

      if (outcomes.length > 0) {
        const latest = outcomes[outcomes.length - 1];
        setText('metric-pipeline-success', `${latest.success_rate_pct}%`);
      }

      renderOutcomesChart(outcomes);
      renderPipelineChart(outcomes);
      renderP95Chart(outcomes);
    } catch (e) {
      console.error('Sessions load failed:', e);
    }
  }

  async function loadSafety() {
    try {
      const safety = await api('/api/v1/analytics/ai-safety-metrics');

      if (safety.length > 0) {
        const latest = safety[safety.length - 1];
        setText('metric-risk-detections', latest.risk_detections);
        setText('metric-guardrail-triggers', latest.guardrail_triggers);
        setText('metric-escalations', latest.escalations);
        setText('metric-grounded', `${latest.grounding_rate_pct}%`);
        setText('metric-grounding-rate', `${latest.grounding_rate_pct}%`);
      }

      renderSafetyTrendChart(safety);
      renderGroundingChart(safety);
    } catch (e) {
      console.error('Safety load failed:', e);
    }
  }

  async function loadExperiments() {
    await refreshExperiments();
  }

  async function refreshExperiments() {
    try {
      const status = document.getElementById('experiment-status-filter').value;
      const experiments = await api('/api/v1/experiments', { status: status || undefined });

      const list = document.getElementById('experiments-list');
      if (experiments.length === 0) {
        list.innerHTML = '<div class="empty-state">No experiments found</div>';
        return;
      }

      list.innerHTML = experiments.map(exp => `
        <div class="experiment-card" onclick="Dashboard.showExperiment('${exp.id}', '${exp.name}')">
          <div class="name">${esc(exp.name)}</div>
          <div class="meta">
            <span class="status-pill ${exp.status}">${exp.status}</span>
            <span>Traffic: ${exp.traffic_percentage}%</span>
            <span>${Object.keys(exp.variants).length} variants</span>
          </div>
        </div>
      `).join('');
    } catch (e) {
      console.error('Experiments load failed:', e);
    }
  }

  async function showExperiment(id, name) {
    const detail = document.getElementById('experiment-detail');
    detail.style.display = 'block';
    document.getElementById('experiment-detail-title').textContent = name;

    try {
      // Try to get results for a common metric name
      const results = await api(`/api/v1/experiments/${id}/results`, { metric_name: 'conversion' }).catch(() => null);

      if (results && Object.keys(results.variant_stats).length > 0) {
        renderExperimentChart(results);
        renderExperimentStats(results);
      } else {
        document.getElementById('experiment-stats').innerHTML =
          '<div class="empty-state">No metric data recorded yet. Record metrics to see results.</div>';
      }
    } catch {
      document.getElementById('experiment-stats').innerHTML =
        '<div class="empty-state">Could not load results.</div>';
    }
  }

  async function loadEvents() {
    eventCursor = null;
    await refreshEvents();
  }

  async function refreshEvents() {
    try {
      const eventName = document.getElementById('event-filter-name').value;
      const category = document.getElementById('event-filter-category').value;

      const [timeline, aggregates] = await Promise.all([
        api('/api/v1/analytics/events/timeline', {
          event_name: eventName || undefined,
          event_category: category || undefined,
          limit: 50,
        }),
        api('/api/v1/analytics/events/aggregate', {
          event_name: eventName || undefined,
          period: 'day',
        }),
      ]);

      renderEventsTable(timeline.events);
      eventCursor = timeline.next_cursor;
      renderEventVolumeChart(aggregates.aggregates);
    } catch (e) {
      console.error('Events load failed:', e);
    }
  }

  async function loadMoreEvents() {
    if (!eventCursor) return;
    try {
      const eventName = document.getElementById('event-filter-name').value;
      const category = document.getElementById('event-filter-category').value;

      const timeline = await api('/api/v1/analytics/events/timeline', {
        cursor: eventCursor,
        event_name: eventName || undefined,
        event_category: category || undefined,
        limit: 50,
      });

      appendEventsTable(timeline.events);
      eventCursor = timeline.next_cursor;
    } catch (e) {
      console.error('Load more events failed:', e);
    }
  }

  // ── Chart Rendering ─────────────────────────────────────────────────

  const COLORS = {
    accent: '#6366f1',
    accentLight: 'rgba(99, 102, 241, 0.2)',
    success: '#22c55e',
    successLight: 'rgba(34, 197, 94, 0.2)',
    warning: '#f59e0b',
    warningLight: 'rgba(245, 158, 11, 0.2)',
    danger: '#ef4444',
    dangerLight: 'rgba(239, 68, 68, 0.2)',
    muted: '#8b8d98',
    grid: '#2a2d3a',
  };

  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { labels: { color: COLORS.muted, font: { size: 11 } } } },
    scales: {
      x: { ticks: { color: COLORS.muted, font: { size: 10 } }, grid: { color: COLORS.grid } },
      y: { ticks: { color: COLORS.muted, font: { size: 10 } }, grid: { color: COLORS.grid } },
    },
  };

  function getOrCreateChart(id, config) {
    if (charts[id]) charts[id].destroy();
    const ctx = document.getElementById(id);
    if (!ctx) return null;
    charts[id] = new Chart(ctx, config);
    return charts[id];
  }

  function renderUtilizationChart(data) {
    const labels = data.map(d => d.period_start);
    getOrCreateChart('chart-utilization', {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Sessions', data: data.map(d => d.sessions_in_period), backgroundColor: COLORS.accent },
          { label: 'Patients', data: data.map(d => d.patients_in_period), backgroundColor: COLORS.success },
        ],
      },
      options: chartDefaults,
    });
  }

  function renderEngagementChart(data) {
    const labels = data.map(d => d.period_start);
    getOrCreateChart('chart-engagement', {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Active Patients',
            data: data.map(d => d.active_patients),
            borderColor: COLORS.accent,
            backgroundColor: COLORS.accentLight,
            fill: true,
            tension: 0.3,
          },
          {
            label: 'Activation Rate %',
            data: data.map(d => d.patient_activation_rate_pct),
            borderColor: COLORS.success,
            borderDash: [5, 5],
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        ...chartDefaults,
        scales: {
          ...chartDefaults.scales,
          y1: {
            position: 'right',
            ticks: { color: COLORS.muted, font: { size: 10 } },
            grid: { display: false },
          },
        },
      },
    });
  }

  function renderOutcomesChart(data) {
    const labels = data.map(d => d.period_start);
    getOrCreateChart('chart-outcomes', {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Ready', data: data.map(d => d.sessions_ready), backgroundColor: COLORS.success },
          { label: 'Failed', data: data.map(d => d.sessions_failed), backgroundColor: COLORS.danger },
        ],
      },
      options: { ...chartDefaults, plugins: { ...chartDefaults.plugins }, scales: { ...chartDefaults.scales, x: { ...chartDefaults.scales.x, stacked: true }, y: { ...chartDefaults.scales.y, stacked: true } } },
    });
  }

  function renderPipelineChart(data) {
    const labels = data.map(d => d.period_start);
    getOrCreateChart('chart-pipeline', {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Success Rate %',
          data: data.map(d => d.success_rate_pct),
          borderColor: COLORS.success,
          backgroundColor: COLORS.successLight,
          fill: true,
          tension: 0.3,
        }],
      },
      options: chartDefaults,
    });
  }

  function renderP95Chart(data) {
    const labels = data.map(d => d.period_start);
    getOrCreateChart('chart-p95', {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Avg Time (s)', data: data.map(d => d.avg_seconds_to_ready), borderColor: COLORS.accent, tension: 0.3 },
          { label: 'P95 Time (s)', data: data.map(d => d.p95_seconds_to_ready), borderColor: COLORS.warning, borderDash: [5, 5], tension: 0.3 },
        ],
      },
      options: chartDefaults,
    });
  }

  function renderSafetyTrendChart(data) {
    const labels = data.map(d => d.period_start);
    getOrCreateChart('chart-safety-trend', {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Risk Detections', data: data.map(d => d.risk_detections), backgroundColor: COLORS.danger },
          { label: 'Guardrail Triggers', data: data.map(d => d.guardrail_triggers), backgroundColor: COLORS.warning },
          { label: 'Escalations', data: data.map(d => d.escalations), backgroundColor: '#dc2626' },
        ],
      },
      options: chartDefaults,
    });
  }

  function renderGroundingChart(data) {
    if (data.length === 0) return;
    const latest = data[data.length - 1];
    getOrCreateChart('chart-grounding', {
      type: 'doughnut',
      data: {
        labels: ['Grounded', 'Zero Source'],
        datasets: [{
          data: [latest.grounded_responses, latest.zero_source_responses],
          backgroundColor: [COLORS.success, COLORS.danger],
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { color: COLORS.muted } },
        },
      },
    });
  }

  function renderExperimentChart(results) {
    const variants = Object.keys(results.variant_stats);
    const means = variants.map(v => results.variant_stats[v].metric_mean);
    const stds = variants.map(v => results.variant_stats[v].metric_std);

    getOrCreateChart('chart-experiment-variants', {
      type: 'bar',
      data: {
        labels: variants,
        datasets: [{
          label: 'Mean',
          data: means,
          backgroundColor: variants.map((_, i) => i === 0 ? COLORS.muted : COLORS.accent),
          errorBars: stds,
        }],
      },
      options: chartDefaults,
    });
  }

  function renderExperimentStats(results) {
    const el = document.getElementById('experiment-stats');
    const rows = Object.entries(results.variant_stats).map(([name, s]) => `
      <tr>
        <td>${esc(name)}</td>
        <td>${s.subject_count}</td>
        <td>${s.metric_mean.toFixed(4)}</td>
        <td>${s.metric_std.toFixed(4)}</td>
        <td>${s.metric_min.toFixed(2)} - ${s.metric_max.toFixed(2)}</td>
      </tr>
    `).join('');

    const sig = results.is_significant
      ? `<span style="color:${COLORS.success}">Significant</span> (p=${results.p_value})`
      : `<span style="color:${COLORS.muted}">Not significant</span>${results.p_value ? ` (p=${results.p_value})` : ''}`;

    el.innerHTML = `
      <p style="margin-bottom:12px">Statistical significance: ${sig}</p>
      <table>
        <thead><tr><th>Variant</th><th>Subjects</th><th>Mean</th><th>Std Dev</th><th>Range</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderEventVolumeChart(aggregates) {
    const grouped = {};
    aggregates.forEach(a => {
      if (!grouped[a.event_name]) grouped[a.event_name] = {};
      grouped[a.event_name][a.period] = a.count;
    });

    const periods = [...new Set(aggregates.map(a => a.period))].sort();
    const palette = [COLORS.accent, COLORS.success, COLORS.warning, COLORS.danger, '#a78bfa', '#38bdf8'];
    const datasets = Object.keys(grouped).map((name, i) => ({
      label: name,
      data: periods.map(p => grouped[name][p] || 0),
      borderColor: palette[i % palette.length],
      tension: 0.3,
    }));

    getOrCreateChart('chart-event-volume', {
      type: 'line',
      data: { labels: periods, datasets },
      options: chartDefaults,
    });
  }

  // ── Events Table ────────────────────────────────────────────────────

  function renderEventsTable(events) {
    const tbody = document.getElementById('events-tbody');
    tbody.innerHTML = events.map(eventRow).join('');
  }

  function appendEventsTable(events) {
    const tbody = document.getElementById('events-tbody');
    tbody.insertAdjacentHTML('beforeend', events.map(eventRow).join(''));
  }

  function eventRow(e) {
    const ts = new Date(e.event_timestamp).toLocaleString();
    const props = e.properties ? JSON.stringify(e.properties).slice(0, 80) : '--';
    return `<tr><td>${ts}</td><td>${esc(e.event_name)}</td><td>${esc(e.event_category || '')}</td><td title="${esc(JSON.stringify(e.properties))}">${esc(props)}</td></tr>`;
  }

  // ── Helpers ─────────────────────────────────────────────────────────

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? '--';
  }

  function esc(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Public API ──────────────────────────────────────────────────────

  return {
    connect,
    switchTab,
    refreshExperiments,
    showExperiment,
    refreshEvents,
    loadMoreEvents,
  };
})();
