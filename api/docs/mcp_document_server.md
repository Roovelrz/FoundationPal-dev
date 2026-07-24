# Grant Proposal Document MCP

The server is a stdio MCP process. It accepts only `file_id` as a tool argument. Caller and organization context are supplied by the trusted process environment, never by the MCP client.

```powershell
Set-Location <项目根目录>\api
$env:MCP_CALLER_ID = 'your_user_id'
$env:MCP_ORGANIZATION_ID = 'your_organization_id'
F:\Anaconda\envs\fundagent\python.exe -m files.mcp_server
```

Tools:

- `parse_document`
- `extract_document_structure`
- `extract_requirements`

Resources:

- `document://{file_id}/metadata`
- `document://{file_id}/page/{page_number}`
- `document://{file_id}/section/{section_index}`

Only organization-bound files owned by the configured caller can be read. The server rejects unscoped files, cross-workspace access, unsupported types, encrypted or malformed PDFs, oversized documents, page-limit violations, and concurrent parsing beyond its configured capacity. `parse_document` returns resource links instead of the complete document content.
