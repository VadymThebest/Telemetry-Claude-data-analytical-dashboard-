---
name: telemetry-analytics
description: Database schema knowledge, SQL query patterns, and analytical metrics for the Claude Code usage telemetry platform.
---

# Telemetry Schema Reference

The SQLite warehouse (`data/warehouse.db`) contains 5 event tables and 1 rollup view[cite: 3]:

### Tables & Key Fields
- `dim_employees`: `email` (PK), `full_name`, `practice`, `level`, `location`[cite: 3].
- `event_user_prompts`: `event_id` (PK), `session_id`, `user_email` (FK), `timestamp`, `prompt_length`[cite: 3].
- `event_api_requests`: `event_id` (PK), `session_id`, `user_email` (FK), `timestamp`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, `duration_ms`[cite: 3].
- `event_tool_decisions`: `event_id` (PK), `session_id`, `user_email` (FK), `timestamp`, `tool_name`, `decision` ('accept'|'reject'), `source`[cite: 3].
- `event_tool_results`: `event_id` (PK), `session_id`, `user_email` (FK), `timestamp`, `tool_name`, `success` (0/1), `duration_ms`, `tool_result_size_bytes`[cite: 3].
- `event_api_errors`: `event_id` (PK), `session_id`, `user_email` (FK), `timestamp`, `error_message`, `status_code`, `model`, `duration_ms`, `attempt`[cite: 3].

### Rollup View
- `session_summary`: `session_id`, `user_email`, `start_time`, `end_time`, `event_count`, `duration_minutes`[cite: 3].

---

# Analytical Query Reference

### 1. Cost & Token Usage by Practice
```sql
SELECT 
    e.practice,
    COUNT(DISTINCT r.session_id) as total_sessions,
    SUM(r.input_tokens) as total_input_tokens,
    SUM(r.output_tokens) as total_output_tokens,
    ROUND(SUM(r.cost_usd), 4) as total_cost_usd
FROM event_api_requests r
JOIN dim_employees e ON r.user_email = e.email
GROUP BY e.practice
ORDER BY total_cost_usd DESC;
```
### 2. Tool Acceptance vs. Rejection Rates
```sql
SELECT 
    tool_name,
    COUNT(*) as total_decisions,
    SUM(CASE WHEN decision = 'accept' THEN 1 ELSE 0 END) as accepted_count,
    SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) as rejected_count,
    ROUND(CAST(SUM(CASE WHEN decision = 'accept' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*), 4) as acceptance_rate
FROM event_tool_decisions
GROUP BY tool_name
ORDER BY total_decisions DESC;
```
### 3. API Errors Breakdown
```sql
SELECT 
    model,
    status_code,
    error_message,
    COUNT(*) as error_count,
    AVG(attempt) as avg_attempts
FROM event_api_errors
GROUP BY model, status_code, error_message
ORDER BY error_count DESC;
```
### 4. Session Duration & Event Summary
```sql  
SELECT 
    s.session_id,
    s.user_email,
    e.practice,
    s.duration_minutes,
    s.event_count
FROM session_summary s
JOIN dim_employees e ON s.user_email = e.email
WHERE s.duration_minutes > 0;
```
