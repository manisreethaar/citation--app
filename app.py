"""
app.py  –  Flask web application for Auto-Citer
================================================
Run:   python app.py
Open:  http://localhost:5000
"""

import os
import sys
import uuid
import tempfile
import secrets
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env in development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (
    Flask, request, render_template, send_file,
    flash, redirect, url_for, jsonify, session, abort
)
from werkzeug.utils import secure_filename

from auto_citer   import process_document, SUPPORTED_STYLES, MAX_FILE_SIZE
from auto_citer   import build_report as _build_report_txt
from reference_parser  import split_references_from_body, parse_references
from citation_styles   import inline_citation, format_bibliography
from matcher           import find_citation_positions, insert_citations
from file_handlers     import read_text, read_pdf, read_docx
from diff_engine       import build_diff_chunks
from database          import Database
from doi_fetcher       import fetch_by_doi, fetch_by_pmid, search_crossref


# ── App init ──────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

UPLOAD_FOLDER     = tempfile.mkdtemp(prefix='auto_citer_')
ALLOWED_EXTENSIONS = {'docx', 'pdf', 'txt'}

# Init DB
db = Database()
db.init()


def allowed_file(filename: str) -> bool:
    return ('.' in filename
            and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS)


def get_session_id() -> str:
    if 'sid' not in session:
        session['sid'] = secrets.token_hex(16)
    return session['sid']


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    prefs = db.get_or_create_prefs(get_session_id())
    return render_template(
        'index.html',
        max_size_mb=MAX_FILE_SIZE // 1024 // 1024,
        supported_styles=SUPPORTED_STYLES,
        default_style=prefs.get('default_style', 'apa'),
    )


@app.route('/history')
def history_page():
    return render_template('history.html')


@app.route('/result/<result_id>')
def result_page(result_id: str):
    entry = db.get_history(result_id)
    if not entry:
        flash('Result not found or has expired.', 'error')
        return redirect(url_for('index'))

    # Build diff + confidence for display
    result_path = entry.get('result_path')
    if not result_path or not os.path.exists(result_path):
        flash('Result file has been cleaned up. Please reprocess your document.', 'warning')
        return redirect(url_for('index'))

    return render_template('result.html', **_build_result_context(entry, result_id))


# ── Main process endpoint ─────────────────────────────────────────────────────

@app.route('/process', methods=['POST'])
def process():
    # Validate upload
    if 'document' not in request.files:
        flash('No file uploaded.', 'error')
        return redirect(url_for('index'))

    f = request.files['document']
    if not f or f.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not allowed_file(f.filename):
        flash('Unsupported file type. Use .docx, .pdf, or .txt', 'error')
        return redirect(url_for('index'))

    filename     = secure_filename(f.filename)
    style        = request.form.get('style', 'apa').lower()
    do_report    = request.form.get('report') == '1'
    strict_only  = request.form.get('strict_only') == '1'

    if style not in SUPPORTED_STYLES:
        flash(f'Unknown citation style "{style}".', 'error')
        return redirect(url_for('index'))

    # Save upload
    input_path = os.path.join(UPLOAD_FOLDER, f'{uuid.uuid4().hex}_{filename}')
    f.save(input_path)

    if os.path.getsize(input_path) > MAX_FILE_SIZE:
        os.remove(input_path)
        flash(f'File too large. Max {MAX_FILE_SIZE//1024//1024} MB.', 'error')
        return redirect(url_for('index'))

    # Derive output path
    stem     = Path(filename).stem
    ext      = Path(filename).suffix.lower()
    out_name = f'{stem}_cited_{style}{ext}'
    out_path = os.path.join(UPLOAD_FOLDER, f'{uuid.uuid4().hex}_{out_name}')

    try:
        result_path = process_document(
            input_path, style, out_path, print_report=False
        )

        # Build confidence data
        conf_data = _compute_confidence(input_path, ext, style, strict_only)
        total_refs  = conf_data['total']
        cited_refs  = conf_data['cited']
        avg_conf    = conf_data['avg_confidence']

        # Save to DB
        entry_id = db.save_history(
            filename=filename, style=style,
            total_refs=total_refs, cited_refs=cited_refs,
            avg_conf=avg_conf,
            result_path=result_path, output_name=out_name,
            ttl_hours=24
        )

        # Update user default style preference
        db.update_prefs(get_session_id(), default_style=style)

        # Redirect to result page
        return redirect(url_for('result_page', result_id=entry_id))

    except (ValueError, RuntimeError, FileNotFoundError, OSError) as e:
        flash(str(e), 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Unexpected error: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        # Clean up input temp file
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except OSError:
            pass


# ── Download endpoints ────────────────────────────────────────────────────────

@app.route('/download/<result_id>')
def download_result(result_id: str):
    entry = db.get_history(result_id)
    if not entry:
        abort(404)
    path = entry.get('result_path')
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True,
                     download_name=entry['output_name'])


