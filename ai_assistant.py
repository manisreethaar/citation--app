"""
ai_assistant.py  –  Gemini-powered citation intelligence for Auto-Citer
========================================================================

Three capabilities:
  1. ai_parse_reference(raw)     – parse a messy/unknown reference into structured fields
  2. ai_suggest_missing(body, refs) – find sentences that likely need citations
  3. ai_complete_reference(partial)  – enrich/complete partial reference metadata

All functions return {} / [] gracefully if no API key is set or quota exceeded.
Set GEMINI_API_KEY in your .env file to enable.
"""

import os
import json
import re
import time
import hashlib
import logging
from typing import Optional, List, Dict, Any

log = logging.getLogger(__name__)

# ── Lazy model init ───────────────────────────────────────────────────────────

_genai   = None
_model   = None
_last_ts = 0.0
_req_count = 0
_RATE_LIMIT = 12   # max requests per minute

_CACHE: Dict[str, Any] = {}   # simple in-memory cache (key=hash, val=response)
_CACHE_MAX = 200

GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')


def is_available() -> bool:
    """Return True if a Gemini API key is configured."""
    return bool(os.environ.get('GEMINI_API_KEY', '').strip())


def _get_model():
    global _genai, _model
    if _model is not None:
        return _model
    try:
        import google.generativeai as genai
        _genai = genai
        genai.configure(api_key=os.environ.get('GEMINI_API_KEY', ''))
        _model = genai.GenerativeModel(GEMINI_MODEL)
        return _model
    except ImportError:
        log.warning('google-generativeai not installed. Run: pip install google-generativeai')
        return None
    except Exception as e:
        log.error('Gemini init error: %s', e)
        return None


def _rate_ok() -> bool:
    """Simple per-minute rate limiter."""
    global _last_ts, _req_count
    now = time.time()
    if now - _last_ts > 60:
        _last_ts  = now
        _req_count = 0
    _req_count += 1
    return _req_count <= _RATE_LIMIT


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _call_gemini(prompt: str, temperature: float = 0.1) -> Optional[str]:
    """
    Call Gemini with a prompt. Returns text response or None on error.
    Handles rate limiting, caching, and graceful failures.
    """
    if not is_available():
        return None

    key = _cache_key(prompt)
    if key in _CACHE:
        return _CACHE[key]

    if not _rate_ok():
        log.warning('Gemini rate limit reached')
        return None

    model = _get_model()
    if model is None:
        return None

    try:
        config = _genai.GenerationConfig(temperature=temperature, max_output_tokens=1024)
        response = model.generate_content(prompt, generation_config=config)
        text = response.text.strip()

        # Cache result
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = text
        return text

    except Exception as e:
        log.error('Gemini API error: %s', e)
        return None


