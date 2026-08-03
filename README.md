[[AI_CONFIG]]
FILE_TYPE: 'MARKETING_README'
INTENDED_READER: 'NON_TECHNICAL_PUBLIC'
PURPOSE: ['Provide an overview of the application', 'Highlight key features and technologies', 'Guide users to relevant documentation', 'Facilitate understanding for non-technical stakeholders']
PRIORITY: 'HIGH'
[[/AI_CONFIG]]

<!-- User-facing product README -->

# ForGranted (codename: FoundationPal)

AI-assisted grant proposal writing for organizations that can't afford a full-time grant writer.

## 工程演示入口

这是一个受控的基金申报 Agent：ProposalSection 是章节唯一事实来源，RAG 证据、工具调用、Graph 运行和人工审批均可按 run_id 追溯。

- 一键启动：`docker compose -f app-compose.yml up --build`
- 后端最小验证：`cd api; F:\Anaconda\envs\fundagent\python.exe manage.py test ai.tests.test_main_workflow_e2e ai.tests.test_proposal_graph ai.tests.test_observability --verbosity 1`
- Phase 10 自动基准：`cd api; F:\Anaconda\envs\fundagent\python.exe manage.py run_phase10_auto_eval --output-dir reports`
- 演示案例、指标和敏感资料边界见 [Phase 11 交付指南](docs/phase11_delivery.md)

当前自动基准使用匿名冻结案例与 DeepSeek 自动裁判。它用于验证工程链路和架构比较，不能替代真实申报材料上的人工质量结论。

 
## Core Agent Architecture

### Context Engineering

FoundationPal uses workflow-driven Context Engineering to assemble the minimum context required for each proposal task instead of sending all available materials to a single prompt. The current workflow composes Policy Context, User Evidence Context, Proposal Context, Section Context, Review Context, and Permission Context according to the active task.

Rule knowledge and user evidence stay in separate retrieval domains. Intake and Grill Me collect and complete task context before generation. Writer and Reviewer receive task-specific context scopes. EvidenceUsage records evidence made available to a generation run and whether it was cited, while organization_id and proposal_id constrain cross-organization and cross-proposal access.

