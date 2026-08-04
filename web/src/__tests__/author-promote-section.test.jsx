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

describe('Author section approval workflow', () => {
  it('submits the existing workflow before the human approval decision', async () => {
    const proposal = {
      id: 1,
      content: { meta: { title: 'T', user_setup: { ready: true }, intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' } }, sections: {} },
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
    let workflowPayload = null
    let pendingTasks = []
    const routes = {
      'GET /proposals/': async () => ({ body: [serverState.proposal] }),
      'GET /ai/human-tasks?proposal_id=1': async () => ({ body: { tasks: pendingTasks } }),
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
      'PATCH /ai/sections/101/draft': async ({ body }) => {
        serverState.proposal.sections[0].draft_content = body.draft_text
        return { body: { draft_text: body.draft_text, previous_draft: '' } }
      },
      'POST /ai/workflow/run': async ({ body }) => {
        workflowPayload = body
        pendingTasks = [{
          id: 11,
          thread_id: 'workflow-1:section_approval',
          node: 'section_approval',
          status: 'pending',
          input: { section_key: 'summary', section_title: 'Executive Summary', draft_summary: body.draft },
          model_output: { review_summary: 'human_review' },
          decision: {},
        }]
        return { body: { run_id: 'workflow-1', status: 'awaiting_human_approval', trace: [] } }
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
    fireEvent.click(screen.getByRole('tab', { name: /3 人工审核与修订/ }))
    fireEvent.click(await screen.findByRole('button', { name: '提交章节审批' }))

    await waitFor(() => {
      expect(workflowPayload).toMatchObject({
        proposal_id: 1,
        section_key: 'summary',
        draft: 'Persisted draft',
        plan: [{ section_key: 'summary', title: 'Executive Summary', questions: [] }],
      })
    })
    expect(await screen.findByTestId('section-approval-tasks')).toBeInTheDocument()
    expect(fetchSpy.mock.calls.some(([url, opts]) => (
      String(url).endsWith('/api/sections/101/promote') && opts?.method === 'POST'
    ))).toBe(false)
    expect(fetchSpy.mock.calls.some(([url, opts]) => (
      String(url).endsWith('/api/proposals/1/') && opts?.method === 'PATCH'
    ))).toBe(false)
  })
})
