"""
web_checker.py
===============
Web-based plagiarism check using Google Custom Search API.

For each "suspicious" sentence (long, content-rich), we:
  1. Extract a distinctive 8-10 word phrase
  2. Query Google Custom Search API
  3. Fetch the top results
  4. Compare fetched text against the original sentence

Requires:
  - Google Custom Search API key   (GOOGLE_API_KEY env var or passed directly)
  - Google Custom Search Engine ID (GOOGLE_CSE_ID  env var or passed directly)
  Both are FREE up to 100 queries/day.
  Get them at: https://programmablesearchengine.google.com/

Usage:
  from web_checker import web_check
  web_matches = web_check(doc_text, api_key="...", cse_id="...")
"""

import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from config import GOOGLE_API_KEY as _CFG_API_KEY, GOOGLE_CSE_ID as _CFG_CSE_ID
except ImportError:
    _CFG_API_KEY = ''
    _CFG_CSE_ID  = ''

from plagiarism_engine import (
    _normalize, _words, _shingles, _jaccard,
    _rare_phrase_overlap, EXACT_THRESHOLD, _STOPWORDS
)


# ─── Configuration ────────────────────────────────────────────────────────────

MAX_QUERIES      = 20   # max API calls per document (100/day free quota)
MIN_SENTENCE_LEN = 12   # skip sentences shorter than this (words)
QUERY_PHRASE_LEN = 9    # words to extract as search query
WEB_JAC_THRESH   = 0.20 # lower threshold for web matches (shorter snippets)


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class WebMatch:
    sentence: str           # original sentence from doc
    url: str                # matched URL
    page_title: str
    snippet: str            # Google's snippet or fetched excerpt
    jaccard: float
    rare_phrases: List[str]
    query_used: str

    @property
    def risk_level(self) -> str:
        if self.jaccard >= 0.50:
            return "HIGH"
        if self.jaccard >= WEB_JAC_THRESH or self.rare_phrases:
            return "MEDIUM"
        return "LOW"

    def summary(self) -> str:
        phrases_str = ''
        if self.rare_phrases:
            phrases_str = '\n    Shared: ' + '; '.join(f'"{p}"' for p in self.rare_phrases[:2])
        return (
            f"  [{self.risk_level}] Web match (Jaccard={self.jaccard:.2f})\n"
            f"    Doc sentence : \"{self.sentence[:100]}{'...' if len(self.sentence)>100 else ''}\"\n"
            f"    Source URL   : {self.url}\n"
            f"    Page title   : {self.page_title}\n"
            f"    Snippet      : \"{self.snippet[:120]}\""
            f"{phrases_str}"
        )


# ─── Sentence extraction ──────────────────────────────────────────────────────

def _split_sentences(text: str) -> List[str]:
    """Simple sentence splitter (reuse from document_model logic)."""
    text = re.sub(r'\s+', ' ', text)
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [p.strip() for p in parts if len(p.split()) >= MIN_SENTENCE_LEN]


def _pick_query_phrase(sentence: str) -> str:
    """
    Extract the most distinctive phrase from a sentence for web search.
    Prefer content-word-dense segments.
    """
    ws = sentence.split()
    best_phrase = ''
    best_score = -1
    for i in range(len(ws) - QUERY_PHRASE_LEN + 1):
        phrase_words = ws[i:i + QUERY_PHRASE_LEN]
        phrase = ' '.join(phrase_words)
        content_count = sum(1 for w in phrase_words
                            if w.lower().strip('.,;:') not in _STOPWORDS
                            and len(w) > 3)
        if content_count > best_score:
            best_score = content_count
            best_phrase = phrase
    return best_phrase or ' '.join(ws[:QUERY_PHRASE_LEN])


# ─── Google Custom Search API ─────────────────────────────────────────────────

