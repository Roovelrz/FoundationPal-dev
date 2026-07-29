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
- candidate_recall_at_20: 0.9156
- candidate_recall_at_40: 0.9805
- final_recall_at_1: 0.0714
- final_recall_at_3: 0.7532
- final_recall_at_5: 0.8442
- negative_status_counts: {'grant_pack_not_published': 1, 'no_applicable_rule': 3}
- no_applicable_rule_accuracy: 1.0
- unpublished_pack_safety_block_rate: 1.0
- unpublished_pack_safety_block_status: measured
### user_evidence_rag
- case_count: 18
- candidate_recall_at_20: 1.0
- context_recall_at_1: 0.8333
- context_recall_at_3: 0.9444
- context_recall_at_5: 0.9444
- context_recall_at_8: 1.0
- context_result_limit: 8
- cross_organization_leakage_rate: 0.0
- cross_organization_authorized_recall_at_8: 1.0
- cross_organization_runnable_case_count: 18
### dual_domain
- case_count: 18
- runnable_case_count: 18
- rule_final_recall_at_5: 0.8333
- evidence_context_recall_at_8: 0.8889
- joint_recall: 0.7222
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
- rule_cases: {'candidate_miss': 3, 'hit': 130, 'rerank_miss': 21}
- evidence_cases: {'hit': 18}

## Claim and Workflow Runtime Metrics
- workflow_status: seeded_cases_pending_workflow_runtime_eval
