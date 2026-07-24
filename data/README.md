# MCP PDF Test Corpus

This folder contains 10 anonymous PDF fixtures for MCP document-service validation.

## Coverage

| File | Scenario | Expected result |
|---|---|---|
| 01 | Small native text | Accept |
| 02 | 12-page native text | Accept |
| 03 | Chinese Unicode text | Accept |
| 04 | Table and form-like layout | Accept |
| 05 | Scan-only, no text layer | Accept with OCR or mark OCR required |
| 06 | Mixed native text and scanned page | Accept and preserve page order |
| 07 | Encrypted | Structured rejection unless passwords are supported |
| 08 | Corrupt and truncated | Structured invalid-PDF rejection |
| 09 | Oversized valid PDF, 88.145 MB | Reject when above configured size limit |
| 10 | 300 pages | Reject or cap when above configured page limit |

## Encrypted fixture

Password: `mcp-test`

## Concurrency

Upload or parse files 01 through 06 at parallelism 2, 5, and 10. Validate request throttling, timeouts, idempotency, and absence of duplicate AIResource records.

## Ownership boundary

For each valid file, create records under at least two organizations and two proposals. MCP calls should accept only `file_id`, derive organization and proposal from persisted ownership, and reject cross-organization access before reading bytes.