def _google_search(query: str, api_key: str, cse_id: str,
                   num: int = 5) -> List[dict]:
    """
    Call Google Custom Search API. Returns list of result dicts:
      {title, link, snippet}
    Returns [] on error (network issue, quota exceeded, etc.)
    """
    params = urllib.parse.urlencode({
        'q':   f'"{query}"',   # exact phrase search
        'key': api_key,
        'cx':  cse_id,
        'num': num,
    })
    url = f'https://www.googleapis.com/customsearch/v1?{params}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'auto-citer-plagcheck/2.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get('items', [])
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("[web_checker] Google API quota exceeded for today.")
        return []
    except Exception:
        return []


def _fetch_page_text(url: str, max_chars: int = 3000) -> str:
    """Fetch raw text from a URL (best-effort, no JS rendering)."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; auto-citer/2.0)',
                'Accept': 'text/html',
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read(max_chars * 5).decode('utf-8', errors='ignore')
        # Strip HTML tags
        raw = re.sub(r'<[^>]+>', ' ', raw)
        raw = re.sub(r'&[a-z]+;', ' ', raw)
        raw = re.sub(r'\s+', ' ', raw)
        return raw[:max_chars]
    except Exception:
        return ''


# ─── Main web checker ─────────────────────────────────────────────────────────

def web_check(
    doc_text: str,
    api_key: Optional[str] = None,
    cse_id: Optional[str] = None,
    max_queries: int = MAX_QUERIES,
) -> List[WebMatch]:
    """
    Check doc_text sentences against the web via Google Custom Search.

    api_key and cse_id can also be set via environment variables:
      GOOGLE_API_KEY, GOOGLE_CSE_ID

    Returns list of WebMatch objects for any sentences with web matches.
    Returns [] if no API key is configured (graceful degradation).
    """
    api_key = api_key or os.environ.get('GOOGLE_API_KEY', '') or _CFG_API_KEY
    cse_id  = cse_id  or os.environ.get('GOOGLE_CSE_ID', '')  or _CFG_CSE_ID

    if not api_key or not cse_id:
        print(
            "[web_checker] No Google API key configured — skipping web check.\n"
            "  Set GOOGLE_API_KEY and GOOGLE_CSE_ID environment variables\n"
            "  or pass them to web_check() to enable web search.\n"
            "  Get free keys at: https://programmablesearchengine.google.com/"
        )
        return []

    sentences = _split_sentences(doc_text)

    # Deduplicate very similar sentences
    seen_phrases: set = set()
    unique_sentences = []
    for s in sentences:
        phrase = _pick_query_phrase(s)
        if phrase not in seen_phrases:
            seen_phrases.add(phrase)
            unique_sentences.append(s)

    matches: List[WebMatch] = []
    queries_used = 0

    for sentence in unique_sentences:
        if queries_used >= max_queries:
            print(f"[web_checker] Reached max queries ({max_queries}). Stopping web check.")
            break

        query = _pick_query_phrase(sentence)
        results = _google_search(query, api_key, cse_id)
        queries_used += 1

        for item in results:
            url     = item.get('link', '')
            title   = item.get('title', '')
            snippet = item.get('snippet', '')

            # Compare sentence against snippet first (fast)
            j_snippet = _jaccard(_shingles(sentence), _shingles(snippet))
            rp_snippet = _rare_phrase_overlap(sentence, snippet)

            if j_snippet >= WEB_JAC_THRESH or rp_snippet:
                matches.append(WebMatch(
                    sentence=sentence,
                    url=url,
                    page_title=title,
                    snippet=snippet,
                    jaccard=j_snippet,
                    rare_phrases=rp_snippet,
                    query_used=query,
                ))
                break  # one match per sentence is enough

            # If snippet alone isn't enough, fetch the full page
            if j_snippet >= WEB_JAC_THRESH * 0.5:
                page_text = _fetch_page_text(url)
                if page_text:
                    j_page = _jaccard(_shingles(sentence), _shingles(page_text))
                    rp_page = _rare_phrase_overlap(sentence, page_text)
                    if j_page >= WEB_JAC_THRESH or rp_page:
                        matches.append(WebMatch(
                            sentence=sentence,
                            url=url,
                            page_title=title,
                            snippet=snippet,
                            jaccard=j_page,
                            rare_phrases=rp_page,
                            query_