"""
LLM Magic Quadrant — Streamlit UI

Run:  streamlit run llm_ui/app.py
"""

import re, json, time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from collections import defaultdict
from io import BytesIO
import openai
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LLM Magic Quadrant",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Model registry ─────────────────────────────────────────────────────────────
MODELS = [
    {"model_id": "databricks-claude-opus-4-7",             "display_name": "Claude Opus 4.7",   "provider": "Anthropic", "input_price_per_1m": 15.00, "output_price_per_1m": 75.00},
    {"model_id": "databricks-claude-sonnet-4-6",           "display_name": "Claude Sonnet 4.6", "provider": "Anthropic", "input_price_per_1m":  3.00, "output_price_per_1m": 15.00},
    {"model_id": "databricks-claude-haiku-4-5",            "display_name": "Claude Haiku 4.5",  "provider": "Anthropic", "input_price_per_1m":  0.80, "output_price_per_1m":  4.00},
    {"model_id": "databricks-gpt-4o",                      "display_name": "GPT-4o",             "provider": "OpenAI",    "input_price_per_1m":  2.50, "output_price_per_1m": 10.00},
    {"model_id": "databricks-gpt-4o-mini",                 "display_name": "GPT-4o-mini",        "provider": "OpenAI",    "input_price_per_1m":  0.15, "output_price_per_1m":  0.60},
    {"model_id": "databricks-gemini-2-5-pro",              "display_name": "Gemini 2.5 Pro",     "provider": "Google",    "input_price_per_1m":  1.25, "output_price_per_1m": 10.00},
    {"model_id": "databricks-gemini-2-5-flash",            "display_name": "Gemini 2.5 Flash",   "provider": "Google",    "input_price_per_1m": 0.075, "output_price_per_1m":  0.30},
    {"model_id": "databricks-llama-4-maverick",            "display_name": "Llama 4 Maverick",   "provider": "Meta",      "input_price_per_1m":  0.15, "output_price_per_1m":  0.60},
    {"model_id": "databricks-meta-llama-3-3-70b-instruct", "display_name": "Llama 3.3 70B",      "provider": "Meta",      "input_price_per_1m":  0.12, "output_price_per_1m":  0.38},
    {"model_id": "databricks-meta-llama-3-1-8b-instruct",  "display_name": "Llama 3.1 8B",       "provider": "Meta",      "input_price_per_1m":  0.02, "output_price_per_1m":  0.05},
]
PRICING = {m["model_id"]: m for m in MODELS}

PROVIDER_COLORS = {
    "Anthropic": "#E07B39",
    "OpenAI":    "#10A37F",
    "Google":    "#4285F4",
    "Meta":      "#1877F2",
}

WEIGHT_PRESETS = {
    "balanced":         {"accuracy": 0.40, "cost": 0.30, "speed": 0.30},
    "quality_first":    {"accuracy": 0.60, "cost": 0.20, "speed": 0.20},
    "cost_sensitive":   {"accuracy": 0.30, "cost": 0.55, "speed": 0.15},
    "latency_critical": {"accuracy": 0.30, "cost": 0.20, "speed": 0.50},
}

ACCURACY_COLORS = {
    "Excellent": "#c6efce",
    "Good":      "#ffeb9c",
    "Partial":   "#ffcc99",
    "Poor":      "#ffc7ce",
    "Error":     "#d9d9d9",
}

# ── Validators ─────────────────────────────────────────────────────────────────
def _tier(s):
    return "Excellent" if s >= 1 else "Good" if s >= 0.75 else "Partial" if s >= 0.4 else "Poor"

def make_contains_all(keywords_str: str):
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    def v(r):
        if not keywords:
            return "Excellent", 1.0, "No keywords defined (auto-pass)"
        t = r.lower()
        missing = [k for k in keywords if k.lower() not in t]
        score = 1 - len(missing) / len(keywords)
        return _tier(score), round(score, 2), ("All keywords found" if not missing else f"Missing: {missing}")
    return v

def make_valid_json(keys_str: str):
    required_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    def v(r):
        try:
            m = re.search(r"(\{.*\}|\[.*\])", r, re.DOTALL)
            data = json.loads(m.group(1) if m else r.strip())
            if isinstance(data, list):
                data = data[0] if data else {}
            missing = [k for k in required_keys if k not in data]
            score = 1 - len(missing) / len(required_keys) if required_keys else 1.0
            return _tier(score), round(score, 2), ("Valid JSON" if not missing else f"Missing keys: {missing}")
        except Exception as e:
            return "Poor", 0.0, f"Invalid JSON: {e}"
    return v

def make_exact_number(expected: float, tolerance: float):
    def v(r):
        nums = re.findall(r"-?\d+(?:\.\d+)?", r.replace(",", ""))
        if not nums:
            return "Poor", 0.0, "No number found"
        got = float(nums[0])
        diff = abs(got - expected)
        if diff <= max(tolerance, 0.01):  return "Excellent", 1.0, f"Correct: {got}"
        if diff <= abs(expected) * 0.1:  return "Partial",   0.4,  f"Close: {got} vs {expected}"
        return "Poor", 0.0, f"Wrong: {got} vs {expected}"
    return v

def always_pass(r):
    return "Excellent", 1.0, "Open-ended (auto-pass)"

def build_validator(p: dict):
    vt = p.get("validator_type", "always_pass")
    if vt == "contains_all":
        return make_contains_all(p.get("validator_params", ""))
    if vt == "valid_json":
        return make_valid_json(p.get("validator_params", ""))
    if vt == "exact_number":
        return make_exact_number(float(p.get("expected", 0)), float(p.get("tolerance", 0.01)))
    return always_pass

