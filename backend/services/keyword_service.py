"""
TextRank keyword extraction, implemented from scratch on top of
networkx (no nltk/sumy dependency — those pull in large corpora/heavy
installs for what's a small, well-understood graph algorithm).

Classic TextRank (Mihalcea & Tarau, 2004): tokenize -> drop stopwords ->
build a co-occurrence graph over a sliding window -> PageRank -> merge
adjacent top-scoring tokens back into keyphrases.

The stopword list is a small hand-curated trilingual set (English +
Filipino + Hiligaynon) — best-effort, not a linguistically exhaustive
resource. Extend it as code-switched transcripts reveal gaps.
"""

import re

import networkx as nx

_WORD_PATTERN = re.compile(r"[a-zA-ZñÑ']+")

_STOPWORDS = {
    # English
    "a", "an", "the", "and", "or", "but", "if", "so", "of", "in", "on", "at", "to", "for",
    "with", "is", "are", "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "it", "its", "i", "you", "he", "she", "we", "they", "them", "his", "her",
    "our", "your", "their", "as", "by", "from", "not", "no", "do", "does", "did", "have",
    "has", "had", "will", "would", "can", "could", "should", "just", "okay", "ok", "yeah",
    "um", "uh", "like", "so", "then", "there", "here", "what", "who", "when", "where",
    "why", "how", "up", "down", "out", "about", "into", "very", "also", "than", "too",
    # Filipino
    "ang", "mga", "ng", "sa", "na", "si", "ay", "at", "ito", "iyon", "ko", "mo", "niya",
    "namin", "natin", "ninyo", "nila", "kami", "tayo", "kayo", "sila", "ako", "ikaw", "ka",
    "hindi", "oo", "opo", "po", "din", "rin", "lang", "naman", "kasi", "para", "pero", "o",
    "kung", "dahil", "dito", "doon", "siya", "yung", "yan", "eto", "diba", "ganun", "ba",
    # Hiligaynon / Ilonggo
    "sang", "kag", "nga", "gid", "indi", "wala", "may", "bangud", "kay", "subong", "diri",
    "dira", "didto", "kamo", "kita", "amon", "aton", "inyo", "ila", "ini", "ina", "abi",
    "bala", "man", "lang",
}

_WINDOW_SIZE = 4


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_PATTERN.findall(text)]


def build_weighted_text(segments: list[dict], teacher_weight: float = 2.0) -> str:
    """
    Concatenates segment text for extract_keywords(), repeating
    teacher-labeled segments `teacher_weight` times over so instructional
    speech dominates the co-occurrence graph instead of getting drowned out
    by side conversation of the same length — the "prioritize instructional
    speech" half of teacher voice prioritization applied to keyword
    extraction (the identification half lives in
    teacher_verification_service.py). Segments with no "is_teacher" key
    (enable_teacher_verification was off for the session) are all weighted
    equally at 1x, so this is a no-op — identical output to just joining
    every segment's text once — when the feature isn't in use.
    """
    repeat = max(1, round(teacher_weight))
    parts: list[str] = []

    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue
        parts.extend([text] * (repeat if segment.get("is_teacher") else 1))

    return " ".join(parts)


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """
    Returns up to `top_n` keywords/keyphrases ranked by TextRank score,
    in descending-score order. Empty/too-short input returns [].
    """
    tokens = _tokenize(text)
    candidate_tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    if len(set(candidate_tokens)) < 2:
        return []

    graph = nx.Graph()
    graph.add_nodes_from(candidate_tokens)

    for i, token in enumerate(candidate_tokens):
        for j in range(i + 1, min(i + _WINDOW_SIZE, len(candidate_tokens))):
            neighbor = candidate_tokens[j]
            if neighbor == token:
                continue
            if graph.has_edge(token, neighbor):
                graph[token][neighbor]["weight"] += 1
            else:
                graph.add_edge(token, neighbor, weight=1)

    try:
        scores = nx.pagerank(graph, weight="weight", max_iter=200)
    except nx.PowerIterationFailedConvergence:
        # PageRank very rarely fails to converge on a natural-text co-occurrence
        # graph, but if it does, a session must still finalize — fall back to
        # weighted degree centrality (same "central tokens" idea, no iteration).
        scores = {node: deg for node, deg in graph.degree(weight="weight")}

    ranked_words = sorted(scores, key=scores.get, reverse=True)
    top_words = set(ranked_words[: max(top_n * 2, 10)])

    return _merge_into_keyphrases(tokens, top_words, scores, top_n)


def _merge_into_keyphrases(
    tokens: list[str], top_words: set[str], scores: dict[str, float], top_n: int
) -> list[str]:
    """Merges consecutive top-ranked tokens (as they appear in the original text) into phrases."""
    phrases: list[tuple[str, float]] = []
    current_phrase: list[str] = []
    current_score = 0.0

    for token in tokens:
        if token in top_words:
            current_phrase.append(token)
            current_score += scores[token]
        else:
            if current_phrase:
                phrases.append((" ".join(current_phrase), current_score))
                current_phrase, current_score = [], 0.0

    if current_phrase:
        phrases.append((" ".join(current_phrase), current_score))

    seen: set[str] = set()
    deduped: list[tuple[str, float]] = []
    for phrase, score in phrases:
        if phrase not in seen:
            seen.add(phrase)
            deduped.append((phrase, score))

    deduped.sort(key=lambda item: item[1], reverse=True)
    return [phrase for phrase, _ in deduped[:top_n]]
