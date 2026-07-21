"""
Unit tests for analytics.py and ml_engine.py.
Covers normal operation on real data, custom parameterization,
and graceful handling of missing or empty databases.
"""

from __future__ import annotations

import os
import unittest
import tempfile
import sqlite3
import pandas as pd

from analytics import (
    get_token_costs_by_practice,
    get_tool_decisions_by_tool,
    get_api_error_counts,
    get_session_durations,
)
from ml_engine import (
    detect_anomalies,
    forecast_token_costs,
)

REAL_DB_PATH = "data/warehouse.db"


class TestTelemetryAnalyticsAndML(unittest.TestCase):
    
    def setUp(self):
        # We will also create a temporary empty database path for testing empty/missing scenarios
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        
        # Non-existent DB path for testing completely missing DB
        self.non_existent_db_path = "data/non_existent_test_db_12345.db"
        if os.path.exists(self.non_existent_db_path):
            os.remove(self.non_existent_db_path)

    def tearDown(self):
        # Clean up temporary DB files
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except OSError:
                pass
        if os.path.exists(self.non_existent_db_path):
            try:
                os.remove(self.non_existent_db_path)
            except OSError:
                pass

    # ==========================================
    # 1. Tests on Real Database (Happy Path)
    # ==========================================

    def test_real_db_exists(self):
        """Verify that the real warehouse database exists before running tests on it."""
        self.assertTrue(
            os.path.exists(REAL_DB_PATH), 
            f"Real database not found at {REAL_DB_PATH}. Please make sure to run ingestion first."
        )

    def test_real_db_token_costs_by_practice(self):
        """Test get_token_costs_by_practice with real database."""
        df = get_token_costs_by_practice(REAL_DB_PATH)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty, "Dataframe should not be empty on real database")
        
        expected_cols = [
            "practice", "input_tokens", "output_tokens", 
            "cache_read_tokens", "cache_creation_tokens", "total_cost_usd"
        ]
        self.assertEqual(list(df.columns), expected_cols)
        self.assertTrue((df["total_cost_usd"] >= 0).all())

    def test_real_db_tool_decisions_by_tool(self):
        """Test get_tool_decisions_by_tool with real database."""
        df = get_tool_decisions_by_tool(REAL_DB_PATH)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty, "Dataframe should not be empty on real database")
        
        expected_cols = [
            "tool_name", "accept_count", "reject_count", 
            "total_decisions", "acceptance_rate", "rejection_rate"
        ]
        self.assertEqual(list(df.columns), expected_cols)
        
        # Rates should be between 0 and 1
        self.assertTrue(((df["acceptance_rate"] >= 0) & (df["acceptance_rate"] <= 1)).all())
        self.assertTrue(((df["rejection_rate"] >= 0) & (df["rejection_rate"] <= 1)).all())
        # accept + reject counts should sum to total
        self.assertTrue((df["accept_count"] + df["reject_count"] == df["total_decisions"]).all())

    def test_real_db_api_error_counts(self):
        """Test get_api_error_counts with various group_by on real database."""
        # Test default group_by ("model")
        df_model = get_api_error_counts(REAL_DB_PATH)
        self.assertIsInstance(df_model, pd.DataFrame)
        self.assertEqual(list(df_model.columns), ["model", "error_count"])
        self.assertFalse(df_model.empty)
        
        # Test group_by "practice" (which requires dim_employees join)
        df_practice = get_api_error_counts(REAL_DB_PATH, group_by="practice")
        self.assertIsInstance(df_practice, pd.DataFrame)
        self.assertEqual(list(df_practice.columns), ["practice", "error_count"])
        self.assertFalse(df_practice.empty)
        
        # Test invalid group_by
        with self.assertRaises(ValueError):
            get_api_error_counts(REAL_DB_PATH, group_by="invalid_field")

    def test_real_db_session_durations(self):
        """Test get_session_durations with real database."""
        df = get_session_durations(REAL_DB_PATH)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty, "Dataframe should not be empty on real database")
        
        expected_cols = ["session_id", "user_email", "duration_minutes", "event_count"]
        self.assertEqual(list(df.columns), expected_cols)
        self.assertTrue((df["duration_minutes"] >= 0).all())

    def test_real_db_anomaly_detection(self):
        """Test detect_anomalies with real database."""
        df = detect_anomalies(REAL_DB_PATH, contamination=0.03)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty, "Dataframe should not be empty on real database")
        
        expected_cols = [
            "event_id", "session_id", "user_email", "timestamp", "model",
            "input_tokens", "output_tokens", "cost_usd", "duration_ms",
            "anomaly_score", "is_anomaly"
        ]
        self.assertEqual(list(df.columns), expected_cols)
        
        # Check that we have exactly or approximately the expected contamination rate
        anomalies_count = df["is_anomaly"].sum()
        total_count = len(df)
        self.assertGreater(anomalies_count, 0)
        # Contamination rate should be close to 3%
        self.assertAlmostEqual(anomalies_count / total_count, 0.03, delta=0.01)

    def test_real_db_forecasting(self):
        """Test forecast_token_costs with real database."""
        forecast_days = 15
        df = forecast_token_costs(REAL_DB_PATH, forecast_days=forecast_days)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), forecast_days)
        self.assertEqual(list(df.columns), ["date", "forecasted_cost"])
        self.assertTrue((df["forecasted_cost"] >= 0).all())
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["date"]))

    # ==========================================
    # 2. Tests for Graceful Error Handling
    # ==========================================

    def test_missing_db_graceful_handling(self):
        """Test that all functions handle a completely missing database file gracefully."""
        # 1. analytics.py functions
        df_costs = get_token_costs_by_practice(self.non_existent_db_path)
        self.assertTrue(df_costs.empty)
        self.assertEqual(
            list(df_costs.columns), 
            ["practice", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "total_cost_usd"]
        )
        
        df_tools = get_tool_decisions_by_tool(self.non_existent_db_path)
        self.assertTrue(df_tools.empty)
        self.assertEqual(
            list(df_tools.columns), 
            ["tool_name", "accept_count", "reject_count", "total_decisions", "acceptance_rate", "rejection_rate"]
        )
        
        df_errors = get_api_error_counts(self.non_existent_db_path, group_by="status_code")
        self.assertTrue(df_errors.empty)
        self.assertEqual(list(df_errors.columns), ["status_code", "error_count"])
        
        df_sessions = get_session_durations(self.non_existent_db_path)
        self.assertTrue(df_sessions.empty)
        self.assertEqual(list(df_sessions.columns), ["session_id", "user_email", "duration_minutes", "event_count"])

        # 2. ml_engine.py functions
        df_anomalies = detect_anomalies(self.non_existent_db_path)
        self.assertTrue(df_anomalies.empty)
        self.assertEqual(
            list(df_anomalies.columns), 
            ["event_id", "session_id", "user_email", "timestamp", "model",
             "input_tokens", "output_tokens", "cost_usd", "duration_ms",
             "anomaly_score", "is_anomaly"]
        )
        
        df_forecast = forecast_token_costs(self.non_existent_db_path)
        self.assertTrue(df_forecast.empty)
        self.assertEqual(list(df_forecast.columns), ["date", "forecasted_cost"])

        # Crucially, check that calling these functions did NOT create an empty DB file
        self.assertFalse(os.path.exists(self.non_existent_db_path))

    def test_empty_db_graceful_handling(self):
        """Test that all functions handle an empty database file gracefully (tables missing)."""
        # Connect to create an empty DB with absolutely no tables
        with sqlite3.connect(self.temp_db_path) as conn:
            pass
            
        df_costs = get_token_costs_by_practice(self.temp_db_path)
        self.assertTrue(df_costs.empty)
        self.assertEqual(len(df_costs.columns), 6)
        
        df_tools = get_tool_decisions_by_tool(self.temp_db_path)
        self.assertTrue(df_tools.empty)
        self.assertEqual(len(df_tools.columns), 6)
        
        df_errors = get_api_error_counts(self.temp_db_path, group_by="model")
        self.assertTrue(df_errors.empty)
        self.assertEqual(len(df_errors.columns), 2)
        
        df_sessions = get_session_durations(self.temp_db_path)
        self.assertTrue(df_sessions.empty)
        self.assertEqual(len(df_sessions.columns), 4)
        
        df_anomalies = detect_anomalies(self.temp_db_path)
        self.assertTrue(df_anomalies.empty)
        self.assertEqual(len(df_anomalies.columns), 11)
        
        df_forecast = forecast_token_costs(self.temp_db_path)
        self.assertTrue(df_forecast.empty)
        self.assertEqual(len(df_forecast.columns), 2)


if __name__ == "__main__":
    unittest.main()
