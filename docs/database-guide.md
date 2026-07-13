# 数据库查看与运维指南

这一页用于第十三阶段：让数据库里的文档、切片、权限、审计轨迹可以被直接查看和排查。适合用 Navicat、DBeaver、pgAdmin 或 Docker 内置的 `psql`。

## 连接信息

本地 Docker Compose 默认暴露 PostgreSQL 到宿主机 `5432` 端口。

| 配置项 | 值 |
| --- | --- |
| 数据库类型 | PostgreSQL |
| Host | `127.0.0.1` |
| Port | `5432` |
| User | `audit_app` |
| Password | `audit_app_dev` |
| Database | `enterprise_audit` |

如果 Navicat 报 `column "datlastsysoid" does not exist`，说明 Navicat 版本太旧，不兼容当前 PostgreSQL 16 的系统表。升级 Navicat，或临时使用 DBeaver / pgAdmin。

## 命令行验证

在项目根目录执行：

```powershell
docker compose ps
docker compose exec db psql -U audit_app -d enterprise_audit
```

进入 `psql` 后执行：

```sql
select id, title, file_type, status, created_at
from documents
order by created_at desc
limit 10;
```

也可以直接运行健康检查脚本：

```powershell
docker compose exec app python scripts/check_database.py
```

本机虚拟环境运行时，需要把 `DATABASE_URL` 指向宿主机端口：

```powershell
$env:DATABASE_URL="postgresql+psycopg://audit_app:audit_app_dev@127.0.0.1:5432/enterprise_audit"
.\.venv\Scripts\python.exe scripts\check_database.py
```

## 核心表说明

| 表名 | 作用 | 重点字段 |
| --- | --- | --- |
| `users` | 演示用户 | `external_id`, `display_name` |
| `knowledge_bases` | 知识库 | `name`, `owner_id` |
| `knowledge_base_members` | 用户和知识库角色关系 | `role`: `owner/editor/viewer` |
| `documents` | 文档元数据和全文 | `title`, `source`, `file_type`, `content`, `status` |
| `document_chunks` | 文档切片和向量 | `chunk_index`, `text`, `location`, `embedding` |
| `workflow_runs` | 审计/问答历史 | `trace_id`, `question`, `approval_status`, `summary` |
| `workflow_trace_steps` | 每一步 Agent trace | `name`, `prompt`, `tool_calls`, `duration_ms`, `trace_data` |
| `alembic_version` | 数据库迁移版本 | `version_num` |

## 常用排查路径

1. 上传后看不到文档：
   - 查 `documents` 是否有新记录。
   - 查 `document_chunks` 是否生成切片。
   - 查 `knowledge_base_members` 确认当前用户是否有这个知识库权限。

2. 检索不到证据：
   - 查 `document_chunks.embedding is not null` 的数量。
   - 用 `scripts/sql/02_documents_and_chunks.sql` 看每个文档的切片数。
   - 重新上传或执行后端补向量逻辑。

3. 查看一次审计执行过程：
   - 先在 `workflow_runs` 找到 `trace_id`。
   - 把 `trace_id` 填入 `scripts/sql/04_trace_detail_by_trace_id.sql` 里的参数位置。

4. 审批没有出现：
   - 查 `workflow_runs.approval_status`。
   - `pending` 表示需要审批，`not_required` 表示规则判断不需要人工审批。

## SQL 脚本目录

常用 SQL 放在 `scripts/sql/`：

| 文件 | 用途 |
| --- | --- |
| `01_database_overview.sql` | 总览扩展、迁移版本、表数据量 |
| `02_documents_and_chunks.sql` | 查看文档、切片数、向量写入情况 |
| `03_recent_audit_runs.sql` | 查看最近审计记录 |
| `04_trace_detail_by_trace_id.sql` | 按 trace_id 查看 Agent 执行步骤 |
| `05_user_permissions.sql` | 查看用户、知识库、角色 |
| `06_duplicate_documents.sql` | 找可能重复上传的文档 |
| `07_clear_audit_history.sql` | 清空审计历史，默认注释，需要手动放开 |

