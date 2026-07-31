# FoundationPal Agent Evaluation Summary

This read-only summary loads committed result files. Key metrics appear first; all current source-report metrics remain below with their original field names.

## Key Metrics
| Metric | Value | Scope | Source |
|---|---:|---|---|
| End-to-End Task Success Rate | 100.00% | Existing eval baseline cases | Eval baseline |
| Claim Support Rate | 80.00% | P1 strict citation labels | Phase 40 P1 strict holdout |
| Unsupported Claim Rate | 20.00% | P1 strict citation labels | Phase 40 P1 strict holdout |
| Cross-Organization Leakage Rate | 0.00% | P1 strict leakage cases | Phase 40 P1 strict holdout |
| Rule Final Recall@5 | 84.42% | P1 strict rule retrieval | Phase 40 P1 strict holdout |

## Normalized Metrics

### Retrieval
| Metric | Value | Scope | Source |
|---|---:|---|---|
| Rule Candidate Recall@20 | 91.56% | P1 strict rule retrieval | Phase 40 P1 strict holdout |
| Rule Candidate Recall@40 | 98.05% | P1 strict rule retrieval | Phase 40 P1 strict holdout |
| User Evidence Candidate Recall@20 | 100.00% | P1 strict user-evidence retrieval | Phase 40 P1 strict holdout |
| User Evidence Context Recall@1 | 83.33% | P1 strict user-evidence retrieval | Phase 40 P1 strict holdout |
| User Evidence Context Recall@3 | 94.44% | P1 strict user-evidence retrieval | Phase 40 P1 strict holdout |
| User Evidence Context Recall@5 | 94.44% | P1 strict user-evidence retrieval | Phase 40 P1 strict holdout |
| User Evidence Context Recall@8 | 100.00% | P1 strict user-evidence retrieval | Phase 40 P1 strict holdout |
| User Evidence Context Result Limit | 8 | P1 strict user-evidence retrieval | Phase 40 P1 strict holdout |
| Dual-Domain Rule Final Recall@5 | 83.33% | P1 strict mixed-domain cases | Phase 40 P1 strict holdout |
| Dual-Domain Evidence Context Recall@8 | 88.89% | P1 strict mixed-domain cases | Phase 40 P1 strict holdout |
| Dual-Domain Joint Recall | 72.22% | P1 strict mixed-domain cases | Phase 40 P1 strict holdout |
| Rule Final Recall@1 | 7.14% | P1 strict rule retrieval | Phase 40 P1 strict holdout |
| Rule Final Recall@3 | 75.32% | P1 strict rule retrieval | Phase 40 P1 strict holdout |
| Rule Final Recall@5 | 84.42% | P1 strict rule retrieval | Phase 40 P1 strict holdout |

### Grounding
| Metric | Value | Scope | Source |
|---|---:|---|---|
| Claim Support Rate | 80.00% | P1 strict citation labels | Phase 40 P1 strict holdout |
| Citation Source Field Completeness Rate | 100.00% | P1 strict citation labels | Phase 40 P1 strict holdout |
| Unsupported Claim Count | 6 | P1 strict citation labels | Phase 40 P1 strict holdout |
| Citation Evaluable Case Count | 30 | P1 strict citation labels | Phase 40 P1 strict holdout |
| Unsupported Claim Rate | 20.00% | P1 strict citation labels | Phase 40 P1 strict holdout |

### Isolation
| Metric | Value | Scope | Source |
|---|---:|---|---|
| Cross-Organization Leakage Rate | 0.00% | P1 strict leakage cases | Phase 40 P1 strict holdout |
| Authorized Evidence Recall@8 | 100.00% | P1 strict leakage cases | Phase 40 P1 strict holdout |
| Cross-Organization Runnable Case Count | 18 | P1 strict leakage cases | Phase 40 P1 strict holdout |
| P1 Holdout Validation | true | P1 strict holdout validation | Phase 40 P1 strict holdout |

### Reviewer
No current output was found for this group.

### Workflow
| Metric | Value | Scope | Source |
|---|---:|---|---|
| Intake Fixture Case Count | 36 | Phase 40 P03 intake contract | Phase 40 P03 intake contract |
| Intake Routing Accuracy | 100.00% | Phase 40 P03 intake contract | Phase 40 P03 intake contract |
| Question Budget Accuracy | 100.00% | Phase 40 P03 intake contract | Phase 40 P03 intake contract |
| Remaining Intake Discrepancy Count | 0 | Phase 40 P03 intake contract | Phase 40 P03 intake contract |

