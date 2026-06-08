"""
ai_language_detector.py
=======================
Heuristic AI-language detector for academic prose.

This is intentionally local and transparent: it does not claim authorship
certainty. It scores sentence-level AI-likeness from visible writing signals
and reports where those signals appear.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict


_AI_PHRASES = [
    (r'\bit is important to note\b', 0.18, 'formulaic qualifier'),
    (r'\bit is worth noting\b', 0.18, 'formulaic qualifier'),
    (r'\bplays? a (?:crucial|critical|vital|significant) role\b', 0.16, 'common AI phrasing'),
    (r'\b(?:crucial|critical|vital|essential) (?:role|aspect|component)\b', 0.12, 'generic emphasis'),
    (r'\b(?:comprehensive|robust|holistic|multifaceted|nuanced) (?:approach|understanding|analysis|framework)\b', 0.14, 'generic academic phrasing'),
    (r'\bnot only\b.+\bbut also\b', 0.15, 'balanced template phrase'),
    (r'\bthis (?:highlights|underscores|emphasizes) the (?:importance|need|significance)\b', 0.14, 'formulaic conclusion'),
    (r'\bin (?:today\'s|the) (?:rapidly evolving|modern|contemporary) (?:world|landscape|era|context)\b', 0.18, 'stock opener'),
    (r'\bdelves? into\b', 0.14, 'AI-styled verb'),
    (r'\btapestry\b|\bseamless(?:ly)?\b|\bleverage(?:s|d)?\b', 0.12, 'AI-styled vocabulary'),
]

_TRANSITIONS = {
    'additionally', 'furthermore', 'moreover', 'therefore', 'thus',
    'consequently', 'however', 'nevertheless', 'in addition',
    'as a result', 'in conclusion', 'overall'
}

_HEDGES = {
    'may', 'might', 'could', 'can', 'often', 'generally', 'typically',
    'arguably', 'potentially', 'suggests', 'indicates'
}

_GENERIC_ACADEMIC = {
    'important', 'significant', 'effective', 'various', 'multiple',
    'complex', 'dynamic', 'critical', 'essential', 'comprehensive',
    'robust', 'innovative', 'context', 'framework', 'approach',
    'implications', 'insights', 'outcomes'
}


@dataclass
class SentenceScore:
    text: str
    start: int
    end: int
    line: int
    paragraph: int
    word_count: int
    score: float
    reasons: List[str] = field(default_factory=list)

    @property
    def percent(self) -> int:
        return round(self.score * 100)

    @property
    def tier(self) -> str:
        if self.score >= 0.72:
            return 'high'
        if self.score >= 0.48:
            return 'medium'
        return 'low'


def detect_ai_language(text: str) -> Dict:
    """Return overall and sentence-level AI-likeness analysis."""
    clean_text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    sentences = _split_sentences(clean_text)

    scored = [_score_sentence(clean_text, s) for s in sentences]
    scored = [s for s in scored if s.word_count >= 5]

    total_words = sum(s.word_count for s in scored)
    if not scored or total_words == 0:
        return {
            'overall_percent': 0,
            'total_words': 0,
            'ai_like_words': 0,
            'sentence_count': 0,
            'flagged_count': 0,
            'locations': [],
            'summary': 'No enough text to analyse.',
        }

    weighted_score = sum(s.score * s.word_count for s in scored) / total_words
    flagged = [s for s in scored if s.score >= 0.48]
    ai_like_words = round(sum(s.word_count * s.score for s in scored))

    locations = [
        {
            'sentence_index': i + 1,
            'line': s.line,
            'paragraph': s.paragraph,
            'start': s.start,
            'end': s.end,
            'word_count': s.word_count,
            'percent': s.percent,
            'tier': s.tier,
            'text': s.text,
            'reasons': s.reasons[:4],
        }
        for i, s in enumerate(scored)
        if s.score >= 0.36
    ]
    locations.sort(key=lambda item: item['percent'], reverse=True)

    return {
        'overall_percent': round(weighted_score * 100),
        'total_words': total_words,
        'ai_like_words': ai_like_words,
        'sentence_count': len(scored),
        'flagged_count': len(flagged),
        'locations': locations[:80],
        'summary': _summary(weighted_score, len(flagged), len(scored)),
    }


def _split_sentences(text: str) -> List[tuple]:
    abbreviations = re.compile(
        r'\b(?:et al|e\.g|i\.e|fig|eq|dr|mr|ms|mrs|prof|vs|no|vol|pp)\.$',
        re.I
    )
    spans = []
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in '.!?':
            i += 1
            continue

        before = text[max(start, i - 20):i + 1]
        if ch == '.' and abbreviations.search(before):
            i += 1
            continue
        if ch == '.' and i > 0 and i + 1 < len(text) and text[i - 1].isdigit() and text[i + 1].isdigit():
            i += 1
            continue

        j = i + 1
        while j < len(text) and text[j].isspace():
            j += 1
        if j >= len(text) or text[j].isupper() or text[j] in '"\'':
            raw = text[start:i + 1]
            stripped = raw.strip()
            if stripped:
                leading = len(raw) - len(raw.lstrip())
                spans.append((stripped, start + leading, i + 1))
            start = j
            i = j
        else:
            i += 1

    tail = text[start:]
    stripped = tail.strip()
    if stripped:
        leading = len(tail) - len(tail.lstrip())
        spans.append((stripped, start + leading, len(text) - (len(tail) - len(tail.rstrip()))))
    return spans


def _score_sentence(full_text: str, span: tuple) -> SentenceScore:
    sentence, start, end = span
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", sentence)
    lower = sentence.lower()
    reasons = []
    score = 0.0

    for pattern, weight, reason in _AI_PHRASES:
        if re.search(pattern, lower):
            score += weight
            reasons.append(reason)

    first_words = ' '.join(w.lower() for w in words[:2])
    first_word = words[0].lower() if words else ''
    if first_word in _TRANSITIONS or first_words in _TRANSITIONS:
        score += 0.08
        reasons.append('formal transition starter')

    word_count = len(words)
    if word_count >= 28:
        score += 0.08
        reasons.append('long polished sentence')
    if word_count >= 38:
        score += 0.06
        reasons.append('very long sentence')

    hedge_hits = sum(1 for word in words if word.lower() in _HEDGES)
    if hedge_hits >= 2:
        score += 0.08
        reasons.append('heavy hedging')

    generic_hits = sum(1 for word in words if word.lower() in _GENERIC_ACADEMIC)
    if generic_hits >= 3:
        score += 0.10
        reasons.append('generic academic vocabulary')

    unique_ratio = len({w.lower() for w in words}) / max(word_count, 1)
    if word_count >= 18 and unique_ratio < 0.62:
        score += 0.08
        reasons.append('repetitive wording')

    comma_count = sentence.count(',')
    if word_count >= 22 and comma_count >= 3:
        score += 0.07
        reasons.append('stacked clauses')

    if re.search(r'\b(?:by|through) (?:leveraging|utilizing|employing)\b', lower):
        score += 0.12
        reasons.append('process-heavy phrasing')

    if not reasons and word_count >= 20:
        score += 0.10
        reasons.append('low-confidence polished prose signal')

    score = min(score, 0.96)
    line = full_text.count('\n', 0, start) + 1
    paragraph = _paragraph_number(full_text, start)

    return SentenceScore(
        text=sentence,
        start=start,
        end=end,
        line=line,
        paragraph=paragraph,
        word_count=word_count,
        score=score,
        reasons=reasons,
    )


def _paragraph_number(text: str, start: int) -> int:
    before = text[:start].strip('\n')
    if not before:
        return 1
    return len(re.split(r'\n\s*\n', before))


def _summary(score: float, flagged_count: int, sentence_count: int) -> str:
    pct = round(score * 100)
    if pct >= 65:
        return f'High AI-language signal across {flagged_count}/{sentence_count} sentences.'
    if pct >= 40:
        return f'Moderate AI-language signal across {flagged_count}/{sentence_count} sentences.'
    if flagged_count:
        return f'Low overall signal, with {flagged_count} localized sentence(s) worth review.'
    return 'Low AI-language signal.'
