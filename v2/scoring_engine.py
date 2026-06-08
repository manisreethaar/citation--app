"""
scoring_engine.py
==================
Core model 3: Matching is scoring, not pattern firing.

For every sentence × reference pair, we compute a relevance score
from multiple independent signals. Citations are inserted only when
the score crosses a confidence threshold.

This replaces the old regex-fire approach entirely.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from document_model import Sentence, SentenceRole, SectionType
from reference_model import Reference, Domain


# ─── Score thresholds ─────────────────────────────────────────────────────────

THRESHOLD_AUTO   = 0.55   # Insert automatically — high confidence
THRESHOLD_REVIEW = 0.25   # Flag for user review — medium confidence
# Below THRESHOLD_REVIEW → do not cite


# ─── Match result ─────────────────────────────────────────────────────────────

@dataclass
class Match:
    sentence: Sentence
    reference: Reference
    score: float
    signals: Dict[str, float] = field(default_factory=dict)
    auto: bool = False          # True if score >= THRESHOLD_AUTO
    needs_review: bool = False  # True if THRESHOLD_REVIEW <= score < THRESHOLD_AUTO

    def __repr__(self):
        tag = "AUTO" if self.auto else ("REVIEW" if self.needs_review else "SKIP")
        return f"[{tag} {self.score:.2f}] Ref {self.reference.index} ← {self.sentence.text[:50]}..."


# ─── Signal implementations ───────────────────────────────────────────────────

# Contexts where a surname is clearly NOT a citation (false positive suppression)
_NON_CITE_CONTEXT = re.compile(
    r'(university|institute|college|laboratory|lab|hospital|school|'
    r'foundation|center|centre|department|dept|award|prize|'
    r'association|society|federation|named\s+after|in\s+honor)\b',
    re.I
)

def _signal_author_mention(sentence: Sentence, ref: Reference) -> float:
    """
    Signal A: Does the reference's first author surname appear in this sentence?
    Context-aware — suppresses false positives.
    Score: 0.0 – 0.60
    """
    surname = ref.first_surname
    if not surname or len(surname) < 3:
        return 0.0

    pattern = re.compile(rf'(?<!\w){re.escape(surname)}(?!\w)', re.I)
    match = pattern.search(sentence.text)
    if not match:
        return 0.0

    # Check surrounding context for false-positive indicators
    start = max(0, match.start() - 40)
    end = min(len(sentence.text), match.end() + 40)
    context = sentence.text[start:end]
    if _NON_CITE_CONTEXT.search(context):
        return 0.0   # "Smith University" → not a citation

    # Check if "et al." follows → stronger signal
    after = sentence.text[match.end():match.end() + 20]
    if re.search(r'\bet\s+al\.?', after, re.I):
        return 0.60  # "Smith et al." — very likely a citation

    return 0.45  # bare surname mention


def _signal_year_proximity(sentence: Sentence, ref: Reference) -> float:
    """
    Signal B: Does the reference year appear near the author mention?
    Acts as a multiplier on signal A.
    Score: 0.0 – 0.25
    """
    if not ref.year:
        return 0.0
    pattern = re.compile(rf'\b{re.escape(ref.year)}\b')
    if pattern.search(sentence.text):
        return 0.25
    return 0.0


def _signal_keyword_overlap(sentence: Sentence, ref: Reference) -> float:
    """
    Signal C: How many of the reference's title noun phrases appear in the sentence?
    This is the PRIMARY signal for the 'no author name' case.
    Score: 0.0 – 0.35 (capped — keyword overlap alone cannot auto-cite)
    """
    if not ref.noun_phrases:
        return 0.0

    sent_lower = sentence.text.lower()
    hits = sum(1 for phrase in ref.noun_phrases if phrase in sent_lower)

    if hits == 0:
        return 0.0

    # Normalise: more hits = higher score, but cap at 0.35
    # (keyword overlap alone stays below THRESHOLD_AUTO so it needs other signals)
    raw = hits / max(len(ref.noun_phrases), 1)
    return min(raw * 0.6, 0.35)


def _signal_domain_match(sentence: Sentence, ref: Reference) -> float:
    """
    Signal D: Does the reference's domain match the section's domain?
    Methods sections should cite method-domain refs, etc.
    Score: 0.0 – 0.10
    """
    # Methods section: method-type references get a small boost
    if (sentence.section_type == SectionType.METHODS and
            ref.claim_type.value == 'method'):
        return 0.10

    # Introduction/Discussion: background/finding refs get a small boost
    if (sentence.section_type in (SectionType.INTRODUCTION, SectionType.DISCUSSION) and
            ref.claim_type.value in ('background', 'finding', 'review')):
        return 0.05

    return 0.0


def _signal_sentence_role(sentence: Sentence, ref: Reference) -> float:
    """
    Signal E: Is this sentence the kind that NEEDS a citation?
    Author's own sentences should never get citations.
    Claim sentences need them most.
    Score: modifier applied to total
    """
    if sentence.role == SentenceRole.AUTHOR_OWN:
        return -1.0    # Hard veto — never cite author's own sentences
    if sentence.role == SentenceRole.TRANSITION:
        return -0.3    # Transitions rarely need citations
    if sentence.role == SentenceRole.CLAIM:
        return 0.10    # Claims are the primary citation targets
    if sentence.role == SentenceRole.METHOD:
        return 0.05
    return 0.0


def _signal_existing_marker(sentence: Sentence, ref: Reference,
                             inventory: Dict[int, List[int]]) -> float:
    """
    Signal F: Was this reference already cited at/near this sentence position
    (detected in the pre-pass citation inventory)?
    Score: 0.80 — highest possible, treated as near-certain
    """
    if ref.index in inventory.get(sentence.index, []):
        return 0.80
    return 0.0


# ─── Master scorer ────────────────────────────────────────────────────────────

def score_pair(sentence: Sentence, ref: Reference,
               inventory: Dict[int, List[int]] = None) -> Match:
    """
    Compute total relevance score for a (sentence, reference) pair.
    Returns a Match object with breakdown of all signals.
    """
    if inventory is None:
        inventory = {}

    signals = {}

    # Signal F first — if this was already cited here, it's near-certain
    sig_f = _signal_existing_marker(sentence, ref, inventory)
    signals['existing_marker'] = sig_f

    sig_e = _signal_sentence_role(sentence, ref)
    signals['sentence_role'] = sig_e

    # Hard veto: author's own sentence
    if sig_e <= -1.0:
        return Match(sentence=sentence, reference=ref, score=0.0,
                     signals=signals, auto=False, needs_review=False)

    sig_a = _signal_author_mention(sentence, ref)
    sig_b = _signal_year_proximity(sentence, ref)
    sig_c = _signal_keyword_overlap(sentence, ref)
    sig_d = _signal_domain_match(sentence, ref)

    signals.update({
        'author_mention':  sig_a,
        'year_proximity':  sig_b,
        'keyword_overlap': sig_c,
        'domain_match':    sig_d,
    })

    # Year acts as a multiplier on author mention, not an additive signal
    if sig_a > 0 and sig_b > 0:
        author_year_combined = sig_a + sig_b
    else:
        author_year_combined = sig_a

    total = sig_f + author_year_combined + sig_c + sig_d + sig_e

    # Clamp to [0, 1]
    total = max(0.0, min(1.0, total))

    return Match(
        sentence=sentence,
        reference=ref,
        score=total,
        signals=signals,
        auto=(total >= THRESHOLD_AUTO),
        needs_review=(THRESHOLD_REVIEW <= total < THRESHOLD_AUTO),
    )


# ─── Document-level scoring ───────────────────────────────────────────────────

def score_document(sentences: List[Sentence], refs: List[Reference],
                   inventory: Dict[int, List[int]] = None) -> List[Match]:
    """
    Score all (sentence, reference) pairs.
    Returns only matches above THRESHOLD_REVIEW (filters noise).
    """
    if inventory is None:
        inventory = {}

    results = []
    for ref in refs:
        for sentence in sentences:
            match = score_pair(sentence, ref, inventory)
            if match.score >= THRESHOLD_REVIEW:
                results.append(match)

    return results


def best_matches_per_ref(all_matches: List[Match]) -> Dict[int, List[Match]]:
    """
    For each reference, return all matches sorted by score descending.
    Key = reference.index
    """
    by_ref: Dict[int, List[Match]] = {}
    for m in all_matches:
        by_ref.setdefault(m.reference.index, []).append(m)
    for idx in by_ref:
        by_ref[idx].sort(key=lambda x: x.score, reverse=True)
    return by_ref


def best_matches_per_sentence(all_matches: List[Match]) -> Dict[int, List[Match]]:
    """
    For each sentence index, return all matches sorted by score descending.
    """
    by_sent: Dict[int, List[Match]] = {}
    for m in all_matches:
        by_sent.setdefault(m.sentence.index, []).append(m)
    for idx in by_sent:
        by_sent[idx].sort(key=lambda x: x.score, reverse=True)
    return by_sent
