# Lesson 03: PDF、Word、Excel 解析

这一阶段把已经跑通的上传链路扩展到常见企业文件：

```text
PDF / DOCX / XLSX
  -> Parser
  -> 可检索纯文本
  -> 保存原文件
  -> 立即进入本地索引
```

## 本阶段支持范围

| 格式 | 解析内容 | 检索定位信息 | 当前限制 |
| --- | --- | --- | --- |
| `.pdf` | 每页文本层 | `[Page N]` | 扫描件需要 OCR |
| `.docx` | 段落和表格 | `[Table N]` | 暂不保留图片内文字 |
| `.xlsx` | 工作表、首行表头、数据行 | `[Sheet: 名称]` | 只读取计算后的单元格值 |
| `.txt` | UTF-8、UTF-8 BOM、GBK | 原始行 | 无 |

## 核心代码

入口仍然只有一个函数：

```python
file_type, parsed_text = parse_document(filename, raw_content)
```

它根据文件扩展名分发给 `parse_pdf`、`parse_docx`、`parse_xlsx` 或 `parse_txt`。所有分支最后都会调用 `normalize_text()`：

1. 移除无意义空行；
2. 拒绝少于 20 个字符的空文档；
3. 返回给检索服务统一处理。

这与 Java 的策略模式很像：`parse_document` 相当于分发器，每个 `parse_*` 函数相当于一个格式专用的解析策略。

## 为什么 PDF 要先区分扫描件

PDF 可能包含真正的文字，也可能只是扫描图片。`pypdf` 只能可靠读取文字层，不能从图片中识别字符。

因此当前实现遇到没有可提取文字的 PDF 时会返回：

```text
PDF has no extractable text. It may be a scanned document and needs OCR before upload.
```

这是刻意设计：对于合规审计系统，空证据比明确失败更危险。OCR 会在后续阶段单独接入，并记录 OCR 置信度。

## Excel 如何转成检索文本

Excel 第一行通常是字段名。解析后，一行表格会转成：

```text
[Sheet: 客户导出]
审批人: 区域经理 | 保存期限: 7 天
```

这样用户询问“客户数据最多保存几天”时，关键词和数值都能进入检索器，同时保留来自哪个工作表的信息。

## 验收方式

安装依赖并运行测试：

```powershell
python -m pip install -r requirements.txt
pytest
python scripts/run_evaluation.py
```

然后启动服务：

```powershell
uvicorn app.main:app --reload
```

在首页上传一个文本型 PDF、DOCX 或 XLSX，成功后提问文档里的制度规则。回答的引用来源应显示刚上传的文件路径。

## 下一步

下一阶段会将整篇文档切分为可引用的片段，并让每条引用带有 PDF 页码、Word 表格或 Excel 工作表定位。
