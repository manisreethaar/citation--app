"""
app.py  –  Flask web application for Auto-Citer
================================================
Run:   python app.py
Open:  http://localhost:5000
"""

import os
import sys
import uuid
import zipfile
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

from auto_citer          import process_document, SUPPORTED_STYLES, MAX_FILE_SIZE
from reference_parser    import split_references_from_body, parse_references
from citation_styles     import inline_citation, format_bibliography
from matcher             import find_citation_positions, insert_citations
from file_handlers       import read_text, read_docx, find_refs_start_paragraph
from diff_engine         import build_diff_chunks
from database            import Database
from doi_fetcher         import fetch_by_doi, fetch_by_pmid, search_crossref
from ai_language_detector import detect_ai_language


# ── v2 Pipeline (semantic citation engine) ────────────────────────────────────
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v2'))
try:
    from v2.bridge import process_v2, preview_v2, SUPPORTED_STYLES_V2
    _V2_AVAILABLE = True
except Exception as _v2_err:
    print(f'[Warning] v2 pipeline unavailable: {_v2_err}', file=_sys.stderr)
    _V2_AVAILABLE = False
    SUPPORTED_STYLES_V2 = []

# Optional: Gemini AI features
try:
    import ai_assistant
    _AI_AVAILABLE = ai_assistant.is_available()
except Exception:
    ai_assistant  = None
    _AI_AVAILABLE = False

# Optional: PyMuPDF for PDF support
try:
    from file_handlers import read_pdf
    _PDF_SUPPORTED = True
except Exception:
    _PDF_SUPPORTED = False

# ── App init ──────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Use /tmp on Vercel (read-only filesystem except /tmp)
_IS_VERCEL = bool(os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV'))
_TMP_BASE  = '/tmp' if _IS_VERCEL else tempfile.gettempdir()

def _get_upload_folder() -> str:
    """Lazy-init upload folder so it's created on first request, not at import time."""
    folder = os.path.join(_TMP_BASE, 'auto_citer_uploads')
    os.makedirs(folder, exist_ok=True)
    return folder

ALLOWED_EXTENSIONS = {'docx', 'pdf', 'txt'}

# Init DB (safe — won't crash if DB unavailable)
try:
    db = Database()
    db.init()
    _DB_OK = True
except Exception as _db_err:
    print(f'[Warning] DB unavailable: {_db_err}', file=sys.stderr)
    db = None
    _DB_OK = False


def allowed_file(filename: str) -> bool:
    return ('.' in filename
            and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS)


def _upload_folder() -> str:
    return _get_upload_folder()


def _read_uploaded_text(path: str, ext: str) -> str:
    """Read an uploaded document into plain text for analysis endpoints."""
    if ext == '.docx':
        full_text, _ = read_docx(path)
        return full_text
    if ext == '.pdf':
        if not _PDF_SUPPORTED:
            raise RuntimeError('PDF support unavailable on this server. Please convert to .txt.')
        from file_handlers import read_pdf as _read_pdf
        return _read_pdf(path)
    return read_text(path)


def _safe_db_call(fn, *args, **kwargs):
    """Call a DB function safely — returns None if DB unavailable."""
    if not _DB_OK or db is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f'[Warning] DB error: {e}', file=sys.stderr)
        return None


def get_session_id() -> str:
    if 'sid' not in session:
        session['sid'] = secrets.token_hex(16)
    return session['sid']


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    prefs = _safe_db_call(db.get_or_create_prefs, get_session_id()) or {}
    return render_template(
        'index.html',
        max_size_mb=MAX_FILE_SIZE // 1024 // 1024,
        supported_styles=SUPPORTED_STYLES,
        default_style=prefs.get('default_style', 'apa'),
        ai_available=_AI_AVAILABLE,
        v2_available=_V2_AVAILABLE,
    )


@app.route('/history')
def history_page():
    return render_template('history.html')


