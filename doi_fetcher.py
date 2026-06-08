"""
doi_fetcher.py  –  Fetch reference metadata from CrossRef and PubMed.

Usage:
    from doi_fetcher import fetch_by_doi, fetch_by_pmid, search_crossref

Free APIs, no API key required (CrossRef asks for polite pool email).
"""

import re
import time
import urllib.request
import urllib.parse
import json
from typing import Optional, Dict

# Polite pool identifier (CrossRef API)
_USER_AGENT = 'AutoCiter/2.0 (https://github.com/manisreethaar/citation--app)'
_CROSSREF_BASE = 'https://api.crossref.org'
_PUBMED_BASE   = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'

# Simple in-memory cache (DOI → metadata)
_cache: Dict[str, Dict] = {}


def fetch_by_doi(doi: str, timeout: int = 8) -> Optional[Dict]:
    """
    Fetch reference metadata from CrossRef by DOI.

    Args:
        doi: Can be bare DOI ("10.1038/nature12345") or full URL.

    Returns:
        dict with keys: authors, year, title, journal, volume, issue, pages, doi, raw
        or None if not found / error.
    """
    doi = _clean_doi(doi)
    if not doi:
        return None

    cache_key = f'doi:{doi}'
    if cache_key in _cache:
        return _cache[cache_key]

    url = f'{_CROSSREF_BASE}/works/{urllib.parse.quote(doi)}'
    try:
        data = _get_json(url, timeout)
    except Exception:
        return None

    if not data or data.get('status') != 'ok':
        return None

    item = data.get('message', {})
    result = _parse_crossref_item(item)
    if result:
        _cache[cache_key] = result
    return result


def fetch_by_pmid(pmid: str, timeout: int = 8) -> Optional[Dict]:
    """
    Fetch reference metadata from PubMed by PMID.
    """
    pmid = re.sub(r'\D', '', str(pmid))
    if not pmid:
        return None

    cache_key = f'pmid:{pmid}'
    if cache_key in _cache:
        return _cache[cache_key]

    # Use esummary to get metadata
    url = (f'{_PUBMED_BASE}/esummary.fcgi'
           f'?db=pubmed&id={pmid}&retmode=json')
    try:
        data = _get_json(url, timeout)
    except Exception:
        return None

    result_data = data.get('result', {}) if data else {}
    item = result_data.get(pmid)
    if not item:
        return None

    result = _parse_pubmed_item(item, pmid)
    if result:
        _cache[cache_key] = result
    return result


def search_crossref(query: str, limit: int = 5, timeout: int = 8) -> list:
    """
    Full-text search CrossRef for references matching a query string.
    Returns list of metadata dicts.
    """
    params = urllib.parse.urlencode({
        'query': query,
        'rows': limit,
        'select': 'DOI,title,author,published,container-title,volume,issue,page'
    })
    url = f'{_CROSSREF_BASE}/works?{params}'
    try:
        data = _get_json(url, timeout)
    except Exception:
        return []

    if not data or data.get('status') != 'ok':
        return []

    items = data.get('message', {}).get('items', [])
    results = []
    for item in items:
        parsed = _parse_crossref_item(item)
        if parsed:
            results.append(parsed)
    return results


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_crossref_item(item: dict) -> Optional[Dict]:
    """Convert a CrossRef API item to our internal format."""
    if not item:
        return None

    # Authors
    authors = []
    for a in item.get('author', []):
        family = a.get('family', '')
        given  = a.get('given', '')
        if family:
            authors.append(f'{family}, {given}' if given else family)

    # Year
    year = None
    pub  = item.get('published') or item.get('published-print') or item.get('published-online')
    if pub:
        dp = pub.get('date-parts', [[]])
        if dp and dp[0]:
            year = str(dp[0][0])

    # Title
    titles = item.get('title', [])
    title = titles[0] if titles else None

    # Journal
    journals = item.get('container-title', [])
    journal  = journals[0] if journals else None

    doi   = item.get('DOI', '')
    vol   = item.get('volume', '')
    issue = item.get('issue', '')
    pages = item.get('page', '')

    # Build raw string
    raw_parts = []
    if authors: raw_parts.append('; '.join(authors[:3]) + (' et al.' if len(authors) > 3 else ''))
    if year:    raw_parts.append(f'({year})')
    if title:   raw_parts.append(title + '.')
    if journal: raw_parts.append(journal)
    if vol:
        v = vol
        if issue: v += f'({issue})'
        raw_parts.append(v)
    if pages:   raw_parts.append(pages)
    if doi:     raw_parts.append(f'https://doi.org/{doi}')
    raw = ' '.join(raw_parts)

    return {
        'authors': authors,
        'year':    year,
        'title':   title,
        'journal': journal,
        'volume':  vol or None,
        'issue':   issue or None,
        'pages':   pages or None,
        'doi':     f'https://doi.org/{doi}' if doi else None,
        'raw':     raw,
        'source':  'crossref'
    }


def _parse_pubmed_item(item: dict, pmid: str) -> Optional[Dict]:
    """Convert a PubMed esummary item to our internal format."""
    if not item:
        return None

    title = item.get('title', '')
    year  = None
    pub_date = item.get('pubdate', '')
    if pub_date:
        m = re.search(r'\b(19|20)\d{2}\b', pub_date)
        if m: year = m.group()

    # Authors
    authors = []
    for a in item.get('authors', []):
        name = a.get('name', '')
        if name:
            authors.append(name)

    journal = item.get('source', '')
    volume  = item.get('volume', '')
    issue   = item.get('issue', '')
    pages   = item.get('pages', '')
    doi     = None

    # Try to get DOI from articleids
    for aid in item.get('articleids', []):
        if aid.get('idtype') == 'doi':
            doi = f"https://doi.org/{aid.get('value', '')}"
            break

    raw_parts = []
    if authors: raw_parts.append('; '.join(authors[:3]) + (' et al.' if len(authors) > 3 else ''))
    if year:    raw_parts.append(f'({year})')
    if title:   raw_parts.append(title)
    if journal: raw_parts.append(journal)
    if volume:  raw_parts.append(volume + (f'({issue})' if issue else ''))
    if pages:   raw_parts.append(pages)
    if doi:     raw_parts.append(doi)
    raw = '. '.join(raw_parts)

    return {
        'authors': authors,
        'year':    year,
        'title':   title,
        'journal': journal,
        'volume':  volume or None,
        'issue':   issue or None,
        'pages':   pages or None,
        'doi':     doi,
        'pmid':    pmid,
        'raw':     raw,
        'source':  'pubmed'
    }


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get_json(url: str, timeout: int) -> Optional[dict]:
    req = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _clean_doi(doi: str) -> str:
    """Normalise DOI: strip URL prefix, whitespace."""
    doi = doi.strip()
    doi = re.sub(r'^https?://doi\.org/', '', doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE)
    return doi.strip()
