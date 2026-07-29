# Phase 11 人工补充与确认数据包

先生成实际工作清单：

```powershell
Set-Location F:\lrz_workplace\Agent\Foundation\FoundationPal\api
F:\Anaconda\envs\fundagent\python.exe manage.py export_phase11_human_worklists --settings=app.settings.test
```

所有 JSON 均需要逐条人工填写，不允许把 AIChunk ID 直接填入 Requirement ID 或 UserEvidence ID。

## 01 规则映射

文件：`01_rule_requirement_mapping.json`。154 条现有规则题各填规则包版本、年份、类别、地区和 Requirement ID。用于 Rule Recall、适用范围准确率、错误年度和错误类别指标。

## 02 用户证据

文件：`02_user_evidence_grounding.json`。至少40条，其中5条来自现有冻结集，另补35条。每条必须填组织、UserEvidence ID、角色、数值或完成状态。用于 Evidence Recall、Precision、角色和数值准确率。

## 03 规则负例

文件：`03_negative_rule_scope.json`。36条，错误年度、项目类别、地区各12条。用于 No Applicable Rule Accuracy、Wrong Year Rate 和 Wrong Program Rate。

## 04 混合题

文件：`04_mixed_dual_domain.json`。24条，每条同时有 Requirement 与 UserEvidence。用于双域路由、跨域隔离和端到端事实核验。

## 05 跨组织泄漏

文件：`05_cross_organization_leakage.json`。24条，必须是两个真实组织中相似或同名资料的碰撞案例。用于 Cross Organization Leakage Rate，禁止使用不存在组织 ID 代替干扰案例。

## 06 Claim 级核验

文件：`06_claim_grounding.json`。30条。每条要给正文 Claim、Requirement、UserEvidence、预期状态和预期 ReviewIssue。用于 Claim Support、Unsupported Claim、数值错误、决策保留和修订成功率。

## 07 Intake 与 Review Grill

文件：`07_intake_and_review_workflow.json`。36条 Intake 加12条 Review Grill。覆盖三种 task_mode、三种 quality_level、提前结束、预算耗尽、阻断缺口和恢复。用于路由、冗余问题、问题数、ProposalBrief 完成率和 Review Grill 解决率。

## Ragas 的使用边界

Ragas 可以从脱敏规则材料和合成用户资料生成候选问题、单跳题、多跳题和扰动题。生成后必须人工填写或复核本包中的 ID、适用范围、授权范围、数值、角色和预期结果。不要把 Ragas 生成题直接写入冻结集或作为最终指标真值。
