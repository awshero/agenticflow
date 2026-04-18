"""
Test prompt suite with ground-truth answers for accuracy scoring.
Each prompt has: question, expected keywords that a correct answer must contain,
and an optional exact_answer for strict matching.
"""

TEST_PROMPTS = [
    {
        "id": "capital_france",
        "category": "Factual",
        "prompt": "What is the capital city of France? Answer in one word.",
        "expected_keywords": ["paris"],
        "exact_answer": "paris",
    },
    {
        "id": "python_inventor",
        "category": "Factual",
        "prompt": "Who created the Python programming language? Answer in one sentence.",
        "expected_keywords": ["guido", "van rossum"],
        "exact_answer": None,
    },
    {
        "id": "sql_join_explain",
        "category": "Technical",
        "prompt": (
            "Explain the difference between INNER JOIN and LEFT JOIN in SQL. "
            "Keep it under 60 words."
        ),
        "expected_keywords": ["inner join", "matching", "left join", "all rows"],
        "exact_answer": None,
    },
    {
        "id": "summarise_text",
        "category": "Reasoning",
        "prompt": (
            "Summarise this in one sentence: "
            "'Databricks is a unified analytics platform built on Apache Spark "
            "that enables data engineering, data science, and machine learning at scale.'"
        ),
        "expected_keywords": ["databricks", "spark", "analytics"],
        "exact_answer": None,
    },
    {
        "id": "math_simple",
        "category": "Math",
        "prompt": "What is 17 multiplied by 23? Provide only the numeric answer.",
        "expected_keywords": ["391"],
        "exact_answer": "391",
    },
    {
        "id": "sentiment",
        "category": "NLP",
        "prompt": (
            "Classify the sentiment of this review as Positive, Negative, or Neutral. "
            "Reply with one word only: "
            "'The product arrived on time and works perfectly. Very happy with the purchase!'"
        ),
        "expected_keywords": ["positive"],
        "exact_answer": "positive",
    },
]