def _extract_json(text: str) -> Any:
    """
    Robustly extract JSON from a Gemini response that may include
    markdown fences like ```json ... ``` or plain text.
    """
    if not text:
        return None
    # Remove markdown fences
    clean = re.sub(r'```(?:json)?\s*', '', text)
    clean = re.sub(r'```', '', clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Try to extract just the JSON object/array
        for pattern in [r'\{.*\}', r'\[.*\]']:
            m = re.search(pattern, clean, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
    return None


# ── Feature 1: Parse malformed reference ─────────────────────────────────────

_PARSE_PROMPT = """You are a reference parser for academic citations. Parse the following raw text into structured fields.

Return ONLY valid JSON — no markdown, no explanation. Use null for unknown fields.

Required JSON format:
{{
  "authors": ["Surname F", "Surname2 G"],
  "year": "2020",
  "title": "Full article title",
  "journal": "Journal name",
  "volume": "10",
  "issue": "2",
  "pages": "1-5",
  "doi": "https://doi.org/10.xxx/yyy",
  "ref_type": "article"
}}

ref_type must be one of: article, book, chapter, web, preprint, report, thesis

Raw reference text:
{raw}
"""

def ai_parse_reference(raw_text: str) -> Dict[str, Any]:
    """
    Use Gemini to parse a raw/messy reference string into structured fields.
    Returns dict with keys: authors, year, title, journal, volume, issue, pages, doi, ref_type
    Returns {} if AI unavailable or parsing fails.
    """
    if not raw_text or not raw_text.strip():
        return {}

    prompt   = _PARSE_PROMPT.format(raw=raw_text.strip()[:800])
    response = _call_gemini(prompt)
    if not response:
        return {}

    data = _extract_json(response)
    if not isinstance(data, dict):
        return {}

    # Validate and sanitise
    result = {}
    for key in ('year', 'title', 'journal', 'volume', 'issue', 'pages', 'doi', 'ref_type'):
        val = data.get(key)
        if val and str(val).strip():
            result[key] = str(val).strip()

    authors = data.get('authors', [])
    if isinstance(authors, list):
        result['authors'] = [str(a).strip() for a in authors if a]

    return result


# ── Feature 2: Suggest missing citations ─────────────────────────────────────

_SUGGEST_PROMPT = """You are reviewing an academic paper body text. Identify sentences that make factual claims, cite statistics, reference findings or studies, but are MISSING an inline citation.

Known references already in the document (don't suggest these need citation if the author name+year appears nearby):
{ref_list}

Rules:
- Only flag sentences where a citation is clearly expected but absent
- Ignore opinion/transition sentences
- Ignore sentences that already have citations in brackets or parentheses nearby
- Focus on: statistics, experimental results, prior work claims, specific findings

Return a JSON array of objects. Maximum 8 items. Return [] if no issues found.
Format:
[
  {{
    "sentence": "exact snippet (max 120 chars)",
    "reason": "why this needs a citation",
    "confidence": "high"
  }}
]
confidence: "high" = almost certainly needs citation, "medium" = likely needs one

Document body excerpt (first 3000 chars):
{body}
"""

def ai_suggest_missing_citations(body: str, refs: list) -> List[Dict[str, str]]:
    """
    Scan document body and suggest sentences likely missing citations.
    refs: list of Reference objects or dicts.
    Returns list of {sentence, reason, confidence} dicts.
    """
    if not body or not body.strip():
        return []

    # Build compact ref list
    ref_lines = []
    for r in refs[:30]:
        if hasattr(r, 'authors'):
            author = r.first_author_surname or (r.authors[0] if r.authors else '?')
            year   = r.year or 'n.d.'
            title  = (r.title or '')[:60]
            ref_lines.append(f"[{r.index}] {author} ({year}) — {title}")
        elif isinstance(r, dict):
            ref_lines.append(f"[{r.get('index','?')}] {r.get('authors',['?'])[0]} ({r.get('year','n.d.')})")

    ref_list = '\n'.join(ref_lines) if ref_lines else 'None provided'

    prompt   = _SUGGEST_PROMPT.format(
        ref_list=ref_list,
        body=body[:3000]
    )
    response = _call_gemini(prompt)
    if not response:
        return []

    data = _extract_json(response)
    if not isinstance(data, list):
        return []

    results = []
    for item in data[:8]:
        if not isinstance(item, dict):
            continue
        sentence   = str(item.get('sentence', '')).strip()
        reason     = str(item.get('reason',   '')).strip()
        confidence = str(item.get('confidence', 'medium')).lower()
        if sentence and reason and confidence in ('high', 'medium'):
            results.append({
                'sentence':   sentence[:150],
                'reason':     reason[:200],
                'confidence': confidence
            })
    return results


# ── Feature 3: Complete / enrich partial reference ────────────────────────────

_COMPLETE_PROMPT = """You are an academic reference database. Complete the missing fields for this partial reference using your knowledge. Only fill fields you are confident about — do not guess.

Return ONLY valid JSON with these exact keys. Use null for any field you cannot confidently fill:
{{
  "authors":  ["Surname F", "Surname2 G"],
  "year":     "2020",
  "title":    "Full article title",
  "journal":  "Full journal name",
  "volume":   "10",
  "issue":    "2",
  "pages":    "1-5",
  "doi":      "https://doi.org/10.xxx/yyy",
  "ref_type": "article"
}}

Partial reference data:
{partial}
"""

def ai_complete_reference(partial: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use Gemini to enrich/complete a partial reference dict.
    partial: dict with some fields already known (e.g. from DOI or manual entry).
    Returns dict with completed fields merged in (existing fields preserved).
    """
    if not partial:
        return {}

    partial_text = json.dumps(partial, indent=2)
    prompt       = _COMPLETE_PROMPT.format(partial=partial_text[:600])
    response     = _call_gemini(prompt)
    if not response:
        return {}

    data = _extract_json(response)
    if not isinstance(data, dict):
        return {}

    # Merge: only fill null/missing fields from AI
    result = dict(partial)
    for key in ('year', 'title', 'journal', 'volume', 'issue', 'pages', 'doi', 'ref_type'):
        if not result.get(key) and data.get(key):
            result[key] = str(data[key]).strip()
    if not result.get('authors') and isinstance(data.get('authors'), list):
        result['authors'] = [str(a).strip() for a in data['authors'] if a]

    return result


# ── Feature 4: Format-detect + explain ───────────────────────────────────────

_FORMAT_PROMPT = """What citation style is this reference written in?
Choose from: APA, Vancouver, IEEE, MLA, Chicago, Harvard, AMA, Nature, or Unknown.
Also explain in one short sentence what style features you identified.

Return JSON only:
{{"style": "APA", "explanation": "Year in parentheses after authors, comma-separated authors"}}

Reference:
{ref}
"""

def ai_detect_style(raw_ref: str) -> Dict[str, str]:
    """
    Use Gemini to identify the citation style of a single reference.
    Returns {style, explanation} or {}.
    """
    if not raw_ref:
        return {}
    prompt   = _FORMAT_PROMPT.format(ref=raw_ref[:400])
    response = _call_gemini(prompt)
    if not response:
        return {}
    data = _extract_json(response)
    if isinstance(data, dict) and 'style' in data:
        return data
    return {}
