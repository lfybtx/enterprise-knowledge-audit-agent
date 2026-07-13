# 测试数据说明

本项目包含三类测试数据：演示上传文档、评测用例、评测结果。

## 1. 演示上传文档

目录：

```text
data/test_uploads
```

当前包含：

| 文件 | 用途 |
| --- | --- |
| `access-control-policy.txt` | 访问控制和跨部门权限问题 |
| `approval-matrix.txt` | 审批矩阵 |
| `contract-sla-terms.txt` | 合同和 SLA 风险 |
| `current-export-policy.txt` | 当前客户数据导出制度 |
| `incident-response-policy.txt` | 数据泄露和异常访问响应 |
| `legacy-export-guide.txt` | 旧版导出工具规范，用于制造冲突 |
| `public-faq.txt` | 公开 FAQ，用于低风险问题 |
| `sensitive-data-handling.txt` | 敏感数据处理规范 |

这些文档用于演示：

- 风险识别。
- 旧制度和新制度冲突。
- 审批要求。
- 敏感信息外发限制。
- 事故响应流程。

## 2. PDF / Word / Excel 样例

目录：

```text
data/sample_uploads
```

包含：

| 文件 | 用途 |
| --- | --- |
| `客户数据导出管理规范.pdf` | 测试 PDF 解析和页码引用 |
| `客户数据导出补充规范.docx` | 测试 Word 段落解析 |
| `客户数据导出审批清单.xlsx` | 测试 Excel Sheet / Row 引用 |

可以在前端上传这三份文件，验证多格式解析能力。

## 3. 评测用例

文件：

```text
data/evaluation_cases.json
```

当前包含 60 条用例。每条用例通常包括：

- 问题。
- 期望命中的文档。
- 期望风险类型。
- 是否期望触发冲突。
- 是否期望触发审批。

评测覆盖：

- 检索命中。
- 引用准确。
- 回答质量。
- 风险类型。
- 冲突识别。
- 审批触发。

## 4. 评测结果

文件：

```text
data/evaluation_results.json
docs/evaluation-report.md
```

重新生成：

```powershell
docker compose exec app python scripts/run_evaluation.py
```

前端的“评测结果”面板会读取 `data/evaluation_results.json`。

## 5. 重置演示数据

先 dry-run：

```powershell
docker compose exec app python scripts/reset_demo_data.py --all
```

确认无误后执行：

```powershell
docker compose exec app python scripts/reset_demo_data.py --all --apply
```

这个命令会：

- 清理 demo 用户的审计历史。
- 清理指定范围内的演示上传文档。
- 从 `data/test_uploads` 重新导入文档。

如果只想清理审计历史：

```powershell
docker compose exec app python scripts/reset_demo_data.py --clear-audit --apply
```

如果想重建演示上传文档：

```powershell
docker compose exec app python scripts/reset_demo_data.py --clear-documents --seed-documents --apply
```

## 6. 数据库查看

可使用 Navicat、DBeaver、pgAdmin 或 psql。

连接信息：

| 配置 | 值 |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `5432` |
| User | `audit_app` |
| Password | `audit_app_dev` |
| Database | `enterprise_audit` |

常用 SQL 在：

```text
scripts/sql
```

详细说明见：

```text
docs/database-guide.md
```

