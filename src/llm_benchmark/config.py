"""
Model registry for Databricks Foundation Model APIs (AI Playground).

Model IDs use the databricks- prefix — these are the exact strings passed
to the Databricks-hosted endpoint.  Prices are vendor AI token rates in
USD per 1M tokens (no DBU compute costs included).

Llama models are open-source; Databricks charges compute (DBU) only —
ai_cost_usd will be $0 for those, DBU cost appears in your workspace bill.
"""

MODELS = [

    # ── Anthropic Claude ─────────────────────────────────────────────────────
    {
        "model_id":             "databricks-claude-opus-4-7",
        "display_name":         "Claude Opus 4.7",
        "provider":             "anthropic",
        "input_price_per_1m":   15.00,
        "output_price_per_1m":  75.00,
    },
    {
        "model_id":             "databricks-claude-sonnet-4-6",
        "display_name":         "Claude Sonnet 4.6",
        "provider":             "anthropic",
        "input_price_per_1m":   3.00,
        "output_price_per_1m":  15.00,
    },
    {
        "model_id":             "databricks-claude-sonnet-4-5",
        "display_name":         "Claude Sonnet 4.5",
        "provider":             "anthropic",
        "input_price_per_1m":   3.00,
        "output_price_per_1m":  15.00,
    },
    {
        "model_id":             "databricks-claude-haiku-4-5",
        "display_name":         "Claude Haiku 4.5",
        "provider":             "anthropic",
        "input_price_per_1m":   0.80,
        "output_price_per_1m":  4.00,
    },

    # ── OpenAI GPT ───────────────────────────────────────────────────────────
    {
        "model_id":             "databricks-gpt-4o",
        "display_name":         "GPT-4o",
        "provider":             "openai",
        "input_price_per_1m":   2.50,
        "output_price_per_1m":  10.00,
    },
    {
        "model_id":             "databricks-gpt-4o-mini",
        "display_name":         "GPT-4o-mini",
        "provider":             "openai",
        "input_price_per_1m":   0.15,
        "output_price_per_1m":  0.60,
    },

    # ── Google Gemini ────────────────────────────────────────────────────────
    {
        "model_id":             "databricks-gemini-2-5-pro",
        "display_name":         "Gemini 2.5 Pro",
        "provider":             "google",
        "input_price_per_1m":   1.25,
        "output_price_per_1m":  10.00,
    },
    {
        "model_id":             "databricks-gemini-2-5-flash",
        "display_name":         "Gemini 2.5 Flash",
        "provider":             "google",
        "input_price_per_1m":   0.075,
        "output_price_per_1m":  0.30,
    },
    {
        "model_id":             "databricks-gemini-3-pro",
        "display_name":         "Gemini 3 Pro",
        "provider":             "google",
        "input_price_per_1m":   2.50,
        "output_price_per_1m":  10.00,
    },
    {
        "model_id":             "databricks-gemini-3-flash",
        "display_name":         "Gemini 3 Flash",
        "provider":             "google",
        "input_price_per_1m":   0.10,
        "output_price_per_1m":  0.40,
    },

    # ── Meta Llama (open-source — Databricks charges compute DBUs only) ──────
    {
        "model_id":             "databricks-llama-4-maverick",
        "display_name":         "Llama 4 Maverick",
        "provider":             "meta",
        "input_price_per_1m":   0.00,   # open-source, DBU compute only
        "output_price_per_1m":  0.00,
    },
    {
        "model_id":             "databricks-meta-llama-3-3-70b-instruct",
        "display_name":         "Llama 3.3 70B Instruct",
        "provider":             "meta",
        "input_price_per_1m":   0.00,
        "output_price_per_1m":  0.00,
    },
    {
        "model_id":             "databricks-meta-llama-3-1-405b-instruct",
        "display_name":         "Llama 3.1 405B Instruct",
        "provider":             "meta",
        "input_price_per_1m":   0.00,
        "output_price_per_1m":  0.00,
    },
    {
        "model_id":             "databricks-meta-llama-3-1-8b-instruct",
        "display_name":         "Llama 3.1 8B Instruct",
        "provider":             "meta",
        "input_price_per_1m":   0.00,
        "output_price_per_1m":  0.00,
    },
]

PRICING = {m["model_id"]: m for m in MODELS}
