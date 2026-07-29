'''Framework-independent business services for the proposal workflow.'''

from __future__ import annotations

from typing import Any

from proposals.finalization import build_approved_markdown, get_export_markdown
from proposals.models import Proposal, ProposalSection

from .section_materializer import materialize_sections
from .section_pipeline import apply_revision, promote_section, save_write_result
from .validators import reviewer_or_human_review
from .writer_evidence import retrieve_writer_evidence
from .query_router import retrieve_dual, search_grant_rules, search_user_evidence


class ServiceError(ValueError):
    '''Stable business error exposed to API, workers, and future graph nodes.'''

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def plan_service(*, proposal_id: int, blueprint: list[dict[str, Any]]) -> list[str]:
    '''Materialize a validated plan and return only newly created keys.'''
    rows = materialize_sections(proposal_id=proposal_id, blueprint=blueprint)
    return [section.key for section, created in rows if created]


def write_service(*, section: ProposalSection, draft_markdown: str, answers: dict[str, Any]) -> None:
    '''Store an editable draft without changing approved content.'''
    if section.locked:
        raise ServiceError('section_locked')
    save_write_result(section, draft_markdown, answers)


def review_service(review: dict[str, Any]) -> dict[str, Any]:
    '''Normalize malformed reviewer output to mandatory human review.'''
    return reviewer_or_human_review(review)


def revise_service(*, section: ProposalSection, revised_text: str, user_id: int | None = None,
                   from_text: str = '', diff: dict[str, Any] | None = None) -> None:
    '''Store one revision as a draft and append its audit record.'''
    if section.locked:
        raise ServiceError('section_locked')
    apply_revision(section, revised_text, promote=False)
    section.append_revision(
        user_id=user_id,
        from_text=from_text,
        to_text=revised_text,
        diff=diff,
        change_ratio=(diff or {}).get('change_ratio'),
    )


def promote_service(*, section: ProposalSection) -> None:
    '''Approve and lock a section exactly once.'''
    if section.locked:
        raise ServiceError('section_locked')
    promote_section(section)


def finalize_service(*, proposal: Proposal, final_markdown: str | None = None) -> str:
    '''Build approved content or persist the final formatter result.'''
    text = final_markdown if final_markdown is not None else build_approved_markdown(proposal)
    if final_markdown is not None:
        proposal.final_markdown = text
        proposal.save(update_fields=['final_markdown', 'last_edited'])
    return text


def export_service(*, proposal: Proposal) -> str:
    '''Return the approved export source, rejecting unapproved proposals.'''
    return get_export_markdown(proposal)


def search_service(*, section_key: str, answers: dict[str, Any], organization_id: str = '',
                   proposal_id: int | None = None):
    '''Retrieve writer evidence without depending on an HTTP request.'''
    return retrieve_writer_evidence(
        section_key,
        answers,
        organization_id=organization_id,
        proposal_id=proposal_id,
    )


def retrieve_for_section_dual(*, question: str, rule_query, evidence_query):
    '''Return typed rule and user-evidence retrieval results without mixing candidates.'''
    return retrieve_dual(question=question, rule_query=rule_query, evidence_query=evidence_query)


__all__ = ['search_grant_rules', 'search_user_evidence', 'retrieve_for_section_dual']
