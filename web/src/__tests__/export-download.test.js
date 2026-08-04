import { afterEach, describe, expect, it, vi } from 'vitest'

import { downloadExport } from '../lib/core.js'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('authenticated export download', () => {
  it('downloads the protected export with the current workspace headers', async () => {
    vi.useFakeTimers()
    const createObjectURL = vi.fn(() => 'blob:export')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    global.fetch = vi.fn(async () => new Response('export content', {
      status: 200,
      headers: { 'Content-Disposition': 'attachment; filename=proposal.md' },
    }))

    await downloadExport('/api/exports/5/download', { token: 'token', orgId: '9' })

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/exports/5/download'),
      expect.objectContaining({ headers: { Authorization: 'Bearer token', 'X-Org-ID': '9' } }),
    )
    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    vi.runAllTimers()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export')
  })
})
