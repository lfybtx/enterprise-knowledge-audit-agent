# 企业知识库审计 Agent

这是一个面向合规、客服、售前、法务场景的企业知识库审计 Agent。用户上传制度、合同、产品资料后，系统不仅回答问题，还会返回证据引用、识别制度冲突、生成风险清单，并记录完整工作流 Trace。

![项目界面](docs/screenshot-placeholder.png)

## 项目定位

这个项目不是简单的“文档问答 Demo”，而是围绕企业 RAG 落地常见要求做的一套完整工程样例：

- 文档解析：支持 `.txt`、文本型 PDF、扫描 PDF OCR、`.docx`、`.xlsx`、网页 URL。
- RAG 检索：关键词检索 + pgvector 向量检索 + 融合排序 + 本地 reranker。
- 证据引用：保留页码、段落、行号、表格、Sheet、Row 等来源信息。
- 多 Agent 工作流：检索 Agent、审计 Agent、报告 Agent、人工确认节点。
- 结构化风险报告：风险等级、依据、建议动作、引用来源。
- 权限隔离：JWT 登录，知识库成员角色和文档级 ACL 会共同限制可见范围。
- 可观测性：记录 prompt、工具调用、耗时、token 估算、失败原因、LLM fallback。
- 可评测：内置 60 条评测用例和可复现评测结果。
- 可部署：FastAPI + PostgreSQL/pgvector + MinIO + Docker Compose 一键启动。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 API | Python, FastAPI |
| 数据库 | PostgreSQL 16, pgvector, SQLAlchemy, Alembic |
| 对象存储 | MinIO |
| Agent 编排 | LangGraph |
| 文档解析 | pypdf, pdf2image, Tesseract OCR, python-docx, openpyxl |
| Embedding | 本地 `BAAI/bge-small-zh-v1.5`，也支持 OpenAI-compatible embedding |
| Reranker | 本地 `BAAI/bge-reranker-base` |
| LLM | 本地规则 fallback，支持 DeepSeek / Ollama / LM Studio 等 OpenAI-compatible Chat API |
| 前端 | 原生 HTML/CSS/JavaScript |
| 部署 | Docker Compose |
| 测试 | pytest |

## 当前评测基线

| 指标 | 结果 |
| --- | --- |
| 评测用例数 | 60 |
| Recall@1 | 96.7% |
| Recall@3 | 100.0% |
| 引用准确率 | 96.7% |
| 回答质量通过率 | 100.0% |
| 风险类型准确率 | 90.0% |
| 冲突识别准确率 | 100.0% |
| 证据绑定准确率 | 100.0% |
| 审批触发准确率 | 100.0% |

详细报告：[docs/evaluation-report.md](docs/evaluation-report.md)

## Docker 一键启动

先复制环境变量文件：

```powershell
copy .env.example .env
```

启动服务：

```powershell
docker compose up -d --build
```

打开浏览器：

```text
http://127.0.0.1:8000
```

Docker Compose 会启动：

- `app`：FastAPI 应用，端口 `8000`
- `db`：PostgreSQL + pgvector，端口 `5432`
- `minio`：对象存储，端口 `9000/9001`

MinIO 控制台：

```text
http://127.0.0.1:9001
账号：minioadmin
密码：minioadmin
```

## 演示账号

| 用户 | 密码 | 角色 | 说明 |
| --- | --- | --- | --- |
| `alice` | `alice123456` | editor | 可上传、可审计、可审批自己的审计记录 |
| `bob` | `bob123456` | viewer | 只读用户，用来演示权限隔离 |
| Header 模式 | `X-User-Id: local-demo` | owner | 本地调试和默认演示用户 |

前端也保留了演示用户切换器，方便展示 Alice / Bob 权限差异。第十六阶段加入了知识库成员管理和文档级 ACL：owner 可以维护成员，editor 可以上传和检索，viewer 只能查看授权内容。

## DeepSeek 接入

默认模式不需要 API Key：embedding 和 reranker 使用本地开源模型，回答生成有规则 fallback。

如果要接入 DeepSeek，只修改 `.env`：

```env
MODEL_PROVIDER=local-hf
CHAT_PROVIDER=openai-compatible
CHAT_OPENAI_BASE_URL=https://api.deepseek.com
CHAT_OPENAI_API_KEY=your_deepseek_api_key
CHAT_OPENAI_MODEL=deepseek-chat
```

说明：

- 文档上传时会生成 embedding 并写入 pgvector。
- 提问时会生成 query embedding，用于向量检索。
- DeepSeek 只负责报告 Agent 的归纳表达。
- 如果 DeepSeek 不可用或返回格式不符合要求，系统会记录失败原因，并 fallback 到本地证据回答。

## 本地开源模型

Docker 构建后可以显式下载模型：

```powershell
docker compose run --rm app python scripts/download_local_model.py
```

模型会缓存到：

