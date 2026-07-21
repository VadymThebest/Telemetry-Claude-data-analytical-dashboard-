# 🚀 Claude Code Telemetry Analytics Dashboard

An operational telemetry dashboard and predictive engine built with Python, SQLite, and Streamlit. This application ingests Claude Code telemetry logs, applies statistical aggregations and machine learning models, and visualizes insights in an interactive dashboard.

---

## 🛠️ Machine Learning & Analytics Engine

The platform features two distinct data-processing engines:

### 📊 Analytics Engine (`analytics.py`)
- **Token Cost by Practice:** Calculates aggregated USD costs categorized by software engineering domains (ML, Frontend, Backend, Data, Platform).
- **Tool Decision Breakdown:** Computes overall acceptance vs. rejection ratios across Claude Code tool executions (e.g., `Read`, `Bash`, `Edit`, `Grep`).
- **Usage Metrics:** Summarizes total tokens, active developer sessions, and cost distributions.

### 🤖 Machine Learning Engine (`ml_engine.py`)
- **Linear Regression (Cost Forecasting):** Fits historical daily token usage to predict future daily expenditure trends.
- **IsolationForest (Anomaly Detection):** Evaluates multi-dimensional session data (token volume, execution latency, tool usage) to identify cost spikes and unusual prompt sessions.

---

## 📁 Repository Structure

```text
├── .gemini/
│   └── skills/
│       └── telemetry-analytics
├           └── SKILL.md     # Project skill definitions & workflow rules
├── __pycache__/             # Python bytecode cache (ignored by git)
├── data/
│   └── warehouse.db         # SQLite telemetry data warehouse
├── data_pipeline/
│   ├── ingest.py            # Data ingestion pipeline
│   └── schema.sql           # Database table schemas & structure
├── .env.example             # Template for environment configuration
├── .gitignore               # Git ignore file for cache & system files
├── analytics.py             # SQL aggregation & statistical querying module
├── app.py                   # Interactive Streamlit dashboard UI
├── GEMINI.md                # Agent instructions and context guidelines
├── ml_engine.py             # Machine learning models (Linear Regression & IsolationForest)
├── Readme.Md                # Project documentation
├── run.py                   # Master entry point script
└── test_analytics_and_ml.py # Automated test runner for analytics & ML models

