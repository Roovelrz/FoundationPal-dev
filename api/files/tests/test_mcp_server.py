import asyncio
import os
import sys
from pathlib import Path

from django.test import SimpleTestCase
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class McpServerTests(SimpleTestCase):
    def test_stdio_server_lists_document_tools_and_resources(self):
        async def check_server():
            api_dir = Path(__file__).resolve().parents[2]
            environment = dict(os.environ)
            environment['DJANGO_SETTINGS_MODULE'] = 'app.settings.test'
            parameters = StdioServerParameters(
                command=sys.executable,
                args=['-m', 'files.mcp_server'],
                cwd=api_dir,
                env=environment,
            )
            async with stdio_client(parameters) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    resources = await session.list_resource_templates()
                    return {tool.name for tool in tools.tools}, {item.uriTemplate for item in resources.resourceTemplates}

        tools, resources = asyncio.run(check_server())
        self.assertEqual(tools, {'parse_document', 'extract_document_structure', 'extract_requirements'})
        self.assertTrue({
            'document://{file_id}/metadata',
            'document://{file_id}/page/{page_number}',
            'document://{file_id}/section/{section_index}',
            'grantpack://{pack_version_id}/metadata',
            'grantpack://requirement/{requirement_id}',
            'evidence://{user_evidence_id}',
            'evidence://claim/{claim_id}/bindings',
        }.issubset(resources))
