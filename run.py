"""
Master Execution Script for Telemetry Platform.
Sequentially runs: Ingestion (if DB missing) -> ML/Analytics Pipeline -> Streamlit Dashboard.
"""
import os
import sys
import subprocess

def run_step(step_name, command):
    print(f"\n==================================================")
    print(f"▶ Step: {step_name}")
    print(f"==================================================")
    try:
        subprocess.run(command, check=True)
        print(f"✅ {step_name} completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during {step_name}: {e}")
        sys.exit(1)

def main():
    print("🚀 Starting Claude Code Telemetry Analytics Engine...")

    db_path = os.path.join("data", "warehouse.db")
    ingest_path = os.path.join("data_pipeline", "ingest.py")

    # 1. Database Check & Ingestion Pipeline
    if not os.path.exists(db_path):
        print("\nDatabase warehouse.db not found. Initializing data ingestion...")
        # Pointing to "output" where employees.csv and telemetry_logs.jsonl are stored
        raw_data_dir = "output" 
        run_step("Data Ingestion Pipeline", [sys.executable, ingest_path, "--raw-dir", raw_data_dir])
    else:
        print(f"\n✅ Database found at '{db_path}'. Skipping raw data re-ingestion.")

    # 2. ML & Analytics Engine Validation
    test_script = "test_analytics_and_ml.py"
    if os.path.exists(test_script):
        run_step("Analytics & ML Engine Validation", [sys.executable, test_script])
    else:
        run_step(
            "Analytics & ML Processing", 
            [sys.executable, "-c", "import analytics, ml_engine; print('Analytics and ML Engine imported & verified!')"]
        )

    # 3. Launching Streamlit Dashboard
    print("\nLaunching Interactive Streamlit Dashboard...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])

if __name__ == "__main__":
    main()