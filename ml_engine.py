"""
Machine Learning Engine for the Claude Code Telemetry Analytics Platform.
Provides functions for anomaly detection and trend-based forecasting.
"""

from __future__ import annotations

import os
import sqlite3
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression


def detect_anomalies(
    db_path: str = "data/warehouse.db", 
    contamination: float = 0.05, 
    random_state: int = 42
) -> pd.DataFrame:
    """
    Identifies anomalies in event_api_requests using IsolationForest based on
    token usage (input and output tokens), cost, and duration.
    
    Args:
        db_path: Path to the SQLite warehouse database.
        contamination: The proportion of outliers in the data set (IsolationForest hyperparameter).
        random_state: Random seed for reproducibility.
        
    Returns:
        pd.DataFrame: A DataFrame of API requests with additional columns:
            - anomaly_score: Raw anomaly score (lower means more anomalous)
            - is_anomaly: Boolean flag indicating if the row is classified as an anomaly
    """
    expected_columns = [
        "event_id", "session_id", "user_email", "timestamp", "model",
        "input_tokens", "output_tokens", "cost_usd", "duration_ms",
        "anomaly_score", "is_anomaly"
    ]
    
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=expected_columns)
        
    query = """
        SELECT 
            event_id,
            session_id,
            user_email,
            timestamp,
            model,
            input_tokens,
            output_tokens,
            cost_usd,
            duration_ms
        FROM event_api_requests;
    """
    
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(query, conn)
            
        if df.empty:
            return pd.DataFrame(columns=expected_columns)
            
        # IsolationForest requires at least a small number of samples to fit.
        # If there is too little data, we return the data with default anomaly indicators.
        if len(df) < 5:
            df["anomaly_score"] = 0.0
            df["is_anomaly"] = False
            return df[expected_columns]
            
        # Select features for anomaly detection
        features = df[["input_tokens", "output_tokens", "cost_usd", "duration_ms"]].fillna(0)
        
        # Train IsolationForest
        clf = IsolationForest(contamination=contamination, random_state=random_state)
        preds = clf.fit_predict(features)
        scores = clf.decision_function(features)
        
        df["anomaly_score"] = scores
        # IsolationForest predicts -1 for anomalies, 1 for inliers
        df["is_anomaly"] = preds == -1
        
        return df
        
    except Exception:
        return pd.DataFrame(columns=expected_columns)


def forecast_token_costs(
    db_path: str = "data/warehouse.db", 
    forecast_days: int = 30
) -> pd.DataFrame:
    """
    Generates a basic trend-based linear forecasting for future daily token costs.
    
    Args:
        db_path: Path to the SQLite warehouse database.
        forecast_days: Number of days in the future to estimate.
        
    Returns:
        pd.DataFrame: A DataFrame with columns:
            - date: Estimated future dates
            - forecasted_cost: Predicted cost in USD for each day
    """
    expected_columns = ["date", "forecasted_cost"]
    
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=expected_columns)
        
    query = """
        SELECT 
            SUBSTR(timestamp, 1, 10) as date_str,
            SUM(cost_usd) as daily_cost
        FROM event_api_requests
        GROUP BY date_str
        ORDER BY date_str ASC;
    """
    
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(query, conn)
            
        if df.empty or len(df) < 2:
            return pd.DataFrame(columns=expected_columns)
            
        # Parse dates and compute numeric day index
        df["date"] = pd.to_datetime(df["date_str"])
        start_date = df["date"].min()
        df["days_since_start"] = (df["date"] - start_date).dt.days
        
        # Fit LinearRegression trend
        X = df[["days_since_start"]].values
        y = df["daily_cost"].values
        
        model = LinearRegression()
        model.fit(X, y)
        
        # Predict future daily costs
        last_date = df["date"].max()
        future_dates = [last_date + pd.Timedelta(days=i) for i in range(1, forecast_days + 1)]
        future_days_since_start = [(d - start_date).days for d in future_dates]
        
        X_future = np.array(future_days_since_start).reshape(-1, 1)
        predictions = model.predict(X_future)
        
        # Cost cannot be negative, so we clip predictions at 0
        predictions = np.clip(predictions, a_min=0, a_max=None)
        
        forecast_df = pd.DataFrame({
            "date": future_dates,
            "forecasted_cost": predictions
        })
        
        return forecast_df
        
    except Exception:
        return pd.DataFrame(columns=expected_columns)
