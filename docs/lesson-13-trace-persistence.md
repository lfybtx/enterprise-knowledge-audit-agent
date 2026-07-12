# 第十三课：工作流追踪持久化

本课把上一课的内存 trace 落到 PostgreSQL，方便重启后继续查看每次审计的执行过程。

## 为什么要分两张表

一条审计请求包含两层信息：

1. 整体摘要
2. 每一步的详细 trace

所以数据库拆成两张表：

- `workflow_runs`：保存一次请求的摘要
- `workflow_trace_steps`：保存每一步的 prompt、工具调用、耗时和失败原因

这样做有两个好处：

- 查询单次 trace 时很直接
- 后续如果想加人工复核、失败重试或图形化追踪，不需要改老结构

## `workflow_runs`

这张表保存：

- `trace_id`
- 当前用户
- 事件类型
- 问题
- 总耗时
- 步数
- 总结

## `workflow_trace_steps`

这张表保存：

- 步骤名
- 步骤状态
- 步骤说明
- 步骤耗时
- prompt
- tool_calls
- input_tokens / output_tokens
- failure_reason

## 接口行为

- `/api/ask` 成功后会写入一条 `question_answered`
- `/api/reports/export` 成功后会写入一条 `report_exported`
- `/api/audit-log` 在数据库可用时优先从 PostgreSQL 读取

## 后续可以怎么扩展

- 给 trace 增加人工确认状态
- 给失败步骤加 retry 次数
- 给每次 trace 增加 LLM 原始输出字段
- 给前端做 trace 详情弹窗