### E2E
| Metric | Value | Scope | Source |
|---|---:|---|---|
| Total Eval Cases | 5 | Existing eval baseline cases | Eval baseline |
| Passed Cases | 5 | Existing eval baseline cases | Eval baseline |
| Failed Cases | 0 | Existing eval baseline cases | Eval baseline |
| End-to-End Task Success Rate | 100.00% | Existing eval baseline cases | Eval baseline |

## All Existing Source Metrics

### Eval baseline
Source: `api/reports/eval-baseline.json`

| Source field | Value |
|---|---:|
| cases.count | 5 |
| failure_count | 0 |
| passed | true |

### Historical Phase 10 automatic report
Source: `api/reports/phase10-auto-eval.json`

| Source field | Value |
|---|---:|
| automatic_eval.case_count | 3 |
| automatic_eval.context_recall_at_3 | 66.67% |
| automatic_eval.faithfulness | 66.67% |
| automatic_eval.judge_estimated_cost_usd | 0.00043508 |
| automatic_eval.judge_token_usage | 897 |
| automatic_eval.no_answer_correctness | 33.33% |
| comparison.architectures.langgraph_single.average_end_to_end_ms | 34.56 |
| comparison.architectures.langgraph_single.average_fallback_count | 0.0 |
| comparison.architectures.langgraph_single.human_intervention_rate | 0.00% |
| comparison.architectures.langgraph_single.run_count | 9 |
| comparison.architectures.langgraph_single.workflow_task_success_rate | 100.00% |
| comparison.architectures.multi_agent.average_end_to_end_ms | 38.18 |
| comparison.architectures.multi_agent.average_fallback_count | 0.0 |
| comparison.architectures.multi_agent.human_intervention_rate | 0.00% |
| comparison.architectures.multi_agent.reviewer_regression_rate | 0.00% |
| comparison.architectures.multi_agent.run_count | 9 |
| comparison.architectures.multi_agent.workflow_task_success_rate | 100.00% |
| comparison.architectures.sequential.average_end_to_end_ms | 31.75 |
| comparison.architectures.sequential.average_fallback_count | 0.0 |
| comparison.architectures.sequential.human_intervention_rate | 0.00% |
| comparison.architectures.sequential.run_count | 10 |
| comparison.architectures.sequential.workflow_task_success_rate | 100.00% |
| comparison.failure_cases.count | 0 |
| cost.estimated_cost_usd | 0.00090972 |
| cost.token_usage | 1776 |
| rag.case_count | 3 |
| rag.context_recall_at_3 | 66.67% |
| rag.evidence_coverage_rate | 100.00% |
| rag.faithfulness | 66.67% |
| rag.incorrect_evidence_citation_rate | 0.00% |
| rag.judge_estimated_cost_usd | 0.00043508 |
| rag.judge_token_usage | 897 |
| rag.no_answer_correctness | 33.33% |
| rag.not_measured.count | 0 |
| scope.run_count | 28 |
| tools.authorization_rejection_correctness | 100.00% |
| tools.average_tool_latency_ms | 0.6 |
| tools.not_measured.count | 0 |
| tools.tool_call_success_rate | 60.00% |
| workflow_and_agents.langgraph_single.average_end_to_end_ms | 34.56 |
| workflow_and_agents.langgraph_single.average_fallback_count | 0.0 |
| workflow_and_agents.langgraph_single.human_intervention_rate | 0.00% |
| workflow_and_agents.langgraph_single.run_count | 9 |
| workflow_and_agents.langgraph_single.workflow_task_success_rate | 100.00% |
| workflow_and_agents.multi_agent.average_end_to_end_ms | 38.18 |
| workflow_and_agents.multi_agent.average_fallback_count | 0.0 |
| workflow_and_agents.multi_agent.human_intervention_rate | 0.00% |
| workflow_and_agents.multi_agent.reviewer_regression_rate | 0.00% |
| workflow_and_agents.multi_agent.run_count | 9 |
| workflow_and_agents.multi_agent.workflow_task_success_rate | 100.00% |
| workflow_and_agents.sequential.average_end_to_end_ms | 31.75 |
| workflow_and_agents.sequential.average_fallback_count | 0.0 |
| workflow_and_agents.sequential.human_intervention_rate | 0.00% |
| workflow_and_agents.sequential.run_count | 10 |
| workflow_and_agents.sequential.workflow_task_success_rate | 100.00% |

### Historical Phase 10 reference report
Source: `api/reports/phase10-eval.json`

