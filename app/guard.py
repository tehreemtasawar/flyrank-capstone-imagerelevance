"""
The mismatch guard.

This is the production-critical piece the brief centers on. It takes a
candidate image for a post and decides: is this actually good enough to
suggest, or should we refuse?

Four checks, any one of which can trigger a REJECT:
  1. Confidence check — the vision model wasn't sure what's in the image.
  2. Similarity check — the image and post aren't semantically close enough.
  3. Category check — a lightweight keyword overlap between the post text
     and the image's subject/category, to catch cases like "fox post,
     wolf image" where the embeddings might still be fairly close
     (foxes and wolves are semantically similar animals) but the
     specific subject is wrong.

Kept as a standalone module with no DB/FastAPI imports so it's easy to
unit test in isolation (see tests/test_guard.py).
"""

import re
from dataclasses import dataclass
from typing import List, Optional


_IRREGULAR_PLURALS = {"wolves": "wolf", "leaves": "leaf"}

# Connector words that can appear inside a subject label (e.g. a vision
# model returning "polar bear and cub" instead of just "polar bear") but
# carry no identifying meaning. Without filtering these out, a subject
# word like "and" matches almost ANY post text, silently satisfying the
# "subject is referenced in the post" check and disabling the guard.
_STOPWORDS = {"and", "the", "with", "a", "an", "of", "for", "in", "on", "at", "to", "its", "or"}


def _normalize_word(word: str) -> str:
    """Crude singularization so "dog" (a subject word) matches "dogs"
    (how the post actually phrases it). Exact-word matching without this
    silently fails on any plural — "dog" != "dogs" as strings — which lets
    a wrong-category image slip past the guard whenever the post uses the
    plural form (almost always, for a post ABOUT a species)."""
    if word in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[word]
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _words(text: str) -> set:
    """Whole-word tokenization, lowercased and singularized. Using plain
    substring checks (e.g. "red" in post_text) is a trap: "red" matches
    inside "bred", "cat" matches inside "category", etc. \\b word-boundary
    regex avoids that; normalization handles the singular/plural mismatch."""
    return {_normalize_word(w) for w in re.findall(r"\b[a-z]+\b", text.lower())}


@dataclass
class GuardResult:
    decision: str  # "ACCEPT" | "REJECT"
    reason: str
    code: str = "OK"  # OK | NO_METADATA | LOW_CONFIDENCE | SUBJECT_MISMATCH | LOW_SIMILARITY


def _subject_words(subject: str) -> set:
    return {
        _normalize_word(w) for w in re.findall(r"[a-z]+", subject.lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def _category_conflict(
    post_text: str,
    image_subject: str,
    image_category: str,
    other_known_subjects: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Corpus-driven subject check (no hardcoded species list).

    For the candidate's subject and for every OTHER subject known to exist in
    the corpus, count how many of the subject's words appear in the post. If
    some other subject is referenced MORE strongly than the candidate's own,
    the pairing is wrong ("fox post, wolf image").

    Comparing strength (rather than "does ANY word match") matters: "red fox"
    shares the generic word "red" with a post about "red deer", but "red deer
    stag" matches two words there vs one, so the fox image is still rejected.
    """
    post_words = _words(post_text)
    own_words = _subject_words(image_subject)
    own_hits = len(own_words & post_words)

    best_other, best_hits = None, 0
    for other in other_known_subjects or []:
        if other.lower() == image_subject.lower():
            continue
        hits = len(_subject_words(other) & post_words)
        if hits > best_hits:
            best_other, best_hits = other, hits

    if best_other is not None and best_hits > own_hits:
        return (
            f"{image_category.capitalize()} category mismatch: "
            f"expected {best_other}, detected {image_subject}"
        )
    return None


def evaluate(
    post_text: str,
    image_subject: Optional[str],
    image_category: Optional[str],
    image_confidence: Optional[float],
    similarity_score: float,
    similarity_threshold: float,
    confidence_threshold: float,
    other_known_subjects: Optional[List[str]] = None,
) -> GuardResult:
    if image_subject is None or image_category is None:
        return GuardResult("REJECT", "No processed image metadata available", "NO_METADATA")

    if image_confidence is not None and image_confidence < confidence_threshold:
        return GuardResult(
            "REJECT",
            f"Low classifier confidence ({image_confidence:.2f} < {confidence_threshold:.2f})",
            "LOW_CONFIDENCE",
        )

    conflict = _category_conflict(post_text, image_subject, image_category, other_known_subjects)
    if conflict:
        return GuardResult("REJECT", conflict, "SUBJECT_MISMATCH")

    if similarity_score < similarity_threshold:
        return GuardResult(
            "REJECT",
            f"Similarity below threshold ({similarity_score:.2f} < {similarity_threshold:.2f}); "
            f"subject '{image_subject}' does not clearly match the post",
            "LOW_SIMILARITY",
        )

    return GuardResult(
        "ACCEPT",
        f"Subject '{image_subject}' matches with similarity {similarity_score:.2f} "
        f"and confidence {image_confidence:.2f}"
    )


def evaluate_candidates(
    post_text: str,
    candidates: List[dict],
    similarity_threshold: float,
    confidence_threshold: float,
):
    """
    candidates: dicts with image_id, subject, category, confidence, similarity_score,
    already sorted by similarity_score desc.

    Returns [(candidate, GuardResult), ...] in the same order — every candidate
    gets a verdict and a human-readable reason (used for the "why was this
    image selected or refused" inspection in the API).
    """
    known_subjects = sorted({c.get("subject") for c in candidates if c.get("subject")})
    return [
        (
            c,
            evaluate(
                post_text=post_text,
                image_subject=c.get("subject"),
                image_category=c.get("category"),
                image_confidence=c.get("confidence"),
                similarity_score=c.get("similarity_score", 0.0),
                similarity_threshold=similarity_threshold,
                confidence_threshold=confidence_threshold,
                other_known_subjects=known_subjects,
            ),
        )
        for c in candidates
    ]


def best_candidate_or_none(
    post_text: str,
    candidates: List[dict],
    similarity_threshold: float,
    confidence_threshold: float,
):
    """
    Walks the ranked list and returns (image_id, GuardResult) for the first
    candidate the guard accepts. If none pass, returns (None, GuardResult)
    explaining why the TOP-ranked candidate was refused.
    """
    if not candidates:
        return None, GuardResult("REJECT", "No candidate images available", "NO_METADATA")

    verdicts = evaluate_candidates(post_text, candidates, similarity_threshold, confidence_threshold)
    for c, result in verdicts:
        if result.decision == "ACCEPT":
            return c["image_id"], result
    return None, verdicts[0][1]
