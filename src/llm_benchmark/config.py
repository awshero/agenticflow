"""
Model registry for Databricks Foundation Model APIs (AI Playground).

Model IDs use the databricks- prefix (exact strings for Databricks API calls).
Prices are vendor/market token rates in USD per 1M tokens — no DBU costs.

Meta Llama pricing based on Meta's llama API / OpenRouter market rates
(Meta does not sell API access directly; these are standard market rates).
"""

MODELS = [

    # ── Anthropic Claude ─────────────────────────────────────────────────────
    {
        "model_id":            "databricks-claude-opus-4-7",
        "display_name":        "Claude Opus 4.7",
        "provider":            "Anthropic",
        "input_price_per_1m":  15.00,
        "output_price_per_1m": 75.00,
    },
    {
        "model_id":            "databricks-claude-sonnet-4-6",
        "display_name":        "Claude Sonnet 4.6",
        "provider":            "Anthropic",
        "input_price_per_1m":  3.00,
        "output_price_per_1m": 15.00,
    },
    {
        "model_id":            "databricks-claude-sonnet-4-5",
        "display_name":        "Claude Sonnet 4.5",
        "provider":            "Anthropic",
        "input_price_per_1m":  3.00,
        "output_price_per_1m": 15.00,
    },
    {
        "model_id":            "databricks-claude-haiku-4-5",
        "display_name":        "Claude Haiku 4.5",
        "provider":            "Anthropic",
        "input_price_per_1m":  0.80,
        "output_price_per_1m": 4.00,
    },

    # ── OpenAI GPT ───────────────────────────────────────────────────────────
    {
        "model_id":            "databricks-gpt-4o",
        "display_name":        "GPT-4o",
        "provider":            "OpenAI",
        "input_price_per_1m":  2.50,
        "output_price_per_1m": 10.00,
    },
    {
        "model_id":            "databricks-gpt-4o-mini",
        "display_name":        "GPT-4o-mini",
        "provider":            "OpenAI",
        "input_price_per_1m":  0.15,
        "output_price_per_1m": 0.60,
    },

    # ── Google Gemini ────────────────────────────────────────────────────────
    {
        "model_id":            "databricks-gemini-3-pro",
        "display_name":        "Gemini 3 Pro",
        "provider":            "Google",
        "input_price_per_1m":  2.50,
        "output_price_per_1m": 10.00,
    },
    {
        "model_id":            "databricks-gemini-3-flash",
        "display_name":        "Gemini 3 Flash",
        "provider":            "Google",
        "input_price_per_1m":  0.10,
        "output_price_per_1m": 0.40,
    },
    {
        "model_id":            "databricks-gemini-2-5-pro",
        "display_name":        "Gemini 2.5 Pro",
        "provider":            "Google",
        "input_price_per_1m":  1.25,
        "output_price_per_1m": 10.00,
    },
    {
        "model_id":            "databricks-gemini-2-5-flash",
        "display_name":        "Gemini 2.5 Flash",
        "provider":            "Google",
        "input_price_per_1m":  0.075,
        "output_price_per_1m": 0.30,
    },

    # ── Meta Llama ───────────────────────────────────────────────────────────
    # Pricing based on Meta Llama API / OpenRouter market rates
    {
        "model_id":            "databricks-llama-4-maverick",
        "display_name":        "Llama 4 Maverick",
        "provider":            "Meta",
        "input_price_per_1m":  0.15,
        "output_price_per_1m": 0.60,
    },
    {
        "model_id":            "databricks-meta-llama-3-3-70b-instruct",
        "display_name":        "Llama 3.3 70B Instruct",
        "provider":            "Meta",
        "input_price_per_1m":  0.12,
        "output_price_per_1m": 0.38,
    },
    {
        "model_id":            "databricks-meta-llama-3-1-405b-instruct",
        "display_name":        "Llama 3.1 405B Instruct",
        "provider":            "Meta",
        "input_price_per_1m":  4.00,
        "output_price_per_1m": 4.00,
    },
    {
        "model_id":            "databricks-meta-llama-3-1-8b-instruct",
        "display_name":        "Llama 3.1 8B Instruct",
        "provider":            "Meta",
        "input_price_per_1m":  0.02,
        "output_price_per_1m": 0.05,
    },
]

PRICING = {m["model_id"]: m for m in MODELS}
