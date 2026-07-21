"""
Streamlit dashboard for the Claude Code Telemetry Analytics Platform.
Visualizes telemetry analytics and ML models.
"""

import os
import pandas as pd
import plotly.express as px
import streamlit as st

import analytics
import ml_engine

# Page Configuration
st.set_page_config(page_title="Telemetry Analytics Dashboard", layout="wide")

# Database Path
DB_PATH = "data/warehouse.db"

# Data Loading
@st.cache_data(show_spinner=False)
def load_data():
    """Loads all required dataframes for the dashboard."""
    if not os.path.exists(DB_PATH):
        return None
    
    return {
        "costs": analytics.get_token_costs_by_practice(DB_PATH),
        "decisions": analytics.get_tool_decisions_by_tool(DB_PATH),
        "errors": analytics.get_api_error_counts(DB_PATH, group_by="model"),
        "sessions": analytics.get_session_durations(DB_PATH),
        "anomalies": ml_engine.detect_anomalies(DB_PATH),
        "forecast": ml_engine.forecast_token_costs(DB_PATH)
    }

# Check Database
if not os.path.exists(DB_PATH):
    st.error(f"Database file not found at '{DB_PATH}'. Please run the ingestion pipeline.")
    st.stop()

# Load data
data = load_data()

if data is None:
    st.error("Failed to load data.")
    st.stop()

# --- Sidebar ---
st.sidebar.title("Dashboard Controls")
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# --- Main Dashboard ---
st.title("Claude Code Telemetry Dashboard")

tab1, tab2, tab3 = st.tabs(["Overview", "Usage & Cost Breakdown", "Predictive & Anomaly Insights"])

# --- TAB 1: Overview ---
with tab1:
    st.header("Key Performance Indicators")
    col1, col2, col3, col4 = st.columns(4)

    # Calculate KPIs
    total_cost = data["costs"]["total_cost_usd"].sum() if not data["costs"].empty else 0
    total_errors = data["errors"]["error_count"].sum() if not data["errors"].empty else 0
    active_sessions = len(data["sessions"])

    # Tool Acceptance Rate calculation
    if not data["decisions"].empty and data["decisions"]["total_decisions"].sum() > 0:
        tool_acceptance_rate = data["decisions"]["accept_count"].sum() / data["decisions"]["total_decisions"].sum()
    else:
        tool_acceptance_rate = 0.0

    col1.metric("Total Cost (USD)", f"${total_cost:,.2f}")
    col2.metric("Tool Acceptance Rate", f"{tool_acceptance_rate:.2%}")
    col3.metric("Total Errors", f"{total_errors:,}")
    col4.metric("Active Sessions", f"{active_sessions:,}")

# --- TAB 2: Usage & Cost Breakdown ---
with tab2:
    st.header("Usage & Cost Breakdown")

    # Bar chart: Costs by practice
    if not data["costs"].empty:
        fig_costs = px.bar(data["costs"], x="practice", y="total_cost_usd", color_discrete_sequence=["#2222CC"], title="Token Cost by Practice")
        st.plotly_chart(fig_costs, width="stretch")
    else:
        st.warning("No token cost data available for breakdown.")

    # Bar chart: Tool decisions
    if not data["decisions"].empty:
        decisions_melted = data["decisions"].melt(
            id_vars="tool_name",
            value_vars=["accept_count", "reject_count"],
            var_name="Decision",
            value_name="Count"
        )
        fig_decisions = px.bar(decisions_melted, x="tool_name", y="Count", color="Decision", barmode="group", color_discrete_sequence=["#D31111", "#DAF413"], title="Tool Decisions")
        st.plotly_chart(fig_decisions, width="stretch")
    else:
        st.warning("No tool decision data available.")

# --- TAB 3: Predictive & Anomaly Insights ---
with tab3:
    st.header("Predictive & Anomaly Insights")

    # Line chart: Forecast
    if not data["forecast"].empty:
        fig_forecast = px.line(data["forecast"], x="date", y="forecasted_cost", color_discrete_sequence=["#00FF2F"], title="Forecasted Daily Token Costs")
        st.plotly_chart(fig_forecast, width="stretch")
    else:
        st.warning("Insufficient data for cost forecasting.")

    # Table: Anomalies
    if not data["anomalies"].empty:
        anomalies = data["anomalies"][data["anomalies"]["is_anomaly"]]
        if not anomalies.empty:
            st.subheader("Detected Anomalies")
            st.dataframe(anomalies, use_container_width=True)
        else:
            st.info("No anomalies detected in the current dataset.")
    else:
        st.warning("No anomaly data available.")