-- Replace the value below with a trace_id from workflow_runs.

select
    wr.trace_id,
    wr.question,
    wr.approval_status,
    wr.review_decision,
    s.step_index,
    s.name,
    s.status,
    s.duration_ms,
    s.input_tokens,
    s.output_tokens,
    s.tool_calls,
    s.failure_reason,
    s.prompt,
    s.detail,
    s.trace_data
from workflow_runs wr
join workflow_trace_steps s on s.workflow_run_id = wr.id
where wr.trace_id = 'replace-with-trace-id'
order by s.step_index;

