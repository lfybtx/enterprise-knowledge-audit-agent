import httpx
import pytest

from app.services.audit import AuditFinding
from app.services.llm_synthesis import LlmSynthesisError, synthesize_answer
from app.services.retrieval import RetrievedChunk
from app.services.workflow import run_audit_workflow


def evidence_chunk():
    return RetrievedChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        title="Export policy",
        source="policy.txt",
        text="Customer export requires manager approval.",
        location={"kind": "document"},
        score=0.91,
    )


def finding():
    return AuditFinding(
        level="High",
        title="Customer export approval",
        rationale="Approval is required by policy.",
        recommendation="Require manager approval before export.",
        evidence_ids=["doc-1"],
    )


def test_local_provider_skips_remote_synthesis(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "local-hf")

    result = synthesize_answer(question="Can I export customers?", evidence=[evidence_chunk()], findings=[finding()])

    assert result is None


def test_openai_compatible_synthesis_parses_strict_json(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "test-chat")

    def fake_post(url, headers, json, timeout):
        assert url == "http://llm.local/v1/chat/completions"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"Export requires manager approval [Evidence 1].","citations":[{"document_id":"doc-1","evidence_index":1}],"risk_summary":"approval required"}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 101, "completion_tokens": 25},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.llm_synthesis.httpx.post", fake_post)

    result = synthesize_answer(question="Can I export customers?", evidence=[evidence_chunk()], findings=[finding()])

    assert result is not None
    assert result.answer.startswith("Export requires manager approval")
    assert result.input_tokens == 101
    assert result.output_tokens == 25
    assert result.trace_data["answer_source"] == "openai_compatible_chat"


def test_openai_compatible_synthesis_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_post(url, headers, json, timeout):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.llm_synthesis.httpx.post", fake_post)

    with pytest.raises(LlmSynthesisError, match="valid JSON"):
        synthesize_answer(question="Can I export customers?", evidence=[evidence_chunk()], findings=[finding()])


def test_workflow_falls_back_when_remote_synthesis_fails(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_post(url, headers, json, timeout):
        raise httpx.ConnectError("offline", request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.llm_synthesis.httpx.post", fake_post)

    response = run_audit_workflow("Can I export customers?", lambda _: [evidence_chunk()])

    assert "manager approval" in response["answer"].lower()
    report_trace = next(step for step in response["workflow_trace"] if step["name"] == "report_agent")
    assert report_trace["trace_data"]["llm"]["status"] == "fallback"
