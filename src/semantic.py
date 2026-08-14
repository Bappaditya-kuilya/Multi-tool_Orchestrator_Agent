from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


SYNONYM_MAP: dict[str, set[str]] = {
    "temperature": {"weather", "climate", "forecast", "temp"},
    "weather": {"temperature", "climate", "forecast", "temp"},
    "temp": {"temperature", "weather", "climate", "forecast"},
    "calculate": {"calculator", "math", "compute"},
    "calculator": {"calculate", "math", "compute"},
    "search": {"github", "find", "query"},
    "github": {"search", "find", "code"},
    "article": {"wikipedia", "encyclopedia", "read"},
    "wikipedia": {"article", "encyclopedia", "read"},
}


def _expand_synonyms(words: set[str]) -> set[str]:
    expanded = set(words)
    for word in words:
        if word in SYNONYM_MAP:
            expanded |= SYNONYM_MAP[word]
    return expanded


class SemanticMatcher:
    """Zero-dependency TF-IDF + substring + synonym matcher for capability routing."""

    def __init__(self, documents: list[str] | None = None) -> None:
        self.documents: list[str] = documents or []
        self._idf: dict[str, float] = {}
        self._fit()

    def _fit(self) -> None:
        if not self.documents:
            return

        doc_count = len(self.documents)
        word_doc_freq: Counter[str] = Counter()

        for doc in self.documents:
            words = set(self._tokenize(doc))
            for word in words:
                word_doc_freq[word] += 1

        self._idf = {
            word: math.log(doc_count / freq)
            for word, freq in word_doc_freq.items()
        }

    def add_document(self, doc: str) -> None:
        """Append a document and rebuild the IDF index."""
        self.documents.append(doc)
        self._fit()

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r'[a-z0-9]+', text.lower())

    def _tfidf(self, text: str) -> dict[str, float]:
        words = self._tokenize(text)
        tf = Counter(words)
        total = len(words) if words else 1
        return {
            word: (count / total) * self._idf.get(word, 1.0)
            for word, count in tf.items()
        }

    def _cosine(self, vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
        common = set(vec_a.keys()) & set(vec_b.keys())
        if not common:
            return 0.0

        dot = sum(vec_a[k] * vec_b[k] for k in common)
        mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
        mag_b = math.sqrt(sum(v * v for v in vec_b.values()))

        if mag_a == 0 or mag_b == 0:
            return 0.0

        return dot / (mag_a * mag_b)

    def _prefix_match(self, a: set[str], b: set[str]) -> bool:
        # ponytail: bucket by prefix, real trie if docs grow
        small, large = (a, b) if len(a) <= len(b) else (b, a)
        short: list[str] = []
        buckets: dict[str, list[str]] = {}
        for word in large:
            if len(word) < 3:
                short.append(word)
            else:
                buckets.setdefault(word[:3], []).append(word)
        for word in small:
            if len(word) < 3:
                for cand in large:
                    if word.startswith(cand) or cand.startswith(word):
                        return True
                continue
            for cand in buckets.get(word[:3], ()):
                if word.startswith(cand) or cand.startswith(word):
                    return True
            for cand in short:
                if word.startswith(cand):
                    return True
        return False

    def _substring_score(self, query: str, document: str) -> float:
        q = query.lower()
        d = document.lower()
        if q in d or d in q:
            return 0.5
        q_words = set(self._tokenize(query))
        d_words = set(self._tokenize(document))
        if not q_words or not d_words:
            return 0.0
        # ponytail: early exit - check intersection first (O(min(n,m))) before prefix match
        if q_words & d_words:
            return 0.3
        if self._prefix_match(q_words, d_words):
            return 0.3
        return 0.0

    def _synonym_score(self, query: str, document: str) -> float:
        q_words = set(self._tokenize(query))
        d_words = set(self._tokenize(document))
        q_expanded = _expand_synonyms(q_words)
        d_expanded = _expand_synonyms(d_words)
        overlap = q_expanded & d_expanded
        if overlap:
            return 0.4
        return 0.0

    def similarity(self, query: str, document: str) -> float:
        """Best of cosine, substring, and synonym similarity, in [0, 1]."""
        if not query.strip():
            return 0.0
        vec_q = self._tfidf(query)
        vec_d = self._tfidf(document)
        cosine = self._cosine(vec_q, vec_d)
        substring = self._substring_score(query, document)
        synonym = self._synonym_score(query, document)
        return max(cosine, substring, synonym)

    def rank(self, query: str, candidates: list[str]) -> list[tuple[str, float]]:
        scored = [(doc, self.similarity(query, doc)) for doc in candidates]
        return sorted(scored, key=lambda x: x[1], reverse=True)
