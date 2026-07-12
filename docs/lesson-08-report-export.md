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

PDF 导出使用 `reportlab`，并嵌入真实中文字体，避免中文被替换成问号或乱码。

如果你本地之前已经启动过服务，需要先更新依赖再重启：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

默认会自动查找 Windows 中文字体，例如：

```text
C:\Windows\Fonts\simhei.ttf
C:\Windows\Fonts\msyh.ttf
```

如果部署环境没有这些字体，可以通过环境变量指定字体文件：

```powershell
$env:AUDIT_PDF_FONT_PATH="C:\path\to\your\chinese-font.ttf"
```
