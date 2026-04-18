"""Accuracy scoring for LLM responses against ground-truth prompts."""

from __future__ import annotations


def score_response(response_text: str, prompt_spec: dict) -> tuple[str, float]:
    """
    Returns (label, score_0_to_1).

    Scoring tiers:
      - exact_answer match  → "Excellent" / 1.0
      - all keywords found  → "Good"      / 0.75
      - some keywords found → "Partial"   / 0.40
      - no keywords found   → "Poor"      / 0.10
    """
    text = response_text.lower().strip()
    exact = prompt_spec.get("exact_answer")
    keywords: list[str] = [k.lower() for k in prompt_spec.get("expected_keywords", [])]

    if exact and exact.lower() in text:
        return "Excellent", 1.0

    if not keywords:
        return "Unknown", 0.5

    matched = sum(1 for kw in keywords if kw in text)
    ratio = matched / len(keywords)

    if ratio == 1.0:
        return "Good", 0.75
    elif ratio >= 0.5:
        return "Partial", 0.40
    else:
        return "Poor", 0.10