# ── Preset use cases ───────────────────────────────────────────────────────────
PRESETS = {
    "Customer Support": {
        "name": "Customer Support Automation",
        "desc": "Classify tickets, generate replies, and extract structured data from customer messages.",
        "prompts": [
            {"id": "ticket_classification", "validator_type": "contains_all", "validator_params": "returns",
             "prompt": "Classify this support ticket into one category: Billing, Technical, Shipping, Returns, Other.\nTicket: 'My order arrived damaged and I want a refund.'\nReply with one word only."},
            {"id": "sentiment_urgency", "validator_type": "contains_all", "validator_params": "high, negative",
             "prompt": "Rate the urgency of this customer message as Low, Medium, or High, and its sentiment as Positive, Neutral, or Negative.\nMessage: 'This is the third time my payment has failed! I need this fixed NOW or I am cancelling!'\nFormat: 'Urgency: <level>, Sentiment: <value>'"},
            {"id": "reply_generation", "validator_type": "contains_all", "validator_params": "apologize, order",
             "prompt": "Write a professional customer support reply (under 60 words).\nMessage: 'Where is my order? It was supposed to arrive 3 days ago.'"},
            {"id": "extract_customer_info", "validator_type": "valid_json", "validator_params": "name, issue, product",
             "prompt": "Extract customer details from this message and return as JSON with fields: name, issue, product.\nMessage: 'Hi, I am Sarah. My laptop model XZ-500 keeps crashing after the last update.'\nReturn only the JSON."},
            {"id": "faq_answer", "validator_type": "contains_all", "validator_params": "refund, business days",
             "prompt": "Answer this customer FAQ in 1-2 sentences:\nQ: How long does a refund take to process?"},
            {"id": "summarise_thread", "validator_type": "contains_all", "validator_params": "internet, escalat",
             "prompt": "Summarise this support thread in one sentence:\nCustomer: My internet is down. Agent: Have you restarted the router? Customer: Yes, still down. Agent: I will escalate to our network team."},
        ],
    },
    "Financial Analysis": {
        "name": "Financial Analysis & Earnings Intelligence",
        "desc": "Extract structured financial data, perform calculations, and generate analyst commentary.",
        "prompts": [
            {"id": "earnings_extraction", "validator_type": "valid_json",
             "validator_params": "revenue_usd_millions, net_income_usd_millions, eps_diluted, gross_margin_pct",
             "prompt": "Extract the key financial metrics from the earnings release below and return them as a JSON object with fields: revenue_usd_millions, net_income_usd_millions, eps_diluted, yoy_revenue_growth_pct, gross_margin_pct, operating_margin_pct, free_cash_flow_usd_millions.\n\n--- EARNINGS RELEASE ---\nAcme Corp reported Q3 2024 revenue of $4,820 million, up 14.3% year-over-year from $4,217 million. Net income reached $612 million. Diluted EPS came in at $2.47. Gross profit was $2,073 million (gross margin: 43.0%). Operating income was $741 million (operating margin: 15.4%). Free cash flow: $524 million.\n---\n\nReturn ONLY the JSON object."},
            {"id": "cagr_calculation", "validator_type": "exact_number", "expected": 16.36, "tolerance": 0.5,
             "validator_params": "",
             "prompt": "Calculate the CAGR from 2018 to 2023 using: CAGR = (End/Start)^(1/Years) - 1\n  2018: 1,200  2019: 1,410  2020: 1,350  2021: 1,740  2022: 2,100  2023: 2,560\nRules: return ONLY the percentage number, no % sign, no words. Example: 13.42"},
            {"id": "dcf_commentary", "validator_type": "contains_all",
             "validator_params": "39.52, wacc, terminal, sensitivity",
             "prompt": "Write a professional DCF valuation commentary (100-150 words) for an equity research report.\n\nAssumptions: 5yr FCFs (USD M): 520, 590, 670, 755, 845. Terminal growth: 3.5%. WACC: 9.2%. Terminal value discounted: 6,840M. EV: 10,120M. Net debt: 320M. Shares: 248M. Implied share price: $39.52.\n\nInclude the implied intrinsic value per share and note key sensitivity risks."},
            {"id": "risk_identification", "validator_type": "valid_json",
             "validator_params": "title, category, impact",
             "prompt": "Identify 5 distinct risk factors from the text below. Return as a JSON array with fields: title (3-5 words), category (Market/Credit/Operational/Regulatory/Liquidity), impact (one sentence).\n\n--- RISK DISCLOSURE ---\nSignificant interest rate exposure — a 100bps increase adds $42M to annual interest expense. Two telecom counterparties represent 38% of $1.2B receivables. Manufacturing in Southeast Asia depends on just-in-time logistics; any port disruption halts production in 72 hours. EU Competition Authority investigation for alleged price-fixing; fines could reach 10% of affected revenue. Revolving credit facility of $600M expires in 14 months with rising refinancing risk.\n---\n\nReturn ONLY the JSON array."},
            {"id": "guidance_classification", "validator_type": "valid_json",
             "validator_params": "tone, revenue_guidance, margin_outlook, confidence",
             "prompt": "Analyse this CFO earnings call statement. Return JSON with fields: tone (Bullish/Neutral/Bearish), revenue_guidance (Raised/Maintained/Lowered/Not provided), margin_outlook (Expanding/Stable/Compressing/Unclear), confidence (High/Medium/Low).\n\n--- CFO STATEMENT ---\nWe are pleased to raise our full-year revenue outlook to $19.4–$19.8B, up from $18.9–$19.3B, reflecting stronger enterprise demand. On margins, we anticipate near-term headwinds from cloud infrastructure costs — operating margins will step down 50–80bps in Q4 before recovering in H1 next year. We remain confident in our long-term margin expansion thesis.\n---\n\nReturn ONLY the JSON."},
        ],
    },
    "Code Review & Security": {
        "name": "Code Review & Security Audit",
        "desc": "Detect bugs, identify security vulnerabilities, generate tests, analyse complexity.",
        "prompts": [
            {"id": "bug_detection", "validator_type": "contains_all",
             "validator_params": "empty, off-by-one, division, zero",
             "prompt": "Review the Python function below. Identify ALL bugs (logic errors, off-by-one, unhandled edge cases). For each bug: state the issue, explain why it is wrong, and provide the fix. Then provide a fully corrected version.\n\n```python\ndef process_transactions(transactions):\n    total = 0\n    for t in transactions:\n        total += t\n    average = total / len(transactions)        # BUG 1: division by zero on empty list\n    above_avg = []\n    for i in range(1, len(transactions)):       # BUG 2: off-by-one, misses index 0\n        if transactions[i] > average:\n            above_avg.append(transactions[i])\n    return {'total': total, 'average': average, 'above_average': above_avg,\n            'max': max(transactions),           # BUG 3: crashes on empty list\n            'count': len(above_avg) / len(transactions)}  # BUG 4: should be int\n```"},
            {"id": "sql_injection_audit", "validator_type": "contains_all",
             "validator_params": "sql injection, parameterized, authentication, information disclosure",
             "prompt": "Perform a security audit of the Flask endpoint below. For each vulnerability: name it, assign CVSS severity (Critical/High/Medium/Low), explain the attack vector, and provide secure remediation code.\n\n```python\nfrom flask import Flask, request, jsonify\nimport sqlite3, os\napp = Flask(__name__)\n@app.route('/login', methods=['POST'])\ndef login():\n    username = request.form.get('username')\n    password = request.form.get('password')\n    conn = sqlite3.connect('users.db')\n    query = f\"SELECT * FROM users WHERE username='{username}' AND password='{password}'\"\n    user = conn.execute(query).fetchone()\n    if user:\n        token = os.urandom(8).hex()\n        return jsonify({'token': token, 'user_data': str(user)})\n    return jsonify({'error': f'Login failed for user {username}'}), 401\n@app.route('/admin/users')\ndef list_users():\n    rows = sqlite3.connect('users.db').execute('SELECT * FROM users').fetchall()\n    return jsonify({'users': [str(r) for r in rows]})\n```"},
            {"id": "unit_test_generation", "validator_type": "contains_all",
             "validator_params": "def test_, pytest, valueerror, parametrize",
             "prompt": "Write a comprehensive pytest test suite for the function below. Cover: happy path, edge cases (empty input, single element, negative numbers, floats), and error conditions. Use parametrize where appropriate.\n\n```python\ndef calculate_statistics(numbers):\n    if not numbers:\n        raise ValueError('Input list cannot be empty')\n    for n in numbers:\n        if not isinstance(n, (int, float)):\n            raise TypeError(f'Non-numeric: {n}')\n    mean = sum(numbers) / len(numbers)\n    s = sorted(numbers); mid = len(s) // 2\n    median = s[mid] if len(s) % 2 else (s[mid-1] + s[mid]) / 2\n    std = (sum((x-mean)**2 for x in numbers)/len(numbers))**0.5\n    return {'mean': mean, 'median': median, 'std_dev': std, 'min': min(numbers), 'max': max(numbers)}\n```"},
            {"id": "infra_security_review", "validator_type": "valid_json",
             "validator_params": "issue, severity, risk, fix",
             "prompt": "Audit the docker-compose.yml below for security misconfigurations. For each issue: severity (Critical/High/Medium/Low), risk description, and corrected config snippet. Return as JSON array with fields: issue, severity, risk, fix.\n\n```yaml\nservices:\n  api:\n    image: myapp:latest\n    ports: ['0.0.0.0:5432:5432']\n    environment:\n      - DB_PASSWORD=admin123\n      - SECRET_KEY=supersecretkey\n      - DEBUG=true\n    volumes: ['/:/host_root']\n    privileged: true\n    user: root\n  db:\n    image: postgres:latest\n    environment: [POSTGRES_PASSWORD=admin123]\n    ports: ['5432:5432']\n```"},
        ],
    },
    "Databricks Engineering": {
        "name": "Databricks & Data Engineering",
        "desc": "Generate PySpark code, DLT pipelines, optimise queries, and document schemas.",
        "prompts": [
            {"id": "pyspark_transformation", "validator_type": "contains_all",
             "validator_params": "from pyspark, groupBy, customer_id, datediff, customer_segment, when",
             "prompt": "Write a PySpark function using the DataFrame API (not RDD). Include all imports.\n\nInput: Delta table 'sales' — columns: order_id (string), customer_id (string), product_id (string), quantity (int), unit_price (double), order_date (date), region (string), is_returned (boolean).\n\nOutput: customer-level summary with:\n- customer_id\n- total_orders (distinct order_id where is_returned=false)\n- total_revenue (sum of quantity*unit_price where is_returned=false)\n- avg_order_value\n- first_order_date, last_order_date\n- days_as_customer (datediff between first and last)\n- top_region (region with highest revenue per customer)\n- customer_segment: 'VIP' if revenue>10000, 'Regular' if >1000, else 'Occasional'\n\nProvide the complete PySpark code in a single code block."},
            {"id": "dlt_pipeline", "validator_type": "contains_all",
             "validator_params": "@dlt.table, bronze, silver, gold, expect_or_drop, streaming",
             "prompt": "Write a complete Delta Live Tables (DLT) Python pipeline for a medallion architecture. Use @dlt.table and @dlt.expect_or_drop decorators.\n\nSource: streaming Kafka topic 'raw_clickstream' — JSON: {event_id, user_id, session_id, page_url, action_type, timestamp_ms, device_type, country}\n\nBronze: ingest JSON, parse timestamp_ms, add ingestion_time. Drop records where event_id IS NULL.\n\nSilver: filter to action_type IN ('click','view','purchase'). Deduplicate on event_id. Add session_duration_seconds. Quarantine (not drop) records where user_id IS NULL.\n\nGold: daily aggregate — date, country, device_type, action_type → event_count, unique_users, unique_sessions.\n\nOutput the complete pipeline code."},
            {"id": "spark_query_optimisation", "validator_type": "contains_all",
             "validator_params": "cast, partition, z-order, broadcast, predicate pushdown",
             "prompt": "The query below runs slowly on a 500M row Delta table. Identify ALL performance problems and provide an optimised version. Specify which Databricks features (Z-ORDER, liquid clustering, AQE, broadcast hints) to apply and why.\n\n```sql\nSELECT c.customer_name, c.email, c.country,\n       SUM(o.quantity * o.unit_price) AS total_spent,\n       COUNT(o.order_id) AS order_count,\n       MAX(o.order_date) AS last_order_date\nFROM orders o\nJOIN customers c ON CAST(o.customer_id AS STRING) = CAST(c.id AS INT)\nLEFT JOIN (SELECT order_id, COUNT(*) AS item_count FROM order_items GROUP BY order_id) sub\n       ON o.order_id = sub.order_id\nWHERE YEAR(o.order_date) = 2023\n  AND UPPER(c.country) IN ('US','UK','DE')\n  AND o.status NOT IN ('CANCELLED','RETURNED')\nGROUP BY c.customer_name, c.email, c.country\nHAVING total_spent > 500 ORDER BY total_spent DESC\n```\n\nList each issue with its impact, then provide the optimised query."},
            {"id": "schema_documentation", "validator_type": "valid_json",
             "validator_params": "column_name, data_type, description, pii_flag, data_quality_rule",
             "prompt": "Generate a comprehensive data dictionary as a JSON array for the schema below. For each field include: column_name, data_type, nullable, description (business meaning), example_value, pii_flag (true/false), data_quality_rule.\n\nSchema:\n  order_id STRING NOT NULL, customer_id STRING NOT NULL, email STRING NULLABLE,\n  order_date DATE NOT NULL, ship_date DATE NULLABLE,\n  status STRING NOT NULL (PENDING/PROCESSING/SHIPPED/DELIVERED/CANCELLED),\n  subtotal_usd DOUBLE NOT NULL, discount_pct DOUBLE NULLABLE (0-100),\n  tax_usd DOUBLE NOT NULL, total_usd DOUBLE NOT NULL,\n  payment_method STRING NOT NULL (CARD/PAYPAL/CRYPTO/INVOICE),\n  card_last4 STRING NULLABLE, ip_address STRING NULLABLE,\n  warehouse_id INT NOT NULL, carrier STRING NULLABLE, tracking_number STRING NULLABLE\n\nReturn ONLY the JSON array."},
            {"id": "data_quality_framework", "validator_type": "contains_all",
             "validator_params": "class, def run, not_null, quarantine, pass_rate, generate_report",
             "prompt": "Design and implement a reusable PySpark data quality framework as a Python class. The class should:\n1. Accept a Spark DataFrame and a list of rule definitions\n2. Support rule types: not_null, unique, range_check(min,max), regex_match, custom_sql\n3. Return a summary DataFrame: rule_name, column, rule_type, pass_count, fail_count, pass_rate_pct, sample_failures\n4. quarantine_mode: if True, split into (clean_df, quarantine_df)\n5. generate_report() method that prints a formatted ASCII summary table\n\nInclude a usage example demonstrating all rule types."},
        ],
    },
    "Legal & Compliance": {
        "name": "Legal & Compliance Document Analysis",
        "desc": "Extract contract data, identify liability clauses, flag GDPR gaps, and detect non-standard provisions.",
        "prompts": [
            {"id": "contract_extraction", "validator_type": "valid_json",
             "validator_params": "parties, effective_date, expiry_date, notice_period_days, governing_law, renewal_type",
             "prompt": "Extract key entities and dates from this contract excerpt. Return JSON with fields: parties (array of {name, role, jurisdiction}), effective_date, expiry_date, notice_period_days, governing_law, renewal_type (auto/manual/none), contract_value_usd.\n\n--- CONTRACT ---\nThis Master Services Agreement is entered into as of March 1, 2024 between Nexus Technologies Inc., a Delaware corporation ('Service Provider'), and GlobalRetail PLC, a company incorporated in England and Wales ('Client').\n1. TERM: 36 months, auto-renewing for 12-month periods unless either party gives 90 days written notice of non-renewal.\n2. GOVERNING LAW: State of New York.\n3. FEES: Monthly retainer of USD 42,000 (USD 1,512,000 over the initial term).\n---\n\nReturn ONLY the JSON object."},
            {"id": "liability_risk_rating", "validator_type": "valid_json",
             "validator_params": "clause_id, risk_rating, risk_bearer, is_non_standard, negotiation_point",
             "prompt": "Review these liability clauses. For each: risk_rating (Critical/High/Medium/Low), which party bears more risk, is_non_standard (bool), negotiation_point if High/Critical. Return JSON array with fields: clause_id, risk_rating, risk_bearer, is_non_standard, negotiation_point.\n\nClause A (Liability Cap): 'Total aggregate liability shall not exceed the greater of USD 500 or the fees paid in the preceding 30 days.'\n\nClause B (Indemnification): 'Client shall indemnify Service Provider from any and all claims arising out of Client's use of the Services, whether or not caused by the negligence of Service Provider.'\n\nClause C (Consequential Damages): 'Neither party shall be liable for indirect, consequential, or punitive damages, except for breaches of confidentiality or willful misconduct.'\n\nClause D (IP Ownership): 'All work product and IP created by Service Provider shall become sole property of Client upon full payment.'"},
            {"id": "gdpr_gap_analysis", "validator_type": "valid_json",
             "validator_params": "article, obligation_summary, status, gap_description",
             "prompt": "Analyse this DPA against GDPR Article 28(3) obligations. For each obligation state: Fully Addresses / Partially Addresses / Does Not Address. For gaps, specify what language should be added. Return JSON array with fields: article, obligation_summary, status, gap_description.\n\nObligations to check: Art.28(3)(a) Instructions only, (b) Confidentiality obligations, (c) Security measures, (d) Sub-processor restrictions, (e) Data subject rights assistance, (f) Deletion/return at end of contract, (g) Audit rights, Art.32 Encryption/pseudonymisation.\n\n--- DPA ---\nThe Processor shall: (i) process Personal Data only on written instructions; (ii) ensure authorised persons are bound by confidentiality obligations; (iii) implement reasonable security measures; (iv) not engage sub-processors without prior written consent; (v) delete all Personal Data within 30 days of termination unless required by law.\n---\n\nReturn ONLY the JSON array."},
            {"id": "nda_clause_review", "validator_type": "valid_json",
             "validator_params": "clause_number, is_non_standard, deviation_description, risk, suggested_language",
             "prompt": "Review these NDA clauses for deviations from market-standard mutual NDAs. For non-standard provisions: explain why it is unusual, what risk it creates, and suggest standard alternative language. Return JSON array: clause_number, is_non_standard (bool), deviation_description, risk, suggested_language.\n\n1. CONFIDENTIALITY PERIOD: 'Obligations shall survive in perpetuity and remain binding forever.'\n2. DEFINITION: 'Confidential Information means any and all information disclosed by either party, regardless of whether marked confidential, including information generally known to the public.'\n3. RESIDUALS: 'No obligation to restrict personnel who retain information in their unaided memories.'\n4. REMEDY: 'Parties agree monetary damages would be an adequate remedy and injunctive relief shall not be available.'\n5. EXCLUSIONS: 'Information is not Confidential if (a) in public domain prior to disclosure, (b) becomes public through no fault of Receiving Party, (c) independently developed.'"},
            {"id": "obligation_timeline", "validator_type": "valid_json",
             "validator_params": "party, action, deadline_or_trigger, consequence, urgency_rank",
             "prompt": "Extract all time-bound obligations from these contract clauses. Return JSON array sorted by urgency (shortest deadline first), fields: party, action, deadline_or_trigger, consequence, urgency_rank.\n\nSection 5.1: Service Provider shall deliver the initial project plan within 10 business days of the Effective Date.\nSection 5.3: Client shall provide written approval or objections within 5 business days of receiving each deliverable. Silence = acceptance.\nSection 7.2: Either party may terminate for cause with 30 days written notice if the other party materially breaches and fails to cure.\nSection 9.1: Service Provider shall notify Client of any confirmed data breach within 48 hours of discovery.\nSection 11.4: Invoices due within 30 days. Late payments accrue 1.5% interest per month.\nSection 14.2: On termination, Service Provider shall return or destroy all Client Confidential Information within 15 business days and provide written certification."},
        ],
    },
}

