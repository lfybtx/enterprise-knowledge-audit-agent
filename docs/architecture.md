# Architecture

```mermaid
flowchart LR
    U["Business user"] --> W["Web UI"]
    W --> A["FastAPI API"]
    A --> R["Hybrid retriever<br/>BM25-like + cosine"]
    R --> K["Knowledge documents"]
    A --> G["Evidence-only answer generator"]
    A --> C["Policy conflict rules"]
    G --> O["Answer with citations"]
    C --> O
    A --> L["Audit log"]
```

## Request flow

1. The user submits a question in the web UI.
2. The API retrieves the highest-scoring knowledge documents.
3. The answer generator only selects sentences from retrieved evidence.
4. The audit rules detect sensitive data export, incident response, and legacy-policy conflicts.
5. The UI renders the answer, source excerpts, and risk findings.
