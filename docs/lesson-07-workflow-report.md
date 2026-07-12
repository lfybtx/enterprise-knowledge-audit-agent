# Lesson 07: 多 Agent 工作流与结构化风险报告

这一小步把 `/api/ask` 从“问一句、回一段话”升级成“固定流程、结构化输出”。

## 工作流分工

现在的请求路径是：

1. `retrieval_agent` 负责找证据；
2. `audit_agent` 负责根据证据产出风险判断；
3. `report_agent` 负责把结果整理成可展示、可评测的报告。

对应实现放在：

```text
app/services/workflow.py
```

## 返回结果

`/api/ask` 现在会返回：

```text
answer
citations
findings
report
workflow_steps
```

其中 `report` 是新的结构化对象，包含：

```text
question
overall_level
finding_count
risk_counts
summary
findings
evidence
```

## 为什么这样做

企业知识库审计场景里，用户通常不只想知道“能不能做”，还要知道：

1. 为什么这么判断；
2. 风险在哪；
3. 应该找谁处理；
4. 证据来自哪里。

把答案、引用和报告拆开之后，前端可以按不同区域展示，后续也方便增加人工复核、导出 PDF、审批流和评测面板。

## 这一阶段怎么验收

启动服务后，调用 `/api/ask`，你应该能看到：

1. `workflow_steps` 里有检索、审计、报告三个步骤；
2. `report.overall_level` 和 `report.finding_count`；
3. `report.evidence` 里保留了引用位置和原文摘要。
