# 0-7人工审核清单总表

本表包含阶段0至7的全部人工审核任务，以及实施过程中确认未关闭的问题。系统当前不具备发布就绪条件。

## 发布结论

- 当前状态：不可发布。
- 原因：用户证据 BGE 基线被18条来源绑定阻断，12条规则适用语义待确认，6类 Reviewer 风险未实现，冻结风险样本每类仅1条，未发布规则包安全阻断尚无期望样本。

## 阶段0至4

- 阶段0：人工标注 Claim 与证据的完整支持、部分支持或不支持，并签署评测夹具版本。
- 阶段1：完成18条原始 Gold Chunk 来源绑定，确认授权、组织、Proposal 和页码。
- 阶段2：完成12条 conditional 或青年 A、B 类规则的适用语义确认。
- 阶段3：阶段1绑定完成后，审核用户证据 BGE 指标。
- 阶段4：阶段1绑定完成后，审核24条双域样本的子问题、证据组合和 BGE Joint Recall。

## 阶段5至6

- 审核已实现检测器的业务真值和误报。
- 为 duplicate_funding_conflict、locked_claim_change_attempt、role_attribution_conflict、metric_definition_conflict、cross_section_consistency、overclaiming 提供定义、样本和实现优先级。
- 为12类风险分别签署允许处置、补充材料要求和关闭条件。

## 阶段7冻结数据

| 风险类型 | 当前冻结样本 | 开发集缺口 | 冻结集缺口 |
| --- | ---: | --- | --- |
| completion_status_conflict | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| cross_section_consistency | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| duplicate_funding_conflict | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| human_decision_preserved | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| locked_claim_change_attempt | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| metric_definition_conflict | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| missing_attachment_evidence | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| missing_budget_decision | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| numerical_conflict | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| overclaiming | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| role_attribution_conflict | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |
| unsupported_claim | 1 | positive4、near_negative4、boundary2 | positive9、near_negative9、boundary4 |

## 实施中发现且未关闭的问题

- phase1_source_binding：绑定原始 Gold Chunk 并确认授权、组织、Proposal 和页码。
- phase2_scope_semantics：确认 conditional 与青年 A、B 类规则的适用字段映射。
- citation_entailment_labels：为 Claim 与证据标注完整支持、部分支持或不支持。
- unimplemented_review_detectors：实现并人工确认剩余风险检测器。
- frozen_test_overfitting_risk：建立未参与调参的开发集和独立发布保留集后，重新签署门槛。
- intake_fixture_contract_gap：逐条复核36条 Intake 夹具与当前路由、问题预算合同的差异，并决定修正实现或更新人工标签。

## 操作顺序

1. 先完成阶段1和阶段2人工确认。
2. 建立独立开发集和发布保留集，避免继续用冻结集调参。
3. 补齐6类 Reviewer 检测器与12类风险样本。
4. 逐条复核 Intake 夹具合同差异。
5. 重跑 BGE、双域、Reviewer、Review Grill 和发布门槛报告，再由业务负责人签署。
