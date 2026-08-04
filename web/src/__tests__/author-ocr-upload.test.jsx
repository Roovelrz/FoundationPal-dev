import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { Proposals } from '../main.jsx'

function mockFetch(routes) {
  const fn = vi.fn(async (url, opts) => {
    const path = String(url).replace(/^[^/]*\/api/, '')
    const key = `${opts?.method || 'GET'} ${path}`
    const handler = routes[key]
    if (!handler) return new Response(JSON.stringify({}), { status: 404 })
    const body = opts?.body instanceof FormData ? opts.body : (opts?.body ? JSON.parse(opts.body) : null)
    const res = await handler({ path, body, opts })
    return new Response(JSON.stringify(res.body || {}), { status: res.status || 200, headers: { 'Content-Type': 'application/json' } })
  })
  global.fetch = fn
  return fn
}

describe('Authoring OCR upload', () => {
  it('shows OCR preview after uploading a file and sends file_refs on write', async () => {
    const token = 't'
    const proposal = { id: 1, content: { meta: { title: 'T', user_setup: { ready: true }, intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' } }, sections: {} }, schema_version: 'v1', state: 'draft' }
    const serverState = { proposal: JSON.parse(JSON.stringify(proposal)) }
    const routes = {
      'GET /proposals/': async () => ({ body: [serverState.proposal] }),
      'POST /ai/plan': async ({ body }) => {
        expect(body.proposal_id).toBe(1)
        return { body: { schema_version: 'v1', sections: [ { id: 'summary', title: 'Executive Summary', inputs: [] } ] } }
      },
      'POST /ai/write': async ({ body }) => {
        // Expect file_refs to be present and include the uploaded file
        if (!body || !Array.isArray(body.file_refs) || body.file_refs.length !== 1) {
          return { status: 400, body: { error: 'missing_file_refs' } }
        }
        const f = body.file_refs[0]
        expect(f.url).toContain('/media/uploads/fake.pdf')
        expect(f.ocr_text).toContain('This is extracted text')
        return { body: { draft_text: 'Draft S' } }
      },
      'PATCH /proposals/1/': async ({ body }) => { serverState.proposal = { ...(serverState.proposal || {}), ...body, id: 1 }; return { body: serverState.proposal, status: 200 } },
      'POST /files': async () => ({ body: { id: 10, url: '/media/uploads/fake.pdf', content_type: 'application/pdf', size: 1234, ocr_text: 'This is extracted text' } }),
    }
    mockFetch(routes)

    render(<Proposals token={token} />)

    await screen.findByText(/我的基金申请/i)
    fireEvent.click(await screen.findByRole('button', { name: /打开撰写区/i }))
    fireEvent.click(await screen.findByRole('button', { name: '生成章节规划' }))
    await screen.findByText(/第 1 章，共 1 章/i)

    const fileInput = await screen.findByLabelText(/上传本章补充材料/i)
    const file = new File([new Uint8Array([0x25,0x50,0x44,0x46])], 'sample.pdf', { type: 'application/pdf' })
    await waitFor(() => {
      fireEvent.change(fileInput, { target: { files: [file] } })
    })

  // Expect OCR preview area to show the returned text
    await screen.findByText(/材料文字预览/i)
    const ta = await screen.findByDisplayValue(/This is extracted text/i)
    expect(ta).toBeTruthy()

  // Click Write and ensure the request includes file_refs
  const writeBtn = await screen.findByRole('button', { name: '生成本章草稿' })
  fireEvent.click(writeBtn)
  // Draft text renders inside a <pre>, so assert by text content
  await screen.findByText(/Draft S/)
  })
})