| Source field | Value |
|---|---:|
| comparison.architectures.langgraph_single.run_count | 0 |
| comparison.architectures.multi_agent.average_end_to_end_ms | 45.23 |
| comparison.architectures.multi_agent.average_fallback_count | 1.0 |
| comparison.architectures.multi_agent.human_intervention_rate | 100.00% |
| comparison.architectures.multi_agent.reviewer_regression_rate | 0.00% |
| comparison.architectures.multi_agent.run_count | 1 |
| comparison.architectures.multi_agent.workflow_task_success_rate | 100.00% |
| comparison.architectures.sequential.run_count | 0 |
| comparison.failure_cases.count | 0 |
| rag.not_measured.count | 2 |
| scope.run_count | 1 |
| tools.not_measured.count | 1 |
| workflow_and_agents.langgraph_single.run_count | 0 |
| workflow_and_agents.multi_agent.average_end_to_end_ms | 45.23 |
| workflow_and_agents.multi_agent.average_fallback_count | 1.0 |
| workflow_and_agents.multi_agent.human_intervention_rate | 100.00% |
| workflow_and_agents.multi_agent.reviewer_regression_rate | 0.00% |
| workflow_and_agents.multi_agent.run_count | 1 |
| workflow_and_agents.multi_agent.workflow_task_success_rate | 100.00% |
| workflow_and_agents.sequential.run_count | 0 |

### Phase 40 P03 intake contract
Source: `api/reports/phase40_p03_intake_eval.json`

| Source field | Value |
|---|---:|
| diagnostics.count | 36 |
| question_budget_accuracy | 100.00% |
| remaining_discrepancy_count | 0 |
| routing_accuracy | 100.00% |

### Phase 40 P0v5 formal report
Source: `api/reports/phase40_p0v5_eval/phase11-formal-eval.json`

| Source field | Value |
|---|---:|
| citation_metrics.citation_entailment_rate | 80.00% |
| citation_metrics.citation_entailment_status | measured_developer_initial_review |
| citation_metrics.citation_evaluable_case_count | 30 |
| citation_metrics.citation_label_case_count | 30 |
| citation_metrics.citation_label_counts.complete_support | 18 |
| citation_metrics.citation_label_counts.partial_support | 6 |
| citation_metrics.citation_label_counts.unsupported | 6 |
| citation_metrics.citation_not_evaluable_case_count | 0 |
| citation_metrics.source_field_completeness_rate | 100.00% |
| claim_grounding.case_count | 30 |
| claim_grounding.status | seeded_cases_pending_claim_runtime_eval |
| diagnostics.evidence_cases.count | 18 |
| diagnostics.leakage_cases.count | 18 |
| diagnostics.mixed_cases.count | 18 |
| diagnostics.negative_cases.count | 4 |
| diagnostics.rule_cases.count | 154 |
| dual_domain.case_count | 18 |
| dual_domain.evidence_context_recall_at_8 | 100.00% |
| dual_domain.joint_recall | 88.89% |
| dual_domain.rule_final_recall_at_5 | 88.89% |
| dual_domain.runnable_case_count | 18 |
| intake_review.case_count | 48 |
| intake_review.status | seeded_cases_pending_workflow_runtime_eval |
| rule_rag.candidate_recall_at_20 | 99.35% |
| rule_rag.candidate_recall_at_40 | 100.00% |
| rule_rag.case_count | 154 |
| rule_rag.final_recall_at_1 | 7.14% |
| rule_rag.final_recall_at_3 | 78.57% |
| rule_rag.final_recall_at_5 | 85.71% |
| rule_rag.negative_status_counts.grant_pack_not_published | 1 |
| rule_rag.negative_status_counts.no_applicable_rule | 3 |
| rule_rag.no_applicable_rule_accuracy | 100.00% |
| rule_rag.unpublished_pack_safety_block_rate | 100.00% |
| rule_rag.unpublished_pack_safety_block_status | measured |
| user_evidence_rag.candidate_recall_at_20 | 100.00% |
| user_evidence_rag.case_count | 18 |
| user_evidence_rag.context_recall_at_1 | 100.00% |
| user_evidence_rag.context_recall_at_3 | 100.00% |
| user_evidence_rag.context_recall_at_5 | 100.00% |
| user_evidence_rag.context_recall_at_8 | 100.00% |
| user_evidence_rag.context_result_limit | 8 |
| user_evidence_rag.cross_organization_runnable_case_count | 0 |

### Phase 40 P1 strict holdout
Source: `api/reports/phase40_p1_holdout_eval/phase40-p1-formal-eval.json`

