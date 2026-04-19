"""
Accuracy scoring — delegates to each prompt's own validator function.
Returns (label, score, detail) so the report can show why a score was given.
"""

from __future__ import annotations


def score_response(
    response_text: str,
    prompt_spec: dict,
) -> tuple[str, float, str]:
    """
    Call the prompt's validator and return (label, score, detail).
    Falls back gracefully if no validator is defined.
    """
    validator = prompt_spec.get("validator")
    if callable(validator):
        try:
            result = validator(response_text)
            # Support both 2-tuple (label, score) and 3-tuple (label, score, detail)
            if len(result) == 3:
                return result
            label, score = result
            return label, score, ""
        except Exception as exc:
            return "Error", 0.0, f"Validator raised: {exc}"

    return "Unknown", 0.5, "No validator defined"
