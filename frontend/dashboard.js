/**
 * TherapyRAG Analytics Dashboard
 * Consumes the /api/v1/analytics and /api/v1/experiments endpoints.
 */

const Dashboard = (() => {
  let apiUrl = '';
  let apiKey = '';
  let charts = {};
  let eventCursor = null;

  // Chat state
  let patientId = null;
  let conversationId = null;
  let chatRateLimit = { remaining: 20, max: 20 };

  // Provider state
  let providerState = {
    step: 1,
    therapistId: null,
    patientId: null,
    consentIds: [],
    sessionId: null,
    pollingInterval: null,
  };

  // ── API Client ──────────────────────────────────────────────────────

  async function api(path, options = {}) {
    const url = new URL(`${apiUrl}${path}`);
    const { method = 'GET', params = {}, body = null } = options;

    // For backwards compatibility: if options is a plain object without method/body, treat as params
    if (!options.method && !options.body && !options.params) {
      Object.entries(options).forEach(([k, v]) => {
        if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v);
      });
    } else {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v);
      });
    }

    const fetchOptions = {
      method,
      headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    };

    if (body) {
      fetchOptions.body = JSON.stringify(body);
    }

    const res = await fetch(url.toString(), fetchOptions);

    if (!res.ok) {
      const err = new Error(`${res.status} ${res.statusText}`);
      err.status = res.status;
      throw err;
    }
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
      initChat();
      loadProviderUsers();
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

    // When switching to Chat tab, use provider's patient if no URL param
    if (tab === 'chat' && !patientId && providerState.patientId) {
      patientId = providerState.patientId;
      updatePatientDisplay();
      loadRateLimit();
    }
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
          event_category: category || undefined,
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

  // ── Chat Functions ─────────────────────────────────────────────────

  function initChat() {
    const params = new URLSearchParams(window.location.search);
    patientId = params.get('patient_id');

    // Fall back to provider's selected patient
    if (!patientId && providerState.patientId) {
      patientId = providerState.patientId;
    }

    updatePatientDisplay();
    if (patientId) {
      loadRateLimit();
    } else {
      updateRateLimitDisplay();
    }
  }

  async function updatePatientDisplay() {
    const patientIdEl = document.getElementById('chat-patient-id');

    if (!patientId) {
      patientIdEl.textContent = 'Not set - add ?patient_id=UUID to URL or select in Provider tab';
      patientIdEl.classList.add('error');
      return;
    }

    patientIdEl.classList.remove('error');

    // Try to look up patient email
    try {
      const patients = await api('/api/v1/users', { params: { role: 'patient' } });
      const patient = patients.find(p => p.id === patientId);
      if (patient) {
        patientIdEl.textContent = patient.email;
      } else {
        patientIdEl.textContent = patientId;
      }
    } catch {
      patientIdEl.textContent = patientId;
    }
  }

  async function loadRateLimit() {
    if (!patientId) return;
    try {
      const data = await api(`/api/v1/chat/rate-limit`, { params: { patient_id: patientId } });
      chatRateLimit = { remaining: data.remaining, max: data.max_per_hour };
    } catch (e) {
      console.error('Failed to load rate limit:', e);
    }
    updateRateLimitDisplay();
  }

  function updateRateLimitDisplay() {
    const badge = document.getElementById('chat-rate-limit');
    if (!patientId) {
      badge.textContent = '';
      return;
    }

    badge.textContent = `${chatRateLimit.remaining}/${chatRateLimit.max} messages`;

    badge.classList.remove('warning', 'danger');
    if (chatRateLimit.remaining <= 0) {
      badge.classList.add('danger');
    } else if (chatRateLimit.remaining <= 5) {
      badge.classList.add('warning');
    }

    // Disable/enable input
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');
    if (chatRateLimit.remaining <= 0) {
      input.disabled = true;
      sendBtn.disabled = true;
    } else {
      input.disabled = false;
      sendBtn.disabled = false;
    }
  }

  async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message || !patientId) return;
    if (chatRateLimit.remaining <= 0) {
      appendMessage('system', 'Rate limit exceeded. Please try again later.');
      return;
    }

    // Clear welcome message on first send
    const welcome = document.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    // Add user message to UI
    appendMessage('user', message);
    input.value = '';
    input.focus();

    // Show typing indicator
    showTypingIndicator();

    try {
      const response = await api(`/api/v1/chat`, {
        method: 'POST',
        params: { patient_id: patientId },
        body: {
          message,
          conversation_id: conversationId,
          top_k: 5,
        },
      });

      conversationId = response.conversation_id;
      appendMessage('assistant', response.response, response.sources);

      // Update rate limit
      chatRateLimit.remaining = Math.max(0, chatRateLimit.remaining - 1);
      updateRateLimitDisplay();

    } catch (err) {
      if (err.status === 429) {
        appendMessage('system', 'Rate limit exceeded. Please try again later.');
        chatRateLimit.remaining = 0;
        updateRateLimitDisplay();
      } else {
        appendMessage('system', 'Error sending message. Please try again.');
        console.error('Chat error:', err);
      }
    } finally {
      hideTypingIndicator();
    }
  }

  function appendMessage(role, content, sources = null) {
    const container = document.getElementById('chat-messages');

    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;

    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    contentEl.textContent = content;
    messageEl.appendChild(contentEl);

    // Add sources for assistant messages
    if (role === 'assistant' && sources && sources.length > 0) {
      const sourcesEl = renderSources(sources);
      messageEl.appendChild(sourcesEl);
    }

    container.appendChild(messageEl);
    container.scrollTop = container.scrollHeight;
  }

  function renderSources(sources) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-sources';

    const toggle = document.createElement('div');
    toggle.className = 'sources-toggle';
    toggle.innerHTML = `<span>&#9654;</span> ${sources.length} source${sources.length > 1 ? 's' : ''}`;

    const list = document.createElement('div');
    list.className = 'sources-list';

    sources.forEach(src => {
      const item = document.createElement('div');
      item.className = 'source-item';

      const meta = document.createElement('div');
      meta.className = 'source-meta';
      meta.innerHTML = `
        <span class="source-score">Score: ${(src.relevance_score * 100).toFixed(0)}%</span>
        ${src.speaker ? `<span>Speaker: ${esc(src.speaker)}</span>` : ''}
        ${src.start_time ? `<span>Time: ${formatTime(src.start_time)}</span>` : ''}
      `;

      const preview = document.createElement('div');
      preview.className = 'source-preview';
      preview.textContent = src.content_preview;

      item.appendChild(meta);
      item.appendChild(preview);
      list.appendChild(item);
    });

    toggle.addEventListener('click', () => {
      list.classList.toggle('expanded');
      toggle.querySelector('span').innerHTML = list.classList.contains('expanded') ? '&#9660;' : '&#9654;';
    });

    wrapper.appendChild(toggle);
    wrapper.appendChild(list);
    return wrapper;
  }

  function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  function showTypingIndicator() {
    const container = document.getElementById('chat-messages');
    const existing = container.querySelector('.typing-indicator');
    if (existing) return;

    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = '<span></span><span></span><span></span>';
    container.appendChild(indicator);
    container.scrollTop = container.scrollHeight;
  }

  function hideTypingIndicator() {
    const indicator = document.querySelector('.typing-indicator');
    if (indicator) indicator.remove();
  }

  // ── Provider Functions ─────────────────────────────────────────────

  async function loadProviderUsers() {
    try {
      const [therapists, patients] = await Promise.all([
        api('/api/v1/users', { params: { role: 'therapist' } }),
        api('/api/v1/users', { params: { role: 'patient' } }),
      ]);

      populateDropdown('provider-therapist', therapists, 'Select a therapist...');
      populateDropdown('provider-patient', patients, 'Select a patient...');
    } catch (e) {
      console.error('Failed to load users:', e);
      setStatusMessage('provider-consent-status', 'Failed to load users. Make sure API is connected.', 'error');
    }
  }

  function populateDropdown(selectId, users, placeholder) {
    const select = document.getElementById(selectId);
    select.innerHTML = `<option value="">${placeholder}</option>`;

    if (users.length === 0) {
      select.innerHTML += '<option value="" disabled>No users found</option>';
      return;
    }

    users.forEach(user => {
      const option = document.createElement('option');
      option.value = user.id;
      option.textContent = user.email;
      select.appendChild(option);
    });
  }

  function setProviderStep(step) {
    providerState.step = step;

    // Update step indicators
    document.querySelectorAll('.workflow-steps .step').forEach((el, i) => {
      el.classList.remove('active', 'completed');
      if (i + 1 < step) el.classList.add('completed');
      if (i + 1 === step) el.classList.add('active');
    });

    // Show/hide step panels
    document.querySelectorAll('.provider-step').forEach(el => el.classList.remove('active'));
    const panel = document.getElementById(`provider-step-${step}`);
    if (panel) panel.classList.add('active');
  }

  function providerNext() {
    if (providerState.step === 1) {
      // Validate user selection
      const therapistId = document.getElementById('provider-therapist').value;
      const patientId = document.getElementById('provider-patient').value;

      if (!therapistId || !patientId) {
        alert('Please select both a therapist and a patient.');
        return;
      }

      providerState.therapistId = therapistId;
      providerState.patientId = patientId;
    }

    setProviderStep(providerState.step + 1);
  }

  function providerBack() {
    if (providerState.step > 1) {
      setProviderStep(providerState.step - 1);
    }
  }

  async function grantConsents() {
    const btn = document.getElementById('provider-consent-btn');
    const statusEl = document.getElementById('provider-consent-status');

    btn.disabled = true;
    btn.textContent = 'Granting...';
    statusEl.className = 'status-message';
    statusEl.textContent = '';

    const consentTypes = ['recording', 'transcription', 'ai_analysis'];
    providerState.consentIds = [];

    try {
      for (const type of consentTypes) {
        try {
          const consent = await api('/api/v1/consent', {
            method: 'POST',
            body: {
              patient_id: providerState.patientId,
              therapist_id: providerState.therapistId,
              consent_type: type,
            },
          });
          providerState.consentIds.push(consent.id);
        } catch (err) {
          if (err.status === 409) {
            // Consent already exists, try to get existing
            setStatusMessage('provider-consent-status', `${type} consent already exists, continuing...`, 'info');
          } else {
            throw err;
          }
        }
      }

      setStatusMessage('provider-consent-status', 'All consents granted successfully!', 'success');
      setTimeout(() => providerNext(), 1000);

    } catch (err) {
      console.error('Consent error:', err);
      setStatusMessage('provider-consent-status', 'Failed to grant consent. Please try again.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Grant All Consents';
    }
  }

  async function createProviderSession() {
    const btn = document.getElementById('provider-session-btn');
    const dateInput = document.getElementById('provider-session-date');

    if (!dateInput.value) {
      setStatusMessage('provider-session-status', 'Please select a session date and time.', 'error');
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Creating...';

    try {
      // Need to get the recording consent ID - if we didn't capture it, fetch active consents
      let consentId = providerState.consentIds[0];

      if (!consentId) {
        // Fetch active consents to get the recording consent
        const consents = await api(`/api/v1/consent/${providerState.patientId}/active`, {
          params: { therapist_id: providerState.therapistId },
        });
        const recordingConsent = consents.find(c => c.consent_type === 'recording');
        if (!recordingConsent) {
          throw new Error('No active recording consent found');
        }
        consentId = recordingConsent.id;
      }

      const session = await api('/api/v1/sessions', {
        method: 'POST',
        body: {
          patient_id: providerState.patientId,
          therapist_id: providerState.therapistId,
          consent_id: consentId,
          session_date: new Date(dateInput.value).toISOString(),
        },
      });

      providerState.sessionId = session.id;
      setStatusMessage('provider-session-status', 'Session created successfully!', 'success');
      setTimeout(() => providerNext(), 1000);

    } catch (err) {
      console.error('Session error:', err);
      setStatusMessage('provider-session-status', 'Failed to create session. Please try again.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Create Session';
    }
  }

  function handleFileSelect() {
    const fileInput = document.getElementById('provider-file');
    const fileNameEl = document.getElementById('provider-file-name');
    const uploadBtn = document.getElementById('provider-upload-btn');

    if (fileInput.files.length > 0) {
      const file = fileInput.files[0];
      fileNameEl.textContent = file.name;
      uploadBtn.disabled = false;
    } else {
      fileNameEl.textContent = '';
      uploadBtn.disabled = true;
    }
  }

  async function uploadRecording() {
    const fileInput = document.getElementById('provider-file');
    const btn = document.getElementById('provider-upload-btn');

    if (!fileInput.files.length) {
      setStatusMessage('provider-upload-status', 'Please select a file to upload.', 'error');
      return;
    }

    const file = fileInput.files[0];
    btn.disabled = true;
    btn.textContent = 'Uploading...';

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${apiUrl}/api/v1/sessions/${providerState.sessionId}/recording`, {
        method: 'POST',
        headers: { 'X-API-Key': apiKey },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`);
      }

      setStatusMessage('provider-upload-status', 'Recording uploaded successfully!', 'success');
      setTimeout(() => providerNext(), 1000);

    } catch (err) {
      console.error('Upload error:', err);
      setStatusMessage('provider-upload-status', 'Failed to upload recording. Please try again.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Upload Recording';
    }
  }

  async function startTranscription() {
    const btn = document.getElementById('provider-transcribe-btn');
    const backBtn = document.getElementById('provider-back-5');
    const statusEl = document.getElementById('provider-transcription-status');

    btn.disabled = true;
    btn.textContent = 'Starting...';
    backBtn.disabled = true;

    try {
      await api(`/api/v1/sessions/${providerState.sessionId}/transcribe`, {
        method: 'POST',
      });

      statusEl.innerHTML = '<p>Transcription in progress...</p>';
      statusEl.className = 'transcription-status processing';
      btn.style.display = 'none';

      pollTranscriptionStatus();

    } catch (err) {
      console.error('Transcription error:', err);
      statusEl.innerHTML = '<p>Failed to start transcription. Please try again.</p>';
      statusEl.className = 'transcription-status failed';
      btn.disabled = false;
      btn.textContent = 'Start Transcription';
      backBtn.disabled = false;
    }
  }

  function pollTranscriptionStatus() {
    const statusEl = document.getElementById('provider-transcription-status');
    const progressFill = document.querySelector('#provider-progress .progress-fill');
    const progressText = document.getElementById('provider-progress-text');

    let progress = 0;

    providerState.pollingInterval = setInterval(async () => {
      try {
        const status = await api(`/api/v1/sessions/${providerState.sessionId}/transcription-status`);

        // Simulate progress
        if (status.job_status === 'processing') {
          progress = Math.min(progress + 10, 90);
          progressFill.style.width = `${progress}%`;
          progressText.textContent = `Processing... ${progress}%`;
        }

        if (status.job_status === 'completed') {
          clearInterval(providerState.pollingInterval);
          progressFill.style.width = '100%';
          progressText.textContent = 'Complete!';
          statusEl.innerHTML = '<p>Transcription completed successfully! The session is now ready for chat.</p>';
          statusEl.className = 'transcription-status completed';

          // Show done button
          document.getElementById('provider-transcribe-btn').style.display = 'none';
          document.getElementById('provider-back-5').style.display = 'none';
          document.getElementById('provider-done-btn').style.display = 'inline-block';
        }

        if (status.job_status === 'failed') {
          clearInterval(providerState.pollingInterval);
          statusEl.innerHTML = `<p>Transcription failed: ${status.error_message || 'Unknown error'}</p>`;
          statusEl.className = 'transcription-status failed';
          document.getElementById('provider-back-5').disabled = false;
        }

      } catch (err) {
        console.error('Status poll error:', err);
      }
    }, 2000);
  }

  function providerReset() {
    // Clear state
    providerState = {
      step: 1,
      therapistId: null,
      patientId: null,
      consentIds: [],
      sessionId: null,
      pollingInterval: null,
    };

    // Reset UI
    setProviderStep(1);
    document.getElementById('provider-therapist').value = '';
    document.getElementById('provider-patient').value = '';
    document.getElementById('provider-session-date').value = '';
    document.getElementById('provider-file').value = '';
    document.getElementById('provider-file-name').textContent = '';
    document.getElementById('provider-upload-btn').disabled = true;

    // Reset transcription UI
    const statusEl = document.getElementById('provider-transcription-status');
    statusEl.innerHTML = '<p>Ready to start transcription</p>';
    statusEl.className = 'transcription-status';
    document.querySelector('#provider-progress .progress-fill').style.width = '0%';
    document.getElementById('provider-progress-text').textContent = '';
    document.getElementById('provider-transcribe-btn').style.display = 'inline-block';
    document.getElementById('provider-transcribe-btn').disabled = false;
    document.getElementById('provider-transcribe-btn').textContent = 'Start Transcription';
    document.getElementById('provider-back-5').style.display = 'inline-block';
    document.getElementById('provider-back-5').disabled = false;
    document.getElementById('provider-done-btn').style.display = 'none';

    // Clear status messages
    document.querySelectorAll('.status-message').forEach(el => {
      el.textContent = '';
      el.className = 'status-message';
    });
  }

  function setStatusMessage(elementId, message, type) {
    const el = document.getElementById(elementId);
    if (el) {
      el.textContent = message;
      el.className = `status-message ${type}`;
    }
  }

  // ── Public API ──────────────────────────────────────────────────────

  return {
    connect,
    switchTab,
    refreshExperiments,
    showExperiment,
    refreshEvents,
    loadMoreEvents,
    sendMessage,
    // Provider functions
    providerNext,
    providerBack,
    grantConsents,
    createProviderSession,
    handleFileSelect,
    uploadRecording,
    startTranscription,
    providerReset,
  };
})();
