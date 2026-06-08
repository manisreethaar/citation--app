"""
app.py  ─  Flask web interface for auto-citer
=============================================
Run:   python app.py
Then:  http://localhost:5000
"""

import os
import sys
import tempfile
from pathlib import Path

# Make sure our modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import (
    Flask, request, render_template_string, send_file,
    flash, redirect, url_for, jsonify
)
from werkzeug.utils import secure_filename
from auto_citer import process_document, build_report, SUPPORTED_STYLES, MAX_FILE_SIZE
from reference_parser import split_references_from_body, parse_references
from citation_styles import inline_citation

app = Flask(__name__)
# Load secret key from environment variable, fall back to a generated one for dev
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)

UPLOAD_FOLDER = tempfile.mkdtemp(prefix='auto_citer_')
ALLOWED_EXTENSIONS = {'docx', 'pdf', 'txt'}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── HTML Template ────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Auto-Citer: Automatically insert APA, Vancouver, IEEE, Nature, MLA, and Chicago citations into your research documents.">
  <title>Auto-Citer — Smart Academic Citation Tool</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:       #0d1117;
      --surface:  #161b22;
      --surface2: #1c2330;
      --border:   #30363d;
      --accent:   #58a6ff;
      --accent2:  #3d8bcd;
      --green:    #3fb950;
      --red:      #f85149;
      --amber:    #d29922;
      --text:     #e6edf3;
      --text-sub: #8b949e;
      --radius:   14px;
      --shadow:   0 8px 32px rgba(0,0,0,.45);
    }

    html { scroll-behavior: smooth; }

    body {
      font-family: 'Inter', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      line-height: 1.6;
    }

    /* ── Hero ── */
    .hero {
      background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d2137 100%);
      border-bottom: 1px solid var(--border);
      padding: 3.5rem 1rem 3rem;
      text-align: center;
      position: relative;
      overflow: hidden;
    }
    .hero::before {
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(ellipse 80% 60% at 50% -10%, rgba(88,166,255,.12) 0%, transparent 70%);
      pointer-events: none;
    }
    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: .5rem;
      background: rgba(88,166,255,.1);
      border: 1px solid rgba(88,166,255,.25);
      border-radius: 100px;
      padding: .3rem .9rem;
      font-size: .75rem;
      font-weight: 600;
      color: var(--accent);
      letter-spacing: .04em;
      text-transform: uppercase;
      margin-bottom: 1.25rem;
    }
    .hero h1 {
      font-size: clamp(2rem, 5vw, 3.2rem);
      font-weight: 800;
      letter-spacing: -.03em;
      background: linear-gradient(135deg, #e6edf3 30%, #58a6ff 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: .75rem;
    }
    .hero p {
      color: var(--text-sub);
      font-size: 1.05rem;
      max-width: 520px;
      margin: 0 auto;
    }

    /* ── Layout ── */
    .container {
      max-width: 820px;
      margin: 0 auto;
      padding: 2rem 1rem 4rem;
    }

    /* ── Cards ── */
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.75rem;
      margin-bottom: 1.25rem;
      transition: border-color .2s;
    }
    .card:hover { border-color: #3d444d; }

    .card-header {
      display: flex;
      align-items: center;
      gap: .75rem;
      margin-bottom: 1.25rem;
    }
    .step-badge {
      width: 28px; height: 28px;
      background: rgba(88,166,255,.15);
      border: 1px solid rgba(88,166,255,.3);
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: .8rem; font-weight: 700; color: var(--accent);
      flex-shrink: 0;
    }
    .card-header h2 {
      font-size: 1rem;
      font-weight: 600;
      color: var(--text);
    }

    /* ── Drop zone ── */
    .drop-zone {
      border: 2px dashed var(--border);
      border-radius: 10px;
      padding: 2.5rem 1.5rem;
      text-align: center;
      cursor: pointer;
      transition: all .2s;
      background: var(--surface2);
      position: relative;
    }
    .drop-zone:hover, .drop-zone.drag-over {
      border-color: var(--accent);
      background: rgba(88,166,255,.06);
    }
    .drop-zone-icon {
      font-size: 2.5rem;
      margin-bottom: .75rem;
      display: block;
      filter: grayscale(.4);
      transition: filter .2s;
    }
    .drop-zone:hover .drop-zone-icon { filter: grayscale(0); }
    .drop-zone p { color: var(--text-sub); font-size: .95rem; }
    .drop-zone .browse { color: var(--accent); text-decoration: underline; cursor: pointer; }
    #file-input { display: none; }
    #file-name {
      margin-top: .75rem;
      font-size: .85rem;
      color: var(--green);
      font-weight: 500;
      min-height: 1.2em;
    }
    .file-type-tags {
      display: flex;
      justify-content: center;
      gap: .5rem;
      margin-top: .6rem;
      flex-wrap: wrap;
    }
    .file-tag {
      background: rgba(255,255,255,.05);
      border: 1px solid var(--border);
      border-radius: 100px;
      padding: .15rem .55rem;
      font-size: .72rem;
      color: var(--text-sub);
      font-weight: 500;
    }

    /* ── Style grid ── */
    .style-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: .75rem;
    }
    .style-card {
      border: 1.5px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.1rem;
      cursor: pointer;
      transition: all .15s;
      background: var(--surface2);
      position: relative;
    }
    .style-card:hover { border-color: var(--accent); background: rgba(88,166,255,.05); }
    .style-card input[type=radio] { display: none; }
    .style-card.selected {
      border-color: var(--accent);
      background: rgba(88,166,255,.1);
      box-shadow: 0 0 0 3px rgba(88,166,255,.12);
    }
    .style-card.selected::after {
      content: '✓';
      position: absolute;
      top: .55rem; right: .7rem;
      font-size: .8rem;
      color: var(--accent);
      font-weight: 700;
    }
    .style-name  { font-weight: 700; font-size: .95rem; color: var(--text); }
    .style-desc  { font-size: .8rem; color: var(--text-sub); margin-top: .2rem; }
    .style-example {
      font-size: .75rem;
      color: var(--accent);
      margin-top: .5rem;
      font-family: 'Courier New', monospace;
      background: rgba(88,166,255,.08);
      border-radius: 4px;
      padding: .25rem .5rem;
      display: inline-block;
    }

    /* ── Options ── */
    .toggle-label {
      display: flex;
      align-items: center;
      gap: .75rem;
      cursor: pointer;
      padding: .75rem 1rem;
      border-radius: 8px;
      background: var(--surface2);
      border: 1px solid var(--border);
      transition: border-color .15s;
      user-select: none;
    }
    .toggle-label:hover { border-color: var(--accent); }
    .toggle-label input[type=checkbox] { display: none; }
    .toggle {
      width: 36px; height: 20px;
      background: var(--border);
      border-radius: 100px;
      position: relative;
      transition: background .2s;
      flex-shrink: 0;
    }
    .toggle::after {
      content: '';
      position: absolute;
      top: 3px; left: 3px;
      width: 14px; height: 14px;
      background: white;
      border-radius: 50%;
      transition: transform .2s;
    }
    .toggle-label input:checked + .toggle { background: var(--accent); }
    .toggle-label input:checked + .toggle::after { transform: translateX(16px); }
    .toggle-text { font-size: .9rem; color: var(--text); }
    .toggle-sub  { font-size: .78rem; color: var(--text-sub); }

    /* ── Alerts ── */
    .alert {
      display: flex;
      align-items: flex-start;
      gap: .75rem;
      padding: .9rem 1.1rem;
      border-radius: 10px;
      margin-bottom: 1.1rem;
      font-size: .9rem;
      border: 1px solid;
    }
    .alert-error   { background: rgba(248,81,73,.08);  border-color: rgba(248,81,73,.3);  color: #ff7b72; }
    .alert-success { background: rgba(63,185,80,.08);  border-color: rgba(63,185,80,.3);  color: #7ee787; }
    .alert-info    { background: rgba(88,166,255,.08); border-color: rgba(88,166,255,.3); color: var(--accent); }

    /* ── How it works info box ── */
    .info-box {
      background: rgba(210,153,34,.06);
      border: 1px solid rgba(210,153,34,.25);
      border-radius: 10px;
      padding: 1rem 1.25rem;
      font-size: .87rem;
      color: #e3b341;
    }
    .info-box strong { display: block; margin-bottom: .5rem; font-size: .92rem; }
    .info-box ol { padding-left: 1.25rem; }
    .info-box li { margin-bottom: .3rem; color: #c9a227; }

    /* ── Submit button ── */
    .btn-submit {
      width: 100%;
      padding: 1rem;
      font-size: 1rem;
      font-weight: 700;
      background: linear-gradient(135deg, #2d7dd2, #58a6ff);
      color: white;
      border: none;
      border-radius: 10px;
      cursor: pointer;
      transition: all .2s;
      letter-spacing: -.01em;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: .6rem;
      box-shadow: 0 4px 15px rgba(88,166,255,.3);
    }
    .btn-submit:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(88,166,255,.45);
    }
    .btn-submit:active { transform: translateY(0); }
    .btn-submit:disabled {
      background: var(--surface2);
      color: var(--text-sub);
      cursor: not-allowed;
      box-shadow: none;
      transform: none;
    }

    /* ── Processing overlay ── */
    #processing-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(13,17,23,.85);
      backdrop-filter: blur(4px);
      z-index: 999;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1.5rem;
    }
    #processing-overlay.visible { display: flex; }
    .spinner-ring {
      width: 60px; height: 60px;
      border: 4px solid rgba(88,166,255,.2);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .processing-text { color: var(--text); font-size: 1.1rem; font-weight: 600; }
    .processing-sub  { color: var(--text-sub); font-size: .88rem; }

    /* ── Stats row ── */
    .stats-row {
      display: flex;
      gap: .75rem;
      margin-bottom: 1.25rem;
      flex-wrap: wrap;
    }
    .stat-pill {
      flex: 1;
      min-width: 120px;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: .9rem 1rem;
      text-align: center;
    }
    .stat-num  { font-size: 1.6rem; font-weight: 800; color: var(--accent); }
    .stat-label{ font-size: .75rem; color: var(--text-sub); margin-top: .1rem; }

    /* ── Footer ── */
    footer {
      text-align: center;
      padding: 2rem;
      color: var(--text-sub);
      font-size: .82rem;
      border-top: 1px solid var(--border);
    }
    footer a { color: var(--accent); text-decoration: none; }

    /* ── Responsive ── */
    @media (max-width: 600px) {
      .style-grid { grid-template-columns: 1fr 1fr; }
      .hero { padding: 2.5rem 1rem 2rem; }
      .card { padding: 1.25rem; }
    }
  </style>
</head>
<body>

<!-- Processing overlay -->
<div id="processing-overlay">
  <div class="spinner-ring"></div>
  <div>
    <div class="processing-text">Processing your document…</div>
    <div class="processing-sub">Matching references and inserting citations</div>
  </div>
</div>

<!-- Hero -->
<div class="hero">
  <div class="hero-badge">✦ Academic Tool</div>
  <h1>📚 Auto-Citer</h1>
  <p>Automatically detect and insert citations into your research documents — APA, Vancouver, IEEE, Nature, MLA &amp; Chicago.</p>
</div>

<div class="container">

  <!-- Stats row -->
  <div class="stats-row">
    <div class="stat-pill">
      <div class="stat-num">6</div>
      <div class="stat-label">Citation Styles</div>
    </div>
    <div class="stat-pill">
      <div class="stat-num">3</div>
      <div class="stat-label">File Formats</div>
    </div>
    <div class="stat-pill">
      <div class="stat-num">∞</div>
      <div class="stat-label">References</div>
    </div>
    <div class="stat-pill">
      <div class="stat-num">0</div>
      <div class="stat-label">Manual Work</div>
    </div>
  </div>

  <!-- Flash messages -->
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }}">
        <span>{{ '✗' if cat == 'error' else '✓' }}</span>
        <span>{{ msg }}</span>
      </div>
    {% endfor %}
  {% endwith %}

  <!-- How it works -->
  <div class="info-box" style="margin-bottom: 1.25rem;">
    <strong>💡 How it works</strong>
    <ol>
      <li>Upload a document with a body text <strong>and</strong> a "References" section at the end.</li>
      <li>The tool detects every reference, scans the body for author name &amp; year mentions.</li>
      <li>Citations are inserted automatically and the bibliography is reformatted to your chosen style.</li>
    </ol>
  </div>

  <form method="POST" action="/process" enctype="multipart/form-data" id="upload-form">

    <!-- Step 1: Upload -->
    <div class="card">
      <div class="card-header">
        <div class="step-badge">1</div>
        <h2>Upload your document</h2>
      </div>
      <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
        <span class="drop-zone-icon">📄</span>
        <p>Drag &amp; drop your file here, or <span class="browse">browse</span></p>
        <div class="file-type-tags">
          <span class="file-tag">.docx</span>
          <span class="file-tag">.pdf</span>
          <span class="file-tag">.txt</span>
          <span class="file-tag">Max {{ max_size_mb }} MB</span>
        </div>
        <div id="file-name"></div>
      </div>
      <input type="file" id="file-input" name="document" accept=".docx,.pdf,.txt">
    </div>

    <!-- Step 2: Style -->
    <div class="card">
      <div class="card-header">
        <div class="step-badge">2</div>
        <h2>Choose citation style</h2>
      </div>
      <div class="style-grid" id="style-grid">
        <label class="style-card selected" id="card-apa">
          <input type="radio" name="style" value="apa" checked>
          <div class="style-name">APA 7th</div>
          <div class="style-desc">Author–year · Social sciences</div>
          <div class="style-example">(Smith et al., 2020)</div>
        </label>
        <label class="style-card" id="card-vancouver">
          <input type="radio" name="style" value="vancouver">
          <div class="style-name">Vancouver</div>
          <div class="style-desc">Numbered · Biomedical journals</div>
          <div class="style-example">[1], [2], [3]</div>
        </label>
        <label class="style-card" id="card-ieee">
          <input type="radio" name="style" value="ieee">
          <div class="style-name">IEEE</div>
          <div class="style-desc">Numbered · Engineering &amp; CS</div>
          <div class="style-example">[1], [2], [3]</div>
        </label>
        <label class="style-card" id="card-nature">
          <input type="radio" name="style" value="nature">
          <div class="style-name">Nature / Cell</div>
          <div class="style-desc">Superscript · High-impact science</div>
          <div class="style-example">¹·² or [1]</div>
        </label>
        <label class="style-card" id="card-mla">
          <input type="radio" name="style" value="mla">
          <div class="style-name">MLA 9th</div>
          <div class="style-desc">Author-page · Humanities</div>
          <div class="style-example">(Smith 42)</div>
        </label>
        <label class="style-card" id="card-chicago">
          <input type="radio" name="style" value="chicago">
          <div class="style-name">Chicago 17th</div>
          <div class="style-desc">Author-date · History &amp; arts</div>
          <div class="style-example">(Smith 2020)</div>
        </label>
      </div>
    </div>

    <!-- Step 3: Options -->
    <div class="card">
      <div class="card-header">
        <div class="step-badge">3</div>
        <h2>Options</h2>
      </div>
      <label class="toggle-label">
        <input type="checkbox" name="report" value="1" id="report-cb">
        <span class="toggle"></span>
        <span>
          <div class="toggle-text">Generate citation match report</div>
          <div class="toggle-sub">Appended to the downloaded document showing which references were found</div>
        </span>
      </label>
    </div>

    <!-- Submit -->
    <button type="submit" class="btn-submit" id="submit-btn">
      <span>✨</span>
      <span>Insert Citations &amp; Download</span>
    </button>

  </form>
</div>

<footer>
  <p>Auto-Citer &mdash; Open source academic citation tool &middot;
    <a href="https://github.com/manisreethaar/citation--app" target="_blank" rel="noopener">GitHub</a>
  </p>
</footer>

<script>
// ── Drag & drop ──────────────────────────────────────────────────────────────
const dz  = document.getElementById('drop-zone');
const fi  = document.getElementById('file-input');
const fn  = document.getElementById('file-name');

fi.addEventListener('change', () => updateFileName(fi.files[0]));

dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
dz.addEventListener('drop', e => {
  e.preventDefault();
  dz.classList.remove('drag-over');
  if (e.dataTransfer.files.length) {
    const dt = new DataTransfer();
    dt.items.add(e.dataTransfer.files[0]);
    fi.files = dt.files;
    updateFileName(fi.files[0]);
  }
});

function updateFileName(file) {
  if (!file) { fn.textContent = ''; return; }
  const sizeKB = (file.size / 1024).toFixed(0);
  fn.textContent = `📎 ${file.name}  (${sizeKB} KB)`;
}

// ── Style card selection ──────────────────────────────────────────────────────
document.querySelectorAll('.style-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.style-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    card.querySelector('input[type=radio]').checked = true;
  });
});

