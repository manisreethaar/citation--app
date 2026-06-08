"""
diff_engine.py  –  Generate a visual diff between original and cited body text.

Returns a list of chunks:
  { 'type': 'norm' | 'inserted' | 'context', 'text': str }
"""

import re
from typing import List, Dict


def build_diff_chunks(original: str, cited: str,
                      context_words: int = 8) -> List[Dict]:
    """
    Compare original and cited body text word-by-word and return
    a list of diff chunks suitable for rendering in HTML.
    """
    orig_words  = _tokenize(original)
    cited_words = _tokenize(cited)

    # Simple LCS-based diff
    chunks = []
    orig_idx = cited_idx = 0
    n_orig  = len(orig_words)
    n_cited = len(cited_words)

    while orig_idx < n_orig or cited_idx < n_cited:
        # Fast-forward matching words
        match_start_orig  = orig_idx
        match_start_cited = cited_idx
        while (orig_idx < n_orig and cited_idx < n_cited
               and orig_words[orig_idx] == cited_words[cited_idx]):
            orig_idx  += 1
            cited_idx += 1

        if orig_idx > match_start_orig:
            text = ' '.join(orig_words[match_start_orig:orig_idx])
            chunks.append({'type': 'norm', 'text': text + ' '})

        if orig_idx >= n_orig and cited_idx >= n_cited:
            break

        # Find next alignment point
        inserted = []
        while cited_idx < n_cited:
            tok = cited_words[cited_idx]
            # Look ahead: is this token present in the near future of original?
            lookahead_range = orig_words[orig_idx:orig_idx + 12]
            if tok in lookahead_range and not _is_citation_token(tok):
                break
            inserted.append(tok)
            cited_idx += 1

        if inserted:
            chunks.append({'type': 'inserted', 'text': ' '.join(inserted) + ' '})
        elif orig_idx < n_orig:
            # Original has token not in cited (shouldn't happen if only insertions)
            chunks.append({'type': 'norm', 'text': orig_words[orig_idx] + ' '})
            orig_idx += 1

    return _merge_chunks(chunks)


def _tokenize(text: str) -> List[str]:
    """Split text into tokens, preserving punctuation."""
    return re.findall(r'\S+', text)


def _is_citation_token(tok: str) -> bool:
    """True if token looks like a citation marker: (Smith, (Smith, [1] etc."""
    return bool(re.match(r'^[\(\[\{]', tok) or re.match(r'[\)\]\}]$', tok))


def _merge_chunks(chunks: List[Dict]) -> List[Dict]:
    """Merge consecutive chunks of the same type."""
    if not chunks:
        return chunks
    merged = [chunks[0].copy()]
    for chunk in chunks[1:]:
        if chunk['type'] == merged[-1]['type']:
            merged[-1]['text'] += chunk['text']
        else:
            merged.append(chunk.copy())
    return merged


def extract_context_snippets(original: str, cited: str, max_snippets: int = 30) -> List[Dict]:
    """
    A lighter-weight approach: only return snippets around insertion points.
    Useful for long documents.
    """
    # Find spans that differ
    orig_lines  = original.split('\n')
    cited_lines = cited.split('\n')

    results = []
    for i, (ol, cl) in enumerate(zip(orig_lines, cited_lines)):
        if ol != cl:
            results.append({
                'line': i + 1,
                'original': ol,
                'cited': cl,
                'type': 'changed'
            })
        if len(results) >= max_snippets:
            break

    return results
