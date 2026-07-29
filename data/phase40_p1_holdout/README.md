# P1 无泄露评测数据

本目录仅用于 P1 用户证据和跨组织检索评测。P0v5 原始资料、Gold 绑定、规则夹具和报告不得修改。

## 填写顺序

1. 先在 00_p1_evidence_query_rewrites.json 填写并人工审核18条改写问题。
2. 将批准后的问题同步到 02、04、05 中对应的 query 或 evidence_query 字段。
3. 运行泄露预检查。问题不得作为连续文本出现在 Gold 原文、标题、结构化事实或种子说明中。
4. 仅在独立 P1 评测数据库中，按 phase40_p1_source_bindings.json 克隆禁止组织证据。

## 不可变字段

所有 external ID、Gold Chunk、组织范围、Proposal、规则 Requirement 和原始来源页码均继承 P0v5，不得修改。

## 跨组织规则

禁止组织证据必须从授权 Gold 原文克隆。评测问题不能写入授权或禁止组织的资源正文、Chunk、结构化事实或说明字段。

