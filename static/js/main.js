/* ═══════════════════════════════════════════════════════════
   Auto-Citer — main.js
   All client-side interactivity
═══════════════════════════════════════════════════════════ */

'use strict';

// ── Theme ──────────────────────────────────────────────────────
(function initTheme() {
  const saved = localStorage.getItem('ac_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
})();

document.addEventListener('DOMContentLoaded', () => {

  // ── Theme toggle ─────────────────────────────────────────────
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next    = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('ac_theme', next);
    });
  }

  // ── File upload & drop zone ───────────────────────────────────
  const dropZone  = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const fileInfo  = document.getElementById('file-info');
  const btnPreview = document.getElementById('btn-preview');
  const submitBtn  = document.getElementById('submit-btn');
  const submitHint = document.getElementById('submit-hint');

  if (!dropZone || !fileInput) return;

  // Click to open browser
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

  // File change
  fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));

  // Drag & drop
  dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) {
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      handleFile(file);
    }
  });

  function handleFile(file) {
    if (!file) return;

    const allowed = ['docx', 'pdf', 'txt'];
    const ext = file.name.split('.').pop().toLowerCase();
    const maxMB = (window.AUTOCITER?.maxSizeMB || 16);

    if (!allowed.includes(ext)) {
      setFileInfo(`⚠️ Unsupported format. Use .docx, .pdf, or .txt`, 'red');
      disableSubmit('Unsupported file type');
      return;
    }
    if (file.size > maxMB * 1024 * 1024) {
      setFileInfo(`⚠️ File too large (${(file.size/1024/1024).toFixed(1)} MB). Max: ${maxMB} MB`, 'red');
      disableSubmit('File too large');
      return;
    }

    const sizeStr = file.size > 1024*1024
      ? `${(file.size/1024/1024).toFixed(1)} MB`
      : `${(file.size/1024).toFixed(0)} KB`;

    setFileInfo(`📎 ${file.name}  (${sizeStr})`, 'green');
    enableSubmit();

    // Show preview button
    if (btnPreview) {
      btnPreview.style.display = 'block';
      advanceStep(2);
    }
  }

  function setFileInfo(msg, color) {
    if (!fileInfo) return;
    fileInfo.textContent = msg;
    fileInfo.style.color = color === 'red' ? 'var(--red)' : 'var(--green)';
  }

  function enableSubmit() {
    if (!submitBtn) return;
    submitBtn.disabled = false;
    if (submitHint) submitHint.textContent = 'Ready — click to insert citations and download';
  }

  function disableSubmit(reason) {
    if (!submitBtn) return;
    submitBtn.disabled = true;
    if (submitHint) submitHint.textContent = reason || 'Select a file above to continue';
  }

  // ── Style card selection ──────────────────────────────────────
  document.querySelectorAll('.style-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.style-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      const radio = card.querySelector('input[type=radio]');
      if (radio) radio.checked = true;
    });
  });

  // ── Toggle switches ───────────────────────────────────────────
  document.querySelectorAll('.toggle-row').forEach(row => {
    row.addEventListener('click', e => {
      if (e.target.tagName !== 'INPUT') {
        const cb = row.querySelector('input[type=checkbox]');
        if (cb) cb.checked = !cb.checked;
      }
    });
  });

  // ── Reference preview modal ───────────────────────────────────
  if (btnPreview) {
    btnPreview.addEventListener('click', () => fetchPreview());
  }

  const modal        = document.getElementById('preview-modal');
  const modalClose   = document.getElementById('modal-close');
  const modalCancel  = document.getElementById('modal-cancel');
  const modalProceed = document.getElementById('modal-proceed');
  const modalBackdrop= document.getElementById('modal-backdrop');

  function openModal()  { if (modal) modal.style.display = 'block'; }
  function closeModal() { if (modal) modal.style.display = 'none';  }

  if (modalClose)   modalClose.addEventListener('click',   closeModal);
  if (modalCancel)  modalCancel.addEventListener('click',  closeModal);
  if (modalBackdrop)modalBackdrop.addEventListener('click',closeModal);
  if (modalProceed) {
    modalProceed.addEventListener('click', () => {
      closeModal();
      submitForm();
    });
  }

  // Esc closes modal
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      document.getElementById('upload-form')?.requestSubmit();
    }
  });

  async function fetchPreview() {
    if (!fileInput.files || !fileInput.files[0]) return;

    btnPreview.textContent = '⏳ Detecting references…';
    btnPreview.disabled = true;

    const fd = new FormData();
    fd.append('document', fileInput.files[0]);

    try {
      const resp = await fetch(window.AUTOCITER?.previewUrl || '/api/preview', {
        method: 'POST',
        body: fd
      });
      const data = await resp.json();

      if (data.error) {
        showToast('⚠️ ' + data.error);
        btnPreview.textContent = '🔍 Preview detected references';
        btnPreview.disabled = false;
        return;
      }

      renderPreviewModal(data);
      openModal();
      renderSidePanel(data);
      advanceStep(3);

    } catch (err) {
      showToast('Could not fetch preview. You can still process directly.');
    } finally {
      btnPreview.textContent = '🔍 Preview detected references';
      btnPreview.disabled = false;
    }
  }

  function renderPreviewModal(data) {
    const list = document.getElementById('modal-ref-list');
    if (!list || !data.refs) return;

    list.innerHTML = data.refs.map((ref, i) => `
      <div class="modal-ref-item">
        <div class="modal-ref-idx">[${ref.index}]</div>
        <div class="modal-ref-body">
          <div class="modal-ref-author">${ref.authors ? ref.authors[0] : 'Unknown'} ${ref.authors && ref.authors.length > 1 ? `<em>et al.</em>` : ''}</div>
          <div class="modal-ref-year">${ref.year || 'n.d.'} ${ref.title ? '— ' + truncate(ref.title, 60) : ''}</div>
        </div>
        <span class="ref-badge badge-${confTier(ref.confidence)}">${ref.confidence ?? '?'}%</span>
      </div>
    `).join('');
  }

  function renderSidePanel(data) {
    const panel = document.getElementById('preview-panel');
    const list  = document.getElementById('ref-preview-list');
    const badge = document.getElementById('ref-count-badge');

    if (!panel || !data.refs) return;

    panel.style.display = 'block';
    if (badge) badge.textContent = data.refs.length;

    if (list) {
      list.innerHTML = data.refs.slice(0, 8).map(ref => `
        <div class="ref-preview-item">
          <span class="ref-preview-idx">[${ref.index}]</span>
          <span class="ref-preview-text">${ref.authors ? ref.authors[0] : 'Unknown'} (${ref.year || 'n.d.'})</span>
          <span class="ref-badge badge-${confTier(ref.confidence)}">${confTier(ref.confidence)}</span>
        </div>
      `).join('');
      if (data.refs.length > 8) {
        list.innerHTML += `<div class="ref-preview-item" style="color:var(--text-muted);justify-content:center">+ ${data.refs.length - 8} more…</div>`;
      }
    }
  }

  function confTier(pct) {
    if (pct === undefined || pct === null) return 'medium';
    if (pct >= 85) return 'high';
    if (pct >= 60) return 'medium';
    return 'low';
  }

  // ── Form submission ───────────────────────────────────────────
  const uploadForm = document.getElementById('upload-form');
  if (uploadForm) {
    uploadForm.addEventListener('submit', e => {
      if (!fileInput.files || !fileInput.files[0]) {
        e.preventDefault();
        setFileInfo('⚠️ Please select a file first.', 'red');
        return;
      }
      showProcessingOverlay();
      advanceStep(4);
    });
  }

  function submitForm() {
    const form = document.getElementById('upload-form');
    if (form) form.requestSubmit();
  }

  // ── Processing overlay with step cycling ──────────────────────
  function showProcessingOverlay() {
    const overlay = document.getElementById('processing-overlay');
    if (overlay) overlay.classList.add('visible');

    const steps = ['step-reading', 'step-parsing', 'step-matching', 'step-writing'];
    let cur = 0;
    const interval = setInterval(() => {
      const el = document.getElementById(steps[cur]);
      if (el) el.classList.add('done');
      cur++;
      if (cur >= steps.length) { clearInterval(interval); return; }
      const next = document.getElementById(steps[cur]);
      if (next) {
        next.classList.remove('done');
        next.classList.add('active');
      }
    }, 1200);
  }

  // ── Step progress bar ─────────────────────────────────────────
  function advanceStep(n) {
    for (let i = 1; i <= 4; i++) {
      const el = document.getElementById(`bar-step-${i}`);
      if (!el) continue;
      el.classList.remove('active', 'done');
      if (i < n)       el.classList.add('done');
      else if (i === n) el.classList.add('active');
    }
  }

  // ── Utility: truncate string ──────────────────────────────────
  function truncate(str, maxLen) {
    return str && str.length > maxLen ? str.slice(0, maxLen) + '…' : str;
  }

});

// ── Toast notification (global) ───────────────────────────────
function showToast(msg, duration = 3000) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => t.classList.add('toast-show'));
  });
  setTimeout(() => {
    t.classList.remove('toast-show');
    setTimeout(() => t.remove(), 350);
  }, duration);
}

// Save to history helper (called from result page)
function saveToHistory(entry) {
  try {
    const history = JSON.parse(localStorage.getItem('autociter_history') || '[]');
    history.push({ ...entry, date: new Date().toISOString() });
    // Keep last 50 entries
    if (history.length > 50) history.splice(0, history.length - 50);
    localStorage.setItem('autociter_history', JSON.stringify(history));
  } catch (e) {
    // localStorage not available
  }
}