| Source field | Value |
|---|---:|
| citation_metrics.citation_entailment_rate | 80.00% |
| citation_metrics.citation_entailment_status | measured_developer_initial_review |
| citation_metrics.citation_evaluable_case_count | 30 |
| citation_metrics.citation_label_case_count | 30 |
| citation_metrics.citation_label_counts.complete_support | 18 |
| citation_metrics.citation_label_counts.partial_support | 6 |
| citation_metrics.citation_label_counts.unsupported | 6 |
| citation_metrics.citation_not_evaluable_case_count | 0 |
| citation_metrics.source_field_completeness_rate | 100.00% |
| claim_grounding.case_count | 30 |
| claim_grounding.status | seeded_cases_pending_claim_runtime_eval |
| diagnostics.evidence_cases.count | 18 |
| diagnostics.leakage_cases.count | 18 |
| diagnostics.mixed_cases.count | 18 |
| diagnostics.negative_cases.count | 4 |
| diagnostics.rule_cases.count | 154 |
| dual_domain.case_count | 18 |
| dual_domain.evidence_context_recall_at_8 | 88.89% |
| dual_domain.joint_recall | 72.22% |
| dual_domain.rule_final_recall_at_5 | 83.33% |
| dual_domain.runnable_case_count | 18 |
| intake_review.case_count | 48 |
| intake_review.status | seeded_cases_pending_workflow_runtime_eval |
| p1_holdout_validation.eight_character_query_leaks.count | 0 |
| p1_holdout_validation.errors.count | 0 |
| p1_holdout_validation.exact_query_leaks.count | 0 |
| p1_holdout_validation.rewrite_count | 18 |
| p1_holdout_validation.valid | true |
| rule_rag.candidate_recall_at_20 | 91.56% |
| rule_rag.candidate_recall_at_40 | 98.05% |
| rule_rag.case_count | 154 |
| rule_rag.final_recall_at_1 | 7.14% |
| rule_rag.final_recall_at_3 | 75.32% |
| rule_rag.final_recall_at_5 | 84.42% |
| rule_rag.negative_status_counts.grant_pack_not_published | 1 |
| rule_rag.negative_status_counts.no_applicable_rule | 3 |
| rule_rag.no_applicable_rule_accuracy | 100.00% |
| rule_rag.unpublished_pack_safety_block_rate | 100.00% |
| rule_rag.unpublished_pack_safety_block_status | measured |
| user_evidence_rag.candidate_recall_at_20 | 100.00% |
| user_evidence_rag.case_count | 18 |
| user_evidence_rag.context_recall_at_1 | 83.33% |
| user_evidence_rag.context_recall_at_3 | 94.44% |
| user_evidence_rag.context_recall_at_5 | 94.44% |
| user_evidence_rag.context_recall_at_8 | 100.00% |
| user_evidence_rag.context_result_limit | 8 |
| user_evidence_rag.cross_organization_authorized_recall_at_8 | 100.00% |
| user_evidence_rag.cross_organization_leakage_rate | 0.00% |
| user_evidence_rag.cross_organization_runnable_case_count | 18 |

### RAG initial candidates
Source: `api/reports/rag-initial-candidates.json`

| Source field | Value |
|---|---:|
| question_count | 15 |
| results.count | 15 |

### Historical RAG judge sample
Source: `api/reports/rag-judge-sample.json`

| Source field | Value |
|---|---:|
| complete | true |
| complete_answer_rate | 86.67% |
| results.count | 30 |
| sample_size | 30 |
| target_sample_size | 30 |

### RAG regression
Source: `api/reports/rag-regression.json`

| Source field | Value |
|---|---:|
| case_count | 150 |
| metrics.average_elapsed_ms | 190.54 |
| metrics.id_recall_at_1 | 54.67% |
| metrics.id_recall_at_20 | 94.67% |
| metrics.id_recall_at_3 | 76.00% |
| metrics.id_recall_at_5 | 84.00% |
| results.count | 150 |

## Coverage

### Loaded result files
- api/reports/eval-baseline.json
- api/reports/phase10-auto-eval.json
- api/reports/phase10-eval.json
- api/reports/phase40_p03_intake_eval.json
- api/reports/phase40_p0v5_eval/phase11-formal-eval.json
- api/reports/phase40_p1_holdout_eval/phase40-p1-formal-eval.json
- api/reports/rag-initial-candidates.json
- api/reports/rag-judge-sample.json
- api/reports/rag-regression.json

### Missing result files
- None

### Metrics not reported by current outputs
- reviewer.risk_recall: No committed result currently reports reviewer risk recall on implemented risk types.
- grounding.numeric_conflict_count: No committed result currently reports numeric-conflict evaluation output.
- workflow.grill_completion_rate: No committed result currently reports Grill completion rate.
- workflow.release_signoff_pass_rate: No committed result currently reports a standalone release-signoff pass rate.
