# FoundationPal Agent Architecture

## Context Flow

FoundationPal uses existing workflow-driven Context Engineering to assemble the context required for a proposal task. This document describes the current composition path only. It does not add a ContextBuilder or change prompts, retrieval, workflow nodes, data models, or dependencies.

```text
User Request
  -> Intake
  -> Grill Me when required
  -> Proposal and Section State
  -> Rule Context Retrieval
  -> User Evidence Retrieval
  -> Permission Filtering
  -> Writer or Reviewer
  -> EvidenceUsage
```

### Context responsibilities

| Existing capability | Documentation term | Current role |
|---|---|---|
| Rule package data | Policy Context or Rule Context | Uses the applicable rule package and its requirements for the task. |
| User materials and controlled public evidence | User Evidence Context | Supplies authorized factual evidence for the active proposal. |
| Proposal data | Proposal Context | Provides the current proposal state. |
| Current section content | Section Context | Provides the active section state and writing target. |
| Proposal and Section State | Workflow Context | Carries the state required by the active workflow step. |
| Current writing or review task | Task Context | Selects the task-specific context scope. |
| Reviewer results | Review Context | Is used only by Reviewer and revision flows. |
| Organization and proposal boundaries | Permission Context | Restricts access by organization_id and proposal_id before evidence is made available to a model invocation. |
| Dual-domain retrieval composition | Context Composition | Keeps Rule Context and User Evidence Context separate before task-specific composition. |
| Intake information collection | Context Collection | Collects the proposal inputs needed to start or continue a task. |
| Grill Me clarification | Context Completion | Confirms missing task context when the workflow requires it. |
| Dual-domain selection | Context Routing | Routes rule and evidence queries to their respective retrieval domains. |
| EvidenceUsage | Context Traceability | Records evidence presented to a generation run and its citation state. |
| Proposal, draft, review, and approval records | Persistent Context | Retains contextual state and audit records across workflow steps. |

### Composition rules

- FoundationPal does not place all available materials into one prompt. Existing dual-domain retrieval selects the task-relevant context before composition.
- Rule Context comes from the applicable rule package. User Evidence Context comes from authorized user materials or controlled public evidence in the evidence domain.
- Proposal Context comes from the current Proposal and Section State.
- Intake and Grill Me collect or confirm missing task context. Grill Me is used only when the workflow requires it.
- Writer and Reviewer receive different task-specific context scopes. Review Context is added only for review or revision work.
- Permission Context applies before retrieval and before evidence is made available for a model invocation. EvidenceUsage is a usage record, not a new retrieval module.

### Current boundary

The existing composition flow is workflow-driven and task-specific. It does not claim general-purpose dynamic context compression, automatic token-budget management, or persistent long-term memory.

## Retrieval Flow

FoundationPal packages its existing retrieval path as Controlled Dual-Domain Agentic RAG, also described as Workflow-Driven Agentic RAG. This is a controlled, workflow-driven retrieval path, not an autonomous planner or an open retrieval loop.

```text
Task
  -> Retrieval Domain Decision
  -> Rule Retrieval, User Evidence Retrieval, or Both
  -> Organization and Proposal Filtering
  -> Evidence Injection
  -> Writer or Reviewer
  -> Claim Grounding
  -> EvidenceUsage
  -> Existing Eval
```

### Retrieval domain decision

- Existing Intake records the task mode, rule-pack readiness, proposal state, and user-evidence readiness for the active proposal.
- The active section and available rule-pack and organization or proposal scope determine which existing typed query can be built.
- Existing deterministic query intent routes rule terms, evidence terms, mixed questions, and ambiguous questions to the applicable domain or both. It does not use model-planned retrieval or introduce a new-query loop.

### Domains, permission boundary, and verification

