"""
Analytics module for the Claude Code Telemetry Analytics Platform.
Provides functions to retrieve and aggregate metrics from the SQLite warehouse database.
"""

from __future__ import annotations

import os
import sqlite3
import pandas as pd


def _run_query(db_path: str, query: str, expected_columns: list[str], params: tuple = ()) -> pd.DataFrame:
    """
    Helper function to run an SQL query against the SQLite database and return a Pandas DataFrame.
    Gracefully handles empty queries, missing tables, or other database-related errors.
    """
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=expected_columns)
        
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)
            if df.empty:
                return pd.DataFrame(columns=expected_columns)
            return df
    except Exception:
        # Gracefully handle any SQLite, connection, or Pandas database errors by returning an empty DataFrame with expected columns
        return pd.DataFrame(columns=expected_columns)


def get_token_costs_by_practice(db_path: str = "data/warehouse.db") -> pd.DataFrame:
    """
    Calculates token usage and costs grouped by engineering practice.
    
    Returns:
        pd.DataFrame: A DataFrame with columns:
            - practice: The engineering practice name
            - input_tokens: Total input tokens
            - output_tokens: Total output tokens
            - cache_read_tokens: Total cache read tokens
            - cache_creation_tokens: Total cache creation tokens
            - total_cost_usd: Total token costs in USD
    """
    query = """
        SELECT 
            e.practice as practice,
            COALESCE(SUM(r.input_tokens), 0) as input_tokens,
            COALESCE(SUM(r.output_tokens), 0) as output_tokens,
            COALESCE(SUM(r.cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(r.cache_creation_tokens), 0) as cache_creation_tokens,
            COALESCE(SUM(r.cost_usd), 0.0) as total_cost_usd
        FROM event_api_requests r
        JOIN dim_employees e ON r.user_email = e.email
        GROUP BY e.practice
        ORDER BY total_cost_usd DESC;
    """
    expected_columns = [
        "practice", "input_tokens", "output_tokens", 
        "cache_read_tokens", "cache_creation_tokens", "total_cost_usd"
    ]
    return _run_query(db_path, query, expected_columns)


def get_tool_decisions_by_tool(db_path: str = "data/warehouse.db") -> pd.DataFrame:
    """
    Calculates tool decision acceptances, rejections, and rates grouped by tool name.
    
    Returns:
        pd.DataFrame: A DataFrame with columns:
            - tool_name: The name of the tool
            - accept_count: Number of accept decisions
            - reject_count: Number of reject decisions
            - total_decisions: Total number of decisions for this tool
            - acceptance_rate: Ratio of acceptances to total decisions
            - rejection_rate: Ratio of rejections to total decisions
    """
    query = """
        SELECT
            tool_name,
            SUM(CASE WHEN decision = 'accept' THEN 1 ELSE 0 END) as accept_count,
            SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) as reject_count,
            COUNT(*) as total_decisions,
            ROUND(CAST(SUM(CASE WHEN decision = 'accept' THEN 1 ELSE 0 END) AS REAL) / COUNT(*), 4) as acceptance_rate,
            ROUND(CAST(SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) AS REAL) / COUNT(*), 4) as rejection_rate
        FROM event_tool_decisions
        GROUP BY tool_name
        ORDER BY total_decisions DESC;
    """
    expected_columns = [
        "tool_name", "accept_count", "reject_count", 
        "total_decisions", "acceptance_rate", "rejection_rate"
    ]
    return _run_query(db_path, query, expected_columns)


def get_api_error_counts(db_path: str = "data/warehouse.db", group_by: str = "model") -> pd.DataFrame:
    """
    Calculates API error counts grouped by a specified attribute.
    
    Args:
        db_path: Path to the SQLite warehouse database.
        group_by: Attribute to group the error counts by. Must be one of:
                  'model', 'error_message', 'status_code', 'practice'.
                  
    Returns:
        pd.DataFrame: A DataFrame containing the grouping column and 'error_count'.
    """
    valid_group_bys = ["model", "error_message", "status_code", "practice"]
    if group_by not in valid_group_bys:
        raise ValueError(f"Invalid group_by parameter. Must be one of {valid_group_bys}")
        
    if group_by == "practice":
        query = """
            SELECT e.practice as practice, COUNT(*) as error_count
            FROM event_api_errors err
            JOIN dim_employees e ON err.user_email = e.email
            GROUP BY e.practice
            ORDER BY error_count DESC;
        """
    else:
        # group_by is safe to interpolate here as we verified it is in a hardcoded whitelist
        query = f"""
            SELECT {group_by}, COUNT(*) as error_count
            FROM event_api_errors
            GROUP BY {group_by}
            ORDER BY error_count DESC;
        """
        
    expected_columns = [group_by, "error_count"]
    return _run_query(db_path, query, expected_columns)


def get_session_durations(db_path: str = "data/warehouse.db") -> pd.DataFrame:
    """
    Retrieves the raw session durations and event counts from the session_summary view.
    This provides the complete distribution of session lengths for analytical mapping.
    
    Returns:
        pd.DataFrame: A DataFrame with columns:
            - session_id: Unique session identifier
            - user_email: Email of the user associated with the session
            - duration_minutes: Total session duration in minutes
            - event_count: Total event count in the session
    """
    query = """
        SELECT 
            session_id,
            user_email,
            duration_minutes,
            event_count
        FROM session_summary
        ORDER BY duration_minutes DESC;
    """
    expected_columns = ["session_id", "user_email", "duration_minutes", "event_count"]
    return _run_query(db_path, query, expected_columns)
