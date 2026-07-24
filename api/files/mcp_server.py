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


if __name__ == '__main__':
    mcp.run(transport='stdio')