# ── Session state ──────────────────────────────────────────────────────────────
for _k, _v in {
    "prompts":       [],
    "raw_results":   None,
    "metrics":       None,
    "ranked":        None,
    "use_case_name": "My Use Case",
    "profile":       "balanced",
    "weights":       WEIGHT_PRESETS["balanced"],
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔮 LLM Magic Quadrant")
    st.caption("Databricks Foundation Model API Benchmarker")
    st.divider()

    st.subheader("🔑 Databricks Credentials")
    db_host = st.text_input(
        "Workspace URL",
        placeholder="https://adb-xxx.cloud.databricks.com",
        help="Your Databricks workspace base URL",
    )
    db_token = st.text_input(
        "Personal Access Token",
        type="password",
        placeholder="dapi…",
        help="User Settings → Access Tokens — needs model-serving scope",
    )

    st.divider()

    st.subheader("🤖 Models")
    selected_models = [
        m for m in MODELS
        if st.checkbox(
            f"{m['display_name']}  ·  {m['provider']}",
            value=True,
            key=f"mdl_{m['model_id']}",
        )
    ]
    st.caption(f"{len(selected_models)} of {len(MODELS)} selected")

    st.divider()

    st.subheader("⚖️ Weights")
    profile = st.selectbox(
        "Profile",
        list(WEIGHT_PRESETS),
        format_func=lambda x: {
            "balanced":         "Balanced  (40 · 30 · 30)",
            "quality_first":    "Quality First  (60 · 20 · 20)",
            "cost_sensitive":   "Cost Sensitive  (30 · 55 · 15)",
            "latency_critical": "Latency Critical  (30 · 20 · 50)",
        }[x],
    )
    weights = WEIGHT_PRESETS[profile]
    st.caption(
        f"Accuracy **{weights['accuracy']:.0%}**  ·  "
        f"Cost **{weights['cost']:.0%}**  ·  "
        f"Speed **{weights['speed']:.0%}**"
    )

    st.divider()

    st.subheader("⚙️ Advanced")
    max_tokens = st.slider("Max tokens / response", 256, 2048, 512, 128)
    call_delay = st.slider(
        "Delay between calls (s)", 0.5, 5.0, 1.0, 0.5,
        help="Increase if you hit 429 rate-limit errors",
    )


# ── Benchmark engine ───────────────────────────────────────────────────────────
def run_benchmark(client, models, prompts, weights, max_tokens, call_delay):
    """Run benchmark; yield (count, total, model_name, prompt_id, row_dict) per call."""
    total = len(models) * len(prompts)
    count = 0

    def _call(model_id, text, retries=4, base_wait=2):
        for attempt in range(retries):
            try:
                return client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": text}],
                    max_tokens=max_tokens,
                    temperature=0,
                )
            except openai.RateLimitError:
                wait = base_wait * (2 ** attempt)
                if attempt < retries - 1:
                    time.sleep(wait)
                else:
                    raise

    for model in models:
        for p in prompts:
            count += 1
            start = time.perf_counter()
            try:
                resp = _call(model["model_id"], p["prompt"])
                elapsed = round(time.perf_counter() - start, 3)
                text = resp.choices[0].message.content or ""
                inp = resp.usage.prompt_tokens if resp.usage else 0
                out = resp.usage.completion_tokens if resp.usage else 0
                cost = (
                    (inp / 1_000_000) * model["input_price_per_1m"]
                    + (out / 1_000_000) * model["output_price_per_1m"]
                )
                label, score, detail = build_validator(p)(text)
                row = dict(
                    model=model["display_name"], model_id=model["model_id"],
                    provider=model["provider"], prompt_id=p["id"],
                    input_tokens=inp, output_tokens=out, total_tokens=inp + out,
                    ai_cost_usd=cost, response_time_s=elapsed,
                    accuracy_label=label, accuracy_score=score,
                    accuracy_detail=detail, response=text, error=None,
                )
            except Exception as e:
                elapsed = round(time.perf_counter() - start, 3)
                row = dict(
                    model=model["display_name"], model_id=model["model_id"],
                    provider=model["provider"], prompt_id=p["id"],
                    input_tokens=0, output_tokens=0, total_tokens=0,
                    ai_cost_usd=0, response_time_s=elapsed,
                    accuracy_label="Error", accuracy_score=0,
                    accuracy_detail=str(e), response="", error=str(e),
                )
            yield count, total, model["display_name"], p["id"], row
            time.sleep(call_delay)