@app.route('/result/<result_id>')
def result_page(result_id: str):
    entry = _safe_db_call(db.get_history, result_id) if _DB_OK else None
    if not entry:
        flash('Result not found or has expired.', 'error')
        return redirect(url_for('index'))

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

    # Save upload to /tmp
    upload_dir = _upload_folder()
    input_path = os.path.join(upload_dir, f'{uuid.uuid4().hex}_{filename}')
    f.save(input_path)

    if os.path.getsize(input_path) > MAX_FILE_SIZE:
        os.remove(input_path)
        flash(f'File too large. Max {MAX_FILE_SIZE//1024//1024} MB.', 'error')
        return redirect(url_for('index'))

    # Derive output path
    stem     = Path(filename).stem
    ext      = Path(filename).suffix.lower()
    out_name = f'{stem}_cited_{style}{ext}'
    out_path = os.path.join(upload_dir, f'{uuid.uuid4().hex}_{out_name}')

    try:
        # ── Read full text BEFORE process_document deletes nothing (we delete below) ──
        if ext == '.docx':
            _pre_text, _ = read_docx(input_path)
        elif ext == '.pdf':
            if not _PDF_SUPPORTED:
                flash('PDF support unavailable on this server. Convert to .txt first.', 'error')
                return redirect(url_for('index'))
            from file_handlers import read_pdf as _rpdf
            _pre_text = _rpdf(input_path)
        else:
            _pre_text = read_text(input_path)

        result_path = process_document(
            input_path, style, out_path, print_report=False
        )

        # Build confidence data from pre-read text (input_path still exists here)
        conf_data = _compute_confidence_from_text(_pre_text, style, strict_only)
        total_refs  = conf_data['total']
        cited_refs  = conf_data['cited']
        avg_conf    = conf_data['avg_confidence']

        # Save to DB
        entry_id = _safe_db_call(
            db.save_history,
            filename=filename, style=style,
            total_refs=total_refs, cited_refs=cited_refs,
            avg_conf=avg_conf,
            result_path=result_path, output_name=out_name,
            ttl_hours=24
        )

        # Update user default style preference
        _safe_db_call(db.update_prefs, get_session_id(), default_style=style)

        # If DB unavailable, fall back to direct download
        if not entry_id:
            return send_file(result_path, as_attachment=True, download_name=out_name)

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
    entry = _safe_db_call(db.get_history, result_id) if _DB_OK else None
    if not entry:
        abort(404)
    path = entry.get('result_path')
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True,
                     download_name=entry['output_name'])


