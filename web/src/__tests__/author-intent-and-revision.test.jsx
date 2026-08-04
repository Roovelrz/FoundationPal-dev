import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { AuthorPanel } from '../pages/Dashboard.jsx'

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function setupResponse(proposalId) {
  return {
    proposal_id: proposalId,
    ready: true,
    research_direction: '测试方向',
    core_problem: '',
    guideline_ready: true,
    guideline_count: 1,
    evidence_count: 0,
    guideline_files: [],
    evidence_files: [],
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('普通用户写作流程', () => {
  it('requires only the two writing-goal choices before planning', async () => {
    let intakePayload = null
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      if (path.endsWith('/ai/proposals/71/setup')) return jsonResponse(setupResponse(71))
      if (path.endsWith('/ai/intake')) {
        intakePayload = JSON.parse(options.body)
        return jsonResponse({ session_id: 1, status: 'active' }, 201)
      }
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token="token"
        orgId="1"
        proposal={{ id: 71, author: 1, content: { meta: { title: '新项目', user_setup: { ready: true } }, sections: {} }, sections: [], schema_version: 'v1' }}
      />,
    )

    const planButton = await screen.findByRole('button', { name: '生成章节规划' })
    expect(planButton).toBeDisabled()
    expect(screen.getByText('你现在希望系统做什么')).toBeInTheDocument()
    expect(screen.getByText('你希望做到什么程度')).toBeInTheDocument()
    expect(screen.queryByText(/规则包审核|ProposalBrief|问题预算/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('从头规划并起草'))
    fireEvent.click(screen.getByLabelText('标准完善'))
    fireEvent.click(screen.getByRole('button', { name: '确认工作目标' }))

    await waitFor(() => expect(intakePayload).toEqual({
      proposal_id: 71,
      task_mode: 'plan_from_scratch',
      quality_level: 'standard',
      inputs: {},
      user_overrides: {},
    }))
    expect(planButton).toBeEnabled()
  })

  it('edits the current draft, keeps the immediate previous draft collapsed, and clears a completed request', async () => {
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      if (path.endsWith('/ai/proposals/72/setup')) return jsonResponse(setupResponse(72))
      if (path.endsWith('/ai/sections/720/evidence')) return jsonResponse({ evidence: [] })
      if (path.endsWith('/ai/revise')) return jsonResponse({ draft_text: '修订后的草稿' })
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token="token"
        orgId="1"
        proposal={{
          id: 72,
          author: 1,
          schema_version: 'v1',
          content: {
            meta: {
              title: '修订项目',
              user_setup: { ready: true },
              intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' },
            },
            sections: {},
          },
          sections: [{
            id: 720,
            key: 'summary',
            title: '摘要',
            state: 'draft',
            questions: ['研究目标是什么？'],
            answers: {},
            draft_content: '原始草稿',
            previous_draft: '更早草稿',
            approved_content: '',
            locked: false,
          }],
        }}
      />,
    )

    fireEvent.click(await screen.findByRole('tab', { name: /3 人工审核与修订/ }))
    const previous = screen.getByText('查看修改前草稿').closest('details')
    expect(previous).not.toHaveAttribute('open')
    expect(screen.getByTestId('current-draft-editor')).toHaveValue('原始草稿')

    const request = screen.getByPlaceholderText('例如：补充前期基础，明确技术路线，并删减重复表述')
    fireEvent.change(request, { target: { value: '补充论证依据' } })
    fireEvent.click(screen.getByRole('button', { name: '按要求修订' }))

    await waitFor(() => expect(screen.getByTestId('current-draft-editor')).toHaveValue('修订后的草稿'))
    expect(request).toHaveValue('')
    fireEvent.click(screen.getByText('查看修改前草稿'))
    expect(screen.getByText('原始草稿')).toBeInTheDocument()
  })
})
