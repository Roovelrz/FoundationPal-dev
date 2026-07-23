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
    const body = opts?.body ? JSON.parse(opts.body) : null
    const res = await handler({ path, body, opts })
    return new Response(JSON.stringify(res.body || {}), {
      status: res.status || 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  global.fetch = fn
  return fn
}

describe('Author section promotion', () => {
  it('approves through the section promote endpoint without patching Proposal.content', async () => {
    const proposal = {
      id: 1,
      content: { meta: { title: 'T' }, sections: {} },
      sections: [
        {
          id: 101,
          key: 'summary',
          title: 'Executive Summary',
          state: 'draft',
          draft_content: '',
          approved_content: '',
          locked: false,
        },
      ],
      schema_version: 'v1',
      state: 'draft',
    }
    const serverState = { proposal: JSON.parse(JSON.stringify(proposal)) }
    const routes = {
      'GET /proposals/': async () => ({ body: [serverState.proposal] }),
      'GET /usage': async () => ({ body: { tier: 'pro', status: 'active' } }),
      'POST /ai/plan': async () => ({
        body: {
          schema_version: 'v1',
          sections: [{ id: 'summary', title: 'Executive Summary', inputs: [] }],
          created_sections: [],
        },
      }),
      'POST /ai/write': async () => {
        serverState.proposal.sections[0].draft_content = 'Persisted draft'
        return { body: { draft_text: 'Persisted draft' } }
      },
      'POST /sections/101/promote': async () => {
        const section = serverState.proposal.sections[0]
        section.state = 'approved'
        section.approved_content = section.draft_content
        section.locked = true
        return { body: { status: 'promoted', section_id: 101 } }
      },
    }
    const fetchSpy = mockFetch(routes)

    render(<Proposals token='t' />)

    await screen.findByText(/我的基金申请/i)
    fireEvent.click(await screen.findByRole('button', { name: /打开撰写区/i }))
    fireEvent.click(await screen.findByRole('button', { name: '生成章节规划' }))
    await screen.findByText(/第 1 章，共 1 章/i)
    fireEvent.click(await screen.findByRole('button', { name: '生成本章草稿' }))
    await screen.findByText(/Persisted draft/i)
    fireEvent.click(await screen.findByRole('button', { name: '审批并保存' }))

    await waitFor(() => {
      expect(fetchSpy.mock.calls.some(([url, opts]) => (
        String(url).endsWith('/api/sections/101/promote') && opts?.method === 'POST'
      ))).toBe(true)
    })
    expect(fetchSpy.mock.calls.some(([url, opts]) => (
      String(url).endsWith('/api/proposals/1/') && opts?.method === 'PATCH'
    ))).toBe(false)
  })
})
