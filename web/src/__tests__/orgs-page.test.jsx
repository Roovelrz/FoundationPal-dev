import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import OrgsPage from '../pages/OrgsPage.jsx'

// Simple Response polyfill for Node test env
class Response {
  constructor(body, init) {
    this._body = body
    this.status = init?.status || 200
    this.ok = this.status >= 200 && this.status < 300
  }
  async json() { try { return JSON.parse(this._body || '{}') } catch { return {} } }
}

describe('OrgsPage', () => {
  it('uses local workspace order, keeps the future members entry, and confirms deletion', async () => {
    const onSelectOrg = vi.fn()
    const onOrgsChanged = vi.fn()
    global.fetch = vi.fn((url, opts) => {
      const u = url.toString()
      if (u.endsWith('/api/orgs/')) {
        return Promise.resolve(new Response(JSON.stringify([
          { id: 4, name: '国自然', description: 'A' },
          { id: 9, name: '省基金', description: 'B' }
        ]), { status: 200 }))
      }
      if (u.includes('/api/orgs/') && u.endsWith('/members/')) {
        return Promise.resolve(new Response(JSON.stringify([{ user: { id: 7, username: 'm1' }, role: 'member' }]), { status: 200 }))
      }
      if (u.endsWith('/api/orgs/4/') && opts?.method === 'DELETE') {
        return Promise.resolve(new Response('', { status: 204 }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })

    render(
      <OrgsPage
        token="t"
        activeOrgId="4"
        onSelectOrg={onSelectOrg}
        onOrgsChanged={onOrgsChanged}
        onClose={vi.fn()}
      />
    )

    expect(await screen.findByRole('heading', { name: '工作区管理' })).toBeInTheDocument()
    expect(screen.getByText('工作区 1：国自然')).toBeInTheDocument()
    expect(screen.getByText('工作区 2：省基金')).toBeInTheDocument()
    expect(screen.queryByText(/Pending invites|Transfer ownership/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: '成员' })[0])
    expect(await screen.findByText('m1')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: '删除' })[0])
    expect(screen.getByRole('heading', { name: '确认删除工作区' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/orgs/4/', expect.objectContaining({ method: 'DELETE' }))
      expect(onOrgsChanged).toHaveBeenCalled()
    })
  })
})
