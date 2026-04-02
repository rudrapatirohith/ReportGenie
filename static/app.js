/**
 * ReportGenie v2.0 — Client-Side Application
 *
 * Handles tab switching, form submission, file upload,
 * API calls, download handling, and toast notifications.
 */

// ── Helpers ──────────────────────────────────────────────────────────────

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function formatDate(date) {
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const y = date.getFullYear();
  return `${m}/${d}/${y}`;
}

function defaultDates() {
  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() - 13);
  return { from: formatDate(from), to: formatDate(today) };
}

function upcomingDate(toStr, weeksAhead) {
  let base;
  try {
    const parts = toStr.split('/');
    base = new Date(parts[2], parts[0] - 1, parts[1]);
    if (isNaN(base.getTime())) throw new Error();
  } catch {
    base = new Date();
  }
  const d = new Date(base);
  d.setDate(d.getDate() + weeksAhead * 7);
  return formatDate(d);
}

// ── Toast Notifications ──────────────────────────────────────────────────

function toast(message, type = 'info') {
  const container = $('#toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Tab Switching ────────────────────────────────────────────────────────

function initTabs() {
  $$('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;

      // Update buttons
      $$('.tab-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');

      // Update panels
      $$('.tab-panel').forEach(p => p.classList.remove('active'));
      $(`#panel-${tab}`).classList.add('active');
    });
  });
}

// ── Accordion ────────────────────────────────────────────────────────────

window.toggleAccordion = function(id) {
  const el = document.getElementById(id);
  el.classList.toggle('open');
};

// ── File Upload ──────────────────────────────────────────────────────────

function initFileUploads() {
  const uploads = [
    { file: '#s-sig-file', name: '#s-sig-name', wrap: '#s-sig-upload' },
    { file: '#a-sig-file', name: '#a-sig-name', wrap: '#a-sig-upload' },
    { file: '#m-sig-file', name: '#m-sig-name', wrap: '#m-sig-upload' },
  ];

  uploads.forEach(({ file, name, wrap }) => {
    const input = $(file);
    if (!input) return;
    input.addEventListener('change', () => {
      const nameEl = $(name);
      const wrapEl = $(wrap);
      if (input.files.length > 0) {
        nameEl.textContent = input.files[0].name;
        wrapEl.classList.add('has-file');
      } else {
        nameEl.textContent = '';
        wrapEl.classList.remove('has-file');
      }
    });
  });
}

// ── Status Updates ───────────────────────────────────────────────────────

function setStatus(prefix, type, icon, message) {
  const el = $(`#${prefix}-status`);
  el.className = `status status-${type}`;
  el.innerHTML = `<span class="status-icon">${icon}</span><span>${message}</span>`;
}

function setModel(prefix, model) {
  const el = $(`#${prefix}-model`);
  if (el) el.textContent = model;
}

function setDownload(prefix, filename) {
  const el = $(`#${prefix}-download`);
  if (filename) {
    el.href = `/api/download/${encodeURIComponent(filename)}`;
    el.classList.remove('hidden');
    el.download = filename;
  } else {
    el.classList.add('hidden');
  }
}

function setJsonPreview(prefix, data) {
  const container = $(`#${prefix}-json`);
  const content = $(`#${prefix}-json-content`);
  if (!container || !content) return;
  if (data) {
    content.textContent = JSON.stringify(data, null, 2);
    container.classList.add('visible');
  } else {
    container.classList.remove('visible');
  }
}

function setButtonLoading(btnId, loading) {
  const btn = $(`#${btnId}`);
  if (loading) {
    btn.classList.add('loading');
    btn.disabled = true;
  } else {
    btn.classList.remove('loading');
    btn.disabled = false;
  }
}

// ── Smart Mode Generate ──────────────────────────────────────────────────

async function generateSmart() {
  const prefix = 's';
  const notes = $('#s-notes').value.trim();
  const fromDate = $('#s-from').value.trim();
  const toDate = $('#s-to').value.trim();

  if (!notes) { toast('Please enter your work notes.', 'error'); return; }
  if (!fromDate || !toDate) { toast('Please fill in both dates.', 'error'); return; }

  setButtonLoading('s-generate', true);
  setStatus(prefix, 'loading', '⏳', 'Processing your notes locally...');
  setDownload(prefix, null);
  setJsonPreview(prefix, null);
  setModel(prefix, '');

  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_notes: notes,
        from_date: fromDate,
        to_date: toDate,
        department: $('#s-dept').value.trim() || 'Technology',
        remarks: $('#s-remarks').value.trim(),
        employee_name: $('#s-employee').value.trim() || 'Rohith Rudrapati',
        project_name: $('#s-project').value.trim() || 'Modelone',
        mode: 'smart',
      }),
    });

    const data = await resp.json();

    if (!resp.ok) {
      throw new Error(data.error || 'Server error');
    }

    setStatus(prefix, 'success', '✅', `Report generated successfully!`);
    setModel(prefix, data.model_used);
    setDownload(prefix, data.pdf_filename);
    setJsonPreview(prefix, data.data);
    toast('Report ready — click Download!', 'success');

  } catch (err) {
    setStatus(prefix, 'error', '❌', `Error: ${err.message}`);
    toast(err.message, 'error');
  } finally {
    setButtonLoading('s-generate', false);
  }
}

// ── AI Mode Generate ─────────────────────────────────────────────────────

