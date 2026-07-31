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
