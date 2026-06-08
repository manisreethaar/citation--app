"""
app.py  —  Flask web UI for auto-citer v2
==========================================
Run:  python app.py
Open: http://localhost:5000
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from flask import (Flask, request, render_template_string,
                   send_file, flash, redirect, url_for)
from pipeline import run_pipeline
from file_io import read_file, write_file
from style_engine import SUPPORTED_STYLES

try:
    from config import GOOGLE_API_KEY as _API_KEY, GOOGLE_CSE_ID as _CSE_ID
except ImportError:
    _API_KEY = ''
    _CSE_ID  = ''

app = Flask(__name__)
app.secret_key = 'auto-citer-v2-2024'
UPLOAD_DIR = tempfile.mkdtemp(prefix='autociter_v2_')
ALLOWED = {'docx', 'pdf', 'txt'}


def allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Auto-Citer v2</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f4f8;color:#1a202c;min-height:100vh}
  .header{background:linear-gradient(135deg,#2b6cb0,#4299e1);color:#fff;padding:2rem;text-align:center}
  .header h1{font-size:2rem;letter-spacing:-.5px}
  .header p{margin-top:.5rem;opacity:.9}
  .badge{display:inline-block;background:rgba(255,255,255,.2);border-radius:12px;
         padding:.2rem .7rem;font-size:.75rem;margin-left:.5rem;vertical-align:middle}
  .container{max-width:780px;margin:2rem auto;padding:0 1rem}
  .card{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 2px 12px rgba(0,0,0,.08);margin-bottom:1.5rem}
  h2{font-size:1.05rem;color:#2d3748;margin-bottom:1rem}
  .drop-zone{border:2px dashed #a0aec0;border-radius:8px;padding:2.5rem;text-align:center;
             cursor:pointer;transition:all .2s;background:#f7fafc}
  .drop-zone:hover,.drop-zone.drag-over{border-color:#4299e1;background:#ebf8ff}
  .drop-zone p{color:#718096;font-size:.95rem}
  .drop-zone .browse{color:#4299e1;text-decoration:underline;cursor:pointer}
  #file-input{display:none}
  #file-name{margin-top:.75rem;font-size:.85rem;color:#4a5568}
  .style-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.75rem}
  .style-card{border:2px solid #e2e8f0;border-radius:8px;padding:1rem;cursor:pointer;transition:all .15s}
  .style-card:hover{border-color:#4299e1}
  .style-card input{display:none}
  .style-card.selected{border-color:#4299e1;background:#ebf8ff}
  .style-card .name{font-weight:600;font-size:.95rem;color:#2d3748}
  .style-card .desc{font-size:.82rem;color:#718096;margin-top:.25rem}
  .style-card .example{font-size:.8rem;color:#4299e1;margin-top:.4rem;font-family:monospace}
  label.opt{display:flex;align-items:center;gap:.5rem;cursor:pointer;font-size:.9rem;color:#4a5568}
  .btn{background:#4299e1;color:#fff;border:none;border-radius:8px;padding:.85rem 2rem;
       font-size:1rem;font-weight:600;cursor:pointer;width:100%;transition:background .2s}
  .btn:hover{background:#3182ce}
  .btn:disabled{background:#a0aec0;cursor:not-allowed}
  .alert{padding:.85rem 1rem;border-radius:8px;margin-bottom:1rem;font-size:.9rem}
  .alert-error{background:#fff5f5;border:1px solid #feb2b2;color:#c53030}
  .alert-success{background:#f0fff4;border:1px solid #9ae6b4;color:#276749}
  .how{background:#fffbeb;border:1px solid #fbd38d;border-radius:8px;
       padding:1rem 1.25rem;font-size:.88rem;color:#744210}
  .how ol{padding-left:1.25rem;margin-top:.5rem}
  .how li{margin-bottom:.4rem}
  .spinner{display:none;text-align:center;padding:1rem}
  @keyframes spin{to{transform:rotate(360deg)}}
  .spinner svg{animation:spin 1s linear infinite}
</style>
</head>
<body>

<div class="header">
  <h1>📄 Auto-Citer <span class="badge">v2 — rebuilt foundation</span></h1>
  <p>Multi-signal scoring · Style conversion · Coverage audit</p>
</div>

<div class="container">

  <div style="text-align:center;margin-bottom:1rem">
    <a href="/check" style="display:inline-block;background:#38a169;color:#fff;
       border-radius:8px;padding:.55rem 1.4rem;font-size:.9rem;font-weight:600;
       text-decoration:none">🔍 Plagiarism Checker</a>
  </div>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}

  <div class="card how">
    <strong>What's new in v2:</strong>
    <ol>
      <li>Detects &amp; strips existing citation markers (any style) before reinserting.</li>
      <li>Multi-signal scoring: author name, year, title keywords, section type, sentence role — all combined.</li>
      <li>Never cites the author's own sentences ("we found...", "our results...").</li>
      <li>Coverage report shows which refs couldn't be matched and why.</li>
    </ol>
  </div>

  <form method="POST" action="/process" enctype="multipart/form-data" id="form">

    <div class="card">
      <h2>1. Upload your document</h2>
      <div class="drop-zone" id="dz" onclick="document.getElementById('file-input').click()">
        <p>Drag & drop here, or <span class="browse">browse</span></p>
        <p style="font-size:.8rem;margin-top:.4rem;color:#a0aec0">Supports .docx · .pdf · .txt</p>
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
          <div class="desc">Author–year · social sciences</div>
          <div class="example">(Smith et al., 2020)</div>
        </label>
        <label class="style-card" id="card-vancouver">
          <input type="radio" name="style" value="vancouver">
          <div class="name">Vancouver</div>
          <div class="desc">Numbered · biomedical</div>
          <div class="example">[1], [2], [3]</div>
        </label>
        <label class="style-card" id="card-ieee">
          <input type="radio" name="style" value="ieee">
          <div class="name">IEEE</div>
          <div class="desc">Numbered · engineering &amp; CS</div>
          <div class="example">[1], [2], [3]</div>
        </label>
        <label class="style-card" id="card-nature">
          <input type="radio" name="style" value="nature">
          <div class="name">Nature / Cell</div>
          <div class="desc">Superscript · high-impact science</div>
          <div class="example">¹ ² ³</div>
        </label>
      </div>
    </div>

    <div class="card">
      <h2>3. Options</h2>
      <label class="opt">
        <input type="checkbox" name="report" value="1">
        Include coverage report in console output
      </label>
    </div>

    <div class="spinner" id="spinner">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#4299e1" stroke-width="2">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83
                 M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      <p style="color:#718096;font-size:.9rem;margin-top:.5rem">Processing…</p>
    </div>

    <button type="submit" class="btn" id="btn">✨ Insert Citations & Download</button>
  </form>
</div>

<script>
const dz=document.getElementById('dz'),fi=document.getElementById('file-input'),fn=document.getElementById('file-name');
fi.addEventListener('change',()=>{fn.textContent=fi.files[0]?'📎 '+fi.files[0].name:''});
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag-over')});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag-over'));
dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('drag-over');
  fi.files=e.dataTransfer.files;fn.textContent=fi.files[0]?'📎 '+fi.files[0].name:''});
document.querySelectorAll('.style-card').forEach(c=>{
  c.addEventListener('click',()=>{
    document.querySelectorAll('.style-card').forEach(x=>x.classList.remove('selected'));
    c.classList.add('selected');c.querySelector('input[type=radio]').checked=true;
  });
});
document.getElementById('form').addEventListener('submit',()=>{
  document.getElementById('spinner').style.display='block';
  document.getElementById('btn').disabled=true;
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
    f = request.files.get('document')
    if not f or f.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not allowed(f.filename):
        flash('Unsupported file type. Use .docx, .pdf, or .txt', 'error')
        return redirect(url_for('index'))

    style = request.form.get('style', 'apa')
    do_report = request.form.get('report') == '1'

    input_path = os.path.join(UPLOAD_DIR, f.filename)
    f.save(input_path)

    ext = Path(f.filename).suffix
    out_name = Path(f.filename).stem + '_cited' + ext
    output_path = os.path.join(UPLOAD_DIR, out_name)

    try:
        text = read_file(input_path)
        result = run_pipeline(text, style, do_report)
        write_file(result.full_text, output_path, original_path=input_path)

        # Write changes report
        report_name = Path(f.filename).stem + '_changes.txt'
        report_path = os.path.join(UPLOAD_DIR, report_name)
        with open(report_path, 'w', encoding='utf-8') as rf:
            rf.write(result.changes_report.full_report())

        # Zip both files together for download
        import zipfile
        zip_name = Path(f.filename).stem + '_cited_output.zip'
        zip_path = os.path.join(UPLOAD_DIR, zip_name)
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(output_path, out_name)
            zf.write(report_path, report_name)

        return send_file(zip_path, as_attachment=True, 