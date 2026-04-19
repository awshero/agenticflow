"""
Auto-validators for LLM benchmark responses.

Each validator receives the raw response text and returns (label, score, detail).
  label  : "Excellent" | "Good" | "Partial" | "Poor" | "Error"
  score  : 0.0 – 1.0
  detail : human-readable explanation of what passed / failed
"""

from __future__ import annotations

import ast
import io
import json
import math
import re
import contextlib
from typing import Any, Callable


# ── Type alias ────────────────────────────────────────────────────────────────
ValidatorFn = Callable[[str], tuple[str, float, str]]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tier(score: float) -> str:
    if score >= 1.0:   return "Excellent"
    if score >= 0.75:  return "Good"
    if score >= 0.40:  return "Partial"
    return "Poor"


def _extract_code_block(text: str) -> str:
    """Pull code out of markdown fences if present."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _extract_json(text: str) -> Any:
    """Find the first JSON object or array in a response."""
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return json.loads(text.strip())


# ── 1 · Numeric validator ─────────────────────────────────────────────────────

def numeric_validator(expected: float, tolerance: float = 0.01) -> ValidatorFn:
    """
    Extract the first number from the response and compare to expected.
    tolerance is an absolute margin (default 0.01).
    """
    def validate(response: str) -> tuple[str, float, str]:
        numbers = re.findall(r"-?\d+(?:\.\d+)?", response.replace(",", ""))
        if not numbers:
            return "Poor", 0.0, "No number found in response"
        got = float(numbers[0])
        diff = abs(got - expected)
        if diff <= tolerance:
            return "Excellent", 1.0, f"Correct: {got} (expected {expected})"
        if diff <= tolerance * 10:
            return "Partial", 0.40, f"Close but off: got {got}, expected {expected}"
        return "Poor", 0.0, f"Wrong: got {got}, expected {expected}"
    return validate


# ── 2 · Code execution validator ─────────────────────────────────────────────

def code_exec_validator(test_cases: list[dict]) -> ValidatorFn:
    """
    Extract Python code from response, execute it, run test cases.

    Each test_case: {"call": "fn(args)", "expected": value}
    Score = fraction of test cases that pass.
    """
    def validate(response: str) -> tuple[str, float, str]:
        code = _extract_code_block(response)
        namespace: dict = {}

        try:
            exec(compile(ast.parse(code), "<llm>", "exec"), namespace)  # noqa: S102
        except Exception as exc:
            return "Poor", 0.0, f"Code failed to compile/run: {exc}"

        passed, failed_details = 0, []
        for tc in test_cases:
            try:
                result = eval(tc["call"], namespace)  # noqa: S307
                if result == tc["expected"]:
                    passed += 1
                else:
                    failed_details.append(
                        f"{tc['call']} → {result!r} (expected {tc['expected']!r})"
                    )
            except Exception as exc:
                failed_details.append(f"{tc['call']} → ERROR: {exc}")

        score = passed / len(test_cases)
        detail = (
            f"{passed}/{len(test_cases)} test cases passed"
            + (f". Failures: {'; '.join(failed_details)}" if failed_details else "")
        )
        return _tier(score), round(score, 2), detail
    return validate


# ── 3 · JSON schema validator ─────────────────────────────────────────────────

def json_schema_validator(required_keys: list[str], value_checks: dict | None = None) -> ValidatorFn:
    """
    Parse JSON from response and verify required keys are present.
    Optionally check specific key values: {"key": expected_value | callable}.
    """
    def validate(response: str) -> tuple[str, float, str]:
        try:
            data = _extract_json(response)
        except Exception as exc:
            return "Poor", 0.0, f"Invalid JSON: {exc}"

        if isinstance(data, list):
            data = data[0] if data else {}

        missing = [k for k in required_keys if k not in data]
        if missing:
            score = 1 - len(missing) / len(required_keys)
            return _tier(score), round(score, 2), f"Missing keys: {missing}"

        failures = []
        if value_checks:
            for key, check in value_checks.items():
                val = data.get(key)
                ok = check(val) if callable(check) else val == check
                if not ok:
                    failures.append(f"{key}={val!r} failed check")

        if failures:
            score = 1 - len(failures) / (len(value_checks or {}))
            return _tier(score), round(score, 2), f"Value failures: {failures}"

        return "Excellent", 1.0, f"All {len(required_keys)} keys present and valid"
    return validate


# ── 4 · Regex extraction validator ───────────────────────────────────────────

def regex_extraction_validator(
    items_to_find: list[str],
    item_pattern: str,
    label_name: str = "item",
) -> ValidatorFn:
    """
    Verify the response contains all expected items AND that every extracted
    item matches item_pattern (e.g. email format, phone format).

    items_to_find : ground-truth list that must appear in the response
    item_pattern  : regex each extracted match must satisfy
    """
    def validate(response: str) -> tuple[str, float, str]:
        found = re.findall(item_pattern, response)
        invalid = [f for f in found if not re.fullmatch(item_pattern, f)]
        missing = [i for i in items_to_find if i.lower() not in response.lower()]

        if invalid:
            return "Partial", 0.40, f"Malformed {label_name}s: {invalid}"

        if missing:
            score = 1 - len(missing) / len(items_to_find)
            return _tier(score), round(score, 2), f"Missing {label_name}s: {missing}"

        return "Excellent", 1.0, (
            f"All {len(items_to_find)} {label_name}s found and valid"
        )
    return validate


# ── 5 · Multi-label classification validator ──────────────────────────────────

def classification_validator(
    items: list[str],
    valid_labels: list[str],
    expected_mapping: dict[str, str] | None = None,
) -> ValidatorFn:
    """
    Given a list of items that must each be assigned one of valid_labels,
    check that:
      1. Every item appears in the response.
      2. Each item is paired with a valid label.
      3. (Optionally) matches expected_mapping exactly.
    """
    def validate(response: str) -> tuple[str, float, str]:
        text = response.lower()
        missing_items = [i for i in items if i.lower() not in text]
        invalid_labels = [
            word for word in re.findall(r"\b\w+\b", text)
            if word in [v.lower() for v in valid_labels]
        ]

        if missing_items:
            score = 1 - len(missing_items) / len(items)
            return _tier(score), round(score, 2), f"Items not classified: {missing_items}"

        if expected_mapping:
            wrong = []
            for item, expected_label in expected_mapping.items():
                pattern = rf"{re.escape(item.lower())}.*?{re.escape(expected_label.lower())}"
                if not re.search(pattern, text, re.DOTALL):
                    wrong.append(f"{item} should be {expected_label}")
            if wrong:
                score = 1 - len(wrong) / len(expected_mapping)
                return _tier(score), round(score, 2), f"Wrong labels: {wrong}"

        return "Excellent", 1.0, f"All {len(items)} items correctly classified"
    return validate


# ── 6 · SQL logic validator ───────────────────────────────────────────────────

def sql_validator(
    required_clauses: list[str],
    forbidden_patterns: list[str] | None = None,
) -> ValidatorFn:
    """
    Extract SQL from response and check structural correctness:
      - required_clauses  : e.g. ["SELECT", "GROUP BY", "HAVING"]
      - forbidden_patterns: e.g. ["SELECT *", "DROP"]
    """
    def validate(response: str) -> tuple[str, float, str]:
        sql_match = re.search(
            r"```(?:sql)?\s*\n(.*?)```", response, re.DOTALL | re.IGNORECASE
        )
        sql = sql_match.group(1).strip() if sql_match else response.strip()
        sql_upper = sql.upper()

        missing = [c for c in required_clauses if c.upper() not in sql_upper]
        forbidden_found = [
            p for p in (forbidden_patterns or [])
            if re.search(p, sql_upper)
        ]

        if forbidden_found:
            return "Poor", 0.0, f"Forbidden patterns found: {forbidden_found}"

        if missing:
            score = 1 - len(missing) / len(required_clauses)
            return _tier(score), round(score, 2), f"Missing clauses: {missing}"

        return "Excellent", 1.0, f"All {len(required_clauses)} required clauses present"
    return validate