def compute_metrics(raw_results, weights):
    agg = defaultdict(lambda: {"acc": [], "time": [], "cost": [], "provider": "", "errors": 0, "calls": 0})
    for r in raw_results:
        a = agg[r["model"]]
        a["provider"] = r["provider"]
        a["calls"] += 1
        if r["error"]:
            a["errors"] += 1
        else:
            a["acc"].append(r["accuracy_score"])
            a["time"].append(r["response_time_s"])
            a["cost"].append(r["ai_cost_usd"])

    metrics = {}
    for name, a in agg.items():
        if not a["acc"]:
            continue
        metrics[name] = {
            "provider":     a["provider"],
            "avg_accuracy": sum(a["acc"]) / len(a["acc"]),
            "avg_time_s":   sum(a["time"]) / len(a["time"]),
            "total_cost":   sum(a["cost"]),
            "errors":       a["errors"],
            "calls":        a["calls"],
        }

    names = list(metrics.keys())
    if not names:
        return {}, []

    def norm(vals):
        mn, mx = min(vals), max(vals)
        return [0.5 if mx == mn else (v - mn) / (mx - mn) for v in vals]

    na = norm([metrics[m]["avg_accuracy"] for m in names])
    ns = norm([1 / metrics[m]["avg_time_s"] if metrics[m]["avg_time_s"] > 0 else 0 for m in names])
    nv = norm([1 / (metrics[m]["total_cost"] + 1e-9) for m in names])

    for i, m in enumerate(names):
        metrics[m].update(
            norm_accuracy=na[i], norm_speed=ns[i], norm_value=nv[i],
            composite=(
                weights["accuracy"] * na[i]
                + weights["cost"]   * nv[i]
                + weights["speed"]  * ns[i]
            ),
        )

    ranked = sorted(names, key=lambda m: metrics[m]["composite"], reverse=True)
    return metrics, ranked


