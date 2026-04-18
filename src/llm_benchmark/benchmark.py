"""
Core benchmark runner.

Sends every test prompt to every configured model via the Databricks
AI Gateway (OpenAI-compatible endpoint) and collects:
  - tokens used (input + output)
  - AI token cost (vendor price only, no DBUs)
  - wall-clock response time
  - accuracy score
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import openai

from .accuracy import score_response
from .config import MODELS, PRICING
from .prompts import TEST_PROMPTS


@dataclass
class ModelResult:
    model_display_name: str
    model_id: str
    prompt_id: str
    prompt_category: str
    prompt_text: str
    response_text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    ai_cost_usd: float
    response_time_sec: float
    accuracy_label: str
    accuracy_score: float
    error: Optional[str] = None


def _build_client() -> openai.OpenAI:
    """
    Returns an OpenAI client pointed at the Databricks AI Gateway.

    Required env vars:
      DATABRICKS_HOST   – e.g. https://adb-<id>.azuredatabricks.net
      DATABRICKS_TOKEN  – Personal Access Token
    """
    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if not host or not token:
        raise EnvironmentError(
            "Set DATABRICKS_HOST and DATABRICKS_TOKEN environment variables."
        )
    return openai.OpenAI(
        base_url=f"{host}/serving-endpoints",
        api_key=token,
    )


def _calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    pricing = PRICING.get(model_id)
    if not pricing:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * pricing["input_price_per_1m"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_price_per_1m"]
    return round(input_cost + output_cost, 8)


def run_single(
    client: openai.OpenAI,
    model_cfg: dict,
    prompt_spec: dict,
    max_tokens: int = 256,
) -> ModelResult:
    model_id = model_cfg["model_id"]
    prompt_text = prompt_spec["prompt"]

    error = None
    response_text = ""
    input_tokens = output_tokens = total_tokens = 0
    ai_cost = 0.0
    accuracy_label = "N/A"
    accuracy_score = 0.0
    elapsed = 0.0

    try:
        start = time.perf_counter()
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=max_tokens,
            temperature=0,
        )
        elapsed = round(time.perf_counter() - start, 3)

        response_text = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        ai_cost = _calculate_cost(model_id, input_tokens, output_tokens)
        accuracy_label, accuracy_score = score_response(response_text, prompt_spec)

    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        elapsed = round(time.perf_counter() - start, 3) if elapsed == 0 else elapsed

    return ModelResult(
        model_display_name=model_cfg["display_name"],
        model_id=model_id,
        prompt_id=prompt_spec["id"],
        prompt_category=prompt_spec["category"],
        prompt_text=prompt_text,
        response_text=response_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        ai_cost_usd=ai_cost,
        response_time_sec=elapsed,
        accuracy_label=accuracy_label,
        accuracy_score=accuracy_score,
        error=error,
    )


def run_benchmark(
    models: list[dict] | None = None,
    prompts: list[dict] | None = None,
    max_tokens: int = 256,
) -> list[ModelResult]:
    """
    Run all prompts against all models.

    Args:
        models:     Override MODELS list (useful for testing a subset).
        prompts:    Override TEST_PROMPTS list.
        max_tokens: Max output tokens per call.

    Returns:
        Flat list of ModelResult, one per (model, prompt) pair.
    """
    client = _build_client()
    models = models or MODELS
    prompts = prompts or TEST_PROMPTS

    results: list[ModelResult] = []
    total = len(models) * len(prompts)
    count = 0

    for model_cfg in models:
        for prompt_spec in prompts:
            count += 1
            print(
                f"[{count}/{total}] {model_cfg['display_name']} ← {prompt_spec['id']}",
                flush=True,
            )
            result = run_single(client, model_cfg, prompt_spec, max_tokens)
            results.append(result)

    return results
