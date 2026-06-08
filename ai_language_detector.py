"""
ai_language_detector.py
=======================
Local, transparent AI-language detector for academic prose.

This is not an authorship oracle. It estimates AI-like language by combining
multiple visible signals:
  - formulaic phrasing
  - predictability / low information density
  - burstiness and rhythm uniformity
  - semantic redundancy
  - low specificity
  - style contrast against the document baseline

The output is designed for review: percentage, locations, and reasons.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Dict, List, Tuple


_AI_PHRASES = [
    (r'\bit is important to note\b', 0.30, 'formulaic qualifier'),
    (r'\bit is worth noting\b', 0.28, 'formulaic qualifier'),
    (r'\bplays? a (?:crucial|critical|vital|significant) role\b', 0.26, 'stock academic phrasing'),
    (r'\b(?:crucial|critical|vital|essential) (?:role|aspect|component)\b', 0.18, 'generic emphasis'),
    (r'\b(?:comprehensive|robust|holistic|multifaceted|nuanced) (?:approach|understanding|analysis|framework)\b', 0.24, 'generic academic phrasing'),
    (r'\bnot only\b.+\bbut also\b', 0.22, 'balanced template structure'),
    (r'\bthis (?:highlights|underscores|emphasizes) the (?:importance|need|significance)\b', 0.22, 'formulaic conclusion'),
    (r'\bin (?:today\'s|the) (?:rapidly evolving|modern|contemporary) (?:world|landscape|era|context)\b', 0.30, 'stock opener'),
    (r'\bdelves? into\b', 0.20, 'AI-styled verb'),
    (r'\btapestry\b|\bseamless(?:ly)?\b|\bleverage(?:s|d)?\b|\butili[sz](?:e|es|ed|ing)\b', 0.18, 'AI-styled vocabulary'),
]

_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'if', 'while', 'of', 'in', 'on',
    'for', 'to', 'from', 'with', 'without', 'by', 'as', 'at', 'is', 'are',
    'was', 'were', 'be', 'been', 'being', 'this', 'that', 'these', 'those',
    'it', 'its', 'their', 'there', 'which', 'who', 'whom', 'what', 'when',
    'where', 'why', 'how', 'can', 'could', 'may', 'might', 'will', 'would',
    'should', 'also', 'not', 'no', 'such', 'than', 'then', 'into', 'through',
}

_COMMON_WORDS = _STOPWORDS | {
    'important', 'significant', 'various', 'different', 'multiple', 'overall',
    'effective', 'complex', 'approach', 'framework', 'context', 'process',
    'development', 'analysis', 'result', 'results', 'study', 'research',
    'method', 'methods', 'data', 'information', 'system', 'systems',
    'provide', 'provides', 'show', 'shows', 'suggest', 'suggests',
}

_GENERIC_ACADEMIC = {
    'important', 'significant', 'effective', 'various', 'multiple',
    'complex', 'dynamic', 'critical', 'essential', 'comprehensive',
    'robust', 'innovative', 'context', 'framework', 'approach',
    'implications', 'insights', 'outcomes', 'landscape', 'understanding',
}

_HEDGES = {
    'may', 'might', 'could', 'can', 'often', 'generally', 'typically',
    'arguably', 'potentially', 'suggests', 'indicates', 'appears',
}

_TRANSITIONS = {
    'additionally', 'furthermore', 'moreover', 'therefore', 'thus',
    'consequently', 'however', 'nevertheless', 'overall',
}

_SPECIFIC_MARKERS = re.compile(
    r'\b(?:\d+(?:\.\d+)?%?|\[[0-9, -]+\]|\([A-Z][A-Za-z-]+,\s*(?:19|20)\d{2}[a-z]?\)|'
    r'(?:19|20)\d{2}|p\s*[<=>]\s*0\.\d+|doi:|https?://)\b',
    re.I,
)


@dataclass
class SentenceFeatures:
    text: str
    start: int
    end: int
    line: int
    paragraph: int
    words: List[str]
    content_words: List[str]
    phrase_score: float = 0.0
    predictability: float = 0.0
    rhythm_uniformity: float = 0.0
    redundancy: float = 0.0
    low_specificity: float = 0.0
    style_contrast: float = 0.0
    genericity: float = 0.0
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.words)

    @property
    def percent(self) -> int:
        return round(max(0.0, min(1.0, self.score)) * 100)

    @property
    def tier(self) -> str:
        if self.score >= 0.72:
            return 'high'
        if self.score >= 0.48:
            return 'medium'
        return 'low'


def detect_ai_language(text: str) -> Dict:
    clean_text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    paragraph_spans = _split_paragraphs(clean_text)
    sentence_spans = _split_sentences(clean_text)

    features = [_initial_features(clean_text, span, paragraph_spans) for span in sentence_spans]
    features = [f for f in features if f.word_count >= 5]

    total_words = sum(f.word_count for f in features)
    if not features or total_words < 20:
        return {
            'overall_percent': 0,
            'total_words': total_words,
            'ai_like_words': 0,
            'sentence_count': len(features),
            'flagged_count': 0,
            'signals': {},
            'paragraphs': [],
            'locations': [],
            'summary': 'Not enough text to analyse.',
            'confidence_note': 'Provide at least 20 words for a useful estimate.',
        }

    _apply_document_signals(features)
    _apply_redundancy(features)
    _finalize_scores(features)

    paragraph_reports = _paragraph_reports(features)
    signal_summary = _signal_summary(features)
    weighted_score = sum(f.score * f.word_count for f in features) / total_words
    flagged = [f for f in features if f.score >= 0.48]
    ai_like_words = round(sum(f.score * f.word_count for f in features))

    locations = [
        {
            'sentence_index': i + 1,
            'line': f.line,
            'paragraph': f.paragraph,
            'start': f.start,
            'end': f.end,
            'word_count': f.word_count,
            'percent': f.percent,
            'tier': f.tier,
            'text': f.text,
            'reasons': f.reasons[:6],
            'evidence': {
                'predictability': round(f.predictability * 100),
                'rhythm_uniformity': round(f.rhythm_uniformity * 100),
                'redundancy': round(f.redundancy * 100),
                'low_specificity': round(f.low_specificity * 100),
                'style_contrast': round(f.style_contrast * 100),
            },
        }
        for i, f in enumerate(features)
        if f.score >= 0.34
    ]
    locations.sort(key=lambda item: item['percent'], reverse=True)

    return {
        'overall_percent': round(weighted_score * 100),
        'total_words': total_words,
        'ai_like_words': ai_like_words,
        'sentence_count': len(features),
        'flagged_count': len(flagged),
        'signals': signal_summary,
        'paragraphs': paragraph_reports,
        'locations': locations[:100],
        'summary': _summary(weighted_score, len(flagged), len(features)),
        'confidence_note': (
            'This is an evidence-based writing-pattern estimate, not proof of authorship. '
            'Use flagged locations for human review.'
        ),
    }


def _split_paragraphs(text: str) -> List[Tuple[int, int, str]]:
    spans = []
    pos = 0
    for match in re.finditer(r'(?:^|\n\s*\n)(.*?)(?=\n\s*\n|$)', text, re.S):
        raw = match.group(1)
        if not raw.strip():
            continue
        start = match.start(1)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw) - len(raw.rstrip())
        spans.append((start + leading, match.end(1) - trailing, raw.strip()))
        pos = match.end()
    if not spans and text.strip():
        leading = len(text) - len(text.lstrip())
        trailing = len(text) - len(text.rstrip())
        spans.append((leading, len(text) - trailing, text.strip()))
    return spans


def _split_sentences(text: str) -> List[Tuple[str, int, int]]:
    abbreviations = re.compile(
        r'\b(?:et al|e\.g|i\.e|fig|eq|dr|mr|ms|mrs|prof|vs|no|vol|pp)\.$',
        re.I,
    )
    spans = []
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in '.!?':
            i += 1
            continue

        before = text[max(start, i - 24):i + 1]
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


def _initial_features(text: str, span: Tuple[str, int, int], paragraphs: List[Tuple[int, int, str]]) -> SentenceFeatures:
    sentence, start, end = span
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]*", sentence)]
    content = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    line = text.count('\n', 0, start) + 1
    paragraph = _paragraph_index(start, paragraphs)
    f = SentenceFeatures(
        text=sentence,
        start=start,
        end=end,
        line=line,
        paragraph=paragraph,
        words=words,
        content_words=content,
    )
    _apply_sentence_signals(f)
    return f


def _paragraph_index(start: int, paragraphs: List[Tuple[int, int, str]]) -> int:
    for i, (p_start, p_end, _) in enumerate(paragraphs, start=1):
        if p_start <= start <= p_end:
            return i
    return max(1, len([p for p in paragraphs if p[0] <= start]))


def _apply_sentence_signals(f: SentenceFeatures) -> None:
    lower = f.text.lower()
    for pattern, weight, reason in _AI_PHRASES:
        if re.search(pattern, lower):
            f.phrase_score += weight
            f.reasons.append(reason)

    if f.words:
        first = f.words[0]
        first_two = ' '.join(f.words[:2])
        if first in _TRANSITIONS or first_two in {'in addition', 'as a'}:
            f.phrase_score += 0.08
            f.reasons.append('formal transition starter')

    common_ratio = sum(1 for w in f.words if w in _COMMON_WORDS) / max(1, f.word_count)
    lexical_diversity = len(set(f.words)) / max(1, f.word_count)
    avg_word_len = mean([len(w) for w in f.words]) if f.words else 0
    f.predictability = _clamp((common_ratio * 0.65) + ((1 - lexical_diversity) * 0.25) + (0.10 if avg_word_len < 5.2 else 0))

    generic_hits = sum(1 for w in f.words if w in _GENERIC_ACADEMIC)
    hedge_hits = sum(1 for w in f.words if w in _HEDGES)
    f.genericity = _clamp((generic_hits / max(1, f.word_count)) * 3.4 + (0.12 if hedge_hits >= 2 else 0))
    if generic_hits >= 3:
        f.reasons.append('generic academic vocabulary')
    if hedge_hits >= 2:
        f.reasons.append('heavy hedging')

    specific_hits = len(_SPECIFIC_MARKERS.findall(f.text))
    capitalized_terms = len(re.findall(r'\b[A-Z][a-z]{3,}\b', f.text))
    content_ratio = len(f.content_words) / max(1, f.word_count)
    specificity = min(1.0, specific_hits * 0.35 + capitalized_terms * 0.08 + content_ratio * 0.65)
    f.low_specificity = _clamp(1 - specificity)
    if f.word_count >= 14 and f.low_specificity > 0.62:
        f.reasons.append('low specificity for sentence length')


def _apply_document_signals(features: List[SentenceFeatures]) -> None:
    lengths = [f.word_count for f in features]
    diversities = [len(set(f.words)) / max(1, f.word_count) for f in features]
    mean_len = mean(lengths)
    len_sd = pstdev(lengths) or 1.0
    doc_cv = len_sd / max(1.0, mean_len)
    global_uniformity = _clamp(1 - (doc_cv / 0.85))

    by_para: Dict[int, List[SentenceFeatures]] = {}
    for f in features:
        by_para.setdefault(f.paragraph, []).append(f)

    for group in by_para.values():
        group_lengths = [f.word_count for f in group]
        group_sd = pstdev(group_lengths) if len(group_lengths) > 1 else 0
        group_cv = group_sd / max(1.0, mean(group_lengths))
        para_uniformity = _clamp(1 - (group_cv / 0.75))
        for f in group:
            near_mean = 1 - min(abs(f.word_count - mean_len) / max(1.0, len_sd * 2.5), 1)
            f.rhythm_uniformity = _clamp((global_uniformity * 0.45) + (para_uniformity * 0.35) + (near_mean * 0.20))
            if f.rhythm_uniformity > 0.72 and f.word_count >= 12:
                f.reasons.append('uniform sentence rhythm')

    doc_div_mean = mean(diversities)
    doc_div_sd = pstdev(diversities) or 0.01
    for f, div in zip(features, diversities):
        z = abs(div - doc_div_mean) / doc_div_sd
        if z > 1.8:
            f.style_contrast = _clamp((z - 1.2) / 2.8)
            f.reasons.append('style differs from document baseline')
        elif f.predictability > 0.55 and f.rhythm_uniformity > 0.65:
            f.style_contrast = 0.20


def _apply_redundancy(features: List[SentenceFeatures]) -> None:
    phrase_counter = Counter()
    sentence_sets = []
    for f in features:
        phrases = set(_ngrams(f.content_words, 2)) | set(_ngrams(f.content_words, 3))
        sentence_sets.append(phrases)
        phrase_counter.update(phrases)

    for idx, f in enumerate(features):
        repeated = [p for p in sentence_sets[idx] if phrase_counter[p] > 1]
        repeated_ratio = len(repeated) / max(1, len(sentence_sets[idx]))
        max_jaccard = 0.0
        current = set(f.content_words)
        for j, other in enumerate(features):
            if idx == j:
                continue
            other_set = set(other.content_words)
            if not current or not other_set:
                continue
            sim = len(current & other_set) / len(current | other_set)
            max_jaccard = max(max_jaccard, sim)
        f.redundancy = _clamp(repeated_ratio * 0.65 + max_jaccard * 0.55)
        if f.redundancy > 0.40:
            f.reasons.append('repeated concepts or phrasing')


def _finalize_scores(features: List[SentenceFeatures]) -> None:
    for f in features:
        length_factor = 1.0
        if f.word_count < 10:
            length_factor = 0.72
        elif f.word_count >= 32:
            length_factor = 1.08
            f.reasons.append('long polished sentence')

        f.score = _clamp((
            f.phrase_score * 0.23
            + f.predictability * 0.20
            + f.rhythm_uniformity * 0.15
            + f.redundancy * 0.18
            + f.low_specificity * 0.14
            + f.style_contrast * 0.06
            + f.genericity * 0.14
        ) * length_factor)

        if f.predictability > 0.58:
            f.reasons.append('highly predictable wording')
        if f.score < 0.34:
            f.reasons = f.reasons[:2]


def _paragraph_reports(features: List[SentenceFeatures]) -> List[Dict]:
    by_para: Dict[int, List[SentenceFeatures]] = {}
    for f in features:
        by_para.setdefault(f.paragraph, []).append(f)
    reports = []
    for para, group in sorted(by_para.items()):
        words = sum(f.word_count for f in group)
        if words < 15:
            continue
        score = sum(f.score * f.word_count for f in group) / words
        reports.append({
            'paragraph': para,
            'percent': round(score * 100),
            'word_count': words,
            'flagged_sentences': sum(1 for f in group if f.score >= 0.48),
            'tier': 'high' if score >= 0.65 else ('medium' if score >= 0.40 else 'low'),
        })
    reports.sort(key=lambda r: r['percent'], reverse=True)
    return reports[:30]


def _signal_summary(features: List[SentenceFeatures]) -> Dict[str, int]:
    total_words = sum(f.word_count for f in features) or 1

    def weighted(attr: str) -> int:
        return round(sum(getattr(f, attr) * f.word_count for f in features) / total_words * 100)

    return {
        'predictability': weighted('predictability'),
        'rhythm_uniformity': weighted('rhythm_uniformity'),
        'redundancy': weighted('redundancy'),
        'low_specificity': weighted('low_specificity'),
        'style_contrast': weighted('style_contrast'),
        'genericity': weighted('genericity'),
    }


def _ngrams(words: List[str], n: int) -> List[str]:
    return [' '.join(words[i:i + n]) for i in range(0, max(0, len(words) - n + 1))]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _summary(score: float, flagged_count: int, sentence_count: int) -> str:
    pct = round(score * 100)
    if pct >= 65:
        return f'High AI-language signal across {flagged_count}/{sentence_count} sentences.'
    if pct >= 40:
        return f'Moderate AI-language signal across {flagged_count}/{sentence_count} sentences.'
    if flagged_count:
        return f'Low overall signal, with {flagged_count} localized sentence(s) worth review.'
    return 'Low AI-language signal.'
