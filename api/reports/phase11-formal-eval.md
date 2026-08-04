# Phase 11 Formal Evaluation

evaluation_scope: phase11_verified_fixture_formal_eval
evaluation_contract_version: phase11-formal-eval-v2

## Runtime Environment
- backend: hash
- model: placeholder-hash-v1
- revision: v1
- dim: 32
- ready: True

## RAG Metrics
### rule_rag
- case_count: 154
- candidate_recall_at_20: 0.9545
- candidate_recall_at_40: 1.0
- final_recall_at_1: 0.2662
- final_recall_at_3: 0.4805
- final_recall_at_5: 0.6429
- negative_status_counts: {'grant_pack_not_published': 24, 'no_applicable_rule': 22}
- no_applicable_rule_accuracy: 0.6111
- unpublished_pack_safety_block_rate: 1.0
- unpublished_pack_safety_block_status: measured
### user_evidence_rag
- case_count: 40
- candidate_recall_at_20: 1.0
- context_recall_at_1: 1.0
- context_recall_at_3: 1.0
- context_recall_at_5: 1.0
- context_recall_at_8: 1.0
- context_result_limit: 8
- cross_organization_leakage_rate: 0.0
- cross_organization_runnable_case_count: 24
### dual_domain
- case_count: 24
- runnable_case_count: 24
- rule_final_recall_at_5: 0.5833
- evidence_context_recall_at_8: 0.9583
- joint_recall: 0.5417
### citation_metrics
- source_field_completeness_rate: 1.0
- citation_label_case_count: 30
- citation_label_counts: {'complete_support': 10, 'not_evaluable': 13, 'unsupported': 7}
- citation_evaluable_case_count: 17
- citation_not_evaluable_case_count: 13
- citation_entailment_rate: 0.5882
- citation_entailment_status: measured_developer_initial_review
- citation_label_fixture: 06_claim_citation_entailment_labels.json

## Failure Reasons
- rule_cases: {'hit': 99, 'rerank_miss': 55}
- evidence_cases: {'hit': 40}

## Claim and Workflow Runtime Metrics
- claim_case_count: 30
### reviewer_execution
- reviewed_section_count: 16
- actual_issue_codes: ['duplicate_claim', 'missing_budget_decision', 'missing_claim_evidence', 'numerical_conflict']
- expected_review_grill_issue_codes_implemented: ['completion_status_conflict', 'human_decision_preserved', 'missing_attachment_evidence', 'missing_budget_decision', 'numerical_conflict', 'unsupported_claim']
- expected_review_grill_issue_codes_observed: ['missing_budget_decision', 'numerical_conflict']
- expected_review_grill_issue_codes_not_implemented: ['cross_section_consistency', 'duplicate_funding_conflict', 'locked_claim_change_attempt', 'metric_definition_conflict', 'overclaiming', 'role_attribution_conflict']
- expected_review_grill_issue_codes_not_observed: ['completion_status_conflict', 'cross_section_consistency', 'duplicate_funding_conflict', 'human_decision_preserved', 'locked_claim_change_attempt', 'metric_definition_conflict', 'missing_attachment_evidence', 'overclaiming', 'role_attribution_conflict', 'unsupported_claim']
### review_grill_execution
- fixture_case_count: 12
- cases_with_actual_reviewer_issues: 8
- sessions_created: 8
- first_decisions_recorded: 2
### intake_execution
- fixture_case_count: 36
- routing_accuracy: 0.6111
- question_budget_accuracy: 0.5556
