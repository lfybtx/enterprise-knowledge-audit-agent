# 第九课：多用户权限数据模型

本课只完成权限隔离的数据库基础。接口鉴权和页面用户切换将在后续步骤接入。

## 为什么不能只使用 `owner_id`

原来的 `knowledge_bases.owner_id` 是一个字符串，只能描述“谁创建了知识库”。企业场景中，一个知识库通常需要由多人协作：

- 合规负责人拥有全部管理权限。
- 业务人员可以上传和维护资料。
- 审计人员只能检索和查看报告。

因此，所有者信息和成员权限是两件事。保留 `owner_id` 可以兼容旧数据；新的权限判断应以成员表为准。

## 表关系

```text
users
  id
  external_id (例如 demo-alice，唯一)
  display_name

knowledge_bases
  id
  name
  owner_id (旧字段，兼容已有数据)

knowledge_base_members
  knowledge_base_id -> knowledge_bases.id
  user_id           -> users.id
  role              -> owner | editor | viewer
```

一个用户可以加入多个知识库，一个知识库也可以有多个成员。因此 `knowledge_base_members` 是一个多对多关联表，并使用 `(knowledge_base_id, user_id)` 唯一约束避免重复成员记录。

## 三种角色

| 角色 | 后续接口中的职责 |
| --- | --- |
| `owner` | 管理成员、删除知识库、上传和检索文档 |
| `editor` | 上传、更新和检索已授权知识库的资料 |
| `viewer` | 只能检索资料、查看审计结论和导出报告 |

数据库还使用 `CHECK` 约束限制角色值，避免无效角色进入数据表。

## 旧数据如何迁移

第 `20260712_0003` 个 Alembic 迁移会读取已有知识库的 `owner_id`：

1. 为每个不同的旧 `owner_id` 创建一个 `users` 记录。
2. 为该用户创建对应知识库的 `owner` 成员记录。

这样升级后，之前上传的文档仍然有唯一的知识库所有者，后续启用鉴权时不会变成“无人可访问”的数据。
