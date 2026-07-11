# Enterprise Knowledge Audit Agent

一个面向企业制度、合同、销售规范等非结构化文档的可审计知识库 Agent。它不只回答问题，还会给出证据引用、风险发现和整改建议。

![Project interface](docs/screenshot-placeholder.png)

> 截图在完成本地运行后生成。该项目可在没有 API Key 的情况下运行：默认使用本地混合检索和基于证据的回答，避免把无依据内容包装成结论。

## Why this project

- **Grounded answers**: every answer is derived from retrieved source sentences.
- **Audit layer**: detects risky data export requests and historical-policy conflicts.
- **Evaluation**: includes a reproducible Recall@1 dataset and script.
- **Deployable**: exposes a web UI and JSON API, with Docker Compose configuration.

## Features

| Capability | Implementation |
| --- | --- |
| Hybrid retrieval | BM25-like lexical score + cosine score over local terms |
| Citation | Source title, path, excerpt, and retrieval score |
| Risk audit | Data export, incident response, and legacy-document conflict rules |
| Evaluation | Four labeled retrieval test cases and a runnable evaluator |
| Audit trail | In-memory request/ingestion event log |
| Upload | `.txt` upload, parsing, local file storage, and immediate indexing |
| Deployment | Dockerfile and Docker Compose |

## Run locally

Requires Python 3.9+.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

> Windows 新手环境说明：这里使用普通 `uvicorn`，不使用 `uvicorn[standard]`，避免在 32 位 Python 或未安装 C++ Build Tools 的机器上编译 `httptools` 失败。

## Run with Docker

```bash
copy .env.example .env
docker compose up --build
```

## Test and evaluate

```bash
pytest
python scripts/run_evaluation.py
```

The included baseline is designed to reach 100% Recall@1 on the four sample cases. Expand `data/evaluation_cases.json` before presenting the project to employers, and report the real result.

## API

### Ask a question

```bash
curl -X POST http://127.0.0.1:8000/api/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"销售是否可以直接导出完整客户名单？\"}"
```

### Ingest a document

```bash
curl -X POST http://127.0.0.1:8000/api/documents ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"示例制度\",\"source\":\"demo.pdf\",\"content\":\"这是一份至少二十字的示例制度文本，用于验证新文档可以被索引和检索。\"}"
```

### Upload a txt document

Use the homepage upload form, or send multipart form data to:

```http
POST /api/documents/upload
```

Fields:

- `title`: document title
- `file`: `.txt` file

## Architecture

See [docs/architecture.md](docs/architecture.md).

## Lessons

- [Lesson 01: FastAPI 最小项目](docs/lesson-01-setup.md)
- [Lesson 02: 文档上传与解析](docs/lesson-02-upload.md)

## Demo script

1. Start with: `销售是否可以直接导出完整客户名单？`
2. Show the answer, evidence citations, and “客户数据导出需要审批” risk finding.
3. Click “加载冲突案例”.
4. Explain that the Agent finds the 2019 historical guide, compares it with current controls, and outputs a remediation recommendation.
5. Run `python scripts/run_evaluation.py`.

## Roadmap

- Replace local token vectors with embedding + pgvector/Qdrant.
- Add authenticated tenant isolation and persistent audit logs.
- Add document parsing for PDF, Word, Excel, and HTML.
- Add LLM synthesis with strict JSON schema validation and LLM-as-judge evaluation.
