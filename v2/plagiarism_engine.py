"""
plagiarism_engine.py
=====================
Core plagiarism detection engine — no external ML libraries needed.

Three detection layers:
  Layer 1 — Exact / near-exact match via n-gram shingling + Jaccard similarity
  Layer 2 — Keyword overlap via TF-IDF cosine similarity
  Layer 3 — Rare-phrase detection (phrases unlikely to appear by coincidence)

Usage:
  from plagiarism_engine import check_document
  results = check_document(doc_text, sources)   # sources: list of (name, text)
  for match in results.matches:
      print(match.summary())
"""

import re
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Set
from collections import Counter


# ─── Configuration ────────────────────────────────────────────────────────────

CHUNK_SIZE       = 60    # words per chunk
CHUNK_OVERLAP    = 20    # word overlap between consecutive chunks
SHINGLE_N        = 5     # n-gram size for shingling
EXACT_THRESHOLD  = 0.25  # Jaccard ≥ this → flagged as match
HIGH_THRESHOLD   = 0.60  # Jaccard ≥ this → flagged as likely copied
RARE_PHRASE_LEN  = 6     # minimum words in a rare phrase to flag
MIN_CHUNK_WORDS  = 10    # skip chunks shorter than this


# ─── Stopwords ────────────────────────────────────────────────────────────────

_STOPWORDS = {
    'a','an','the','and','or','but','in','on','at','to','for','of','with',
    'by','from','is','are','was','were','be','been','have','has','had',
    'do','does','did','will','would','shall','should','may','might','must',
    'can','could','not','no','this','that','these','those','it','its',
    'as','if','then','than','so','such','each','all','both','into','also',
    'about','which','who','what','when','where','how','their','our','we',
    'they','he','she','his','her','him','them','us','me','my','your',
}


# ─── Text normalisation ───────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _words(text: str) -> List[str]:
    return _normalize(text).split()


def _content_words(text: str) -> List[str]:
    return [w for w in _words(text) if w not in _STOPWORDS and len(w) > 2]


# ─── Chunking ─────────────────────────────────────────────────────────────────

@dataclass
class TextChunk:
    text: str           # original (un-normalised) text
    word_start: int     # index of first word in parent document
    word_end: int
    chunk_index: int

    @property
    def preview(self) -> str:
        words = self.text.split()
        return ' '.join(words[:15]) + ('...' if len(words) > 15 else '')


def _chunk_text(text: str) -> List[TextChunk]:
    """Split text into overlapping word-window chunks."""
    words_raw = text.split()
    chunks = []
    i = 0
    idx = 0
    while i < len(words_raw):
        end = min(i + CHUNK_SIZE, len(words_raw))
        chunk_words = words_raw[i:end]
        if len(chunk_words) >= MIN_CHUNK_WORDS:
            chunks.append(TextChunk(
                text=' '.join(chunk_words),
                word_start=i,
                word_end=end,
                chunk_index=idx,
            ))
            idx += 1
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ─── Shingling ────────────────────────────────────────────────────────────────

def _shingles(text: str, n: int = SHINGLE_N) -> Set[str]:
    """Return set of n-word shingles from normalised text."""
    ws = _words(text)
    if len(ws) < n:
        return set()
    return {' '.join(ws[i:i+n]) for i in range(len(ws) - n + 1)}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ─── TF-IDF cosine similarity ─────────────────────────────────────────────────

def _tf(words: List[str]) -> Dict[str, float]:
    counts = Counter(words)
    total = max(len(words), 1)
    return {w: c / total for w, c in counts.items()}


