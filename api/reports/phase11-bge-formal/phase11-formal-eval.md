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
- candidate_recall_at_20: 0.5455
- candidate_recall_at_40: 0.5455
- final_recall_at_1: 0.3961
- final_recall_at_3: 0.513
- final_recall_at_5: 0.5325
- negative_status_counts: {}
- no_applicable_rule_accuracy: None
- unpublished_pack_safety_block_rate: None
- unpublished_pack_safety_block_status: unmeasured_no_expected_unpublished_cases
### user_evidence_rag
- case_count: 40
- candidate_recall_at_20: 1.0
- context_recall_at_1: 0.175
- context_recall_at_3: 0.425
- context_recall_at_5: 0.55
- context_recall_at_8: 0.65
- context_result_limit: 8
- cross_organization_leakage_rate: 0.0
- cross_organization_runnable_case_count: 24
### dual_domain
- case_count: 24
- runnable_case_count: 24
- rule_final_recall_at_5: 0.625
- evidence_context_recall_at_8: 0.9583
- joint_recall: 0.5833
### citation_metrics
- source_field_completeness_rate: 1.0
- citation_label_case_count: 30
- citation_label_counts: {'complete_support': 10, 'not_evaluable': 13, 'unsupported': 7}
- citation_evaluable_case_count: 17
- citation_not_evaluable_case_count: 13
- citation_entailment_rate: 0.5882
- citation_entailment_status: measured_synthetic_test_fixture
- citation_annotation_level: synthetic_test_developer_review
- citation_label_fixture: 06_claim_citation_entailment_labels.json

## Failure Reasons
- rule_cases: {'candidate_miss': 70, 'hit': 82, 'rerank_miss': 2}
- evidence_cases: {'hit': 26, 'rerank_miss': 14}

## Claim and Workflow Runtime Metrics
- workflow_status: seeded_cases_pending_workflow_runtime_eval
