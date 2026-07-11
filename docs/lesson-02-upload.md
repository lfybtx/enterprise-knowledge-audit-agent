# Lesson 02: 文档上传与解析

这一阶段的目标是跑通第一条真实入库链路：

```text
选择 .txt 文件
  -> 上传到 FastAPI
  -> 保存原始文件
  -> 解析文本
  -> 加入知识库索引
  -> 立刻可检索和问答
```

## 新增文件

```text
app/services/parsers.py       # 文件解析服务
data/runtime/uploads/         # 上传文件保存目录，运行时自动创建
tests/test_parsers.py         # 解析器测试
tests/test_upload_api.py      # 上传接口测试
```

## 新增接口

```http
POST /api/documents/upload
```

表单字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | text | 文档标题 |
| `file` | file | 当前支持 `.txt` |

## 为什么先只做 txt

上传链路比文件格式更重要。先用 `.txt` 跑通 Controller、Parser、Storage、Index，再扩展 PDF、Word、Excel。这样每次只解决一个问题。

## 和 Java 后端的类比

| Java / Spring Boot | 当前项目 |
| --- | --- |
| `MultipartFile` | FastAPI `UploadFile` |
| `@RequestParam` | FastAPI `Form(...)` |
| 文件解析 Service | `app/services/parsers.py` |
| 数据库保存 | 当前先保存到 `data/runtime/documents.json` |
| 文件对象存储 | 当前先保存到 `data/runtime/uploads/` |

## 验收方式

1. 启动服务：

   ```powershell
   uvicorn app.main:app --reload
   ```

2. 打开首页：

   ```text
   http://127.0.0.1:8000
   ```

3. 上传一个 `.txt` 文件，内容示例：

   ```text
   客户名单导出必须由区域经理审批，导出文件保存不得超过 7 天。
   ```

4. 提问：

   ```text
   客户名单导出需要审批吗？
   ```

5. 检查回答里的引用来源是否包含你刚上传的文档。

## 下一步

下一小步会加入 PDF、Word、Excel 解析，并把本地 JSON 存储替换为 PostgreSQL。
