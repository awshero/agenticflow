"""
Model registry and pricing table for Databricks-hosted LLMs.
Prices are vendor AI token prices only (not DBU compute costs).
All prices in USD per 1M tokens.
"""

MODELS = [
    # ── OpenAI ──────────────────────────────────────────────────
    {
        "model_id": "openai/gpt-4o",
        "display_name": "GPT-4o",
        "provider": "openai",
        "input_price_per_1m": 2.50,
        "output_price_per_1m": 10.00,
    },
    {
        "model_id": "openai/gpt-4o-mini",
        "display_name": "GPT-4o-mini",
        "provider": "openai",
        "input_price_per_1m": 0.15,
        "output_price_per_1m": 0.60,
    },
    # ── Anthropic ────────────────────────────────────────────────
    {
        "model_id": "anthropic/claude-3-5-sonnet-2",
        "display_name": "Claude 3.5 Sonnet",
        "provider": "anthropic",
        "input_price_per_1m": 3.00,
        "output_price_per_1m": 15.00,
    },
    {
        "model_id": "anthropic/claude-3-opus",
        "display_name": "Claude 3 Opus",
        "provider": "anthropic",
        "input_price_per_1m": 15.00,
        "output_price_per_1m": 75.00,
    },
    # ── Google ───────────────────────────────────────────────────
    {
        "model_id": "google/gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "provider": "google",
        "input_price_per_1m": 1.25,   # ≤200k context window
        "output_price_per_1m": 10.00,
    },
    {
        "model_id": "google/gemini-2.0-flash",
        "display_name": "Gemini 2.0 Flash",
        "provider": "google",
        "input_price_per_1m": 0.10,
        "output_price_per_1m": 0.40,
    },
    # Legacy — kept for reference only
    {
        "model_id": "google/gemini-1.5-pro",
        "display_name": "Gemini 1.5 Pro (legacy)",
        "provider": "google",
        "input_price_per_1m": 2.50,   # corrected from 1.25
        "output_price_per_1m": 10.00,
    },
    {
        "model_id": "google/gemini-1.5-flash",
        "display_name": "Gemini 1.5 Flash (legacy)",
        "provider": "google",
        "input_price_per_1m": 0.075,
        "output_price_per_1m": 0.30,
    },
]

# Map model_id → pricing for quick lookup
PRICING = {m["model_id"]: m for m in MODELS}