async function generateAI() {
  const prefix = 'a';
  const notes = $('#a-notes').value.trim();
  const fromDate = $('#a-from').value.trim();
  const toDate = $('#a-to').value.trim();

  if (!notes) { toast('Please enter your work notes.', 'error'); return; }
  if (!fromDate || !toDate) { toast('Please fill in both dates.', 'error'); return; }

  const geminiKey = $('#a-gemini-key').value.trim();
  const groqKey = $('#a-groq-key').value.trim();
  const openrouterKey = $('#a-openrouter-key').value.trim();

  if (!geminiKey && !groqKey && !openrouterKey) {
    toast('Enter at least one API key, or use Smart Mode.', 'error');
    return;
  }

  setButtonLoading('a-generate', true);
  setStatus(prefix, 'loading', '🤖', 'Calling AI providers (with automatic fallback)...');
  setDownload(prefix, null);
  setJsonPreview(prefix, null);
  setModel(prefix, '');

  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_notes: notes,
        from_date: fromDate,
        to_date: toDate,
        department: $('#a-dept').value.trim() || 'Technology',
        remarks: $('#a-remarks').value.trim(),
        employee_name: $('#a-employee').value.trim() || 'Rohith Rudrapati',
        project_name: $('#a-project').value.trim() || 'Modelone',
        mode: 'ai',
        gemini_key: geminiKey,
        groq_key: groqKey,
        openrouter_key: openrouterKey,
        save_keys: $('#a-save-keys').checked,
      }),
    });

    const data = await resp.json();

    if (!resp.ok) {
      throw new Error(data.error || 'Server error');
    }

    setStatus(prefix, 'success', '✅', `Report generated! Model: ${data.model_used}`);
    setModel(prefix, data.model_used);
    setDownload(prefix, data.pdf_filename);
    setJsonPreview(prefix, data.data);
    toast(`Report ready — powered by ${data.model_used}`, 'success');

  } catch (err) {
    setStatus(prefix, 'error', '❌', `Error: ${err.message}`);
    toast(err.message, 'error');
  } finally {
    setButtonLoading('a-generate', false);
  }
}

// ── Manual Mode Generate ─────────────────────────────────────────────────

async function generateManual() {
  const prefix = 'm';
  const fromDate = $('#m-from').value.trim();
  const toDate = $('#m-to').value.trim();
  const t1 = $('#m-task1').value.trim();
  const t2 = $('#m-task2').value.trim();
  const t3 = $('#m-task3').value.trim();

  if (!fromDate || !toDate) { toast('Please fill in both dates.', 'error'); return; }
  if (!t1 && !t2 && !t3) { toast('Enter at least one task.', 'error'); return; }

  setButtonLoading('m-generate', true);
  setStatus(prefix, 'loading', '⏳', 'Generating PDF...');
  setDownload(prefix, null);
  setModel(prefix, '');

  try {
    const resp = await fetch('/api/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from_date: fromDate,
        to_date: toDate,
        department: $('#m-dept').value.trim() || 'Technology',
        remarks: $('#m-remarks').value.trim(),
        employee_name: $('#m-employee').value.trim() || 'Rohith Rudrapati',
        project_name: $('#m-project').value.trim() || 'Modelone',
        tasks_performed: [t1 || '-', t2 || '-', t3 || '-'],
        upcoming_tasks: [
          { task: $('#m-ut1').value.trim() || '-', date: $('#m-ud1').value.trim() || upcomingDate(toDate, 1) },
          { task: $('#m-ut2').value.trim() || '-', date: $('#m-ud2').value.trim() || upcomingDate(toDate, 1) },
          { task: $('#m-ut3').value.trim() || '-', date: $('#m-ud3').value.trim() || upcomingDate(toDate, 2) },
        ],
      }),
    });

    const data = await resp.json();

    if (!resp.ok) {
      throw new Error(data.error || 'Server error');
    }

    setStatus(prefix, 'success', '✅', 'Report generated successfully!');
    setModel(prefix, data.model_used);
    setDownload(prefix, data.pdf_filename);
    toast('Report ready — click Download!', 'success');

  } catch (err) {
    setStatus(prefix, 'error', '❌', `Error: ${err.message}`);
    toast(err.message, 'error');
  } finally {
    setButtonLoading('m-generate', false);
  }
}

// ── Provider Health Check ────────────────────────────────────────────────

async function checkHealth() {
  try {
    const resp = await fetch('/api/health');
    const data = await resp.json();

    if (data.has_gemini_key) $('#chip-gemini').classList.add('active');
    if (data.has_groq_key) $('#chip-groq').classList.add('active');
    if (data.has_openrouter_key) $('#chip-openrouter').classList.add('active');

    // Pre-fill API key fields if keys exist in env
    if (data.has_gemini_key) {
      $('#a-gemini-key').placeholder = '••• saved in .env •••';
    }
    if (data.has_groq_key) {
      $('#a-groq-key').placeholder = '••• saved in .env •••';
    }
    if (data.has_openrouter_key) {
      $('#a-openrouter-key').placeholder = '••• saved in .env •••';
    }
  } catch {
    // Server not ready yet
  }
}

// ── Initialize ───────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Set default dates
  const dates = defaultDates();
  ['s-from', 'a-from', 'm-from'].forEach(id => {
    const el = $(`#${id}`);
    if (el) el.value = dates.from;
  });
  ['s-to', 'a-to', 'm-to'].forEach(id => {
    const el = $(`#${id}`);
    if (el) el.value = dates.to;
  });

  // Set upcoming dates for manual mode
  $('#m-ud1').value = upcomingDate(dates.to, 1);
  $('#m-ud2').value = upcomingDate(dates.to, 1);
  $('#m-ud3').value = upcomingDate(dates.to, 2);

  // Init components
  initTabs();
  initFileUploads();

  // Wire buttons
  $('#s-generate').addEventListener('click', generateSmart);
  $('#a-generate').addEventListener('click', generateAI);
  $('#m-generate').addEventListener('click', generateManual);

  // Health check
  checkHealth();
});
