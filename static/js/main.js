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
    window._lastBodyText = '';  // reset
    if (!fileInput?.files?.[0]) return;
    btnPreview.textContent = '⏳ Detecting…';
    btnPreview.disabled = true;

    const fd = new FormData();
    fd.append('document', fileInput.files[0]);

    try {
      const resp = await fetch(window.AUTOCITER?.previewUrl || '/api/preview', { method: 'POST', body: fd });
      const data = await resp.json();
      if (data.error) { showToast('⚠️ ' + data.error); return; }
      window._lastPreviewData = data;
      window._lastBodyText    = data.body_text || '';
      renderPreviewModal(data);
      openModal();
      renderSidePanel(data);
      advanceStep(3);
      // Show AI suggest button if AI available
      if (window.AUTOCITER?.aiAvailable) {
        const suggestBtn = document.getElementById('btn-ai-suggest');
        if (suggestBtn) suggestBtn.style.display = 'block';
      }
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

    // Detection mode banner
    const det = data.detection || {};
    const modeInfo = {
      numbered:    { icon: '🔢', label: 'Numbered citations detected',  cls: 'mode-numbered',    text: 'Your document already has [1] [2] style markers — we will reformat them to your chosen style.' },
      superscript: { icon: '¹²', label: 'Superscript citations detected', cls: 'mode-numbered',   text: 'Superscript markers (¹²³) found — bibliography will be reformatted.' },
      author_year: { icon: '👤', label: 'Author-year citations detected', cls: 'mode-author-year', text: 'Your document already has (Author, Year) markers — we will reformat them.' },
      none:        { icon: '✨', label: 'No existing citations',          cls: 'mode-none',        text: 'No inline citations found — will insert from author+year matching.' },
    };
    const mi = modeInfo[det.mode] || modeInfo.none;
    const banner = `
      <div class="detection-banner ${mi.cls}">
        <span class="det-icon">${mi.icon}</span>
        <div>
          <div class="det-label">${mi.label}</div>
          <div class="det-desc">${det.description || mi.text}</div>
          ${det.examples?.length ? `<div class="det-examples">e.g. ${det.examples.slice(0,3).map(e=>`<code>${e}</code>`).join(' ')}</div>` : ''}
          ${det.mode === 'numbered' ? `<div class="det-tip">💡 Tip: Switch style to <strong>Vancouver</strong> or <strong>IEEE</strong> to keep numbered format</div>` : ''}
        </div>
      </div>`;

    list.innerHTML = banner + data.refs.map(ref => `
      <div class="modal-ref-item">
        <div class="modal-ref-idx">[${ref.index}]</div>
        <div class="modal-ref-body">
          <div class="modal-ref-author">${ref.authors?.[0] || 'Unknown'}${ref.authors?.length > 1 ? ' <em>et al.</em>' : ''}</div>
          <div class="modal-ref-year">${ref.year || 'n.d.'}${ref.title ? ' — ' + truncate(ref.title, 60) : ''}
            ${ref.ref_type && ref.ref_type !== 'article' ? `<span class="ref-type-badge">${ref.ref_type}</span>` : ''}
          </div>
        </div>
        <span class="ref-badge badge-${confTier(ref.confidence)}">${ref.confidence > 0 ? ref.confidence + '%' : ref.cited ? '✓' : '?'}</span>
      </div>`).join('');
  }

  function renderSidePanel(data) {
    const panel = document.getElementById('preview-panel');
    const list  = document.getElementById('ref-preview-list');
    const badge = document.getElementById('ref-count-badge');
    if (!panel || !data.refs) return;
    panel.style.display = 'block';
    if (badge) badge.textContent = data.refs.length;

    // Show detection mode in side panel
    const det = data.detection || {};
    const modeColors = { numbered: 'var(--accent)', author_year: '#a371f7', none: 'var(--green)', superscript: 'var(--amber)' };
    const modeLabels = { numbered: '🔢 Numbered', author_year: '👤 Author-year', none: '✨ No citations', superscript: '¹² Superscript' };
    const modeEl = document.getElementById('detected-mode-badge');
    if (modeEl) {
      modeEl.textContent = modeLabels[det.mode] || '? Unknown';
      modeEl.style.background = modeColors[det.mode] || 'var(--surface3)';
      modeEl.style.display = 'inline-block';
    }

    if (list) {
      list.innerHTML = data.refs.slice(0, 8).map(ref => `
        <div class="ref-preview-item">
          <span class="ref-preview-idx">[${ref.index}]</span>
          <span class="ref-preview-text">${ref.authors?.[0] || 'Unknown'} (${ref.year || 'n.d.'})</span>
          <span class="ref-badge badge-${confTier(ref.confidence)}">${ref.cited ? (ref.confidence > 0 ? ref.confidence+'%' : '✓') : '?'}</span>
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

  // ── AI language detector ──────────────────────────────────────
  const aiLangDrop = document.getElementById('ai-lang-drop-zone');
  const aiLangFile = document.getElementById('ai-lang-file-input');
  const aiLangInfo = document.getElementById('ai-lang-file-info');
  const aiLangText = document.getElementById('ai-lang-text');
  const aiLangBtn = document.getElementById('btn-ai-lang-detect');
  const aiLangResult = document.getElementById('ai-lang-result');

  if (aiLangDrop && aiLangFile) {
    aiLangDrop.addEventListener('click', () => aiLangFile.click());
    aiLangFile.addEventListener('change', () => setAiLangFileInfo(aiLangFile.files[0]));
    aiLangDrop.addEventListener('dragover', e => { e.preventDefault(); aiLangDrop.classList.add('drag-over'); });
    aiLangDrop.addEventListener('dragleave', () => aiLangDrop.classList.remove('drag-over'));
    aiLangDrop.addEventListener('drop', e => {
      e.preventDefault();
      aiLangDrop.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (!file) return;
      try {
        const dt = new DataTransfer();
        dt.items.add(file);
        aiLangFile.files = dt.files;
      } catch (_) {}
      setAiLangFileInfo(file);
    });
  }

  function setAiLangFileInfo(file) {
    if (!aiLangInfo || !file) return;
    aiLangInfo.textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
    aiLangInfo.style.color = 'var(--green)';
  }

  aiLangBtn?.addEventListener('click', async () => {
    const text = aiLangText?.value.trim() || '';
    const file = aiLangFile?.files?.[0];
    if (!text && !file) {
      showToast('Paste text or upload a document first.');
      return;
    }

    aiLangBtn.disabled = true;
    aiLangBtn.querySelector('.btn-text').textContent = 'Checking...';
    if (aiLangResult) {
      aiLangResult.style.display = 'block';
      aiLangResult.innerHTML = '<div class="fetch-loading">Analysing language patterns...</div>';
    }

    try {
      let resp;
      if (file) {
        const fd = new FormData();
        fd.append('document', file);
        resp = await fetch(window.AUTOCITER?.aiLanguageUrl || '/api/ai-language/detect', { method: 'POST', body: fd });
      } else {
        resp = await fetch(window.AUTOCITER?.aiLanguageUrl || '/api/ai-language/detect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, filename: 'pasted text' })
        });
      }
      const data = await resp.json();
      renderAiLanguageResult(data);
    } catch (e) {
      if (aiLangResult) aiLangResult.innerHTML = `<div class="fetch-error">${escapeHtml(e.message)}</div>`;
    } finally {
      aiLangBtn.disabled = false;
      aiLangBtn.querySelector('.btn-text').textContent = 'Check AI Language';
    }
  });

  function renderAiLanguageResult(data) {
    if (!aiLangResult) return;
    aiLangResult.style.display = 'block';
    if (data.error) {
      aiLangResult.innerHTML = `<div class="fetch-error">${escapeHtml(data.error)}</div>`;
      return;
    }

    const pct = data.overall_percent || 0;
    const tier = pct >= 65 ? 'high' : (pct >= 40 ? 'medium' : 'low');
    const locations = data.locations || [];
    const signals = data.signals || {};
    const paragraphs = data.paragraphs || [];
    aiLangResult.innerHTML = `
      <div class="ai-lang-score-card ai-lang-${tier}">
        <div class="ai-lang-score">
          <strong>${pct}%</strong>
          <span>AI-language signal</span>
        </div>
        <div class="ai-lang-summary">
          <div>${escapeHtml(data.summary || '')}</div>
          <small>${data.ai_like_words || 0} weighted AI-like words across ${data.total_words || 0} total words</small>
        </div>
      </div>
      <div class="ai-lang-note">${escapeHtml(data.confidence_note || '')}</div>
      <div class="ai-lang-signals">
        ${Object.entries(signals).map(([name, value]) => renderAiLanguageSignal(name, value)).join('')}
      </div>
      ${paragraphs.length ? `
      <div class="ai-lang-paragraphs">
        <div class="section-label">Highest-risk paragraphs <span class="badge">${paragraphs.length}</span></div>
        ${paragraphs.slice(0, 8).map(renderAiLanguageParagraph).join('')}
      </div>` : ''}
      <div class="ai-lang-locations">
        <div class="section-label">Flagged locations <span class="badge">${locations.length}</span></div>
        ${locations.length ? locations.map(renderAiLanguageLocation).join('') : '<div class="fetch-empty">No strong AI-language locations found.</div>'}
      </div>`;
  }

  function renderAiLanguageSignal(name, value) {
    const label = name.replace(/_/g, ' ');
    return `
      <div class="ai-lang-signal">
        <div class="ai-lang-signal-top"><span>${escapeHtml(label)}</span><strong>${value}%</strong></div>
        <div class="ai-lang-meter"><span style="width:${Math.max(0, Math.min(100, value))}%"></span></div>
      </div>`;
  }

  function renderAiLanguageParagraph(item) {
    return `
      <div class="ai-lang-para ai-lang-${item.tier || 'low'}">
        <strong>${item.percent}%</strong>
        <span>Paragraph ${item.paragraph}</span>
        <small>${item.word_count} words, ${item.flagged_sentences} flagged sentence(s)</small>
      </div>`;
  }

  function renderAiLanguageLocation(item) {
    const reasons = (item.reasons || []).map(r => `<span class="ai-lang-reason">${escapeHtml(r)}</span>`).join('');
    const evidence = item.evidence || {};
    const evidenceHtml = Object.entries(evidence).map(([k, v]) =>
      `<span class="ai-lang-evidence">${escapeHtml(k.replace(/_/g, ' '))}: ${v}%</span>`
    ).join('');
    return `
      <div class="ai-lang-location ai-lang-${item.tier || 'low'}">
        <div class="ai-lang-location-head">
          <strong>${item.percent}%</strong>
          <span>Line ${item.line}, paragraph ${item.paragraph}</span>
        </div>
        <p>${escapeHtml(item.text)}</p>
        <div class="ai-lang-evidence-row">${evidenceHtml}</div>
        <div class="ai-lang-reasons">${reasons}</div>
      </div>`;
  }

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

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
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


// ── AI Features ───────────────────────────────────────────────────────────────

async function aiRequest(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  return resp.json();
}

function renderAiResult(container, data, type='parse') {
  if (!container) return;
  container.style.display = 'block';
  if (data.error) {
    container.innerHTML = `<div class="ai-error">❌ ${data.error}</div>`;
    return;
  }
  const d = data.data || data;
  if (type === 'parse' || type === 'complete') {
    const authors = (d.authors || []).join('; ') || '—';
    container.innerHTML = `
      <div class="ai-parsed-card">
        <div class="ai-parsed-row"><span class="ai-field-label">Authors</span><span>${authors}</span></div>
        <div class="ai-parsed-row"><span class="ai-field-label">Year</span><span>${d.year || '—'}</span></div>
        <div class="ai-parsed-row"><span class="ai-field-label">Title</span><span>${d.title || '—'}</span></div>
        <div class="ai-parsed-row"><span class="ai-field-label">Journal</span><span>${d.journal || '—'}</span></div>
        ${d.volume ? `<div class="ai-parsed-row"><span class="ai-field-label">Volume</span><span>${d.volume}${d.issue ? '('+d.issue+')' : ''}</span></div>` : ''}
        ${d.pages  ? `<div class="ai-parsed-row"><span class="ai-field-label">Pages</span><span>${d.pages}</span></div>` : ''}
        ${d.doi    ? `<div class="ai-parsed-row"><span class="ai-field-label">DOI</span><a href="${d.doi}" target="_blank">${d.doi}</a></div>` : ''}
        <div style="margin-top:.6rem;display:flex;gap:.5rem">
          <button class="btn-sm" onclick="addAiParsedRef(${JSON.stringify(d).replace(/"/g,'&quot;')})">➕ Add to list</button>
          <button class="btn-sm" onclick="navigator.clipboard.writeText(document.getElementById('ai-parse-input')?.value||'').then(()=>showToast('Copied'))">📋 Copy raw</button>
        </div>
      </div>`;
  } else if (type === 'style') {
    container.innerHTML = `
      <div class="ai-parsed-card">
        <div class="ai-parsed-row"><span class="ai-field-label">Detected Style</span><strong style="color:var(--accent)">${d.style || '—'}</strong></div>
        <div class="ai-parsed-row"><span class="ai-field-label">Explanation</span><span>${d.explanation || '—'}</span></div>
      </div>`;
  }
}

window.addAiParsedRef = function(refData) {
  if (typeof refData === 'string') { try { refData = JSON.parse(refData); } catch(e) { return; } }
  addReference({ ...refData, raw: refData.title || 'AI-parsed reference' });
  showToast('✅ Added to reference list');
};

// AI Parse button (manual tab)
document.getElementById('btn-ai-parse')?.addEventListener('click', async () => {
  const text = document.getElementById('manual-input')?.value.trim();
  if (!text) { showToast('⚠️ Enter a reference first'); return; }
  const btn = document.getElementById('btn-ai-parse');
  btn.textContent = '⏳ Parsing…'; btn.disabled = true;
  const resultEl = document.getElementById('ai-parse-result');
  try {
    const data = await aiRequest(window.AUTOCITER.aiParseUrl, { text });
    renderAiResult(resultEl, data, 'parse');
  } finally { btn.textContent = '🤖 AI Parse'; btn.disabled = false; }
});

// AI Detect Style (manual tab)
document.getElementById('btn-ai-detect-style')?.addEventListener('click', async () => {
  const text = document.getElementById('manual-input')?.value.trim();
  if (!text) { showToast('⚠️ Enter a reference first'); return; }
  const btn = document.getElementById('btn-ai-detect-style');
  btn.textContent = '⏳…'; btn.disabled = true;
  const resultEl = document.getElementById('ai-parse-result');
  try {
    const data = await aiRequest(window.AUTOCITER.aiDetectUrl, { text });
    renderAiResult(resultEl, data, 'style');
  } finally { btn.textContent = '🔍 Detect Style'; btn.disabled = false; }
});

// AI Suggest missing citations (preview panel)
document.getElementById('btn-ai-suggest')?.addEventListener('click', async () => {
  const btn = document.getElementById('btn-ai-suggest');
  const panel = document.getElementById('ai-suggest-results');
  btn.textContent = '⏳ Analysing…'; btn.disabled = true;
  try {
    // Send parsed refs + body via JSON (body stored in state from last preview)
    if (!window._lastPreviewData) { showToast('Preview first to load references'); return; }
    const data = await aiRequest(window.AUTOCITER.aiSuggestUrl, {
      body: window._lastBodyText || '',
      refs: window._lastPreviewData.refs || []
    });
    if (!panel) return;
    panel.style.display = 'block';
    if (data.error || !data.suggestions?.length) {
      panel.innerHTML = `<div class="ai-suggest-empty">${data.error ? '❌ '+data.error : '✅ No missing citations detected — good coverage!'}</div>`;
      return;
    }
    panel.innerHTML = `<div class="ai-suggest-label">🤖 AI found ${data.count} potentially uncited claim${data.count > 1 ? 's' : ''}:</div>` +
      data.suggestions.map(s => `
        <div class="ai-suggest-item suggest-${s.confidence}">
          <div class="suggest-sentence">"…${s.sentence}…"</div>
          <div class="suggest-reason">${s.reason}</div>
          <span class="suggest-conf suggest-${s.confidence}">${s.confidence === 'high' ? '🔴 High priority' : '🟡 Medium'}</span>
        </div>`).join('');
  } finally { btn.textContent = '🤖 Find missing citations with AI'; btn.disabled = false; }
});

// Standalone AI tab: Parse
document.getElementById('btn-ai-parse-standalone')?.addEventListener('click', async () => {
  const text = document.getElementById('ai-parse-input')?.value.trim();
  if (!text) { showToast('⚠️ Enter a reference first'); return; }
  const btn = document.getElementById('btn-ai-parse-standalone');
  btn.textContent = '⏳ Parsing…'; btn.disabled = true;
  try {
    const data = await aiRequest(window.AUTOCITER.aiParseUrl, { text });
    renderAiResult(document.getElementById('ai-parse-standalone-result'), data, 'parse');
  } finally { btn.textContent = '🤖 Parse with Gemini'; btn.disabled = false; }
});

// Standalone AI tab: Complete
document.getElementById('btn-ai-complete')?.addEventListener('click', async () => {
  const author  = document.getElementById('ai-comp-author')?.value.trim();
  const year    = document.getElementById('ai-comp-year')?.value.trim();
  const title   = document.getElementById('ai-comp-title')?.value.trim();
  const journal = document.getElementById('ai-comp-journal')?.value.trim();
  if (!title && !author) { showToast('⚠️ Provide at least an author or title'); return; }
  const btn = document.getElementById('btn-ai-complete');
  btn.textContent = '⏳ Completing…'; btn.disabled = true;
  const partial = {};
  if (author)  partial.authors = [author];
  if (year)    partial.year    = year;
  if (title)   partial.title   = title;
  if (journal) partial.journal = journal;
  try {
    const data = await aiRequest(window.AUTOCITER.aiCompleteUrl, { partial });
    renderAiResult(document.getElementById('ai-complete-result'), data, 'complete');
  } finally { btn.textContent = '🤖 Complete Reference'; btn.disabled = false; }
});

// Standalone AI tab: Detect style
document.getElementById('btn-ai-detect')?.addEventListener('click', async () => {
  const text = document.getElementById('ai-style-input')?.value.trim();
  if (!text) { showToast('⚠️ Enter a reference first'); return; }
  const btn = document.getElementById('btn-ai-detect');
  btn.textContent = '⏳…'; btn.disabled = true;
  try {
    const data = await aiRequest(window.AUTOCITER.aiDetectUrl, { text });
    renderAiResult(document.getElementById('ai-style-result'), data, 'style');
  } finally { btn.textContent = '🔍 Identify Style'; btn.disabled = false; }
});

// Store preview data for AI suggest
const _origFetchPreview = window._fetchPreviewFn;