# ── Magic Quadrant chart ───────────────────────────────────────────────────────
def build_quadrant_figure(metrics, ranked, use_case_name, profile, weights):
    winner = ranked[0]
    names = list(metrics.keys())

    fig, (ax_quad, ax_card) = plt.subplots(
        1, 2, figsize=(18, 8),
        gridspec_kw={"width_ratios": [2, 1]},
    )
    fig.patch.set_facecolor("#F4F6F9")
    fig.suptitle(
        f"LLM Magic Quadrant — {use_case_name}\n"
        f"Profile: {profile.replace('_',' ').title()}  "
        f"(Accuracy {weights['accuracy']:.0%}  ·  Cost {weights['cost']:.0%}  ·  Speed {weights['speed']:.0%})",
        fontsize=14, fontweight="bold", y=1.02,
    )

    # ── Quadrant scatter ──────────────────────────────────────────────────────
    ax = ax_quad
    ax.set_facecolor("#FFFFFF")
    ax.set_xlim(-0.08, 1.18)
    ax.set_ylim(-0.08, 1.18)
    ax.set_xlabel("Performance Score  (Accuracy →)", fontsize=11, labelpad=8)
    ax.set_ylabel("Value Score  (Cost Efficiency →)", fontsize=11, labelpad=8)
    ax.set_title("Magic Quadrant", fontsize=12, fontweight="bold", pad=10)
    ax.axvline(0.5, color="#BBBBBB", lw=1.5, ls="--", zorder=1)
    ax.axhline(0.5, color="#BBBBBB", lw=1.5, ls="--", zorder=1)

    for (x0, y0, bg, label, tc) in [
        (0.5, 0.5, "#E8F5E9", "⭐ LEADERS\n(Best overall)",         "#2e7d32"),
        (0.0, 0.5, "#FFF3E0", "💰 BUDGET OPTIONS\n(Cheap & decent)", "#e65100"),
        (0.5, 0.0, "#E3F2FD", "🏆 PREMIUM\n(Accurate but costly)",   "#1565c0"),
        (0.0, 0.0, "#FFEBEE", "⚠️  AVOID\n(Poor value & accuracy)",  "#b71c1c"),
    ]:
        ax.add_patch(plt.Rectangle((x0, y0), 0.5, 0.5, color=bg, zorder=0, alpha=0.55))
        ax.text(x0 + 0.25, y0 + 0.25, label, ha="center", va="center",
                fontsize=8, color=tc, alpha=0.5, fontweight="bold", linespacing=1.5)

    used_providers = set()
    for m in names:
        mx = metrics[m]
        xv = mx["norm_accuracy"]
        yv = mx["norm_value"]
        sp = mx["norm_speed"]
        color = PROVIDER_COLORS.get(mx["provider"], "#888888")
        size = 300 + sp * 1200
        is_w = m == winner

        ax.scatter(xv, yv, s=size, color=color,
                   edgecolors="#FFD700" if is_w else "white",
                   linewidths=4 if is_w else 1.5,
                   zorder=5, alpha=0.92)

        short = m.replace(" Instruct", "").replace(" Maverick", " Mvk")
        oy = 0.08 if yv < 0.85 else -0.08
        ax.annotate(
            ("⭐ " if is_w else "") + short,
            xy=(xv, yv), xytext=(xv, yv + oy),
            ha="center", va="center", fontsize=8,
            fontweight="bold" if is_w else "normal",
            color="#1a1a2e",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, alpha=0.88, lw=1.2),
        )
        ax.annotate(
            f"acc={mx['avg_accuracy']:.2f}\n{mx['avg_time_s']:.2f}s\n${mx['total_cost']:.5f}",
            xy=(xv, yv), xytext=(xv + 0.03, yv - 0.12),
            fontsize=6.2, color="#555555", ha="left", va="top",
            bbox=dict(boxstyle="round,pad=0.2", fc="#F9F9F9", ec="#DDDDDD", alpha=0.8),
        )
        used_providers.add(mx["provider"])

    handles = [mpatches.Patch(color=PROVIDER_COLORS[p], label=p) for p in sorted(used_providers)]
    handles.append(plt.scatter([], [], s=300, c="gray", label="Bubble = Speed"))
    ax.legend(handles=handles, fontsize=8.5, loc="lower right", framealpha=0.9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # ── Scorecard ─────────────────────────────────────────────────────────────
    ax2 = ax_card
    ax2.set_facecolor("#FFFFFF")
    ax2.axis("off")
    ax2.set_title("Recommendation Scorecard", fontsize=12, fontweight="bold", pad=10)
    wm = metrics[winner]

    ax2.text(0.5, 0.97,
        f"\n⭐  RECOMMENDED FOR\n\"{use_case_name}\"",
        ha="center", va="top", fontsize=11, fontweight="bold",
        color="#2e7d32", transform=ax2.transAxes, linespacing=1.6,
    )
    ax2.text(0.5, 0.79, winner,
        ha="center", va="top", fontsize=15, fontweight="bold",
        color=PROVIDER_COLORS.get(wm["provider"], "#333"),
        transform=ax2.transAxes,
    )
    ax2.axhline(y=0.0, xmin=0.05, xmax=0.95, color="#CCC", transform=ax2.transAxes)

    for i, (lbl, val, color) in enumerate([
        ("Accuracy Score",   f"{wm['avg_accuracy']:.2f} / 1.00",  "#2e7d32"),
        ("Avg Response Time",f"{wm['avg_time_s']:.2f}s",           "#1565c0"),
        ("Total AI Cost",    f"${wm['total_cost']:.6f}",           "#6a1b9a"),
        ("Composite Score",  f"{wm['composite']:.3f} / 1.000",     "#e65100"),
        ("Provider",         wm["provider"],                        "#444444"),
        ("Weight Profile",   profile.replace("_", " ").title(),    "#444444"),
    ]):
        y = 0.62 - i * 0.09
        ax2.text(0.08, y, lbl + ":", ha="left", va="center", fontsize=9.5,
                 color="#555", transform=ax2.transAxes)
        ax2.text(0.92, y, val, ha="right", va="center", fontsize=10,
                 fontweight="bold", color=color, transform=ax2.transAxes)

    if len(ranked) > 1:
        runner = ranked[1]
        rm = metrics[runner]
        ax2.text(0.5, 0.05,
            f"Runner-up: {runner}\nComposite: {rm['composite']:.3f}   "
            f"Accuracy: {rm['avg_accuracy']:.2f}",
            ha="center", va="bottom", fontsize=8.5, color="#666",
            transform=ax2.transAxes, linespacing=1.5,
        )

    plt.tight_layout(pad=2)
    return fig


# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_cfg, tab_quad, tab_detail = st.tabs([
    "⚙️ Configure & Run",
    "📊 Magic Quadrant",
    "📋 Detail Results",
])

