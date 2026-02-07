/**
 * Dashboard tests
 *
 * Tests for the TherapyRAG Dashboard functionality.
 * Uses jsdom to simulate browser environment.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { JSDOM } from 'jsdom';
import fs from 'fs';
import path from 'path';

// Read the HTML and JS files
const htmlPath = path.join(import.meta.dirname, '..', 'index.html');
const jsPath = path.join(import.meta.dirname, '..', 'dashboard.js');
const htmlContent = fs.readFileSync(htmlPath, 'utf-8');
const jsContent = fs.readFileSync(jsPath, 'utf-8');

describe('Dashboard HTML Structure', () => {
  let dom;
  let document;

  beforeEach(() => {
    dom = new JSDOM(htmlContent);
    document = dom.window.document;
  });

  it('has all required tabs', () => {
    const tabs = document.querySelectorAll('nav .tab');
    expect(tabs.length).toBe(7);

    const tabNames = Array.from(tabs).map((t) => t.dataset.tab);
    expect(tabNames).toContain('overview');
    expect(tabNames).toContain('sessions');
    expect(tabNames).toContain('safety');
    expect(tabNames).toContain('experiments');
    expect(tabNames).toContain('events');
    expect(tabNames).toContain('chat');
    expect(tabNames).toContain('provider');
  });

  it('has connection controls', () => {
    expect(document.getElementById('api-key')).not.toBeNull();
    expect(document.getElementById('api-url')).not.toBeNull();
    expect(document.getElementById('connection-status')).not.toBeNull();
  });

  it('has overview metrics', () => {
    expect(document.getElementById('metric-active-patients')).not.toBeNull();
    expect(document.getElementById('metric-sessions-week')).not.toBeNull();
    expect(document.getElementById('metric-pipeline-success')).not.toBeNull();
    expect(document.getElementById('metric-grounding-rate')).not.toBeNull();
  });

  it('has chat interface elements', () => {
    expect(document.getElementById('chat-messages')).not.toBeNull();
    expect(document.getElementById('chat-input')).not.toBeNull();
    expect(document.getElementById('chat-send')).not.toBeNull();
  });

  it('has provider workflow steps', () => {
    const steps = document.querySelectorAll('.workflow-steps .step');
    expect(steps.length).toBe(5);
  });

  it('has provider form elements', () => {
    expect(document.getElementById('provider-therapist')).not.toBeNull();
    expect(document.getElementById('provider-patient')).not.toBeNull();
    expect(document.getElementById('provider-session-date')).not.toBeNull();
    expect(document.getElementById('provider-file')).not.toBeNull();
  });
});

describe('Dashboard Tab Content', () => {
  let dom;
  let document;

  beforeEach(() => {
    dom = new JSDOM(htmlContent);
    document = dom.window.document;
  });

  it('overview tab is active by default', () => {
    const overviewTab = document.querySelector('[data-tab="overview"]');
    const overviewContent = document.getElementById('tab-overview');

    expect(overviewTab.classList.contains('active')).toBe(true);
    expect(overviewContent.classList.contains('active')).toBe(true);
  });

  it('has chart canvases', () => {
    const canvases = document.querySelectorAll('canvas');
    expect(canvases.length).toBeGreaterThan(0);

    // Check specific charts exist
    expect(document.getElementById('chart-utilization')).not.toBeNull();
    expect(document.getElementById('chart-engagement')).not.toBeNull();
    expect(document.getElementById('chart-outcomes')).not.toBeNull();
  });

  it('safety tab has metrics', () => {
    expect(document.getElementById('metric-risk-detections')).not.toBeNull();
    expect(document.getElementById('metric-guardrail-triggers')).not.toBeNull();
    expect(document.getElementById('metric-escalations')).not.toBeNull();
    expect(document.getElementById('metric-grounded')).not.toBeNull();
  });
});

describe('Dashboard JavaScript Loading', () => {
  let dom;
  let window;

  beforeEach(() => {
    // Create DOM with script
    dom = new JSDOM(htmlContent, {
      runScripts: 'dangerously',
      resources: 'usable',
    });
    window = dom.window;

    // Mock fetch
    window.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    // Mock Chart.js (would be loaded via CDN)
    window.Chart = vi.fn();

    // Execute dashboard script
    const script = window.document.createElement('script');
    script.textContent = jsContent;
    window.document.body.appendChild(script);
  });

  it('Dashboard object is created', () => {
    expect(window.Dashboard).toBeDefined();
  });

  it('Dashboard has required methods', () => {
    expect(typeof window.Dashboard.connect).toBe('function');
    expect(typeof window.Dashboard.switchTab).toBe('function');
    expect(typeof window.Dashboard.sendMessage).toBe('function');
    expect(typeof window.Dashboard.providerNext).toBe('function');
    expect(typeof window.Dashboard.providerBack).toBe('function');
  });
});

describe('API URL Handling', () => {
  it('default API URL is localhost', () => {
    const dom = new JSDOM(htmlContent);
    const apiUrlInput = dom.window.document.getElementById('api-url');
    expect(apiUrlInput.value).toBe('http://localhost:8000');
  });
});

describe('Accessibility', () => {
  let dom;
  let document;

  beforeEach(() => {
    dom = new JSDOM(htmlContent);
    document = dom.window.document;
  });

  it('has lang attribute on html', () => {
    expect(document.documentElement.lang).toBe('en');
  });

  it('has page title', () => {
    expect(document.title).toBe('TherapyRAG Dashboard');
  });

  it('form inputs have placeholders', () => {
    const apiKeyInput = document.getElementById('api-key');
    const apiUrlInput = document.getElementById('api-url');

    expect(apiKeyInput.placeholder).toBeTruthy();
    expect(apiUrlInput.placeholder).toBeTruthy();
  });

  it('chat input has placeholder', () => {
    const chatInput = document.getElementById('chat-input');
    expect(chatInput.placeholder).toBeTruthy();
  });
});