This describes the current workflow only. It does not claim general-purpose dynamic context compression, automatic token-budget management, or persistent long-term memory. See [Context Flow](docs/agent_architecture.md#context-flow) for the existing composition path.

### Controlled Dual-Domain Agentic RAG

FoundationPal uses controlled dual-domain retrieval across rule knowledge and user evidence. Existing task and query conditions select the rule domain, user-evidence domain, or both; organization and proposal boundaries apply before evidence is injected into Writer or Reviewer work.

EvidenceUsage records the retrieved evidence used for a model invocation, Claim Grounding supports evidence checks, and Reviewer performs its implemented post-generation checks. This is workflow-driven retrieval without an autonomous re-query loop, a new retrieval model, or a claim of independent-source generalization. See [Retrieval Flow](docs/agent_architecture.md#retrieval-flow).

### Agent Harness

The thin `run_agent_task` entry invokes the existing `full_pipeline` LangGraph workflow without duplicating business logic. It forwards the existing task scope and payload to the current graph and returns a minimal result envelope. It is not a general-purpose autonomous runtime. See [Harness Entry](docs/agent_architecture.md#harness-entry).

### Agent Evaluation Suite

The read-only Agent Evaluation Suite aggregates committed Retrieval, Grounding, Isolation, Intake, workflow, and E2E report fields. It does not rerun evaluations, create Gold data, change scoring, or add an evaluator. See [Evaluation Suite](docs/evaluation.md) and the [complete current metric summary](api/evals/reports/summary.md).

## Evaluation Results

Current key metrics are shown in priority order. The complete generated summary retains all existing report metrics.

| Metric | Value |
|---|---:|
| Intake Routing Accuracy | 100.00% |
| Rule Final Recall@5 | 84.42% |
| Dual-Domain Joint Recall | 72.22% |
| Claim Support Rate | 80.00% |
| Cross-Organization Leakage Rate | 0.00% |

End-to-End and Unsupported Claim metrics remain in the complete report instead of the project-facing priority set. The strict P1 values are limited to current same-lineage source coverage under an eight-item context budget, not independent-source generalization. [All existing report metrics and coverage](api/evals/reports/summary.md) remain in the generated summary.


---

## 1. Problem

Small nonprofits, research teams, and early-stage founders lose funding opportunities because:

1. Grant calls are long, jargon-heavy, and change structure across funders.
2. Teams lack an internal playbook of past winning language and templates.
3. Drafting + reformatting cycles consume scarce time; errors creep in under deadline.
4. Generic AI chat tools don't understand grant-specific structure, compliance, or reuse past context safely.

## 2. Our Solution

ForGranted turns a raw grant call (URL or text) plus your organization profile into a guided, section-by-section authoring workflow. The platform plans required sections, asks only the clarifying questions that matter, drafts each section with context, tracks revisions, and outputs a clean, funder-aligned proposal you can export (PDF / DOCX) deterministically.

## 3. How It Works (High-Level Flow)

1. Input the grant call URL (or paste requirements).
2. The planning agent researches + matches templates/samples (RAG) and builds a section blueprint.
3. For each section: we ask concise questions to fill real gaps (org metadata reused automatically).
4. The writing agent drafts; you review, revise, or request changes (diffs coming).
5. Approved sections lock their content (still revisable after unlock while revisions remaining); future memory snippets (usage_count scored) will boost context relevance.
6. Formatting agent assembles a final structured proposal (semantic markdown → PDF/DOCX).
7. Exports are deterministic: same inputs → same hash (integrity you can trust).

## 4. Key Features

### Core (Alpha)

- Guided Q&A planning (single-run; fallback universal template when retrieval empty)
- AI drafting & revision cycles per section (proposal already sectionized)
- Deterministic formatting & export (PDF/DOCX)
- Organizational usage quotas & plan-based limits (lifetime free + monthly paid)
- Stripe-powered subscriptions (seats, bundles, discounts)
- Secure file uploads (content-type, magic-byte & size checks)
- PII redaction layer in prompt assembly (hashed category tokens)
- (Planned) Memory snippet suggestions (usage_count scoring; not yet enforced in prompts)

### Coming Next (Short Horizon)

- Planner → Section materialization improvements (auto instantiate sections from blueprint)
- Enforce 5 revision cap per section (currently truncates to 50)
- Dynamic question generation engine (template + retrieval + web fallback)
- Provider fallback + circuit breaker
- Prompt injection shield
- Memory injection block (top K usage_count snippets)
- Metrics hashes (structure_hash, question_hash, fallback_mode flag)

### Later (Roadmap Highlights)

- RAG expansion: scheduled ingestion of public grant calls & sample libraries
- Retrieval caching + semantic reranking
- Streaming drafting (SSE)
- i18n & accessibility expansion

## 5. Why It’s Different

- Purpose-built workflow (not free-form chat)
- Deterministic exports & audit trail of prompts
- Strict separation of user answers vs engineered prompts (no raw prompt injection)
- Privacy-first redaction & memory scoping per user/org
- Security and compliance guardrails baked into architecture (RLS, CSP, rate limits)

## 6. Privacy & Security (Snapshot)

Layered controls to keep proposal data safe:

- Data Segregation: Postgres Row-Level Security (RLS) enforces per-user/org access.
- Secrets Hygiene: Distinct signing vs framework secrets; automated env doctor checks.
- Content Sandboxing: File type/MIME validation + optional virus scan hooks.
- Prompt Safety: Deterministic redaction of PII categories before logging; future injection shield.
- Network & Headers: Strict CSP, HSTS, referrer, and CORS controls (no wildcard in production).
- Rate Limits & Quotas: Per-plan AI request caps; daily/monthly token thresholds; 429 responses expose retry guidance.
- Backups: Automated media + database routines (retention window & restore drills documented).
- Export Integrity: Re-computable hash for deterministic outputs (detect silent tampering).

For extended details see: `docs/security_hardening.md`, `docs/ops_coolify_deployment_guide.md`.

## 7. Plans & Pricing (Preview)

- Free: Limited proposals & AI calls (fair trial of core flow)
- Pro: Higher monthly AI/token caps, priority formatting, collaboration basics
- Enterprise / Org Seats: Multi-seat allocation, advanced RAG ingestion cadence, extended retention

Pricing tiers finalize prior to public launch; billing is powered by Stripe for transparency and self-service management.

## 8. Getting Started (Early Access)

Request early access: (placeholder form / email)
While in private alpha, accounts are provisioned manually. OAuth (Google, GitHub, Facebook) is supported; local password auth is disabled for reduced attack surface.

## 9. Using the App (Alpha Walkthrough)

1. Sign in via OAuth & create or join your organization.
2. Start a proposal; paste the grant call URL.
3. Answer focused questions per section; reuse suggested memory chips.
4. Review draft; request revision if needed.
5. Approve all sections → generate formatted draft → export.
6. Upgrade if you approach quota caps (usage panel shows live consumption).

## 10. Data Handling & Privacy FAQ

Q: Do you train on my proposal text?
A: No. Your data is used only to serve your organization; RAG ingestion of user content is opt-in and scoped.

Q: Can staff access my drafts?
A: Only for explicit support cases with logged, auditable access (policy to be published).

Q: How are personal identifiers treated in prompts?
A: Redacted into stable hashed category tokens before logging or evaluation.

Q: Can I delete my account & data?
A: Yes—hard delete pipeline (with short grace) scheduled; exports can be downloaded first.

## 11. Roadmap (Selected Near-Term Items)

- Section workflow model & revision diff engine
- Injection shield & provider fallback
- Dynamic question generation
- Token/phase metrics & enhanced quota binding
- RAG ingestion scheduling & retrieval caching

Full engineering backlog lives in `Todo.md` (developer oriented).

## 12. Responsible AI Principles

- User answers are never silently rephrased without audit context.
- Prompts are versioned & checksummed; changes are traceable.
- Deterministic pathways favored where quality permits; randomness is controlled & documented.
- Fallback logic designed to fail safe (partial degradation instead of silent misuse).

## 13. Contributing

External contribution guidelines will open post-alpha. Until then, internal engineering standards: conventional commits, strict lint, deterministic tests, security-first reviews. See `CONTRIBUTING.md` (subject to revision pre-public).

## 14. Contact / Early Feedback

Questions, partnership, or early access request: [thomas@intelfy.dk](mailto:thomas@intelfy.dk)
Security disclosures: see `SECURITY.md` for coordinated disclosure instructions.

## 15. Legal & Compliance (Preview)

- Privacy Policy (draft) emphasizes minimal data retention & transparent user control.
- Data export & deletion endpoints shipping before public launch.
- Future: optional data processing addendum for enterprise clients.

## 16. Trademarks & Naming

"ForGranted" is the public-facing product name; "FoundationPal" may appear in code/internal docs during transition.

---

### At a Glance

| Aspect | Status |
| ------ | ------ |
| Core authoring workflow | Alpha (iterating) |
| Deterministic exports | Implemented |
| RLS data isolation | Implemented |
| AI memory & redaction | Redaction implemented; memory injection pending |
| Section diff engine | Implemented (structured block logging) |
| Dynamic Q generation | Pending |
| Provider fallback | Pending |
| Billing & quotas | Implemented |
| i18n | Planned |

---

This document is user-facing. Developer/deployment specifics live under `docs/`.