| Existing capability | Documentation term | Current role |
|---|---|---|
| Rule pack RAG | Rule Retrieval Domain | Selects applicable requirements from the selected published rule pack. |
| User material RAG | User Evidence Retrieval Domain | Retrieves user evidence authorized for the active organization and proposal. |
| Dual-domain selection | Retrieval Domain Routing | Uses the existing task and query conditions to select the rule domain, evidence domain, or both. |
| Organization and proposal filtering | Retrieval Permission Boundary | Applies organization, proposal, ownership, authorization, and verified-fact filters before evidence is ranked or injected. |
| EvidenceUsage | Evidence Audit Trail | Records the retrieval query, rank, domain, prompt use, citation state, and evidence snapshot for a model invocation. |
| Claim Grounding | Grounding Verification | Binds factual and numerical claims to evidence so implemented review checks can evaluate them. |
| Reviewer | Post-Generation Review | Checks implemented requirement, evidence, locked-claim, factual-conflict, and cross-section risk types after generation. |
| Recall evaluation | Retrieval Evaluation | Reuses existing Recall at K, MRR, authorized-evidence recall, and leakage readings. |
| Cross-organization leakage evaluation | Retrieval Isolation Evaluation | Reuses existing forbidden-organization leakage cases and results. |

Selected rule and user-evidence candidates remain separate until task-specific evidence injection. Writer output can cite only retrieved candidate identifiers, and its evidence use is persisted as an audit record. Reviewer and revision flows consume the existing claim and evidence state; they do not trigger a second retrieval cycle.

### Existing evaluation evidence

This packaging reuses existing evaluation assets and does not add Gold data, metrics, or reruns:

- [Rule requirement mapping](../data/phase11_human_verified/01_rule_requirement_mapping.json) and [user-evidence grounding](../data/phase11_human_verified/02_user_evidence_grounding.json) cover the existing individual domains.
- [Mixed dual-domain cases](../data/phase11_human_verified/04_mixed_dual_domain.json) cover tasks requiring both domains.
- [Cross-organization leakage cases](../data/phase11_human_verified/05_cross_organization_leakage.json) support the existing Retrieval Isolation Evaluation.
- [Claim Grounding cases](../data/phase11_human_verified/06_claim_grounding.json) support the existing Grounding Verification and implemented review checks.
- The [P1 strict readout](../api/reports/phase40_p1_holdout_eval/phase40-p1-strict-readout.md) reports the existing Recall at K, MRR, authorized-evidence recall, and forbidden-organization leakage readings.

The strict readout limits its conclusion to the current same-lineage source coverage under the existing eight-item context budget. It is not evidence of independent-source generalization or autonomous retrieval.

### Known gaps and boundary

This packaging does not add open automatic re-query, a retrieval sufficiency grader, model-driven query rewriting, autonomous self-correction, a new retrieval model, or a new dependency. It does not change existing retrieval logic, prompts, evaluation results, data, or permission behavior.

## Harness Entry

`ai.agent_runner.run_agent_task` is the thin Agent Harness entry for the existing `full_pipeline` LangGraph workflow. It validates the required task and scope inputs, forwards the caller-provided organization and proposal values with the existing payload to `run_proposal_graph`, and returns the existing graph result in a minimal envelope.

| Harness field | Current source |
|---|---|
| task_type | The existing `full_pipeline` workflow only. |
| organization_id | Forwarded into the existing graph state. |
| proposal_id | Forwarded into the existing graph state. |
| status | Maps existing `completed`, `awaiting_human_approval`, and failure statuses without adding a state machine. |
| output | The unmodified result returned by the existing graph. |

The entry does not add a second workflow, dispatch new agent roles, change graph nodes or their order, reconstruct prompts, access the database directly, or bypass existing services. Planner, Writer, Reviewer, human approval, and finalization remain owned by the current graph and services.

## Eval Coverage

`api/evals/run_all.py` is a read-only aggregation entry for the existing evaluation reports. It reads a fixed set of committed JSON artifacts, presents available key metrics first, then preserves all current source-report metrics in the generated summary.

The current coverage is retrieval, grounding, isolation, reviewer-related reported fields, Intake, release evidence within the E2E baseline, and end-to-end workflow cases. Missing result fields remain absent from metrics and are listed as coverage gaps. The aggregation does not rerun evaluations, change Gold data, modify scoring, add an evaluator, or add dependencies. See [Evaluation Suite](evaluation.md) for source paths, metric definitions, and current gaps.
