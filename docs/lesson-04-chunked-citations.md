# Lesson 04: 分块检索与精确引用

这一阶段解决一个真实 RAG 系统必须面对的问题：不能只说“证据来自某个文件”，还要说明来自文件的哪个位置。

## 处理流程

```text
上传文件
  -> 解析成 sections
  -> sections 切成 chunks
  -> 检索 chunks
  -> 回答引用 chunk 的精确位置
```

## 新增核心概念

| 概念 | 说明 |
| --- | --- |
| section | 解析器识别出的自然结构，例如 PDF 页、Word 段落、Excel 行 |
| chunk | 检索器真正索引的片段 |
| location | chunk 的来源定位，例如页码、表格行、工作表行 |

## 和 Java 后端的类比

| Java 常见对象 | 当前项目 |
| --- | --- |
| Entity | 文档和 chunk 字典 |
| DTO | API 返回的 citation |
| Service | `chunking.py`、`retrieval.py` |
| Value Object | `location` 字典 |

## 为什么要分块

整篇文档检索有两个问题：

1. 一篇文档很长时，匹配到的关键词可能离真正答案很远。
2. 引用整篇文档不够审计，面试时也缺乏说服力。

分块后，系统可以返回：

```text
客户数据导出管理规范.pdf，第 1 页
客户数据导出补充规范.docx，表格 1，第 2 行
客户数据导出审批清单.xlsx，工作表：客户数据导出，第 4 行
```

## 本阶段代码变化

```text
app/services/chunking.py      # 分块和位置标签
app/services/parsers.py       # 输出 ParsedDocument 和 ParsedSection
app/services/retrieval.py     # 检索 chunks，不再只检索整篇文档
app/main.py                   # 上传后保存 chunks，API 返回 location_label
web/app.js                    # 证据卡片展示精确位置
```

## 分块策略

- PDF：每页先成为 section，长页再按长度切分。
- Word：普通段落按长度切分；表格行保持完整，不拆开。
- Excel：每个数据行成为一个 section，保留工作表名和行号。
- TXT：每一行成为一个 section，保留行号。

## 验收方式

```powershell
pytest
python scripts/run_evaluation.py
uvicorn app.main:app --reload
```

上传文件后提问：

```text
导出完整客户名单需要谁审批？
导出文件最多可以保存几天？
发现未授权导出后应该怎么处理？
```

证据卡片底部应显示文件路径和具体位置。

## 下一步

下一阶段可以开始做 PostgreSQL/pgvector 存储，把当前内存索引替换成持久化索引。
