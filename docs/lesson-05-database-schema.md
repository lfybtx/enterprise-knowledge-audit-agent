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

下一小步才会引入 Repository，把上传后的 document 和 chunk 写入这些表。

## 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
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