// ── Form submit → overlay ────────────────────────────────────────────────────
document.getElementById('upload-form').addEventListener('submit', function(e) {
  if (!fi.files || !fi.files[0]) {
    e.preventDefault();
    fn.textContent = '⚠️  Please select a file first.';
    fn.style.color = '#f85149';
    return;
  }
  document.getElementById('processing-overlay').classList.add('visible');
  document.getElementById('submit-btn').disabled = true;
});
</script>
</body>
</html>"""


@app.route('/', methods=['GET'])
def index():
    return render_template_string(
        HTML,
        max_size_mb=MAX_FILE_SIZE // 1024 // 1024,
        supported_styles=SUPPORTED_STYLES,
    )


@app.route('/process', methods=['POST'])
def process():
    # ── Validate upload ───────────────────────────────────────────────────────
    if 'document' not in request.files:
        flash('No file uploaded.', 'error')
        return redirect(url_for('index'))

    f = request.files['document']
    if not f or f.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not allowed_file(f.filename):
        flash('Unsupported file type. Please upload .docx, .pdf, or .txt', 'error')
        return redirect(url_for('index'))

    # ── Save upload ───────────────────────────────────────────────────────────
    filename = secure_filename(f.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(input_path)

    # ── Check file size ───────────────────────────────────────────────────────
    if os.path.getsize(input_path) > MAX_FILE_SIZE:
        os.remove(input_path)
        flash(
            f'File too large. Maximum allowed size is {MAX_FILE_SIZE // 1024 // 1024} MB.',
            'error'
        )
        return redirect(url_for('index'))

    # ── Derive output path ────────────────────────────────────────────────────
    style     = request.form.get('style', 'apa').lower()
    do_report = request.form.get('report') == '1'

    if style not in SUPPORTED_STYLES:
        flash(f'Unknown citation style "{style}".', 'error')
        return redirect(url_for('index'))

    stem      = Path(filename).stem
    ext       = Path(filename).suffix
    out_name  = f"{stem}_cited_{style}{ext}"
    output_path = os.path.join(UPLOAD_FOLDER, out_name)

    # ── Process ───────────────────────────────────────────────────────────────
    try:
        result_path = process_document(
            input_path, style, output_path, print_report=False
        )

        # Optionally append a match report for text-based outputs
        if do_report and ext.lower() in ('.txt',):
            try:
                from auto_citer import build_report as _build_report
                from reference_parser import split_references_from_body, parse_references
                from citation_styles import inline_citation as _ic
                from file_handlers import read_text

                full_text = read_text(input_path)
                body, ref_section = split_references_from_body(full_text)
                refs = parse_references(ref_section)
                if refs:
                    cited_text = read_text(result_path)
                    report = _build_report(body, cited_text, refs, style)
                    with open(result_path, 'a', encoding='utf-8') as fout:
                        fout.write('\n\n' + report)
            except Exception:
                pass   # report generation is non-critical

        return send_file(
            result_path,
            as_attachment=True,
            download_name=out_name
        )

    except (ValueError, RuntimeError, FileNotFoundError, OSError) as e:
        flash(str(e), 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Unexpected error: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/health')
def health():
    """Health-check endpoint for deployment platforms."""
    return jsonify({'status': 'ok', 'styles': SUPPORTED_STYLES})


if __name__ == '__main__':
    print("=" * 55)
    print("  Auto-Citer Web UI")
    print("  Open http://localhost:5000 in your browser")
    print(f"  Supported styles: {', '.join(SUPPORTED_STYLES)}")
    print("=" * 55)
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1', port=5000)
