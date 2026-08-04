import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AuthorPanel } from '../pages/Dashboard.jsx'

describe('AuthorPanel workspace recovery', () => {
  it('restores saved questions, answers, and draft without replanning', async () => {
    const proposal = {
      id: 12,
      author: 2,
      schema_version: 'v1',
      content: { meta: { title: 'Recovered proposal' }, sections: {} },
      sections: [
        {
          id: 1201,
          key: 'summary',
          title: 'Summary',
          state: 'drafted',
          questions: ['Saved question'],
          answers: { 'Saved question': 'Saved answer' },
          draft_content: '# Saved draft',
          approved_content: '',
          locked: false,
        },
      ],
    }

    global.fetch = vi.fn(async () => new Response(JSON.stringify({
      user: { id: 2, username: 'demo' },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))

    render(<AuthorPanel token="t" orgId="" proposal={proposal} onSaved={() => {}} />)

    const writingTab = await screen.findByRole('tab', { name: /^2 / })
    fireEvent.click(writingTab)

    expect(await screen.findByText(/Saved question/)).toBeInTheDocument()
    expect(screen.getByDisplayValue('Saved answer')).toBeInTheDocument()
    expect(screen.getByText('Saved draft')).toBeInTheDocument()

    await waitFor(() => {
      expect(global.fetch.mock.calls.some(([url]) => String(url).includes('/api/ai/plan'))).toBe(false)
    })
  })
})
