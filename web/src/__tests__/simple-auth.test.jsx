import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { LoginPage, RegisterPage } from '../main.jsx'

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


describe('Simple username authentication', () => {
  it('shows only username login and account creation actions', () => {
    render(
      <MemoryRouter>
        <LoginPage token="" setToken={() => {}} />
      </MemoryRouter>
    )

    expect(screen.getByLabelText('用户名')).toBeInTheDocument()
    expect(screen.getByLabelText('密码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建新用户' })).toBeInTheDocument()
    expect(screen.queryByText(/Google|GitHub|Facebook|Upgrade|Pro/)).not.toBeInTheDocument()
  })

  it('logs in with username and password', async () => {
    const setToken = vi.fn()
    global.fetch = vi.fn(async (url) => (
      String(url).endsWith('/token')
        ? jsonResponse({ access: 'access-token' })
        : jsonResponse([{ id: 1, name: '工作区' }])
    ))

    render(
      <MemoryRouter>
        <LoginPage token="" setToken={setToken} />
      </MemoryRouter>
    )

    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'tester' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'strong-pass' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => expect(setToken).toHaveBeenCalledWith('access-token'))
  })

  it('creates a user and signs in directly', async () => {
    const setToken = vi.fn()
    global.fetch = vi.fn(async () => jsonResponse({
      access: 'new-access-token',
      org: { id: 7, name: 'new-user的工作区' },
    }, 201))

    render(
      <MemoryRouter>
        <RegisterPage setToken={setToken} />
      </MemoryRouter>
    )

    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'new-user' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'strong-pass' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'strong-pass' } })
    fireEvent.click(screen.getByRole('button', { name: '创建并登录' }))

    await waitFor(() => expect(setToken).toHaveBeenCalledWith('new-access-token'))
  })
})
