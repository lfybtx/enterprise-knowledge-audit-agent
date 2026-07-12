# Lesson 06: PGVector 与混合检索

这一小步把上传后的分块从“只能关键词匹配”推进到“关键词 + 向量”的混合检索。

## 新增的数据字段

`document_chunks` 增加了：

```text
embedding vector(64)
```

每个 chunk 写入数据库时，都会同步生成一个 64 维向量。向量字段上创建了 cosine 距离索引：

```sql
CREATE INDEX ix_document_chunks_embedding_cosine
ON document_chunks USING ivfflat (embedding vector_cosine_ops)
WHERE embedding IS NOT NULL;
```

## 为什么先用本地哈希 embedding

真实项目可以使用 OpenAI embedding、bge、gte、jina 等模型。但本阶段为了让项目不依赖 API key 和大模型下载，先实现了一个确定性的本地哈希 embedding：

```text
app/services/embeddings.py
```

它的价值不是语义质量，而是先跑通完整工程链路：

1. chunk -> embedding；
2. embedding -> PostgreSQL vector 字段；
3. 问题 -> query embedding；
4. pgvector cosine search；
5. 与关键词检索结果合并排序。

后续替换成真实 embedding 模型时，Repository 和数据库结构不需要大改，只替换 `embed_text()` 的实现。

## 混合检索怎么做

入口在：

```text
app/repositories/knowledge_repository.py
```

核心函数：

```text
hybrid_search_chunks()
```

流程：

1. 从数据库读取文档和 chunk；
2. 用现有 `HybridRetriever` 做关键词/BM25 风格检索；
3. 用 pgvector 做 cosine 相似度检索；
4. 用 `merge_search_results()` 合并两路结果。

当前合并权重：

```text
0.55 * lexical_score + 0.45 * semantic_score
```

这样保留了关键词的精确性，也给语义相近但用词不同的问题留出命中机会。

## API 行为

`/api/ask` 会优先尝试 PostgreSQL 混合检索：

1. 数据库可用并且有命中：返回数据库检索结果；
2. 数据库不可用或没有命中：回退到原来的内存检索。

这个过渡设计让你在 Docker 环境里演示数据库检索，在本地直接启动 Uvicorn 时也能继续调试。

## 验收命令

先升级数据库：

```powershell
docker compose run --rm app alembic upgrade head
```

再运行测试：

```powershell
docker compose run --rm app pytest -q
```

如果要确认字段存在：

```powershell
docker compose exec db psql -U audit_app -d enterprise_audit -c "\d document_chunks"
```

应该能看到 `embedding vector(64)`。
