import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { Proposals } from '../main.jsx'

// Minimal fetch mock with routing logic used in main.jsx's api()
function mockFetch(routes) {
  const fn = vi.fn(async (url, opts) => {
    const path = String(url).replace(/^[^/]*\/api/, '')
    const key = `${opts?.method || 'GET'} ${path}`
    const handler = routes[key]
    if (!handler) return new Response(JSON.stringify({}), { status: 404 })
    const body = opts?.body ? JSON.parse(opts.body) : null
    const res = await handler({ path, body, opts })
    return new Response(JSON.stringify(res.body || {}), { status: res.status || 200, headers: { 'Content-Type': 'application/json' } })
  })
  global.fetch = fn
  return fn
}

describe('Author final-format flow', () => {
  it('shows final-format only after all sections approved and calls /ai/format', async () => {
    const token = 't'
  const proposal = {
    id: 1,
    content: { meta: { title: 'T' }, sections: {} },
    sections: [
      { id: 101, key: 'summary', title: 'Executive Summary', state: 'draft', draft_content: 'S', approved_content: '', locked: false },
      { id: 102, key: 'narrative', title: 'Project Narrative', state: 'draft', draft_content: '', approved_content: '', locked: false },
    ],
    schema_version: 'v1',
    state: 'draft',
  }
  const serverState = { proposal: JSON.parse(JSON.stringify(proposal)) }
    const routes = {
  'GET /proposals/': async () => ({ body: [serverState.proposal] }),
      'GET /usage': async () => ({ body: { tier: 'pro', status: 'active' } }),
      'POST /ai/plan': async () => ({ body: { schema_version: 'v1', sections: [ { id: 'summary', title: 'Executive Summary', inputs: [] }, { id: 'narrative', title: 'Project Narrative', inputs: [] } ] } }),
      'POST /ai/write': async () => {
        serverState.proposal.sections[1].draft_content = 'Draft...'
        return { body: { draft_text: 'Draft...' } }
      },
      'POST /sections/101/promote': async () => {
        Object.assign(serverState.proposal.sections[0], { state: 'approved', approved_content: 'S', locked: true })
        return { body: { status: 'promoted', section_id: 101 } }
      },
      'POST /sections/102/promote': async () => {
        Object.assign(serverState.proposal.sections[1], { state: 'approved', approved_content: 'Draft...', locked: true })
        return { body: { status: 'promoted', section_id: 102 } }
      },
      'POST /ai/format': async ({ body }) => ({ body: { formatted_text: `[gemini:final_format]\n\n${body.full_text}` } }),
    }
    const fetchSpy = mockFetch(routes)

    render(<Proposals token={token} />)

    // Wait for list
    await screen.findByText(/我的基金申请/i)

    // Open author
    const openBtn = await screen.findByRole('button', { name: /打开撰写区/i })
    fireEvent.click(openBtn)

  // Start plan and wait for section 1 to appear
  const startBtn = await screen.findByRole('button', { name: '生成章节规划' })
  fireEvent.click(startBtn)
  await screen.findByText(/第 1 章，共 2 章/i)

    // Approve first section
  const approveBtn = await screen.findByRole('button', { name: '审批并保存' })
  fireEvent.click(approveBtn)
  // After save, UI advances to section 2
  await screen.findByText(/第 2 章，共 2 章/i)

    // Move to next section (narrative), author a draft and approve it
  const writeBtn = await screen.findByRole('button', { name: '生成本章草稿' })
  fireEvent.click(writeBtn)
  // Wait for draft to be available which enables Approve & Save
  await screen.findByTestId('draft-text')
  const approveBtn2 = await screen.findByRole('button', { name: '审批并保存' })
    fireEvent.click(approveBtn2)

  // Final-format controls should now be visible
  const runBtn = await screen.findByRole('button', { name: /生成最终定稿/i })
    fireEvent.click(runBtn)

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled()
      const called = fetchSpy.mock.calls.some(([url]) => String(url).includes('/api/ai/format'))
      expect(called).toBe(true)
    })
    // Preview should render
    await screen.findByText(/定稿预览/i)
  })
})
