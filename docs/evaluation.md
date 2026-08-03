# FoundationPal Agent Evaluation Suite

## Evaluation Scope

FoundationPal packages existing evaluation artifacts as a read-only Agent Evaluation Suite. `api/evals/run_all.py` reads fixed committed JSON reports and writes a normalized summary. It does not execute an evaluation, modify Gold data, change a metric definition, or add an evaluator.

| Coverage | Existing source | Current boundary |
|---|---|---|
| Retrieval | P0v5 and P1 formal reports, RAG regression | P1 strict values are the current key retrieval readout. |
| Grounding | P1 citation metrics | Claim support and unsupported-claim values come from the existing citation labels. |
| Isolation | P1 strict holdout | Includes forbidden-organization leakage and authorized-evidence recall. |
| Reviewer | Existing workflow and Phase 10 report fields | No committed report currently provides Reviewer Risk Recall. |
| Intake and Grill | P03 intake contract | Intake routing and question-budget accuracy are reported; Grill completion is not. |
| Release | Existing E2E baseline | Approval and export appear in the baseline workflow, without a standalone release-signoff rate. |
| E2E | `eval-baseline.json` | Uses the existing five fixed baseline cases and their reported failure count. |

## Metric Definitions

| Metric | Source field | Numerator and denominator | Scope | Key metric |
|---|---|---|---|---|
| Intake Routing Accuracy | `routing_accuracy` | Existing reported rate | P03 intake contract cases | Yes |
| Rule Final Recall at 5 | `rule_rag.final_recall_at_5` | Existing reported recall | P1 strict rule retrieval | Yes |
| Dual-Domain Joint Recall | `dual_domain.joint_recall` | Existing reported recall | P1 strict mixed-domain cases | Yes |
| Claim Support Rate | `citation_metrics.citation_entailment_rate` | Existing reported rate | P1 strict citation labels | Yes |
| Cross-Organization Leakage Rate | `user_evidence_rag.cross_organization_leakage_rate` | Existing reported rate | P1 strict leakage cases | Yes |
| End-to-End Task Success Rate | `cases` and `failure_count` | `(case count - failure count) / case count` | Existing five E2E baseline cases | No |
| Unsupported Claim Rate | `citation_label_counts.unsupported / citation_evaluable_case_count` | Existing unsupported labels divided by existing evaluable labels | P1 strict citation labels | No |
| Question Budget Accuracy | `question_budget_accuracy` | Existing reported rate | P03 intake contract cases | No |

The P1 strict readout is qualified by the current same-lineage source coverage and eight-item context budget. It is not evidence of independent-source generalization.

## Result Files

The fixed result map currently reads these committed files:

- `api/reports/eval-baseline.json`
- `api/reports/phase10-auto-eval.json`
- `api/reports/phase10-eval.json`
- `api/reports/phase40_p03_intake_eval.json`
- `api/reports/phase40_p0v5_eval/phase11-formal-eval.json`
- `api/reports/phase40_p1_holdout_eval/phase40-p1-formal-eval.json`
- `api/reports/rag-initial-candidates.json`
- `api/reports/rag-judge-sample.json`
- `api/reports/rag-regression.json`

Run the read-only aggregation from `api` with `F:\Anaconda\envs\fundagent\python.exe evals/run_all.py`. The generated outputs are `api/evals/reports/summary.json`, the published `api/evals/reports/summary.md`, and the ignored local-detail view `api/evals/reports/summary.local.md`.

## Key Metric Priority

The summary orders existing available key metrics as follows:

1. Intake Routing Accuracy
2. Rule Final Recall at 5
3. Dual-Domain Joint Recall
4. Claim Support Rate
5. Cross-Organization Leakage Rate

All other current source-report indicators follow in the normalized and source-report sections of the summary.

## Known Gaps

- Reviewer Risk Recall on Implemented Risk Types is not displayed until a committed result provides that field. Unreported risk types are not treated as passed.
- Numeric-conflict, Grill-completion, and standalone release-signoff rates are not displayed because no current result provides them.
- Current Agentic RAG does not include open automatic re-query.
- The current Harness is the unified entry to the existing workflow, not a second workflow.
- Historical Phase 10 automatic and RAG judge report fields remain listed as source metrics only. They are not promoted to new evaluation capabilities or key metrics.
