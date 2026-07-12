# 第十五课：检索与回答评测

本课把原来的 4 条 smoke test 扩展成 50 条可复现评测集。

## 评测文件

```text
data/evaluation_cases.json
data/evaluation_results.json
scripts/run_evaluation.py
```

每条 case 包含：

- `id`
- `question`
- `expected_document_id`
- `expected_location_kind`

## 当前指标

运行：

```powershell
python scripts/run_evaluation.py
```

会输出：

| 指标 | 当前结果 |
| --- | --- |
| Total cases | 50 |
| Recall@1 | 98.0% |
| Recall@3 | 100.0% |
| Citation accuracy | 98.0% |
| Answer quality pass rate | 100.0% |

## 指标含义

- `Recall@1`：第一条检索结果是否命中目标文档。
- `Recall@3`：前三条检索结果是否包含目标文档。
- `Citation accuracy`：第一条结果的文档和引用位置类型是否正确。
- `Answer quality pass rate`：回答是否基于证据生成，并带有证据引用标记。

## 为什么不是 100%

当前保留了一个真实失败样例：历史销售工具说明和当前客户导出规范的冲突问题，第一条结果会命中当前销售导出规范。

这不是坏事。面试展示时，真实评测结果比“强行满分”更可信，也能说明系统已经具备定位失败样例、继续优化检索策略的能力。

## 下一步

后续可以继续加入：

- 100 条以上企业制度问答
- 多文档冲突类评测
- LLM-as-judge 回答质量评测
- 人工标注的引用段落准确率