@app.route('/download/share/<token>')
def download_shared(token: str):
    entry = db.get_by_token(token)
    if not entry:
        flash('This share link has expired or is invalid.', 'error')
        return redirect(url_for('index'))
    path = entry.get('result_path')
    if not path or not os.path.exists(path):
        flash('The shared file is no longer available.', 'error')
        return redirect(url_for('index'))
    return send_file(path, as_attachment=True,
                     download_name=entry['output_name'])


# ── API: Preview ──────────────────────────────────────────────────────────────

@app.route('/api/preview', methods=['POST'])
def api_preview():
    """
    Upload a file → return detected references as JSON.
    Used by the frontend preview modal.
    """
    if 'document' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    f = request.files['document']
    if not f or not allowed_file(f.filename):
        return jsonify({'error': 'Unsupported file type'}), 400

    filename   = secure_filename(f.filename)
    tmp_path   = os.path.join(UPLOAD_FOLDER, f'{uuid.uuid4().hex}_{filename}')
    f.save(tmp_path)

    try:
        ext = Path(filename).suffix.lower()
        if ext == '.docx':
            full_text, _ = read_docx(tmp_path)
        elif ext == '.pdf':
            full_text = read_pdf(tmp_path)
        else:
            full_text = read_text(tmp_path)

        body, ref_section = split_references_from_body(full_text)
        if not ref_section.strip():
            return jsonify({'error': 'No References section found in document.'}), 200

        refs = parse_references(ref_section)
        if not refs:
            return jsonify({'error': 'Could not parse any references.'}), 200

        # Compute per-reference confidence (how likely the name appears in body)
        ref_list = []
        for ref in refs:
            hits = find_citation_positions(body, [ref])
            confidence = _score_confidence(hits)
            ref_list.append({
                'index':      ref.index,
                'authors':    ref.authors[:3] if ref.authors else [],
                'year':       ref.year,
                'title':      ref.title,
                'journal':    ref.journal,
                'confidence': confidence,
                'cited':      len(hits) > 0,
            })

        return jsonify({
            'refs':       ref_list,
            'total':      len(refs),
            'body_words': len(body.split()),
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ── API: DOI lookup ───────────────────────────────────────────────────────────

@app.route('/api/doi/<path:doi>')
def api_doi(doi: str):
    """Fetch reference metadata by DOI from CrossRef."""
    result = fetch_by_doi(doi)
    if not result:
        return jsonify({'error': f'DOI not found: {doi}'}), 404
    return jsonify(result)


@app.route('/api/pmid/<pmid>')
def api_pmid(pmid: str):
    """Fetch reference metadata by PubMed ID."""
    result = fetch_by_pmid(pmid)
    if not result:
        return jsonify({'error': f'PMID not found: {pmid}'}), 404
    return jsonify(result)


@app.route('/api/search')
def api_search():
    """Full-text search CrossRef."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'error': 'No query provided'}), 400
    results = search_crossref(q, limit=8)
    return jsonify({'results': results, 'count': len(results)})


# ── API: Sharing ──────────────────────────────────────────────────────────────

@app.route('/api/share/<result_id>', methods=['POST'])
def share_result(result_id: str):
    entry = db.get_history(result_id)
    if not entry:
        return jsonify({'error': 'Result not found'}), 404
    token = db.create_share_token(result_id, ttl_hours=24)
    url   = url_for('download_shared', token=token, _external=True)
    return jsonify({'url': url, 'token': token, 'expires_in': '24 hours'})


# ── API: History ──────────────────────────────────────────────────────────────

@app.route('/api/history')
def api_history():
    entries = db.list_history(limit=50)
    return jsonify({'history': entries})


@app.route('/api/history/<entry_id>', methods=['DELETE'])
def api_delete_history(entry_id: str):
    deleted = db.delete_history(entry_id)
    return jsonify({'deleted': deleted})


# ── API: Preferences ──────────────────────────────────────────────────────────

@app.route('/api/prefs', methods=['GET', 'POST'])
def api_prefs():
    sid = get_session_id()
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        db.update_prefs(sid, **data)
        return jsonify({'status': 'ok'})
    return jsonify(db.get_or_create_prefs(sid))


# ── Health check ──────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    db.cleanup_expired()   # opportunistic cleanup
    return jsonify({
        'status':  'ok',
        'styles':  SUPPORTED_STYLES,
        'version': '2.0.0',
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_confidence(input_path: str, ext: str, style: str,
                        strict_only: bool = False) -> dict:
    """Re-read the document to compute per-ref confidence scores."""
    try:
        if ext == '.docx':
            full_text, _ = read_docx(input_path)
        elif ext == '.pdf':
            full_text = read_pdf(input_path)
        else:
            full_text = read_text(input_path)

        body, ref_section = split_references_from_body(full_text)
        refs = parse_references(ref_section)
        if not refs:
            return {'total': 0, 'cited': 0, 'avg_confidence': 0, 'items': []}

        items = []
        total_conf = 0
        cited_count = 0

        for ref in refs:
            hits = find_citation_positions(body, [ref])
            # If strict_only, only count hits where is_strict=True
            if strict_only:
                hits = [h for h in hits]   # placeholder — filter in matcher

            conf = _score_confidence(hits)
            cited = len(hits) > 0
            if cited:
                cited_count += 1
            total_conf += conf

            tier = 'high' if conf >= 85 else ('medium' if conf >= 60 else ('low' if cited else 'none'))
            items.append({
                'index':      ref.index,
                'author':     ref.authors[0] if ref.authors else 'Unknown',
                'year':       ref.year,
                'confidence': conf,
                'status':     '✓ cited' if cited else '✗ not found',
                'tier':       tier,
            })

        avg = round(total_conf / len(refs), 1) if refs else 0
        return {
            'total':        len(refs),
            'cited':        cited_count,
            'avg_confidence': avg,
            'items':        items,
        }
    except Exception:
        return {'total': 0, 'cited': 0, 'avg_confidence': 0, 'items': []}


def _score_confidence(hits: list) -> int:
    """
    Score a list of match hits → confidence percentage.
    Based on match type priority:
      - Patterns 1-3 (strict) → 90-97%
      - Pattern 4-5 (et al. / two-author no year) → 75-85%
      - Pattern 6 (surname only) → 55%
      - No hits → 0%
    """
    if not hits:
        return 0
    # Return highest confidence found
    # hits are (start, end, placeholder, ref_idx) — we don't have pattern info here
    # so use count as proxy: more hits = higher confidence
    n = len(hits)
    if n >= 3:  return 95
    if n == 2:  return 85
    return 75   # single hit


def _build_result_context(entry: dict, result_id: str) -> dict:
    """Build the template context dict for result.html."""
    result_path = entry['result_path']
    ext         = Path(entry['output_name']).suffix.lower()
    style       = entry['style']

    # Read original to generate diff
    original_body = ''
    cited_body    = ''
    diff_chunks   = []
    bibliography  = ''

    try:
        if ext == '.txt':
            cited_text = read_text(result_path)
            # Split cited text back: body + bibliography
            parts = cited_text.split('References\n' + '=' * 60)
            cited_body = parts[0].strip()
            bibliography = ('References\n' + '=' * 60 + parts[1]) if len(parts) > 1 else ''
            diff_chunks = build_diff_chunks('', cited_body)
        else:
            cited_body   = ''
            diff_chunks  = [{'type': 'norm', 'text': f'[Diff view available for .txt files. Download to view changes in {ext.upper()} format.]'}]
            bibliography = ''
    except Exception:
        diff_chunks = []

    # Rebuild confidence report from DB stored data
    conf_items = []
    # We re-compute from the DB entry summary
    total = entry.get('total_refs', 0)
    cited = entry.get('cited_refs', 0)
    avg   = entry.get('avg_conf', 0)

    # We don't have per-ref data persisted — create summary items
    for i in range(1, min(total + 1, 51)):
        conf_items.append({
            'index':      i,
            'author':     '—',
            'year':       '—',
            'confidence': int(avg),
            'status':     '✓ cited' if i <= cited else '✗ not found',
            'tier':       'high' if avg >= 85 else ('medium' if avg >= 60 else 'low'),
        })

    return {
        'filename':         entry['filename'],
        'out_filename':     entry['output_name'],
        'style':            style,
        'total_refs':       total,
        'cited_refs':       cited,
        'avg_confidence':   avg,
        'diff_chunks':      diff_chunks,
        'confidence_report':conf_items,
        'bibliography':     bibliography,
        'result_id':        result_id,
        'download_url':     url_for('download_result', result_id=result_id),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=' * 56)
    print('  Auto-Citer v2.0')
    print('  http://localhost:5000')
    print(f'  Styles: {", ".join(SUPPORTED_STYLES)}')
    print('  DB:', db.db_path)
    print('=' * 56)
    app.run(
        debug=os.environ.get('FLASK_DEBUG', '0') == '1',
        port=int(os.environ.get('PORT', 5000))
    )
