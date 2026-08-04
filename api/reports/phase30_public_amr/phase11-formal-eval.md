# Phase 11 Formal Evaluation

evaluation_scope: phase11_verified_fixture_formal_eval
evaluation_contract_version: phase11-formal-eval-v2

## Runtime Environment
- backend: bge
- model: bge-base-zh-v1.5
- revision: local
- dim: 768
- ready: True

## RAG Metrics
### rule_rag
- case_count: 154
- candidate_recall_at_20: 0.5974
- candidate_recall_at_40: 0.6948
- final_recall_at_1: 0.0
- 
- final_recall_at_3: 0.1818
- final_recall_at_5: 0.3117
- negative_status_counts: {'grant_pack_not_published': 1, 'no_applicable_rule': 3}
- no_applicable_rule_accuracy: 1.0
- unpublished_pack_safety_block_rate: 1.0
- unpublished_pack_safety_block_status: measured
### user_evidence_rag
- case_count: 18
- candidate_recall_at_20: 1.0
- context_recall_at_1: 1.0
- context_recall_at_3: 1.0
- context_recall_at_5: 1.0
- context_recall_at_8: 1.0
- context_result_limit: 8
- cross_organization_leakage_rate: 0.0
- cross_organization_runnable_case_count: 18
### dual_domain
- case_count: 18
- runnable_case_count: 18
- rule_final_recall_at_5: 0.1111
- evidence_context_recall_at_8: 1.0
- joint_recall: 0.1111
### citation_metrics
- source_field_completeness_rate: 1.0
- citation_label_case_count: 30
- citation_label_counts: {'complete_support': 18, 'partial_support': 6, 'unsupported': 6}
- citation_evaluable_case_count: 30
- citation_not_evaluable_case_count: 0
- citation_entailment_rate: 0.8
- citation_entailment_status: measured_developer_initial_review
- citation_annotation_level: public_source_human_verified
- citation_label_fixture: 06_claim_citation_entailment_labels.json

## Failure Reasons
- rule_cases: {'candidate_miss': 47, 'hit': 48, 'rerank_miss': 59}
- evidence_cases: {'hit': 18}

## Claim and Workflow Runtime Metrics
- claim_case_count: 30
### reviewer_execution
- reviewed_section_count: 1
- actual_issue_codes: []
- expected_review_grill_issue_codes_implemented: ['completion_status_conflict', 'cross_section_consistency', 'duplicate_funding_conflict', 'human_decision_preserved', 'locked_claim_change_attempt', 'metric_definition_conflict', 'missing_attachment_evidence', 'missing_budget_decision', 'numerical_conflict', 'overclaiming', 'role_attribution_conflict', 'unsupported_claim']
- expected_review_grill_issue_codes_observed: []
- expected_review_grill_issue_codes_not_implemented: []
- expected_review_grill_issue_codes_not_observed: ['completion_status_conflict', 'cross_section_consistency', 'duplicate_funding_conflict', 'human_decision_preserved', 'locked_claim_change_attempt', 'metric_definition_conflict', 'missing_attachment_evidence', 'missing_budget_decision', 'numerical_conflict', 'overclaiming', 'role_attribution_conflict', 'unsupported_claim']
### review_grill_execution
- fixture_case_count: 12
- cases_with_actual_reviewer_issues: 0
- sessions_created: 0
- first_decisions_recorded: 0
- reverification_successes: 0
- direct_closures: 0
### intake_execution
- fixture_case_count: 36
- routing_accuracy: 0.6111
- question_budget_accuracy: 0.5556
