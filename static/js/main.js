/* ═══════════════════════════════════════════════════════════
   Auto-Citer — main.js  v2.1
   All client-side interactivity
═══════════════════════════════════════════════════════════ */

'use strict';

// ── Theme (runs immediately, before DOMContentLoaded) ─────────────────────────
(function initTheme() {
  const saved = localStorage.getItem('ac_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
})();

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  addedRefs:   [],   // manually added / DOI-fetched references
  nextRefIdx:  1000, // start index for manually added refs (won't conflict with doc refs)
};

// ── DOMContentLoaded ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {

  // ── Theme toggle ─────────────────────────────────────────────
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const cur  = document.documentElement.getAttribute('data-theme');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('ac_theme', next);
    });
  }

  // ── Tab bar ───────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const content = document.getElementById(`tab-content-${tab}`);
      if (content) content.classList.add('active');
    });
  });

  // ── Sub-tabs ──────────────────────────────────────────────────
  document.querySelectorAll('.sub-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.closest('.collapsible-body') || btn.closest('.doi-lookup-form') || document;
      group.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
      group.querySelectorAll('.sub-tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const target = group.querySelector(`#subtab-${btn.dataset.subtab}`);
      if (target) target.classList.add('active');
    });
  });

  // ── Collapsible cards ─────────────────────────────────────────
  document.querySelectorAll('.collapsible-trigger').forEach(trigger => {
    trigger.addEventListener('click', () => {
      const bodyId  = trigger.dataset.target;
      const body    = document.getElementById(bodyId);
      const iconId  = bodyId.replace('-body', '-icon');
      const icon    = document.getElementById(iconId);
      if (!body) return;
      const open = body.style.display !== 'none';
      body.style.display = open ? 'none' : 'block';
      if (icon) icon.textContent = open ? '▸' : '▾';
    });
  });

  // ── File upload & drop zone ───────────────────────────────────
  const dropZone  = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const fileInfo  = document.getElementById('file-info');
  const btnPreview = document.getElementById('btn-preview');
  const submitBtn  = document.getElementById('submit-btn');
  const submitHint = document.getElementById('submit-hint');
  const wordCounter= document.getElementById('word-counter');

  if (dropZone && fileInput) {
    dropZone.addEventListener('click',  () => fileInput.click());
    dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });
    fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));
    dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault(); dropZone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) { setFileInputFile(file); handleFile(file); }
    });
  }

  function setFileInputFile(file) {
    try { const dt = new DataTransfer(); dt.items.add(file); fileInput.files = dt.files; } catch (_) {}
  }

  function handleFile(file) {
    if (!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    const allowed = ['docx', 'pdf', 'txt'];
    const maxMB = window.AUTOCITER?.maxSizeMB || 16;

    if (!allowed.includes(ext)) {
      setFileInfo('⚠️ Unsupported format. Use .docx, .pdf, or .txt', 'error'); disableSubmit('Unsupported file'); return;
    }
    if (file.size > maxMB * 1024 * 1024) {
      setFileInfo(`⚠️ Too large (${(file.size/1024/1024).toFixed(1)} MB). Max: ${maxMB} MB`, 'error'); disableSubmit('File too large'); return;
    }

    const sizeStr = file.size > 1024*1024 ? `${(file.size/1024/1024).toFixed(1)} MB` : `${Math.round(file.size/1024)} KB`;
    setFileInfo(`📎 ${file.name}  (${sizeStr})`, 'ok');
    enableSubmit();
    if (btnPreview) { btnPreview.style.display = 'block'; }
    advanceStep(2);

    // Word count for .txt files
    if (ext === 'txt' && wordCounter) {
      const reader = new FileReader();
      reader.onload = e => {
        const text  = e.target.result;
        const words = text.trim() ? text.trim().split(/\s+/).length : 0;
        document.getElementById('word-count').textContent  = words.toLocaleString();
        document.getElementById('char-count').textContent  = text.length.toLocaleString();
        wordCounter.style.display = 'flex';
      };
      reader.readAsText(file);
    }
  }

  function setFileInfo(msg, type) {
    if (!fileInfo) return;
    fileInfo.textContent = msg;
    fileInfo.style.color = type === 'error' ? 'var(--red)' : 'var(--green)';
  }
  function enableSubmit()  { if (submitBtn) { submitBtn.disabled = false; if (submitHint) submitHint.textContent = 'Ready — click to insert citations'; } }
  function disableSubmit(r){ if (submitBtn) { submitBtn.disabled = true;  if (submitHint) submitHint.textContent = r || 'Select a file'; } }

  // ── Batch file input ──────────────────────────────────────────
  const batchDZ    = document.getElementById('batch-drop-zone');
  const batchInput = document.getElementById('batch-file-input');
  const batchInfo  = document.getElementById('batch-file-info');
  const batchBtn   = document.getElementById('batch-submit-btn');

  if (batchDZ && batchInput) {
    batchInput.addEventListener('change', () => {
      const f = batchInput.files[0];
      if (f) {
        batchInfo.textContent = `📦 ${f.name}  (${(f.size/1024/1024).toFixed(1)} MB)`;
        if (batchBtn) batchBtn.disabled = false;
      }
    });
    batchDZ.addEventListener('dragover',  e => { e.preventDefault(); batchDZ.classList.add('drag-over'); });
    batchDZ.addEventListener('dragleave', () => batchDZ.classList.remove('drag-over'));
    batchDZ.addEventListener('drop', e => {
      e.preventDefault(); batchDZ.classList.remove('drag-over');
      const f = e.dataTransfer.files[0];
      if (f && f.name.endsWith('.zip')) {
        try { const dt = new DataTransfer(); dt.items.add(f); batchInput.files = dt.files; } catch (_) {}
        batchInfo.textContent = `📦 ${f.name}  (${(f.size/1024/1024).toFixed(1)} MB)`;
        if (batchBtn) batchBtn.disabled = false;
      }
    });
    document.getElementById('batch-form')?.addEventListener('submit', () => {
      const prog = document.getElementById('batch-progress');
      if (prog) prog.style.display = 'block';
      if (batchBtn) batchBtn.disabled = true;
    });
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

  // ── Preview modal ─────────────────────────────────────────────
  if (btnPreview) btnPreview.addEventListener('click', () => fetchPreview());

  const modal        = document.getElementById('preview-modal');
  const modalClose   = document.getElementById('modal-close');
  const modalCancel  = document.getElementById('modal-cancel');
  const modalProceed = document.getElementById('modal-proceed');
  const modalBackdrop= document.getElementById('modal-backdrop');

  const openModal  = () => { if (modal) modal.style.display = 'block'; };
  const closeModal = () => { if (modal) modal.style.display = 'none';  };

  modalClose?.addEventListener('click',    closeModal);
  modalCancel?.addEventListener('click',   closeModal);
  modalBackdrop?.addEventListener('click', closeModal);
  modalProceed?.addEventListener('click',  () => { closeModal(); submitForm(); });

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); document.getElementById('upload-form')?.requestSubmit(); }
  });

  async function fetchPreview() {
    if (!fileInput?.files?.[0]) return;
    btnPreview.textContent = '⏳ Detecting…';
    btnPreview.disabled = true;

    const fd = new FormData();
    fd.append('document', fileInput.files[0]);

    try {
      const resp = await fetch(window.AUTOCITER?.previewUrl || '/api/preview', { method: 'POST', body: fd });
      const data = await resp.json();
      if (data.error) { showToast('⚠️ ' + data.error); return; }
      renderPreviewModal(data);
      openModal();
      renderSidePanel(data);
      advanceStep(3);
    } catch (_) {
      showToast('Could not fetch preview — you can still process directly.');
    } finally {
      btnPreview.textContent = '🔍 Preview detected references';
      btnPreview.disabled = false;
    }
  }

  function renderPreviewModal(data) {
    const list = document.getElementById('modal-ref-list');
    if (!list || !data.refs) return;
    list.innerHTML = data.refs.map(ref => `
      <div class="modal-ref-item">
        <div class="modal-ref-idx">[${ref.index}]</div>
        <div class="modal-ref-body">
          <div class="modal-ref-author">${ref.authors?.[0] || 'Unknown'}${ref.authors?.length > 1 ? ' <em>et al.</em>' : ''}</div>
          <div class="modal-ref-year">${ref.year || 'n.d.'}${ref.title ? ' — ' + truncate(ref.title, 60) : ''}</div>
        </div>
        <span class="ref-badge badge-${confTier(ref.confidence)}">${ref.confidence ?? '?'}%</span>
      </div>`).join('');
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
          <span class="ref-preview-text">${ref.authors?.[0] || 'Unknown'} (${ref.year || 'n.d.'})</span>
          <span class="ref-badge badge-${confTier(ref.confidence)}">${confTier(ref.confidence)}</span>
        </div>`).join('');
      if (data.refs.length > 8) list.innerHTML += `<div class="ref-preview-item" style="color:var(--text-muted);justify-content:center">+${data.refs.length - 8} more…</div>`;
    }
  }

  // ── Form submit ───────────────────────────────────────────────
  document.getElementById('upload-form')?.addEventListener('submit', e => {
    if (!fileInput?.files?.[0]) { e.preventDefault(); setFileInfo('⚠️ Please select a file first.', 'error'); return; }
    // Embed added refs into hidden field
    const hidden = document.getElementById('extra-refs-hidden');
    if (hidden && state.addedRefs.length) hidden.value = JSON.stringify(state.addedRefs);
    showProcessingOverlay();
    advanceStep(4);
  });

  function submitForm() { document.getElementById('upload-form')?.requestSubmit(); }

  // ── Processing overlay ────────────────────────────────────────
  function showProcessingOverlay() {
    const ov = document.getElementById('processing-overlay');
    if (ov) ov.classList.add('visible');
    const steps = ['step-reading', 'step-parsing', 'step-matching', 'step-writing'];
    let cur = 0;
    const iv = setInterval(() => {
      document.getElementById(steps[cur])?.classList.add('done');
      cur++;
      if (cur >= steps.length) { clearInterval(iv); return; }
      const next = document.getElementById(steps[cur]);
      if (next) { next.classList.remove('done'); next.classList.add('active'); }
    }, 1200);
  }

  // ── Step progress ─────────────────────────────────────────────
  function advanceStep(n) {
    for (let i = 1; i <= 4; i++) {
      const el = document.getElementById(`bar-step-${i}`);
      if (!el) continue;
      el.classList.remove('active', 'done');
      if (i < n) el.classList.add('done');
      else if (i === n) el.classList.add('active');
    }
  }

  // ── DOI / PMID fetch (inline editor) ─────────────────────────
  document.getElementById('btn-fetch-doi')?.addEventListener('click', () => {
    const doi = document.getElementById('doi-input')?.value.trim();
    if (!doi) return;
    fetchDOI(doi, 'doi-result');
  });

  document.getElementById('btn-fetch-pmid')?.addEventListener('click', () => {
    const pmid = document.getElementById('pmid-input')?.value.trim();
    if (!pmid) return;
    fetchPMID(pmid, 'pmid-result');
  });

  // ── Standalone DOI tab ────────────────────────────────────────
  document.getElementById('standalone-btn-fetch-doi')?.addEventListener('click', () => {
    const doi = document.getElementById('standalone-doi-input')?.value.trim();
    if (!doi) return;
    fetchDOI(doi, 'standalone-doi-result', true);
  });

  document.getElementById('standalone-btn-fetch-pmid')?.addEventListener('click', () => {
    const pmid = document.getElementById('standalone-pmid-input')?.value.trim();
    if (!pmid) return;
    fetchPMID(pmid, 'standalone-doi-result', true);
  });

  document.getElementById('btn-crossref-search')?.addEventListener('click', async () => {
    const q = document.getElementById('crossref-search-input')?.value.trim();
    if (!q) return;
    const resultEl = document.getElementById('standalone-doi-result');
    resultEl.style.display = 'block';
    resultEl.innerHTML = '<div class="fetch-loading">🔍 Searching CrossRef…</div>';
    try {
      const resp = await fetch(`${window.AUTOCITER.searchUrl}?q=${encodeURIComponent(q)}`);
      const data = await resp.json();
      if (!data.results?.length) { resultEl.innerHTML = '<div class="fetch-empty">No results found.</div>'; return; }
      resultEl.innerHTML = data.results.map(r => buildRefCard(r, true)).join('');
      attachAddButtons(resultEl);
    } catch (e) {
      resultEl.innerHTML = `<div class="fetch-error">❌ Search failed: ${e.message}</div>`;
    }
  });

  async function fetchDOI(doi, resultId, isStandalone = false) {
    const resultEl = document.getElementById(resultId);
    if (!resultEl) return;
    resultEl.style.display = 'block';
    resultEl.innerHTML = '<div class="fetch-loading">⏳ Fetching from CrossRef…</div>';
    try {
      const url  = (window.AUTOCITER?.doiUrl || '/api/doi/') + encodeURIComponent(doi);
      const resp = await fetch(url);
      const data = await resp.json();
      if (data.error) { resultEl.innerHTML = `<div class="fetch-error">❌ ${data.error}</div>`; return; }
      resultEl.innerHTML = buildRefCard(data, isStandalone);
      attachAddButtons(resultEl);
    } catch (e) {
      resultEl.innerHTML = `<div class="fetch-error">❌ ${e.message}</div>`;
    }
  }

  async function fetchPMID(pmid, resultId, isStandalone = false) {
    const resultEl = document.getElementById(resultId);
    if (!resultEl) return;
    resultEl.style.display = 'block';
    resultEl.innerHTML = '<div class="fetch-loading">⏳ Fetching from PubMed…</div>';
    try {
      const url  = (window.AUTOCITER?.pmidUrl || '/api/pmid/') + encodeURIComponent(pmid);
      const resp = await fetch(url);
      const data = await resp.json();
      if (data.error) { resultEl.innerHTML = `<div class="fetch-error">❌ ${data.error}</div>`; return; }
      resultEl.innerHTML = buildRefCard(data, isStandalone);
      attachAddButtons(resultEl);
    } catch (e) {
      resultEl.innerHTML = `<div class="fetch-error">❌ ${e.message}</div>`;
    }
  }

  function buildRefCard(data, isStandalone) {
    const authors = (data.authors || []).join('; ') || 'Unknown';
    const doi     = data.doi ? `<a href="${data.doi}" target="_blank" rel="noopener">${data.doi}</a>` : '';
    return `
      <div class="ref-result-card" data-ref='${JSON.stringify(data).replace(/'/g,"&#39;")}'>
        <div class="ref-result-title">${data.title || '—'}</div>
        <div class="ref-result-meta">
          <span>${authors}</span>
          ${data.year  ? `<span>· ${data.year}</span>` : ''}
          ${data.journal ? `<span>· <em>${data.journal}</em></span>` : ''}
        </div>
        ${doi ? `<div class="ref-result-doi">${doi}</div>` : ''}
        ${!isStandalone ? `<button class="btn-sm btn-add-ref" style="margin-top:.5rem">➕ Add to reference list</button>` : `
        <div class="ref-result-raw"><strong>Formatted:</strong><br><code>${data.raw || ''}</code></div>
        <button class="btn-sm" onclick="navigator.clipboard.writeText(this.previousElementSibling.querySelector('code').textContent).then(()=>showToast('Copied!'))">📋 Copy</button>`}
      </div>`;
  }

  function attachAddButtons(container) {
    container.querySelectorAll('.btn-add-ref').forEach(btn => {
      btn.addEventListener('click', () => {
        const card = btn.closest('.ref-result-card');
        const data = JSON.parse(card.dataset.ref.replace(/&#39;/g, "'"));
        addReference(data);
        btn.textContent = '✅ Added';
        btn.disabled = true;
      });
    });
  }

  // ── BibTeX parser ─────────────────────────────────────────────
  document.getElementById('btn-parse-bibtex')?.addEventListener('click', () => {
    const bib = document.getElementById('bibtex-input')?.value || '';
    const refs = parseBibTeX(bib);
    if (!refs.length) { showToast('⚠️ No valid BibTeX entries found.'); return; }
    refs.forEach(r => addReference(r));
    showToast(`✅ Imported ${refs.length} reference${refs.length > 1 ? 's' : ''} from BibTeX`);
    document.getElementById('bibtex-input').value = '';
  });

  function parseBibTeX(bibtex) {
    const results = [];
    const entryRe = /@\w+\s*\{[^@]+/g;
    const entries = bibtex.match(entryRe) || [];
    entries.forEach(entry => {
      const getField = k => {
        const m = entry.match(new RegExp(`${k}\\s*=\\s*[{"]([^}"]+)[}"]`, 'i'));
        return m ? m[1].trim() : null;
      };
      const authorStr = getField('author') || '';
      const authors   = authorStr ? authorStr.split(/\s+and\s+/i).map(a => a.trim()) : [];
      const title  = getField('title');
      const year   = getField('year');
      const journal= getField('journal') || getField('booktitle');
      const volume = getField('volume');
      const pages  = (getField('pages') || '').replace('--', '-');
      const doi    = getField('doi');
      if (title || authors.length) {
        results.push({ authors, year, title, journal, volume, pages, doi: doi ? `https://doi.org/${doi}` : null, raw: `${authors[0] || ''} (${year || 'n.d.'}). ${title || ''}.` });
      }
    });
    return results;
  }

  // ── Manual reference add ──────────────────────────────────────
  document.getElementById('btn-add-manual')?.addEventListener('click', () => {
    const text = document.getElementById('manual-input')?.value.trim();
    if (!text) return;
    addReference({ raw: text, authors: [], year: null, title: text });
    document.getElementById('manual-input').value = '';
    showToast('✅ Reference added');
  });

  function addReference(refData) {
    const ref = { ...refData, _localIdx: state.nextRefIdx++ };
    state.addedRefs.push(ref);
    renderAddedRefs();
    // Show section
    const sec = document.getElementById('added-refs-section');
    if (sec) sec.style.display = 'block';
    updateAddedCount();
  }

  function renderAddedRefs() {
    const list = document.getElementById('added-refs-list');
    if (!list) return;
    list.innerHTML = state.addedRefs.map((ref, i) => `
      <div class="added-ref-item" data-idx="${i}">
        <span class="added-ref-text">${ref.authors?.[0] || '?'} (${ref.year || 'n.d.'}) — ${truncate(ref.title || ref.raw || '', 60)}</span>
        <button class="btn-remove-ref" onclick="removeAddedRef(${i})" title="Remove">✕</button>
      </div>`).join('');
  }

  function updateAddedCount() {
    const badge = document.getElementById('added-refs-count');
    if (badge) badge.textContent = state.addedRefs.length;
  }

  // Expose globally
  window.removeAddedRef = (idx) => {
    state.addedRefs.splice(idx, 1);
    renderAddedRefs();
    updateAddedCount();
    if (!state.addedRefs.length) {
      const sec = document.getElementById('added-refs-section');
      if (sec) sec.style.display = 'none';
    }
  };

  // ── Deduplication ─────────────────────────────────────────────
  document.getElementById('btn-dedup')?.addEventListener('click', async () => {
    if (state.addedRefs.length < 2) { showToast('Need at least 2 references to deduplicate.'); return; }
    const before = state.addedRefs.length;
    // Client-side dedup: compare normalised titles + first-author surname + year
    const seen = new Set();
    state.addedRefs = state.addedRefs.filter(ref => {
      const key = [
        (ref.authors?.[0] || '').split(',')[0].toLowerCase().trim(),
        (ref.year || ''),
        (ref.title || '').toLowerCase().replace(/\s+/g, ' ').slice(0, 40),
        (ref.doi || '')
      ].join('|');
      if (seen.has(key)) return false;
      seen.add(key); return true;
    });
    const removed = before - state.addedRefs.length;
    renderAddedRefs(); updateAddedCount();
    showToast(removed > 0 ? `✅ Removed ${removed} duplicate${removed > 1 ? 's' : ''}` : 'No duplicates found.');
  });

  // ── Utilities ─────────────────────────────────────────────────
  function confTier(pct) {
    if (pct == null) return 'medium';
    if (pct >= 85) return 'high';
    if (pct >= 60) return 'medium';
    return 'low';
  }

  function truncate(str, max) {
    return str && str.length > max ? str.slice(0, max) + '…' : str;
  }

});

// ── Toast (global) ────────────────────────────────────────────────────────────
function showToast(msg, duration = 3000) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => requestAnimationFrame(() => t.classList.add('toast-show')));
  setTimeout(() => { t.classList.remove('toast-show'); setTimeout(() => t.remove(), 350); }, duration);
}

// ── History helper (global) ───────────────────────────────────────────────────
function saveToHistory(entry) {
  try {
    const h = JSON.parse(localStorage.getItem('autociter_history') || '[]');
    h.push({ ...entry, date: new Date().toISOString() });
    if (h.length > 50) h.splice(0, h.length - 50);
    localStorage.setItem('autociter_history', JSON.stringify(h));
  } catch (_) {}
}
