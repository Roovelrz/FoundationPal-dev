import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { Phase12Workspace } from '../components/Phase12Workspace.jsx'

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('普通用户项目基础信息', () => {
  it('only exposes required materials and saves the simplified setup', async () => {
    const onReady = vi.fn()
    let payload = null
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      if (path.endsWith('/ai/proposals/1/setup') && (options.method || 'GET') === 'GET') {
        return jsonResponse({
          proposal_id: 1,
          ready: false,
          research_direction: '',
          core_problem: '',
          guideline_ready: false,
          guideline_count: 0,
          evidence_count: 0,
        })
      }
      if (path.endsWith('/ai/proposals/1/setup') && options.method === 'POST') {
        payload = JSON.parse(options.body)
        return jsonResponse({
          proposal_id: 1,
          ready: true,
          research_direction: payload.research_direction,
          core_problem: payload.core_problem,
          guideline_text: payload.guideline_text,
          guideline_ready: true,
          guideline_count: 1,
          evidence_count: 1,
        })
      }
      return jsonResponse({})
    })

    render(<Phase12Workspace proposal={{ id: 1 }} token="token" orgId="1" onReady={onReady} />)

    await screen.findByTestId('project-setup')
    expect(screen.getByLabelText('研究方向与核心问题')).toBeInTheDocument()
    expect(screen.getByLabelText('基金指南或申报要求')).toBeInTheDocument()
    expect(screen.getByText('提供清晰的基金指南或申报要求，有助于提升申报书质量。可填写文本或上传可解析的指南文件，任选其一即可。本项为必填；若暂无相关材料，可如实填写：不清楚。')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('粘贴与本项目相关的指南、通知或申报要求；提供清晰的指南和要求有助于提升申报书质量，若暂无材料可填写：不清楚')).toBeInTheDocument()
    expect(document.querySelectorAll('.fund-required-marker')).toHaveLength(3)
    expect(screen.queryByText(/Grill|ProposalBrief|规则包审核|新规则材料资源编号/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '保存基础信息并继续' }))
    expect(await screen.findByText(/请填写带红色星号/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('研究方向与核心问题'), { target: { value: '低信噪比自动调制识别' } })
    fireEvent.change(screen.getByLabelText('基金指南或申报要求'), { target: { value: '说明研究目标、内容与技术路线。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存基础信息并继续' }))

    await waitFor(() => expect(payload).toEqual({
      research_direction: '低信噪比自动调制识别',
      core_problem: '',
      guideline_text: '说明研究目标、内容与技术路线。',
    }))
    expect(screen.getByLabelText('基金指南或申报要求')).toHaveValue('说明研究目标、内容与技术路线。')
    expect(onReady).toHaveBeenCalledWith(expect.objectContaining({ ready: true }))
  })

  it('keeps unfinished fields and shows every saved file after uploading a guide', async () => {
    let setupReads = 0
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      if (path.endsWith('/ai/proposals/1/setup') && (options.method || 'GET') === 'GET') {
        setupReads += 1
        return jsonResponse({
          proposal_id: 1,
          ready: false,
          research_direction: '',
          core_problem: '',
          guideline_ready: setupReads > 1,
          guideline_count: setupReads > 1 ? 1 : 0,
          evidence_count: 0,
          guideline_files: setupReads > 1 ? [{ id: 7, name: 'guide-a.txt', uploaded_at: '2026-07-29T00:00:00Z' }] : [],
          evidence_files: [],
        })
      }
      if (path.endsWith('/files') && options.method === 'POST') {
        return jsonResponse({ resource_id: 7, material_kind: 'guideline' })
      }
      return jsonResponse({})
    })

    render(<Phase12Workspace proposal={{ id: 1 }} token="token" orgId="1" />)

    const direction = await screen.findByLabelText('研究方向与核心问题')
    const problem = screen.getByLabelText('深化描述核心科学问题')
    const guide = screen.getByLabelText('基金指南或申报要求')
    fireEvent.change(direction, { target: { value: 'Keep this direction' } })
    fireEvent.change(problem, { target: { value: 'Keep this problem' } })
    fireEvent.change(guide, { target: { value: 'Keep this pasted guide' } })
    fireEvent.change(screen.getByTestId('guideline-file-input'), {
      target: { files: [new File(['guide text'], 'guide-a.txt', { type: 'text/plain' })] },
    })

    await waitFor(() => expect(screen.getByText('guide-a.txt')).toBeInTheDocument())
    expect(direction).toHaveValue('Keep this direction')
    expect(problem).toHaveValue('Keep this problem')
    expect(guide).toHaveValue('Keep this pasted guide')
  })
})
