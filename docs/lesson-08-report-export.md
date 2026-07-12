# Lesson 08: 风险报告导出

这一小步把工作流产出的 `report` 变成可下载文件。

## 新增接口

```text
POST /api/reports/export
```

请求体：

```json
{
  "question": "Can customer data be exported?",
  "export_format": "markdown"
}
```

支持格式：

1. `json`
2. `markdown`
3. `pdf`

## 输出内容

导出的内容来自工作流中的 `report`，所以会包含：

1. 问题；
2. 总体风险等级；
3. 风险项；
4. 证据摘要；
5. 证据来源。

## 前端支持

结果区上方新增了导出按钮，可以直接下载 Markdown 或 PDF。

## 说明

当前 PDF 是轻量实现，目标是先把下载链路和文件格式跑通。后续如果要做更漂亮的版式，可以再切换到更完整的 PDF 生成方案。
