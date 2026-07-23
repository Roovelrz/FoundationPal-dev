import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import { Proposals } from '../main.jsx'

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

describe('Author final-format visibility', () => {
  it('hides final-format controls until all sections approved', async () => {
    const token = 't'
    const proposal = {
      id: 1,
      content: { meta: { title: 'T' }, sections: {} },
      sections: [
        { id: 101, key: 'summary', title: 'Executive Summary', state: 'draft', draft_content: '', approved_content: '', locked: false },
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
        serverState.proposal.sections[0].draft_content = 'Draft S'
        return { body: { draft_text: 'Draft S' } }
      },
      'POST /sections/101/promote': async () => {
        Object.assign(serverState.proposal.sections[0], { state: 'approved', approved_content: 'Draft S', locked: true })
        return { body: { status: 'promoted', section_id: 101 } }
      },
    }
    mockFetch(routes)

    render(<Proposals token={token} />)

    await screen.findByText(/我的基金申请/i)
    fireEvent.click(await screen.findByRole('button', { name: /打开撰写区/i }))
    fireEvent.click(await screen.findByRole('button', { name: '生成章节规划' }))
    await screen.findByText(/第 1 章，共 2 章/i)
    fireEvent.click(await screen.findByRole('button', { name: '生成本章草稿' }))
  await screen.findByTestId('draft-text')
    fireEvent.click(await screen.findByRole('button', { name: '审批并保存' }))
    await screen.findByText(/第 2 章，共 2 章/i)

    // Final-format controls should NOT be visible yet (one section remaining)
    const runBtns = screen.queryAllByRole('button', { name: /生成最终定稿/i })
    expect(runBtns.length).toBe(0)
  })
})