```text
data/models
```

该目录不应提交到 GitHub。

## 常用命令

运行测试：

```powershell
pytest
```

Docker 内运行测试：

```powershell
docker compose exec app pytest
```

运行评测：

```powershell
docker compose exec app python scripts/run_evaluation.py
```

重置演示数据，先 dry-run：

```powershell
docker compose exec app python scripts/reset_demo_data.py --all
```

真正执行重置：

```powershell
docker compose exec app python scripts/reset_demo_data.py --all --apply
```

检查数据库健康状态：

```powershell
docker compose exec app python scripts/check_database.py
```

## 当前项目状态

本项目当前适合用于功能演示和内测，核心审计、检索、权限、追踪、评测和导出能力已经具备。最近一次本地验证结果为：`80 passed, 8 skipped`，前端 JavaScript 语法检查通过。

正式部署前仍需完成 PostgreSQL、MinIO、Redis 集成验证，并处理生产密钥校验、文件上传限制、URL 导入 SSRF 防护和异步任务闭环等事项。详细状态和后续计划见：[项目状态与后续路线图](docs/project-status-and-roadmap.md)。

## 重要文档

- [架构说明](docs/architecture.md)
- [交付检查清单](docs/delivery-checklist.md)
- [项目状态与后续路线图](docs/project-status-and-roadmap.md)
- [评测报告](docs/evaluation-report.md)
- [测试数据说明](docs/test-data.md)
- [演示脚本](docs/demo-script.md)

## API 示例

登录：

```http
POST /api/auth/login
```

提问：

```http
POST /api/ask
Authorization: Bearer <token>
Content-Type: application/json

{
  "question": "销售是否可以直接导出完整客户名单？请说明风险和正确流程。"
}
```

上传文档：

```http
POST /api/documents/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

title: 文档标题
file: .txt / .pdf / .docx / .xlsx
```

查看系统诊断：

```http
GET /api/admin/system-status
Authorization: Bearer <token>
```

## 面试演示路径

推荐按这个顺序演示：

1. 打开首页，说明项目解决的是企业知识库审计，不只是问答。
2. 登录 Alice，查看已有知识库文档。
3. 提问“销售是否可以直接导出完整客户名单？”
4. 展示回答里的证据引用、风险发现和来源位置。
5. 查看工作流 Trace，说明检索、审计、报告和人工确认节点。
6. 上传一份和现有制度冲突的文档，再次提问，展示冲突识别。
7. 切换 Bob，演示 viewer 不能上传、不能查看系统诊断。
8. 导出 Markdown 或 PDF 报告。
9. 打开“系统状态与索引诊断”，展示工程可运维能力。
10. 展示评测结果和 GitHub 文档。

详细脚本：[docs/demo-script.md](docs/demo-script.md)

## 文档入口

- 架构说明：[docs/architecture.md](docs/architecture.md)
- 数据库指南：[docs/database-guide.md](docs/database-guide.md)
- 演示脚本：[docs/demo-script.md](docs/demo-script.md)
- 项目亮点与局限：[docs/project-highlights.md](docs/project-highlights.md)
- 测试数据说明：[docs/test-data.md](docs/test-data.md)
- 交付检查清单：[docs/delivery-checklist.md](docs/delivery-checklist.md)

## 学习笔记

- [第 01 课：FastAPI 最小服务](docs/lesson-01-setup.md)
- [第 02 课：上传接口](docs/lesson-02-upload.md)
- [第 03 课：PDF、Word、Excel 解析](docs/lesson-03-parsers.md)
- [第 04 课：切片与引用](docs/lesson-04-chunked-citations.md)
- [第 05 课：数据库模型](docs/lesson-05-database-schema.md)
- [第 06 课：向量检索](docs/lesson-06-vector-search.md)
- [第 07 课：工作流报告](docs/lesson-07-workflow-report.md)
- [第 08 课：报告导出](docs/lesson-08-report-export.md)
- [第 09 课：权限模型](docs/lesson-09-permission-schema.md)
- [第 10 课：鉴权隔离](docs/lesson-10-auth-isolation.md)
- [第 11 课：用户切换器](docs/lesson-11-user-switcher.md)
- [第 12 课：可观测性](docs/lesson-12-observability.md)
- [第 13 课：Trace 持久化](docs/lesson-13-trace-persistence.md)
- [第 14 课：审计历史](docs/lesson-14-audit-history.md)
- [第 15 课：评测体系](docs/lesson-15-evaluation.md)

## 后续优化

- 接入更强的中文 reranker，并对 TopK 和融合权重做离线调参。
- 为 OCR 增加页面质量诊断、版面分析和表格还原。
- 引入更严格的 JSON Schema 约束和 LLM-as-judge 评测。
- 增加多租户管理后台和更细粒度的文档 ACL。
- 录制完整演示视频，补充真实浏览器截图。
