# Lesson 05: 数据库模型与初始迁移

本小步不替换现有 JSON 入库逻辑，只建立未来持久化所需的数据库契约。

## 三张核心表

```text
knowledge_bases
  1 -> N documents
  documents
    1 -> N document_chunks
```

| 表 | 用途 |
| --- | --- |
| `knowledge_bases` | 一个独立知识库，后续权限隔离会以它为边界 |
| `documents` | 上传文件的标题、来源、类型、完整解析文本和状态 |
| `document_chunks` | 实际检索单元，保存正文和页码/表格/工作表定位 |

## 为什么先建模型，不立刻改 API

当前上传和检索流程仍在内存和 JSON 中运行。先把 ORM 模型和 Alembic 迁移独立完成，可以分别验证：

1. Python 对象和数据库表是否一致；
2. 数据库能否升级；
3. 旧功能是否保持可用。

## Repository 持久化

Repository 已经把 `KnowledgeDocument` 和 `DocumentChunk` 的写入集中在
`app/repositories/knowledge_repository.py` 中。上传接口会优先使用 PostgreSQL：

1. 创建或复用 `Local demo knowledge base`；
2. 保存文件解析后的完整文本到 `documents`；
3. 保存每一个可检索分块和来源位置到 `document_chunks`；
4. 重启应用时，从 PostgreSQL 重新载入已上传的文档与分块。

当你直接在宿主机用 Uvicorn 启动，而 `.env` 中的 `db:5432` 无法访问时，应用会继续使用
`data/runtime/documents.json` 作为本地回退，不会影响前面阶段的学习和验收。

在 Docker Compose 中启动时，数据库可用，上传数据只会写入 PostgreSQL，因此容器重启后仍可检索。

## 持久化验收

确认迁移完成后，执行：

```powershell
docker compose run --rm app pytest -q
```

这会额外运行 `tests/test_postgres_persistence.py`：写入一份临时文档、重新查询其分块与定位信息。

## 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

普通本地页面调试、上传解析、报告导出不需要数据库依赖。如果要在宿主机直接执行 Alembic 或连接 PostgreSQL，再安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-db.txt
```

## 执行迁移

数据库容器启动后，执行：

```powershell
docker compose build app
docker compose run --rm app alembic upgrade head
```

这里在 `app` 容器内执行迁移，因此 `DATABASE_URL` 中的 `db:5432` 可以正确连接到 Compose 网络中的 PostgreSQL 服务。

## 验收 SQL

```powershell
docker compose exec db psql -U audit_app -d enterprise_audit -c "\dt"
```

应能看到：

```text
knowledge_bases
documents
document_chunks
alembic_version
```
