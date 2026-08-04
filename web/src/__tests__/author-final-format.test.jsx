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
    content: { meta: { title: 'T', user_setup: { ready: true }, intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' } }, sections: {} },
    sections: [
      { id: 101, key: 'summary', title: 'Executive Summary', state: 'draft', draft_content: 'S', approved_content: '', locked: false },
      { id: 102, key: 'narrative', title: 'Project Narrative', state: 'draft', draft_content: '', approved_content: '', locked: false },
    ],
    schema_version: 'v1',
    state: 'draft',
  }
  const serverState = { proposal: JSON.parse(JSON.stringify(proposal)) }
    let pendingTasks = []
    const fullDraft = {
      draft_text: '# T\n\n## Executive Summary\nS\n\n## Project Narrative\nDraft...',
      version: 1,
      approval_status: 'draft',
      section_keys: ['summary', 'narrative'],
    }
    const approveTask = (sectionKey) => {
      const section = serverState.proposal.sections.find(item => item.key === sectionKey)
      Object.assign(section, {
        state: 'approved',
        approved_content: section.draft_content,
        locked: true,
      })
      pendingTasks = []
      return { body: { status: 'completed' } }
    }
    const routes = {
      'GET /proposals/': async () => ({ body: [serverState.proposal] }),
      'GET /ai/human-tasks?proposal_id=1': async () => ({ body: { tasks: pendingTasks } }),
      'GET /ai/proposals/1/full-draft': async () => ({ body: fullDraft }),
      'PATCH /ai/proposals/1/full-draft': async ({ body }) => ({
        body: { ...fullDraft, draft_text: body.draft_text, previous_draft: fullDraft.draft_text },
      }),
      'POST /ai/plan': async () => ({ body: { schema_version: 'v1', sections: [ { id: 'summary', title: 'Executive Summary', inputs: [] }, { id: 'narrative', title: 'Project Narrative', inputs: [] } ] } }),
      'POST /ai/write': async () => {
        serverState.proposal.sections[1].draft_content = 'Draft...'
        return { body: { draft_text: 'Draft...' } }
      },
      'PATCH /ai/sections/102/draft': async ({ body }) => {
        serverState.proposal.sections[1].draft_content = body.draft_text
        return { body: { draft_text: body.draft_text, previous_draft: '' } }
      },
      'POST /ai/workflow/run': async ({ body }) => {
        const taskId = body.section_key === 'summary' ? 11 : 12
        const section = serverState.proposal.sections.find(item => item.key === body.section_key)
        pendingTasks = [{
          id: taskId,
          thread_id: `workflow-${taskId}:section_approval`,
          node: 'section_approval',
          status: 'pending',
          input: { section_key: body.section_key, section_title: section.title, draft_summary: body.draft },
          model_output: { review_summary: 'human_review' },
          decision: {},
        }]
        return { body: { run_id: `workflow-${taskId}`, status: 'awaiting_human_approval', trace: [] } }
      },
      'POST /ai/human-tasks/11/decision': async () => approveTask('summary'),
      'POST /ai/human-tasks/12/decision': async () => approveTask('narrative'),
      'POST /ai/human-tasks': async () => {
        const task = {
          id: 13,
          thread_id: 'full-draft-1-1',
          node: 'final_export_confirmation',
          status: 'pending',
          input: { kind: 'full_draft', draft_title: '审批后全文草稿', draft_version: 1, draft_text: fullDraft.draft_text },
          model_output: {},
          decision: {},
        }
        pendingTasks = [task]
        return { body: task, status: 201 }
      },
      'POST /ai/human-tasks/13/decision': async () => {
        fullDraft.approval_status = 'approved'
        pendingTasks = []
        return { body: { id: 13, status: 'approved' } }
      },
      'POST /ai/format': async () => ({ body: { formatted_text: '[gemini:final_format]\n\nFormatted final draft' } }),
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
  const approveBtn = await screen.findByRole('button', { name: '提交章节审批' })
  fireEvent.click(approveBtn)
  fireEvent.click(await screen.findByRole('button', { name: '通过并锁定章节' }))
  // After save, UI advances to section 2
  await screen.findByText(/第 2 章，共 2 章/i)

    // Move to next section (narrative), author a draft and approve it
  const writeBtn = await screen.findByRole('button', { name: '生成本章草稿' })
  fireEvent.click(writeBtn)
  // Wait for draft to be available which enables Approve & Save
  await screen.findByTestId('draft-text')
  fireEvent.click(screen.getByRole('tab', { name: /3 人工审核与修订/ }))
  const approveBtn2 = await screen.findByRole('button', { name: '提交章节审批' })
    fireEvent.click(approveBtn2)
    fireEvent.click(await screen.findByRole('button', { name: '通过并锁定章节' }))

  // The approved full draft requires its own human approval before final formatting.
  fireEvent.click(await screen.findByRole('button', { name: '提交全文审批' }))
  fireEvent.click(await screen.findByRole('button', { name: '通过全文审批' }))
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
