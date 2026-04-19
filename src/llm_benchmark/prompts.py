"""
Test prompt suite with auto-validators for accuracy scoring.

Each prompt has:
  id          : unique identifier
  category    : Factual | Math | Code | Data | SQL | Classification
  prompt      : text sent to the model
  validator   : callable(response_text) → (label, score, detail)
"""

from .validators import (
    classification_validator,
    code_exec_validator,
    json_schema_validator,
    numeric_validator,
    regex_extraction_validator,
    sql_validator,
)

TEST_PROMPTS = [

    # ── Factual ───────────────────────────────────────────────────────────────
    {
        "id":       "capital_france",
        "category": "Factual",
        "prompt":   "What is the capital city of France? Answer in one word only.",
        "validator": lambda r: (
            ("Excellent", 1.0, "Correct") if "paris" in r.lower()
            else ("Poor", 0.0, f"Expected 'Paris', got: {r.strip()[:50]}")
        ),
    },

    # ── Math: numeric extraction ──────────────────────────────────────────────
    {
        "id":       "compound_interest",
        "category": "Math",
        "prompt": (
            "Calculate compound interest: principal=$10,000, annual rate=5%, "
            "compounded monthly, time=3 years. "
            "Return only the final amount rounded to 2 decimal places."
        ),
        # A = 10000 * (1 + 0.05/12)^(12*3) = 11614.72
        "validator": numeric_validator(expected=11614.72, tolerance=0.05),
    },
    {
        "id":       "prime_check_math",
        "category": "Math",
        "prompt": (
            "How many prime numbers are there between 1 and 50? "
            "Answer with a single integer."
        ),
        # Primes: 2,3,5,7,11,13,17,19,23,29,31,37,41,43,47 = 15
        "validator": numeric_validator(expected=15, tolerance=0),
    },

    # ── Code execution ────────────────────────────────────────────────────────
    {
        "id":       "code_reverse_string",
        "category": "Code",
        "prompt": (
            "Write a Python function named `reverse_string` that takes a string "
            "and returns it reversed. Return only the function, no explanation."
        ),
        "validator": code_exec_validator([
            {"call": "reverse_string('hello')",   "expected": "olleh"},
            {"call": "reverse_string('databricks')", "expected": "skcirbaatad"},
            {"call": "reverse_string('')",         "expected": ""},
            {"call": "reverse_string('a')",        "expected": "a"},
        ]),
    },
    {
        "id":       "code_fibonacci",
        "category": "Code",
        "prompt": (
            "Write a Python function named `fibonacci` that returns the nth "
            "Fibonacci number (0-indexed, so fibonacci(0)=0, fibonacci(1)=1). "
            "Return only the function."
        ),
        "validator": code_exec_validator([
            {"call": "fibonacci(0)",  "expected": 0},
            {"call": "fibonacci(1)",  "expected": 1},
            {"call": "fibonacci(6)",  "expected": 8},
            {"call": "fibonacci(10)", "expected": 55},
        ]),
    },
    {
        "id":       "code_word_count",
        "category": "Code",
        "prompt": (
            "Write a Python function named `word_count` that takes a string and "
            "returns a dict of word frequencies (case-insensitive). "
            "Return only the function."
        ),
        "validator": code_exec_validator([
            {"call": "word_count('the cat sat on the mat')",
             "expected": {"the": 2, "cat": 1, "sat": 1, "on": 1, "mat": 1}},
            {"call": "word_count('Hello hello HELLO')",
             "expected": {"hello": 3}},
            {"call": "word_count('')",
             "expected": {}},
        ]),
    },

    # ── JSON / structured output ──────────────────────────────────────────────
    {
        "id":       "json_person_extraction",
        "category": "Data",
        "prompt": (
            "Extract the following information from this text and return as JSON:\n"
            "Text: 'John Smith is 34 years old and works as a Data Engineer at Databricks.'\n"
            "Required fields: name, age, job_title, company.\n"
            "Return only the JSON object."
        ),
        "validator": json_schema_validator(
            required_keys=["name", "age", "job_title", "company"],
            value_checks={
                "name":      lambda v: "john" in str(v).lower(),
                "age":       lambda v: int(str(v).replace('"', '')) == 34,
                "job_title": lambda v: "engineer" in str(v).lower(),
                "company":   lambda v: "databricks" in str(v).lower(),
            },
        ),
    },
    {
        "id":       "json_product_list",
        "category": "Data",
        "prompt": (
            "Return a JSON array of 3 products with fields: id (integer), "
            "name (string), price (float), in_stock (boolean). "
            "Return only the JSON array."
        ),
        "validator": json_schema_validator(
            required_keys=["id", "name", "price", "in_stock"],
        ),
    },

    # ── Regex extraction ──────────────────────────────────────────────────────
    {
        "id":       "extract_emails",
        "category": "Data",
        "prompt": (
            "Extract all email addresses from this text:\n"
            "'Contact us at support@databricks.com or sales@company.org. "
            "For billing: billing@example.co.uk'\n"
            "List each email on a new line."
        ),
        "validator": regex_extraction_validator(
            items_to_find=[
                "support@databricks.com",
                "sales@company.org",
                "billing@example.co.uk",
            ],
            item_pattern=r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
            label_name="email",
        ),
    },

    # ── Classification ────────────────────────────────────────────────────────
    {
        "id":       "sentiment_multi",
        "category": "Classification",
        "prompt": (
            "Classify the sentiment of each review as Positive, Negative, or Neutral.\n"
            "1. 'Absolutely love this product!'\n"
            "2. 'Terrible experience, never buying again.'\n"
            "3. 'It arrived on time.'\n"
            "Format: '1. <label>, 2. <label>, 3. <label>'"
        ),
        "validator": classification_validator(
            items=["1", "2", "3"],
            valid_labels=["Positive", "Negative", "Neutral"],
            expected_mapping={"1": "Positive", "2": "Negative", "3": "Neutral"},
        ),
    },
    {
        "id":       "topic_classification",
        "category": "Classification",
        "prompt": (
            "Classify each sentence into one of: Technology, Sports, Finance, Health.\n"
            "A. 'The stock market hit a record high today.'\n"
            "B. 'Scientists developed a new cancer vaccine.'\n"
            "C. 'The team won the championship after overtime.'\n"
            "D. 'AI models are now used in chip design.'\n"
            "Format: 'A. <topic>, B. <topic>, C. <topic>, D. <topic>'"
        ),
        "validator": classification_validator(
            items=["A", "B", "C", "D"],
            valid_labels=["Technology", "Sports", "Finance", "Health"],
            expected_mapping={
                "A": "Finance",
                "B": "Health",
                "C": "Sports",
                "D": "Technology",
            },
        ),
    },

    # ── SQL ───────────────────────────────────────────────────────────────────
    {
        "id":       "sql_aggregation",
        "category": "SQL",
        "prompt": (
            "Write a SQL query to find the top 3 customers by total order value "
            "from a table called `orders` with columns: customer_id, order_amount, order_date. "
            "Include total_spent per customer. Return only the SQL."
        ),
        "validator": sql_validator(
            required_clauses=["SELECT", "FROM", "GROUP BY", "ORDER BY", "LIMIT"],
            forbidden_patterns=[r"SELECT \*", r"DROP", r"DELETE"],
        ),
    },
    {
        "id":       "sql_window_function",
        "category": "SQL",
        "prompt": (
            "Write a SQL query using a window function to rank employees by salary "
            "within each department. Table: `employees(id, name, department, salary)`. "
            "Include columns: name, department, salary, rank. Return only the SQL."
        ),
        "validator": sql_validator(
            required_clauses=["SELECT", "FROM", "OVER", "PARTITION BY", "ORDER BY"],
            forbidden_patterns=[r"DROP", r"DELETE", r"TRUNCATE"],
        ),
    },
]
