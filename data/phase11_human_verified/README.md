# Phase 11 人工工作清单 04 至 07 完成版

本目录包含四份已逐条填写的 JSON：

- 04_mixed_dual_domain.json，共24条
- 05_cross_organization_leakage.json，共24条
- 06_claim_grounding.json，共30条
- 07_intake_and_review_workflow.json，共48条，其中36条 Intake，12条 Review Grill

同时包含原始 Markdown 说明、外部 ID 种子清单与 validation_report.json。

## ID 说明

上传材料未提供当前数据库真实主键表。为避免伪造数据库 ID，本目录使用独立受控外部 ID：

- GrantPackVersion 使用 GPV 命名空间
- GrantRequirement 使用 GRANTREQ 命名空间
- Organization 使用 ORG 命名空间
- UserEvidence 使用 UE 命名空间
- Claim 使用 CLAIM 命名空间

所有外部 ID 均需在导入数据库后映射为真实主键。任何 AIChunk ID 都没有被写入 Requirement ID 或 UserEvidence ID。

## 跨组织测试说明

跨组织泄漏数据使用西南民族大学与四川大学两个真实组织名称。证据值是专门构造的多租户隔离测试种子，不代表两所高校的真实科研数据。导入时必须在数据库中创建或绑定两条真实 Organization 记录，再映射外部组织 ID。

## 校验结果

validation_report.json 的 status 为 passed，覆盖数量、字段完整性、组织隔离、Claim 状态分布、Intake 组合覆盖和 ID 安全检查。

## 最终冻结提醒

JSON中的 annotation_status 已按目标模板填写为 human_confirmed。由于本次未连接你的本地数据库和真实组织权限环境，数据库主键映射、组织成员授权检查及最终人工签核仍需在本地执行后再作为正式冻结评测集。
