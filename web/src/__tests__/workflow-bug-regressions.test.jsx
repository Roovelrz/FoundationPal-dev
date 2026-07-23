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
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/proposals/') && method === 'GET') return jsonResponse([])
      if (path.endsWith('/proposals/') && method === 'POST') {
        createOrgHeader = options.headers['X-Org-ID']
        return jsonResponse({
          id: 21,
          org: 2,
          state: 'draft',
          content: JSON.parse(options.body).content,
          sections: [],
        }, 201)
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
    fireEvent.click(screen.getByRole('button', { name: '新建申请' }))

    await waitFor(() => expect(createOrgHeader).toBe('2'))
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

  it('shows thinking and completion feedback beside generation', async () => {
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
          content: { meta: { title: '反馈测试' }, sections: {} },
          sections: [],
          schema_version: 'v1',
        }}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '生成章节规划' }))
    expect(await screen.findByText('正在深度思考中')).toBeInTheDocument()
    resolvePlan(jsonResponse({
      schema_version: 'v1',
      sections: [{ id: 'summary', title: '摘要', inputs: [] }],
    }))
    expect(await screen.findByText('内容生成完毕！')).toBeInTheDocument()
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
    expect(await screen.findByText('内容生成完毕！')).toBeInTheDocument()
    expect(screen.getAllByText('未审批但已经持久化的草稿').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: '下一章节' }))
    fireEvent.click(screen.getByRole('button', { name: '上一章节' }))
    expect((await screen.findAllByText('未审批但已经持久化的草稿')).length).toBeGreaterThan(0)
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