# ════════════════════════════════════════════════════════════════════════════════
# Tab 1 — Configure & Run
# ════════════════════════════════════════════════════════════════════════════════
with tab_cfg:
    col_uc, col_preset = st.columns([1, 1])

    with col_uc:
        st.subheader("Use Case")
        use_case_name = st.text_input("Name", st.session_state.use_case_name)
        use_case_desc = st.text_area("Description", height=72,
                                     placeholder="What tasks will this LLM need to handle?")

    with col_preset:
        st.subheader("Quick-load example")
        preset_key = st.selectbox(
            "Preset use case",
            ["— custom —"] + list(PRESETS.keys()),
        )
        if st.button("⚡ Load preset", disabled=(preset_key == "— custom —")):
            preset = PRESETS[preset_key]
            st.session_state.prompts = [dict(p) for p in preset["prompts"]]
            st.session_state.use_case_name = preset["name"]
            use_case_name = preset["name"]
            st.rerun()

    st.divider()

    # ── Prompt builder ──────────────────────────────────────────────────────
    header_c1, header_c2 = st.columns([3, 1])
    with header_c1:
        st.subheader(f"📝 Prompts  ({len(st.session_state.prompts)} defined)")
    with header_c2:
        col_add, col_clr = st.columns(2)
        with col_add:
            if st.button("➕ Add", use_container_width=True):
                st.session_state.prompts.append({
                    "id": f"prompt_{len(st.session_state.prompts)+1}",
                    "prompt": "",
                    "validator_type": "contains_all",
                    "validator_params": "",
                })
                st.rerun()
        with col_clr:
            if st.button("🗑 Clear", use_container_width=True):
                st.session_state.prompts = []
                st.rerun()

    to_delete = []
    for i, p in enumerate(st.session_state.prompts):
        label = f"Prompt {i+1} — {p.get('id','')}"
        expanded = (i == len(st.session_state.prompts) - 1)
        with st.expander(label, expanded=expanded):
            r1c1, r1c2, r1c3 = st.columns([1.8, 1.8, 0.4])
            with r1c1:
                p["id"] = st.text_input("ID", p.get("id", ""), key=f"pid_{i}")
            with r1c2:
                vtypes = ["contains_all", "valid_json", "exact_number", "always_pass"]
                cur = p.get("validator_type", "contains_all")
                p["validator_type"] = st.selectbox(
                    "Validator",
                    vtypes,
                    index=vtypes.index(cur) if cur in vtypes else 0,
                    key=f"pvt_{i}",
                )
            with r1c3:
                st.write("")
                st.write("")
                if st.button("🗑", key=f"del_{i}", help="Remove this prompt"):
                    to_delete.append(i)

            p["prompt"] = st.text_area(
                "Prompt text (sent verbatim to the LLM)",
                p.get("prompt", ""),
                height=130,
                key=f"ptxt_{i}",
            )

            vt = p["validator_type"]
            if vt == "contains_all":
                p["validator_params"] = st.text_input(
                    "Keywords to check (comma-separated, case-insensitive)",
                    p.get("validator_params", ""),
                    placeholder="e.g.  error, exception, json",
                    key=f"vp_{i}",
                )
                st.caption("Score = (keywords found) / (total keywords)")
            elif vt == "valid_json":
                p["validator_params"] = st.text_input(
                    "Required JSON keys (comma-separated)",
                    p.get("validator_params", ""),
                    placeholder="e.g.  name, status, value",
                    key=f"vp_{i}",
                )
                st.caption("Excellent if response is valid JSON containing all listed keys")
            elif vt == "exact_number":
                ec1, ec2 = st.columns(2)
                with ec1:
                    p["expected"] = st.number_input(
                        "Expected number", value=float(p.get("expected", 0)), key=f"vexp_{i}"
                    )
                with ec2:
                    p["tolerance"] = st.number_input(
                        "Tolerance (±)", value=float(p.get("tolerance", 0.01)),
                        format="%.4f", key=f"vtol_{i}"
                    )
                st.caption("Extracts first number in response and compares with tolerance")
            else:
                st.caption("always_pass: every response scores 1.0 — useful for open-ended/generative tasks")

    if to_delete:
        for idx in sorted(to_delete, reverse=True):
            st.session_state.prompts.pop(idx)
        st.rerun()

    st.divider()

    # ── Readiness check ─────────────────────────────────────────────────────
    issues = []
    if not db_host:                  issues.append("Databricks Workspace URL is required (sidebar)")
    if not db_token:                 issues.append("Databricks Token is required (sidebar)")
    if not selected_models:          issues.append("Select at least one model (sidebar)")
    if not st.session_state.prompts: issues.append("Add at least one prompt above")
    for p in st.session_state.prompts:
        if not p.get("prompt", "").strip():
            issues.append(f"Prompt '{p.get('id','')}' has empty text")

    for issue in issues:
        st.warning(f"⚠  {issue}")

    n_calls = len(selected_models) * len(st.session_state.prompts)
    run_btn = st.button(
        f"▶  Run Benchmark  —  {len(selected_models)} models  ×  "
        f"{len(st.session_state.prompts)} prompts  =  {n_calls} API calls",
        type="primary",
        disabled=bool(issues),
        use_container_width=True,
    )

    if run_btn:
        client = openai.OpenAI(
            base_url=f"{db_host.rstrip('/')}/serving-endpoints",
            api_key=db_token,
        )

        progress_bar = st.progress(0.0, text="Starting…")
        status_text  = st.empty()
        log_text     = st.empty()
        raw_results  = []

        for count, total, mname, pid, row in run_benchmark(
            client, selected_models, st.session_state.prompts,
            weights, max_tokens, call_delay
        ):
            pct = count / total
            progress_bar.progress(pct, text=f"[{count}/{total}]  {mname}  ←  {pid}")
            icon = {"Excellent": "✅", "Good": "🟡", "Partial": "🟠", "Poor": "🔴", "Error": "⛔"}.get(
                row["accuracy_label"], "•"
            )
            log_text.markdown(
                f"`{mname}` / `{pid}`  →  "
                f"{icon} **{row['accuracy_label']}** "
                f"(score={row['accuracy_score']:.2f})  "
                f"·  {row['response_time_s']:.2f}s  "
                f"·  ${row['ai_cost_usd']:.6f}"
            )
            raw_results.append(row)

        progress_bar.progress(1.0, text="✅ Benchmark complete!")
        log_text.empty()

        metrics, ranked = compute_metrics(raw_results, weights)
        st.session_state.raw_results   = raw_results
        st.session_state.metrics       = metrics
        st.session_state.ranked        = ranked
        st.session_state.use_case_name = use_case_name
        st.session_state.profile       = profile
        st.session_state.weights       = weights

        if ranked:
            st.success(
                f"🏆  **{ranked[0]}** is the top recommendation for **{use_case_name}**  "
                f"(composite score: {metrics[ranked[0]]['composite']:.3f}).  "
                f"Open the **📊 Magic Quadrant** tab to see the full chart."
            )
            st.balloons()
        else:
            st.error("All API calls failed — no results to show. Check your credentials and model availability.")


