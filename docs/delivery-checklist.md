# GitHub 与面试交付检查清单

提交或面试前按这份清单检查。

## 1. 基础运行

- [ ] `.env.example` 存在，且不包含真实密钥。
- [ ] `docker compose up -d --build` 可以启动。
- [ ] `http://127.0.0.1:8000` 可以打开。
- [ ] Swagger 文档可访问：`http://127.0.0.1:8000/docs`。
- [ ] `/api/health` 返回正常。

## 2. 文档上传

- [ ] 可以上传 `.txt`。
- [ ] 可以上传文本型 PDF。
- [ ] 可以上传扫描 PDF 并走 OCR。
- [ ] 可以上传 `.docx`。
- [ ] 可以上传 `.xlsx`。
- [ ] 可以抓取 HTML URL。
- [ ] 上传后文档写入 PostgreSQL。
- [ ] 上传后 chunk 写入 `document_chunks`。
- [ ] 上传后 embedding 写入 pgvector。
- [ ] 原始文件写入 MinIO 或本地 fallback。

## 3. RAG 与 Agent

- [ ] 问答必须带证据引用。
- [ ] 没有证据时不直接回答。
- [ ] 关键词检索可用。
- [ ] 向量检索可用。
- [ ] reranker 可用。
- [ ] Trace 中能看到检索候选排序。
- [ ] 审计 Agent 能识别风险。
- [ ] 能识别新旧制度冲突。
- [ ] 高风险或冲突能触发人工确认。

## 4. 权限与审计

- [ ] admin 可以上传并管理知识库。
- [ ] 普通 viewer 用户不能上传。
- [ ] 不同用户文档可见范围隔离。
- [ ] 审计历史按用户隔离。
- [ ] viewer 不能访问系统诊断。
- [ ] Trace 可持久化。
- [ ] 审批结果可持久化。

## 5. 报告导出

- [ ] Markdown 导出可用。
- [ ] PDF 导出可用。
- [ ] 中文 PDF 不乱码。
- [ ] 报告包含风险等级、依据、建议动作、引用来源。

## 6. 评测

- [ ] `data/evaluation_cases.json` 存在。
- [ ] 至少 50 条评测用例。
- [ ] `scripts/run_evaluation.py` 可运行。
- [ ] `data/evaluation_results.json` 已生成。
- [ ] `docs/evaluation-report.md` 已生成。
- [ ] README 中展示关键指标。

## 7. 运维

- [ ] `docs/database-guide.md` 存在。
- [ ] `scripts/sql` 存在常用 SQL。
- [ ] `scripts/check_database.py` 可运行。
- [ ] 前端系统状态面板可显示数据库和索引状态。
- [ ] 可以查看文档数、切片数、审计记录数、Trace 步骤数。

## 8. GitHub 文档

- [ ] README 是中文。
- [ ] README 有项目定位。
- [ ] README 有 Docker 启动命令。
- [ ] README 有 DeepSeek 接入说明。
- [ ] README 有演示账号。
- [ ] README 有评测结果。
- [ ] README 有面试演示路径。
- [ ] 架构文档存在：`docs/architecture.md`。
- [ ] 演示脚本存在：`docs/demo-script.md`。
- [ ] 项目亮点和局限存在：`docs/project-highlights.md`。
- [ ] 测试数据说明存在：`docs/test-data.md`。

## 9. 提交前验证

```powershell
node --check web\app.js
.\.venv\Scripts\python.exe -m pytest
docker compose up -d --build
docker compose exec app pytest
docker compose exec app python scripts/check_database.py
git status --short
```

## 本次状态记录（2026-07-14）

- 本地测试：`80 passed, 8 skipped`。
- 前端语法检查：`node --check web\app.js` 通过。
- 跳过测试：6 个 PostgreSQL/SQLAlchemy 测试，以及 2 个需要 PostgreSQL 权限环境的测试。
- Docker Compose 集成验证：未完成，当前环境无法访问 Docker Engine。
- 上线前重点：生产密钥校验、文件上传安全、URL 导入 SSRF 防护、异步任务闭环和集成测试 CI。

完整风险说明和实施顺序见：[项目状态与后续路线图](project-status-and-roadmap.md)。

## 10. 推送到远程仓库

```powershell
git push origin main
```

如果出现 dubious ownership：

```powershell
git config --global --add safe.directory C:/Users/12785/Documents/Codex/2026-07-10/new-chat/enterprise-knowledge-audit-agent
```
