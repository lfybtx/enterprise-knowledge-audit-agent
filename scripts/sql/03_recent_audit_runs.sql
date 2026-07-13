-- Recent audit/question runs.

select
    trace_id,
    user_id,
    event_type,
    status,
    approval_status,
    review_decision,
    duration_ms,
    step_count,
    left(question, 120) as question_preview,
    left(summary, 160) as summary_preview,
    created_at
from workflow_runs
order by created_at desc
limit 50;

