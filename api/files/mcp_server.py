'''Stdio MCP server exposing controlled PDF document operations.'''

from __future__ import annotations

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

import django

django.setup()

from django.contrib.auth import get_user_model
from mcp.server.fastmcp import FastMCP

from .document_services import (
    DocumentServiceError,
    extract_document_structure as build_structure,
    extract_requirements as build_requirements,
    parse_controlled_pdf,
)
from ai.models import Claim, GrantPackVersion, GrantRequirement, UserEvidence


mcp = FastMCP('Grant Proposal Document MCP')


def _context():
    try:
        caller_id = int(os.environ['MCP_CALLER_ID'])
        organization_id = int(os.environ['MCP_ORGANIZATION_ID'])
    except (KeyError, ValueError) as error:
        raise RuntimeError('MCP_CALLER_ID and MCP_ORGANIZATION_ID are required') from error
    caller = get_user_model().objects.filter(id=caller_id).first()
    if caller is None:
        raise RuntimeError('MCP caller does not exist')
    return caller, organization_id


def _result(operation):
    try:
        return operation()
    except DocumentServiceError as error:
        return {'schema_version': 'v1', 'error': {'code': error.code, 'details': error.details}}


def _document(file_id: int):
    caller, organization_id = _context()
    return parse_controlled_pdf(file_id=file_id, caller=caller, organization_id=organization_id)


@mcp.tool()
def parse_document(file_id: int) -> dict:
    '''Parse a controlled PDF file_id and return metadata plus resource links only.'''
    def operation():
        document = _document(file_id)
        return {
            key: value for key, value in document.items() if key != 'pages'
        } | {
            'resources': {
                'metadata': f'document://{file_id}/metadata',
                'page_template': f'document://{file_id}/page/{{page_number}}',
                'section_template': f'document://{file_id}/section/{{section_index}}',
            }
        }
    return _result(operation)


@mcp.tool()
def extract_document_structure(file_id: int) -> dict:
    '''Extract deterministic page and section structure from a controlled PDF file_id.'''
    return _result(lambda: build_structure(_document(file_id)))


@mcp.tool()
def extract_requirements(file_id: int) -> dict:
    '''Extract deterministic requirement-like lines from a controlled PDF file_id.'''
    return _result(lambda: build_requirements(_document(file_id)))


@mcp.resource('document://{file_id}/metadata', mime_type='application/json')
def get_document_metadata(file_id: int) -> dict:
    return _result(lambda: {key: value for key, value in _document(file_id).items() if key != 'pages'})


@mcp.resource('document://{file_id}/page/{page_number}', mime_type='application/json')
def get_page_content(file_id: int, page_number: int) -> dict:
    def operation():
        document = _document(file_id)
        for page in document['pages']:
            if page['page_number'] == page_number:
                return {'schema_version': 'v1', 'file_id': file_id, 'page': page}
        raise DocumentServiceError('page_not_found')
    return _result(operation)


@mcp.resource('document://{file_id}/section/{section_index}', mime_type='application/json')
def get_document_section(file_id: int, section_index: int) -> dict:
    def operation():
        document = _document(file_id)
        structure = build_structure(document)
        if section_index < 1 or section_index > len(structure['sections']):
            raise DocumentServiceError('section_not_found')
        return {'schema_version': 'v1', 'file_id': file_id, 'section': structure['sections'][section_index - 1]}
    return _result(operation)


@mcp.resource('grantpack://{pack_version_id}/metadata', mime_type='application/json')
def get_grantpack_metadata(pack_version_id: int) -> dict:
    def operation():
        _, organization_id = _context()
        version = GrantPackVersion.objects.select_related('pack__program').filter(pk=pack_version_id, status='published').first()
        if version is None or (version.pack.organization_id and version.pack.organization_id != str(organization_id)):
            raise DocumentServiceError('grant_pack_not_found')
        return {'schema_version': 'v1', 'pack_version_id': version.id, 'year': version.year, 'program': version.pack.program.name, 'status': version.status}
    return _result(operation)


@mcp.resource('grantpack://requirement/{requirement_id}', mime_type='application/json')
def get_grant_requirement(requirement_id: int) -> dict:
    def operation():
        _, organization_id = _context()
        requirement = GrantRequirement.objects.select_related('pack_version__pack', 'source_chunk__resource').filter(pk=requirement_id, pack_version__status='published').first()
        if requirement is None or (requirement.pack_version.pack.organization_id and requirement.pack_version.pack.organization_id != str(organization_id)):
            raise DocumentServiceError('requirement_not_found')
        return {'schema_version': 'v1', 'knowledge_domain': 'grant_rule', 'requirement_id': requirement.id, 'excerpt': requirement.source_excerpt or requirement.text, 'source': requirement.source_chunk.resource.display_name}
    return _result(operation)


@mcp.resource('evidence://{user_evidence_id}', mime_type='application/json')
def get_user_evidence(user_evidence_id: int) -> dict:
    def operation():
        _, organization_id = _context()
        evidence = UserEvidence.objects.select_related('chunk__resource').filter(pk=user_evidence_id, organization_id=str(organization_id)).first()
        if evidence is None:
            raise DocumentServiceError('user_evidence_not_found')
        return {'schema_version': 'v1', 'knowledge_domain': 'user_evidence', 'user_evidence_id': evidence.id, 'excerpt': evidence.controlled_summary or evidence.chunk.text[:1000], 'source': evidence.chunk.resource.display_name}
    return _result(operation)


@mcp.resource('evidence://claim/{claim_id}/bindings', mime_type='application/json')
def get_claim_bindings(claim_id: int) -> dict:
    def operation():
        _, organization_id = _context()
        claim = Claim.objects.filter(pk=claim_id, proposal__org_id=organization_id).first()
        if claim is None:
            raise DocumentServiceError('claim_not_found')
        return {'schema_version': 'v1', 'claim_id': claim.id, 'bindings': list(claim.evidence_bindings.values('grant_requirement_id', 'user_evidence_id', 'support_type', 'support_strength', 'reviewer_status'))}
    return _result(operation)


if __name__ == '__main__':
    mcp.run(transport='stdio')
