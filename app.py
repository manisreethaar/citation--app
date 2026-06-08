"""
app.py  ─  Flask web interface for auto-citer
=============================================
Run: python app.py
Then open http://localhost:5000 in your browser.
"""

import os
import sys
import tempfile
from pathlib import Path

# Make sure our modules are importable
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, render_template_string, send_file, flash, redirect, url_for
from auto_citer import process_document, SUPPORTED_STYLES

app = Flask(__name__)
app.secret_key = 'auto-citer-secret-2024'
UPLOAD_FOLDER = tempfile.mkdtemp(prefix='auto_citer_')
ALLOWED_EXTENSIONS = {'docx', 'pdf', 'txt'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Auto-Citer — Automatic Reference Citation Tool</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0f4f8; color: #1a202c; min-height: 100vh; }
  .header { background: linear-gradient(135deg, #2b6cb0, #4299e1); color: white; padding: 2rem; text-align: center; }
  .header h1 { font-size: 2rem; letter-spacing: -0.5px; }
  .header p  { margin-top: 0.5rem; opacity: 0.9; font-size: 1rem; }
  .container { max-width: 760px; margin: 2rem auto; padding: 0 1rem; }
  .card { background: white; border-radius: 12px; padding: 2rem; box-shadow: 0 2px 12px rgba(0,0,0,.08); margin-bottom: 1.5rem; }
  h2 { font-size: 1.1rem; color: #2d3748; margin-bottom: 1rem; }
  .drop-zone { border: 2px dashed #a0aec0; border-radius: 8px; padding: 2.5rem; text-align: center;
               cursor: pointer; transition: all .2s; background: #f7fafc; }
  .drop-zone:hover, .drop-zone.drag-over { border-color: #4299e1; background: #ebf8ff; }
  .drop-zone svg { width: 48px; height: 48px; color: #a0aec0; margin-bottom: 0.75rem; }
  .drop-zone p { color: #718096; font-size: 0.95rem; }
  .drop-zone .browse { color: #4299e1; text-decoration: underline; cursor: pointer; }
  #file-input { display: none; }
  #file-name  { margin-top: 0.75rem; font-size: 0.85rem; color: #4a5568; }
  .style-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
  .style-card { border: 2px solid #e2e8f0; border-radius: 8px; padding: 1rem; cursor: pointer;
                transition: all .15s; }
  .style-card:hover { border-color: #4299e1; }
  .style-card input[type=radio] { display: none; }
  .style-card.selected { border-color: #4299e1; background: #ebf8ff; }
  .style-card .name  { font-weight: 600; font-size: 0.95rem; color: #2d3748; }
  .style-card .desc  { font-size: 0.82rem; color: #718096; margin-top: 0.25rem; }
  .style-card .example { font-size: 0.8rem; color: #4299e1; margin-top: 0.4rem; font-family: monospace; }
  .options { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
  .options label { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.9rem; color: #4a5568; }
  .btn { background: #4299e1; color: white; border: none; border-radius: 8px; padding: 0.85rem 2rem;
         font-size: 1rem; font-weight: 600; cursor: pointer; width: 100%; transition: background .2s; }
  .btn:hover { background: #3182ce; }
  .btn:disabled { background: #a0aec0; cursor: not-allowed; }
  .alert { padding: 0.85rem 1rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.9rem; }
  .alert-error   { background: #fff5f5; border: 1px solid #feb2b2; color: #c53030; }
  .alert-success { background: #f0fff4; border: 1px solid #9ae6b4; color: #276749; }
  .how-it-works { background: #fffbeb; border: 1px solid #fbd38d; border-radius: 8px;
                   padding: 1rem 1.25rem; font-size: 0.88rem; color: #744210; }
  .how-it-works ol { padding-left: 1.25rem; margin-top: 0.5rem; }
  .how-it-works li { margin-bottom: 0.35rem; }
  .spinner { display: none; text-align: center; padding: 1rem; }
  .spinner svg { animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header">
  <h1>📄 Auto-Citer</h1>
  <p>Automatically insert citations into your research document</p>
</div>

<div class="container">

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}

  <div class="card how-it-works">
    <strong>How it works:</strong>
    <ol>
      <li>Upload your document — body text + a "References" section at the end.</li>
      <li>The tool detects every reference, then scans the body for author names and years.</li>
      <li>Citations are inserted automatically and the bibliography is reformatted to your chosen style.</li>
    </ol>
  </div>

  <form method="POST" action="/process" enctype="multipart/form-data" id="upload-form">

    <div class="card">
      <h2>1. Upload your document</h2>
      <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
        </svg>
        <p>Drag & drop your file here, or <span class="browse">browse</span></p>
        <p style="font-size:0.8rem;margin-top:0.4rem;color:#a0aec0">Supports .docx · .pdf · .txt</p>
        <div id="file-name"></div>
      </div>
      <input type="file" id="file-input" name="document" accept=".docx,.pdf,.txt">
    </div>

    <div class="card">
      <h2>2. Choose citation style</h2>
      <div class="style-grid">
        <label class="style-card selected" id="card-apa">
          <input type="radio" name="style" value="apa" checked>
          <div class="name">APA</div>
          <div class="desc">Author–year, social sciences</div>
          <div class="example">(Smith et al., 2020)</div>
        </label>
        <label class="style-card" id="card-vancouver">
          <input type="radio" name="style" value="vancouver">
          <div class="name">Vancouver</div>
          <div class="desc">Numbered, biomedical journals</div>
          <div class="example">[1], [2], [3]</div>
        </label>
        <label class="style-card" id="card-ieee">
          <input type="radio" name="style" value="ieee">
          <div class="name">IEEE</div>
          <div class="desc">Numbered, engineering & CS</div>
          <div class="example">[1], [2], [3]</div>
        </label>
        <label class="style-card" id="card-nature">
          <input type="radio" name="style" value="nature">
          <div class="name">Nature / Cell</div>
          <div class="desc">Superscript numbers, high-impact</div>
          <div class="example">¹·²·³ or [1]</div>
        </label>
      </div>
    </div>

    <div class="card">
      <h2>3. Options</h2>
      <div class="options">
        <label>
          <input type="checkbox" name="report" value="1">
          Generate citation match report
        </label>
      </div>
    </div>

    <div class="spinner" id="spinner">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#4299e1" stroke-width="2">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4
                 M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      <p style="color:#718096;font-size:0.9rem;margin-top:0.5rem">Processing your document…</p>
    </div>

    <button type="submit" class="btn" id="submit-btn">✨ Insert Citations & Download</button>
  </form>

</div>

<script>
// Drag & drop
const dz = document.getElementById('drop-zone');
const fi = document.getElementById('file-input');
const fn = document.getElementById('file-name');

fi.addEventListener('change', () => {
  fn.textContent = fi.files[0] ? '📎 ' + fi.files[0].name : '';
});
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
dz.addEventListener('drop', e => {
  e.preventDefault(); dz.classList.remove('drag-over');
  fi.files = e.dataTransfer.files;
  fn.textContent = fi.files[0] ? '📎 ' + fi.files[0].name : '';
});

// Style card selection
document.querySelectorAll('.style-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.style-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    card.querySelector('input[type=radio]').checked = true;
  });
});

// Show spinner on submit
document.getElementById('upload-form').addEventListener('submit', () => {
  document.getElementById('spinner').style.display = 'block';
  document.getElementById('submit-btn').disabled = true;
});
</script>
</body>
</html>
"""


@app.route('/', methods=['GET'])
def index():
    return render_template_string(HTML)


@app.route('/process', methods=['POST'])
def process():
    if 'document' not in request.files:
        flash('No file uploaded.', 'error')
        return redirect(url_for('index'))

    f = request.files['document']
    if f.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not allowed_file(f.filename):
        flash('Unsupported file type. Please upload .docx, .pdf, or .txt', 'error')
        return redirect(url_for('index'))

    style = request.form.get('style', 'apa')
    do_report = request.form.get('report') == '1'

    # Save upload
    filename = f.filename
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(input_path)

    # Derive output path
    stem = Path(filename).stem
    ext  = Path(filename).suffix
    out_name = f"{stem}_cited{ext}"
    output_path = os.path.join(UPLOAD_FOLDER, out_name)

    try:
        result_path = process_document(input_path, style, output_path, do_report)
        return send_file(result_path, as_attachment=True,
                         download_name=out_name)
    except SystemExit as e:
        flash(str(e), 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('index'))


if __name__ == '__main__':
    print("=" * 50)
    print("  Auto-Citer Web UI")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 50)
    app.run(debug=False, port=5000)
