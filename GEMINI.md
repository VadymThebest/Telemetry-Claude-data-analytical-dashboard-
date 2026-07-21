# Claude Code Telemetry Analytics Platform - Agent Guidance

## Project Environment
- Database Path: `data/warehouse.db`
- Ingestion Pipeline: `python data_pipeline/ingest.py --raw-dir output/ --reset`
- Primary Stack: Python 3.10+, Streamlit, Plotly, Pandas, SQLite3

## System Directives & Architecture Rules
1. Always validate SQL queries against `data/warehouse.db` schema before generating application code[cite: 3].
2. Ensure all code is modular, well-commented, type-hinted, and includes error handling for empty DB queries or missing tables.
3. Dashboard components must load telemetry metrics dynamically from SQLite views and tables[cite: 3].
4. Modules (`analytics.py`, `ml_engine.py`) must handle missing/null values or empty database queries gracefully.
5. Keep data aggregation (`analytics.py`) and machine learning logic (`ml_engine.py`) separate from the UI layer (`app.py`).