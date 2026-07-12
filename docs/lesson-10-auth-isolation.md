# 第十课：后端权限隔离

本课完成演示级鉴权。系统还没有接入真实登录，但后端已经可以根据请求头区分用户，并且只查询当前用户有权限的知识库。

## 当前用户从哪里来

接口读取请求头：

```http
X-User-Id: demo-alice
```

如果没有传这个请求头，系统默认使用：

```text
local-demo
```

这样做的好处是：前端和测试可以先模拟多用户场景，不需要在学习早期引入完整的登录、注册、JWT、密码加密和会话管理。

## 已隔离的接口

以下接口都会按当前用户过滤数据：

| 接口 | 隔离行为 |
| --- | --- |
| `GET /api/documents` | 只返回当前用户有权限的文档 |
| `POST /api/documents` | 文档写入当前用户的默认知识库 |
| `POST /api/documents/upload` | 上传文件写入当前用户的默认知识库 |
| `POST /api/ask` | 只检索当前用户有权限的文档块 |
| `POST /api/reports/export` | 只基于当前用户可见证据生成报告 |
| `POST /api/evaluate` | 只在当前用户可见文档内评测 |

## PostgreSQL 中如何隔离

数据库查询会通过成员表过滤：

```text
users.external_id = X-User-Id
users.id = knowledge_base_members.user_id
knowledge_base_members.knowledge_base_id = knowledge_bases.id
documents.knowledge_base_id = knowledge_bases.id
```

也就是说，只有当前用户是某个知识库的成员时，才能看到这个知识库下的文档和文档块。

## 本地 JSON 兜底如何隔离

如果没有配置 `DATABASE_URL`，系统会退回到 `data/runtime/documents.json`。这时每个文档会带上：

```json
{
  "owner_id": "demo-alice"
}
```

后端会用这个字段做最小可用的隔离。这个模式适合本地开发，不适合生产环境。

## 手动验证

先用 Alice 上传一份文档：

```powershell
curl -X POST http://127.0.0.1:8000/api/documents ^
  -H "Content-Type: application/json" ^
  -H "X-User-Id: demo-alice" ^
  -d "{\"title\":\"Alice Policy\",\"source\":\"alice.txt\",\"content\":\"Alice customer export requires manager approval before sharing data.\"}"
```

Alice 可以看到：

```powershell
curl http://127.0.0.1:8000/api/documents -H "X-User-Id: demo-alice"
```

Bob 看不到：

```powershell
curl http://127.0.0.1:8000/api/documents -H "X-User-Id: demo-bob"
```

Bob 用相同问题查询时，也不会检索到 Alice 的文档。