# ════════════════════════════════════════════════════════════════════════════════
# Tab 2 — Magic Quadrant
# ════════════════════════════════════════════════════════════════════════════════
with tab_quad:
    if not st.session_state.metrics:
        st.info("Run the benchmark first (⚙️ Configure & Run tab).")
    else:
        metrics  = st.session_state.metrics
        ranked   = st.session_state.ranked
        uc_name  = st.session_state.use_case_name
        prof     = st.session_state.profile
        wts      = st.session_state.weights
        winner   = ranked[0]

        # ── Top KPI strip ────────────────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        wm = metrics[winner]
        k1.metric("🏆 Recommended Model", winner)
        k2.metric("Accuracy",     f"{wm['avg_accuracy']:.2f} / 1.00")
        k3.metric("Avg Response", f"{wm['avg_time_s']:.2f}s")
        k4.metric("Total AI Cost",f"${wm['total_cost']:.6f}")

        st.divider()

        # ── Chart ────────────────────────────────────────────────────────────
        fig = build_quadrant_figure(metrics, ranked, uc_name, prof, wts)
        st.pyplot(fig, use_container_width=True)

        # ── Download chart ───────────────────────────────────────────────────
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        st.download_button(
            "⬇ Download chart (PNG)",
            data=buf,
            file_name=f"llm_magic_quadrant_{uc_name.lower().replace(' ','_')}.png",
            mime="image/png",
        )

        st.divider()

        # ── Ranked scorecard table ────────────────────────────────────────────
        st.subheader("Ranked Scorecard")
        mean_acc  = sum(metrics[m]["avg_accuracy"] for m in ranked) / len(ranked)
        mean_time = sum(metrics[m]["avg_time_s"]   for m in ranked) / len(ranked)
        mean_cost = sum(metrics[m]["total_cost"]   for m in ranked) / len(ranked)

        def pct_diff(v, ref):
            if ref == 0: return "N/A"
            d = (v - ref) / ref * 100
            return f"+{d:.1f}%" if d >= 0 else f"{d:.1f}%"

        rows = []
        for rank, m in enumerate(ranked, 1):
            mx = metrics[m]
            rows.append({
                "Rank":          f"#{rank}" + (" ⭐" if m == winner else ""),
                "Model":         m,
                "Provider":      mx["provider"],
                "Accuracy":      round(mx["avg_accuracy"], 3),
                "Acc vs Mean":   pct_diff(mx["avg_accuracy"], mean_acc),
                "Avg Time (s)":  round(mx["avg_time_s"], 2),
                "Time vs Mean":  pct_diff(mx["avg_time_s"],   mean_time),
                "Total Cost $":  round(mx["total_cost"], 6),
                "Cost vs Mean":  pct_diff(mx["total_cost"],   mean_cost),
                "Composite":     round(mx["composite"], 3),
                "Errors":        mx["errors"],
            })

        df_score = pd.DataFrame(rows)

        def _style_pct(v):
            if not isinstance(v, str): return ""
            if v.startswith("+"): return "color: #d32f2f; font-weight: bold"
            if v.startswith("-"): return "color: #388e3c; font-weight: bold"
            return ""

        def _style_pct_inv(v):
            if not isinstance(v, str): return ""
            if v.startswith("+"): return "color: #388e3c; font-weight: bold"
            if v.startswith("-"): return "color: #d32f2f; font-weight: bold"
            return ""

        styled = (
            df_score.style
            .background_gradient(subset=["Accuracy"],   cmap="RdYlGn")
            .background_gradient(subset=["Total Cost $"],cmap="RdYlGn_r")
            .background_gradient(subset=["Avg Time (s)"],cmap="RdYlGn_r")
            .background_gradient(subset=["Composite"],   cmap="RdYlGn")
            .map(_style_pct_inv, subset=["Acc vs Mean"])
            .map(_style_pct,     subset=["Time vs Mean", "Cost vs Mean"])
            .set_caption(f"Scorecard — {uc_name}  |  Profile: {prof}")
            .hide(axis="index")
        )
        st.dataframe(df_score, use_container_width=True, hide_index=True)

        # ── Exports ──────────────────────────────────────────────────────────
        st.subheader("Export")
        ec1, ec2 = st.columns(2)

        with ec1:
            csv_bytes = df_score.to_csv(index=False).encode()
            st.download_button(
                "⬇ Scorecard CSV",
                data=csv_bytes,
                file_name=f"llm_scorecard_{uc_name.lower().replace(' ','_')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with ec2:
            sc_json = json.dumps({
                "use_case": uc_name,
                "profile":  prof,
                "weights":  wts,
                "recommendation": winner,
                "scores": {
                    m: {
                        "accuracy":   round(metrics[m]["avg_accuracy"], 4),
                        "avg_time_s": round(metrics[m]["avg_time_s"], 3),
                        "total_cost": round(metrics[m]["total_cost"], 8),
                        "composite":  round(metrics[m]["composite"], 4),
                    }
                    for m in ranked
                },
            }, indent=2)
            st.download_button(
                "⬇ Scorecard JSON",
                data=sc_json.encode(),
                file_name=f"llm_scorecard_{uc_name.lower().replace(' ','_')}.json",
                mime="application/json",
                use_container_width=True,
            )


# ════════════════════════════════════════════════════════════════════════════════
# Tab 3 — Detail Results
# ════════════════════════════════════════════════════════════════════════════════
with tab_detail:
    if not st.session_state.raw_results:
        st.info("Run the benchmark first (⚙️ Configure & Run tab).")
    else:
        raw   = st.session_state.raw_results
        uc    = st.session_state.use_case_name

        df_raw = pd.DataFrame(raw)

        # ── Filters ──────────────────────────────────────────────────────────
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            filter_model = st.multiselect(
                "Filter by model",
                options=sorted(df_raw["model"].unique()),
                default=[],
            )
        with fc2:
            filter_prompt = st.multiselect(
                "Filter by prompt",
                options=sorted(df_raw["prompt_id"].unique()),
                default=[],
            )
        with fc3:
            filter_result = st.multiselect(
                "Filter by result",
                options=["Excellent", "Good", "Partial", "Poor", "Error"],
                default=[],
            )

        df_filtered = df_raw.copy()
        if filter_model:   df_filtered = df_filtered[df_filtered["model"].isin(filter_model)]
        if filter_prompt:  df_filtered = df_filtered[df_filtered["prompt_id"].isin(filter_prompt)]
        if filter_result:  df_filtered = df_filtered[df_filtered["accuracy_label"].isin(filter_result)]

        st.caption(f"{len(df_filtered)} of {len(df_raw)} results shown")

        # ── Detail table ──────────────────────────────────────────────────────
        display_cols = [
            "model", "prompt_id", "accuracy_label", "accuracy_score",
            "input_tokens", "output_tokens", "ai_cost_usd", "response_time_s",
            "accuracy_detail",
        ]
        st.dataframe(
            df_filtered[display_cols].rename(columns={
                "model":            "Model",
                "prompt_id":        "Prompt",
                "accuracy_label":   "Result",
                "accuracy_score":   "Score",
                "input_tokens":     "In Tok",
                "output_tokens":    "Out Tok",
                "ai_cost_usd":      "Cost ($)",
                "response_time_s":  "Time (s)",
                "accuracy_detail":  "Validator Detail",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # ── Accuracy heatmap ──────────────────────────────────────────────────
        st.subheader("Accuracy Heatmap — Score by Model × Prompt")
        pivot = df_raw.pivot_table(
            index="prompt_id", columns="model",
            values="accuracy_score", aggfunc="mean",
        )
        fig2, ax2 = plt.subplots(figsize=(max(8, len(pivot.columns) * 1.4), max(4, len(pivot) * 0.7)))
        im = ax2.imshow(pivot.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        ax2.set_xticks(range(len(pivot.columns)))
        ax2.set_xticklabels(pivot.columns, rotation=30, ha="right", fontsize=9)
        ax2.set_yticks(range(len(pivot.index)))
        ax2.set_yticklabels(pivot.index, fontsize=9)
        for r in range(len(pivot.index)):
            for c in range(len(pivot.columns)):
                val = pivot.values[r, c]
                if not np.isnan(val):
                    ax2.text(c, r, f"{val:.2f}", ha="center", va="center",
                             fontsize=8, color="black" if 0.3 < val < 0.85 else "white")
        plt.colorbar(im, ax=ax2, label="Accuracy Score")
        ax2.set_title(f"Accuracy by Prompt × Model — {uc}", fontsize=11, fontweight="bold")
        plt.tight_layout()
        st.pyplot(fig2, use_container_width=True)

        # ── Per-model bar charts ──────────────────────────────────────────────
        st.subheader("Model Comparison — Accuracy · Cost · Speed")
        if st.session_state.metrics:
            met = st.session_state.metrics
            rnk = st.session_state.ranked
            fig3, axes = plt.subplots(1, 3, figsize=(16, 5))
            fig3.suptitle(f"Model Comparison — {uc}", fontsize=12, fontweight="bold")
            colors = [PROVIDER_COLORS.get(met[m]["provider"], "#888") for m in rnk]
            x = range(len(rnk))
            for ax3, key, title, ylabel, fmt in [
                (axes[0], "avg_accuracy", "Avg Accuracy",    "Score 0-1", "{:.2f}"),
                (axes[1], "total_cost",   "Total AI Cost",   "USD",       "${:.5f}"),
                (axes[2], "avg_time_s",   "Avg Response Time","Seconds",  "{:.2f}s"),
            ]:
                vals = [met[m][key] for m in rnk]
                bars = ax3.bar(x, vals, color=colors)
                ax3.set_title(title, fontweight="bold")
                ax3.set_xticks(x)
                ax3.set_xticklabels(
                    [m.replace(" Instruct","").replace(" Maverick"," Mvk") for m in rnk],
                    rotation=30, ha="right", fontsize=8,
                )
                ax3.set_ylabel(ylabel, fontsize=9)
                for j, v in enumerate(vals):
                    ax3.text(j, v * 1.03, fmt.format(v), ha="center", fontsize=7.5)
                ax3.spines["top"].set_visible(False)
                ax3.spines["right"].set_visible(False)
            axes[0].set_ylim(0, 1.2)
            plt.tight_layout()
            st.pyplot(fig3, use_container_width=True)

        # ── Raw response inspector ────────────────────────────────────────────
        st.subheader("Inspect Raw Response")
        ic1, ic2 = st.columns(2)
        with ic1:
            inspect_model = st.selectbox("Model", sorted(df_raw["model"].unique()), key="ins_m")
        with ic2:
            inspect_prompt = st.selectbox("Prompt", sorted(df_raw["prompt_id"].unique()), key="ins_p")

        row = df_raw[
            (df_raw["model"] == inspect_model) & (df_raw["prompt_id"] == inspect_prompt)
        ]
        if not row.empty:
            r = row.iloc[0]
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Result",    r["accuracy_label"])
            rc2.metric("Score",     f"{r['accuracy_score']:.2f}")
            rc3.metric("Time",      f"{r['response_time_s']:.2f}s")
            rc4.metric("Cost",      f"${r['ai_cost_usd']:.6f}")
            st.text_area("Validator Detail", r["accuracy_detail"], height=40, disabled=True)
            st.text_area("Raw Response", r["response"], height=250, disabled=True)

        # ── Full raw results CSV ─────────────────────────────────────────────
        st.divider()
        raw_csv = df_raw.drop(columns=["response"]).to_csv(index=False).encode()
        st.download_button(
            "⬇ Full raw results CSV",
            data=raw_csv,
            file_name=f"llm_raw_{st.session_state.use_case_name.lower().replace(' ','_')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