@app.route('/download/share/<token>')
def download_shared(token: str):
    entry = _safe_db_call(db.get_by_token, token) if _DB_OK else None
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
    Upload a file → return detected references + citation mode as JSON.
    Used by the frontend preview modal.
    """
    if 'document' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    f = request.files['document']
    if not f or not allowed_file(f.filename):
        return jsonify({'error': 'Unsupported file type'}), 400

    filename   = secure_filename(f.filename)
    tmp_path   = os.path.join(_upload_folder(), f'{uuid.uuid4().hex}_{filename}')
    f.save(tmp_path)

    try:
        ext = Path(filename).suffix.lower()
        if ext == '.docx':
            full_text, _ = read_docx(tmp_path)
        elif ext == '.pdf':
            if not _PDF_SUPPORTED:
                return jsonify({'error': 'PDF support unavailable on this server. Please convert to .txt'}), 200
            from file_handlers import read_pdf as _read_pdf
            full_text = _read_pdf(tmp_path)
        else:
            full_text = read_text(tmp_path)

        # Use v2 engine for richer preview if available
        if _V2_AVAILABLE:
            try:
                preview_data = preview_v2(full_text)
                return jsonify(preview_data)
            except ValueError as ve:
                return jsonify({'error': str(ve)}), 200
            except Exception:
                pass  # fall through to v1

        # v1 fallback
        body, ref_section = split_references_from_body(full_text)
        if not ref_section.strip():
            return jsonify({'error': 'No References section found in document.'}), 200

        refs = parse_references(ref_section)
        if not refs:
            return jsonify({'error': 'Could not parse any references.'}), 200

        from citation_detector import detect_citation_mode, extract_cited_numbers
        detection = detect_citation_mode(body)
        cited_nums = set(extract_cited_numbers(body)) if detection['mode'] == 'numbered' else set()

        ref_list = []
        for ref in refs:
            if detection['mode'] == 'numbered':
                is_cited = ref.index in cited_nums
                confidence = 95 if is_cited else 0
            elif detection['mode'] == 'superscript':
                confidence = 80
                is_cited   = True
            else:
                hits = find_citation_positions(body, [ref])
                confidence = _score_confidence(hits)
                is_cited   = len(hits) > 0

            ref_list.append({
                'index':      ref.index,
                'authors':    ref.authors[:3] if ref.authors else [],
                'year':       ref.year,
                'title':      ref.title,
                'journal':    ref.journal,
                'ref_type':   getattr(ref, 'ref_type', 'article'),
                'confidence': confidence,
                'cited':      is_cited,
            })

        return jsonify({
            'refs':       ref_list,
            'total':      len(refs),
            'body_words': len(body.split()),
            'detection': {
                'mode':        detection['mode'],
                'count':       detection['count'],
                'style_guess': detection['style_guess'],
                'description': detection['description'],
                'examples':    detection['examples'][:3],
            },
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


# ── API: AI-language detector ─────────────────────────────────────────────────

@app.route('/api/ai-language/detect', methods=['POST'])
def api_ai_language_detect():
    """Analyse pasted text or an uploaded file for AI-like language."""
    tmp_path = None
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            full_text = (data.get('text') or '').strip()
            filename = data.get('filename') or 'pasted text'
        else:
            f = request.files.get('document')
            if not f or f.filename == '':
                return jsonify({'error': 'Upload a document or paste text first.'}), 400
            if not allowed_file(f.filename):
                return jsonify({'error': 'Unsupported file type. Use .docx, .pdf, or .txt'}), 400

            filename = secure_filename(f.filename)
            ext = Path(filename).suffix.lower()
            tmp_path = os.path.join(_upload_folder(), f'{uuid.uuid4().hex}_{filename}')
            f.save(tmp_path)
            full_text = _read_uploaded_text(tmp_path, ext)

        if not full_text or len(full_text.split()) < 20:
            return jsonify({'error': 'Not enough text to analyse. Provide at least 20 words.'}), 400

        result = detect_ai_language(full_text)
        result['filename'] = filename
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ── API: Sharing ──────────────────────────────────────────────────────────────

@app.route('/api/share/<result_id>', methods=['POST'])
def share_result(result_id: str):
    if not _DB_OK:
        return jsonify({'error': 'Sharing unavailable (no database)'}), 503
    entry = _safe_db_call(db.get_history, result_id)
    if not entry:
        return jsonify({'error': 'Result not found'}), 404
    token = _safe_db_call(db.create_share_token, result_id, ttl_hours=24)
    if not token:
        return jsonify({'error': 'Could not create share token'}), 500
    share_url = url_for('download_shared', token=token, _external=True)
    return jsonify({'url': share_url, 'token': token, 'expires_in': '24 hours'})


# ── API: History ──────────────────────────────────────────────────────────────

@app.route('/api/history')
def api_history():
    if not _DB_OK:
        return jsonify({'history': []})
    entries = _safe_db_call(db.list_history, 50) or []
    return jsonify({'history': entries})


@app.route('/api/history/<entry_id>', methods=['DELETE'])
def api_delete_history(entry_id: str):
    deleted = _safe_db_call(db.delete_history, entry_id) or False
    return jsonify({'deleted': deleted})


# ── API: Preferences ──────────────────────────────────────────────────────────

@app.route('/api/prefs', methods=['GET', 'POST'])
def api_prefs():
    sid = get_session_id()
    if not _DB_OK:
        return jsonify({'theme': 'dark', 'default_style': 'apa'})
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        _safe_db_call(db.update_prefs, sid, **data)
        return jsonify({'status': 'ok'})
    return jsonify(_safe_db_call(db.get_or_create_prefs, sid) or {})


# ── Health check ──────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    if _DB_OK:
        _safe_db_call(db.cleanup_expired)
    return jsonify({
        'status':       'ok',
        'styles':       SUPPORTED_STYLES,
        'version':      '2.0.0',
        'db':           _DB_OK,
        'pdf_support':  _PDF_SUPPORTED,
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_confidence_from_text(full_text: str, style: str,
                                   strict_only: bool = False) -> dict:
    """Compute per-ref confidence scores from already-read document text."""
    try:
        if _V2_AVAILABLE:
            # Use v2 preview for accurate per-ref scoring
            try:
                data = preview_v2(full_text)
                refs_data = data.get('refs', [])
                cited_count = sum(1 for r in refs_data if r.get('cited'))
                total_conf  = sum(r.get('confidence', 0) for r in refs_data)
                avg = round(total_conf / len(refs_data), 1) if refs_data else 0
                items = []
                for r in refs_data:
                    conf = r.get('confidence', 0)
                    cited = r.get('cited', False)
                    tier = 'high' if conf >= 85 else ('medium' if conf >= 60 else ('low' if cited else 'none'))
                    items.append({
                        'index':      r['index'],
                        'author':     r['authors'][0] if r.get('authors') else 'Unknown',
                        'year':       r.get('year', ''),
                        'confidence': conf,
                        'status':     '✓ cited' if cited else '✗ not found',
                        'tier':       tier,
                    })
                return {
                    'total':          len(refs_data),
                    'cited':          cited_count,
                    'avg_confidence': avg,
                    'items':          items,
                }
            except Exception:
                pass  # fall through to v1

        # v1 fallback
        body, ref_section = split_references_from_body(full_text)
        refs = parse_references(ref_section)
        if not refs:
            return {'total': 0, 'cited': 0, 'avg_confidence': 0, 'items': []}

        items = []
        total_conf = 0
        cited_count = 0

        for ref in refs:
            hits = find_citation_positions(body, [ref])
            conf  = _score_confidence(hits)
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


def _compute_confidence(input_path: str, ext: str, style: str,
                        strict_only: bool = False) -> dict:
    """Legacy: re-read file then call _compute_confidence_from_text."""
    try:
        if ext == '.docx':
            full_text, _ = read_docx(input_path)
        elif ext == '.pdf':
            if not _PDF_SUPPORTED:
                return {'total': 0, 'cited': 0, 'avg_confidence': 0, 'items': []}
            from file_handlers import read_pdf as _rpdf2
            full_text = _rpdf2(input_path)
        else:
            full_text = read_text(input_path)
        return _compute_confidence_from_text(full_text, style, strict_only)
    except Exception:
        return {'total': 0, 'cited': 0, 'avg_confidence': 0, 'items': []}


def _score_confidence(hits: list) -> int:
    """
    Score a list of match hits → confidence percentage.
      >= 3 hits → 95%  (very well cited)
      2 hits    → 85%
      1 hit     → 75%
      0 hits    → 0%   (not found in text)
    """
    if not hits:
        return 0
    n = len(hits)
    if n >= 3: return 95
    if n == 2: return 85
    return 75


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


# ── Batch processing ──────────────────────────────────────────────────────────



# ── Engine status ─────────────────────────────────────────────────────────────

@app.route('/api/engine/status')
def api_engine_status():
    """Return which processing engine is active."""
    return jsonify({
        'v2':  _V2_AVAILABLE,
        'v1':  True,
        'active': 'v2' if _V2_AVAILABLE else 'v1',
        'styles_v2': SUPPORTED_STYLES_V2,
    })

# -- AI Endpoints -------------------------------------------------------------

@app.route('/api/ai/status')
def api_ai_status():
    return jsonify({'available': _AI_AVAILABLE,
                    'model': os.environ.get('GEMINI_MODEL','gemini-2.0-flash') if _AI_AVAILABLE else None})

@app.route('/api/ai/parse', methods=['POST'])
def api_ai_parse():
    if not _AI_AVAILABLE:
        return jsonify({'error': 'AI not available. Set GEMINI_API_KEY.'}), 503
    data = request.get_json(silent=True) or {}
    raw  = (data.get('text') or '').strip()
    if not raw:
        return jsonify({'error': 'No text provided'}), 400
    try:
        result = ai_assistant.ai_parse_reference(raw)
        if not result:
            return jsonify({'error': 'AI could not parse this reference.'}), 200
        return jsonify({'ok': True, 'data': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/suggest', methods=['POST'])
def api_ai_suggest():
    if not _AI_AVAILABLE:
        return jsonify({'error': 'AI not available. Set GEMINI_API_KEY.'}), 503
    body_text = ''
    refs_data = []
    if request.is_json:
        data      = request.get_json(silent=True) or {}
        body_text = data.get('body', '')
        refs_data = data.get('refs', [])
    elif 'document' in request.files:
        f = request.files['document']
        if f and allowed_file(f.filename):
            from werkzeug.utils import secure_filename
            filename = secure_filename(f.filename)
            import uuid as _uuid, pathlib as _pl
            tmp_path = os.path.join(_upload_folder(), _uuid.uuid4().hex + '_' + filename)
            f.save(tmp_path)
            try:
                ext = _pl.Path(filename).suffix.lower()
                full_text = read_docx(tmp_path)[0] if ext == '.docx' else read_text(tmp_path)
                body_text, ref_section = split_references_from_body(full_text)
                refs_data = [{'index': r.index, 'authors': r.authors, 'year': r.year}
                             for r in parse_references(ref_section)]
            finally:
                try: os.remove(tmp_path)
                except OSError: pass
    if not body_text.strip():
        return jsonify({'error': 'Empty document body'}), 400
    try:
        suggestions = ai_assistant.ai_suggest_missing_citations(body_text, refs_data)
        return jsonify({'ok': True, 'suggestions': suggestions, 'count': len(suggestions)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/complete', methods=['POST'])
def api_ai_complete():
    if not _AI_AVAILABLE:
        return jsonify({'error': 'AI not available. Set GEMINI_API_KEY.'}), 503
    data    = request.get_json(silent=True) or {}
    partial = data.get('partial', {})
    if not partial:
        return jsonify({'error': 'No partial reference provided'}), 400
    try:
        completed = ai_assistant.ai_complete_reference(partial)
        return jsonify({'ok': True, 'data': completed})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/detect-style', methods=['POST'])
def api_ai_detect_style():
    if not _AI_AVAILABLE:
        return jsonify({'error': 'AI not available.'}), 503
    data = request.get_json(silent=True) or {}
    raw  = (data.get('text') or '').strip()
    if not raw:
        return jsonify({'error': 'No text provided'}), 400
    try:
        result = ai_assistant.ai_detect_style(raw)
        if result:
            return jsonify({'ok': True, **result})
        return jsonify({'error': 'Could not detect style.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/batch', methods=['POST'])
def batch_process():
    """
    Accept a ZIP file containing .docx/.pdf/.txt documents.
    Process each with the chosen citation style.
    Return a ZIP of all cited outputs.
    """
    if 'zipfile' not in request.files:
        flash('No ZIP file uploaded.', 'error')
        return redirect(url_for('index'))

    zf = request.files['zipfile']
    if not zf or not zf.filename.lower().endswith('.zip'):
        flash('Please upload a .zip file.', 'error')
        return redirect(url_for('index'))

    style = request.form.get('style', 'apa').lower()
    if style not in SUPPORTED_STYLES:
        style = 'apa'

    upload_dir = _upload_folder()
    zip_path   = os.path.join(upload_dir, f'{uuid.uuid4().hex}_batch.zip')
    zf.save(zip_path)

    output_zip_path = os.path.join(upload_dir, f'{uuid.uuid4().hex}_batch_cited.zip')
    processed = 0
    errors    = []

    try:
        with zipfile.ZipFile(zip_path, 'r') as zin:
            names = [n for n in zin.namelist()
                     if not n.startswith('__MACOSX')
                     and Path(n).suffix.lower() in {'.docx', '.pdf', '.txt'}]

            if not names:
                flash('No supported files (.docx/.pdf/.txt) found in ZIP.', 'error')
                return redirect(url_for('index'))

            with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for name in names:
                    tmp_in  = os.path.join(upload_dir, f'{uuid.uuid4().hex}_{Path(name).name}')
                    stem    = Path(name).stem
                    ext     = Path(name).suffix.lower()
                    out_name= f'{stem}_cited_{style}{ext}'
                    tmp_out = os.path.join(upload_dir, f'{uuid.uuid4().hex}_{out_name}')
                    try:
                        data = zin.read(name)
                        with open(tmp_in, 'wb') as f:
                            f.write(data)
                        result_path = process_document(tmp_in, style, tmp_out, print_report=False)
                        zout.write(result_path, out_name)
                        processed += 1
                    except Exception as e:
                        errors.append(f'{name}: {str(e)}')
                    finally:
                        for p in (tmp_in, tmp_out):
                            try: os.remove(p)
                            except OSError: pass

        download_name = f'cited_{style}_batch.zip'
        return send_file(output_zip_path, as_attachment=True, download_name=download_name)

    except zipfile.BadZipFile:
        flash('Invalid ZIP file.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Batch processing error: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        try: os.remove(zip_path)
        except OSError: pass


# ── HTML diff export ──────────────────────────────────────────────────────────

@app.route('/download/diff/<result_id>')
def download_diff_html(result_id: str):
    """
    Generate a downloadable HTML diff report for a processed document.
    """
    entry = _safe_db_call(db.get_history, result_id) if _DB_OK else None
    if not entry:
        abort(404)

    result_path = entry.get('result_path')
    if not result_path or not os.path.exists(result_path):
        abort(404)

    try:
        ext = Path(entry['output_name']).suffix.lower()
        cited_text = read_text(result_path) if ext == '.txt' else ''

        html = _build_diff_html(
            filename=entry['filename'],
            style=entry['style'],
            cited_text=cited_text,
            total_refs=entry.get('total_refs', 0),
            cited_refs=entry.get('cited_refs', 0),
            avg_conf=entry.get('avg_conf', 0),
        )

        from flask import Response
        return Response(
            html,
            mimetype='text/html',
            headers={'Content-Disposition': f'attachment; filename="diff_{entry["filename"]}.html"'}
        )
    except Exception as e:
        flash(f'Could not generate diff: {str(e)}', 'error')
        return redirect(url_for('result_page', result_id=result_id))


def _build_diff_html(filename, style, cited_text, total_refs, cited_refs, avg_conf):
    """Build a self-contained HTML diff report."""
    import html as html_mod

    # Highlight citation markers
    import re
    highlighted = re.sub(
        r'(\([A-Z][a-z]+(?:\s+et\s+al\.)?(?:,\s*\d{4})?(?:\s*[a-z])?\)|\[\d+\]|[⁰¹²³⁴⁵⁶⁷⁸⁹]+)',
        r'<mark class="cite">\1</mark>',
        html_mod.escape(cited_text)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Citation Diff — {html_mod.escape(filename)}</title>
<style>
  body {{ font-family: system-ui,-apple-system,sans-serif; background:#0d1117; color:#e6edf3;
          padding:2rem; line-height:1.7; }}
  h1   {{ font-size:1.5rem; margin-bottom:.25rem; }}
  .meta {{ color:#8b949e; font-size:.9rem; margin-bottom:2rem; }}
  .stats {{ display:flex; gap:1.5rem; flex-wrap:wrap; margin-bottom:2rem; }}
  .stat {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
            padding:.75rem 1.25rem; text-align:center; }}
  .stat strong {{ display:block; font-size:1.5rem; color:#58a6ff; }}
  .stat span   {{ font-size:.8rem; color:#8b949e; }}
  pre  {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
           padding:1.5rem; white-space:pre-wrap; word-break:break-word;
           font-size:.85rem; font-family:'JetBrains Mono',monospace; }}
  mark.cite {{ background:rgba(63,185,80,.25); color:#3fb950;
               border-radius:3px; padding:.05rem .2rem;
               border-bottom:2px solid #3fb950; }}
  footer {{ margin-top:3rem; color:#6e7681; font-size:.8rem; }}
</style>
</head>
<body>
<h1>📄 Citation Diff Report</h1>
<div class="meta">File: <strong>{html_mod.escape(filename)}</strong> · Style: <strong>{style.upper()}</strong></div>
<div class="stats">
  <div class="stat"><strong>{total_refs}</strong><span>Total refs</span></div>
  <div class="stat"><strong>{cited_refs}</strong><span>Cited</span></div>
  <div class="stat"><strong>{avg_conf:.0f}%</strong><span>Avg confidence</span></div>
</div>
<pre>{highlighted}</pre>
<footer>Generated by Auto-Citer v2.0 · <mark class="cite">highlighted</mark> = inserted citation</footer>
</body></html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=' * 56)
    print('  Auto-Citer v2.0')
    print('  http://localhost:5000')
    print(f'  Styles: {", ".join(SUPPORTED_STYLES)}')
    if _DB_OK and db:
        print('  DB:', db.db_path)
    print('=' * 56)
    app.run(
        debug=os.environ.get('FLASK_DEBUG', '0') == '1',
        port=int(os.environ.get('PORT', 5000))
    )