def _cosine(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    shared = set(vec_a) & set(vec_b)
    dot = sum(vec_a[w] * vec_b[w] for w in shared)
    mag_a = math.sqrt(sum(v**2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(v**2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ─── Rare phrase detection ────────────────────────────────────────────────────

def _extract_rare_phrases(text: str, n: int = RARE_PHRASE_LEN) -> Set[str]:
    """
    Extract long phrases (≥ n words) from text that contain at least 2 content words.
    These are unlikely to match by accident.
    """
    ws = _words(text)
    phrases = set()
    for i in range(len(ws) - n + 1):
        phrase = ' '.join(ws[i:i+n])
        content = [w for w in ws[i:i+n] if w not in _STOPWORDS]
        if len(content) >= 2:
            phrases.add(phrase)
    return phrases


def _rare_phrase_overlap(a: str, b: str) -> List[str]:
    """Return phrases from a that appear verbatim in b (normalised)."""
    phrases_a = _extract_rare_phrases(a)
    norm_b = _normalize(b)
    return [p for p in phrases_a if p in norm_b]


# ─── Match result types ───────────────────────────────────────────────────────

@dataclass
class ChunkMatch:
    doc_chunk: TextChunk
    source_name: str
    source_chunk: TextChunk
    jaccard: float
    cosine: float
    rare_phrases: List[str]

    @property
    def risk_level(self) -> str:
        if self.jaccard >= HIGH_THRESHOLD:
            return "HIGH"
        if self.jaccard >= EXACT_THRESHOLD or self.cosine >= 0.70:
            return "MEDIUM"
        if self.rare_phrases:
            return "LOW"
        return "NONE"

    def summary(self) -> str:
        phrases_str = ''
        if self.rare_phrases:
            phrases_str = (
                f"\n    Shared phrases: "
                + '; '.join(f'"{p}"' for p in self.rare_phrases[:3])
            )
        return (
            f"  [{self.risk_level}] Jaccard={self.jaccard:.2f} "
            f"Cosine={self.cosine:.2f}\n"
            f"    Doc  : \"{self.doc_chunk.preview}\"\n"
            f"    Source ({self.source_name}): \"{self.source_chunk.preview}\""
            f"{phrases_str}"
        )


@dataclass
class PlagiarismResult:
    doc_word_count: int
    flagged_word_count: int
    matches: List[ChunkMatch] = field(default_factory=list)
    web_matches: List['WebMatch'] = field(default_factory=list)  # filled later

    @property
    def similarity_pct(self) -> float:
        if self.doc_word_count == 0:
            return 0.0
        return min(100.0, 100.0 * self.flagged_word_count / self.doc_word_count)

    @property
    def risk_label(self) -> str:
        pct = self.similarity_pct
        if pct >= 30:
            return "HIGH RISK"
        if pct >= 10:
            return "MEDIUM RISK"
        if pct >= 3:
            return "LOW RISK"
        return "LIKELY ORIGINAL"

    def sources_hit(self) -> List[str]:
        seen = []
        for m in self.matches:
            if m.source_name not in seen:
                seen.append(m.source_name)
        return seen


# ─── Main engine ──────────────────────────────────────────────────────────────

def check_document(
    doc_text: str,
    sources: List[Tuple[str, str]],   # list of (source_name, source_text)
) -> PlagiarismResult:
    """
    Compare doc_text against each source.

    sources = [("My source paper", full_text), ...]
    Returns PlagiarismResult with all ChunkMatch objects above threshold.
    """
    doc_chunks = _chunk_text(doc_text)
    doc_words  = len(doc_text.split())

    # Pre-compute source chunks + shingles
    source_data: List[Tuple[str, List[TextChunk], List[Set[str]]]] = []
    for src_name, src_text in sources:
        src_chunks = _chunk_text(src_text)
        src_shingles = [_shingles(c.text) for c in src_chunks]
        source_data.append((src_name, src_chunks, src_shingles))

    matches: List[ChunkMatch] = []
    flagged_ranges: List[Tuple[int, int]] = []   # (word_start, word_end) of flagged chunks

    for dc in doc_chunks:
        dc_shingles = _shingles(dc.text)
        dc_tf       = _tf(_content_words(dc.text))

        best_match: Optional[ChunkMatch] = None

        for src_name, src_chunks, src_shingles_list in source_data:
            for sc, sc_shingles in zip(src_chunks, src_shingles_list):
                j = _jaccard(dc_shingles, sc_shingles)
                if j < EXACT_THRESHOLD * 0.5:
                    continue  # fast skip

                c = _cosine(dc_tf, _tf(_content_words(sc.text)))
                rp = _rare_phrase_overlap(dc.text, sc.text)

                # Must pass at least one threshold
                if j < EXACT_THRESHOLD and c < 0.60 and not rp:
                    continue

                cm = ChunkMatch(
                    doc_chunk=dc,
                    source_name=src_name,
                    source_chunk=sc,
                    jaccard=j,
                    cosine=c,
                    rare_phrases=rp,
                )

                if best_match is None or cm.jaccard > best_match.jaccard:
                    best_match = cm

        if best_match and best_match.risk_level != "NONE":
            matches.append(best_match)
            flagged_ranges.append((dc.word_start, dc.word_end))

    # Count flagged words (de-duplicate overlapping chunks)
    flagged_words = 0
    if flagged_ranges:
        flagged_ranges.sort()
        merged = [flagged_ranges[0]]
        for s, e in flagged_ranges[1:]:
            if s < merged[-1][1]:
                mer