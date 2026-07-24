# Phase 10 Eval and Observability Report

- Workflow runs: 1
- Evidence coverage rate: None
- Tool call success rate: None

## Architecture comparison

| Architecture | Runs | Success rate | Human intervention | Average latency ms |
| --- | ---: | ---: | ---: | ---: |
| sequential | 0 | None | None | None |
| langgraph_single | 0 | None | None | None |
| multi_agent | 1 | 1.0 | 1.0 | 45.23 |

## Not measured

- no_answer_correctness_requires_answer_annotations
- faithfulness_requires_claim_level_annotations
- authorization_rejection_correctness_requires_rejected_call_audit_rows
