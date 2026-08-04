import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { Proposals } from '../main.jsx'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}


describe('Proposal title editing', () => {
  it('uses the selected application system when creating a proposal', async () => {
    const items = []
    let createBody = null
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/proposals/') && method === 'GET') return jsonResponse(items)
      if (path.endsWith('/proposals/') && method === 'POST') {
        createBody = JSON.parse(options.body)
        const created = {
          id: 91,
          author: 1,
          state: 'draft',
          content: createBody.content,
          sections: [],
          schema_version: 'v1',
        }
        items.push(created)
        return jsonResponse(created, 201)
      }
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({})
    })

    render(
      <MemoryRouter>
        <Proposals token="token" />
      </MemoryRouter>
    )

    expect(await screen.findByText('本项为必填。选择后，系统会按对应申报体系调整写作侧重点。')).toBeInTheDocument()
    fireEvent.change(await screen.findByPlaceholderText('输入新项目标题'), {
      target: { value: '小样本调制识别研究' },
    })
    fireEvent.click(screen.getByLabelText('省基金'))
    fireEvent.click(screen.getByRole('button', { name: '新建申请' }))

    await waitFor(() => {
      expect(createBody.content.meta.title).toBe('小样本调制识别研究')
      expect(createBody.content.meta.application_system).toBe('provincial')
    })
    expect(await screen.findByText('小样本调制识别研究')).toBeInTheDocument()
  })

  it('requires an application system before creating a proposal', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/proposals/') && method === 'GET') return jsonResponse([])
      return jsonResponse({})
    })

    render(
      <MemoryRouter>
        <Proposals token="token" />
      </MemoryRouter>
    )

    fireEvent.change(await screen.findByPlaceholderText('输入新项目标题'), {
      target: { value: '未选择体系的项目' },
    })
    fireEvent.click(screen.getByRole('button', { name: '新建申请' }))

    expect(alertSpy).toHaveBeenCalledWith('请选择申报体系')
    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining('/proposals/'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('edits and saves an existing proposal title', async () => {
    const proposal = {
      id: 92,
      author: 1,
      state: 'draft',
      content: { meta: { title: '旧标题' }, sections: {} },
      sections: [],
      schema_version: 'v1',
    }
    let patchBody = null
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = options.method || 'GET'
      if (path.endsWith('/proposals/') && method === 'GET') return jsonResponse([proposal])
      if (path.endsWith('/proposals/92/') && method === 'PATCH') {
        patchBody = JSON.parse(options.body)
        proposal.content = patchBody.content
        return jsonResponse(proposal)
      }
      if (path.endsWith('/me')) return jsonResponse({ user: { id: 1, username: 'tester' } })
      return jsonResponse({})
    })

    render(
      <MemoryRouter>
        <Proposals token="token" />
      </MemoryRouter>
    )

    const titleInput = await screen.findByLabelText('项目标题')
    fireEvent.change(titleInput, { target: { value: '新的基金项目标题' } })
    fireEvent.click(screen.getByRole('button', { name: '保存标题' }))

    await waitFor(() => {
      expect(patchBody.content.meta.title).toBe('新的基金项目标题')
    })
  })
})
