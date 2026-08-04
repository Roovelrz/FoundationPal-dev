import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { Proposals } from '../main.jsx'
import { AuthorPanel } from '../pages/Dashboard.jsx'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

describe('Workflow bug regressions', () => {
  it('creates the proposal in the selected workspace', async () => {
    let createOrgHeader = null
    let createdProposal = null
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/proposals/') && method === 'GET') return jsonResponse(createdProposal ? [createdProposal] : [])
      if (path.endsWith('/proposals/') && method === 'POST') {
        createOrgHeader = options.headers['X-Org-ID']
        createdProposal = {
          id: 21,
          org: 2,
          workspace_number: 1,
          state: 'draft',
          content: JSON.parse(options.body).content,
          sections: [],
        }
        return jsonResponse(createdProposal, 201)
      }
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({ items: [] })
    })

    render(
      <MemoryRouter>
        <Proposals token="token" selectedOrgId="2" />
      </MemoryRouter>
    )

    fireEvent.change(await screen.findByPlaceholderText('输入新项目标题'), {
      target: { value: '工作区二项目' },
    })
    fireEvent.click(screen.getByLabelText('国自然'))
    fireEvent.click(screen.getByRole('button', { name: '新建申请' }))

    await waitFor(() => expect(createOrgHeader).toBe('2'))
    expect(await screen.findByText(/编号 1/)).toBeInTheDocument()
    expect(screen.queryByText(/编号 21/)).not.toBeInTheDocument()
  })

  it('keeps projects isolated while switching workspaces', async () => {
    const rows = {
      1: [{ id: 91, org: 1, workspace_number: 1, state: 'draft', content: { meta: { title: '工作区一项目' } }, sections: [] }],
      2: [{ id: 22, org: 2, workspace_number: 1, state: 'draft', content: { meta: { title: '工作区二项目' } }, sections: [] }],
    }
    global.fetch = vi.fn(async (url, options = {}) => {
      if (String(url).endsWith('/proposals/') && (options.method || 'GET') === 'GET') {
        return jsonResponse(rows[options.headers['X-Org-ID']] || [])
      }
      return jsonResponse({})
    })

    const view = render(
      <MemoryRouter>
        <Proposals token="token" selectedOrgId="1" />
      </MemoryRouter>
    )

    expect(await screen.findByText('工作区一项目')).toBeInTheDocument()
    view.rerender(
      <MemoryRouter>
        <Proposals token="token" selectedOrgId="2" />
      </MemoryRouter>
    )
    expect(await screen.findByText('工作区二项目')).toBeInTheDocument()
    expect(screen.queryByText('工作区一项目')).not.toBeInTheDocument()
  })

  it('shows a clear selected-workspace error when creation is forbidden', async () => {
    global.fetch = vi.fn(async (url, options = {}) => {
      if (String(url).endsWith('/proposals/') && (options.method || 'GET') === 'GET') return jsonResponse([])
      if (String(url).endsWith('/proposals/') && options.method === 'POST') {
        return jsonResponse({ error: 'invalid_org_scope' }, 403)
      }
      return jsonResponse({})
    })

    render(
      <MemoryRouter>
        <Proposals token="token" selectedOrgId="2" />
      </MemoryRouter>
    )
    fireEvent.change(await screen.findByPlaceholderText('输入新项目标题'), { target: { value: '待创建项目' } })
    fireEvent.click(screen.getByLabelText('国自然'))
    fireEvent.click(screen.getByRole('button', { name: '新建申请' }))

    expect(await screen.findByText(/当前账号无权操作这个工作区/)).toBeInTheDocument()
  })

  it('moves archived proposals into the recycle bin with feedback', async () => {
    const proposal = {
      id: 31,
      org: 1,
      author: 1,
      state: 'draft',
      content: { meta: { title: '待归档项目' }, sections: {} },
      sections: [],
      schema_version: 'v1',
    }
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/proposals/') && method === 'GET') return jsonResponse([clone(proposal)])
      if (path.endsWith('/proposals/31/') && method === 'PATCH') {
        proposal.state = JSON.parse(options.body).state
        return jsonResponse(clone(proposal))
      }
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({ items: [] })
    })

    render(
      <MemoryRouter>
        <Proposals token="token" selectedOrgId="1" />
      </MemoryRouter>
    )

    fireEvent.click(await screen.findByRole('button', { name: '归档' }))
    expect(await screen.findByText(/已移入回收站/)).toBeInTheDocument()
    const trashButton = screen.getByRole('button', { name: /回收站/ })
    expect(trashButton.closest('aside').lastElementChild).toHaveClass('fund-sidebar-footer')
    fireEvent.click(trashButton)
    expect(await screen.findByRole('button', { name: '恢复项目' })).toBeInTheDocument()
  })

  it('shows thinking feedback and moves to the generated chapter', async () => {
    let resolvePlan
    const planResponse = new Promise(resolve => { resolvePlan = resolve })
    global.fetch = vi.fn(async (url) => {
      const path = String(url)
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.endsWith('/ai/plan')) return planResponse
      return jsonResponse({ items: [] })
    })

    render(
      <AuthorPanel
        token="token"
        orgId="1"
        proposal={{
          id: 41,
          author: 1,
          content: { meta: { title: '反馈测试', user_setup: { ready: true }, intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' } }, sections: {} },
          sections: [],
          schema_version: 'v1',
        }}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '生成章节规划' }))
    expect(await screen.findByText('深度思考中，请稍候')).toBeInTheDocument()
    resolvePlan(jsonResponse({
      schema_version: 'v1',
      sections: [{ id: 'summary', title: '摘要', inputs: [] }],
    }))
    expect(await screen.findByText('逐题回答')).toBeInTheDocument()
    expect(screen.queryByText('内容生成完毕！')).not.toBeInTheDocument()
  })

  it('opens planning information after an unconfirmed planning session blocks generation', async () => {
    let savedPlanningPayload = null
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.endsWith('/ai/proposals/73/setup')) return jsonResponse({ proposal_id: 73, ready: true, guideline_ready: true })
      if (path.endsWith('/ai/plan') && method === 'POST') {
        return jsonResponse({ error: 'grill_confirmation_required' }, 409)
      }
      if (path.includes('/ai/grill?proposal_id=73&mode=planning')) {
        return jsonResponse({
          mode: 'planning',
          question: {
            index: 1,
            prompt: '本项目申报什么类别，并计划研究哪个方向？',
            fields: ['funding_category', 'research_direction'],
          },
          question_count: 0,
          max_questions: 5,
          completion_reason: '',
          confirmed: false,
        })
      }
      if (path.endsWith('/ai/grill') && method === 'POST') {
        savedPlanningPayload = JSON.parse(options.body)
        return jsonResponse({
          mode: 'planning',
          question: {
            index: 2,
            prompt: '当前可用于支撑项目的条件有哪些？',
            fields: ['existing_conditions'],
          },
          question_count: 1,
          max_questions: 5,
          completion_reason: '',
          confirmed: false,
        })
      }
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 73,
          author: 1,
          content: {
            meta: {
              title: '规划补充测试',
              user_setup: { ready: true },
              intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' },
            },
            sections: {},
          },
          sections: [],
          schema_version: 'v1',
        }}
      />
    )

    fireEvent.click(await screen.findByRole('button', { name: '生成章节规划' }))

    expect(await screen.findByTestId('planning-info')).toBeInTheDocument()
    expect(screen.getByText(/本项目申报什么类别，并计划研究哪个方向/)).toBeInTheDocument()
    expect(screen.getByText(/对暂时无法判断的问题，可留空或如实填写：不清楚/)).toBeInTheDocument()
    expect(screen.getAllByPlaceholderText('请填写已掌握的信息；若无可提供信息，可留空或如实填写：不清楚')).toHaveLength(2)
    expect(screen.getByRole('button', { name: '上一题' })).toBeDisabled()
    const nextButton = screen.getByRole('button', { name: '下一题' })
    expect(nextButton).toBeEnabled()
    expect(screen.getByRole('button', { name: '结束补充' })).toBeInTheDocument()
    expect(global.fetch.mock.calls.some(([url]) => String(url).includes('/ai/grill?proposal_id=73&mode=planning'))).toBe(true)

    fireEvent.click(nextButton)

    await waitFor(() => {
      expect(savedPlanningPayload).toEqual({
        proposal_id: 73,
        mode: 'planning',
        answers: { funding_category: '', research_direction: '' },
        skip: false,
      })
    })
    expect(await screen.findByText(/当前可用于支撑项目的条件有哪些/)).toBeInTheDocument()
  })

  it('restores a pending section approval task and returns to editing', async () => {
    let pending = true
    let decisionPayload = null
    const task = {
      id: 9,
      thread_id: 'approval-74',
      node: 'section_approval',
      status: 'pending',
      input: {
        section_key: 'summary',
        section_title: '摘要',
        draft_summary: '待审批草稿',
      },
      model_output: { review_summary: '审查结论：approve' },
      decision: {},
    }
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.endsWith('/ai/proposals/74/setup')) return jsonResponse({ proposal_id: 74, ready: true, guideline_ready: true })
      if (path.includes('/ai/human-tasks?proposal_id=74')) return jsonResponse({ tasks: pending ? [task] : [] })
      if (path.endsWith('/ai/human-tasks/9/decision') && method === 'POST') {
        decisionPayload = JSON.parse(options.body)
        pending = false
        return jsonResponse({ ...task, status: 'ready_after_edit', decision: decisionPayload })
      }
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 74,
          author: 1,
          content: {
            meta: {
              title: '章节审批测试',
              user_setup: { ready: true },
              intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' },
            },
            sections: {},
          },
          sections: [
            { id: 740, key: 'summary', title: '摘要', order: 0, state: 'draft', draft_content: '待审批草稿', approved_content: '', inputs: [], answers: {} },
          ],
          schema_version: 'v1',
        }}
      />
    )

    expect(await screen.findByTestId('section-approval-tasks')).toBeInTheDocument()
    expect(screen.getByText('待审批章节')).toBeInTheDocument()
    expect(screen.getByText('摘要')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '退回修改' }))

    await waitFor(() => expect(decisionPayload).toEqual({ thread_id: 'approval-74', action: 'edit' }))
    await waitFor(() => expect(screen.queryByTestId('section-approval-tasks')).not.toBeInTheDocument())
    expect(screen.getByRole('tab', { name: /3 人工审核与修订/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps accepted section pre-review in its own dialog and card', async () => {
    const review = {
      summary: '本章定位清楚，但阶段目标需要量化。',
      strengths: ['已明确说明项目服务对象。'],
      issues: [{
        problem: '阶段目标不够具体。',
        reason: '草稿没有给出可验收的阶段指标。',
        direction: '补充量化节点和验收标准。',
      }],
      revision_request: '补充量化节点和验收标准。',
    }
    const preReviewAlert = vi.spyOn(window, 'alert').mockImplementation(() => {})
    let preReviewCount = 0
    let resolvePreReview
    const firstPreReviewResponse = new Promise(resolve => { resolvePreReview = resolve })
    let resolveRevision
    const revisionResponse = new Promise(resolve => { resolveRevision = resolve })
    let task = {
      id: 76,
      thread_id: 'approval-76',
      node: 'section_approval',
      status: 'pending',
      input: { section_key: 'summary', section_title: '摘要' },
      model_output: {},
      decision: {},
    }
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.endsWith('/ai/proposals/76/setup')) return jsonResponse({ proposal_id: 76, ready: true, guideline_ready: true })
      if (path.includes('/ai/human-tasks?proposal_id=76')) return jsonResponse({ tasks: [task] })
      if (path.endsWith('/ai/revise') && method === 'POST') return revisionResponse
      if (path.endsWith('/ai/human-tasks/76/pre-review') && method === 'POST') {
        const body = options.body ? JSON.parse(options.body) : {}
        if (body.action === 'accept') task = {
          ...task,
          model_output: { ...task.model_output, pre_review: review, pre_review_status: 'accepted' },
        }
        else if (body.action === 'dismiss') task = {
          ...task,
          model_output: { pre_review_request_count: task.model_output.pre_review_request_count || 0 },
        }
        else {
          preReviewCount += 1
          task = {
            ...task,
            model_output: { pre_review: review, pre_review_status: 'pending', pre_review_request_count: preReviewCount },
          }
          if (preReviewCount === 1) return firstPreReviewResponse
        }
        return jsonResponse(task)
      }
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 76,
          author: 1,
          content: {
            meta: {
              title: '章节预评审测试',
              user_setup: { ready: true },
              intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' },
            },
            sections: {},
          },
          sections: [{ id: 760, key: 'summary', title: '摘要', state: 'draft', draft_content: '当前草稿全文', approved_content: '', inputs: [], answers: {} }],
          schema_version: 'v1',
        }}
      />,
    )

    expect(await screen.findByTestId('section-approval-tasks')).toBeInTheDocument()
    expect(screen.queryByText('查看草稿摘要')).not.toBeInTheDocument()
    expect(screen.queryByText(/审查摘要/)).not.toBeInTheDocument()
    const approvalActions = screen.getByText('摘要').closest('article').querySelector('.fund-section-approval-actions')
    expect(approvalActions.lastElementChild).toHaveTextContent('退回修改')
    fireEvent.click(screen.getByRole('button', { name: '章节预评审' }))
    expect(await screen.findByText('深度思考中，请等待预审批结果。')).toBeInTheDocument()
    resolvePreReview(jsonResponse(task))
    expect(await screen.findByRole('dialog', { name: '章节预评审' })).toBeInTheDocument()
    expect(screen.getByText('阶段目标不够具体。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '采纳' }))
    expect(await screen.findByText('是否需要根据评审内容重新修改草稿？')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '否' }))
    expect(await screen.findByText('已采纳的章节预评审')).toBeInTheDocument()
    expect(screen.getByText('已采纳的章节预评审').parentElement).toHaveTextContent('补充量化节点和验收标准。')
    fireEvent.click(screen.getByRole('button', { name: '章节预评审' }))
    expect(preReviewAlert).toHaveBeenCalledWith('请谨慎采纳章节预审批意见！')
    fireEvent.click(await screen.findByRole('button', { name: '采纳' }))
    fireEvent.click(await screen.findByRole('button', { name: '是' }))
    expect(await screen.findByText('已采纳审批结果，正在根据建议重新优化该章节。')).toBeInTheDocument()
    resolveRevision(jsonResponse({ draft_text: '已根据预评审修订' }))
    expect(await screen.findByDisplayValue('已根据预评审修订')).toBeInTheDocument()
    expect(screen.queryByText('已采纳的章节预评审')).not.toBeInTheDocument()
  })

  it('keeps an unapproved draft when moving between sections', async () => {
    const proposal = {
      id: 51,
      org: 1,
      author: 1,
      state: 'draft',
      content: { meta: { title: '草稿保留测试' }, sections: {} },
      schema_version: 'v1',
      sections: [
        { id: 501, key: 'first', title: '第一章', order: 0, state: 'draft', draft_content: '', approved_content: '', inputs: [], answers: {} },
        { id: 502, key: 'second', title: '第二章', order: 1, state: 'draft', draft_content: '', approved_content: '', inputs: [], answers: {} },
      ],
    }
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      if (path.endsWith('/proposals/')) return jsonResponse([clone(proposal)])
      if (path.endsWith('/ai/write')) {
        proposal.sections[0].draft_content = '未审批但已经持久化的草稿'
        return jsonResponse({ draft_text: proposal.sections[0].draft_content })
      }
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({ items: [] })
    })

    render(
      <MemoryRouter>
        <Proposals token="token" selectedOrgId="1" />
      </MemoryRouter>
    )

    fireEvent.click(await screen.findByRole('tab', { name: /2 分章写作/ }))
    expect(screen.queryByText('历史材料建议')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '生成本章草稿' }))
    const completed = await screen.findByText('内容生成完毕！')
    expect(completed.parentElement).toHaveClass('fund-generation-action')
    expect(screen.getAllByText('未审批但已经持久化的草稿').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: '下一章节' }))
    expect(screen.queryByText('内容生成完毕！')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '上一章节' }))
    expect((await screen.findAllByText('未审批但已经持久化的草稿')).length).toBeGreaterThan(0)
  })

  it('reopens the clicked source chapter from the approved full draft preview', async () => {
    let reopened = false
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.includes('/ai/human-tasks?proposal_id=88')) return jsonResponse({ tasks: [] })
      if (path.endsWith('/ai/proposals/88/full-draft')) {
        return jsonResponse({
          draft_text: '# 全文\n\n## 第一章 概述\n概述正文\n\n## 第三章 实施计划\n实施计划正文',
          version: 1,
          approval_status: 'draft',
          section_keys: ['summary', 'plan'],
        })
      }
      if (path.endsWith('/ai/sections/882/reopen') && method === 'POST') {
        reopened = true
        return jsonResponse({
          section_id: 882,
          section_key: 'plan',
          state: 'draft',
          locked: false,
          draft_text: '实施计划正文',
        })
      }
      if (path.includes('/evidence')) return jsonResponse({ evidence: [] })
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 88,
          author: 1,
          content: {
            meta: {
              title: '全文追溯测试',
              user_setup: { ready: true },
              intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' },
            },
            sections: {},
          },
          sections: [
            { id: 881, key: 'summary', title: '第一章 概述', order: 0, state: 'approved', locked: true, draft_content: '概述正文', approved_content: '概述正文', inputs: [], answers: {} },
            { id: 882, key: 'plan', title: '第三章 实施计划', order: 1, state: 'approved', locked: true, draft_content: '实施计划正文', approved_content: '实施计划正文', inputs: [], answers: {} },
          ],
          schema_version: 'v1',
        }}
      />,
    )

    fireEvent.click(screen.getByRole('tab', { name: /4 定稿与导出/ }))
    fireEvent.click(await screen.findByRole('button', { name: '第三章 实施计划' }))

    await waitFor(() => expect(reopened).toBe(true))
    expect(screen.getByRole('tab', { name: /3 人工审核与修订/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/第 2 章，共 2 章/)).toBeInTheDocument()
    expect(screen.getByTestId('current-draft-editor')).not.toBeDisabled()
  })

  it('shows only the final preview after the full draft is approved', async () => {
    global.fetch = vi.fn(async (url) => {
      const path = String(url)
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.includes('/ai/human-tasks?proposal_id=90')) return jsonResponse({ tasks: [] })
      if (path.endsWith('/ai/proposals/90/full-draft')) {
        return jsonResponse({
          draft_text: '# 全文\n\n## 第一章 概述\n审批后的全文内容',
          version: 2,
          approval_status: 'approved',
          section_keys: ['summary'],
        })
      }
      if (path.includes('/evidence')) return jsonResponse({ evidence: [] })
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 90,
          author: 1,
          content: {
            meta: {
              title: '全文审批预览测试',
              user_setup: { ready: true },
              intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' },
            },
            sections: {},
          },
          sections: [
            { id: 901, key: 'summary', title: '第一章 概述', order: 0, state: 'approved', locked: true, draft_content: '审批后的全文内容', approved_content: '审批后的全文内容', inputs: [], answers: {} },
          ],
          schema_version: 'v1',
        }}
      />,
    )

    fireEvent.click(screen.getByRole('tab', { name: /4 定稿与导出/ }))
    expect(await screen.findByText('定稿预览')).toBeInTheDocument()
    expect(screen.queryByText('审批后全文草稿')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.fund-full-draft-workspace')).toHaveLength(1)
  })

  it('revises the full draft from the manual review request with visible feedback', async () => {
    let resolveRevision
    const revisionResponse = new Promise(resolve => { resolveRevision = resolve })
    let revisedRequest = null
    let fullDraft = '# 全文\n\n## 第一章 概述\n原始全文内容'
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.includes('/ai/human-tasks?proposal_id=94')) return jsonResponse({ tasks: [] })
      if (path.endsWith('/ai/proposals/94/full-draft') && method === 'GET') {
        return jsonResponse({ draft_text: fullDraft, version: 1, approval_status: 'draft', section_keys: ['summary'] })
      }
      if (path.endsWith('/ai/revise') && method === 'POST') {
        revisedRequest = JSON.parse(options.body)
        return revisionResponse
      }
      if (path.endsWith('/ai/proposals/94/full-draft') && method === 'PATCH') {
        fullDraft = JSON.parse(options.body).draft_text
        return jsonResponse({ draft_text: fullDraft, version: 2, approval_status: 'draft', section_keys: ['summary'] })
      }
      if (path.includes('/evidence')) return jsonResponse({ evidence: [] })
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 94,
          author: 1,
          content: { meta: { title: '全文手动修订测试', user_setup: { ready: true }, intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' } }, sections: {} },
          sections: [{ id: 941, key: 'summary', title: '第一章 概述', state: 'approved', locked: true, draft_content: '原始全文内容', approved_content: '原始全文内容', inputs: [], answers: {} }],
          schema_version: 'v1',
        }}
      />,
    )

    fireEvent.click(screen.getByRole('tab', { name: /4 定稿与导出/ }))
    await screen.findByText('审批后全文草稿')
    fireEvent.change(screen.getByPlaceholderText('例如：统一各章术语，补充章节衔接，并删除重复论述'), {
      target: { value: '统一术语并补充章节衔接。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '按要求修订全文' }))

    expect((await screen.findAllByText('深度思考中，正在按照要求修订全文。')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /正在修订全文/ })).toBeDisabled()
    resolveRevision(jsonResponse({ draft_text: '# 全文\n\n## 第一章 概述\n手动修订后的全文内容' }))

    await waitFor(() => expect(revisedRequest).toMatchObject({
      proposal_id: 94,
      draft_scope: 'full',
      base_text: '# 全文\n\n## 第一章 概述\n原始全文内容',
      change_request: '统一术语并补充章节衔接。',
    }))
    expect(await screen.findByText('手动修订后的全文内容')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('例如：统一各章术语，补充章节衔接，并删除重复论述')).toHaveValue('')
  })

  it('revises the full draft from accepted pre-review advice with distinct feedback', async () => {
    let resolveRevision
    const revisionResponse = new Promise(resolve => { resolveRevision = resolve })
    let revisedRequest = null
    let fullDraft = '# 全文\n\n## 第一章 概述\n原始全文内容'
    const review = {
      summary: '全文逻辑完整，但章节过渡需要加强。',
      strengths: ['章节结构清晰。'],
      issues: [{ problem: '章节衔接不足。', reason: '前后内容缺少承接。', direction: '补充过渡段。' }],
      revision_request: '补充章节之间的过渡段，并统一术语。',
    }
    let task = {
      id: 95,
      thread_id: 'full-draft-95',
      node: 'final_export_confirmation',
      status: 'pending',
      input: { kind: 'full_draft', draft_title: '审批后全文草稿', draft_text: fullDraft, draft_version: 1 },
      model_output: {},
      decision: {},
    }
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      if (path.includes('/ai/human-tasks?proposal_id=95')) return jsonResponse({ tasks: task.status === 'pending' ? [task] : [] })
      if (path.endsWith('/ai/proposals/95/full-draft') && method === 'GET') {
        return jsonResponse({ draft_text: fullDraft, version: 1, approval_status: 'draft', section_keys: ['summary'] })
      }
      if (path.endsWith('/ai/human-tasks/95/pre-review') && method === 'POST') {
        const body = options.body ? JSON.parse(options.body) : {}
        if (body.action === 'accept') {
          task = { ...task, model_output: { pre_review: review, pre_review_status: 'accepted' } }
        } else if (body.action === 'dismiss') {
          task = { ...task, status: 'ready_after_edit', model_output: {} }
        } else {
          task = { ...task, model_output: { pre_review: review, pre_review_status: 'pending', pre_review_request_count: 1 } }
        }
        return jsonResponse(task)
      }
      if (path.endsWith('/ai/revise') && method === 'POST') {
        revisedRequest = JSON.parse(options.body)
        return revisionResponse
      }
      if (path.endsWith('/ai/proposals/95/full-draft') && method === 'PATCH') {
        fullDraft = JSON.parse(options.body).draft_text
        task = { ...task, status: 'ready_after_edit' }
        return jsonResponse({ draft_text: fullDraft, version: 2, approval_status: 'draft', section_keys: ['summary'] })
      }
      if (path.includes('/evidence')) return jsonResponse({ evidence: [] })
      return jsonResponse({})
    })

    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 95,
          author: 1,
          content: { meta: { title: '全文预评审修订测试', user_setup: { ready: true }, intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' } }, sections: {} },
          sections: [{ id: 951, key: 'summary', title: '第一章 概述', state: 'approved', locked: true, draft_content: '原始全文内容', approved_content: '原始全文内容', inputs: [], answers: {} }],
          schema_version: 'v1',
        }}
      />,
    )

    fireEvent.click(screen.getByRole('tab', { name: /4 定稿与导出/ }))
    await screen.findByTestId('full-draft-preview')
    fireEvent.click(await screen.findByRole('button', { name: '全文预评审' }))
    expect(await screen.findByRole('dialog', { name: '全文预评审' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '采纳' }))
    expect(await screen.findByText('是否需要根据评审内容重新修改草稿？')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '是' }))

    expect((await screen.findAllByText('已采纳全文预评审结果，正在根据建议重新优化全文。')).length).toBeGreaterThan(0)
    resolveRevision(jsonResponse({ draft_text: '# 全文\n\n## 第一章 概述\n预评审修订后的全文内容' }))

    await waitFor(() => expect(revisedRequest).toMatchObject({
      proposal_id: 95,
      draft_scope: 'full',
      base_text: '# 全文\n\n## 第一章 概述\n原始全文内容',
      change_request: '补充章节之间的过渡段，并统一术语。',
    }))
    expect(await screen.findByText('预评审修订后的全文内容')).toBeInTheDocument()
  })

  it('locks chapter planning after a final draft has been generated', () => {
    render(
      <AuthorPanel
        token='token'
        orgId='1'
        proposal={{
          id: 89,
          author: 1,
          final_markdown: '# 已定稿',
          content: {
            meta: {
              title: '定稿锁定测试',
              user_setup: { ready: true },
              intake_snapshot: { task_mode: 'plan_from_scratch', quality_level: 'quick' },
            },
            sections: {},
          },
          sections: [],
          schema_version: 'v1',
        }}
      />,
    )

    expect(screen.getByRole('button', { name: '生成章节规划' })).toBeDisabled()
    expect(screen.getByText('最终定稿已生成，章节规划已锁定。')).toBeInTheDocument()
  })

  it('does not leak a completed project plan into another project', async () => {
    const proposals = [
      {
        id: 61,
        org: 1,
        author: 1,
        state: 'draft',
        content: { meta: { title: '项目一' }, sections: {} },
        schema_version: 'v1',
        sections: [
          { id: 601, key: 'only', title: '项目一章节', order: 0, state: 'draft', draft_content: '项目一专属草稿', approved_content: '', inputs: [], answers: {} },
        ],
      },
      {
        id: 62,
        org: 1,
        author: 1,
        state: 'draft',
        content: { meta: { title: '项目二' }, sections: {} },
        schema_version: 'v1',
        sections: [],
      },
    ]
    global.fetch = vi.fn(async (url) => {
      const path = String(url)
      if (path.endsWith('/proposals/')) return jsonResponse(clone(proposals))
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({ items: [] })
    })

    render(
      <MemoryRouter>
        <Proposals token="token" selectedOrgId="1" />
      </MemoryRouter>
    )

    fireEvent.click(await screen.findByRole('tab', { name: /2 分章写作/ }))
    expect(await screen.findByText('项目一专属草稿')).toBeInTheDocument()
    fireEvent.click(screen.getByText('项目二'))

    await waitFor(() => {
      expect(screen.queryByText('项目一专属草稿')).not.toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /2 分章写作/ })).toBeDisabled()
    })
  })
})
